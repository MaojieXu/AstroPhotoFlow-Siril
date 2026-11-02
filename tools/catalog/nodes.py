"""Build node identities and port bindings from the operation contract."""
from uuid import NAMESPACE_URL, uuid5

from adapter.recipes import Recipe

from astrophotoflow.contracts.nodes import NodeDefinition
from astrophotoflow.contracts.software import SoftwareOperation

from .. import presentation as PRESENTATION


def build_node(recipe: Recipe, value: SoftwareOperation, display: dict) -> NodeDefinition:
    name = recipe.command
    operation = value.model_dump(mode='json', exclude_none=True, exclude={'content_token', 'ready', 'reason'})
    parameters = operation['parameters']
    description = value.description
    presentation = {'operations': {name: display}}
    definition_id = '169de083-7f81-4cde-a329-5541ecacf463' if name == 'autostretch' else str(uuid5(NAMESPACE_URL, 'https://astrophotoflow.local/siril/' + name))
    node = {'definition_id': definition_id, 'source': 'package',
                'name': PRESENTATION.node_name(presentation['operations'][name], name, 'en'),
                'category': presentation['operations'][name]['category'],
                'description': description, 'inputs': [{'name': item['name'], 'type': item['type']} for item in operation['inputs']],
                'outputs': [{'name': item['name'], 'type': item['type']} for item in operation['outputs']],
                'parameters': parameters,
                'execution': {'package_id': 'siril', 'operation_id': name,
                               'inputs': {item['name']: item['name'] for item in operation['inputs']},
                               'outputs': {item['name']: item['name'] for item in operation['outputs']},
                               'parameters': {item['name']: {'kind': 'parameter', 'name': item['name']} for item in parameters}}}
    return NodeDefinition.model_validate(node)
