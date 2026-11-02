import json

import pytest
from adapter import arguments
from adapter import siril as adapter

from .adapter_test_helpers import build, script


def test_live_preview_keeps_an_unstretched_sample_before_processing(tmp_path):
    plan = build(tmp_path, 'autostretch', preview=True, prepare_sample=True)
    text = script(plan)
    assert text.index('resample -maxdim=1024 -interp=area') < text.index('linear.fit') < text.index('autostretch ')
    assert plan.linear_sample == tmp_path / 'work/linear.fit'
    assert plan.temporary_directory == tmp_path / 'work/tmp'
    assert len(plan.outputs['image'].files) == 1


def test_only_supported_paths_and_script_patterns_are_accepted(tmp_path):
    with pytest.raises(ValueError):
        arguments.quoted(tmp_path / 'quote".fit')
    with pytest.raises(ValueError):
        arguments.token('value\nexit')
    with pytest.raises(ValueError, match='relative'):
        build(tmp_path, 'pyscript', sources={}, values={'output_files': '[{"pattern":"../outside.fit","format":"fits"}]'})
    with pytest.raises(ValueError, match='Unsupported operation'):
        adapter.build_plan('unknown', {}, {}, tmp_path)


def test_result_layout_must_belong_to_the_requested_operation(tmp_path):
    plan = build(tmp_path, 'autostretch')
    work = tmp_path / 'work'
    layout_path = work / 'layout.json'
    layout = json.loads(layout_path.read_text())
    layout['operation_id'] = 'asinh'
    layout_path.write_text(json.dumps(layout))
    log = work / 'process.log'
    log.write_text('')
    with pytest.raises(ValueError, match='another Siril operation'):
        adapter.parse_result('autostretch', work, plan, log)


@pytest.mark.parametrize('values, box', [({}, '0 0 32 32'), ({'selection': '[3,4,20,21]'}, '3 4 20 21')])
def test_psf_builds_a_typed_selection_without_changing_input(tmp_path, values, box):
    plan = build(tmp_path, 'psf', values=values)
    assert 'boxselect ' + box in script(plan)
    assert 'psf' in script(plan)
    assert (tmp_path / 'original.fit').read_bytes() == b'protected original'
