from __future__ import annotations

import json
import math
import re
from pathlib import Path

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
    if type(result) is not expected:
        raise ValueError(name + ' has the wrong JSON type.')
    return result


def encode_parameters(recipe, values, *, skip=()):
    result = []
    for item in recipe.parameters:
        if item.control:
            continue
        schema = item.schema
        name, option = schema.name, item.token
        if name in skip or option in SPECIAL_TOKENS or (item.enabled and not values[item.enabled]):
            continue
        value = values[name]
        if schema.kind == 'boolean':
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
    if 'model' in values and recipe.command in {'subsky', 'seqsubsky'}:
        result.insert(0, '-rbf' if values['model'] == 'rbf' else str(values['degree']))
    if 'denoise_method' in {item.token for item in recipe.parameters}:
        if values['method'] in {'vst', 'da3d'}:
            result.append('-' + values['method'])
        elif values['method'] == 'sos':
            result.append('-sos=' + str(values['sos_iterations']))
    if 'statistics' in values and recipe.command == 'stat' and values['statistics'] == 'main':
        if values['cfa']:
            raise ValueError('Siril 1.4.4 cannot combine CFA statistics with main; choose one mode.')
        result.append('main')
    if recipe.command in {'platesolve', 'seqplatesolve'} and values['use_centre_coordinates']:
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


def header_arguments(values):
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


def calibration_arguments(values, sources):
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


def image_arguments(recipe, values, sources):
    command, arguments = recipe.command, encode_parameters(recipe, values)
    if recipe.mode == 'image_operand':
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
    if (all(name in values for name in ['low_protection', 'symmetry_point', 'high_protection'])
            and not 0 <= values['low_protection'] <= values['symmetry_point'] <= values['high_protection'] <= 1):
        raise ValueError('GHS requires LP <= SP <= HP.')
    return arguments


def analysis_command(command, recipe, values, folder, source):
    args = encode_parameters(recipe, values)
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


def stack_arguments(recipe, values):
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
    result.extend(encode_parameters(recipe, values))
    return result


def sequence_analysis_commands(command, recipe, values, sources, base, folder):
    args = encode_parameters(recipe, values)
    if command == 'seqstat':
        args = [quoted(folder / 'statistics.csv'), values['statistics']] + (['-cfa'] if values['cfa'] else [])
    elif command == 'seqheader':
        keywords = json_value(values['keywords'], list, 'keywords')
        if not keywords or any(not isinstance(key, str) or not re.fullmatch('[A-Za-z0-9_-]{1,8}', key) for key in keywords):
            raise ValueError('seqheader requires a nonempty JSON array of FITS keywords.')
        args = [*keywords, *args, token('-out=' + (folder / 'headers.csv').as_posix())]
    elif command in {'seqpsf', 'light_curve'}:
        position = values['position']
        if values['coordinate_type'] != 'nina' and not valid_coordinate(position, pixel=values['coordinate_type'] == 'pixel'):
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
                if not valid_coordinate(position, pixel=values['coordinate_type'] == 'pixel'):
                    raise ValueError('Reference positions must be comma-separated numeric pairs.')
                args.append(token(('-refat=' if values['coordinate_type'] == 'pixel' else '-refwcs=') + position))
    elif command == 'seqprofile':
        args.append('-savedat')
        if values['x_axis'] != 'distance':
            args.append('-xaxis=' + values['x_axis'])
    return command + ' ' + token(base) + (' ' + ' '.join(args) if args else '')


def valid_coordinate(value, pixel=False):
    if not isinstance(value, str) or len(value.split(',')) != 2:
        return False
    parts = value.split(',')
    if pixel:
        return all(re.fullmatch(r'\d+', part) for part in parts)
    try:
        return all(math.isfinite(float(part)) for part in parts)
    except ValueError:
        return False
