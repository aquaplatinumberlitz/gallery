# Search Discovery Evolution Implementation Plan for OpenCode

Status: Proposed

Last reviewed: 2026-07-13

Owner: OpenCode

Priority: P2

Execution: Sequential and phase-gated

Depends on: every acceptance gate in
[Search Hardening](SEARCH_HARDENING_IMPLEMENTATION_PLAN.md)

Follow-up: [Semantic Search](SEARCH_SEMANTIC_IMPLEMENTATION_PLAN.md)

## Objective

Add the high-value discovery patterns identified in DiffusionToolkit and
Immich after lexical search is correct, stable, and covered by performance
gates.

This plan implements:

- a canonical structured Search V2 contract;
- shareable URL state and browser-local saved/recent searches;
- explicit search-index readiness and durable rebuild jobs;
- grouped positive/negative prompt discovery;
- observed model-name/model-hash identity;
- a typed, whitelisted ComfyUI node/property index;
- opt-in bounded raw workflow search.

The useful DiffusionToolkit lesson is its separation of residual text,
structured metadata, prompt groups, and workflow properties. The useful Immich
lesson is explicit capabilities, index readiness, rebuild state, and safe
feature degradation. Do not copy DT's dynamic SQL or `%LIKE%` primary engine,
and do not copy Immich's PostgreSQL/Redis/ML operational stack.

## Non-goals

- No semantic embeddings or image similarity in this plan.
- No arbitrary user-supplied SQL property names.
- No raw workflow search enabled by default.
- No server-global saved-search table without an authenticated owner model.
- No ratings, favorites, NSFW, delete flags, OCR, faces, or locations.
- No synchronous full-library backfill during application startup or migration.

## OpenCode execution rules

Apply all execution rules from the hardening plan. Additionally:

1. Verify the hardening plan is complete and archived before starting D0.
2. Keep legacy `GET /api/search`, `/api/search-metadata`, and `/api/facets`
   working as adapters while the frontend moves to Search V2.
3. Add only additive schema migrations. Use the next unused schema version if
   concurrent user work has already advanced it.
4. Rebuilds must use durable jobs; never use FastAPI `BackgroundTasks` for
   long-running index work.
5. Never log full prompts, raw workflows, local paths, or sidecar content in
   public status/error payloads.

## D0 - Canonical Search V2, URL state, and saved searches

**Goal:** Create one versioned search representation for API requests, query
keys, URLs, saved searches, and future semantic modes.

### Public request contract

Add `POST /api/search/query` with a regular Pydantic request model:

```json
{
  "schema_version": 1,
  "mode": "lexical",
  "text": "cat model:pony",
  "scope": {
    "kind": "folder",
    "library_id": 2,
    "import_path_id": 7,
    "relative_path": "portraits/2026"
  },
  "filters": {
    "prompt_groups": [],
    "workflow_groups": []
  },
  "cursor": null,
  "limit": 60
}
```

### Contract rules

- [ ] `schema_version` is exactly `1`.
- [ ] Initial modes are `lexical`, `workflow`, and `raw`.
- [ ] Scope is a discriminated union:
  - `folder`: requires library, import path, and case-preserved relative path;
  - `library`: requires library only;
  - `all`: has no path fields.
- [ ] The backend resolves folder scope from registered IDs. The canonical
      request never accepts an absolute path.
- [ ] `text` is at most 512 Unicode characters.
- [ ] Request body is at most 32 KiB after JSON decoding constraints.
- [ ] `limit` defaults to 60 and is bounded to 1-100.
- [ ] A persistable search removes `cursor` and `limit`.
- [ ] Every TanStack Query key contains the complete canonical request except cursor.
- [ ] Legacy GET search maps `current`/absolute path into the canonical model
      after authorization.

### Frontend state and URL codec

Use Vue Router query parameters on the existing gallery route:

| Parameter | Meaning |
| --- | --- |
| `search_v=1` | URL schema version |
| `q` | Canonical visible text query |
| `scope=folder\|library\|all` | Search scope |
| `library` | Registered library ID |
| `import` | Registered import-path ID |
| `path` | Case-preserved relative folder path |
| `mode=lexical\|workflow\|raw` | Search mode |
| `pg` | Bounded base64url JSON prompt-group filters |
| `wf` | Bounded base64url JSON workflow groups |

- [ ] Hydrate URL state once after libraries are available.
- [ ] Debounced typing uses `router.replace()`.
- [ ] Enter, drawer Apply, saved/recent selection, scope change, and mode change
      use `router.push()`.
- [ ] Back/Forward updates search state without writing the same state back.
- [ ] Invalid URL data is sanitized with one `replace()` and a safe fallback.
- [ ] Do not store cursor, drawer-open state, loading state, or absolute paths in URLs.

### Saved and recent searches

Use versioned browser `localStorage`, wrapped in error handling:

- [ ] Maximum 50 saved searches and 20 recent searches.
- [ ] Saved records contain ID, name, canonical request, created time, and updated time.
- [ ] Recent records are written only after a successful first page with at
      least one result.
- [ ] Dedupe by canonical semantic request key; do not lowercase paths/values.
- [ ] Support save, rename, delete, clear recent, schema migration, and corrupt
      storage fallback.
- [ ] Do not save an asset-reference/similar-image request when semantic support
      is added later.

### Acceptance gates

- [ ] URL copy/reload reproduces the same request.
- [ ] Back/Forward produces no request loop or duplicate request.
- [ ] A folder path's casing survives URL and localStorage round-trips.
- [ ] Legacy GET and Search V2 return equivalent lexical rows for equivalent input.

## D1 - Search capabilities and durable index lifecycle

**Goal:** Make derived search indexes observable, rebuildable, resumable, and
safe to disable independently.

### Additive schema

Create per-library state:

```text
search_index_states
- index_name TEXT
- library_id INTEGER REFERENCES libraries(id) ON DELETE CASCADE
- state TEXT                 # pending|building|ready|degraded|failed|disabled
- schema_version INTEGER
- extractor_version INTEGER
- indexed_count INTEGER
- target_count INTEGER
- failed_count INTEGER
- active_job_id INTEGER NULL
- started_at REAL NULL
- completed_at REAL NULL
- updated_at REAL
- error_code TEXT NULL
- error_summary TEXT NULL
PRIMARY KEY(index_name, library_id)
```

Create durable jobs:

```text
search_index_jobs
- id INTEGER PRIMARY KEY
- index_name TEXT
- library_id INTEGER REFERENCES libraries(id) ON DELETE CASCADE
- mode TEXT                  # missing|full
- state TEXT                 # queued|running|cancel_requested|cancelled|succeeded|failed|interrupted
- cursor_asset_id INTEGER NULL
- processed_count INTEGER
- target_count INTEGER
- failed_count INTEGER
- requested_at REAL
- started_at REAL NULL
- finished_at REAL NULL
- claimed_by TEXT NULL
- claim_token TEXT NULL
- lease_expires_at REAL NULL
- error_code TEXT NULL
- error_summary TEXT NULL
```

Track per-asset extraction:

```text
asset_search_extractions
- asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE
- index_name TEXT
- source_fingerprint TEXT
- extractor_version INTEGER
- status TEXT                # ready|not_applicable|skipped|failed
- error_code TEXT NULL
- indexed_at REAL
PRIMARY KEY(asset_id, index_name)
```

### Worker behavior

- [ ] One search-index writer runs by default to limit SQLite contention.
- [ ] Claim/lease/fencing behavior follows the existing durable worker patterns.
- [ ] Select work by `asset_id` keyset, not offset.
- [ ] Process at most 200 assets per batch and keep write transactions short.
- [ ] Parse/extract outside the write transaction; persist one asset's derived
      rows and extraction status atomically.
- [ ] On startup, stale running jobs become interrupted and resume from
      fingerprint/cursor state.
- [ ] `missing` is the default rebuild mode. `full` is manual.
- [ ] Duplicate active rebuilds for the same library/index return `409`.
- [ ] Migration creates tables/indexes only; it never performs the backfill inline.

### Public APIs

```text
GET  /api/search/capabilities
GET  /api/search/indexes?library_id=...
GET  /api/search/index-jobs/{job_id}
POST /api/search/indexes/{index_name}/rebuild
POST /api/search/index-jobs/{job_id}/cancel
```

Rebuild request:

```json
{
  "mode": "missing",
  "library_id": 2
}
```

### Capability/index semantics

- [ ] Capabilities advertise enabled modes, supported scopes, field limits,
      workflow registry, raw-search limits, and index requirements.
- [ ] Index status exposes `state` and a separate `usable` boolean.
- [ ] A stale/building old index may remain usable and show a warning.
- [ ] A required unusable index returns `503 SEARCH_INDEX_NOT_READY` with
      `Retry-After` where meaningful.
- [ ] A disabled feature returns `409 FEATURE_DISABLED`.
- [ ] Error summaries are sanitized and never include prompts/workflows/tracebacks.

### Acceptance gates

- [ ] Jobs resume after process interruption without duplicating derived rows.
- [ ] Claim fencing prevents an expired worker from completing a newer claim.
- [ ] Cancel is idempotent and does not leave state marked ready incorrectly.
- [ ] Lexical search remains usable while optional indexes rebuild or fail.

## D2 - Prompt usage and observed model identity

**Goal:** Add DT-style prompt/model discovery using normalized indexed data,
not full-text scans over every request.

### Prompt value schema

```text
asset_prompt_values
- id INTEGER PRIMARY KEY
- asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE
- kind TEXT                 # positive|negative
- display_text TEXT
- normalized_text TEXT
- search_text TEXT
- value_hash BLOB           # SHA-256
- extractor_version INTEGER
- source_fingerprint TEXT
UNIQUE(asset_id, kind)
```

Required indexes:

- `(kind, value_hash, asset_id)`
- `(kind, search_text, asset_id)`
- `(asset_id)`

Normalization is fixed:

1. Unicode NFKC.
2. Trim leading/trailing whitespace.
3. Collapse internal whitespace.
4. Casefold for `search_text`.
5. Hash `kind + NUL + search_text` with SHA-256.

Keep the original display text. Group identity uses the hash and normalized
search text. Use active catalog rows only.

### Prompt usage API

Add `POST /api/search/prompt-usage/query` with:

- polarity `positive|negative`;
- canonical scope;
- optional prefix/text query;
- `sort=usage|recent`;
- opaque keyset cursor;
- limit 1-100.

Response item:

```json
{
  "value_id": "base64url-sha256",
  "kind": "positive",
  "text": "masterpiece, portrait",
  "asset_count": 42,
  "last_asset_mtime_ns": 1760000000000000000,
  "sample_asset": {
    "asset_id": 123,
    "library_id": 2,
    "path": "/authorized/catalog/path.png"
  }
}
```

- [ ] Search V2 accepts exact prompt groups by `kind + value_id`.
- [ ] Prompt-group querying never places full prompt text in a URL cursor.
- [ ] Missing prompts are `not_applicable`, not failures.
- [ ] Backfill reads existing DB metadata and does not reopen media files.

### Observed model identity

Create an incrementally maintained model alias table from
`image_metadata.model`, `image_metadata.model_hash`, and checkpoint resources:

```text
model_identity_aliases
- normalized_name TEXT
- normalized_hash TEXT
- display_name TEXT
- display_hash TEXT
- asset_count INTEGER
- last_seen_mtime_ns INTEGER
PRIMARY KEY(normalized_name, normalized_hash)
```

- [ ] `model:` continues to match model names directly.
- [ ] Exact observed names may expand to all associated hashes.
- [ ] Ambiguous name-to-hash mappings remain explicit OR candidates; never pick
      one hash silently.
- [ ] `model_hash:` and `model_or_hash:` remain available.

### Acceptance gates

- [ ] Equivalent whitespace/case prompt values group together while display text remains useful.
- [ ] Positive and negative prompts with identical text remain different groups.
- [ ] Prompt usage first page and exact group filter meet the 300 ms lexical budget at 25,000 assets.
- [ ] Model alias expansion is deterministic and covered for ambiguous names.

## D3 - Typed ComfyUI node/property index

**Goal:** Add rich ComfyUI search without dynamic SQL, arbitrary property
names, or raw-workflow scans.

### Schema

```text
workflow_nodes
- id INTEGER PRIMARY KEY
- asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE
- node_key TEXT
- node_type TEXT
- title TEXT NULL
- extractor_version INTEGER
- source_fingerprint TEXT
UNIQUE(asset_id, node_key)
```

```text
workflow_property_values
- node_id INTEGER REFERENCES workflow_nodes(id) ON DELETE CASCADE
- property_key TEXT
- ordinal INTEGER DEFAULT 0
- value_type TEXT            # text|integer|real|boolean|uint64_token
- value_text TEXT NULL
- value_text_folded TEXT NULL
- value_integer INTEGER NULL
- value_real REAL NULL
- value_boolean INTEGER NULL
PRIMARY KEY(node_id, property_key, ordinal)
```

Add CHECK constraints so only the typed value column is populated. Add indexes
for node type/asset and for each typed `(property_key, value, node_id)` lookup.

### Code-owned registry v1

| Node type | Indexed properties |
| --- | --- |
| `KSampler` | seed, steps, cfg, sampler_name, scheduler, denoise |
| `KSamplerAdvanced` | noise_seed, steps, start_at_step, end_at_step, cfg, sampler_name, scheduler, add_noise, return_with_leftover_noise |
| `CheckpointLoaderSimple` | ckpt_name |
| `LoraLoader`, `LoraLoaderModelOnly` | lora_name, strength_model, strength_clip |
| `EmptyLatentImage` | width, height, batch_size |
| `VAELoader` | vae_name |
| `ControlNetLoader` | control_net_name |
| `UNETLoader` | unet_name, weight_dtype |
| `CLIPLoader`, `DualCLIPLoader` | clip_name, clip_name1, clip_name2, type |
| `SaveImage` | filename_prefix |

### Extraction limits

- Raw workflow/prompt source: 2 MiB maximum.
- Nodes: 2,048 maximum per asset.
- Indexed properties: 32 maximum per node.
- Property rows: 8,192 maximum per asset.
- Node/property identifiers: 128 characters maximum.
- Text property value: 512 characters maximum.
- Scalar primitives only; skip links, arrays, objects, NaN, and Infinity.
- Store unsigned seed/noise seed as canonical decimal `uint64_token`; equality only.

### Extraction flow

- [ ] Extend the Comfy parser to return a normalized internal workflow document
      together with existing metadata.
- [ ] Do not parse the workflow twice in extraction and persistence.
- [ ] Persist normalized metadata, workflow nodes/properties, and extraction
      state in the same asset transaction.
- [ ] API prompt graphs are authoritative for named inputs.
- [ ] UI graph widget positions require a versioned mapping; unknown widgets
      store node type/title only.
- [ ] Parse failure does not fail asset import. Mark the extraction failed and
      the index degraded.

### Search semantics

Workflow groups contain one node type and up to eight predicates. The request
contains at most four groups.

```json
{
  "node_type": "KSampler",
  "predicates": [
    {"property": "steps", "op": "gte", "value": 20},
    {"property": "cfg", "op": "lte", "value": 8.0}
  ]
}
```

- All predicates in one group must match the **same node**.
- Different groups are ANDed and may match different nodes.
- Text operators: `eq`, `prefix`, `contains`.
- Integer/real operators: `eq`, `gt`, `gte`, `lt`, `lte`.
- Boolean and uint64 token operator: `eq` only.
- Backend maps registry enums to fixed SQL and binds every value.

### Acceptance gates

- [ ] Same-asset predicates on different KSampler nodes do not incorrectly
      satisfy one same-node group.
- [ ] Unsupported node/property/operator combinations return field-specific 422 errors.
- [ ] Injection strings remain data and cannot become SQL identifiers.
- [ ] Property query plans use the appropriate typed indexes.
- [ ] Representative workflow queries remain at or below 300 ms on the
      25,000-asset/500,000-property fixture.

## D4 - Opt-in raw workflow search

**Goal:** Offer DT-style raw workflow discovery as a visibly expensive,
bounded, separately controlled feature.

### Configuration and schema

```text
GALLERY_SEARCH_WORKFLOW_RAW_ENABLED=false
GALLERY_SEARCH_WORKFLOW_RAW_MAX_DOCUMENT_BYTES=1048576
GALLERY_SEARCH_WORKFLOW_RAW_INDEX_BUDGET_BYTES=536870912
```

Create `workflow_raw_documents` plus an external-content FTS5 trigram table:

```text
workflow_raw_documents
- asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE
- library_id INTEGER
- canonical_text TEXT
- byte_length INTEGER
- source_fingerprint TEXT
- extractor_version INTEGER
```

### Required behavior

- [ ] Canonicalize supported JSON into compact UTF-8 before indexing.
- [ ] Skip documents over 1 MiB; do not truncate silently.
- [ ] Stop adding documents when the configured index budget is reached and
      report skipped counts as degraded status.
- [ ] Use trigram FTS literal search; never `%LIKE%` over raw JSON.
- [ ] Query length is 3-128 characters, limit is at most 50, and scope is required.
- [ ] Use a dedicated SQLite read connection with a 250 ms progress-handler deadline.
- [ ] Timeout returns a typed error, never partial results presented as complete.
- [ ] Add `POST /api/search/workflow/raw`; include warning/capability metadata
      in the response.
- [ ] Keep the feature absent from normal UI when disabled or unsupported.
- [ ] Deprecate the old `raw:` fielded alias. When enabled it may redirect into
      the bounded raw mode; when disabled it returns a clear validation error.
- [ ] Restrict `param:`/`advanced:` keys to a documented identifier grammar and
      bind JSON paths/values as parameters.

### Acceptance gates

- [ ] Disabled or unavailable raw search does not prevent application startup.
- [ ] Oversized documents and total-budget overflow are visible in index status.
- [ ] Malicious/control-character terms are rejected.
- [ ] Raw workflow p95 is at most 500 ms on the bounded fixture and every query
      terminates within its deadline.

## D5 - Vue discovery surfaces

**Goal:** Add the new capabilities without turning `App.vue`, headers,
`GalleryGrid.vue`, or the Advanced Search drawer into larger multi-purpose
components.

### Component map

| Component/composable | Single responsibility |
| --- | --- |
| `SearchLibraryPopover.vue` | Saved/recent list, save, rename, delete, clear |
| `PromptUsagePanel.vue` | Positive/negative grouped prompts and show-assets action |
| `WorkflowFilterBuilder.vue` | Typed node/property predicate rows from capabilities |
| `RawWorkflowSearch.vue` | Explicit opt-in, warning, term validation, Apply-only execution |
| `SearchIndexStatusPanel.vue` | Readiness, progress, failures, rebuild, cancel |
| `useSearchUrlSync.ts` | Vue Router encode/decode/push/replace loop prevention |
| `useSavedSearches.ts` | Versioned localStorage and bounded actions |
| `usePromptUsageQuery.ts` | Prompt-group server state and cursor pagination |
| `useSearchIndexStatusQuery.ts` | Status polling only while building or panel is open |

### Data-flow rules

- [ ] Root/layout components remain composition surfaces.
- [ ] Presentational children use typed props down and events up.
- [ ] Drawer sections keep local drafts and emit an applied canonical request.
- [ ] TanStack Query owns capabilities, prompt groups, facets, jobs, and index status.
- [ ] Pinia owns the current search session and UI preferences only.
- [ ] Computed getters remain pure; router/localStorage writes happen in explicit
      actions or watchers with loop guards.
- [ ] New primitive local state uses `shallowRef()`.
- [ ] All SFCs use `<script setup lang="ts">`, PascalCase filenames, declarative
      templates, scoped class selectors, and `useTemplateRef()` where DOM access
      is required.

### UX rules

- Prompt panel has positive/negative tabs, usage count, sample thumbnail, copy,
  and `Show assets`.
- Workflow builder exposes only advertised nodes, properties, types, and operators.
- Backend 422 details map to the exact predicate row.
- Raw search requires an explicit enable/acknowledgement and does not run while typing.
- Index status distinguishes ready, usable-stale, building, degraded, failed,
  unavailable, and disabled.
- Rebuild requires confirmation and prevents duplicate submit.

### Acceptance gates

- [ ] Saved/recent searches survive reload and corrupted storage fails safely.
- [ ] Prompt group selection creates the expected canonical filter.
- [ ] Workflow controls cannot produce an unsupported request.
- [ ] Raw search remains hidden/disabled when capability is false.
- [ ] Desktop, tablet, and mobile expose equivalent behavior and keyboard labels.

## D6 - Test, performance, and documentation gates

### Backend coverage

- Migration creation, rollback, foreign-key checks, and no synchronous backfill.
- Durable claim/lease/resume/cancel/coalescing behavior.
- Prompt normalization, hashing, grouping, cursor stability, and scope filtering.
- Model alias ambiguity and incremental updates/deletes.
- Every registry node/property/type/operator and extraction limit.
- Same-node workflow semantics and SQL-injection attempts.
- Raw feature flags, FTS capability, size/budget/deadline enforcement.
- Search V2 validation, compatibility adapter parity, and response models.

### Frontend coverage

- URL encode/decode and push/replace/popstate loop prevention.
- Saved/recent limits, migration, dedupe, rename/delete, and corrupt storage.
- Prompt usage loading/error/empty/paging/show-assets behavior.
- Workflow registry rendering and field-specific validation.
- Index usable/stale/building/degraded/failed/rebuild/cancel states.
- Raw warning, acknowledgement, Apply-only behavior, and timeout errors.

### Managed E2E scenarios

- Share/reload/back-forward a mixed text and fielded search.
- Save, rerun, rename, and delete a query.
- Browse positive and negative prompt groups and show their assets.
- Apply two predicates to the same Comfy node.
- Run raw workflow search only after explicit acknowledgement.
- Rebuild an index through success, failure, and cancellation fixtures.
- Confirm responsive and accessible parity across desktop, tablet, and mobile.

### Final gates

```bash
./test.sh backend-api
./test.sh lint
./test.sh e2e
./test.sh perf
./test.sh docs
./test.sh fast
```

## Completion criteria

- Search V2 is the active frontend contract while legacy GET remains compatible.
- Search state is shareable and browser Back/Forward safe.
- Saved/recent searches are bounded and browser-local.
- Prompt grouping and model aliases are indexed and paginated.
- Typed ComfyUI queries use a fixed registry and same-node semantics.
- Raw workflow search is implemented, bounded, warned, and disabled by default.
- Search index readiness/rebuild state is explicit and durable.

When complete, move this file to `docs/archived/`, update the plans index, and
only then start the semantic plan.

## Execution log

| Date | Phase | Result | Evidence |
| --- | --- | --- | --- |
| - | - | Not started | - |
