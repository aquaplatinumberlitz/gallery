# Metadata Parsing

Status: Maintained

Last verified against `backend/metadata_extract.py`, `backend/metadata_parse.py`, and
`backend/metadata_store/`: 2026-06-25.

## Supported generators

| Generator                   | Verified input shape                                                                                                   | Normalized tool |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------- |
| AUTOMATIC1111 / WebUI-style | Text in the image `parameters` field or an exact same-basename `.txt` sidecar                                          | `A1111`         |
| ComfyUI                     | JSON in `prompt` and/or `workflow` image fields                                                                        | `ComfyUI`       |
| SwarmUI                     | `sui_image_params` JSON in `parameters` or EXIF `UserComment`                                                          | `SwarmUI`       |
| NovelAI                     | JSON whose `Software` value contains `NovelAI`, or A1111-like text beginning with the recognized NovelAI prompt prefix | `NovelAI`       |
| EasyDiffusion               | JSON containing `prompt`, `negative_prompt`, `width`, and `height`, excluding SwarmUI JSON                             | `EasyDiffusion` |
| Unknown/generic             | Recognized text fields that do not match a generator parser                                                            | `Unknown`       |

The generic text keys read from Pillow metadata are `Description`, `Comment`,
`UserComment`, `Software`, `parameters`, `prompt`, and `workflow`. EXIF tag 37510 is
also read as `UserComment` when available.

## Source precedence and parser dispatch

`extract_metadata()` opens the image with Pillow, applies EXIF orientation for stored
dimensions, gathers image text/EXIF fields, and dispatches sources in this order:

1. SwarmUI JSON from `parameters`, then EXIF `UserComment`.
2. ComfyUI JSON from `prompt`; if that cannot be decoded, `workflow` is used.
3. The `parameters` field:
   - JSON is tried as NovelAI, then EasyDiffusion, then A1111-style text.
   - Non-JSON text is parsed as A1111-style parameters; the recognized NovelAI prompt
     prefix changes the normalized tool to `NovelAI`.
4. An exact same-basename `.txt` sidecar, parsed as A1111-style text.
5. Generic recognized text fields, stored with tool `Unknown`.
6. An empty normalized `Unknown` result when no supported metadata is found.

The first successful parser wins. Sidecars therefore do not override supported embedded
metadata. Only `.txt` sidecars produced by `path.with_suffix(".txt")` are considered.
Before a sidecar is read, its size is checked against
`GALLERY_METADATA_SIDECAR_MAX_BYTES` (1 MiB by default). Oversized sidecars are
never truncated; API reads return `413` and lifecycle jobs persist a bounded
failure.

## API and cache flow

`GET /api/metadata?path=...` is defined in `backend/metadata_parse.py`.

- The route resolves the path, enforces `PATH_SAFETY_ROOT`, requires an active
  registered-library image asset, verifies the file and image extension, and
  runs parsing in a thread pool.
- `parse_metadata()` keys its in-memory LRU by path, mtime, and size.
- A matching SQLite row is preferred before reopening the original image.
- Concurrent cold requests for the same key share one in-flight parse.
- A cold parse calls `extract_metadata()`, persists the normalized record, and marks a
  matching current metadata-index job done.

Background indexing uses the same `extract_metadata()` function, so the API and indexer
share one parser implementation.

Catalog status metadata coverage counts active image assets only. Videos never
enter the metadata denominator, so a video-only library converges with zero
metadata assets.

## Background lifecycle

Background metadata work is scheduled through
`indexer.dispatch_metadata_index_paths()`. The scheduler persists/coalesces rows
in `metadata_index_jobs` and wakes `MetadataLifecycleWorker`; it does not push
runtime work into an in-memory queue.

The worker claims queued jobs directly from SQLite, extracts metadata outside
any long DB transaction, writes `image_metadata`, and then completes the job
through the store-layer completion helper. Completion verifies the current
`path + mtime_ns + size` identity, marks `metadata_index_jobs.state='done'`, and
materializes `assets.metadata_state='done'` together. Missing asset rows become
`skipped`; changed file versions become `stale`.

Backend startup runs metadata job recovery before starting the worker. Recovery
resets interrupted `running` jobs, fails exhausted attempts, and repairs
historical rows where a done job/current metadata row exists but the asset state
was not materialized.

The shared catalog database is schema version 2. Upgrading a version 1 database
creates a consistent `.v1.bak` before atomically rebuilding legacy REAL-affinity
nanosecond identity columns as INTEGER. Metadata and catalog rows remain in the
same single-process SQLite database; the migration does not introduce a second
store or modify source media.

## Stored database fields

The `image_metadata` table stores:

| Group                    | Fields                                                                                                                                                                         |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| File identity/version    | `id`, `path`, `name`, `mtime`, `mtime_ns`, `size`                                                                                                                              |
| Image properties         | `width`, `height`, `format`, `mode`, `has_alpha`, `aspect_ratio`                                                                                                               |
| Core generation data     | `prompt`, `negative_prompt`, `model`, `sampler`, `seed`, `steps`, `cfg_scale`                                                                                                  |
| Extended generation data | `tool`, `scheduler`, `model_hash`, `lora_text`, `generation_time`, `clip_skip`, `hires_upscale`, `hires_steps`, `denoising_strength`, `vae`, `ensd`, `aesthetic_score`, `date` |
| Raw/normalized payloads  | `raw_metadata_text`, `metadata_json`                                                                                                                                           |
| Timestamps               | `updated_at`, `indexed_at`                                                                                                                                                     |

FTS5 unicode and trigram tables index `name`, `prompt`, `negative_prompt`, `model`,
`sampler`, and `raw_metadata_text`.

Parsed LoRA/resource data is also normalized into `image_resources` with `path`, `kind`,
`name`, `hash`, `resource_hash`, `weight`, `strength`, `raw_json`, and `updated_at`.

## Normalized API shape

The parser returns a dictionary containing at least:

- `tool`
- `prompt`
- `negative_prompt`
- `params`
- `width`
- `height`
- `name`

Generator-specific data such as SwarmUI models and dates remains in `metadata_json` and
the API response after JSON sanitization.
