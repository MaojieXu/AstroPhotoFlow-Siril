"""Concrete planning and result facts shared by Siril adapter stages."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import JsonValue, TypeAdapter

from astrophotoflow.contracts.bundles import BundleInputMetadata, ProcessOutput

from .recipes import Recipe


@dataclass(frozen=True, slots=True)
class RuntimeOptions:
    threads: int | None
    compression_enabled: bool
    selection_set: bool
    selection: tuple[int, int, int, int] | None


@dataclass(frozen=True, slots=True)
class SequenceDescriptor:
    name: str
    start: int
    frames: int
    selected: int
    fixed: int
    members: list[tuple[int, int]]
    type: Literal['R', 'S', 'F', 'A']


@dataclass(slots=True)
class SequenceLayout:
    folder: str
    output_base: str
    input_base: str | None = None
    expected_frames: int | None = None


@dataclass(slots=True)
class SingleSequenceLayout:
    folder: str
    base: str
    member: int
    selected: int
    fixed: int


@dataclass(slots=True)
class ResultLayout:
    operation_id: str
    members: list[str] = field(default_factory=list)
    sequences: list[SequenceLayout] = field(default_factory=list)
    single_sequences: list[SingleSequenceLayout] = field(default_factory=list)
    expected_live_frames: int | None = None


RESULT_LAYOUT = TypeAdapter(ResultLayout)


@dataclass(slots=True)
class BuildContext:
    recipe: Recipe
    sources: dict[str, list[Path]]
    values: dict[str, JsonValue]
    directory: Path
    commands: list[str]
    outputs: dict[str, ProcessOutput]
    runtime: RuntimeOptions
    supporting_sources: dict[str, list[Path]]
    source_groups: dict[str, list[list[Path]]]
    supporting_groups: dict[str, list[list[Path]]]
    source_metadata: dict[str, list[BundleInputMetadata]]
    layout: ResultLayout
    preview: bool
    prepare_sample: bool
