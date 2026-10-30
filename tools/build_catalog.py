"""Build declarations from implemented, explicit Siril recipes."""
import json
import runpy
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from astrophotoflow.contracts.nodes import NodeDefinition
from astrophotoflow.contracts.software import SoftwareOperation


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = runpy.run_path(str(ROOT / 'adapter/recipes.py'))
RECIPES, SESSION_COMMANDS = NAMESPACE['RECIPES'], NAMESPACE['SESSION_COMMANDS']


def output(name, type='APF_SCIENCE', formats=None, required=True):
    return dict(name=name, type=type, formats=formats or ['fits'], cardinality='many', required=required)


def outputs(recipe):
    mode, name = recipe['mode'], recipe['command']
    if mode in {'analysis', 'metadata'}:
        result = [output('analysis', 'APF_ANALYSIS', ['other'])]
        return result + [output('files', 'APF_FILE', ['other', 'image'], False)]
    if mode == 'sequence_analysis':
        return [output('image', formats=['fits', 'video']), output('analysis', 'APF_ANALYSIS', ['other']), output('files', 'APF_FILE', ['other', 'image'], False)]
    if mode == 'split':
        return [output('channel_' + str(index)) for index in range(1, 4)]
    if mode in {'split_cfa', 'sequence_split_cfa'}:
        return [output('cfa' + str(index), formats=['fits', 'video'] if mode.startswith('sequence') else ['fits']) for index in range(4)]
    if mode == 'extract_hao' or name == 'seqextract_HaOIII':
        return [output('ha', formats=['fits', 'video'] if name.startswith('seq') else ['fits']),
                output('oiii', formats=['fits', 'video'] if name.startswith('seq') else ['fits'])]
    if mode == 'fft_direct':
        return [output('modulus'), output('phase')]
    if mode == 'extract':
        return [output('layers')]
    if mode == 'makepsf':
        return [output('psf')]
    if mode in {'starnet', 'sequence_starnet'}:
        return [output('image', formats=['fits', 'video'] if mode.startswith('sequence') else ['fits']),
                output('stars', formats=['fits', 'video'] if mode.startswith('sequence') else ['fits'], required=False)]
    if mode in {'stack', 'stack_all'}:
        return [output('image'), output('rejection_maps', required=False)]
    if mode == 'python_script':
        formats = ['fits', 'xisf', 'image', 'raw', 'video', 'numpy', 'other']
        return [output('image', formats=formats, required=False), output('files', 'APF_FILE', formats, False), output('analysis', 'APF_ANALYSIS', ['other'])]
    if mode == 'export' and name != 'save':
        return [output('file', 'APF_FILE', ['image'])]
    return [output('image', formats=['fits', 'video'] if mode.startswith('sequence') or mode in {'conversion', 'registration', 'apply_registration', 'merge_sequences', 'calibration_sequence'} else ['fits'])]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def main():
    reference = json.loads((ROOT / 'reference/commands.json').read_text(encoding='utf-8'))
    commands = {item['command']: item for item in reference}
    cli = json.loads((ROOT / 'reference/cli-help.json').read_text(encoding='utf-8'))
    observed = {item['command']: item for item in cli['commands']}
    coverage, operation_paths, node_paths, endpoints = {}, [], [], []
    for name, recipe in RECIPES.items():
        covers = recipe.get('covers', [name])
        if any(command not in commands or not observed[command]['scriptable'] for command in covers):
            raise ValueError('A recipe claims a command unavailable to this CLI: ' + name)
        parameters = [item['schema'] for item in recipe['parameters']]
        parameters += [dict(name='runtime', kind='string', default='{}', advanced=True, nullable=False)]
        description = '\n\n'.join(commands[command]['description'] for command in covers)
        description += '\n\nUses fixed input references and writes only invocation-owned outputs. Optional argument values are sent only when their use_* control is true; zero is preserved.'
        operation = dict(package_id='siril', version='1.4.4', operation_id=name,
                         name=name.replace('_', ' '), description=description,
                         syntax='\n'.join(commands[command]['syntax'] for command in covers), scriptable=True,
                         inputs=recipe['inputs'], outputs=outputs(recipe), parameters=parameters, cancel_supported=True)
        operation['parameter_widgets'] = {item['name']: 'multiline' for item in parameters
            if item['kind'] == 'string' and item['name'] in {'runtime', 'script', 'arguments', 'output_files',
                'expression', 'reference_positions', 'coefficients', 'keywords', 'selection'}}
        sequence_mode = recipe['mode'].startswith('sequence') or recipe['mode'] in {
            'calibration_sequence', 'registration', 'apply_registration', 'stack', 'stack_all', 'merge_sequences', 'python_script'}
        for item in operation['inputs']:
            item['data_kind'] = 'file' if item['type'] == 'APF_FILE' or recipe['mode'] == 'python_script' else \
                'sequence' if sequence_mode and item['cardinality'] == 'many' else 'image'
            if item['data_kind'] != 'file' and 'fits' in item['formats']:
                item['colour_layout'] = 'planar'
        if recipe['mode'] != 'python_script':
            for item in operation['outputs']:
                if 'fits' in item['formats']:
                    item['colour_layout'] = 'planar'
        if name == 'seqccm':
            operation['syntax'] = 'seqccm sequence m00 m01 m02 m10 m11 m12 m20 m21 m22 [gamma] [-prefix=]'
        elif name == 'seqwiener':
            operation['syntax'] = 'seqwiener sequence [-loadpsf=] [-alpha=]'
        elif name == 'threshhi':
            operation['syntax'] = 'threshhi level'
        SoftwareOperation.model_validate(dict(operation, content_token='', ready=False, reason=None))
        definition_id = '169de083-7f81-4cde-a329-5541ecacf463' if name == 'autostretch' else str(uuid5(NAMESPACE_URL, 'https://astrophotoflow.local/siril/' + name))
        node = dict(definition_id=definition_id, source='package', name='Siril ' + ('Auto Stretch' if name == 'autostretch' else name.replace('_', ' ')),
                    description=description, inputs=[dict(name=item['name'], type=item['type']) for item in operation['inputs']],
                    outputs=[dict(name=item['name'], type=item['type']) for item in operation['outputs']],
                    parameters=parameters,
                    execution=dict(package_id='siril', operation_id=name,
                                   inputs={item['name']: item['name'] for item in operation['inputs']},
                                   outputs={item['name']: item['name'] for item in operation['outputs']},
                                   parameters={item['name']: dict(kind='parameter', name=item['name']) for item in parameters}))
        NodeDefinition.model_validate(node)
        help_text = ('Siril 1.4.4. ' + description + '\n\n' +
                     '\n'.join(recipe.get('limitations', []) + recipe.get('dependencies', []) + recipe.get('corrections', [])) +
                     '\n\nruntime is a JSON object. Supported keys: ini, settings, threads, memory_ratio, output_bits, compression, online, selection, findstar, photometry. Networking starts offline and must be enabled explicitly. '
                     'Selection is omitted for the whole image or explicitly null to clear it; optional CLI arguments use separate use_* controls. '
                     'Connect transforms to an explicit export, stacking, or analysis endpoint. Only requested dependencies are executed; previews do not make other branches endpoints. '
                     'Saved output references identify complete checked files, never preview pixels. See reference/coverage.json and docs/usage.md.')
        entry = dict(operation=operation, preview=dict(kind='science-image', input='image', max_edge=1024) if recipe['live'] else None,
                     output_display=recipe['display'], help=help_text,
                     examples=[{item['name']: item['default'] for item in parameters}],
                     limitations=recipe.get('limitations', []), dependencies=recipe.get('dependencies', []), corrections=recipe.get('corrections', []))
        operation_path, node_path = 'operations/' + name + '.json', 'nodes/' + name + '.json'
        write(ROOT / operation_path, entry)
        write(ROOT / node_path, node)
        operation_paths.append(operation_path); node_paths.append(node_path)
        if name == 'autostretch' or recipe['mode'] in {'analysis', 'sequence_analysis', 'metadata', 'export', 'stack', 'stack_all', 'live_stack', 'python_script'}:
            endpoints.append(definition_id)
        for command in covers:
            coverage[command] = dict(command=command, disposition='executable' if name == command else 'mapped_operation',
                                     operation_id=name, definition_id=definition_id, cli_available=True, scriptable=True,
                                     implementation='adapter/siril.py', limitations=recipe.get('limitations', []),
                                     verification='implemented; runtime acceptance pending')
    for command, reason in SESSION_COMMANDS.items():
        coverage[command] = dict(command=command, disposition='runtime_or_io', reason=reason, cli_available=True,
                                 scriptable=True, implementation='adapter/siril.py', verification='implemented; runtime acceptance pending')
    for item in reference:
        command = item['command']
        if command in coverage:
            continue
        if item['scriptable']:
            raise ValueError('A scriptable command has no implementation: ' + command)
        coverage[command] = dict(command=command, disposition='not_executable', cli_available=observed[command]['available'],
                                 scriptable=observed[command]['scriptable'],
                                 reason='Unavailable on Windows; dir is the platform alias.' if command == 'ls' else
                                        'Official Siril 1.4.4 non-scriptable command. No executable canvas node is declared. GUI/state integration is deferred by user decision.',
                                 verification='fixed executable help observed')
        if command == 'visu':
            coverage[command]['view_alternative'] = 'Shared viewer display thresholds in decoded pixel units; display only, no scientific file rewrite. This does not execute Siril visu.'
        elif command == 'inspector':
            coverage[command]['view_alternative'] = 'Shared viewer full-resolution pan/zoom and 100% inspection allow manual checks of the center and corners. The exact nine-panel mosaic remains deferred.'
        elif command in {'dir', 'ls'}:
            coverage[command]['view_alternative'] = 'Checked output ports expose fixed member names and downloads. No arbitrary host-directory listing or Siril session is exposed.'
    if set(coverage) != set(commands):
        raise ValueError('Coverage does not match the full reference index.')
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    manifest.update(bundle_version='0.2.0-dev.1', host_api=2, operations=operation_paths, nodes=node_paths, output_nodes=endpoints)
    write(ROOT / 'bundle.json', manifest)
    write(ROOT / 'reference/coverage.json', dict(software_version='1.4.4', platform='windows-x86_64', indexed_commands=len(commands),
                                               executable_operations=len(RECIPES), commands=[coverage[item['command']] for item in reference]))
    assessments = json.loads((ROOT / 'reference/assessments.json').read_text(encoding='utf-8'))
    for row in assessments['commands']:
        item = coverage[row['command']]
        assessment = row['assessment']
        row.setdefault('prior_runtime_evidence', {key: assessment[key] for key in ['runtime_test_status', 'runtime_test_reason']})
        if item['disposition'] in {'executable', 'mapped_operation'}:
            operation_id = item['operation_id']
            assessment.update(
                parameter_details='Fixed executable help is recorded in reference/cli-help.json. The implemented parameter contract is operations/' + operation_id + '.json; optional values require their use_* control, preserving zero.',
                structured_parameter_defaults_ranges='See the operation declaration and adapter/recipes.py. Values disabled by use_* are omitted from the command; their widget seed is not a claimed Siril default.',
                input_output_semantics='Fixed named image, sequence or file inputs and checked named outputs are declared by operations/' + operation_id + '.json. Originals are protected by invocation-owned writable staging.',
                headless_status='fixed_executable_help_scriptable; current_recipe_runtime_verification_pending',
                semantic_review_status='structured_recipe_implemented; independent_review_pending',
                node_definition_status='implemented_executable', node_definition_reason='Mapped to real operation ' + operation_id + ' in Bundle 0.2.0-dev.1.',
                node_generation_status='generated', node_generation_reason='Explicit implemented recipe and typed declarations, not generated CLI placeholders.',
                registry_load_status='not_verified_current_feature', registry_load_reason='Installation and native loading of the current fixed candidate have not been verified.',
                runtime_test_status='not_run_for_current_bundle', runtime_test_reason='Current recipe tests are written but not executed in the Feature stage; prior command evidence is retained separately.')
        elif item['disposition'] == 'runtime_or_io':
            assessment.update(node_definition_status='mapped_to_runtime_or_io', node_definition_reason=item['reason'],
                node_generation_status='not_a_standalone_node', node_generation_reason=item['reason'],
                registry_load_status='not_a_standalone_node', registry_load_reason='No placeholder canvas node is declared.',
                runtime_test_status='not_run_for_current_bundle', runtime_test_reason='Current runtime/IO mapping awaits integration verification.')
        else:
            assessment.update(node_definition_status='not_executable', node_definition_reason=item['reason'],
                node_generation_status='not_generated', node_generation_reason=item['reason'],
                registry_load_status='not_applicable', registry_load_reason='No executable declaration is provided for non-scriptable/unavailable commands.',
                runtime_test_status='not_executable', runtime_test_reason='Fixed CLI help and user-approved GUI deferral; no fake execution result.')
            if item.get('view_alternative'):
                assessment['node_definition_reason'] += ' ' + item['view_alternative']
    write(ROOT / 'reference/assessments.json', assessments)
    print(json.dumps(dict(operations=len(RECIPES), indexed_commands=len(coverage), endpoints=len(endpoints))))


if __name__ == '__main__':
    main()
