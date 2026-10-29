import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('siril_adapter', ROOT / 'adapter/siril.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def test_formal_script_preserves_order_and_negative_parameters(tmp_path):
    sources = [tmp_path / 'first.fit', tmp_path / 'second.fit']
    plan = adapter.build_plan('autostretch', sources, {'linked': True, 'shadowsclip': -4.2, 'targetbg': 0}, tmp_path)
    script = Path(plan.arguments[-1]).read_text()
    assert script.index('first.fit') < script.index('second.fit')
    assert script.count('autostretch -linked -4.2000000000000002 0') == 2
    assert 'resample' not in script
    assert len(plan.outputs) == 2
    assert all(path.parent == tmp_path for path in plan.outputs)


def test_live_preview_saves_linear_sample_before_stretch(tmp_path):
    plan = adapter.build_plan('autostretch', [tmp_path / 'source.xisf'],
        {'linked': False, 'shadowsclip': -2.8, 'targetbg': .25}, tmp_path, preview=True, prepare_sample=True)
    script = Path(plan.arguments[-1]).read_text()
    assert script.index('resample -maxdim=1024 -interp=area') < script.index('linear.fit') < script.index('autostretch ')
    assert plan.linear_sample == tmp_path / 'linear.fit'
    assert len(plan.outputs) == 1
    assert (tmp_path / 'siril.ini').read_text() == '[core]\n'


def test_only_declared_operation_and_safe_script_paths(tmp_path):
    with pytest.raises(ValueError):
        adapter.build_plan('unknown', [], {}, tmp_path)
    with pytest.raises(ValueError):
        adapter.quoted(tmp_path / 'quote".fit')


def test_operation_is_parameter_authority():
    from astrophotoflow.contracts.software import SoftwareOperation, ParameterDefinition
    entry = json.loads((ROOT / 'operations/autostretch.json').read_text())
    operation = SoftwareOperation.model_validate(dict(entry['operation'], ready=False, content_token='', reason=None))
    shadows = next(item for item in operation.parameters if item.name == 'shadowsclip')
    assert shadows.minimum is None and shadows.maximum is None
    assert ParameterDefinition.model_validate({**shadows.model_dump(), 'default': -100}).default == -100
    target = next(item for item in operation.parameters if item.name == 'targetbg')
    with pytest.raises(ValueError):
        ParameterDefinition.model_validate({**target.model_dump(), 'default': 1.1})


def test_only_declared_output_node_is_an_execution_endpoint():
    manifest=json.loads((ROOT/'bundle.json').read_text())
    assert manifest['output_nodes']==['169de083-7f81-4cde-a329-5541ecacf463']
    assert (ROOT/'examples/agent.md').is_file()
