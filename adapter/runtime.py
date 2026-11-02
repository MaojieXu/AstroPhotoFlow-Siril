from __future__ import annotations

import configparser
import math
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import JsonValue

from .arguments import json_value, scalar, token
from .types import RuntimeOptions


def prepare_runtime(directory: Path, values: Mapping[str, JsonValue]) -> tuple[list[str], RuntimeOptions]:
    runtime = json_value(values.get('runtime', '{}'), dict, 'runtime')
    unknown = set(runtime) - {'ini', 'settings', 'threads', 'memory_ratio', 'output_bits', 'compression', 'online', 'selection', 'findstar', 'photometry'}
    if unknown:
        raise ValueError('Unknown runtime settings: ' + ', '.join(sorted(unknown)))
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    ini = runtime.get('ini', '[core]\n')
    if type(ini) is not str:
        raise ValueError('runtime.ini must be text, not null.')
    parser.read_string(ini)
    if not parser.has_section('core'):
        parser.add_section('core')
    parser.set('core', 'wd', directory.resolve().as_posix())
    parser.set('core', 'swap_dir', (directory / 'tmp').resolve().as_posix())
    with (directory / 'siril.ini').open('w', encoding='utf-8') as stream:
        parser.write(stream)
    commands = ['requires 1.4.4', 'setext fit', 'set32bits', 'pwd']
    settings = runtime.get('settings', {})
    if type(settings) is not dict:
        raise ValueError('runtime.settings must be an object.')
    for name, value in settings.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]*', name) or name in {'core.wd', 'core.swap_dir', 'core.extension'}:
            raise ValueError('This setting is controlled by the invocation: ' + name)
        if value is None or isinstance(value, (dict, list)):
            raise ValueError('Siril setting values must be explicit scalars; null is not omission.')
        commands.append('set ' + token(name + '=' + scalar(value)))
    if 'threads' in runtime:
        count = runtime['threads']
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError('runtime.threads must be a positive integer.')
        commands.append('setcpu ' + str(count))
    if 'memory_ratio' in runtime:
        ratio = runtime['memory_ratio']
        if isinstance(ratio, bool) or not isinstance(ratio, (float, int)) or not math.isfinite(ratio) or not 0.05 <= ratio <= 4:
            raise ValueError('runtime.memory_ratio must be finite and in the Siril range [0.05,4].')
        commands.append('setmem ' + scalar(ratio))
    if 'output_bits' in runtime:
        if type(runtime['output_bits']) is not int or runtime['output_bits'] not in (16, 32):
            raise ValueError('runtime.output_bits must be 16 or 32.')
        commands.append('set' + str(runtime['output_bits']) + 'bits')
    commands.append('setcompress 0')
    compression = runtime.get('compression')
    if 'compression' in runtime:
        if not isinstance(compression, dict) or set(compression) - {'enabled', 'type', 'quantisation'} or type(compression.get('enabled')) is not bool:
            raise ValueError('runtime.compression requires an explicit enabled boolean.')
        if not compression['enabled']:
            commands.append('setcompress 0')
        else:
            method, quantisation = compression.get('type', 'rice'), compression.get('quantisation', 16)
            if method not in {'rice', 'gzip1', 'gzip2'} or isinstance(quantisation, bool) or not isinstance(quantisation, (int, float)):
                raise ValueError('Invalid FITS compression settings.')
            commands.append('setcompress 1 -type=' + method + ' ' + scalar(quantisation))
    for name, command, options in [
        ('findstar', 'setfindstar', {'radius', 'sigma', 'roundness', 'focal', 'pixelsize', 'convergence', 'gaussian', 'moffat', 'minbeta', 'relax', 'minA', 'maxA', 'maxR', 'reset'}),
        ('photometry', 'setphot', {'inner', 'outer', 'aperture', 'dyn_ratio', 'gain', 'min_val', 'max_val'}),
    ]:
        if name not in runtime:
            continue
        mapping = runtime[name]
        if not isinstance(mapping, dict) or set(mapping) - options:
            raise ValueError('Invalid runtime.' + name + ' controls.')
        arguments = []
        for key, value in mapping.items():
            if key in {'gaussian', 'moffat', 'reset'}:
                if type(value) is not bool:
                    raise ValueError(key + ' must be a boolean.')
                if value:
                    arguments.append('reset' if key == 'reset' else '-' + key)
            else:
                if value is None:
                    raise ValueError('null does not mean an omitted Siril control.')
                arguments.append(token('-' + key + '=' + scalar(value)))
        if arguments:
            commands.append(command + ' ' + ' '.join(arguments))
    if 'online' in runtime and type(runtime['online']) is not bool:
        raise ValueError('runtime.online must be a boolean.')
    if runtime.get('online', False):
        commands.append('online')
    selected = runtime.get('selection')
    if selected is not None and not isinstance(selected, list):
        raise ValueError('runtime.selection must be [x,y,width,height] or null to clear.')
    options = RuntimeOptions(threads=runtime.get('threads'), compression_enabled=runtime.get('compression', {}).get('enabled', False),
        selection_set='selection' in runtime, selection=tuple(selected) if selected is not None else None)
    selection_commands(options)
    return commands, options


def selection_commands(runtime: RuntimeOptions) -> list[str]:
    if not runtime.selection_set:
        return []
    selection = runtime.selection
    if selection is None:
        return ['boxselect -clear']
    if not isinstance(selection, tuple) or len(selection) != 4 or any(type(value) is not int for value in selection):
        raise ValueError('runtime.selection must be [x,y,width,height] or null to clear.')
    if min(selection[:2]) < 0 or min(selection[2:]) <= 0:
        raise ValueError('Selection coordinates must be nonnegative and dimensions positive.')
    return ['boxselect ' + ' '.join(map(str, selection))]
