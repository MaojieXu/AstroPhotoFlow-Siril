# AstroPhotoFlow Siril Bundle

Bundle 0.1.1 / Siril 1.4.4 / Windows x86_64 / host API 1.

Install through AstroPhotoFlow using the release tag and pinned Git commit. The app directory is tracked with ordinary Git, not LFS. Only Auto Stretch is an executable node; the 199 reference commands are documentation.

The adapter imports only the platform contracts SDK and standard library. It writes process scripts; the host owns process launch, cancellation, science references, caches and canvas authority. Run tests with `python -m pytest tests` in an environment containing AstroPhotoFlow.

Siril is GPL-3.0-or-later. Distributed runtime license notices remain under app; upstream corresponding source: https://gitlab.com/free-astro/siril/-/tree/1.4.4 . Do not remove dependency notices.

Only nodes explicitly listed in bundle.json output_nodes are native execution endpoints. See examples/agent.md for discovery and authorized canvas editing.
