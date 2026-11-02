"""Small factories for typed recipe parameters and ports."""
from typing import Literal

from pydantic import JsonValue

from astrophotoflow.contracts.inputs import ScienceFormat
from astrophotoflow.contracts.software import ParameterDefinition, SoftwareInputDefinition, SoftwareOutputDefinition

from .types import Recipe, RecipeParameter


def parameter(name: str, kind: Literal['int', 'float', 'string', 'boolean', 'choice'], default: JsonValue, *, token: str | None = None, minimum: float | None = None, maximum: float | None = None, choices: list[JsonValue] | None = None, enabled: str | None = None) -> list[RecipeParameter]:
    schema = ParameterDefinition(name=name, kind=kind, default=default, advanced=enabled is not None,
                                 nullable=False, minimum=minimum, maximum=maximum, choices=choices)
    value = RecipeParameter(schema=schema, token=token, enabled=enabled)
    if enabled:
        switch = RecipeParameter(schema=ParameterDefinition(name=enabled, kind='boolean', default=False,
                                                            advanced=True, nullable=False), control=True)
        return [switch, value]
    return [value]


def number(name: str, default: float, *, token: str | None = None, minimum: float | None = None, maximum: float | None = None, optional: bool = False, integer: bool = False) -> list[RecipeParameter]:
    return parameter(name, 'int' if integer else 'float', default, token=token,
                     minimum=minimum, maximum=maximum, enabled='use_' + name if optional else None)


def text(name: str, default: str = '', *, token: str | None = None, optional: bool = False) -> list[RecipeParameter]:
    return parameter(name, 'string', default, token=token, enabled='use_' + name if optional else None)


def choice(name: str, values: list[JsonValue], default: JsonValue = None, *, token: str | None = None, optional: bool = False) -> list[RecipeParameter]:
    return parameter(name, 'choice', values[0] if default is None else default, token=token,
                     choices=values, enabled='use_' + name if optional else None)


def flag(name: str, token: str | None = None) -> list[RecipeParameter]:
    return parameter(name, 'boolean', False, token=token or '-' + name)


def port(name: str = 'image', *, required: bool = True, one: bool = False, file: bool = False, video: bool = False, multiple: bool = False, formats: list[ScienceFormat] | None = None) -> SoftwareInputDefinition:
    return SoftwareInputDefinition(name=name, type='APF_FILE' if file else 'APF_SCIENCE',
        formats=formats if formats is not None else ['other', 'fits', 'image'] if file else ['fits', 'xisf', 'image', 'raw'] + (['video'] if video else []),
        cardinality='one' if one else 'many', required=required, supports_hdu=False, supports_slice=False,
        multiple_connections=multiple)


def output(name: str, type: str = 'APF_SCIENCE', formats: list[ScienceFormat] | None = None, required: bool = True) -> SoftwareOutputDefinition:
    return SoftwareOutputDefinition(name=name, type=type, formats=formats or ['fits'], cardinality='many', required=required)


def output_definitions(recipe: Recipe) -> list[SoftwareOutputDefinition]:
    mode, name = recipe.mode, recipe.command
    if mode in {'analysis', 'metadata'}:
        result = [output('analysis', 'APF_ANALYSIS', ['other'])]
        return result + [output('files', 'APF_FILE', ['other', 'image'], False)]
    if mode == 'sequence_analysis':
        return [output('image', formats=['fits', 'video']), output('analysis', 'APF_ANALYSIS', ['other']), output('files', 'APF_FILE', ['other', 'image'], False)]
    if mode == 'split':
        return [output('channel_' + str(index)) for index in range(1, 4)]
    if mode in {'split_cfa', 'sequence_split_cfa'}:
        return [output('cfa' + str(index), formats=['fits', 'video'] if mode.startswith('sequence') else ['fits']) for index in range(4)]
    if mode == 'extract_hao' or name == 'seqextract_HaOIII':
        return [output('ha', formats=['fits', 'video'] if name.startswith('seq') else ['fits']),
                output('oiii', formats=['fits', 'video'] if name.startswith('seq') else ['fits'])]
    if mode == 'fft_direct':
        return [output('modulus'), output('phase')]
    if mode == 'extract':
        return [output('layers')]
    if mode == 'makepsf':
        return [output('psf')]
    if mode in {'starnet', 'sequence_starnet'}:
        return [output('image', formats=['fits', 'video'] if mode.startswith('sequence') else ['fits']),
                output('stars', formats=['fits', 'video'] if mode.startswith('sequence') else ['fits'], required=False)]
    if mode in {'stack', 'stack_all'}:
        return [output('image'), output('rejection_maps', required=False)]
    if mode == 'python_script':
        formats = ['fits', 'xisf', 'image', 'raw', 'video', 'numpy', 'other']
        return [output('image', formats=formats, required=False), output('files', 'APF_FILE', formats, False), output('analysis', 'APF_ANALYSIS', ['other'])]
    if mode == 'export' and name != 'save':
        return [output('file', 'APF_FILE', ['image'])]
    return [output('image', formats=['fits', 'video'] if mode.startswith('sequence') or mode in {'conversion', 'registration', 'apply_registration', 'merge_sequences', 'calibration_sequence'} else ['fits'])]


def finalize_ports(recipe: Recipe) -> None:
    """Resolve mode-dependent science layout once for all consumers."""
    sequence = recipe.mode.startswith('sequence') or recipe.mode in {
        'calibration_sequence', 'registration', 'apply_registration', 'stack',
        'stack_all', 'merge_sequences', 'python_script'}
    inputs = []
    for item in recipe.inputs:
        kind = ('file' if item.type == 'APF_FILE' or recipe.mode == 'python_script'
                else 'sequence' if sequence and item.cardinality == 'many' else 'image')
        update = {'data_kind': kind}
        if kind != 'file' and 'fits' in item.formats:
            update['colour_layout'] = 'planar'
        inputs.append(SoftwareInputDefinition.model_validate({**item.model_dump(), **update}))
    recipe.inputs = inputs
    recipe.outputs = [SoftwareOutputDefinition.model_validate({**item.model_dump(), 'colour_layout': 'planar'})
                      if recipe.mode != 'python_script' and 'fits' in item.formats else item
                      for item in output_definitions(recipe)]
