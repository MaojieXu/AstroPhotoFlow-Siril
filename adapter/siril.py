from pathlib import Path

from astrophotoflow.contracts.bundles import ProcessPlan


def quoted(path: Path) -> str:
    value = path.resolve().as_posix()
    if any(character in value for character in ('"', '\n', '\r')):
        raise ValueError('Siril paths cannot contain quotes or newlines.')
    return '"' + value + '"'


def build_plan(operation_id, sources, parameters, directory, *, preview=False, prepare_sample=False):
    if operation_id != 'autostretch':
        raise ValueError('Unsupported operation: ' + operation_id)
    (directory / 'siril.ini').write_text('[core]\n', encoding='utf-8')
    command = 'autostretch ' + ('-linked ' if parameters['linked'] else '') + \
        f"{parameters['shadowsclip']:.17g} {parameters['targetbg']:.17g}"
    commands = ['requires 1.4.4', 'setext fit', 'set32bits']
    targets = []
    for index, source in enumerate(sources):
        target = directory / ('result.fit' if preview else f'autostretch-{index:06d}.fit')
        targets.append(target)
        commands.append('load ' + quoted(source))
        if prepare_sample:
            commands.extend(['resample -maxdim=1024 -interp=area', 'save ' + quoted(directory / 'linear.fit')])
        commands.extend([command, 'save ' + quoted(target), 'close'])
    script = directory / 'operation.ssf'
    script.write_text('\n'.join(commands) + '\n', encoding='utf-8')
    return ProcessPlan(arguments=['-o', '-i', str(directory / 'siril.ini'), '-d', str(directory), '-s', str(script)],
                       outputs=targets, output_format='fits',
                       linear_sample=directory / 'linear.fit' if prepare_sample else None)
