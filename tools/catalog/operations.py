"""Generate executable contracts and their display-only envelope."""
from collections.abc import Mapping

from adapter.recipes import Recipe

from astrophotoflow.contracts.software import SoftwareOperation


def build_operation(recipe: Recipe, commands: Mapping[str, dict]) -> SoftwareOperation:
    name = recipe.command
    covers = recipe.covers or [name]
    parameters = [item.schema.model_dump(exclude_none=True) for item in recipe.parameters]
    parameters += [{'name': 'runtime', 'kind': 'string', 'default': '{}', 'advanced': True, 'nullable': False}]
    description = '\n\n'.join(commands[command]['description'] for command in covers)
    description += '\n\nUses fixed input references and writes only invocation-owned outputs. Optional argument values are sent only when their use_* control is true; zero is preserved.'
    operation = {'package_id': 'siril', 'version': '1.4.4', 'operation_id': name,
                     'name': name.replace('_', ' '), 'description': description,
                     'syntax': '\n'.join(commands[command]['syntax'] for command in covers), 'scriptable': True,
                     'inputs': [item.model_dump(exclude_none=True) for item in recipe.inputs], 'outputs': [item.model_dump(exclude_none=True) for item in recipe.outputs], 'parameters': parameters, 'cancel_supported': True}
    operation['parameter_widgets'] = {item['name']: 'multiline' for item in parameters
        if item['kind'] == 'string' and item['name'] in {'runtime', 'script', 'arguments', 'output_files',
            'expression', 'reference_positions', 'coefficients', 'keywords', 'selection'}}
    if name == 'seqccm':
        operation['syntax'] = 'seqccm sequence m00 m01 m02 m10 m11 m12 m20 m21 m22 [gamma] [-prefix=]'
    elif name == 'seqwiener':
        operation['syntax'] = 'seqwiener sequence [-loadpsf=] [-alpha=]'
    elif name == 'threshhi':
        operation['syntax'] = 'threshhi level'
    return SoftwareOperation.model_validate(dict(operation, content_token='', ready=False, reason=None))


def build_entry(recipe: Recipe, value: SoftwareOperation, display: dict) -> dict:
    name = recipe.command
    operation = value.model_dump(mode='json', exclude_none=True, exclude={'content_token', 'ready', 'reason'})
    parameters = operation['parameters']
    description = value.description
    presentation = {'operations': {name: display}}
    help_text = ('Siril 1.4.4. ' + description + '\n\n' +
                 '\n'.join(recipe.limitations + recipe.dependencies + recipe.corrections) +
                 '\n\nruntime is a JSON object. Supported keys: ini, settings, threads, memory_ratio, output_bits, compression, online, selection, findstar, photometry. Networking starts offline and must be enabled explicitly. '
                 'Selection is omitted for the whole image or explicitly null to clear it; optional CLI arguments use separate use_* controls. '
                 'Automatic complete-result calculation can target explicitly opted-in processing and analysis operations without an export node. Manual execution retains explicit export, stacking, or analysis endpoints. Only requested dependencies are executed. '
                 'Saved output references identify complete checked files, never preview pixels. See reference/coverage.json and docs/usage.md.')
    return {'operation': operation, 'preview': {'kind': 'science-image', 'input': 'image', 'output': 'image', 'max_edge': 1024} if recipe.live else None,
                 'automatic_result_preview': presentation['operations'][name]['automatic_result_preview'],
                 'output_display': recipe.display, 'help': help_text,
                 'examples': [{item['name']: item['default'] for item in parameters}],
                 'limitations': recipe.limitations, 'dependencies': recipe.dependencies, 'corrections': recipe.corrections}
