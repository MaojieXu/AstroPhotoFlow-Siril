# AstroPhotoFlow Siril Bundle

Bundle 0.1.2-dev.1 / Siril 1.4.4 / Windows x86_64 / host API 1.

Install through AstroPhotoFlow using the release tag and pinned Git commit. The app directory is tracked with ordinary Git, not LFS. Only Auto Stretch is an executable node; the 199 reference commands are documentation.

The adapter imports only the platform contracts SDK and standard library. It writes process scripts; the host owns process launch, cancellation, science references, caches and canvas authority. Run tests with `python -m pytest tests` in an environment containing AstroPhotoFlow.

Siril is GPL-3.0-or-later. Distributed runtime license notices remain under app; upstream corresponding source: https://gitlab.com/free-astro/siril/-/tree/1.4.4 . Do not remove dependency notices.

Only nodes explicitly listed in bundle.json output_nodes are native execution endpoints. See examples/agent.md for discovery and authorized canvas editing.

## Release policy

This repository currently contains development builds only. Development uses the dev branch and vX.Y.Z-dev.N tags; release_channel is dev. Versions v0.1.0 and v0.1.1 are historical experimental tags, not approved production releases. They are retained for traceability and are not installed by the current catalog.

Production releases require explicit owner approval, a stable release_channel and a vX.Y.Z tag without a prerelease suffix. Development tags are never promoted by moving or overwriting an existing tag. A production release must use a separate approved catalog entry. No production release has been published.
