# DiffusionToolkit Metadata Search Analysis

Last reviewed: 2026-06-09

## Purpose

This document analyzes DiffusionToolkit's metadata search logic and identifies
which ideas should be borrowed for gallery-repo.

It focuses on query parsing, metadata facets, ComfyUI node/property search, raw
workflow search, prompt grouping, and how those ideas fit the current
FastAPI/Vue search pipeline.

## Sources inspected

| Repo | Files |
| --- | --- |
| DiffusionToolkit at `153409c3a0e9569886e6601530365808d4ecbb0e` | [`QueryBuilder.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/QueryBuilder.cs), [`QueryCombiner.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/QueryCombiner.cs), [`ComfyUIQueryBuilder.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/ComfyUIQueryBuilder.cs), [`DataStore.Search.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/DataStore.Search.cs), [`DataStore.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/DataStore.cs), [`Models/Image.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/Models/Image.cs), [`Models/Node.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/Models/Node.cs), [`Models/NodeProperty.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/Models/NodeProperty.cs), [`CSVParser.cs`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Database/CSVParser.cs), [`Tips.md`](https://github.com/RupertAvery/DiffusionToolkit/blob/153409c3a0e9569886e6601530365808d4ecbb0e/Diffusion.Toolkit/Tips.md) |
| gallery-repo | [`backend/search.py`](../../backend/search.py), [`backend/metadata_store.py`](../../backend/metadata_store.py), [`frontend/src/composables/useUnifiedSearchQuery.ts`](../../frontend/src/composables/useUnifiedSearchQuery.ts), [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) |

## Current gallery-repo search

gallery-repo exposes two search endpoints:

- `GET /api/search`: active frontend search. It returns grouped Albums, Photos,
  and Prompt sections.
- `GET /api/search-metadata`: legacy metadata-only search. The frontend no
  longer uses it for main gallery search.

Current behavior:

1. Frontend debounces search input by 300 ms.
2. `GET /api/search` passes query, scope, current path, and limit.
3. Album/photo filename search uses `file_index_fts`.
4. Prompt search uses `image_metadata_fts` or `image_metadata_fts_trigram`.
5. CJK queries use trigram FTS when length is at least three characters.
6. FTS failures or misses fall back to `LIKE`.
7. Prompt matches are scope-filtered by joining `image_metadata` to
   `file_index`.
8. API output is path-safety filtered and stale rows trigger stale-index
   cleanup.

Strengths:

- Good default text search with SQLite FTS5 and BM25 ordering.
- CJK substring handling through trigram FTS.
- Web-safe path checks and current-folder/all-indexed scoping.
- Grouped search results match the existing gallery UX.
- Backend search is simple and predictable.

Current gaps:

- No fielded metadata query language, so users cannot search precisely by
  `seed:`, `steps:`, `cfg:`, `sampler:`, `model:`, or negative prompt.
- Structured fields already present in `image_metadata` are not exposed as
  filters in the unified search box.
- The query parser cannot split residual prompt text from structured metadata
  filters.
- There is no prompt usage/grouping view.
- ComfyUI node/property values are not indexed separately.
- Raw workflow search is not available as an explicit opt-in mode.

## DiffusionToolkit search architecture

DiffusionToolkit treats metadata search as a small query language over a rich
SQLite schema.

### Schema support

`Image` rows store structured generation fields:

- prompt, negative prompt
- steps, sampler, CFG scale, seed
- width, height
- model hash, model name
- batch data
- aesthetic score
- hypernetwork and strength
- clip skip, ENSD
- file size, hash, image/video type
- workflow and workflow ID
- user-owned flags such as rating, favorite, delete, NSFW, unavailable

`Node` and `NodeProperty` tables store ComfyUI nodes and scalar input values.
DiffusionToolkit indexes many of these columns individually, including prompt,
negative prompt, model, model hash, seed, sampler, width, height, CFG scale,
steps, workflow, node name, and node property name/value.

### Query parsing

`QueryBuilder.ParseParameters()` removes recognized field tokens from the query
string and turns them into SQL predicates. The remaining text becomes the prompt
query.

Recognized token families include:

| Token family | Behavior |
| --- | --- |
| `seed:` | Exact seed, numeric range, or wildcard prefix pattern. |
| `steps:` | One or more step counts, OR-ed. |
| `sampler:` | Matches known sampler names, including multi-word names. |
| `cfg:`, `cfg_scale:`, `cfg scale:` | Numeric CFG equality, with pipe-separated OR values. |
| `size:` | Exact dimensions, wildcard width/height, orientation, or aspect ratio. |
| `model_hash:`, `model hash:` | Case-insensitive hash equality, with OR values. |
| `model:` | Model name search, plus hash lookup when DT has model cache data. |
| `model_or_hash:` | Exact model name or hash branch. |
| `negative prompt:`, `negative_prompt:`, `negative:` | Negative prompt text search. |
| `aesthetic_score:` | Numeric comparison with `=`, `<`, `>`, `<=`, `>=`, or `<>`. |
| `hypernet:` and `hypernet strength:` | Hypernetwork name and strength filters. |
| `path:`, `folder:`, `album:` | Location and album predicates. |
| `date:` | Created-date predicates. |
| `type:` | Image/video filter. |
| `favorite:`, `rating:`, `delete:`, `nsfw:`, `nometa:` | DT-specific user metadata filters. |

Prompt text uses `CSVParser.Parse()`: comma-separated tokens are AND-ed, and
quoted text preserves commas as one token.

Example intent:

```text
girl, rain steps: 30 cfg: 7 seed: 123* negative: watermark, blurry
```

DT interprets this as:

- prompt contains `girl`
- prompt contains `rain`
- steps equals `30`
- CFG equals `7`
- seed starts with `123`
- negative prompt contains `watermark`
- negative prompt contains `blurry`

### Query composition

`QueryCombiner.Parse()` composes three result sets:

1. Structured metadata predicates from `ParseParameters()`.
2. Prompt/negative prompt text predicates from `QueryBuilder.Parse()`.
3. Optional raw workflow and ComfyUI node/property searches.

It then combines them roughly as:

```text
(prompt search UNION raw workflow search UNION ComfyUI property search)
INTERSECT
(structured metadata filters)
INTERSECT
(view/album/tag/model/folder filters)
```

This is the most useful design idea in DT: text search and structured metadata
filters are separate, then combined by image ID.

### ComfyUI search

`ComfyUIQueryBuilder.Parse()` searches `NodeProperty.Value` for residual prompt
tokens. If `SearchNodes` is enabled, it limits matching to configured property
names. If `SearchAllProperties` is enabled, it searches all node properties.

Filter UI can also add explicit node property filters:

- contains
- starts with
- ends with
- equals

Property names can use `*` as a wildcard.

### Raw workflow search

When `SearchRawData` is enabled, DT searches the raw `Workflow` text with
`LIKE`. The UI labels this as potentially slow. That warning is correct; raw
JSON/workflow search can be expensive and noisy.

### Prompt usage view

`SearchPrompts()` and `SearchNegativePrompts()` group unique prompt strings and
return usage counts. They support:

- empty query: list prompts by usage
- normal query: reuse prompt parser and group matches
- full text mode: exact full-prompt match
- optional Hamming-distance similarity over cached prompt groups

This is a library-management feature, not a lightbox feature.

## What gallery-repo should borrow

| Priority | Idea | gallery-repo application | Acceptance criteria |
| --- | --- | --- | --- |
| P1 | Split query into residual text plus structured facets | Parse supported metadata tokens, remove them from the text query, keep the remaining text in current FTS search. | `cat seed:123 steps:20` searches prompt text for `cat` and filters metadata rows by seed and steps. |
| P1 | Keep FTS as the default prompt engine | Use current `image_metadata_fts` and trigram FTS for residual text; add SQL predicates only for structured fields. | Existing text search relevance and CJK behavior remain unchanged for plain queries. |
| P1 | Fielded filters over existing columns | Support `seed:`, `steps:`, `cfg:`, `sampler:`, `model:`, `negative:` and `size:` using current `image_metadata` fields. | Exact/range/wildcard fixtures pass; scoped `current` search still works. |
| P1 | Quoted/comma token helper | Add a small tested tokenizer for field values and prompt phrases. | `model:"Realistic Vision"` and prompt text with commas parse predictably. |
| P1 | Query parser tests | Add backend tests for plain text, CJK text, field filters, malformed filters, scope filtering, and fallback behavior. | Parser and SQL builder tests run without image fixtures where possible. |
| P2 | Model hash and richer columns | Add `model_hash`, `tool`, `scheduler`, and maybe `lora_text` columns after parser unification. | Field filters can query data that is currently only present inside `metadata_json`. |
| P2 | Prompt usage endpoint | Add a dedicated endpoint for grouped prompt/negative prompt counts, separate from gallery search. | It returns prompt, usage count, and sample image path with pagination. |
| P2 | Optional raw workflow search | Add explicit `raw:` or settings-gated raw metadata search, never default. | Raw workflow search is opt-in and bounded by limit/scope. |
| P2 | ComfyUI node/property index | Store compact node property rows or a flattened searchable node summary after parser unification. | `node:`/`property:` filters work for ComfyUI samples without bloating normal responses. |
| P3 | Saved searches | Store recent/saved search strings client-side or in a local backend table. | Users can rerun complex metadata queries without retyping them. |

## Things not to copy

| DT behavior | Why not copy directly |
| --- | --- |
| Prompt text search through `%LIKE%` as the primary path | gallery-repo already has FTS5 relevance, CJK trigram support, and better fallback behavior. |
| UI-owned filters such as favorite/rating/delete/NSFW before those concepts exist in gallery-repo | They would add schema and UX scope unrelated to metadata search. |
| Raw workflow search enabled by default | Large ComfyUI workflows can make it slow and noisy. |
| Dynamic SQL for user-supplied node property names without a whitelist/parameterized design | Node/property search must avoid SQL injection and unbounded table scans. |
| Hamming-distance scan over all prompts as an initial feature | It is memory-heavy and less useful than exact/grouped prompt counts for this app. |
| Absolute Windows path syntax and folder assumptions | gallery-repo must keep current `GALLERY_ROOT` path safety and current/all scope behavior. |
| Prompt-first syntax requirement | DT recommends prompt text before parameters; gallery-repo can design a clearer parser that recognizes field tokens anywhere when values are quoted or unambiguous. |

## Proposed syntax for gallery-repo

Start small:

```text
portrait rain seed:123 steps:30 cfg:7 sampler:"Euler a" model:"realistic*" negative:"watermark, blurry" size:1024x?
```

Initial fields:

| Field | Behavior |
| --- | --- |
| `seed:` | Exact string match; `*` wildcard maps to `LIKE`; numeric range can come later. |
| `steps:` | Integer equality; pipe-separated OR values can come later. |
| `cfg:` | Float equality initially; comparison operators can come later. |
| `sampler:` | Case-insensitive exact or wildcard match. |
| `model:` | Case-insensitive exact or wildcard match over `model`. |
| `negative:` | FTS/LIKE against negative prompt only. |
| `size:` | `WIDTHxHEIGHT`, `WIDTHx?`, `?xHEIGHT`, `portrait`, `landscape`, or `square`. |

Parsing rule:

1. Scan for `field:value` tokens with quoted-value support.
2. Remove recognized field tokens from the query.
3. Treat the remaining text as the normal FTS query.
4. Combine residual text and structured predicates with `AND`.
5. Keep current `scope=current/all` path filtering unchanged.
6. On malformed filters, ignore the malformed token as text or return a clear
   400 only after the UI can show that error well.

## Suggested implementation tasks

| Task | Files likely affected | Risk | Test plan |
| --- | --- | --- | --- |
| Add metadata query parser | New backend parser module, `backend/metadata_store.py`, `backend/search.py` | Medium | Unit tests for tokenization, quoted values, malformed filters, plain text compatibility. |
| Add SQL predicate builder | `backend/metadata_store.py` | Medium | SQL builder tests with in-memory SQLite fixtures. |
| Integrate facets into `/api/search` prompt section | `backend/metadata_store.py`, maybe response types only if exposing parsed filters | Medium | Existing search tests plus scope/current folder tests. |
| Keep `/api/search-metadata` compatible | `backend/metadata_store.py` | Low | Legacy endpoint still returns old shape for plain queries. |
| Add prompt usage endpoint | New route or `search.py` | Low-medium | Group-by tests and pagination tests. |
| Add richer metadata columns | `backend/metadata_parse.py`, `backend/metadata_extract.py`, `backend/metadata_store.py` | Medium | Parser fixtures and migration/backfill tests. |
| Add ComfyUI node/property search | Parser/index schema plus search builder | High | ComfyUI fixture tests and performance checks. |

## Recommended order

1. Finish parser unification from
   [DiffusionToolkit Metadata Parse Analysis](DIFFUSIONTOOLKIT_METADATA_PARSE_ANALYSIS.md).
2. Add query parser tests with plain search compatibility locked down.
3. Implement fielded search for existing columns only.
4. Add richer columns such as `model_hash`, `tool`, scheduler, and LoRA text.
5. Add prompt usage/grouping endpoint.
6. Add raw workflow and ComfyUI node/property search as explicit opt-in features.

The best DT idea to borrow is not its exact SQL. The best idea is the split
between residual prompt text and structured metadata predicates, then combining
the result sets while preserving a simple search box.
