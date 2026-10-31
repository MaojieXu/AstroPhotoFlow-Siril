# AstroPhotoFlow Siril Bundle

Bundle 0.2.0-dev.2 / Siril 1.4.4 / Windows x86_64 / host API 2.

Install this development release through AstroPhotoFlow using tag `v0.2.0-dev.2` and its pinned Git commit. The app directory is tracked with ordinary Git, not LFS; the Siril 1.4.4 runtime is unchanged.

English and Simplified Chinese display catalogs cover all 160 declared operations/nodes, parameters and ports. They require a platform that supports the optional `locales` Bundle metadata. Authored Chinese text lives in `locales/source.zh.json`; `python tools/build_catalog.py` rebuilds declarations and both display catalogs. `python tools/build_locales.py` rebuilds display catalogs alone without modifying executable declarations. Labels never rename command, parameter, node or port identities. Original Siril logs remain unchanged.

The candidate implements 160 typed operations covering all 181 scriptable reference commands through executable nodes, per-call runtime/IO settings and explicit combined operations. All 199 indexed entries are accounted for in [coverage](reference/coverage.json). The fixed Windows executable provides 198 entries: 181 scriptable, 17 non-scriptable; `ls` is unavailable on Windows, which uses `dir`. Non-scriptable/GUI/session display commands are documented without fake executable nodes, as agreed with the owner.

Declarations and process-plan compilation are not runtime acceptance. Current recipe tests are written but have not been executed; native loading, scientific processing combinations and visual acceptance remain to be verified. See [usage](docs/usage.md) and the retained prior evidence in `reference/assessments.json`.

The adapter imports only the platform contracts SDK and standard library. It writes invocation-owned scripts and parses actual files/logs into normalized analysis artifacts; the host owns process launch, progress, observed process-tree cancellation, fixed references, scientific checks, caches and canvas authority. Build declarations with `python tools/build_catalog.py`. Integration-stage tests use `python -m pytest tests` in an environment containing SDK v2; Feature development does not run the test suite by default.

Siril is GPL-3.0-or-later. Distributed runtime license notices remain under app; upstream corresponding source: https://gitlab.com/free-astro/siril/-/tree/1.4.4 . Do not remove dependency notices.

Only nodes explicitly listed in bundle.json output_nodes are native execution endpoints. See examples/agent.md for discovery and authorized canvas editing.

## Release policy

This repository currently contains development builds only. Development uses the dev branch and vX.Y.Z-dev.N tags; release_channel is dev. Versions v0.1.0 and v0.1.1 are historical experimental tags, not approved production releases. They are retained for traceability and are not installed by the current catalog.

Production releases require explicit owner approval, a stable release_channel and a vX.Y.Z tag without a prerelease suffix. Development tags are never promoted by moving or overwriting an existing tag. A production release must use a separate approved catalog entry. No production release has been published.
