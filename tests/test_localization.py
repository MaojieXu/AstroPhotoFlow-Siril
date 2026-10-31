import json
from pathlib import Path
import runpy
import shutil
from collections import Counter
from uuid import NAMESPACE_URL, uuid5

import pytest

from astrophotoflow.contracts.localization import CapabilityDisplay


ROOT = Path(__file__).resolve().parents[1]


def test_each_operation_has_an_explicit_automatic_result_policy():
    source = json.loads((ROOT / 'locales/source.zh.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    entries = [json.loads((ROOT / name).read_text(encoding='utf-8')) for name in manifest['operations']]
    assert len(entries) == len(source['operations']) == 160
    for entry in entries:
        identity = entry['operation']['operation_id']
        assert type(source['operations'][identity]['automatic_result_preview']) is bool
        assert entry['automatic_result_preview'] is source['operations'][identity]['automatic_result_preview']
    for identity in ['save', 'pyscript', 'capabilities', 'help', 'seqclean']:
        assert source['operations'][identity]['automatic_result_preview'] is False
    for identity in ['subsky', 'seqsubsky', 'stat', 'seqstat', 'register', 'stack']:
        assert source['operations'][identity]['automatic_result_preview'] is True


def test_all_nodes_have_bilingual_names_and_exactly_two_category_levels():
    source = json.loads((ROOT / 'locales/source.zh.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    locales = {locale: json.loads((ROOT / path).read_text(encoding='utf-8')) for locale, path in manifest['locales'].items()}
    counts = Counter()
    identities = []
    for filename in manifest['nodes']:
        node = json.loads((ROOT / filename).read_text(encoding='utf-8'))
        identity = node['execution']['operation_id']
        identities.append(identity)
        entry = source['operations'][identity]
        assert len(node['category']) == 2
        assert node['category'] == entry['category']
        counts[node['category'][0]] += 1
        expected_id = '169de083-7f81-4cde-a329-5541ecacf463' if identity == 'autostretch' else str(uuid5(NAMESPACE_URL, 'https://astrophotoflow.local/siril/' + identity))
        assert node['definition_id'] == expected_id
        operation = json.loads((ROOT / f'operations/{identity}.json').read_text(encoding='utf-8'))['operation']
        assert node['parameters'] == operation['parameters']
        for direction in ('inputs', 'outputs'):
            assert node[direction] == [{'name': port['name'], 'type': port['type']} for port in operation[direction]]
            assert node['execution'][direction] == {port['name']: port['name'] for port in operation[direction]}
        for locale, values in locales.items():
            display = values[identity]
            expected_name = entry['name'] + '（' + identity + '）' if locale == 'zh' else entry['name_en'] + ' (' + identity + ')'
            assert display['name'] == expected_name
            assert display['category'] == [source['categories'][part][locale] for part in node['category']]
            if locale == 'en':
                assert node['name'] == display['name']
    assert len(identities) == len(set(identities)) == 160
    assert counts == {'files-sequences': 18, 'preprocessing': 18, 'stretch-color': 29,
                      'background-filters': 22, 'geometry-channels': 22, 'stars': 4,
                      'pixel-math': 16, 'analysis': 21, 'tools': 10}


@pytest.mark.parametrize('change', ['missing', 'extra', 'depth', 'label'])
def test_presentation_generation_rejects_incomplete_mapping(tmp_path, change):
    source = json.loads((ROOT / 'locales/source.zh.json').read_text(encoding='utf-8'))
    identities = list(source['operations'])
    if change == 'missing':
        del source['operations']['ght']
    elif change == 'extra':
        source['operations']['unknown'] = source['operations']['ght']
    elif change == 'depth':
        source['operations']['ght']['category'] = ['stretch-color']
    else:
        source['categories']['stretch-color']['zh'] = ''
    (tmp_path / 'locales').mkdir()
    (tmp_path / 'locales/source.zh.json').write_text(json.dumps(source), encoding='utf-8')
    load = runpy.run_path(str(ROOT / 'tools/presentation.py'))['load_presentation']
    with pytest.raises(ValueError):
        load(tmp_path, identities)


def test_every_operation_parameter_and_port_has_bilingual_display_text():
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    assert set(manifest['locales']) == {'en', 'zh'}
    operations = {entry['operation']['operation_id']: entry['operation'] for name in manifest['operations']
                  for entry in [json.loads((ROOT / name).read_text(encoding='utf-8'))]}
    assert len(operations) == 160
    for locale, filename in manifest['locales'].items():
        values = json.loads((ROOT / filename).read_text(encoding='utf-8'))
        assert set(values) == set(operations)
        for identity, raw in values.items():
            display = CapabilityDisplay.model_validate(raw)
            assert display.name.strip() and display.description.strip() and display.help.strip()
            for section in ('parameters', 'inputs', 'outputs'):
                assert set(getattr(display, section)) == {item['name'] for item in operations[identity][section]}
                assert all(value.label.strip() and value.description.strip() for value in getattr(display, section).values())


def test_translation_rebuild_preserves_executable_declarations(tmp_path):
    for directory in ('operations', 'nodes', 'locales'):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / 'bundle.json', tmp_path / 'bundle.json')
    paths = [*tmp_path.glob('operations/*.json'), *tmp_path.glob('nodes/*.json')]
    before = {path: path.read_bytes() for path in paths}
    build = runpy.run_path(str(ROOT / 'tools/build_locales.py'))['main']
    build.__globals__['ROOT'] = tmp_path
    build()
    assert {path: path.read_bytes() for path in paths} == before
    for locale in ('en', 'zh'):
        assert (tmp_path / f'locales/{locale}.json').read_bytes() == (ROOT / f'locales/{locale}.json').read_bytes()
