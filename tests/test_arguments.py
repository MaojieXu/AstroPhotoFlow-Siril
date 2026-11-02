import hashlib

import pytest
from adapter import recipes

from astrophotoflow.contracts.software import ParameterDefinition

from .adapter_test_helpers import build, script


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


def test_optional_numeric_zero_is_sent_only_when_explicitly_enabled(tmp_path):
    source = tmp_path / 'source.fit'
    source.write_bytes(b'science')
    plan = build(tmp_path, 'rl', sources={'image': [source], 'psf': [source]}, values={'use_regularisation': True, 'regularisation': 0})
    assert '"-alpha=0"' in script(plan)
    other = tmp_path / 'other'; other.mkdir()
    disabled = build(other, 'rl', sources={'image': [source], 'psf': [source]}, values={'use_regularisation': False, 'regularisation': 0})
    assert '-alpha=' not in script(disabled)


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
        parameter = next(item.schema for item in recipes.RECIPES[operation].parameters if item.schema.name == name)
        ParameterDefinition.model_validate({**parameter.model_dump(), "default": value})
    assert expected in script(build(tmp_path, operation, values=values))


def test_register_uses_the_fixed_file_distortion_syntax(tmp_path):
    image, distortion = tmp_path/'source.fit', tmp_path/'distortion.wcs'
    image.write_bytes(b'fixed image')
    distortion.write_bytes(b'fixed distortion')
    plan = build(tmp_path, 'register', sources={'image': [image], 'distortion': [distortion]})
    text = script(plan)
    assert '-disto=file ' in text
    assert '-disto=' + distortion.as_posix() not in text


def test_stat_rejects_the_fixed_cli_combination_that_ignores_cfa_and_main(tmp_path):
    with pytest.raises(ValueError, match='CFA.*main'):
        build(tmp_path, 'stat', values={'cfa': True, 'statistics': 'main'})


@pytest.mark.parametrize('operation', ['register', 'seqapplyreg'])
def test_registration_layer_remains_a_numeric_cli_channel(tmp_path, operation):
    parameter = next(item.schema for item in recipes.RECIPES[operation].parameters if item.schema.name == 'layer')
    ParameterDefinition.model_validate({**parameter.model_dump(), 'default': 0})
    text = script(build(tmp_path, operation, values={'use_layer': True, 'layer': 0}))
    assert '"-layer=0"' in text
