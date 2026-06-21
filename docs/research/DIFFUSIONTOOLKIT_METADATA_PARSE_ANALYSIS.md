# DiffusionToolkit Metadata Parse Analysis

> **Status:** Research snapshot. Upstream findings are retained for reference;
> use [Architecture](../ARCHITECTURE.md) and [Metadata Parsing](../METADATA_PARSING.md)
> for the current gallery implementation.

Last reviewed: 2026-06-09

## Purpose

This document looks specifically at DiffusionToolkit's metadata parsing logic and
which ideas should be borrowed for gallery-repo.

It complements [DiffusionToolkit Pipeline Audit](DIFFUSIONTOOLKIT_PIPELINE_AUDIT.md),
which covers the broader scan, indexing, thumbnail, and viewer pipeline.

## Sources inspected

| Repo                                                           | Files                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| DiffusionToolkit at `153409c3a0e9569886e6601530365808d4ecbb0e` | [`Metadata.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Scanner/Metadata.cs), [`FileParameters.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Scanner/FileParameters.cs), [`StealthPng.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Scanner/StealthPng.cs), [`ComfyUIParser.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.ComfyUI/ComfyUIParser.cs), [`SimpleWorkflowParser.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.ComfyUI/SimpleWorkflowParser.cs), [`AnimatedWebPWorkflowParser.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.ComfyUI/AnimatedWebPWorkflowParser.cs) |
| gallery-repo                                                   | [`backend/metadata_parse.py`](../../backend/metadata_parse.py), [`backend/metadata_extract.py`](../../backend/metadata_extract.py), [`backend/metadata_store.py`](../../backend/metadata_store.py), [`docs/METADATA_PARSING.md`](../METADATA_PARSING.md)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

## DiffusionToolkit parser shape

DiffusionToolkit has one parser entry point, `Metadata.ReadFromFile()`, which
wraps `ReadFromFileInternal()` with IO retries, error capture, and a no-metadata
fallback.

`ReadFromFileInternal()` does this:

1. Reads the whole file into memory and hashes it.
2. Sniffs magic bytes to identify PNG, JPEG, WebP, WebM, or RIFF/WebP. MP4 is
   detected by extension only after magic-byte fallback.
3. Uses metadata readers per container type.
4. Chooses a generator-specific parser from tags/chunks.
5. Falls back to sidecar `.txt`.
6. Falls back to Stealth PNG for PNG files.
7. Fills width and height from container headers or image identification.

The normalized output is `FileParameters`: prompt, negative prompt, steps,
sampler, CFG scale, seed, width, height, model hash, model, batch data,
aesthetic score, hypernetwork fields, prompt strength, file size, workflow,
workflow ID, ComfyUI nodes, hash, type, and error flags.

## Source and format matrix

| Container/source                          | DT detection                                             | DT parser                      |
| ----------------------------------------- | -------------------------------------------------------- | ------------------------------ |
| PNG `tEXt` `parameters:`                  | JSON containing `sui_image_params`                       | SwarmUI                        |
| PNG `tEXt` `parameters:`                  | JSON that parses as RuinedFooocus/Fooocus                | RuinedFooocus/Fooocus          |
| PNG `tEXt` `parameters:`                  | Other text or JSON fallback                              | A1111                          |
| PNG `tEXt` `Comment:`                     | Any PNG text directory has `Software: NovelAI`           | NovelAI                        |
| PNG `tEXt` `Comment:`                     | Otherwise                                                | FooocusMRE                     |
| PNG `tEXt` `Software: NovelAI`            | Exact software tag                                       | NovelAI                        |
| PNG `tEXt` `Dream:`                       | InvokeAI legacy command string                           | InvokeAI                       |
| PNG `tEXt` `sd-metadata:`                 | InvokeAI JSON wrapper                                    | InvokeAI new                   |
| PNG `tEXt` `invokeai_metadata:`           | InvokeAI JSON                                            | InvokeAI 2                     |
| PNG `tEXt` `prompt:`                      | JSON payload                                             | ComfyUI                        |
| PNG `tEXt` `prompt:`                      | Non-JSON payload                                         | EasyDiffusion                  |
| PNG `tEXt` `Score:` or `aesthetic_score:` | Numeric score                                            | Adds aesthetic score           |
| PNG `iTXt` `parameters:`                  | Textual data                                             | A1111                          |
| PNG EXIF SubIFD `User Comment`            | User comment text                                        | A1111                          |
| JPEG EXIF SubIFD `User Comment`           | Contains `sui_image_params`                              | SwarmUI                        |
| JPEG EXIF IFD0 `Software` + `Makernote`   | Fooocus software, makernote `fooocus` or `a1111`         | Fooocus or A1111               |
| JPEG EXIF IFD0 `User Comment`             | JSON starting with `{"prompt":`                          | ComfyUI                        |
| JPEG fallback                             | EXIF/metadata directories                                | A1111                          |
| WebP EXIF IFD0 `Make`                     | `workflow:` JSON                                         | ComfyUI workflow               |
| WebP EXIF IFD0 `Model`                    | `prompt:` JSON                                           | ComfyUI prompt data            |
| WebP EXIF SubIFD `User Comment`           | JSON starting with `{"prompt":`                          | ComfyUI                        |
| WebP fallback                             | EXIF/metadata directories                                | A1111                          |
| WebM comment                              | `Comment` tag                                            | ComfyUI                        |
| MP4 metadata comment                      | QuickTime metadata `Comment`                             | ComfyUI                        |
| Exact sidecar                             | Same image basename with `.txt`                          | A1111 or Stable Diffusion text |
| Directory sidecar fallback                | Cached directory `.txt` whose basename is a prefix match | A1111 or Stable Diffusion text |
| Stealth PNG                               | Alpha/RGB least-significant-bit payload, optional gzip   | A1111                          |

## Format parser notes

### A1111

DT uses a line-state parser:

- Prompt state until `Negative prompt:`.
- Negative prompt state until `Steps:`.
- Parameter state parses the `Steps:` line by splitting comma-separated
  key/value pairs.

It extracts steps, sampler, CFG scale, seed, size, model hash, model, batch
size, hypernetwork, hypernetwork strength, and aesthetic score.

This is pragmatic but brittle for values that contain commas or extra colons.
gallery-repo's regex-based parser avoids some of that fragility but currently
has two separate implementations.

### Stable Diffusion text sidecar

DT also supports a separate multiline sidecar format detected by the presence of
`Width:`, `Height:`, and `Seed:` lines. It parses prompt, negative prompt,
width, height, guidance scale, seed, sampler, and prompt strength.

gallery-repo does not currently have a distinct adapter for this text format.

### ComfyUI

DT does not primarily normalize ComfyUI into prompt/negative prompt fields. It
preserves workflow JSON and parses nodes for display/search:

- If JSON has a top-level `prompt` field, that field becomes the root.
- If the root is a JSON string, it is parsed again.
- If the root has a `nodes` array, DT treats it as a visual/animated WebP style
  workflow and maps `widgets_values` to property names from `comfy-nodes.json`.
- Otherwise it treats the object as a simple API prompt graph and records scalar
  input values per node.
- It replaces `NaN` with `null` before parsing some prompt JSON.

gallery-repo currently does a more user-facing ComfyUI extraction in
`metadata_parse.py`: it finds `CLIPTextEncode`, `KSampler`, checkpoint, VAE,
upscale, ControlNet, LoRA, and clip-skip nodes. That is better for the lightbox,
but it is heuristic and not shared with `metadata_extract.py`.

### NovelAI, EasyDiffusion, InvokeAI, Fooocus, SwarmUI

DT has dedicated adapters for each family and keeps a workflow/raw-data string
for most of them. The biggest format coverage not currently represented in
gallery-repo is Fooocus/RuinedFooocus/FooocusMRE, InvokeAI, Stable Diffusion
sidecar text, WebP ComfyUI EXIF conventions, MP4/WebM ComfyUI comments, and
Stealth PNG.

gallery-repo already supports SwarmUI, A1111, ComfyUI, NovelAI, EasyDiffusion,
and exact `.txt` sidecars in the `/api/metadata` path.

## gallery-repo gaps

### 1. Two parser stacks

gallery-repo currently has two metadata parsers:

- `metadata_parse.py` powers `/api/metadata` and has richer generator support.
- `metadata_extract.py` powers SQLite indexing via `metadata_store.index_image()`
  and extracts a smaller subset.

This means the lightbox can show data that prompt search may not index with the
same fidelity. SwarmUI, NovelAI, EasyDiffusion, richer ComfyUI fields, LoRA, and
structured params can diverge between the API response and the search index.

### 2. Missing source provenance

DT's code path implicitly knows whether a result came from PNG text, EXIF user
comment, WebP EXIF, sidecar, video comment, or Stealth PNG. gallery-repo returns
`tool`, but it does not preserve source location or parser confidence.

Source provenance would help debugging and future UI copy/actions without
changing the current lightbox design.

### 3. Limited WebP and EXIF conventions

gallery-repo reads Pillow `img.info` and EXIF `UserComment`, but it does not yet
model the WebP conventions DT handles:

- EXIF IFD0 `Make` containing `workflow:` JSON.
- EXIF IFD0 `Model` containing `prompt:` JSON.
- EXIF SubIFD `User Comment` containing ComfyUI JSON.

These are worth testing with real samples before implementation because Pillow's
surface for WebP EXIF differs from MetadataExtractor's directory/tag model.

### 4. Sidecar matching is narrower

gallery-repo checks only `image.with_suffix(".txt")`. DT first checks exact
basename, then searches cached directory `.txt` files for a prefix match.

Prefix matching can recover metadata exported with naming variants, but it can
also attach the wrong sidecar in busy folders. If borrowed, it should be unique,
opt-in, or heavily constrained.

### 5. No parser fixture suite

The parser has no representative fixture tests for A1111, SwarmUI, ComfyUI,
NovelAI, EasyDiffusion, EXIF UserComment, sidecar text, or malformed metadata.
The next parser changes should start with fixture tests because regressions are
otherwise hard to see from the UI.

## Ideas worth applying

| Priority | Idea                          | Application in gallery-repo                                                                                                                                                                 | Acceptance criteria                                                                                                                                |
| -------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1       | One normalized parser core    | Introduce a shared parser module used by both `/api/metadata` and SQLite indexing. Keep API shaping in `metadata_parse.py` and file/index shaping in `metadata_extract.py`.                 | Same fixture produces equivalent prompt, negative prompt, model, sampler, seed, steps, CFG, dimensions, raw text, and JSON in API and index paths. |
| P1       | Source candidate pipeline     | Separate "read metadata candidates from file" from "parse generator format". Candidates should include PNG text, EXIF UserComment, WebP EXIF conventions where supported, and sidecar text. | Each parse result records `tool`, `source`, and `confidence` internally; frontend response remains backward-compatible.                            |
| P1       | Preserve raw workflow/json    | Keep raw workflow or generator JSON for ComfyUI, SwarmUI, NovelAI, EasyDiffusion, and future Fooocus/InvokeAI adapters.                                                                     | `metadata_json` stores the original structured payload or normalized payload without losing raw workflow text.                                     |
| P1       | Parser fixtures               | Add tests for existing supported formats before widening coverage.                                                                                                                          | Golden tests cover happy path, malformed JSON, missing optional fields, exact sidecar, and EXIF UserComment.                                       |
| P2       | WebP ComfyUI EXIF support     | Add candidate extraction for `workflow:` and `prompt:` WebP EXIF fields if Pillow exposes them reliably.                                                                                    | WebP fixture populates workflow JSON and ComfyUI params without changing `/api/scan`.                                                              |
| P2       | Fooocus and InvokeAI adapters | Add small `try_parse_fooocus*()` and `try_parse_invokeai*()` adapters based on DT's field mappings.                                                                                         | Fixtures populate prompt, negative prompt, seed, steps, CFG, sampler, model, dimensions.                                                           |
| P2       | Safer sidecar fallback        | Add unique-prefix sidecar matching only when exact sidecar is absent and exactly one candidate matches.                                                                                     | Ambiguous matches are ignored and logged/debuggable; exact sidecar still wins.                                                                     |
| P2       | ComfyUI node summaries        | Store a compact node/input summary for search and debugging, separate from lightbox prompt fields.                                                                                          | Search can match relevant node scalar values without bloating the API response.                                                                    |
| P3       | Stealth PNG fallback          | Support only in explicit/background indexing, not the lightbox hot path.                                                                                                                    | Stealth scan is bounded, cancellable, and never blocks `/api/scan` or initial lightbox open.                                                       |

## Things not to copy

| DT behavior                                            | Why not copy                                                                                                    |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| Read and hash the whole file before parsing            | gallery-repo already invalidates cache by path, mtime, and size. Full reads hurt large images and cold folders. |
| Synchronous parse in viewer selection                  | The current lightbox opens first and lets metadata resolve asynchronously. Keep that behavior.                  |
| Stealth PNG pixel scan in normal metadata request      | It can require scanning image pixels and should not be part of common UI latency.                               |
| Blind prefix sidecar matching                          | It can attach the wrong metadata in folders with similar filenames.                                             |
| ComfyUI node indexing as the only ComfyUI parse result | The lightbox needs human-readable prompt/negative prompt/params. Node summaries should be additive.             |
| Desktop-only file watcher assumptions                  | gallery-repo is local-first web software; watcher support should remain optional.                               |

## Recommended implementation sequence

1. Add parser fixture tests around current gallery behavior.
2. Extract the common normalized parser core from `metadata_parse.py` and
   `metadata_extract.py`.
3. Route both `/api/metadata` and `metadata_store.index_image()` through the
   shared parser core.
4. Add source/provenance fields internally, keeping the public
   `MetadataResponse` backward-compatible.
5. Add WebP EXIF ComfyUI support if Pillow can expose the required fields
   reliably.
6. Add Fooocus, InvokeAI, and Stable Diffusion sidecar adapters behind fixtures.
7. Consider Stealth PNG only for explicit rebuild/background indexing.

The most valuable change is parser unification. Broader format coverage should
come after tests, because the current duplication can otherwise make lightbox and
search behavior diverge further.
