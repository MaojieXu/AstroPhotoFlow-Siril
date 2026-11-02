from __future__ import annotations

import re

from astrophotoflow.contracts.bundles import (
    BundleFile,
    OutputPattern,
    ProcessOutput,
)

EXPORTS = {'save': ('.fit', 'fits'), 'savebmp': ('.bmp', 'image'), 'savejpg': ('.jpg', 'image'),
           'savejxl': ('.jxl', 'image'), 'savepng': ('.png', 'image'), 'savepnm': ('.pnm', 'image'),
           'savetif': ('.tif', 'image'), 'savetif32': ('.tif', 'image'), 'savetif8': ('.tif', 'image')}


def add_file(outputs, name, path, format='fits'):
    outputs.setdefault(name, ProcessOutput()).files.append(BundleFile(path=path, format=format, frame_count=1 if format == 'fits' else None))


def add_pattern(outputs, name, directory, folder, pattern, format='fits', minimum=1, supporting=False):
    output = outputs.setdefault(name, ProcessOutput())
    value = OutputPattern(pattern=(folder / pattern).relative_to(directory).as_posix(), format=format, minimum_count=minimum,
                          allow_empty=format == 'other' and pattern.endswith(('.lst', '.csv', '.dat')))
    (output.supporting_patterns if supporting else output.patterns).append(value)


def compressed_paths(commands, outputs, runtime):
    if not runtime.compression_enabled:
        return commands
    replacements = {}
    for command in commands:
        match = re.match(r'^save "([^"]+\.fit)"', command)
        if match:
            replacements[match[1]] = match[1] + '.fz'
    for output in outputs.values():
        for file in output.files:
            if file.format == 'fits' and file.path.suffix == '.fit':
                replacements[file.path.as_posix()] = file.path.as_posix() + '.fz'
                file.path = file.path.with_name(file.path.name + '.fz')
    for old, new in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
        commands = [command.replace(old, new) for command in commands]
    return commands
