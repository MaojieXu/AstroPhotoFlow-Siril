from __future__ import annotations

import re
from pathlib import Path

from astrophotoflow.contracts.bundles import (
    ProcessOutput,
)

from ..arguments import calibration_arguments, header_arguments, image_arguments, quoted, sequence_analysis_commands, stack_arguments, token
from ..outputs import add_file, add_pattern
from ..runtime import selection_commands
from ..sequences import read_sequence_descriptor, sequence_output, stage_sequence
from ..types import BuildContext, SequenceLayout


def build_sequence(context: BuildContext) -> None:
    recipe = context.recipe
    sources = context.sources
    values = context.values
    directory = context.directory
    commands = context.commands
    outputs = context.outputs
    runtime = context.runtime
    supporting_sources = context.supporting_sources
    source_metadata = context.source_metadata
    layout = context.layout
    command, mode = recipe.command, recipe.mode
    folder = directory / 'sequence'
    base = stage_sequence(commands, sources['image'], supporting_sources.get('image', []), folder, metadata=source_metadata.get('image', []), compressed=runtime.compression_enabled)
    descriptor = folder / (base + '.seq')
    single_frame = read_sequence_descriptor(descriptor) if descriptor.is_file() else None
    if single_frame and (single_frame.frames != 1 or single_frame.type != 'R'):
        single_frame = None
    layout.sequences.append(SequenceLayout(folder='sequence', input_base=base, output_base=base))
    if runtime.selection is not None:
        commands.append('load ' + quoted(sources['image'][0]))
        commands.extend(selection_commands(runtime))
    arguments = image_arguments(recipe, values, sources)
    output_base = 'result_' + base
    if mode == 'sequence_analysis':
        commands.append(sequence_analysis_commands(command, recipe, values, sources, base, folder))
        sequence_output(outputs, 'image', directory, folder, base, single_frame)
        add_file(outputs, 'analysis', folder / 'analysis.json', 'other')
        outputs.setdefault('files', ProcessOutput())
        for pattern in {'seqstat': ['statistics.csv'], 'seqheader': ['headers.csv'], 'seqfindstar': ['*.lst'],
                        'seqprofile': ['*.dat'], 'light_curve': ['*.dat'], 'seqpsf': ['*.dat']}.get(command, []):
            add_pattern(outputs, 'files', directory, folder, pattern, 'other', minimum=0 if command in {'seqpsf', 'light_curve'} else 1)
        if command in {'seqprofile', 'light_curve', 'seqpsf', 'seqtilt'}:
            add_pattern(outputs, 'files', directory, folder, '*.png', 'image', minimum=0)
        return
    if mode == 'sequence_state':
        if command == 'setref':
            number = str(values['image_number'])
            commands.append('select ' + token(base) + ' ' + number + ' ' + number)
        commands.append(command + ' ' + token(base) + (' ' + ' '.join(arguments) if arguments else ''))
        packed = len(sources['image']) == 1 and (sources['image'][0].suffix.lower() == '.ser' or
            any((item.scientific_metadata or {}).get('frame_count', 1) is not None and (item.scientific_metadata or {}).get('frame_count', 1) > 1 for item in source_metadata.get('image', [])) or
            any(re.search(r'(?m)^T[SF]$', Path(path).read_text(encoding='utf-8')) for path in supporting_sources.get('image', []) if Path(path).suffix == '.seq'))
        output_base = 'ps_' + base if command == 'seqplatesolve' and packed else base
    elif mode == 'sequence_header_update':
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(header_arguments(values)))
        output_base = base
    elif mode == 'calibration_sequence':
        arguments = calibration_arguments(values, sources) + arguments + ['-prefix=result_']
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
    elif mode in {'registration', 'apply_registration'}:
        if 'flat' in sources:
            arguments.append(token('-flat=' + sources['flat'][0].as_posix()))
        arguments.append('-prefix=result_')
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
        if command == 'register' and values['two_pass']:
            output_base = base
    elif mode == 'stack':
        commands.append('stack ' + token(base) + ' ' + ' '.join(stack_arguments(recipe, values) + [token('-out=' + (folder / 'stacked.fit').as_posix())]))
        add_file(outputs, 'image', folder / 'stacked.fit')
        outputs.setdefault('rejection_maps', ProcessOutput())
        if values['rejection_maps'] != 'none':
            add_pattern(outputs, 'rejection_maps', directory, folder, '*rej*.fit*', minimum=1)
        return
    elif mode == 'sequence_split_cfa':
        commands.append('seqsplit_cfa ' + token(base))
        for index in range(4):
            sequence_output(outputs, 'cfa' + str(index), directory, folder, f'CFA{index}_' + base, single_frame)
        return
    elif mode == 'sequence_starnet':
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
        sequence_output(outputs, 'image', directory, folder, 'starless_' + base, single_frame)
        outputs.setdefault('stars', ProcessOutput())
        if not values['no_starmask']:
            sequence_output(outputs, 'stars', directory, folder, 'starmask_' + base, single_frame)
        return
    elif mode == 'sequence_transform':
        if 'bad_pixels' in sources:
            arguments.insert(0, quoted(sources['bad_pixels'][0]))
        if command == 'seqextract_HaOIII':
            commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
            for name, prefix in [('ha', 'Ha_'), ('oiii', 'OIII_')]:
                sequence_output(outputs, name, directory, folder, prefix + base, single_frame)
            return
        if command in {'seqrl', 'seqsb', 'seqwiener'}:
            output_base = 'dec_' + base
            commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
        else:
            commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments + ['-prefix=result_']))
    else:
        raise ValueError('Unsupported sequence execution mode: ' + mode)
    layout.sequences[-1].output_base = output_base
    sequence_output(outputs, 'image', directory, folder, output_base, single_frame)
