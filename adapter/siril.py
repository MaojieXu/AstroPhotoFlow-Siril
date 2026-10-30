import configparser
import csv
import io
import json
import math
import re
import runpy
import shutil
from pathlib import Path

from astrophotoflow.contracts.bundles import AnalysisResult, BundleFile, BundleInputMetadata, BundleProgress, NamedProcessPlan, OutputPattern, ProcessOutput


RECIPES = runpy.run_path(str(Path(__file__).with_name('recipes.py')))['RECIPES']
FORMATS = json.loads((Path(__file__).resolve().parents[1] / 'reference/formats.json').read_text(encoding='utf-8'))
EXPORTS = {'save': ('.fit', 'fits'), 'savebmp': ('.bmp', 'image'), 'savejpg': ('.jpg', 'image'),
           'savejxl': ('.jxl', 'image'), 'savepng': ('.png', 'image'), 'savepnm': ('.pnm', 'image'),
           'savetif': ('.tif', 'image'), 'savetif32': ('.tif', 'image'), 'savetif8': ('.tif', 'image')}
SPECIAL_TOKENS = {'channels', 'colour_model', 'denoise_method', 'sos_iterations', 'size_mode', 'size_value',
                  'rectangle', 'rect_x', 'rect_y', 'rect_width', 'rect_height',
                  'background_model', 'background_degree', 'stat_mode', 'selection', 'profile', 'split_mode',
                  'composition_mode', 'header_action', 'header_key', 'header_value', 'header_comment',
                  'wavelet_coefficients', 'psf_method', 'psf_function', 'bias_mode', 'bias_expression',
                  'cosmetic_mode', 'cosmetic_sigmas', 'cold_sigma', 'hot_sigma', 'dark_optimisation',
                  'sequence_format', 'filter_unit', 'stack_method', 'stack_rejection', 'sigma_low', 'sigma_high',
                  'stack_normalisation', 'stack_weight', 'rejection_maps', 'keywords', 'coordinate_type',
                  'star_position', 'reference_positions', 'profile_axis', 'centre_coordinates', 'search_width',
                  'get_query', 'get_variable'}


def token(value):
    value = str(value)
    if not value or any(character in value for character in ('\x00', '\n', '\r')):
        raise ValueError('Siril arguments must be nonempty single-line values.')
    if '"' not in value:
        return '"' + value + '"'
    if "'" not in value:
        return "'" + value + "'"
    raise ValueError('The Siril 1.4.4 parser cannot represent an argument containing both quote types.')


def quoted(path):
    value = Path(path).resolve().as_posix()
    if '"' in value:
        raise ValueError('Siril file paths cannot contain double quotes.')
    return token(value)


def scalar(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (float, int)):
        if not math.isfinite(value):
            raise ValueError('Siril numeric arguments must be finite.')
        return format(value, '.17g')
    return str(value)


def json_value(value, expected, name):
    result = json.loads(value)
    if not isinstance(result, expected):
        raise ValueError(name + ' has the wrong JSON type.')
    return result


def inside(directory, path):
    resolved = (directory / path).resolve()
    if not resolved.is_relative_to(directory.resolve()):
        raise ValueError('Output paths must stay inside this invocation.')
    return resolved


def _tokens(recipe, values, *, skip=()):
    result = []
    for item in recipe['parameters']:
        if item.get('control'):
            continue
        schema = item['schema']
        name, option = schema['name'], item.get('token')
        if name in skip or option in SPECIAL_TOKENS or (item.get('enabled') and not values[item['enabled']]):
            continue
        value = values[name]
        if schema['kind'] == 'boolean':
            if value:
                result.append(option)
            continue
        if option and option.startswith('-filter-'):
            suffix = {'absolute': '', 'percent': '%', 'sigma': 'k'}[values['filter_unit']]
            result.append(token(option + scalar(value) + suffix))
        elif option:
            result.append(token(option + scalar(value)))
        else:
            result.append(token(scalar(value)))
    if 'channels' in values and values['channels'] != 'RGB':
        result.append(values['channels'])
    if 'colour_model' in values:
        result.append('-' + values['colour_model'])
    if 'size_mode' in values:
        size = values['size']
        if size <= 0 or (values['size_mode'] in {'width', 'height', 'maxdim'} and int(size) != size):
            raise ValueError('Output dimensions must be positive integers; scale must be positive.')
        result.insert(0, token(scalar(size) if values['size_mode'] == 'factor' else '-' + values['size_mode'] + '=' + scalar(size)))
    if 'model' in values and recipe['command'] in {'subsky', 'seqsubsky'}:
        result.insert(0, '-rbf' if values['model'] == 'rbf' else str(values['degree']))
    if 'denoise_method' in {item.get('token') for item in recipe['parameters']}:
        if values['method'] in {'vst', 'da3d'}:
            result.append('-' + values['method'])
        elif values['method'] == 'sos':
            result.append('-sos=' + str(values['sos_iterations']))
    if 'statistics' in values and recipe['command'] == 'stat' and values['statistics'] == 'main':
        if values['cfa']:
            raise ValueError('Siril 1.4.4 cannot combine CFA statistics with main; choose one mode.')
        result.append('main')
    if recipe['command'] in {'platesolve', 'seqplatesolve'} and values['use_centre_coordinates']:
        coordinates = values['centre_coordinates']
        if coordinates.lstrip().startswith('['):
            pair = json_value(coordinates, list, 'centre_coordinates')
            if len(pair) != 2 or any(not isinstance(value, str) for value in pair):
                raise ValueError('Centre coordinates need ["RA","Dec"].')
            result[:0] = [token(value) for value in pair]
        elif ',' in coordinates:
            result.insert(0, token(coordinates))
        elif len(coordinates.split()) == 2:
            result[:0] = [token(value) for value in coordinates.split()]
        else:
            raise ValueError('Centre coordinates need RA,Dec or a JSON ["RA","Dec"] pair; sexagesimal strings may contain spaces.')
    if values.get('use_rectangle', False):
        result.extend(scalar(values[name]) for name in ['x', 'y', 'width', 'height'])
    return result


def _runtime(directory, values):
    runtime = json_value(values.get('runtime', '{}'), dict, 'runtime')
    unknown = set(runtime) - {'ini', 'settings', 'threads', 'memory_ratio', 'output_bits', 'compression', 'online', 'selection', 'findstar', 'photometry'}
    if unknown:
        raise ValueError('Unknown runtime settings: ' + ', '.join(sorted(unknown)))
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    ini = runtime.get('ini', '[core]\n')
    if not isinstance(ini, str):
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
    if not isinstance(settings, dict):
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
    return commands, runtime


def _selection(runtime):
    if 'selection' not in runtime:
        return []
    selection = runtime['selection']
    if selection is None:
        return ['boxselect -clear']
    if not isinstance(selection, list) or len(selection) != 4 or any(type(value) is not int for value in selection):
        raise ValueError('runtime.selection must be [x,y,width,height] or null to clear.')
    if min(selection[:2]) < 0 or min(selection[2:]) <= 0:
        raise ValueError('Selection coordinates must be nonnegative and dimensions positive.')
    return ['boxselect ' + ' '.join(map(str, selection))]


def _add_file(outputs, name, path, format='fits'):
    outputs.setdefault(name, ProcessOutput()).files.append(BundleFile(path=path, format=format, frame_count=1 if format == 'fits' else None))


def _add_pattern(outputs, name, directory, folder, pattern, format='fits', minimum=1, supporting=False):
    output = outputs.setdefault(name, ProcessOutput())
    value = OutputPattern(pattern=(folder / pattern).relative_to(directory).as_posix(), format=format, minimum_count=minimum,
                          allow_empty=format == 'other' and pattern.endswith(('.lst', '.csv', '.dat')))
    (output.supporting_patterns if supporting else output.patterns).append(value)


def _fits_copy(commands, source, target):
    commands.extend(['load ' + quoted(source), 'save ' + quoted(target), 'close'])
    return target


def _stage_sequence(commands, sources, supporting, folder, base_hint=None, metadata=()):
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
            _fits_copy(commands, source, folder / f'{base}{index:05d}.fit')
    commands.extend(['cd ' + quoted(folder), 'getref ' + token(base)])
    return base


def _sequence_output(outputs, name, directory, folder, base):
    for suffix, format in [('*.fit', 'fits'), ('*.fit.fz', 'fits'), ('*.ser', 'video'), *[('*' + extension, 'video') for extension in FORMATS['video_extensions']]]:
        _add_pattern(outputs, name, directory, folder, base + suffix, format, minimum=0)
    _add_pattern(outputs, name, directory, folder, base + '*.seq', 'other', supporting=True)
    for suffix in ['*.lst', '*.wcs', '*conversion.txt']:
        _add_pattern(outputs, name, directory, folder, base + suffix, 'other', minimum=0, supporting=True)
    _add_pattern(outputs, name, directory, folder, base + '*.idx', 'other', minimum=0, supporting=True)


def _header_arguments(values):
    action, key, value, comment = (values[name] for name in ['action', 'key', 'value', 'comment'])
    if action == 'comment':
        return ['-comment', token(comment)]
    if not key or len(key) > 8:
        raise ValueError('FITS keyword names must contain 1–8 characters.')
    if action == 'delete':
        return ['-delete', token(key)]
    if action == 'rename':
        return ['-modify', token(key), token(value)]
    return [token(key), token(value)] + ([token(comment)] if comment else [])


def _calibration_arguments(values, sources):
    result = []
    if values['bias_mode'] == 'image':
        if 'bias' not in sources:
            raise ValueError('Image bias calibration requires the fixed bias input.')
        result.append(token('-bias=' + sources['bias'][0].as_posix()))
    elif values['bias_mode'] == 'expression':
        if not values['bias_expression'].startswith('='):
            raise ValueError('A synthetic bias expression must start with =.')
        result.append(token('-bias=' + values['bias_expression']))
    for name in ['dark', 'flat']:
        if name in sources:
            result.append(token('-' + name + '=' + sources[name][0].as_posix()))
    if values['cosmetic'] == 'dark':
        if 'dark' not in sources:
            raise ValueError('Dark cosmetic correction requires a fixed master dark.')
        result.append('-cc=dark')
        if values['cosmetic_sigmas']:
            result.extend([scalar(values['cold_sigma']), scalar(values['hot_sigma'])])
    elif values['cosmetic'] == 'bpm':
        if 'bad_pixels' not in sources:
            raise ValueError('Bad-pixel correction requires a fixed bad pixel map.')
        result.extend(['-cc=bpm', quoted(sources['bad_pixels'][0])])
    if values['dark_optimisation'] != 'none':
        result.append('-opt' if values['dark_optimisation'] == 'optimise' else '-opt=exp')
    return result


def _image_arguments(recipe, values, sources):
    command, arguments = recipe['command'], _tokens(recipe, values)
    if recipe['mode'] == 'image_operand':
        name = 'reference' if command == 'linear_match' else 'bad_pixels' if command.startswith('cosme') else 'operand'
        arguments.insert(0, quoted(sources[name][0]))
    if command in {'icc_assign', 'icc_convert_to'}:
        profile = sources['icc_profile'][0].as_posix() if 'icc_profile' in sources else values['profile']
        arguments.insert(0, token(profile))
    for name, option in [('guide', '-guideimage='), ('psf', '-loadpsf='), ('distortion', '-disto=')]:
        if name in sources:
            if name == 'distortion' and command == 'register':
                arguments.extend(['-disto=file', quoted(sources[name][0])])
            else:
                arguments.append(token(option + sources[name][0].as_posix()))
    if command in {'ght', 'invght', 'modasinh', 'invmodasinh'} and values['stretch'] <= 0:
        raise ValueError('Generalised stretch D must be greater than zero.')
    if command in {'mtf', 'invmtf', 'seqmtf'} and not (0 <= values['low'] < values['high'] <= 1 and 0 < values['mid'] < 1):
        raise ValueError('MTF requires 0 <= low < high <= 1 and 0 < mid < 1.')
    if all(name in values for name in ['low_protection', 'symmetry_point', 'high_protection']):
        if not 0 <= values['low_protection'] <= values['symmetry_point'] <= values['high_protection'] <= 1:
            raise ValueError('GHS requires LP <= SP <= HP.')
    return arguments


def _analysis_command(command, recipe, values, folder, source):
    args = _tokens(recipe, values)
    if command == 'jsonmetadata':
        return command + ' ' + quoted(source) + ' ' + ' '.join(args + [token('-out=' + (folder / 'metadata.json').as_posix())])
    if command == 'findstar':
        args.append(token('-out=' + (folder / 'stars.lst').as_posix()))
    elif command == 'find_hot':
        args.insert(0, quoted(folder / 'badpixels'))
    elif command in {'profile', 'conesearch', 'findcompstars'}:
        args.append(token(('-filename=' if command == 'profile' else '-out=') + (folder / ('profile.dat' if command == 'profile' else 'catalogue.csv')).as_posix()))
    if command == 'findcompstars' and values['search_width'] != 'default':
        args.append('-' + values['search_width'])
    return command + (' ' + ' '.join(args) if args else '')


def _stack_arguments(recipe, values):
    result = [values['method']]
    if values['method'] == 'mean':
        result.extend([values['rejection'], scalar(values['sigma_low']), scalar(values['sigma_high'])])
    if values['method'] in {'mean', 'median'}:
        result.append('-nonorm' if values['normalisation'] == 'none' else '-norm=' + values['normalisation'])
    if values['weight'] != 'none':
        if values['method'] != 'mean':
            raise ValueError('Stacking weights require mean stacking.')
        result.append('-weight=' + values['weight'])
    if values['rejection_maps'] != 'none':
        if values['method'] != 'mean':
            raise ValueError('Rejection maps require mean stacking.')
        result.append('-rejmaps' if values['rejection_maps'] == 'separate' else '-rejmap')
    result.extend(_tokens(recipe, values))
    return result


def _sequence_analysis(command, recipe, values, sources, base, folder):
    args = _tokens(recipe, values)
    if command == 'seqstat':
        args = [quoted(folder / 'statistics.csv'), values['statistics']] + (['-cfa'] if values['cfa'] else [])
    elif command == 'seqheader':
        keywords = json_value(values['keywords'], list, 'keywords')
        if not keywords or any(not isinstance(key, str) or not re.fullmatch('[A-Za-z0-9_-]{1,8}', key) for key in keywords):
            raise ValueError('seqheader requires a nonempty JSON array of FITS keywords.')
        args = [*keywords, *args, token('-out=' + (folder / 'headers.csv').as_posix())]
    elif command in {'seqpsf', 'light_curve'}:
        position = values['position']
        if values['coordinate_type'] != 'nina' and not _coordinate(position, pixel=values['coordinate_type'] == 'pixel'):
            raise ValueError('Star position must contain two comma-separated numbers.')
        if values['coordinate_type'] == 'nina':
            if 'nina_stars' not in sources:
                raise ValueError('NINA photometry requires the fixed comparison-star file.')
            args.append(token('-ninastars=' + sources['nina_stars'][0].as_posix()))
        else:
            args.append(token(('-at=' if values['coordinate_type'] == 'pixel' else '-wcs=') + position))
        if command == 'light_curve' and values['coordinate_type'] != 'nina':
            references = json_value(values['reference_positions'], list, 'reference_positions')
            if not references:
                raise ValueError('A light curve requires explicit comparison stars.')
            for position in references:
                if not _coordinate(position, pixel=values['coordinate_type'] == 'pixel'):
                    raise ValueError('Reference positions must be comma-separated numeric pairs.')
                args.append(token(('-refat=' if values['coordinate_type'] == 'pixel' else '-refwcs=') + position))
    elif command == 'seqprofile':
        args.append('-savedat')
        if values['x_axis'] != 'distance':
            args.append('-xaxis=' + values['x_axis'])
    return command + ' ' + token(base) + (' ' + ' '.join(args) if args else '')


def _build_sequence(recipe, sources, values, directory, commands, outputs, runtime, supporting_sources, source_metadata, layout):
    command, mode = recipe['command'], recipe['mode']
    folder = directory / 'sequence'
    base = _stage_sequence(commands, sources['image'], supporting_sources.get('image', []), folder, metadata=source_metadata.get('image', []))
    layout['sequences'].append({'folder': 'sequence', 'input_base': base, 'output_base': base})
    if runtime.get('selection') is not None:
        commands.append('load ' + quoted(sources['image'][0]))
        commands.extend(_selection(runtime))
    arguments = _image_arguments(recipe, values, sources)
    output_base = 'result_' + base
    if mode == 'sequence_analysis':
        commands.append(_sequence_analysis(command, recipe, values, sources, base, folder))
        _sequence_output(outputs, 'image', directory, folder, base)
        _add_file(outputs, 'analysis', folder / 'analysis.json', 'other')
        outputs.setdefault('files', ProcessOutput())
        for pattern in {'seqstat': ['statistics.csv'], 'seqheader': ['headers.csv'], 'seqfindstar': ['*.lst'],
                        'seqprofile': ['*.dat'], 'light_curve': ['*.dat'], 'seqpsf': ['*.dat']}.get(command, []):
            _add_pattern(outputs, 'files', directory, folder, pattern, 'other', minimum=0 if command in {'seqpsf', 'light_curve'} else 1)
        if command in {'seqprofile', 'light_curve', 'seqpsf', 'seqtilt'}:
            _add_pattern(outputs, 'files', directory, folder, '*.png', 'image', minimum=0)
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
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(_header_arguments(values)))
        output_base = base
    elif mode == 'calibration_sequence':
        arguments = _calibration_arguments(values, sources) + arguments + ['-prefix=result_']
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
    elif mode in {'registration', 'apply_registration'}:
        if 'flat' in sources:
            arguments.append(token('-flat=' + sources['flat'][0].as_posix()))
        arguments.append('-prefix=result_')
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
        if command == 'register' and values['two_pass']:
            output_base = base
    elif mode == 'stack':
        commands.append('stack ' + token(base) + ' ' + ' '.join(_stack_arguments(recipe, values) + [token('-out=' + (folder / 'stacked.fit').as_posix())]))
        _add_file(outputs, 'image', folder / 'stacked.fit')
        outputs.setdefault('rejection_maps', ProcessOutput())
        if values['rejection_maps'] != 'none':
            _add_pattern(outputs, 'rejection_maps', directory, folder, '*rej*.fit*', minimum=1)
        return
    elif mode == 'sequence_split_cfa':
        commands.append('seqsplit_cfa ' + token(base))
        for index in range(4):
            _sequence_output(outputs, 'cfa' + str(index), directory, folder, f'CFA{index}_' + base)
        return
    elif mode == 'sequence_starnet':
        commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
        _sequence_output(outputs, 'image', directory, folder, 'starless_' + base)
        outputs.setdefault('stars', ProcessOutput())
        if not values['no_starmask']:
            _sequence_output(outputs, 'stars', directory, folder, 'starmask_' + base)
        return
    elif mode == 'sequence_transform':
        if 'bad_pixels' in sources:
            arguments.insert(0, quoted(sources['bad_pixels'][0]))
        if command == 'seqextract_HaOIII':
            commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
            for name, prefix in [('ha', 'Ha_'), ('oiii', 'OIII_')]:
                _sequence_output(outputs, name, directory, folder, prefix + base)
            return
        if command in {'seqrl', 'seqsb', 'seqwiener'}:
            output_base = 'dec_' + base
            commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments))
        else:
            commands.append(command + ' ' + token(base) + ' ' + ' '.join(arguments + ['-prefix=result_']))
    else:
        raise ValueError('Unsupported sequence execution mode: ' + mode)
    layout['sequences'][-1]['output_base'] = output_base
    _sequence_output(outputs, 'image', directory, folder, output_base)


def _build_non_image(recipe, sources, values, directory, commands, outputs, runtime,
                     supporting_sources, source_groups, supporting_groups, source_metadata, layout):
    mode, command = recipe['mode'], recipe['command']
    if mode in {'sequence_transform', 'sequence_analysis', 'sequence_state', 'sequence_header_update',
                'calibration_sequence', 'registration', 'apply_registration', 'stack', 'sequence_split_cfa', 'sequence_starnet'}:
        _build_sequence(recipe, sources, values, directory, commands, outputs, runtime, supporting_sources, source_metadata, layout)
    elif mode == 'metadata':
        args = _tokens(recipe, values)
        if command == 'get':
            args = [token(values['variable_name'])] if values['query'] == 'variable' else ['-A' if values['query'] == 'all_with_comments' else '-a']
        commands.append(command + (' ' + ' '.join(args) if args else ''))
        _add_file(outputs, 'analysis', directory / 'analysis.json', 'other')
        outputs.setdefault('files', ProcessOutput())
    elif mode == 'conversion':
        folder, result = directory / 'sources', directory / 'sequence'
        folder.mkdir(); result.mkdir()
        permitted = FORMATS['static_extensions']['raw'] if command == 'convertraw' else FORMATS['static_extensions']['fits'] + FORMATS['compressed_fits_extensions'] if command == 'link' else [suffix for group in FORMATS['static_extensions'].values() for suffix in group] + FORMATS['compressed_fits_extensions']
        if any(not source.name.lower().endswith(tuple(permitted)) for source in sources['image']):
            raise ValueError('The conversion input includes a file type this fixed Siril build would skip; no partial conversion is started.')
        for index, source in enumerate(sources['image']):
            shutil.copy2(source, folder / (f'input-{index:06d}' + ''.join(source.suffixes)))
        commands.extend(['cd ' + quoted(folder), command + ' result_ ' + ' '.join(_tokens(recipe, values) + [token('-out=' + result.as_posix())])])
        if command != 'link' and values['sequence_format'] != 'images':
            commands[-1] += ' -' + values['sequence_format']
        commands.extend(['cd ' + quoted(result), 'getref result_'])
        _sequence_output(outputs, 'image', directory, result, 'result_')
        layout['sequences'].append({'folder': 'sequence', 'output_base': 'result_', 'expected_frames': len(sources['image'])})
    elif mode in {'fft_inverse', 'rgb_composition', 'merge_cfa'}:
        local = {}
        for name, paths in sources.items():
            local[name] = paths[0] if paths[0].name.lower().endswith(('.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz')) else _fits_copy(commands, paths[0], directory / (name + '.fit'))
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
        _add_file(outputs, 'image', result)
    elif mode in {'merge_sequences', 'stack_all', 'sequence_merge_cfa'}:
        sequences = []
        names = ['cfa' + str(index) for index in range(4)] if mode == 'sequence_merge_cfa' else ['sequences']
        for name in names:
            for index, paths in enumerate(source_groups[name]):
                folder = directory if mode == 'stack_all' else directory / f'{name}-{index:06d}'
                base = _stage_sequence(commands, paths, supporting_groups.get(name, [[]])[index], folder,
                                       base_hint=f'group{index:06d}_' if mode == 'stack_all' else None,
                                       metadata=[item for item in source_metadata.get(name, []) if item.reference_index == index])
                sequences.append(folder / base)
        commands.append('cd ' + quoted(directory))
        if mode == 'merge_sequences':
            if len(sequences) < 2:
                raise ValueError('Sequence merge needs at least two fixed sequences.')
            commands.append('merge ' + ' '.join(quoted(path) for path in sequences) + ' result_')
            commands.append('getref result_')
            _sequence_output(outputs, 'image', directory, directory, 'result_')
        elif mode == 'sequence_merge_cfa':
            commands.append('seqmerge_cfa ' + ' '.join(quoted(path) for path in sequences) + ' ' + values['bayer_pattern'])
            _sequence_output(outputs, 'image', directory, directory, 'mCFA_')
        else:
            commands.append('stackall ' + ' '.join(_stack_arguments(recipe, values)))
            extension = '.fit.fz' if runtime.get('compression', {}).get('enabled', False) else '.fit'
            _add_pattern(outputs, 'image', directory, directory, '*stacked*' + extension, minimum=len(sequences))
            outputs.setdefault('rejection_maps', ProcessOutput())
            if values['rejection_maps'] != 'none':
                _add_pattern(outputs, 'rejection_maps', directory, directory, '*rej*.fit*')
    elif mode == 'makepsf':
        images = sources.get('image', [])
        if values['method'] in {'blind', 'stars'} and not images:
            raise ValueError('Blind or star PSF estimation requires a fixed image.')
        for index, source in enumerate(images or [None]):
            folder = directory / f'member-{index:06d}'; folder.mkdir()
            commands.append('cd ' + quoted(folder))
            if source is not None:
                commands.append('load ' + quoted(source))
                commands.extend(_selection(runtime))
            if values['method'] == 'stars':
                commands.append('findstar')
            arguments = [values['method']]
            if values['method'] == 'manual':
                arguments.append('-' + values['function'])
            arguments += _tokens(recipe, values) + [token('-savepsf=' + (folder / 'psf.fit').as_posix())]
            commands.append('makepsf ' + ' '.join(arguments))
            _add_file(outputs, 'psf', folder / 'psf.fit')
            commands.append('close')
    elif mode == 'pixel_math':
        paths = []
        for index, source in enumerate(sources['images']):
            paths.append(source if source.name.lower().endswith(('.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz')) else _fits_copy(commands, source, directory / f'input-{index:06d}.fit'))
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
        _add_file(outputs, 'image', directory / 'result.fit')
    elif mode == 'live_stack':
        paths = [_fits_copy(commands, source, directory / f'input-{index:06d}.fit') for index, source in enumerate(sources['image'])]
        arguments = _tokens(recipe, values)
        for name in ['dark', 'flat']:
            if name in sources:
                arguments.append(token('-' + name + '=' + sources[name][0].as_posix()))
        commands.append('start_ls ' + ' '.join(arguments))
        commands.extend('livestack ' + quoted(path) for path in paths)
        commands.append('stop_ls')
        _add_file(outputs, 'image', directory / 'live_stack_00001.fit')
        layout['expected_live_frames'] = len(paths)
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
            _add_pattern(outputs, 'image' if role == 'science' else 'files', directory, directory, pattern, entry['format'])
        _add_file(outputs, 'analysis', directory / 'analysis.json', 'other')
    else:
        raise ValueError('Unsupported execution mode: ' + mode)


def _compressed_paths(commands, outputs, runtime):
    if not runtime.get('compression', {}).get('enabled', False):
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


def build_plan(operation_id, sources, parameters, directory, *, preview=False, prepare_sample=False,
               supporting_sources=None, source_groups=None, supporting_groups=None, source_metadata=None):
    if operation_id not in RECIPES:
        raise ValueError('Unsupported operation: ' + operation_id)
    recipe = RECIPES[operation_id]
    if preview and not recipe['live']:
        raise ValueError('This operation does not support display-sample preview.')
    directory = Path(directory).resolve()
    sources = {name: [Path(path).resolve() for path in paths] for name, paths in sources.items()}
    supporting_sources = supporting_sources or {}
    source_groups = source_groups or {name: [paths] for name, paths in sources.items()}
    supporting_groups = supporting_groups or {name: [supporting_sources.get(name, [])] for name in sources}
    source_metadata = {name: [BundleInputMetadata.model_validate(item) for item in items] for name, items in (source_metadata or {}).items()}
    commands, runtime = _runtime(directory, parameters)
    (directory / 'parameters.json').write_text(json.dumps(parameters, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    outputs = {}
    mode = recipe['mode']
    layout = {'operation_id': operation_id, 'members': [], 'sequences': []}
    for definition in recipe['inputs']:
        name = definition['name']
        if definition['cardinality'] != 'one' or definition['type'] != 'APF_SCIENCE' or name not in sources:
            continue
        source = sources[name][0]
        if not source.name.lower().endswith(('.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz')):
            folder = directory / 'operands'; folder.mkdir(exist_ok=True)
            sources[name] = [_fits_copy(commands, source, folder / (name + '.fit'))]
    if mode in {'image', 'image_operand', 'analysis', 'split', 'split_cfa', 'extract', 'extract_ha', 'extract_hao',
                'extract_green', 'fft_direct', 'export', 'file_transform', 'calibration_single', 'update_header', 'starnet', 'wavelet'}:
        for index, source in enumerate(sources['image']):
            folder = directory if preview else directory / f'member-{index:06d}'
            folder.mkdir(parents=True, exist_ok=True)
            layout['members'].append(folder.relative_to(directory).as_posix())
            commands.append('cd ' + quoted(folder))
            if mode in {'calibration_single', 'file_transform'}:
                copied = folder / ('source.fit.fz' if mode == 'file_transform' and runtime.get('compression', {}).get('enabled', False) else 'source.fit')
                shutil.copy2(source, copied)
                source = copied
            if mode != 'calibration_single' or 'selection' in runtime:
                commands.append('load ' + quoted(source))
            if prepare_sample:
                commands.extend(['resample -maxdim=1024 -interp=area', 'save ' + quoted(directory / 'linear.fit')])
            if mode in {'starnet', 'extract_green', 'extract_ha', 'extract_hao', 'split_cfa'}:
                source = folder / 'source.fit'
                commands.extend(['save ' + quoted(source), 'close', 'load ' + quoted(source)])
            commands.extend(_selection(runtime))
            args = _image_arguments(recipe, parameters, sources)
            target = folder / 'result.fit'
            if mode in {'image', 'image_operand'}:
                if operation_id == 'synthstar':
                    commands.append('findstar')
                commands.append(operation_id + (' ' + ' '.join(args) if args else ''))
                commands.append('save ' + quoted(target))
                _add_file(outputs, 'image', target)
            elif mode == 'analysis':
                if operation_id == 'psf':
                    commands.extend(_selection({'selection': json_value(parameters['selection'], list, 'selection')}))
                commands.append(_analysis_command(operation_id, recipe, parameters, folder, source))
                _add_file(outputs, 'analysis', folder / 'analysis.json', 'other')
                outputs.setdefault('files', ProcessOutput())
                for pattern in {'histo': ['histo_*.dat'], 'jsonmetadata': ['metadata.json'], 'findstar': ['stars.lst'],
                                'find_hot': ['badpixels.lst'], 'profile': ['profile.dat'], 'conesearch': ['catalogue.csv'],
                                'findcompstars': ['catalogue.csv']}.get(operation_id, []):
                    _add_pattern(outputs, 'files', directory, folder, pattern, 'other')
                if operation_id == 'profile':
                    _add_pattern(outputs, 'files', directory, folder, 'profile.png', 'image', minimum=0)
            elif mode == 'export':
                suffix, format = EXPORTS[operation_id]
                target = folder / ('result' + suffix)
                argument = target if operation_id in {'save', 'savepnm'} else folder / 'result'
                commands.append(operation_id + ' ' + quoted(argument) + (' ' + ' '.join(args) if args else ''))
                _add_file(outputs, 'image' if operation_id == 'save' else 'file', target, format)
            elif mode == 'update_header':
                commands.extend(['update_key ' + ' '.join(_header_arguments(parameters)), 'save ' + quoted(target)])
                _add_file(outputs, 'image', target)
            elif mode == 'file_transform':
                commands.extend(['close', 'mirrorx_single ' + quoted(source)])
                _add_file(outputs, 'image', source)
            elif mode == 'calibration_single':
                commands.append('calibrate_single ' + quoted(source) + ' ' + ' '.join(
                    _calibration_arguments(parameters, sources) + args + ['-prefix=result_']))
                _add_file(outputs, 'image', folder / 'result_source.fit')
            elif mode == 'split':
                names = [folder / ('channel_' + str(channel)) for channel in range(1, 4)]
                commands.append('split ' + ' '.join(quoted(path) for path in names) +
                                ('' if parameters['colour_space'] == 'rgb' else ' -' + parameters['colour_space']))
                for channel, path in enumerate(names, 1):
                    _add_file(outputs, 'channel_' + str(channel), path.with_suffix('.fit'))
            elif mode == 'split_cfa':
                commands.append('split_cfa')
                for channel in range(4):
                    _add_file(outputs, 'cfa' + str(channel), folder / f'CFA{channel}_source.fit')
            elif mode in {'extract_ha', 'extract_hao', 'extract_green'}:
                commands.append(operation_id + (' ' + ' '.join(args) if args else ''))
                if mode == 'extract_hao':
                    _add_file(outputs, 'ha', folder / 'Ha_source.fit')
                    _add_file(outputs, 'oiii', folder / 'OIII_source.fit')
                else:
                    _add_file(outputs, 'image', folder / ('Green_source.fit' if mode == 'extract_green' else 'Ha_source.fit'))
            elif mode == 'extract':
                commands.append('extract ' + str(parameters['layers']))
                for layer in range(parameters['layers']):
                    _add_file(outputs, 'layers', folder / f'layer{layer:02d}.fit')
            elif mode == 'fft_direct':
                commands.append('fftd ' + quoted(folder / 'modulus.fit') + ' ' + quoted(folder / 'phase.fit'))
                for name in ['modulus', 'phase']:
                    _add_file(outputs, name, folder / (name + '.fit'))
            elif mode == 'wavelet':
                coefficients = json_value(parameters['coefficients'], list, 'coefficients')
                if len(coefficients) != parameters['layers'] + 1 or len(coefficients) > 7 or any(
                    isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) for value in coefficients):
                    raise ValueError('Wavelet reconstruction needs layers + 1 finite coefficients, at most seven.')
                commands.extend(['wavelet ' + str(parameters['layers']) + ' ' + str(parameters['transform']),
                                 'wrecons ' + ' '.join(scalar(value) for value in coefficients), 'save ' + quoted(target)])
                _add_file(outputs, 'image', target)
            elif mode == 'starnet':
                commands.append('starnet ' + ' '.join(args))
                _add_file(outputs, 'image', folder / 'starless_source.fit')
                outputs.setdefault('stars', ProcessOutput())
                if not parameters['no_starmask']:
                    _add_file(outputs, 'stars', folder / 'starmask_source.fit')
            commands.append('close')
    else:
        _build_non_image(recipe, sources, parameters, directory, commands, outputs, runtime,
                         supporting_sources, source_groups, supporting_groups, source_metadata, layout)
    sequence_queries = set()
    for output in outputs.values():
        for pattern in output.supporting_patterns:
            if pattern.pattern.endswith('*.seq'):
                prefix = directory / pattern.pattern.removesuffix('*.seq')
                query = str(prefix)
                if query not in sequence_queries:
                    commands.extend(['cd ' + quoted(prefix.parent), 'getref ' + token(prefix.name)])
                    sequence_queries.add(query)
    script = directory / 'operation.ssf'
    script.write_text('\n'.join(_compressed_paths(commands, outputs, runtime)) + '\n', encoding='utf-8')
    (directory / 'layout.json').write_text(json.dumps(layout, ensure_ascii=False), encoding='utf-8')
    return NamedProcessPlan(arguments=['-o', '-i', str(directory / 'siril.ini'), '-d', str(directory), '-s', str(script)],
                            outputs=outputs, temporary_directory=directory / 'tmp', thread_limit=runtime.get('threads'),
                            environment={'LC_ALL': 'C', 'LANG': 'C', 'LANGUAGE': 'C'},
                            linear_sample=directory / ('linear.fit.fz' if runtime.get('compression', {}).get('enabled', False) else 'linear.fit') if prepare_sample else None)


def _cell(value):
    stripped = value.strip()
    if not stripped or stripped.lower() in {'nan', '-nan', '+nan', 'inf', '+inf', '-inf', 'n/a'}:
        return None
    if re.fullmatch(r'[+-]?\d+', stripped):
        number = int(stripped)
        # Catalogue identifiers can exceed JavaScript's exact integer range.
        return number if abs(number) <= 2**53 - 1 else stripped
    try:
        number = float(stripped)
    except ValueError:
        return stripped
    if not math.isfinite(number):
        return None
    return number


def _table(path, command):
    rows, columns, count = [], [], 0
    with path.open('r', encoding='utf-8', errors='replace', newline='') as stream:
        content = (line for line in stream if line.strip() and not line.lstrip().startswith('#'))
        records = csv.reader(content, delimiter='\t' if command == 'seqstat' else ',') if path.suffix.lower() == '.csv' else (line.split() for line in content)
        for record in records:
            values = [_cell(value) for value in record]
            if not columns:
                if path.suffix.lower() == '.lst' and record[0] == 'P':
                    columns = ['record', 'x', 'y', 'pixel_type']
                elif any(isinstance(value, str) for value in values):
                    columns = [str(value) if value is not None else 'unnamed' for value in values]
                    continue
                else:
                    columns = ['column_' + str(index + 1) for index in range(len(values))]
            count += 1
            if len(rows) < 200:
                rows.append(values + [None] * max(0, len(columns) - len(values)))
    return AnalysisResult(kind='table', title=path.name, source='Siril 1.4.4 ' + command, columns=columns,
                          rows=rows, values={'row_count': count, 'source_file': path.name},
                          sample=f'First {len(rows)} of {count} rows; empty/nonfinite values remain unavailable. Full data is retained in the file output. Units not stated in column headers remain unavailable.')


def _histogram(path):
    bins = [0] * 512
    count = 0
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            parts = line.split()
            if len(parts) != 2:
                raise ValueError('Siril histogram contains an invalid row.')
            code, frequency = map(int, parts)
            if code != count or not 0 <= code < 65536 or frequency < 0:
                raise ValueError('Siril histogram has missing bins or an invalid count.')
            bins[code // 128] += frequency
            count += 1
    if count != 65536:
        raise ValueError('Siril histogram is incomplete.')
    return AnalysisResult(kind='series', title=path.stem, source='Siril 1.4.4 histo',
                          unit='Siril 16-bit scaled code / pixel count', columns=['intensity', 'count'],
                          rows=[[index * 128 + 63.5, frequency] for index, frequency in enumerate(bins)],
                          values={'source_bins': 65536, 'display_bins': 512, 'aggregation': 'sum', 'source_file': path.name},
                          sample='Full selected image/channel; each displayed bin sums 128 original bins. The raw 65,536-bin file is retained.')


def _log_blocks(log, command):
    blocks = []
    for match in re.finditer(r'(?m)^log: Running command: ' + re.escape(command) + r'\r?\n', log):
        end = re.search(r'(?m)^log: Running command: ', log[match.end():])
        block = log[match.end():match.end() + end.start()] if end else log[match.end():]
        block = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', block)
        block = re.sub(r'(?m)^\d+: running command[^\n]*\n?', '', block)
        blocks.append(block.strip())
    return blocks


def _metrics(command, block):
    values, unit = {}, None
    if command == 'bg':
        for channel, code, normalised in re.findall(r'Background value \(channel: #(\d+)\): (\d+) \(([^)]+)\)', block):
            values['channel_' + channel] = _cell(normalised)
            values['channel_' + channel + '_16bit_code'] = int(code)
        unit = 'normalised intensity; separate 16-bit scaled codes'
    elif command == 'entropy':
        match = re.search(r'Entropy:\s*([+-]?[\d.eE]+)', block)
        if match:
            values['entropy'] = _cell(match[1])
        unit = 'Siril entropy, summed over channels'
    elif command == 'cdg':
        match = re.search(r'Center of gravity coordinates are \(([^,]+), ([^)]+)\)', block)
        if match:
            values = {'x': _cell(match[1]), 'y': _cell(match[2])}
        unit = 'pixel; Siril image coordinates'
    elif command == 'stat':
        for channel, rest in re.findall(r'(B&W|Red|Green|Blue) layer:\s*([^\n]+)', block):
            for name, number in re.findall(r'([\w()]+):\s*([+-]?(?:[\d.eE]+|nan|inf))', rest):
                values[channel + '.' + name] = _cell(number)
        unit = 'Siril 16-bit scaled intensity'
    elif command == 'bgnoise':
        for channel, code, normalised in re.findall(r'Background noise value \(channel: #(\d+)\): ([\d.eE+-]+) \(([^)]+)\)', block):
            values['channel_' + channel] = _cell(normalised)
            values['channel_' + channel + '_16bit_code'] = _cell(code)
        unit = 'normalised noise intensity; separate 16-bit scaled values'
    elif command == 'psf':
        for name, number, unit_value in re.findall(r'\b(x0|y0|FWHMx|FWHMy|r|B|A|m|SNR|RMSE)=([+-]?[\d.eE]+)(px|arcsec|deg|dB|\x22)?', block):
            values[name] = _cell(number)
            if unit_value:
                values[name + '_unit'] = unit_value
        angle = re.search(r'Angle:\s*([+-]?[\d.eE]+)deg', block)
        magnitude = re.search(r'm=([+-]?[\d.eE]+)±([+-]?[\d.eE]+)', block)
        reference = re.search(r'Magnitude \(([^)]+)\)', block)
        if angle:
            values['angle_degrees'] = _cell(angle[1])
        if magnitude:
            values['magnitude_uncertainty'] = _cell(magnitude[2])
        if reference:
            values['magnitude_reference'] = reference[1]
        if 'FWHMx' not in values or 'FWHMy' not in values:
            return AnalysisResult(kind='metrics', title='PSF fit unavailable', source='Siril 1.4.4 psf',
                                  values={'available': False}, text=block[:12000], sample='No PSF fit was reported for the selected star rectangle; no missing measurement is replaced with zero.')
        unit = 'Centroid px; FWHM units per value; angle deg; magnitude mag; SNR dB; intensity/RMSE in Siril native units'
    elif command == 'getref':
        match = re.search(r'Image (\d+)(?::\s*\x27([^\x27]+)\x27)?', block)
        if match:
            values = {'zero_based_reference_index': int(match[1]), 'filename': match[2]}
        unit = 'zero-based sequence index'
    if command in {'bg', 'entropy', 'cdg', 'stat', 'bgnoise', 'getref', 'psf'}:
        if not values:
            raise ValueError('Siril did not report a complete ' + command + ' result.')
        return AnalysisResult(kind='metrics', title=command, source='Siril 1.4.4 ' + command, unit=unit,
                              values=values, text=block[:12000], sample='Actual selected image/sequence; unavailable numeric values remain null.')
    if not block:
        raise ValueError('Siril did not report the requested analysis result: ' + command)
    return AnalysisResult(kind='text', title=command, source='Siril 1.4.4 ' + command, text=block[:12000],
                          values={'log_characters': len(block), 'display_characters': min(len(block), 12000), 'truncated': len(block) > 12000},
                          sample='Command output excerpt, at most 12,000 characters. The complete log is retained in the file output and invocation log.')


def _sequence_descriptor(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    for line in lines:
        match = re.match(r"S '([^']+)' (\d+) (\d+) (\d+) (\d+) (-?\d+)", line)
        if match:
            members = [(int(item[1]), int(item[2])) for text in lines if (item := re.match(r'I (\d+) ([01])', text))]
            if len(members) != int(match[3]) or sum(selected for _, selected in members) != int(match[4]):
                raise ValueError('The sequence member list and declared counts disagree.')
            return {'name': match[1], 'start': int(match[2]), 'frames': int(match[3]), 'selected': int(match[4]),
                    'fixed': int(match[5]), 'members': members,
                    'type': next((line[1] for line in lines if re.fullmatch('T[SFA]', line)), 'R')}
    raise ValueError('Siril sequence descriptor is incomplete: ' + path.name)


def _coordinate(value, pixel=False):
    if not isinstance(value, str) or len(value.split(',')) != 2:
        return False
    parts = value.split(',')
    if pixel:
        return all(re.fullmatch(r'\d+', part) for part in parts)
    try:
        return all(math.isfinite(float(part)) for part in parts)
    except ValueError:
        return False


def parse_result(operation_id, directory, plan, log_path):
    directory = Path(directory)
    recipe = RECIPES[operation_id]
    log = Path(log_path).read_text(encoding='utf-8', errors='replace')
    layout = json.loads((directory / 'layout.json').read_text(encoding='utf-8'))
    values = json.loads((directory / 'parameters.json').read_text(encoding='utf-8'))
    if re.search(r'(?im)^(?:log: )?(?:Script execution failed|Sequence processing failed|Error in line\s+\d+)', log):
        raise ValueError(parse_failure(log_path))
    for output in plan.outputs.values():
        descriptors = [path for pattern in output.supporting_patterns if pattern.pattern.endswith('*.seq')
                       for path in directory.glob(pattern.pattern)]
        if len(descriptors) > 1:
            raise ValueError('An output port must identify one fixed sequence, not several unrelated descriptors.')
        for descriptor in descriptors:
            sequence = _sequence_descriptor(descriptor)
            base = inside(directory, descriptor.parent / sequence['name'])
            if sequence['type'] == 'R':
                for index, selected in sequence['members']:
                    if selected and not any(Path(str(base) + format(index, '0' + str(sequence['fixed']) + 'd') + suffix).is_file()
                                            for suffix in ['.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz']):
                        raise ValueError('A selected sequence output frame is missing.')
            for pattern in output.patterns:
                if pattern.format in {'fits', 'video'}:
                    pattern.frame_count = None if sequence['type'] == 'A' else 1 if sequence['type'] == 'R' else sequence['frames']
    if recipe['mode'] == 'live_stack' and re.search(r'(Stacking failed|Failed to open|Error:)', log, re.IGNORECASE):
        raise ValueError('Live stacking reported a failed frame; the partial result is not a complete output.')
    if recipe['mode'] == 'live_stack' and layout['expected_live_frames'] > 1:
        counts = re.findall(r'Stacked image (\d+)', log)
        if not counts or int(counts[-1]) != layout['expected_live_frames']:
            raise ValueError('Live stacking did not report completion of all fixed input frames.')
    for sequence in layout['sequences']:
        folder = directory / sequence['folder']
        output = folder / (sequence['output_base'] + '.seq')
        if not output.is_file():
            raise ValueError('Siril did not produce the output sequence descriptor.')
        result = _sequence_descriptor(output)
        if 'expected_frames' in sequence and result['frames'] != sequence['expected_frames']:
            raise ValueError('The conversion output omitted some fixed input files.')
        if 'input_base' in sequence and sequence['input_base'] != sequence['output_base']:
            source = _sequence_descriptor(folder / (sequence['input_base'] + '.seq'))
            filtering = operation_id == 'seqapplyreg' and any(value for name, value in values.items() if name.startswith('use_filter_') or name == 'filter_included')
            if result['frames'] not in {source['frames'], source['selected']} and not (filtering and 0 < result['frames'] <= source['frames']):
                raise ValueError('The sequence output does not cover the requested members.')
    if recipe['mode'] not in {'analysis', 'sequence_analysis', 'metadata', 'python_script'}:
        return
    folders = [directory / member for member in layout['members']]
    if recipe['mode'] == 'sequence_analysis':
        folders = [directory / 'sequence']
    if not folders:
        folders = [directory]
    blocks = _log_blocks(log, operation_id)
    for index, folder in enumerate(folders):
        raw = []
        if operation_id == 'histo':
            files = sorted(folder.glob('histo_*.dat'))
            if len(files) != 1:
                raise ValueError('The requested histogram channel was not produced.')
            raw.append(_histogram(files[0]))
        elif operation_id == 'jsonmetadata':
            value = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
            raw.append(AnalysisResult(kind='json', title='FITS metadata', source='Siril 1.4.4 jsonmetadata', values=value))
        else:
            declared_files = {path for pattern in plan.outputs['files'].patterns
                              for path in directory.glob(pattern.pattern) if path.parent == folder}
            for file in sorted(declared_files):
                if file.suffix.lower() in {'.csv', '.lst', '.dat'} and file.is_file():
                    raw.append(_table(file, operation_id))
            if not raw:
                block = blocks[index] if index < len(blocks) else blocks[-1] if blocks else ''
                raw.append(_metrics(operation_id, block))
        if recipe['mode'] == 'analysis':
            for value in raw:
                value.member_index = index
        (folder / 'analysis.json').write_text(json.dumps([value.model_dump(mode='json') for value in raw],
                                                       ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    outputs = plan.outputs['files']
    if not any(file.path == Path(log_path) for file in outputs.files):
        outputs.files.append(BundleFile(path=Path(log_path), format='other', allow_empty=True))


def parse_progress(text):
    result = BundleProgress()
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text).replace('\r', '\n')
    for line in text.splitlines():
        command = re.match(r'log: Running command: (\S+)', line)
        progress = re.match(r'progress:\s*(?:(.*),\s*)?([\d.]+)%\s*$', line)
        if command:
            result = BundleProgress(phase=command[1])
        elif progress:
            value = float(progress[2]) / 100
            if not 0 <= value <= 1:
                raise ValueError('Siril reported an invalid progress value.')
            result = BundleProgress(phase=progress[1] or result.phase, progress=value)
    return result


def parse_failure(log_path):
    lines = Path(log_path).read_text(encoding='utf-8', errors='replace').splitlines()
    errors = [re.sub(r'<[^>]+>', '', line.removeprefix('log: ')) for line in lines
              if re.search(r'error|failed|cannot|could not|must be|not available|not found|missing', line, re.IGNORECASE)]
    return '\n'.join(errors[-6:])[-2400:] if errors else '\n'.join(lines[-8:])[-2400:] or 'Siril exited without an error message.'
