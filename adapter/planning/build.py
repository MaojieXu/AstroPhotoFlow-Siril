from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import JsonValue

from astrophotoflow.contracts.bundles import (
    BundleInputMetadata,
    NamedProcessPlan,
)

from ..arguments import quoted, token
from ..outputs import compressed_paths
from ..planning.files import build_file_plan
from ..planning.image import IMAGE_MODES, build_image
from ..recipes import RECIPES
from ..runtime import prepare_runtime
from ..sequences import copy_fits, read_sequence_descriptor
from ..types import RESULT_LAYOUT, BuildContext, ResultLayout, SingleSequenceLayout


def build_plan(operation_id: str, sources: Mapping[str, Sequence[Path]], parameters: Mapping[str, JsonValue], directory: Path, *,
    preview: bool = False, prepare_sample: bool = False,
    supporting_sources: Mapping[str, Sequence[Path]] | None = None,
    source_groups: Mapping[str, Sequence[Sequence[Path]]] | None = None,
    supporting_groups: Mapping[str, Sequence[Sequence[Path]]] | None = None,
    source_metadata: Mapping[str, Sequence[BundleInputMetadata]] | None = None) -> NamedProcessPlan:
    if operation_id not in RECIPES:
        raise ValueError('Unsupported operation: ' + operation_id)
    parameters = dict(parameters)
    recipe = RECIPES[operation_id]
    if preview and not recipe.live:
        raise ValueError('This operation does not support display-sample preview.')
    directory = Path(directory).resolve()
    sources = {name: [Path(path).resolve() for path in paths] for name, paths in sources.items()}
    supporting_sources = supporting_sources or {}
    source_groups = source_groups or {name: [paths] for name, paths in sources.items()}
    supporting_groups = supporting_groups or {name: [supporting_sources.get(name, [])] for name in sources}
    source_metadata = {name: [BundleInputMetadata.model_validate(item) for item in items] for name, items in (source_metadata or {}).items()}
    commands, runtime = prepare_runtime(directory, parameters)
    (directory / 'parameters.json').write_text(json.dumps(parameters, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    outputs = {}
    layout = ResultLayout(operation_id=operation_id)
    for definition in recipe.inputs:
        name = definition.name
        if definition.cardinality != 'one' or definition.type != 'APF_SCIENCE' or name not in sources:
            continue
        source = sources[name][0]
        if not source.name.lower().endswith(('.fit', '.fits', '.fts', '.fit.fz', '.fits.fz', '.fts.fz')):
            folder = directory / 'operands'; folder.mkdir(exist_ok=True)
            sources[name] = [copy_fits(commands, source, folder / (name + '.fit'))]
    context = BuildContext(recipe=recipe, sources=sources, values=parameters, directory=directory, commands=commands, outputs=outputs,
        runtime=runtime, supporting_sources=supporting_sources, source_groups=source_groups, supporting_groups=supporting_groups,
        source_metadata=source_metadata, layout=layout, preview=preview, prepare_sample=prepare_sample)
    if recipe.mode in IMAGE_MODES:
        build_image(context)
    else:
        build_file_plan(context)
    sequence_queries = set()
    for output in outputs.values():
        for pattern in output.supporting_patterns:
            if pattern.pattern.endswith('*.seq'):
                prefix = directory / pattern.pattern.removesuffix('*.seq')
                query = str(prefix)
                if query not in sequence_queries:
                    descriptor = Path(str(prefix) + '.seq')
                    single = read_sequence_descriptor(descriptor) if descriptor.is_file() else None
                    if single and single.frames == 1 and single.type == 'R':
                        layout.single_sequences.append(SingleSequenceLayout(folder=prefix.parent.relative_to(directory).as_posix(), base=prefix.name, member=single.members[0][0], selected=single.members[0][1], fixed=single.fixed))
                    else:
                        commands.extend(['cd ' + quoted(prefix.parent), 'getref ' + token(prefix.name)])
                    sequence_queries.add(query)
    script = directory / 'operation.ssf'
    script.write_text('\n'.join(compressed_paths(commands, outputs, runtime)) + '\n', encoding='utf-8')
    (directory / 'layout.json').write_bytes(RESULT_LAYOUT.dump_json(layout))
    return NamedProcessPlan(arguments=['-o', '-i', str(directory / 'siril.ini'), '-d', str(directory), '-s', str(script)],
                            outputs=outputs, temporary_directory=directory / 'tmp', thread_limit=runtime.threads,
                            environment={'LC_ALL': 'C', 'LANG': 'C', 'LANGUAGE': 'C'},
                            linear_sample=directory / ('linear.fit.fz' if runtime.compression_enabled else 'linear.fit') if prepare_sample else None)
