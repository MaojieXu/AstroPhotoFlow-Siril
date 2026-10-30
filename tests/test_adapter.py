import hashlib
import importlib.util
import json
from pathlib import Path

from astrophotoflow.contracts.software import ParameterDefinition

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('siril_adapter', ROOT / 'adapter/siril.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def defaults(operation):
    values = {item['schema']['name']: item['schema']['default'] for item in adapter.RECIPES[operation]['parameters']}
    return {**values, 'runtime': '{}'}


def build(tmp_path, operation, *, sources=None, values=None, **options):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    if sources is None:
        source = tmp_path / 'original.fit'
        source.write_bytes(b'protected original')
        sources = {'image': [source]}
    return adapter.build_plan(operation, sources, {**defaults(operation), **(values or {})}, work, **options)


def script(plan):
    return Path(plan.arguments[-1]).read_text(encoding='utf-8')


def test_formal_script_preserves_fixed_order_negative_and_zero(tmp_path):
    sources = [tmp_path / 'first.fit', tmp_path / 'second.fit']
    for source in sources:
        source.write_bytes(b'original')
    before = [hashlib.sha256(source.read_bytes()).hexdigest() for source in sources]
    plan = build(tmp_path, 'autostretch', sources={'image': sources},
                 values={'linked': True, 'shadowsclip': -4.2, 'targetbg': 0})
    text = script(plan)
    assert text.index('first.fit') < text.index('second.fit')
    assert text.count('autostretch -linked "-4.2000000000000002" "0"') == 2
    assert 'resample' not in text
    assert len(plan.outputs['image'].files) == 2
    assert all(file.path.is_relative_to(tmp_path / 'work') and file.path not in sources for file in plan.outputs['image'].files)
    assert [hashlib.sha256(source.read_bytes()).hexdigest() for source in sources] == before


def test_live_preview_keeps_an_unstretched_sample_before_processing(tmp_path):
    plan = build(tmp_path, 'autostretch', preview=True, prepare_sample=True)
    text = script(plan)
    assert text.index('resample -maxdim=1024 -interp=area') < text.index('linear.fit') < text.index('autostretch ')
    assert plan.linear_sample == tmp_path / 'work/linear.fit'
    assert plan.temporary_directory == tmp_path / 'work/tmp'
    assert len(plan.outputs['image'].files) == 1


def test_optional_numeric_zero_is_sent_only_when_explicitly_enabled(tmp_path):
    source = tmp_path / 'source.fit'
    source.write_bytes(b'science')
    plan = build(tmp_path, 'rl', sources={'image': [source], 'psf': [source]}, values={'use_regularisation': True, 'regularisation': 0})
    assert '"-alpha=0"' in script(plan)
    other = tmp_path / 'other'; other.mkdir()
    disabled = build(other, 'rl', sources={'image': [source], 'psf': [source]}, values={'use_regularisation': False, 'regularisation': 0})
    assert '-alpha=' not in script(disabled)


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


@pytest.mark.parametrize('operation,suffix', [('savebmp', '.bmp'), ('savejpg', '.jpg'), ('savepng', '.png'), ('savejxl', '.jxl'), ('savetif32', '.tif')])
def test_export_commands_receive_a_stem_when_siril_appends_the_suffix(tmp_path, operation, suffix):
    plan = build(tmp_path, operation)
    assert plan.outputs['file'].files[0].path.name == 'result' + suffix
    line = next(line for line in script(plan).splitlines() if line.startswith(operation + ' '))
    assert ('result' + suffix) not in line


def test_fill_can_omit_its_rectangle_without_treating_zero_as_absence(tmp_path):
    plan = build(tmp_path, 'fill', values={'value': 0, 'use_rectangle': False})
    assert '\nfill "0"\n' in script(plan)
    other = tmp_path / 'rectangle'; other.mkdir()
    explicit = build(other, 'fill', values={'value': 0, 'use_rectangle': True, 'x': 0, 'y': 0, 'width': 1, 'height': 1})
    assert '\nfill "0" 0 0 1 1\n' in script(explicit)


@pytest.mark.parametrize('value', [{'threads': 0}, {'output_bits': 16.0}, {'compression': None}, {'settings': {'core.wd': 'C:/outside'}}, {'selection': [0, 0, 0, 1]}])
def test_invalid_runtime_controls_fail_before_process_launch(tmp_path, value):
    with pytest.raises(ValueError):
        build(tmp_path, 'autostretch', values={'runtime': json.dumps(value)})


def test_sequence_metadata_is_copied_and_rebound_without_writable_original_links(tmp_path):
    prior = tmp_path / 'prior'; prior.mkdir()
    original = prior / 'input_00001.fit'; original.write_bytes(b'protected science')
    descriptor = prior / 'input_.seq'
    descriptor.write_text(f"S '{(prior / 'input_').as_posix()}' 1 1 1 5 -1 6 0 0 0\nL 1\nI 1 1\n", encoding='utf-8')
    build(tmp_path, 'sequpdate_key', sources={'image': [original]},
          values={'key': 'TESTKEY', 'value': '1'}, supporting_sources={'image': [descriptor]})
    local = tmp_path / 'work/sequence/input_00001.fit'
    local.write_bytes(b'updated FITS header')
    assert original.read_bytes() == b'protected science'
    assert "S 'input_'" in (tmp_path / 'work/sequence/input_.seq').read_text(encoding='utf-8')
    assert str(prior) not in (tmp_path / 'work/sequence/input_.seq').read_text(encoding='utf-8')


def test_missing_selected_sequence_frame_is_not_complete_success(tmp_path):
    plan = build(tmp_path, 'seqcrop')
    folder = tmp_path / 'work/sequence'
    (folder / 'result_input_.seq').write_text("S 'result_input_' 1 2 2 5 -1 6 0 0 0\nL 1\nI 1 1\nI 2 1\n", encoding='utf-8')
    (folder / 'result_input_00001.fit').write_bytes(b'one frame')
    log = tmp_path / 'work/process.log'; log.write_text('log: Script execution finished successfully.\n')
    with pytest.raises(ValueError, match='selected sequence output frame is missing'):
        adapter.parse_result('seqcrop', tmp_path / 'work', plan, log)


def test_packed_fits_sequence_is_copied_without_loading_only_its_first_frame(tmp_path):
    source = tmp_path / 'packed.fit'; source.write_bytes(b'complete multi-frame container')
    plan = build(tmp_path, 'seqstat', sources={'image': [source]}, source_metadata={'image': [
        {'reference_index': 0, 'selection': {'kind': 'whole_file'},
         'scientific_metadata': {'format': 'fits', 'frame_count': 3, 'hdu_count': 3, 'selected_hdu': 0}}
    ]})
    assert (tmp_path / 'work/sequence/input.fit').read_bytes() == source.read_bytes()
    assert 'input_00001.fit' not in script(plan)
    assert 'getref "input"' in script(plan)


def test_histogram_aggregation_preserves_counts_and_rejects_truncated_bins(tmp_path):
    path = tmp_path / 'histogram.dat'
    path.write_text(''.join(f'{index} {2 if index == 0 else 3 if index == 127 else 0}\n' for index in range(65536)), encoding='utf-8')
    result = adapter._histogram(path)
    assert result.kind == 'series' and len(result.rows) == 512
    assert result.rows[0][1] == 5 and sum(row[1] for row in result.rows) == 5
    path.write_text('0 5\n', encoding='utf-8')
    with pytest.raises(ValueError, match='incomplete'):
        adapter._histogram(path)


def test_bad_pixel_table_retains_first_record_and_zero_coordinates(tmp_path):
    path = tmp_path / 'pixels.lst'; path.write_text('P 0 0 H\nP 1 2 C\n', encoding='utf-8')
    result = adapter._table(path, 'find_hot')
    assert result.rows == [['P', 0, 0, 'H'], ['P', 1, 2, 'C']]
    assert result.values['row_count'] == 2


def test_catalogue_identifiers_keep_all_digits_in_web_analysis(tmp_path):
    path = tmp_path / 'catalogue.csv'
    path.write_text('source_id,flux,flag\n9007199254740993,0.5,0\n-9007199254740993,1.25,1\n', encoding='utf-8')
    result = adapter._table(path, 'conesearch')
    assert result.rows == [['9007199254740993', .5, 0], ['-9007199254740993', 1.25, 1]]


def test_getref_ignores_unrelated_supporting_star_tables(tmp_path):
    plan = build(tmp_path, 'getref')
    folder = tmp_path / 'work/sequence'
    (folder / 'input_.seq').write_text("S 'input_' 1 1 1 5 -1 6 0 0 0\nL 1\nI 1 1\n", encoding='utf-8')
    (folder / 'input_00001.fit').write_bytes(b'plan parser fixture')
    (folder / 'old-stars.lst').write_text('X Y\n99 99\n', encoding='utf-8')
    log = tmp_path / 'work/process.log'
    log.write_text("log: Running command: getref\nlog: Image 0: 'input_00001.fit'\n", encoding='utf-8')
    adapter.parse_result('getref', tmp_path / 'work', plan, log)
    result = json.loads((folder / 'analysis.json').read_text(encoding='utf-8'))
    assert result[0]['kind'] == 'metrics'
    assert result[0]['values']['zero_based_reference_index'] == 0


def test_progress_idle_zero_is_not_reported_as_processing_completion():
    result = adapter.parse_progress('progress: Sequence processing succeeded., 0.00%\n')
    assert result.progress == 0
    assert result.phase == 'Sequence processing succeeded.'


def test_only_supported_paths_and_script_patterns_are_accepted(tmp_path):
    with pytest.raises(ValueError):
        adapter.quoted(tmp_path / 'quote".fit')
    with pytest.raises(ValueError):
        adapter.token('value\nexit')
    with pytest.raises(ValueError, match='relative'):
        build(tmp_path, 'pyscript', sources={}, values={'output_files': '[{"pattern":"../outside.fit","format":"fits"}]'})
    with pytest.raises(ValueError, match='Unsupported operation'):
        adapter.build_plan('unknown', {}, {}, tmp_path)


def test_full_index_is_accounted_for_without_non_scriptable_placeholder_nodes():
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    coverage = json.loads((ROOT / 'reference/coverage.json').read_text(encoding='utf-8'))['commands']
    reference = json.loads((ROOT / 'reference/commands.json').read_text(encoding='utf-8'))
    assert {row['command'] for row in coverage} == {row['command'] for row in reference}
    assert len(coverage) == 199
    assert all(row['disposition'] == 'not_executable' for row in coverage if row['scriptable'] is not True)
    definitions = [json.loads((ROOT / path).read_text(encoding='utf-8')) for path in manifest['nodes']]
    assert all(node['execution']['operation_id'] in adapter.RECIPES for node in definitions)
    assert not any(node['execution']['operation_id'] == 'addmax' for node in definitions)
    assert 0 < len(manifest['output_nodes']) < len(definitions)
    gauss = next(node for node in definitions if node['execution']['operation_id'] == 'gauss')
    assert gauss['definition_id'] not in manifest['output_nodes']


@pytest.mark.parametrize('operation,values,expected', [
    ('icc_convert_to', {'intent': 'perceptual'}, 'icc_convert_to "sRGB" "perceptual"'),
    ('limit', {'method': 'clip'}, 'limit "-clip"'),
    ('limit', {'method': 'posrescale'}, 'limit "-posrescale"'),
    ('limit', {'method': 'rescale'}, 'limit "-rescale"'),
    ('profile', {'use_layer': True, 'layer': 'lum'}, '"-layer=lum"'),
    ('seqprofile', {'use_layer': True, 'layer': 'red'}, '"-layer=red"'),
])
def test_fixed_cli_parameter_spellings(tmp_path, operation, values, expected):
    for name, value in values.items():
        parameter = next(item["schema"] for item in adapter.RECIPES[operation]["parameters"] if item["schema"]["name"] == name)
        ParameterDefinition.model_validate({**parameter, "default": value})
    assert expected in script(build(tmp_path, operation, values=values))


def test_register_uses_the_fixed_file_distortion_syntax(tmp_path):
    image, distortion = tmp_path/'source.fit', tmp_path/'distortion.wcs'
    image.write_bytes(b'fixed image')
    distortion.write_bytes(b'fixed distortion')
    plan = build(tmp_path, 'register', sources={'image': [image], 'distortion': [distortion]})
    text = script(plan)
    assert '-disto=file ' in text
    assert '-disto=' + distortion.as_posix() not in text


def test_sequence_statistics_tsv_preserves_columns_zero_and_unavailable(tmp_path):
    path = tmp_path/'statistics.csv'
    path.write_text('image\tchannel\tmean\tnoise\n1\t0\t0.25\tnan\n', encoding='utf-8')
    result = adapter._table(path, 'seqstat')
    assert result.columns == ['image', 'channel', 'mean', 'noise']
    assert result.rows == [[1, 0, 0.25, None]]


def test_stat_rejects_the_fixed_cli_combination_that_ignores_cfa_and_main(tmp_path):
    with pytest.raises(ValueError, match='CFA.*main'):
        build(tmp_path, 'stat', values={'cfa': True, 'statistics': 'main'})


@pytest.mark.parametrize('operation', ['register', 'seqapplyreg'])
def test_registration_layer_remains_a_numeric_cli_channel(tmp_path, operation):
    parameter = next(item['schema'] for item in adapter.RECIPES[operation]['parameters'] if item['schema']['name'] == 'layer')
    ParameterDefinition.model_validate({**parameter, 'default': 0})
    text = script(build(tmp_path, operation, values={'use_layer': True, 'layer': 0}))
    assert '"-layer=0"' in text
