import json
from pathlib import Path
import runpy
import shutil

from astrophotoflow.contracts.localization import CapabilityDisplay


ROOT = Path(__file__).resolve().parents[1]


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
