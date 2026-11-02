from __future__ import annotations

import re
import shutil
from pathlib import Path

from .arguments import quoted, token
from .formats import FORMATS
from .outputs import add_pattern
from .types import SequenceDescriptor


def copy_fits(commands, source, target):
    commands.extend(['load ' + quoted(source), 'save ' + quoted(target), 'close'])
    return target


def write_single_sequence(folder, base, member=1, selected=1, fixed=5, compressed=False):
    (folder / (base + '.seq')).write_text(
        f"S '{base}' {member} 1 {selected} {fixed} -1 6 0 {int(compressed)} 0\nL -1\nI {member} {selected}\n", encoding='utf-8')


def stage_sequence(commands, sources, supporting, folder, base_hint=None, metadata=(), compressed=False):
    folder.mkdir(parents=True, exist_ok=True)
    sequence_files = [path for path in supporting if path.suffix.lower() == '.seq']
    containers = [item for item in metadata if item.selection.kind == 'whole_file' and (item.scientific_metadata or {}).get('frame_count', 1) is not None and (item.scientific_metadata or {}).get('frame_count', 1) > 1]
    if len(sources) > 1 and containers:
        raise ValueError('Several packed containers must use separate Merge sequence connections; their first frames are not an image group.')
    if sequence_files:
        if len(sequence_files) != 1:
            raise ValueError('One fixed sequence must have exactly one sequence descriptor.')
        old_base = sequence_files[0].stem
        base = base_hint or old_base
        names = set()
        for path in [*sources, *supporting]:
            name = base + path.name[len(old_base):] if path.name.startswith(old_base) else path.name
            if name in names:
                raise ValueError('Sequence files have duplicate basenames.')
            names.add(name)
            if path.suffix.lower() == '.seq':
                descriptor = path.read_text(encoding='utf-8')
                descriptor = re.sub(r"(?m)^S '[^']+'", "S '" + base + "'", descriptor, count=1)
                (folder / name).write_text(descriptor, encoding='utf-8')
            else:
                shutil.copy2(path, folder / name)
    elif len(sources) == 1 and sources[0].suffix.lower() == '.ser':
        base = base_hint or 'input'
        shutil.copy2(sources[0], folder / (base + '.ser'))
    elif len(sources) == 1 and sources[0].suffix.lower() in FORMATS['video_extensions']:
        base = base_hint or 'input'
        shutil.copy2(sources[0], folder / (base + sources[0].suffix.lower()))
    elif len(sources) == 1 and containers:
        base = base_hint or 'input'
        suffix = '.fit.fz' if sources[0].name.lower().endswith(('.fit.fz', '.fits.fz', '.fts.fz')) else '.fit'
        shutil.copy2(sources[0], folder / (base + suffix))
    else:
        if not sources:
            raise ValueError('A sequence requires at least one fixed member.')
        base = base_hint or 'input_'
        for index, source in enumerate(sources, 1):
            if source.suffix.lower() in {'.ser', '.mkv', *FORMATS['video_extensions']}:
                raise ValueError('A video sequence must be provided alone with a fixed-build supported extension; movies are not a static-image group.')
            copy_fits(commands, source, folder / f'{base}{index:05d}.fit')
        if len(sources) == 1:
            write_single_sequence(folder, base, compressed=compressed)
    commands.extend(['cd ' + quoted(folder), 'getref ' + token(base)])
    return base


def sequence_output(outputs, name, directory, folder, base, single_frame=None):
    if single_frame is not None and not (folder / (base + '.seq')).exists():
        member, selected = single_frame.members[0]
        write_single_sequence(folder, base, member, selected, single_frame.fixed)
    for suffix, format in [('*.fit', 'fits'), ('*.fit.fz', 'fits'), ('*.ser', 'video'), *[('*' + extension, 'video') for extension in FORMATS['video_extensions']]]:
        add_pattern(outputs, name, directory, folder, base + suffix, format, minimum=0)
    add_pattern(outputs, name, directory, folder, base + '*.seq', 'other', supporting=True)
    for suffix in ['*.lst', '*.wcs', '*conversion.txt']:
        add_pattern(outputs, name, directory, folder, base + suffix, 'other', minimum=0, supporting=True)
    add_pattern(outputs, name, directory, folder, base + '*.idx', 'other', minimum=0, supporting=True)


def read_sequence_descriptor(path: Path) -> SequenceDescriptor:
    lines = path.read_text(encoding='utf-8').splitlines()
    for line in lines:
        match = re.match(r"S '([^']+)' (\d+) (\d+) (\d+) (\d+) (-?\d+)", line)
        if match:
            members = [(int(item[1]), int(item[2])) for text in lines if (item := re.match(r'I (\d+) ([01])', text))]
            if len(members) != int(match[3]) or sum(selected for _, selected in members) != int(match[4]):
                raise ValueError('The sequence member list and declared counts disagree.')
            return SequenceDescriptor(name=match[1], start=int(match[2]), frames=int(match[3]), selected=int(match[4]), fixed=int(match[5]), members=members,
                type=next((line[1] for line in lines if re.fullmatch('T[SFA]', line)), 'R'))
    raise ValueError('Siril sequence descriptor is incomplete: ' + path.name)
