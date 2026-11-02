import json

import pytest
from adapter import siril as adapter

from .adapter_test_helpers import build, script


@pytest.mark.parametrize('selection,expected', [('absent', None), (None, 'boxselect -clear'), ([0, 0, 1, 1], 'boxselect 0 0 1 1')])
def test_selection_omission_null_and_zero_are_distinct(tmp_path, selection, expected):
    runtime = {} if selection == 'absent' else {'selection': selection}
    plan = build(tmp_path, 'autostretch', values={'runtime': json.dumps(runtime)})
    if expected:
        assert expected in script(plan)
    else:
        assert 'boxselect' not in script(plan)


def test_compression_and_thread_limit_are_explicit_and_scoped(tmp_path):
    runtime = {'threads': 2, 'compression': {'enabled': True, 'type': 'gzip1', 'quantisation': 0}}
    plan = build(tmp_path, 'autostretch', values={'runtime': json.dumps(runtime)}, preview=True, prepare_sample=True)
    assert 'setcompress 1 -type=gzip1 0' in script(plan)
    assert plan.thread_limit == 2
    assert plan.linear_sample.name == 'linear.fit.fz'
    assert plan.outputs['image'].files[0].path.name == 'result.fit.fz'


@pytest.mark.parametrize('value', [{'threads': 0}, {'output_bits': 16.0}, {'compression': None}, {'settings': {'core.wd': 'C:/outside'}}, {'selection': [0, 0, 0, 1]}])
def test_invalid_runtime_controls_fail_before_process_launch(tmp_path, value):
    with pytest.raises(ValueError):
        build(tmp_path, 'autostretch', values={'runtime': json.dumps(value)})


def test_progress_idle_zero_is_not_reported_as_processing_completion():
    result = adapter.parse_progress('progress: Sequence processing succeeded., 0.00%\n')
    assert result.progress == 0
    assert result.phase == 'Sequence processing succeeded.'


@pytest.mark.parametrize('runtime_value,expected', [({}, None), ({'selection': None}, 'boxselect -clear'),
    ({'selection': [0, 0, 1, 1]}, 'boxselect 0 0 1 1')])
def test_runtime_selection_preserves_omission_null_and_zero(tmp_path, runtime_value, expected):
    build(tmp_path, 'autostretch', values={'runtime': json.dumps(runtime_value)})
    script = (tmp_path / 'work/operation.ssf').read_text()
    if expected is None:
        assert 'boxselect' not in script
    else:
        assert expected in script
