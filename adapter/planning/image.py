from __future__ import annotations

import math
import shutil

from astrophotoflow.contracts.bundles import (
    ProcessOutput,
)

from ..arguments import analysis_command, calibration_arguments, header_arguments, image_arguments, json_value, quoted, scalar
from ..outputs import EXPORTS, add_file, add_pattern
from ..runtime import selection_commands
from ..types import BuildContext

IMAGE_MODES = frozenset({'image', 'image_operand', 'analysis', 'split', 'split_cfa', 'extract', 'extract_ha', 'extract_hao', 'extract_green', 'fft_direct', 'export', 'file_transform', 'calibration_single', 'update_header', 'starnet', 'wavelet'})


def build_image(context: BuildContext) -> None:
    recipe = context.recipe
    sources = context.sources
    directory = context.directory
    commands = context.commands
    outputs = context.outputs
    runtime = context.runtime
    layout = context.layout
    preview = context.preview
    prepare_sample = context.prepare_sample
    parameters = context.values
    mode = recipe.mode
    operation_id = recipe.command
    for index, source in enumerate(sources['image']):
        folder = directory if preview else directory / f'member-{index:06d}'
        folder.mkdir(parents=True, exist_ok=True)
        layout.members.append(folder.relative_to(directory).as_posix())
        commands.append('cd ' + quoted(folder))
        if mode in {'calibration_single', 'file_transform'}:
            copied = folder / ('source.fit.fz' if mode == 'file_transform' and runtime.compression_enabled else 'source.fit')
            shutil.copy2(source, copied)
            source = copied
        if mode != 'calibration_single' or runtime.selection_set:
            commands.append('load ' + quoted(source))
        if prepare_sample:
            commands.extend(['resample -maxdim=1024 -interp=area', 'save ' + quoted(directory / 'linear.fit')])
        if mode in {'starnet', 'extract_green', 'extract_ha', 'extract_hao', 'split_cfa'}:
            source = folder / 'source.fit'
            commands.extend(['save ' + quoted(source), 'close', 'load ' + quoted(source)])
        commands.extend(selection_commands(runtime))
        args = image_arguments(recipe, parameters, sources)
        target = folder / 'result.fit'
        if mode in {'image', 'image_operand'}:
            if operation_id == 'synthstar':
                commands.append('findstar')
            commands.append(operation_id + (' ' + ' '.join(args) if args else ''))
            commands.append('save ' + quoted(target))
            add_file(outputs, 'image', target)
        elif mode == 'analysis':
            if operation_id == 'psf':
                commands.extend(selection_commands({'selection': json_value(parameters['selection'], list, 'selection')}))
            commands.append(analysis_command(operation_id, recipe, parameters, folder, source))
            add_file(outputs, 'analysis', folder / 'analysis.json', 'other')
            outputs.setdefault('files', ProcessOutput())
            for pattern in {'histo': ['histo_*.dat'], 'jsonmetadata': ['metadata.json'], 'findstar': ['stars.lst'],
                            'find_hot': ['badpixels.lst'], 'profile': ['profile.dat'], 'conesearch': ['catalogue.csv'],
                            'findcompstars': ['catalogue.csv']}.get(operation_id, []):
                add_pattern(outputs, 'files', directory, folder, pattern, 'other')
            if operation_id == 'profile':
                add_pattern(outputs, 'files', directory, folder, 'profile.png', 'image', minimum=0)
        elif mode == 'export':
            suffix, format = EXPORTS[operation_id]
            target = folder / ('result' + suffix)
            argument = target if operation_id in {'save', 'savepnm'} else folder / 'result'
            commands.append(operation_id + ' ' + quoted(argument) + (' ' + ' '.join(args) if args else ''))
            add_file(outputs, 'image' if operation_id == 'save' else 'file', target, format)
        elif mode == 'update_header':
            commands.extend(['update_key ' + ' '.join(header_arguments(parameters)), 'save ' + quoted(target)])
            add_file(outputs, 'image', target)
        elif mode == 'file_transform':
            commands.extend(['close', 'mirrorx_single ' + quoted(source)])
            add_file(outputs, 'image', source)
        elif mode == 'calibration_single':
            commands.append('calibrate_single ' + quoted(source) + ' ' + ' '.join(
                calibration_arguments(parameters, sources) + args + ['-prefix=result_']))
            add_file(outputs, 'image', folder / 'result_source.fit')
        elif mode == 'split':
            names = [folder / ('channel_' + str(channel)) for channel in range(1, 4)]
            commands.append('split ' + ' '.join(quoted(path) for path in names) +
                            ('' if parameters['colour_space'] == 'rgb' else ' -' + parameters['colour_space']))
            for channel, path in enumerate(names, 1):
                add_file(outputs, 'channel_' + str(channel), path.with_suffix('.fit'))
        elif mode == 'split_cfa':
            commands.append('split_cfa')
            for channel in range(4):
                add_file(outputs, 'cfa' + str(channel), folder / f'CFA{channel}_source.fit')
        elif mode in {'extract_ha', 'extract_hao', 'extract_green'}:
            commands.append(operation_id + (' ' + ' '.join(args) if args else ''))
            if mode == 'extract_hao':
                add_file(outputs, 'ha', folder / 'Ha_source.fit')
                add_file(outputs, 'oiii', folder / 'OIII_source.fit')
            else:
                add_file(outputs, 'image', folder / ('Green_source.fit' if mode == 'extract_green' else 'Ha_source.fit'))
        elif mode == 'extract':
            commands.append('extract ' + str(parameters['layers']))
            for layer in range(parameters['layers']):
                add_file(outputs, 'layers', folder / f'layer{layer:02d}.fit')
        elif mode == 'fft_direct':
            commands.append('fftd ' + quoted(folder / 'modulus.fit') + ' ' + quoted(folder / 'phase.fit'))
            for name in ['modulus', 'phase']:
                add_file(outputs, name, folder / (name + '.fit'))
        elif mode == 'wavelet':
            coefficients = json_value(parameters['coefficients'], list, 'coefficients')
            if len(coefficients) != parameters['layers'] + 1 or len(coefficients) > 7 or any(
                isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) for value in coefficients):
                raise ValueError('Wavelet reconstruction needs layers + 1 finite coefficients, at most seven.')
            commands.extend(['wavelet ' + str(parameters['layers']) + ' ' + str(parameters['transform']),
                             'wrecons ' + ' '.join(scalar(value) for value in coefficients), 'save ' + quoted(target)])
            add_file(outputs, 'image', target)
        elif mode == 'starnet':
            commands.append('starnet ' + ' '.join(args))
            add_file(outputs, 'image', folder / 'starless_source.fit')
            outputs.setdefault('stars', ProcessOutput())
            if not parameters['no_starmask']:
                add_file(outputs, 'stars', folder / 'starmask_source.fit')
        commands.append('close')
