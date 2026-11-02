# AstroPhotoFlow Siril Bundle

Bundle 0.2.0-dev.2 / Siril 1.4.4 / Windows x86_64 / host API 2.

Command references and Siril-specific assessment/coverage checks are owned here under `reference/` and `tests/test_catalog.py`. The platform consumes exported metadata; it does not maintain another Siril command reference. Live operations declare both `preview.input` and `preview.output`; Siril decoding, sampling commands and output file naming remain in this adapter. Current checkout changes are unpublished and are not changes to the existing v0.2.0-dev.2 tag.

Install this development release through AstroPhotoFlow using tag `v0.2.0-dev.2` and its pinned Git commit. The app directory is tracked with ordinary Git, not LFS; the Siril 1.4.4 runtime is unchanged.

English and Simplified Chinese display catalogs cover all 160 declared operations/nodes, parameters and ports. They require a platform that supports the optional `locales` Bundle metadata. Authored Chinese text lives in `locales/source.zh.json`; `python -m tools.build_catalog` rebuilds declarations and both display catalogs. `python -m tools.build_locales` rebuilds display catalogs alone without modifying executable declarations. Labels never rename command, parameter, node or port identities. Original Siril logs remain unchanged.

The candidate implements 160 typed operations covering all 181 scriptable reference commands through executable nodes, per-call runtime/IO settings and explicit combined operations. All 199 indexed entries are accounted for in [coverage](reference/coverage.json). The fixed Windows executable provides 198 entries: 181 scriptable, 17 non-scriptable; `ls` is unavailable on Windows, which uses `dir`. Non-scriptable/GUI/session display commands are documented without fake executable nodes, as agreed with the owner.

Declarations and process-plan compilation are not runtime acceptance. Current recipe tests are written but have not been executed; native loading, scientific processing combinations and visual acceptance remain to be verified. See [usage](docs/usage.md) and the retained prior evidence in `reference/assessments.json`.

The adapter uses standard-library dataclasses and the platform contracts SDK; Pydantic TypeAdapter validates its typed per-call result layout. It writes invocation-owned scripts and parses actual files/logs into normalized analysis artifacts; the host owns process launch, progress, observed process-tree cancellation, fixed references, scientific checks, caches and canvas authority. Build declarations with `python -m tools.build_catalog`. Integration-stage tests use `python -m pytest tests` in an environment containing SDK v2; Feature development does not run the test suite by default.

Siril is GPL-3.0-or-later. Distributed runtime license notices remain under app; upstream corresponding source: https://gitlab.com/free-astro/siril/-/tree/1.4.4 . Do not remove dependency notices.

Only nodes explicitly listed in bundle.json output_nodes are native execution endpoints. See examples/agent.md for discovery and authorized canvas editing.

## Release policy

This repository currently contains development builds only. Development uses the dev branch and vX.Y.Z-dev.N tags; release_channel is dev. Versions v0.1.0 and v0.1.1 are historical experimental tags, not approved production releases. They are retained for traceability and are not installed by the current catalog.

Production releases require explicit owner approval, a stable release_channel and a vX.Y.Z tag without a prerelease suffix. Development tags are never promoted by moving or overwriting an existing tag. A production release must use a separate approved catalog entry. No production release has been published.

The four SDK entry points in `adapter/siril.py` delegate to typed planning, runtime, sequences, outputs, analysis and result modules. `BuildContext`, `RuntimeOptions`, `SequenceDescriptor` and `ResultLayout` describe actual per-call inputs and output facts; they do not store ComfyUI graphs or schedule execution.


## Local integration verification (2026-11-01)

The reference/preview-output candidate `a6f5ad0f3eafceb44018ac4b99dc7b9f5b9c3786` and generator normalization `7c75f46931a2aa52b86d06e43ab295f8fad850cf` were independently reviewed read-only. The latter only orders ten preview declarations as generated; parsed JSON values are unchanged. All 60 Bundle tests passed on the normalized candidate. Platform validation is committed in `docs/development/test-matrix.md#file-ownership-siril-decoupling-integration` in AstroPhotoFlow: generic named preview contracts, command references, HTTP/client/MCP/CLI, frontend and wheel resources. No new scientific processing acceptance or publication is implied. Manifest remains Bundle 0.2.0-dev.2 / Siril 1.4.4 / SDK v2; published tag v0.2.0-dev.2 remains at `5d16fb6fc10b4ee57de428d6eba522c918b1b441`.
