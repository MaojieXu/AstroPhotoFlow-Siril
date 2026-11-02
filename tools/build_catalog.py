"""Build declarations from implemented, explicit Siril recipes."""
import json
from pathlib import Path

from adapter.recipes import RECIPES

from . import presentation as PRESENTATION
from .catalog.coverage import complete_coverage, update_assessments
from .catalog.nodes import build_node
from .catalog.operations import build_entry, build_operation

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def main():
    presentation = PRESENTATION.load_presentation(ROOT, list(RECIPES))
    reference = json.loads((ROOT / 'reference/commands.json').read_text(encoding='utf-8'))
    commands = {item['command']: item for item in reference}
    cli = json.loads((ROOT / 'reference/cli-help.json').read_text(encoding='utf-8'))
    observed = {item['command']: item for item in cli['commands']}
    coverage, operation_paths, node_paths, endpoints = {}, [], [], []
    for name, recipe in RECIPES.items():
        covers = recipe.covers or [name]
        if any(command not in commands or not observed[command]['scriptable'] for command in covers):
            raise ValueError('A recipe claims a command unavailable to this CLI: ' + name)
        operation = build_operation(recipe, commands)
        node = build_node(recipe, operation, presentation['operations'][name])
        definition_id = str(node.definition_id)
        entry = build_entry(recipe, operation, presentation['operations'][name])
        operation_path, node_path = 'operations/' + name + '.json', 'nodes/' + name + '.json'
        write(ROOT / operation_path, entry)
        write(ROOT / node_path, node.model_dump(mode='json', exclude_none=True))
        operation_paths.append(operation_path); node_paths.append(node_path)
        if name == 'autostretch' or recipe.mode in {'analysis', 'sequence_analysis', 'metadata', 'export', 'stack', 'stack_all', 'live_stack', 'python_script'}:
            endpoints.append(definition_id)
        for command in covers:
            coverage[command] = {'command': command, 'disposition': 'executable' if name == command else 'mapped_operation',
                                     'operation_id': name, 'definition_id': definition_id, 'cli_available': True, 'scriptable': True,
                                     'implementation': 'adapter/siril.py', 'limitations': recipe.limitations,
                                     'verification': 'implemented; runtime acceptance pending'}
    complete_coverage(coverage, reference, commands, observed)
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    manifest.update(bundle_version='0.2.0-dev.2', host_api=2, operations=operation_paths, nodes=node_paths, output_nodes=endpoints,
                    locales={'en': 'locales/en.json', 'zh': 'locales/zh.json'})
    write(ROOT / 'bundle.json', manifest)
    write(ROOT / 'reference/coverage.json', {'software_version': '1.4.4', 'platform': 'windows-x86_64', 'indexed_commands': len(commands),
                                               'executable_operations': len(RECIPES), 'commands': [coverage[item['command']] for item in reference]})
    assessments = json.loads((ROOT / 'reference/assessments.json').read_text(encoding='utf-8'))
    update_assessments(assessments, coverage)
    write(ROOT / 'reference/assessments.json', assessments)
    from .build_locales import main as build_locales
    build_locales()
    print(json.dumps({'operations': len(RECIPES), 'indexed_commands': len(coverage), 'endpoints': len(endpoints)}))


if __name__ == '__main__':
    main()
