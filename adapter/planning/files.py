from __future__ import annotations

import re
import shutil
from pathlib import Path

from astrophotoflow.contracts.bundles import (
    ProcessOutput,
)

from ..arguments import encode_parameters, json_value, quoted, scalar, stack_arguments, token
from ..formats import FORMATS
from ..outputs import add_file, add_pattern
from ..paths import inside
from ..planning.sequence import build_sequence
from ..runtime import selection_commands
from ..sequences import copy_fits, sequence_output, stage_sequence
from ..types import BuildContext, SequenceLayout


def build_file_plan(context: BuildContext) -> None:
    recipe = context.recipe
    sources = context.sources
    values = context.values
    directory = context.directory
    commands = context.commands
    outputs = context.outputs
    runtime = context.runtime
    source_groups = context.source_groups
    supporting_groups = context.supporting_groups
    source_metadata = context.source_metadata
    layout = context.layout
    mode, command = recipe.mode, recipe.command
    if mode in {'sequence_transform', 'sequence_analysis', 'sequence_state', 'sequence_header_update',
                'calibration_sequence', 'registration', 'apply_registration', 'stack', 'sequence_split_cfa', 'sequence_starnet'}:
        build_sequence(context)
    elif mode == 'metadata':
        args = encode_parameters(recipe, values)
        if command == 'get':
            args = [token(values['variable_name'])] if values['query'] == 'variable' else ['-A' if values['query'] == 'all_with_comments' else '-a']
        commands.append(command + (' ' + ' '.join(args) if args else ''))
        add_file(outputs, 'analysis', directory / 'analysis.json', 'other')
        outputs.setdefault('files', ProcessOutput())
    elif mode == 'conversion':
        folder, result = directory / 'sources', directory / 'sequence'
        folder.mkdir(); result.mkdir()
        permitted = FORMATS['static_extensions']['raw'] if command == 'convertraw' else FORMATS['static_extensions']['fits'] + FORMATS['compressed_fits_extensions'] if command == 'link' else [suffix for group in FORMATS['static_extensions'].values() for suffix in group] + FORMATS['compressed_fits_extensions']
        if any(not source.name.lower().endswith(tuple(permitted)) for source in sources['image']):
            raise ValueError('The conversion input includes a file type this fixed Siril build would skip; no partial conversion is started.')
        for index, source in enumerate(sources['image']):
            shutil.copy2(source, folder / (f'input-{index:06d}' + ''.join(source.suffixes)))
        commands.extend(['cd ' + quoted(folder), command + ' result_ ' + ' '.join(encode_parameters(recipe, values) + [token('-out=' + result.as_posix())])])
        if command != 'link' and values['sequence_format'] != 'images':
            commands[-1] += ' -' + values['sequence_format']
        commands.extend(['cd ' + quoted(result), 'getref result_'])
        sequence_output(outputs, 'image', directory, result, 'result_')
        layout.sequences.append(SequenceLayout(folder='sequence', output_base='result_', expected_frames=len(sources['image'])))
    elif mode in {'fft_inverse', 'rgb_composition', 'merge_cfa'}:
        local = {}
        for name, paths in sources.items():
            local[name] = paths[0] if paths[0].name.lower().endswith(('.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz')) else copy_fits(commands, paths[0], directory / (name + '.fit'))
        result = directory / 'result.fit'
        if mode == 'fft_inverse':
            commands.extend(['load ' + quoted(local['modulus']), 'ffti ' + quoted(local['modulus']) + ' ' + quoted(local['phase']), 'save ' + quoted(result)])
        elif mode == 'merge_cfa':
            commands.append('merge_cfa ' + ' '.join(quoted(local['cfa' + str(index)]) for index in range(4)) + ' ' + values['bayer_pattern'])
            commands.append('save ' + quoted(result))
        else:
            selected = ['red', 'green', 'blue'] if values['mode'] in {'rgb', 'lrgb'} else ['rgb']
            if values['mode'] != 'rgb' and 'luminance' not in local or any(name not in local for name in selected):
                raise ValueError('RGB composition is missing an explicitly selected input channel.')
            arguments = ([] if values['mode'] == 'rgb' else [token('-lum=' + local['luminance'].as_posix())])
            arguments += [quoted(local[name]) for name in selected]
            arguments += [token('-out=' + result.as_posix())] + (['-nosum'] if values['no_sum'] else [])
            commands.append('rgbcomp ' + ' '.join(arguments))
        add_file(outputs, 'image', result)
    elif mode in {'merge_sequences', 'stack_all', 'sequence_merge_cfa'}:
        sequences = []
        names = ['cfa' + str(index) for index in range(4)] if mode == 'sequence_merge_cfa' else ['sequences']
        for name in names:
            for index, paths in enumerate(source_groups[name]):
                folder = directory if mode == 'stack_all' else directory / f'{name}-{index:06d}'
                base = stage_sequence(commands, paths, supporting_groups.get(name, [[]])[index], folder,
                                       base_hint=f'group{index:06d}_' if mode == 'stack_all' else None,
                                       metadata=[item for item in source_metadata.get(name, []) if item.reference_index == index])
                sequences.append(folder / base)
        commands.append('cd ' + quoted(directory))
        if mode == 'merge_sequences':
            if len(sequences) < 2:
                raise ValueError('Sequence merge needs at least two fixed sequences.')
            commands.append('merge ' + ' '.join(quoted(path) for path in sequences) + ' result_')
            commands.append('getref result_')
            sequence_output(outputs, 'image', directory, directory, 'result_')
        elif mode == 'sequence_merge_cfa':
            commands.append('seqmerge_cfa ' + ' '.join(quoted(path) for path in sequences) + ' ' + values['bayer_pattern'])
            sequence_output(outputs, 'image', directory, directory, 'mCFA_')
        else:
            commands.append('stackall ' + ' '.join(stack_arguments(recipe, values)))
            extension = '.fit.fz' if runtime.compression_enabled else '.fit'
            add_pattern(outputs, 'image', directory, directory, '*stacked*' + extension, minimum=len(sequences))
            outputs.setdefault('rejection_maps', ProcessOutput())
            if values['rejection_maps'] != 'none':
                add_pattern(outputs, 'rejection_maps', directory, directory, '*rej*.fit*')
    elif mode == 'makepsf':
        images = sources.get('image', [])
        if values['method'] in {'blind', 'stars'} and not images:
            raise ValueError('Blind or star PSF estimation requires a fixed image.')
        for index, source in enumerate(images or [None]):
            folder = directory / f'member-{index:06d}'; folder.mkdir()
            commands.append('cd ' + quoted(folder))
            if source is not None:
                commands.append('load ' + quoted(source))
                commands.extend(selection_commands(runtime))
            if values['method'] == 'stars':
                commands.append('findstar')
            arguments = [values['method']]
            if values['method'] == 'manual':
                arguments.append('-' + values['function'])
            arguments += encode_parameters(recipe, values) + [token('-savepsf=' + (folder / 'psf.fit').as_posix())]
            commands.append('makepsf ' + ' '.join(arguments))
            add_file(outputs, 'psf', folder / 'psf.fit')
            commands.append('close')
    elif mode == 'pixel_math':
        paths = []
        for index, source in enumerate(sources['images']):
            paths.append(source if source.name.lower().endswith(('.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz')) else copy_fits(commands, source, directory / f'input-{index:06d}.fit'))
        expression = values['expression']
        if re.sub(r'\$\d+|\$T\b', '', expression).find('$') >= 0:
            raise ValueError('PixelMath image references must be $0, $1, … or $T from fixed inputs.')
        def replace(match):
            index = int(match.group(1))
            if index >= len(paths):
                raise ValueError('PixelMath input index is outside the fixed input list.')
            return '$' + paths[index].as_posix() + '$'
        expression = re.sub(r'\$(\d+)', replace, expression)
        commands.append('load ' + quoted(paths[0]))
        arguments = [token(expression)]
        if values['rescale']:
            arguments += ['-rescale', scalar(values['low']), scalar(values['high'])]
        if values['no_sum']:
            arguments.append('-nosum')
        commands += ['pm ' + ' '.join(arguments), 'save ' + quoted(directory / 'result.fit')]
        add_file(outputs, 'image', directory / 'result.fit')
    elif mode == 'live_stack':
        paths = [copy_fits(commands, source, directory / f'input-{index:06d}.fit') for index, source in enumerate(sources['image'])]
        arguments = encode_parameters(recipe, values)
        for name in ['dark', 'flat']:
            if name in sources:
                arguments.append(token('-' + name + '=' + sources[name][0].as_posix()))
        commands.append('start_ls ' + ' '.join(arguments))
        commands.extend('livestack ' + quoted(path) for path in paths)
        commands.append('stop_ls')
        add_file(outputs, 'image', directory / 'live_stack_00001.fit')
        layout.expected_live_frames = len(paths)
    elif mode == 'python_script':
        paths = []
        for index, source in enumerate(sources.get('image', [])):
            target = directory / (f'input-{index:06d}' + ''.join(source.suffixes))
            shutil.copy2(source, target)
            paths.append(target)
        if paths and values['load_image']:
            commands.append('load ' + quoted(paths[0]))
        script = directory / 'user-script.py'
        if values['script_source'] == 'file':
            if 'script_file' not in sources:
                raise ValueError('File script mode requires a fixed library script file input.')
            shutil.copy2(sources['script_file'][0], script)
        else:
            script.write_text(values['script'], encoding='utf-8')
        arguments = json_value(values['arguments'], list, 'arguments')
        if any(not isinstance(argument, str) for argument in arguments):
            raise ValueError('Python script arguments must be a JSON array of strings.')
        for index, path in enumerate(paths):
            arguments = [argument.replace('{input' + str(index) + '}', path.as_posix()) for argument in arguments]
        commands.append('pyscript ' + quoted(script) + (' ' + ' '.join(token(argument) for argument in arguments) if arguments else ''))
        outputs.update(image=ProcessOutput(), files=ProcessOutput())
        for entry in json_value(values['output_files'], list, 'output_files'):
            if not isinstance(entry, dict) or set(entry) - {'pattern', 'format', 'role'} or not {'pattern', 'format'}.issubset(entry):
                raise ValueError('Script outputs require pattern and format, with optional science/file role.')
            pattern = entry['pattern']
            if Path(pattern).is_absolute() or '..' in Path(pattern).parts:
                raise ValueError('Script output patterns must be relative to this invocation.')
            inside(directory, pattern)
            role = entry.get('role', 'file')
            if role not in {'science', 'file'}:
                raise ValueError('Script output role must be science or file.')
            add_pattern(outputs, 'image' if role == 'science' else 'files', directory, directory, pattern, entry['format'])
        add_file(outputs, 'analysis', directory / 'analysis.json', 'other')
    else:
        raise ValueError('Unsupported execution mode: ' + mode)
