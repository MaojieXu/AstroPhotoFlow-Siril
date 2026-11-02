import json

from adapter import recipes

from astrophotoflow.contracts.software import ParameterDefinition

from .adapter_test_helpers import ROOT


def test_full_index_is_accounted_for_without_non_scriptable_placeholder_nodes():
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    coverage = json.loads((ROOT / 'reference/coverage.json').read_text(encoding='utf-8'))['commands']
    reference = json.loads((ROOT / 'reference/commands.json').read_text(encoding='utf-8'))
    assert {row['command'] for row in coverage} == {row['command'] for row in reference}
    assert len(coverage) == 199
    assert all(row['disposition'] == 'not_executable' for row in coverage if row['scriptable'] is not True)
    definitions = [json.loads((ROOT / path).read_text(encoding='utf-8')) for path in manifest['nodes']]
    assert all(node['execution']['operation_id'] in recipes.RECIPES for node in definitions)
    assert not any(node['execution']['operation_id'] == 'addmax' for node in definitions)
    assert 0 < len(manifest['output_nodes']) < len(definitions)
    gauss = next(node for node in definitions if node['execution']['operation_id'] == 'gauss')
    assert gauss['definition_id'] not in manifest['output_nodes']


def test_development_watch_covers_adapter_format_dependency():
    configuration = json.loads((ROOT / 'development.json').read_text(encoding='utf-8'))
    assert any(ROOT / 'reference/formats.json' in ROOT.glob(pattern) for pattern in configuration['watch'])


def test_all_generated_ports_and_parameters_are_owned_by_typed_recipes():
    from adapter.recipes import Recipe, RecipeParameter

    from astrophotoflow.contracts.software import SoftwareInputDefinition, SoftwareOperation, SoftwareOutputDefinition
    assert len(recipes.RECIPES) == 160
    for name, recipe in recipes.RECIPES.items():
        assert isinstance(recipe, Recipe)
        assert all(isinstance(item, RecipeParameter) and isinstance(item.schema, ParameterDefinition) for item in recipe.parameters)
        assert all(isinstance(item, SoftwareInputDefinition) for item in recipe.inputs)
        assert all(isinstance(item, SoftwareOutputDefinition) for item in recipe.outputs)
        entry = json.loads((ROOT / 'operations' / (name + '.json')).read_text(encoding='utf-8'))
        operation = SoftwareOperation.model_validate({**entry['operation'], 'content_token': '', 'ready': False, 'reason': None})
        assert operation.inputs == recipe.inputs, name
        assert operation.outputs == recipe.outputs, name
        assert operation.parameters[:-1] == [item.schema for item in recipe.parameters], name
