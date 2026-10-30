"""Explicit command recipes for Siril 1.4.4, not inferred from its usage strings."""

RECIPES = {}


def parameter(name, kind, default, *, token=None, minimum=None, maximum=None, choices=None, enabled=None):
    schema = dict(name=name, kind=kind, default=default, advanced=enabled is not None, nullable=False)
    if minimum is not None:
        schema['minimum'] = minimum
    if maximum is not None:
        schema['maximum'] = maximum
    if choices is not None:
        schema['choices'] = choices
    value = dict(schema=schema, token=token, enabled=enabled)
    if enabled:
        switch = dict(schema=dict(name=enabled, kind='boolean', default=False, advanced=True, nullable=False), control=True)
        return [switch, value]
    return [value]


def number(name, default, *, token=None, minimum=None, maximum=None, optional=False, integer=False):
    return parameter(name, 'int' if integer else 'float', default, token=token,
                     minimum=minimum, maximum=maximum, enabled='use_' + name if optional else None)


def text(name, default='', *, token=None, optional=False):
    return parameter(name, 'string', default, token=token, enabled='use_' + name if optional else None)


def choice(name, values, default=None, *, token=None, optional=False):
    return parameter(name, 'choice', values[0] if default is None else default, token=token,
                     choices=values, enabled='use_' + name if optional else None)


def flag(name, token=None):
    return parameter(name, 'boolean', False, token=token or '-' + name)


def port(name='image', *, required=True, one=False, file=False, video=False, multiple=False):
    return dict(name=name, type='APF_FILE' if file else 'APF_SCIENCE',
                formats=['other', 'fits', 'image'] if file else ['fits', 'xisf', 'image', 'raw'] + (['video'] if video else []),
                cardinality='one' if one else 'many', required=required, supports_hdu=False, supports_slice=False,
                multiple_connections=multiple)


def add(command, mode='image', *parameters, inputs=None, outputs=None, display='auto', live=False, **options):
    if command in RECIPES:
        raise ValueError('Duplicate command recipe: ' + command)
    RECIPES[command] = dict(command=command, mode=mode, parameters=[item for group in parameters for item in group],
                            inputs=[port()] if inputs is None else inputs, outputs=outputs,
                            display=display, live=live, **options)


CLIP = ['rgbblend', 'clip', 'rescale', 'globalrescale']
CHANNELS = ['RGB', 'R', 'G', 'B', 'RG', 'RB', 'GB']
INTERPOLATION = ['lanczos4', 'nearest', 'cubic', 'linear', 'area']

add('autostretch', 'image', flag('linked'), number('shadowsclip', -2.8), number('targetbg', 0.25, minimum=0, maximum=1), display='direct', live=True)
add('asinh', 'image', flag('human'), number('stretch', 100), number('offset', 0, minimum=0, maximum=1, optional=True),
    choice('clipmode', CLIP, token='-clipmode='), display='direct', live=True)
add('autoghs', 'image', flag('linked'), number('shadowsclip', -2.8), number('stretchamount', 2),
    number('b', 13, token='-b='), number('hp', 0.7, token='-hp='), number('lp', 0, token='-lp='),
    choice('clipmode', CLIP, token='-clipmode='), display='direct', live=True)
for command in ['ght', 'invght', 'modasinh', 'invmodasinh', 'linstretch']:
    parameters = [number('black_point', 0, minimum=0, maximum=1, token='-BP=')] if command == 'linstretch' else [
        number('stretch', 1, minimum=0, maximum=10, token='-D=')]
    if command in {'ght', 'invght'}:
        parameters.append(number('local_intensity', 0, minimum=0, maximum=15, token='-B='))
    if command != 'linstretch':
        parameters += [number('low_protection', 0, minimum=0, maximum=1, token='-LP='),
                       number('symmetry_point', 0, minimum=0, maximum=1, token='-SP='),
                       number('high_protection', 1, minimum=0, maximum=1, token='-HP=')]
    parameters += [choice('clipmode', CLIP, token='-clipmode='), choice('channels', CHANNELS, token='channels')]
    parameters.append(flag('saturation', '-sat') if command == 'linstretch' else
                      choice('colour_model', ['independent', 'human', 'even', 'sat'], token='colour_model'))
    add(command, 'image', *parameters, display='direct', live=True)
for command in ['mtf', 'invmtf']:
    add(command, 'image', number('low', 0, minimum=0, maximum=1), number('mid', 0.5, minimum=0, maximum=1),
        number('high', 1, minimum=0, maximum=1), choice('channels', CHANNELS, token='channels'), display='direct', live=True)

for command in ['fix_xtrans', 'grey_flat', 'mirrory', 'rotatePi', 'neg', 'log', 'icc_remove', 'unclipstars']:
    add(command)
add('binxy', 'image', number('coefficient', 2, minimum=1, integer=True), flag('sum'))
add('clahe', 'image', number('cliplimit', 2), number('tile_size', 8, integer=True))
add('fixbanding', 'image', number('amount', 1), number('sigma', 1), flag('vertical'))
add('fmedian', 'image', number('kernel_size', 3, minimum=1, integer=True), number('modulation', 1))
add('fmul', 'image', number('scalar', 1))
add('gauss', 'image', number('sigma', 1))
add('mirrorx', 'image', flag('bottomup'))
add('nozero', 'image', number('level', 1))
add('offset', 'image', number('value', 0))
for command in ['threshlo', 'threshhi']:
    add(command, 'image', number('level', 0 if command == 'threshlo' else 65535))
add('thresh', 'image', number('low', 0), number('high', 65535))
add('unsharp', 'image', number('sigma', 1), number('multiplier', 1))
add('rgradient', 'image', number('centre_x', 0), number('centre_y', 0), number('radial_step', 1), number('angular_step', 1))
add('rmgreen', 'image', flag('no_preserve', '-nopreserve'), number('method', 0, minimum=0, maximum=3, integer=True),
    number('amount', 1, minimum=0, maximum=1))
add('satu', 'image', number('amount', 0.2), number('background_factor', 1), number('hue_range', 6, minimum=0, maximum=6, integer=True))
add('unpurple', 'image', flag('starmask'), number('blue', 0, token='-blue=', optional=True),
    number('threshold', 0, token='-thresh=', optional=True))
add('denoise', 'image', flag('no_cosmetic', '-nocosmetic'), number('modulation', 1, token='-mod='),
    choice('method', ['default', 'vst', 'da3d', 'sos'], token='denoise_method'),
    number('sos_iterations', 1, minimum=1, integer=True, token='sos_iterations'),
    number('rho', 0, token='-rho=', optional=True), flag('independent', '-indep'))
add('epf', 'image', flag('guided'), number('diameter', 0, token='-d=', optional=True, integer=True),
    number('intensity_sigma', 0, token='-si=', optional=True), number('spatial_sigma', 0, token='-ss=', optional=True),
    number('modulation', 0, token='-mod=', optional=True),
    inputs=[port(), port('guide', one=True, required=False)])
for command in ['find_cosme', 'find_cosme_cfa']:
    add(command, 'image', number('cold_sigma', 3), number('hot_sigma', 3))
for command in ['fill', 'ffill']:
    add(command, 'image', number('value', 0), parameter('use_rectangle', 'boolean', False, token='rectangle'),
        number('x', 0, minimum=0, integer=True, token='rect_x'), number('y', 0, minimum=0, integer=True, token='rect_y'),
        number('width', 1, minimum=1, integer=True, token='rect_width'), number('height', 1, minimum=1, integer=True, token='rect_height'))
add('crop', 'image', parameter('use_rectangle', 'boolean', True, token='rectangle'),
    number('x', 0, minimum=0, integer=True, token='rect_x'), number('y', 0, minimum=0, integer=True, token='rect_y'),
    number('width', 1, minimum=1, integer=True, token='rect_width'), number('height', 1, minimum=1, integer=True, token='rect_height'))
add('resample', 'image', choice('size_mode', ['factor', 'width', 'height', 'maxdim'], token='size_mode'),
    number('size', 1, token='size_value'), choice('interpolation', INTERPOLATION, token='-interp='), flag('no_clamp', '-noclamp'))
add('rotate', 'image', number('degrees', 0), flag('no_crop', '-nocrop'), choice('interpolation', INTERPOLATION, token='-interp='),
    flag('no_clamp', '-noclamp'))

MATRIX = [number('m' + str(i) + str(j), 1 if i == j else 0) for i in range(3) for j in range(3)]
add('ccm', 'image', *MATRIX, number('gamma', 1, minimum=0, maximum=10))
for command in ['iadd', 'idiv', 'imul', 'isub']:
    add(command, 'image_operand', inputs=[port(), port('operand', one=True)])
add('fdiv', 'image_operand', number('scalar', 1), inputs=[port(), port('operand', one=True)])
add('linear_match', 'image_operand', number('low', 0), number('high', 0.9), inputs=[port(), port('reference', one=True)])
for command in ['cosme', 'cosme_cfa']:
    add(command, 'image_operand', inputs=[port(), port('bad_pixels', one=True, file=True)])
for command in ['icc_assign', 'icc_convert_to']:
    params = [text('profile', 'sRGB', token='profile')]
    if command == 'icc_convert_to':
        params.append(choice('intent', ['perceptual', 'relative', 'saturation', 'absolute']))
    add(command, 'image', *params, inputs=[port(), port('icc_profile', one=True, file=True, required=False)])

add('subsky', 'image', choice('model', ['polynomial', 'rbf'], token='background_model'),
    number('degree', 1, minimum=1, maximum=4, integer=True, token='background_degree'), flag('dither'),
    number('samples', 20, minimum=2, integer=True, token='-samples='), number('tolerance', 1, minimum=0, token='-tolerance='),
    number('smooth', 0.5, minimum=0, maximum=1, token='-smooth='),
    limitations=['-existing needs GUI background samples; this stateless operation creates samples from the fixed input.'])

for command in ['bg', 'bgnoise', 'entropy', 'cdg', 'dumpheader']:
    add(command, 'analysis')
add('stat', 'analysis', flag('cfa'), choice('statistics', ['basic', 'main'], token='stat_mode'))
add('histo', 'analysis', number('channel', 0, minimum=0, maximum=2, integer=True))
add('jsonmetadata', 'analysis', flag('statistics_from_loaded', '-stats_from_loaded'), flag('no_statistics', '-nostats'),
    inputs=[dict(port(), formats=['fits'])])
add('findstar', 'analysis', number('layer', 0, minimum=0, maximum=2, integer=True, token='-layer=', optional=True),
    number('maximum_stars', 0, minimum=0, integer=True, token='-maxstars=', optional=True))
add('find_hot', 'analysis', number('cold_sigma', 3), number('hot_sigma', 3))
add('psf', 'analysis', number('channel', 0, minimum=0, maximum=2, integer=True), text('selection', '[0,0,32,32]', token='selection'))
add('profile', 'analysis', text('from_pixel', '0,0', token='-from='), text('to_pixel', '1,1', token='-to='), flag('tri'), flag('cfa'),
    flag('arcsec'), choice('layer', ['red', 'green', 'blue', 'lum', 'col'], token='-layer=', optional=True), number('width', 1, token='-width=', optional=True),
    number('spacing', 1, token='-spacing=', optional=True), text('title', token='-title=', optional=True))

add('split', 'split', choice('colour_space', ['rgb', 'hsl', 'hsv', 'lab'], token='split_mode'))
add('split_cfa', 'split_cfa')
add('extract', 'extract', number('layers', 3, minimum=1, integer=True))
add('extract_Green', 'extract_green')
add('extract_Ha', 'extract_ha', flag('upscale'))
add('extract_HaOIII', 'extract_hao', choice('resample', ['ha', 'oiii'], token='-resample=', optional=True))
add('fftd', 'fft_direct')
add('ffti', 'fft_inverse', inputs=[port('modulus', one=True), port('phase', one=True)])
add('rgbcomp', 'rgb_composition', choice('mode', ['rgb', 'lrgb', 'l_rgb'], token='composition_mode'), flag('no_sum', '-nosum'),
    inputs=[port('red', one=True, required=False), port('green', one=True, required=False),
            port('blue', one=True, required=False), port('luminance', one=True, required=False), port('rgb', one=True, required=False)])
add('merge_cfa', 'merge_cfa', choice('bayer_pattern', ['RGGB', 'BGGR', 'GRBG', 'GBRG']),
    inputs=[port('cfa0', one=True), port('cfa1', one=True), port('cfa2', one=True), port('cfa3', one=True)])

for command in ['save', 'savebmp', 'savejpg', 'savejxl', 'savepng', 'savepnm', 'savetif', 'savetif32', 'savetif8']:
    params = []
    if command == 'save':
        params += [flag('checksum', '-chksum')]
    elif command == 'savejpg':
        params += [number('quality', 95, minimum=0, maximum=100, integer=True)]
    elif command == 'savejxl':
        params += [number('effort', 7, minimum=1, maximum=9, integer=True, token='-effort='),
                   number('quality', 100, minimum=0, maximum=100, token='-quality='), flag('eight_bit', '-8bit')]
    elif command.startswith('savetif'):
        params += [flag('astro'), flag('deflate')]
    add(command, 'export', *params, display='direct')

for command in ['update_key', 'sequpdate_key']:
    add(command, 'update_header' if command == 'update_key' else 'sequence_header_update',
        choice('action', ['set', 'delete', 'rename', 'comment'], token='header_action'), text('key', token='header_key'),
        text('value', token='header_value'), text('comment', token='header_comment'))

add('wavelet_reconstruction', 'wavelet', number('layers', 3, minimum=1, maximum=6, integer=True),
    choice('transform', [1, 2], 2), text('coefficients', '[1,1,1,1]', token='wavelet_coefficients'),
    covers=['wavelet', 'wrecons'])

for command in ['rl', 'sb', 'wiener', 'seqrl', 'seqsb', 'seqwiener']:
    params = [number('regularisation', 0, minimum=0, token='-alpha=', optional=True)]
    if command not in ['wiener', 'seqwiener']:
        params += [number('iterations', 1, minimum=1, integer=True, token='-iters=', optional=True)]
    if command in ['rl', 'seqrl']:
        params += [number('stop', 0, token='-stop=', optional=True), number('gradient_step', 0, token='-gdstep=', optional=True),
                   flag('total_variation', '-tv'), flag('frequency_filter', '-fh'), flag('multiplicative', '-mul')]
    add(command, 'sequence_transform' if command.startswith('seq') else 'image', *params,
        inputs=[port(video=command.startswith('seq')), port('psf', one=True)], output_prefix='result_')

add('makepsf', 'makepsf', choice('method', ['manual', 'blind', 'stars'], token='psf_method'),
    choice('function', ['gaussian', 'moffat', 'disc', 'airy'], token='psf_function'),
    flag('l0'), flag('si'), flag('multiscale'), flag('symmetric', '-sym'),
    *[number(name, 0, token='-' + option + '=', optional=True, integer=name == 'kernel_size') for name, option in [
        ('lambda', 'lambda'), ('compensation', 'comp'), ('kernel_size', 'ks'), ('fwhm', 'fwhm'), ('angle', 'angle'),
        ('ratio', 'ratio'), ('beta', 'beta'), ('diameter', 'dia'), ('focal_length', 'fl'), ('wavelength', 'wl'),
        ('pixel_size', 'pixelsize'), ('obstruction', 'obstruct')]],
    inputs=[port(required=False)], limitations=['load/save/clear are mapped to fixed PSF input/output and a fresh per-call process.'])

for command in ['starnet', 'seqstarnet']:
    add(command, 'starnet' if command == 'starnet' else 'sequence_starnet', flag('stretch'), flag('upscale'),
        number('stride', 0, token='-stride=', optional=True, integer=True), flag('no_starmask', '-nostarmask'),
        dependencies=['A compatible StarNet executable and weights configured in the isolated Siril settings.'])
add('synthstar', 'image', dependencies=['Siril star measurements are prepared with findstar on the fixed image before synthstar.'])

add('mirrorx_single', 'file_transform', inputs=[dict(port(), formats=['fits'])])

for command, original in [
    ('seqccm', 'ccm'), ('seqcrop', 'crop'), ('seqextract_Green', 'extract_Green'), ('seqextract_Ha', 'extract_Ha'),
    ('seqextract_HaOIII', 'extract_HaOIII'), ('seqfind_cosme', 'find_cosme'), ('seqfind_cosme_cfa', 'find_cosme_cfa'),
    ('seqfixbanding', 'fixbanding'), ('seqght', 'ght'), ('seqinvght', 'invght'), ('seqinvmodasinh', 'invmodasinh'),
    ('seqlinstretch', 'linstretch'), ('seqmodasinh', 'modasinh'), ('seqmtf', 'mtf')]:
    source = RECIPES[original]
    RECIPES[command] = dict(source, command=command, mode='sequence_transform', live=False,
                             output_prefix='result_', inputs=[port(video=True)])
    if command == 'seqccm':
        RECIPES[command]['corrections'] = ['The shipped help omits the matrix arguments; command.c requires nine coefficients and optional gamma.']
    if command == 'seqcrop':
        RECIPES[command]['parameters'] = [item for group in [number('x', 0, minimum=0, integer=True), number('y', 0, minimum=0, integer=True),
            number('width', 1, minimum=1, integer=True), number('height', 1, minimum=1, integer=True)] for item in group]
for command in ['seqcosme', 'seqcosme_cfa']:
    add(command, 'sequence_transform', inputs=[port(video=True), port('bad_pixels', one=True, file=True)], output_prefix='result_')
add('seqsplit_cfa', 'sequence_split_cfa', inputs=[port(video=True)])
add('seqmerge_cfa', 'sequence_merge_cfa', choice('bayer_pattern', ['RGGB', 'BGGR', 'GRBG', 'GBRG']),
    inputs=[port('cfa0', video=True), port('cfa1', video=True), port('cfa2', video=True), port('cfa3', video=True)])
add('seqresample', 'sequence_transform', choice('size_mode', ['scale', 'width', 'height', 'maxdim'], token='size_mode'),
    number('size', 1, token='size_value'), choice('interpolation', INTERPOLATION, token='-interp='), output_prefix='result_',
    inputs=[port(video=True)])
add('seqsubsky', 'sequence_transform', choice('model', ['polynomial', 'rbf'], token='background_model'),
    number('degree', 1, minimum=1, maximum=4, integer=True, token='background_degree'), flag('no_dither', '-nodither'),
    number('samples', 20, minimum=2, integer=True, token='-samples='), number('tolerance', 1, minimum=0, token='-tolerance='),
    number('smooth', 0.5, minimum=0, maximum=1, token='-smooth='), inputs=[port(video=True)], output_prefix='result_')

for command in ['calibrate', 'calibrate_single']:
    params = [choice('bias_mode', ['none', 'image', 'expression'], token='bias_mode'), text('bias_expression', '=0', token='bias_expression'),
              choice('cosmetic', ['none', 'dark', 'bpm'], token='cosmetic_mode'),
              flag('cosmetic_sigmas', 'cosmetic_sigmas'), number('cold_sigma', 0, token='cold_sigma'), number('hot_sigma', 3, token='hot_sigma'),
              flag('cfa'), flag('debayer'), flag('fix_xtrans'), flag('equalize_cfa'),
              choice('dark_optimisation', ['none', 'optimise', 'exposure'], token='dark_optimisation')]
    if command == 'calibrate':
        params += [flag('all_frames', '-all'), flag('fits_sequence', '-fitseq')]
    add(command, 'calibration_sequence' if command == 'calibrate' else 'calibration_single', *params,
        inputs=[port(video=True) if command == 'calibrate' else dict(port(), formats=['fits']), port('bias', one=True, required=False), port('dark', one=True, required=False),
                port('flat', one=True, required=False), port('bad_pixels', one=True, file=True, required=False)])

for command in ['convert', 'convertraw', 'link']:
    parameters = [number('start_index', 1, minimum=1, integer=True, token='-start=')]
    if command == 'link':
        parameters += [flag('date')]
    else:
        parameters += [flag('debayer'), choice('sequence_format', ['images', 'fitseq', 'ser'], token='sequence_format')]
    add(command, 'conversion', *parameters, inputs=[dict(port(), formats=['raw'] if command == 'convertraw' else ['fits'] if command == 'link' else ['fits', 'xisf', 'image', 'raw'])])

FILTERS = [number('filter_' + name, 0, token='-filter-' + name + '=', optional=True)
           for name in ['fwhm', 'wfwhm', 'round', 'bkg', 'nbstars', 'quality']]
FILTERS += [choice('filter_unit', ['absolute', 'percent', 'sigma'], token='filter_unit'), flag('filter_included', '-filter-included')]
REGISTER = [number('scale', 1, token='-scale=', optional=True), number('layer', 0, integer=True, minimum=0, maximum=2, token='-layer=', optional=True),
            choice('interpolation', INTERPOLATION, token='-interp='), flag('no_clamp', '-noclamp'), flag('drizzle'),
            number('pixel_fraction', 1, token='-pixfrac=', optional=True), text('kernel', token='-kernel=', optional=True)]
add('register', 'registration', flag('two_pass', '-2pass'), flag('selected'), *REGISTER,
    text('transformation', token='-transf=', optional=True), number('minimum_pairs', 0, integer=True, token='-minpairs=', optional=True),
    number('maximum_stars', 0, integer=True, token='-maxstars=', optional=True), flag('no_star_list', '-nostarlist'),
    inputs=[port(video=True), port('flat', one=True, required=False), port('distortion', one=True, required=False, file=True)])
add('seqapplyreg', 'apply_registration', *REGISTER, text('framing', token='-framing=', optional=True), *FILTERS,
    inputs=[port(video=True), port('flat', one=True, required=False)])

STACK = [choice('method', ['mean', 'sum', 'min', 'max', 'median'], token='stack_method'),
         choice('rejection', ['none', 'percentile', 'sigma', 'mad', 'median', 'winsorized', 'linear', 'generalized'], 'winsorized', token='stack_rejection'),
         number('sigma_low', 3, token='sigma_low'), number('sigma_high', 3, token='sigma_high'),
         choice('normalisation', ['none', 'add', 'mul', 'addscale', 'mulscale'], token='stack_normalisation'),
         flag('fast_normalisation', '-fastnorm'), flag('rgb_equal'), flag('output_normalisation', '-output_norm'),
         flag('overlap_normalisation', '-overlap_norm'), choice('weight', ['none', 'noise', 'wfwhm', 'nbstars', 'nbstack'], token='stack_weight'),
         number('feather', 0, token='-feather=', optional=True), flag('maximise', '-maximize'), flag('upscale'), flag('force_32bit', '-32b'),
         choice('rejection_maps', ['none', 'combined', 'separate'], token='rejection_maps')]
add('stack', 'stack', *STACK, *FILTERS, inputs=[port(video=True)])
add('stackall', 'stack_all', *STACK, inputs=[port('sequences', video=True, multiple=True)])
add('merge', 'merge_sequences', inputs=[port('sequences', video=True, multiple=True)])

for command in ['select', 'unselect']:
    add(command, 'sequence_state', number('from_index', 1, minimum=1, integer=True), number('to_index', 1, minimum=1, integer=True), inputs=[port(video=True)])
add('setref', 'sequence_state', number('image_number', 1, minimum=1, integer=True), inputs=[port(video=True)])
add('getref', 'sequence_analysis', inputs=[port(video=True)])
add('seqclean', 'sequence_state', flag('registration', '-reg'), flag('statistics', '-stat'), flag('selection', '-sel'), inputs=[port(video=True)])
add('seqstat', 'sequence_analysis', choice('statistics', ['basic', 'main', 'full'], 'main'), flag('cfa'), inputs=[port(video=True)])
add('seqheader', 'sequence_analysis', text('keywords', '["DATE-OBS","EXPTIME"]', token='keywords'), flag('selected', '-sel'), inputs=[port(video=True)])
add('seqfindstar', 'sequence_analysis', number('layer', 0, minimum=0, maximum=2, integer=True, token='-layer=', optional=True),
    number('maximum_stars', 0, minimum=0, integer=True, token='-maxstars=', optional=True), inputs=[port(video=True)])
add('seqtilt', 'sequence_analysis', inputs=[port(video=True)])
add('seqpsf', 'sequence_analysis', number('channel', 0, minimum=0, maximum=2, integer=True),
    choice('coordinate_type', ['pixel', 'wcs'], token='coordinate_type'), text('position', '64,64', token='star_position'), flag('follow_star', '-followstar'),
    inputs=[port(video=True)])
add('light_curve', 'sequence_analysis', number('channel', 0, minimum=0, maximum=2, integer=True), flag('autoring'),
    choice('coordinate_type', ['pixel', 'wcs', 'nina'], token='coordinate_type'), text('position', '64,64', token='star_position'),
    text('reference_positions', '[]', token='reference_positions'), inputs=[port(video=True), port('nina_stars', one=True, file=True, required=False)])
add('seqprofile', 'sequence_analysis', *[ [dict(item) for item in RECIPES['profile']['parameters']] ],
    choice('x_axis', ['distance', 'wavelength', 'wavenumber'], token='profile_axis'),
    *[number(name, 0, token='-' + name + '=', optional=True) for name in ['wavenumber1', 'wavenumber2', 'wavelength1', 'wavelength2']],
    text('first_reference_pixel', '0,0', token='-wn1at=', optional=True), text('second_reference_pixel', '1,1', token='-wn2at=', optional=True),
    inputs=[port(video=True)])

SOLVER = [flag('force'), text('centre_coordinates', token='centre_coordinates', optional=True),
          number('focal_length', 0, token='-focal=', optional=True), number('pixel_size', 0, token='-pixelsize=', optional=True),
          flag('downscale'), number('order', 0, integer=True, token='-order=', optional=True), number('radius', 0, token='-radius=', optional=True),
          text('magnitude_limit', token='-limitmag=', optional=True), text('catalogue', token='-catalog=', optional=True), flag('no_crop', '-nocrop'),
          flag('local_solver', '-localasnet'), flag('blind_position', '-blindpos'), flag('blind_resolution', '-blindres')]
add('platesolve', 'image', *SOLVER, flag('no_flip', '-noflip'),
    inputs=[port(), port('distortion', one=True, required=False, file=True)], dependencies=['A catalogue service, local catalogue, or configured astrometry.net solver.'])
add('seqplatesolve', 'sequence_state', *SOLVER, flag('no_registration', '-noreg'), flag('no_cache', '-nocache'),
    inputs=[port(video=True), port('distortion', one=True, required=False, file=True)])
for command in ['pcc', 'spcc']:
    parameters = [text('magnitude_limit', token='-limitmag=', optional=True), text('background_tolerance', token='-bgtol=', optional=True)]
    if command == 'pcc':
        parameters += [text('catalogue', token='-catalog=', optional=True)]
    else:
        parameters += [text(name, token='-' + option + '=', optional=True) for name, option in [
            ('mono_sensor', 'monosensor'), ('red_filter', 'rfilter'), ('green_filter', 'gfilter'), ('blue_filter', 'bfilter'),
            ('osc_sensor', 'oscsensor'), ('osc_filter', 'oscfilter'), ('osc_low_pass', 'osclpf'), ('white_reference', 'whiteref')]]
        parameters += [flag('narrowband'), flag('atmosphere', '-atmos')]
        parameters += [number(name, 0, token='-' + option + '=', optional=True) for name, option in [
            ('red_wavelength', 'rwl'), ('green_wavelength', 'gwl'), ('blue_wavelength', 'bwl'), ('red_bandwidth', 'rbw'),
            ('green_bandwidth', 'gbw'), ('blue_bandwidth', 'bbw'), ('observatory_height', 'obsheight'), ('pressure', 'pressure'), ('sea_level_pressure', 'slp')]]
    add(command, 'image', *parameters, dependencies=['Plate-solved input and the catalogue/response data selected in the isolated settings.'])
add('spcc_list', 'metadata', choice('category', ['oscsensor', 'monosensor', 'redfilter', 'greenfilter', 'bluefilter', 'oscfilter', 'osclpf', 'whiteref']), inputs=[])
add('conesearch', 'analysis', number('magnitude_limit', 0, optional=True), text('catalogue', token='-cat=', optional=True), flag('photometry', '-phot'),
    text('observatory_code', token='-obscode=', optional=True), choice('tag', ['on', 'off'], token='-tag='),
    choice('log', ['on', 'off'], token='-log='), text('trixel', token='-trix=', optional=True))
add('catsearch', 'analysis', text('object_name'))
add('trixel', 'analysis', flag('print_id', '-p'))
add('findcompstars', 'analysis', text('star_name'), choice('search_width', ['default', 'narrow', 'wide'], token='search_width'),
    choice('catalogue', ['nomad', 'apass'], token='-catalog='), number('magnitude_difference', 3, token='-dvmag='),
    number('colour_difference', 0.5, token='-dbv='), number('magnitude_error', 0.03, token='-emag='))

add('pm', 'pixel_math', text('expression', '$0'), flag('rescale'), number('low', 0), number('high', 1), flag('no_sum', '-nosum'),
    inputs=[port('images', multiple=True)], limitations=['Filenames in expressions are replaced by explicit $0, $1, … fixed image inputs; arbitrary disk paths are rejected.'])
add('limit', 'image', choice('method', ['clip', 'posrescale', 'rescale'], token='-'))
add('live_stack', 'live_stack', flag('rotate'), flag('force_32bit', '-32bits'),
    inputs=[port(), port('dark', one=True, required=False), port('flat', one=True, required=False)],
    covers=['start_ls', 'livestack', 'stop_ls'], limitations=['A finite fixed group is consumed in order; GUI file watching is not provided by Siril headless.'])

add('capabilities', 'metadata', inputs=[])
add('help', 'metadata', text('command_name', optional=True), inputs=[])
add('get', 'metadata', choice('query', ['all', 'all_with_comments', 'variable'], token='get_query'), text('variable_name', token='get_variable'), inputs=[])
add('parse', 'analysis', text('expression'), flag('read_mode', '-r'))
add('pyscript', 'python_script', choice('script_source', ['inline', 'file'], token='script_source'),
    parameter('load_image', 'boolean', True),
    text('script', 'print("Siril Python script")'), text('arguments', '[]'),
    text('output_files', '[]'), inputs=[port(required=False), port('script_file', one=True, file=True, required=False)],
    limitations=['Runs synchronously so completion and cancellation remain observable; -async is not exposed as a fire-and-forget node. User scripts execute with local user permissions.',
                 'Input bytes are copied unchanged into the call directory. load_image loads the first staged input as the Siril image context; turn it off for non-image scientific containers. Argument placeholders {input0}, {input1}, … address the fixed staged files.'])

SESSION_COMMANDS = {
    'cd': 'Each invocation has an isolated working directory; user outputs cannot address original files.',
    'pwd': 'The isolated directory is logged at the beginning of each invocation.',
    'load': 'Every image input is loaded from its fixed reference before processing.',
    'close': 'Each member is closed before the next image and the invocation process owns no shared session.',
    'exit': 'Process completion is observed by the host; cancellation targets the invocation process tree.',
    'requires': 'Every generated script requires the pinned Siril 1.4.4 version.',
    'boxselect': 'The runtime selection parameter supplies an explicit rectangle; an omitted selection leaves the full image.',
    'set': 'The runtime settings JSON supports per-call ini content and typed Siril setting values in a private init file.',
    'set16bits': 'runtime.output_bits selects 16-bit output explicitly.',
    'set32bits': 'runtime.output_bits selects 32-bit output explicitly; this is the scientific output default.',
    'setcompress': 'runtime.compression carries enabled/type/quantisation values; zero is retained.',
    'setcpu': 'runtime.threads explicitly sets the Siril CPU count when provided.',
    'setext': 'Scientific FITS outputs use the invocation-owned .fit extension; export operations choose their declared format.',
    'setfindstar': 'runtime.findstar supplies the documented star detection controls before the operation.',
    'setmem': 'runtime.memory_ratio explicitly sets the Siril memory ratio when provided.',
    'setphot': 'runtime.photometry supplies the documented photometry controls before measurement.',
    'online': 'runtime.online explicitly enables Siril networking for this invocation.',
    'offline': 'The process starts offline unless runtime.online is explicitly true.',
}
