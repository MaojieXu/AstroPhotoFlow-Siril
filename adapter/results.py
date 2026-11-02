from __future__ import annotations

import json
import re
from pathlib import Path

from astrophotoflow.contracts.bundles import (
    AnalysisResult,
    BundleFile,
    NamedProcessPlan,
)

from .analysis import log_blocks, parse_histogram, parse_metrics, parse_table
from .logs import parse_failure
from .paths import inside
from .recipes import RECIPES
from .sequences import read_sequence_descriptor, write_single_sequence
from .types import RESULT_LAYOUT


def parse_result(operation_id: str, directory: Path, plan: NamedProcessPlan, log_path: Path) -> None:
    directory = Path(directory)
    recipe = RECIPES[operation_id]
    log = Path(log_path).read_text(encoding='utf-8', errors='replace')
    layout = RESULT_LAYOUT.validate_json((directory / 'layout.json').read_bytes(), strict=True)
    if layout.operation_id != operation_id:
        raise ValueError('Result layout belongs to another Siril operation.')
    values = json.loads((directory / 'parameters.json').read_text(encoding='utf-8'))
    if re.search(r'(?im)^(?:log: )?(?:Script execution failed|Sequence processing failed|Error in line\s+\d+)', log):
        raise ValueError(parse_failure(log_path))
    for single in layout.single_sequences:
        folder = inside(directory, directory / single.folder)
        stem = single.base + format(single.member, '0' + str(single.fixed) + 'd')
        files = [folder / (stem + suffix) for suffix in ['.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz'] if (folder / (stem + suffix)).is_file()]
        if len(files) != 1:
            raise ValueError('The single sequence frame is missing or ambiguous.')
        descriptor = folder / (single.base + '.seq')
        if not descriptor.exists():
            write_single_sequence(folder, single.base, single.member, single.selected, single.fixed, compressed=files[0].name.endswith('.fz'))
        elif read_sequence_descriptor(descriptor).frames == 1:
            lines = descriptor.read_text(encoding='utf-8').splitlines()
            for index, line in enumerate(lines):
                if line.startswith("S '"):
                    fields = line.rsplit(' ', 4)
                    if len(fields) == 5:
                        fields[-2] = str(int(files[0].name.endswith('.fz')))
                        lines[index] = ' '.join(fields)
            descriptor.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    for output in plan.outputs.values():
        descriptors = [path for pattern in output.supporting_patterns if pattern.pattern.endswith('*.seq')
                       for path in directory.glob(pattern.pattern)]
        if len(descriptors) > 1:
            raise ValueError('An output port must identify one fixed sequence, not several unrelated descriptors.')
        for descriptor in descriptors:
            sequence = read_sequence_descriptor(descriptor)
            base = inside(directory, descriptor.parent / sequence.name)
            if sequence.type == 'R':
                for index, selected in sequence.members:
                    if selected and not any(Path(str(base) + format(index, '0' + str(sequence.fixed) + 'd') + suffix).is_file()
                                            for suffix in ['.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz']):
                        raise ValueError('A selected sequence output frame is missing.')
            for pattern in output.patterns:
                if pattern.format in {'fits', 'video'}:
                    pattern.frame_count = None if sequence.type == 'A' else 1 if sequence.type == 'R' else sequence.frames
    if recipe.mode == 'live_stack' and re.search(r'(Stacking failed|Failed to open|Error:)', log, re.IGNORECASE):
        raise ValueError('Live stacking reported a failed frame; the partial result is not a complete output.')
    if recipe.mode == 'live_stack' and layout.expected_live_frames > 1:
        counts = re.findall(r'Stacked image (\d+)', log)
        if not counts or int(counts[-1]) != layout.expected_live_frames:
            raise ValueError('Live stacking did not report completion of all fixed input frames.')
    for sequence in layout.sequences:
        folder = directory / sequence.folder
        output = folder / (sequence.output_base + '.seq')
        if not output.is_file():
            raise ValueError('Siril did not produce the output sequence descriptor.')
        result = read_sequence_descriptor(output)
        if sequence.expected_frames is not None and result.frames != sequence.expected_frames:
            raise ValueError('The conversion output omitted some fixed input files.')
        if sequence.input_base is not None and sequence.input_base != sequence.output_base:
            source = read_sequence_descriptor(folder / (sequence.input_base + '.seq'))
            filtering = operation_id == 'seqapplyreg' and any(value for name, value in values.items() if name.startswith('use_filter_') or name == 'filter_included')
            if result.frames not in {source.frames, source.selected} and not (filtering and 0 < result.frames <= source.frames):
                raise ValueError('The sequence output does not cover the requested members.')
    if recipe.mode not in {'analysis', 'sequence_analysis', 'metadata', 'python_script'}:
        return
    folders = [directory / member for member in layout.members]
    if recipe.mode == 'sequence_analysis':
        folders = [directory / 'sequence']
    if not folders:
        folders = [directory]
    blocks = log_blocks(log, operation_id)
    for index, folder in enumerate(folders):
        raw = []
        if operation_id == 'histo':
            files = sorted(folder.glob('histo_*.dat'))
            if len(files) != 1:
                raise ValueError('The requested histogram channel was not produced.')
            raw.append(parse_histogram(files[0]))
        elif operation_id == 'jsonmetadata':
            value = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
            raw.append(AnalysisResult(kind='json', title='FITS metadata', source='Siril 1.4.4 jsonmetadata', values=value))
        else:
            declared_files = {path for pattern in plan.outputs['files'].patterns
                              for path in directory.glob(pattern.pattern) if path.parent == folder}
            for file in sorted(declared_files):
                if file.suffix.lower() in {'.csv', '.lst', '.dat'} and file.is_file():
                    raw.append(parse_table(file, operation_id))
            if not raw:
                block = blocks[index] if index < len(blocks) else blocks[-1] if blocks else ''
                raw.append(parse_metrics(operation_id, block))
        if recipe.mode == 'analysis':
            for value in raw:
                value.member_index = index
        (folder / 'analysis.json').write_text(json.dumps([value.model_dump(mode='json') for value in raw],
                                                       ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    outputs = plan.outputs['files']
    if not any(file.path == Path(log_path) for file in outputs.files):
        outputs.files.append(BundleFile(path=Path(log_path), format='other', allow_empty=True))
