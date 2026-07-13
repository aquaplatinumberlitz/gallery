# Metadata Parsing

Status: Maintained

Last verified against `backend/metadata_extract.py`, `backend/metadata_parse.py`, and
`backend/metadata_store/`: 2026-07-13.

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
Embedded parsers run before sidecar content is opened. When supported embedded
metadata wins, the sidecar's validated descriptor identity is still persisted
for cache/watcher invalidation, but unused content is not read or rejected for
size. The bounded content read and `413` behavior apply only when precedence
actually reaches the sidecar parser.
The sidecar is accepted only for an active registered image asset, beside the
authorized image, inside its matched import root and `PATH_SAFETY_ROOT`, and
outside exclusion patterns. Symlinks are rejected without following them for
content. The same descriptor is inspected and bounded-read using no-follow
flags where supported plus a cross-platform identity fallback. At most
`GALLERY_METADATA_SIDECAR_MAX_BYTES + 1` bytes are read (1 MiB plus one by
default). Oversized or concurrently grown sidecars are never truncated; API
reads return `413` and lifecycle jobs persist a bounded failure. Persisted
sidecar identity comes from that validated descriptor.

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

The shared catalog database is schema version 10. Version 10 creates
`asset_generation_signatures` through a consistent `.v8.bak`, one
`BEGIN IMMEDIATE`, a foreign-key check, and a final `user_version` publish. It
does not backfill inline. Version 9 remains reserved for a historical catalog
sentinel, so maintained schema evolution advances directly from 8 to 10.
Earlier migrations retain their documented backups and ownership rules.
Metadata and catalog rows remain in the same single-process SQLite database;
migrations do not introduce a second store or modify source media.

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

The durable `prompt_values` search index derives `asset_prompt_values` from
these stored metadata rows. Prompt identity uses Unicode NFKC, trimmed and
collapsed whitespace, casefolded search text, and SHA-256 of
`kind + NUL + search_text`. Missing prompts are recorded as
`not_applicable`; the backfill never reopens media. Observed model names and
hashes from core metadata and checkpoint/model resources are retained as
explicit many-to-many aliases.

The separate version-1 generation prompt normalizer splits positive and
negative prompts primarily on comma/newline atoms, applies Unicode NFKC,
collapses whitespace, casefolds identity while retaining display text, and
parses only supported outer emphasis syntax into a weight clamped from `0.1`
through `2`. It rejects empty, control-heavy, and over-160-character atoms;
each prompt is capped at 64 atoms and candidate lookup may select at most 16.

The enabled `generation_signatures` derived index stores one current row per
active asset. `prompt_hash` covers normalized positive/negative atoms;
`family_hash` adds explicit model identity plus sorted resource identities;
`recipe_hash` adds recorded sampler, scheduler, steps, CFG, dimensions,
denoising, hires, VAE, resource strength, and approved typed workflow
properties; `exact_hash` adds recorded seed/deterministic identifiers. Model
and resource hashes win over normalized name fallbacks. Numeric inputs use a
finite, non-exponent decimal form with trailing zeroes removed and negative
zero mapped to `0`. Missing inputs remain explicit and a promptless record
cannot create family, recipe, or exact hashes from common model/seed/sampler
defaults. Raw workflow JSON is never hashed wholesale.

Full metadata persistence deletes any prior signature and extraction marker in
the same transaction, then coalesces a durable missing-index job after commit.
Backfill uses active `asset_id` keysets in batches of at most 200; source
mtime/size and extractor version drive refresh, and failures remain observable
in the standard derived-index job/state tables without blocking metadata or
lexical search.

For ComfyUI, parsing also retains a bounded normalized internal workflow
document in the stored metadata payload. The document prefers API prompt graph
named inputs and uses a versioned widget-position map only for recognized UI
graph node types. The durable `workflow_properties` index converts the fixed
registry's scalar values into text, integer, real, boolean, or canonical uint64
rows. Links, arrays, objects, NaN/Infinity, oversized identifiers/text, and
unknown widget layouts are not indexed; internal workflow keys are stripped
from public metadata DTOs.

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
