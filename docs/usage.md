# Siril 1.4.4 candidate

This candidate covers commands by their actual capability, not by assuming 199 commands equal 199 canvas nodes. `reference/coverage.json` is the complete mapping. `reference/cli-help.json` records help from the fixed executable; `reference/formats.json` records static extensions and the six movie extensions declared by the fixed source. Definitions are built from explicit recipes in `adapter/recipes.py`, backed by process construction and parsing in `adapter/siril.py`.

The host must support Bundle SDK v2 in `astrophotoflow.contracts.bundles`. No unmerged hot-reload Feature is required. The current default platform catalog may still point to the previously released Auto Stretch Bundle; this candidate has not been published and cannot be represented by that old SHA.

## Inputs and outputs

Use library references to fixed asset/group versions. Scientific images use `APF_SCIENCE`; bad pixel lists, ICC profiles, WCS files, comparison-star CSV and Python scripts use `APF_FILE`. File originals are pinned and copied/staged when writable context is necessary. A preview is never an input file. Scalar operands and masters are explicit named ports. Optional ports may remain disconnected.

Single-image operations process an ordered static group without taking only the first member. Sequence operations retain the `.seq` descriptor and supporting registration/star/index files across nodes. Writable sequence descriptors are rebound to the new invocation; no hard link exposes an old scientific file to in-place changes. Packed FITS/SER/movie containers stay complete; several packed containers require separate Merge inputs rather than silently taking their first frames.

Merge and Stack All use native growing inputs. Export, stacking and analysis nodes are explicit execution endpoints. Auto Stretch retains its existing endpoint identity. Other transforms are connected to an endpoint; the Bundle does not mark every node as a terminal or execute unrelated branches to obtain previews.

Output references identify checked complete files by run, node, output and fixed member. The host checks format, containment, content identity and FITS/SER frame counts. Movie sequence counts come from Siril's fixed FFMS2 reader and descriptor; codec-specific execution remains unverified. Completion images, file browsing, HDU/frame viewing, metrics, tables and histogram display use the platform's shared structures. Opening a view does not register a material or change canvas control.

## Parameters and runtime

The operation declaration is authoritative. Optional numeric/string arguments have a separate `use_*` boolean. Disabled values are omitted; an enabled zero is passed as zero. A widget seed is not a claimed default of Siril. Missing, null and zero are not substituted for one another. `fill`/`ffill` can omit the rectangle; `crop` can explicitly use the current selection instead of positional coordinates.

`runtime` is per-call JSON. It supports private `ini` content, scalar Siril `settings`, `threads`, `memory_ratio`, `output_bits`, `compression`, `online`, `selection`, `findstar` and `photometry`. Working/swap directories and the managed output extension remain invocation-owned. `selection` is omitted for the native default context, null to clear it, or `[x,y,width,height]`; only commands that use Siril's selection consume that rectangle. There is no shared Siril session between graph nodes. Networking starts offline; enabling it is explicit. The process uses C locale for reproducible parsing. A thread limit also applies at BLAS/OpenMP startup.

Example controls:

```json
{"threads":2,"output_bits":32,"compression":{"enabled":true,"type":"gzip1","quantisation":0}}
```

Coordinate pairs for plate solving accept `RA,Dec`, two unambiguous space-separated values, or a JSON string array such as `["12 34 56","+12 34 56"]`. Photometry pixel/WCS positions use `x,y` or decimal `ra,dec`; reference stars are a JSON list of pairs. CSV/DAT exports retain full data; normalized display tables show the first 200 rows, histograms sum 128 original bins into each of 512 displayed bins, and text reports identify their excerpt limit. Full logs and original report files remain available. Unavailable values remain null with the source/sample information, never synthetic zeroes.

Python scripts run through Siril's `pyscript`, synchronously. Choose inline content or a fixed library `.py` input. Input bytes are copied unchanged, argument placeholders `{input0}`, `{input1}`, etc. address those copies, and `load_image` controls whether the first input is loaded as the Siril image context. Script output patterns are relative, explicitly typed and checked inside the invocation directory. The script runs with local user permissions; this is not a sandbox for malicious code. Scripts must finish their child work before returning. The host observes owned processes and reports an uncertain stop as unknown.

## Fixed-version differences and dependencies

- The executable help omits the nine matrix coefficients for `seqccm`; the implemented binding follows the fixed source. `seqwiener`/`threshhi` help contain command-name typos. Sequence deconvolution writes the native `dec_` prefix, not an invented `-prefix` option. Most export commands append their own suffix.
- `seqmerge_cfa` has inconsistent documented/parsed prefix spelling in 1.4.4. The managed operation uses its actual native output name inside the private invocation directory.
- A synthetic calibration bias expression evaluating to zero is rejected by Siril 1.4.4 itself. It is not silently turned into an omitted bias; select the distinct no-bias mode if that is the intended operation.
- `subsky -existing` needs GUI background samples and is not fabricated by a stateless node. The executable operation generates its own samples. Non-scriptable commands retain their complete reference and are explicitly non-executable. For `visu`, the shared viewer offers black/white display thresholds in decoded pixel units without rewriting science files. For `inspector`, full-resolution pan/zoom and 100% display support manual corner/center checks; the exact nine-panel mosaic remains deferred. `dir`/`ls` have fixed output-member names/downloads instead of arbitrary directory browsing. Other GUI/state-dependent capabilities await a separate GUI design.
- StarNet requires a compatible executable/weights. Local astrometry.net, local/online catalogs, SPCC responses and embedded Python must be available for the selected operation. No proprietary dependency, login or global configuration is silently installed. Missing requirements produce the real CLI failure and log.

No current operation is claimed as runtime-verified merely because its declaration compiles. Integration must exercise the meaningful image, calibration, registration, stacking, movie/container, multi-output, analysis, dependency-error and cancellation combinations on synthetic data, then distinguish those results from user visual acceptance.
