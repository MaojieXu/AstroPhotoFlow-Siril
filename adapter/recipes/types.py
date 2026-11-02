"""Typed command definitions shared by generation and execution."""
from dataclasses import dataclass, field
from typing import Literal

from astrophotoflow.contracts.software import ParameterDefinition, SoftwareInputDefinition, SoftwareOutputDefinition

RecipeMode = Literal['analysis', 'apply_registration', 'calibration_sequence', 'calibration_single', 'conversion', 'export', 'extract', 'extract_green', 'extract_ha', 'extract_hao', 'fft_direct', 'fft_inverse', 'file_transform', 'image', 'image_operand', 'live_stack', 'makepsf', 'merge_cfa', 'merge_sequences', 'metadata', 'pixel_math', 'python_script', 'registration', 'rgb_composition', 'sequence_analysis', 'sequence_header_update', 'sequence_merge_cfa', 'sequence_split_cfa', 'sequence_starnet', 'sequence_state', 'sequence_transform', 'split', 'split_cfa', 'stack', 'stack_all', 'starnet', 'update_header', 'wavelet']

@dataclass(slots=True)
class RecipeParameter:
    schema: ParameterDefinition
    token: str | None = None
    enabled: str | None = None
    control: bool = False

@dataclass(slots=True)
class Recipe:
    command: str
    mode: RecipeMode
    parameters: list[RecipeParameter]
    inputs: list[SoftwareInputDefinition]
    display: Literal['auto', 'direct'] = 'auto'
    live: bool = False
    covers: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    output_prefix: str | None = None
    outputs: list[SoftwareOutputDefinition] = field(default_factory=list)
