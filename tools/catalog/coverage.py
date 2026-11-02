"""Account for real command implementations without inventing executable nodes."""
from adapter.recipes import SESSION_COMMANDS


def complete_coverage(coverage: dict, reference: list[dict], commands: dict, observed: dict) -> dict:
    for command, reason in SESSION_COMMANDS.items():
        coverage[command] = {'command': command, 'disposition': 'runtime_or_io', 'reason': reason, 'cli_available': True,
                                 'scriptable': True, 'implementation': 'adapter/siril.py', 'verification': 'implemented; runtime acceptance pending'}
    for item in reference:
        command = item['command']
        if command in coverage:
            continue
        if item['scriptable']:
            raise ValueError('A scriptable command has no implementation: ' + command)
        coverage[command] = {'command': command, 'disposition': 'not_executable', 'cli_available': observed[command]['available'],
                                 'scriptable': observed[command]['scriptable'],
                                 'reason': 'Unavailable on Windows; dir is the platform alias.' if command == 'ls' else
                                        'Official Siril 1.4.4 non-scriptable command. No executable canvas node is declared. GUI/state integration is deferred by user decision.',
                                 'verification': 'fixed executable help observed'}
        if command == 'visu':
            coverage[command]['view_alternative'] = 'Shared viewer display thresholds in decoded pixel units; display only, no scientific file rewrite. This does not execute Siril visu.'
        elif command == 'inspector':
            coverage[command]['view_alternative'] = 'Shared viewer full-resolution pan/zoom and 100% inspection allow manual checks of the center and corners. The exact nine-panel mosaic remains deferred.'
        elif command in {'dir', 'ls'}:
            coverage[command]['view_alternative'] = 'Checked output ports expose fixed member names and downloads. No arbitrary host-directory listing or Siril session is exposed.'
    if set(coverage) != set(commands):
        raise ValueError('Coverage does not match the full reference index.')
    return coverage


def update_assessments(assessments: dict, coverage: dict) -> dict:
    for row in assessments['commands']:
        item = coverage[row['command']]
        assessment = row['assessment']
        row.setdefault('prior_runtime_evidence', {key: assessment[key] for key in ['runtime_test_status', 'runtime_test_reason']})
        if item['disposition'] in {'executable', 'mapped_operation'}:
            operation_id = item['operation_id']
            assessment.update(
                parameter_details='Fixed executable help is recorded in reference/cli-help.json. The implemented parameter contract is operations/' + operation_id + '.json; optional values require their use_* control, preserving zero.',
                structured_parameter_defaults_ranges='See the operation declaration and adapter/recipes/catalog.py. Values disabled by use_* are omitted from the command; their widget seed is not a claimed Siril default.',
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
    return assessments
