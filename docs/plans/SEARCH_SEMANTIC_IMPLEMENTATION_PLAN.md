# Semantic Search Implementation Plan for OpenCode

Status: Proposed

Last reviewed: 2026-07-13

Owner: OpenCode

Priority: P3 optional capability

Execution: Sequential and phase-gated

Depends on:

- every gate in [Search Hardening](SEARCH_HARDENING_IMPLEMENTATION_PLAN.md);
- the Search V2 and index-lifecycle foundation in
  [Search Discovery Evolution](SEARCH_DISCOVERY_EVOLUTION_IMPLEMENTATION_PLAN.md).

## Objective

Implement optional local semantic text search, indexed image similarity, and
experimental lexical/semantic hybrid ranking without making ML a requirement
for normal gallery operation.

Defaults selected for this project:

- lexical search remains the default and works with no ML dependencies;
- semantic support runs in an optional loopback-only sidecar process;
- target scale is up to 100,000 indexed image assets;
- the reference deployment is the current Linux ARM64, 4-CPU, no-NVIDIA host;
- model files are supplied locally and verified by checksum;
- semantic, similar-image, and hybrid modes are disabled by default;
- saved/recent search persistence remains browser-local in the discovery plan.

The plan borrows Immich's explicit model/index lifecycle and image/text
embedding concepts. It does not copy Immich's PostgreSQL vector extension,
Redis/BullMQ, OCR, face recognition, or multi-service deployment model.

## Non-goals

- No automatic model download or outbound inference request.
- No user-uploaded query image in v1.
- No video embeddings in v1.
- No OCR, faces, people, duplicate detection, or location search.
- No semantic fallback that silently changes lexical relevance.
- No requirement to install optional dependencies when semantic search is off.
- No raw cosine/BM25 arithmetic for hybrid ranking.

## OpenCode execution rules

1. Verify the predecessor plans are complete before starting S0.
2. Keep the main backend healthy when the sidecar, model, sqlite-vec extension,
   or optional Python packages are absent.
3. Never expose the sidecar through nginx or bind it to a public interface by default.
4. Never send an unvalidated filesystem path to the sidecar.
5. Do not infer an embedding synchronously from an asset during a user search.
   Missing asset embeddings return a clear state and are filled by durable jobs.
6. Keep model ID, dimensions, preprocessing, and checksums versioned. A model
   change always requires a semantic rebuild.
7. Stop if supported ARM64 packages or the pinned model cannot be reproduced
   without adding an external hosted service.

## S0 - Optional dependency and sidecar boundary

**Goal:** Isolate ML memory, inference, and failure modes from the primary
FastAPI process.

### Optional dependencies

Add a separate pinned requirements file or install extra for:

- ONNX Runtime CPU;
- Hugging Face `tokenizers` or the smallest compatible tokenizer runtime;
- NumPy;
- sqlite-vec.

Do not add these packages to the normal `backend/requirements.txt` install.
Update [Third-Party Libraries](../THIRD_PARTY_LIBRARIES.md) with their optional
roles and failure behavior.

### Configuration

```text
GALLERY_SEARCH_SEMANTIC_ENABLED=false
GALLERY_SEARCH_HYBRID_ENABLED=false
GALLERY_SEARCH_ML_URL=http://127.0.0.1:4703
GALLERY_SEARCH_ML_TOKEN=
GALLERY_SEARCH_ML_MODEL_DIR=
GALLERY_SEARCH_ML_MODEL_ID=ViT-B-32__openai
GALLERY_SEARCH_ML_QUEUE_LIMIT=32
GALLERY_SEARCH_ML_TIMEOUT_SECONDS=30
GALLERY_SEARCH_SEMANTIC_VECTOR_DB=
GALLERY_SEARCH_SEMANTIC_INDEX_WORKERS=1
```

- [ ] Empty/missing token or model directory means semantic capability is unavailable.
- [ ] Start scripts launch the sidecar only when semantic support is explicitly enabled.
- [ ] Production documentation describes running the sidecar separately on loopback.
- [ ] Nginx configuration remains unchanged; port 4703 is not proxied.

### Pinned model bundle

Support one v1 manifest for `ViT-B-32__openai`, 512 dimensions. The local
bundle contains:

- text encoder ONNX;
- vision encoder ONNX;
- tokenizer vocabulary/configuration;
- image preprocessing configuration;
- model ID, embedding dimension, normalization policy, and file SHA-256 values.

Required behavior:

- [ ] Validate every checksum before loading the model.
- [ ] Reject unknown model IDs, dimensions, tokenizer configuration, or
      preprocessing manifests.
- [ ] Never download missing files automatically.
- [ ] Normalize every output vector to unit length before returning it.
- [ ] A checksum mismatch fails closed and leaves lexical search healthy.

### Internal sidecar API

The sidecar is a small typed FastAPI application with explicit return models,
`Annotated` parameters/dependencies, and one operation per route:

```text
GET  /health
POST /v1/embed/text
POST /v1/embed/image
```

Health response includes model ID, dimension, provider, ready state, and queue
depth without paths or secrets.

Text request constraints:

- 1-16 texts;
- each text 1-256 Unicode characters;
- bounded body size.

Image request constraints:

- 1-8 validated image payloads;
- bounded request and per-image bytes;
- no filesystem path field;
- Pillow decompression-bomb and dimension limits remain enforced.

The main backend validates catalog ownership and reads/resizes source images in
background index work, then sends bytes to the sidecar. It never passes a
client-provided path through.

### Inference scheduling

- [ ] Use one inference worker on the ARM64 CPU reference by default.
- [ ] Maintain bounded interactive-text and background-image queues.
- [ ] Interactive text requests have priority over background indexing.
- [ ] Queue overflow returns `429` with retry guidance.
- [ ] Sidecar timeouts/unavailability map to semantic capability errors, not a
      generic lexical-search failure.

### Acceptance gates

- [ ] Normal backend starts and passes tests with no optional packages installed.
- [ ] Enabled configuration with a missing/invalid model reports capability unavailable.
- [ ] Sidecar rejects missing/invalid bearer token.
- [ ] No sidecar endpoint accepts a filesystem path.
- [ ] Model checksum failure is covered and produces no outbound request.

## S1 - Semantic storage and durable indexing

**Goal:** Persist embeddings safely, expose coverage, and rebuild them through
the discovery plan's durable index lifecycle.

### Core schema

Create the model state table:

```text
semantic_model_states
- model_id TEXT PRIMARY KEY
- manifest_sha256 TEXT
- dimension INTEGER
- preprocessing_version INTEGER
- activated_at REAL
- updated_at REAL
```

Store the authoritative embedding in a regular SQLite table:

```text
semantic_embeddings
- asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE
- library_id INTEGER REFERENCES libraries(id) ON DELETE CASCADE
- model_id TEXT
- source_mtime_ns INTEGER
- source_size INTEGER
- embedding BLOB             # normalized little-endian float32[512]
- indexed_at REAL
```

Indexes:

- `(library_id, model_id, asset_id)`
- `(model_id, indexed_at)`

The BLOB table is the durable source of truth and exact-scoring fallback.

### sqlite-vec acceleration

Keep sqlite-vec in a dedicated derived database, separate from the primary
catalog/metadata database. `GALLERY_SEARCH_SEMANTIC_VECTOR_DB` defaults to a
cache/application-state path such as `backend/.cache/semantic_vectors.db` when
semantic support is enabled.

The derived database contains:

- a manifest table with schema version, model identity, dimension, and build time;
- a lazy `vec0` table keyed by `asset_id` with float32 embeddings and library
  partition metadata where supported by the pinned sqlite-vec version.

Rules:

- [ ] Extension/database creation happens only when semantic support is enabled.
- [ ] Normal catalog connections never load sqlite-vec and never require the
      optional module to read or migrate the main database.
- [ ] sqlite-vec failure marks semantic capability unsupported; it never fails
      the core schema migration or lexical startup.
- [ ] Write the authoritative BLOB first, then update the derived vector row.
- [ ] A derived-write failure retains the BLOB, marks the semantic index
      degraded, and queues repair.
- [ ] Integrity checks compare model identity, dimensions, row counts, and asset IDs.
- [ ] Rebuild into a temporary vector database, validate it, then atomically
      replace the active derived database.
- [ ] The derived vector database is disposable and is not required in catalog backups.

### Fingerprint and lifecycle

The semantic source fingerprint includes:

- active asset ID;
- source `mtime_ns` and size;
- model ID;
- manifest SHA-256;
- preprocessing version.

Use the discovery plan's `search_index_states`, `search_index_jobs`, and
`asset_search_extractions` with `index_name=semantic`.

- [ ] A model/manifest/preprocessing change invalidates all previous semantic rows.
- [ ] Missing-image rebuild is the default; full rebuild is manual or required
      after model change.
- [ ] Backfill uses active image assets only and skips videos.
- [ ] Unsupported/corrupt images are counted as skipped/failed without failing
      catalog or metadata import.
- [ ] Delete/offline/catalog replacement removes or invalidates semantic rows.
- [ ] Background concurrency defaults to one and yields between batches.
- [ ] No search request reads or embeds an original image to repair coverage.

### Scoped scoring strategy

Use this fixed decision policy:

1. For `all` or whole-library scope without complex filters, use sqlite-vec KNN
   and library partition filtering where available.
2. For folder or complex metadata/workflow filters, obtain eligible asset IDs
   from normal SQLite first.
3. If the eligible set is at most 20,000, load its BLOB embeddings in bounded
   chunks and score exact cosine similarity with NumPy.
4. For larger eligible sets, use adaptive vec0 overfetch, filter by eligible
   IDs, and increase K until the requested result count is satisfied.
5. If overfetch cannot prove a complete top-K within its bound, fall back to
   exact scoped BLOB scoring rather than returning an incorrectly ranked page.

This policy prioritizes correctness and supports the declared 100,000-asset
target without requiring PostgreSQL or a separate vector database.

### Acceptance gates

- [ ] Job interruption/resume produces one current embedding per active asset.
- [ ] Model change makes old rows unusable and queues a rebuild.
- [ ] Deleted/offline/replaced assets cannot appear through stale vectors.
- [ ] Exact scoped scoring and accelerated all/library scoring return the same
      ordering on deterministic fixtures.
- [ ] Corrupt/missing derived vector state rebuilds from durable BLOB embeddings.

## S2 - Semantic and similar-image public search

**Goal:** Extend Search V2 with explicit semantic modes and no silent fallback.

### Search V2 mode extension

Extend `POST /api/search/query` modes to:

```text
lexical | workflow | raw | semantic | hybrid | similar
```

Validation:

- `semantic`: requires non-empty text, no reference asset.
- `hybrid`: requires non-empty text, no reference asset.
- `similar`: requires `reference_asset_id`, and text/field filters are cleared
  unless explicitly documented as supported.
- Semantic text is at most 256 characters.
- Result limit is at most 100.
- Semantic/hybrid/similar return one bounded top-K page with
  `next_cursor=null` and `has_more=false` in v1.

### Reference-image behavior

- [ ] Reference must be an active image asset visible in the requested scope.
- [ ] Use only an existing indexed embedding.
- [ ] Exclude the reference asset from its own results.
- [ ] Missing embedding returns `409 REFERENCE_NOT_INDEXED` with index-status context.
- [ ] Unsupported video or unavailable asset returns the existing typed error.
- [ ] Do not add an upload or arbitrary-path API.

### Response additions

At response level:

- `search_mode`;
- `semantic_model_id` when relevant;
- semantic index coverage ratio/counts;
- semantic index usable/degraded state.

At result level, add nullable fields:

- `similarity_score` in a documented 0-1 cosine-similarity range;
- `semantic_rank`;
- `lexical_rank`;
- `fusion_rank`.

Do not expose raw vectors.

### Error policy

| Condition | Status |
| --- | ---: |
| Feature disabled | 409 |
| Reference asset has no embedding | 409 |
| Sidecar queue full | 429 |
| Semantic index unusable/not ready | 503 |
| Sidecar unavailable/timed out | 503 |
| Invalid mode/input combination | 422 |

No semantic error may be converted silently into lexical results. The UI may
offer an explicit `Search lexically` action.

### Acceptance gates

- [ ] Text and asset modes use the same model ID and normalized vector space.
- [ ] Scope and active-asset filters apply before final output.
- [ ] The reference asset never appears in similar results.
- [ ] Disabled/unready/degraded states produce the documented capability/error behavior.
- [ ] Response models and OpenAPI include all semantic fields and errors.

## S3 - Experimental hybrid ranking

**Goal:** Combine lexical precision and semantic recall without comparing
incompatible raw score scales.

### Fixed fusion policy

- Retrieve the top 200 lexical candidates using the hardening plan's ordering.
- Retrieve the top 200 semantic candidates using cosine similarity.
- Fuse by Reciprocal Rank Fusion:

```text
RRF score = sum(1 / (60 + source_rank))
```

- Deduplicate by `library_id + asset_id` before final ordering.
- Order equal RRF values by best lexical rank, best semantic rank, then stable
  `asset_id`.
- Return the top requested limit only.
- Never add raw BM25 values to cosine similarity.

### Enablement gate

Implement hybrid mode behind `GALLERY_SEARCH_HYBRID_ENABLED=false`. Enable it
only when a versioned relevance fixture demonstrates:

- at least 10% NDCG@10 improvement over lexical-only for the semantic-intent set;
- no regression in exact-filename expected-first cases;
- no cross-library/scope leakage;
- latency within the semantic endpoint budget.

If the gate fails, keep the code and capability disabled and record evidence.

### Acceptance gates

- [ ] RRF fixtures match hand-calculated expected order.
- [ ] Assets present in both sources appear once.
- [ ] Exact filename guard cases remain first.
- [ ] Semantic outage makes hybrid unavailable rather than silently changing mode.

## S4 - Vue semantic and similar-image UX

**Goal:** Expose optional modes only when capabilities and usable indexes
support them.

### Component map

| Component/composable | Single responsibility |
| --- | --- |
| `SearchModeSelect.vue` | Lexical, Semantic, and Hybrid mode selection |
| `ReferenceImageChip.vue` | Similar-image reference preview/context and clear action |
| `SearchIndexStatusPanel.vue` extension | Semantic model, coverage, queue, rebuild, failures |
| `useSearchCapabilitiesQuery.ts` | Long-lived capability state |
| `useSemanticSearchState.ts` | Mode/reference validation and explicit actions |

Existing `SearchResultsPanel.vue` and `SearchResultMetadata.vue` render semantic
results; do not add a second result grid.

### Required behavior

- [ ] Before capabilities load, render only lexical mode to avoid dead-control flash.
- [ ] Show Semantic/Hybrid only when the backend advertises support.
- [ ] Disable unavailable modes with a reason and link/action to index status.
- [ ] Metadata/lexical remains the default after reload unless the URL explicitly
      requests an available semantic mode.
- [ ] A media-card overflow action offers `Find similar` only for indexed image assets.
- [ ] `Find similar` creates a `similar` Search V2 request, keeps scope, clears
      incompatible text/filters, and shows the reference chip.
- [ ] Clearing the reference restores the prior lexical session when available.
- [ ] Similar searches are not saved to saved-search storage.
- [ ] Semantic errors preserve any successful prior data and offer retry or an
      explicit lexical action.
- [ ] Result metadata displays similarity as a restrained relevance indicator,
      not a misleading probability.

### Vue implementation rules

- Use `<script setup lang="ts">`, typed props/emits, and PascalCase SFCs.
- Keep route/root components as composition surfaces.
- Use TanStack Query for capabilities, index status, results, and mutations.
- Keep computed getters pure and use watchers only for URL or other side effects.
- Use `shallowRef()` for new primitive local state.
- Keep snippets/labels escaped through normal Vue interpolation; no `v-html`.
- Reuse the canonical Search V2 URL codec from the discovery plan. Extend
  `mode` with `semantic|hybrid|similar` and `ref` with the asset ID.

### Acceptance gates

- [ ] Semantic controls are absent when the feature is not installed.
- [ ] Unready/building/degraded/failed states render accurately.
- [ ] Find Similar sets and clears the correct reference.
- [ ] Reload/back-forward reproduces available semantic modes safely.
- [ ] Desktop, tablet, mobile, keyboard, and screen-reader behavior are equivalent.

## S5 - Performance, reliability, and documentation gates

### Deterministic performance fixtures

Add a generated 100,000-vector fixture using a fixed seed. It must not require
the real ONNX model and must include:

- known nearest neighbors;
- multiple libraries;
- narrow folder scopes;
- inactive/deleted assets;
- equal-distance ties;
- metadata/workflow filters;
- a corrupt/missing accelerated-index case.

Normal CI uses a deterministic fake embedding provider. Real-model tests run
only when `GALLERY_SEARCH_ML_MODEL_DIR` points to the pinned local bundle.

### Performance budgets

| Measurement | Budget |
| --- | ---: |
| 100k accelerated vector retrieval p95 | <= 150 ms |
| Warm end-to-end semantic text request on the ARM64 reference p95 | <= 1,500 ms |
| Existing lexical search p95 | <= 300 ms |
| Lexical p95 regression during semantic backfill | < 20% |

The real-model benchmark report includes CPU architecture, provider, model ID,
warmup count, p50/p95/max, queue depth, index coverage, and fixture size.

### Reliability coverage

- Optional packages absent.
- Sidecar stopped, slow, unauthorized, overloaded, or malformed response.
- Model file missing/checksum mismatch/dimension mismatch.
- Restart during embedding job.
- Source file changes during inference.
- Unsupported/corrupt/oversized image.
- sqlite-vec load/table corruption and BLOB rebuild.
- Model switch/full rebuild.
- Reference embedding missing.
- Capability/index status transitions.
- Hybrid RRF and enablement gate.
- Verification that no network download/request occurs.

### Required commands

Add focused semantic commands to the testing docs, then run the relevant
targeted suites followed by:

```bash
./test.sh backend-api
./test.sh lint
./test.sh e2e
./test.sh perf
./test.sh docs
./test.sh fast
```

Run the opt-in real-model smoke and 100,000-vector benchmark separately and
record their evidence. Do not make normal CI download the model.

### Documentation updates

Update:

- `docs/CONFIGURATION.md` for every semantic/sidecar setting;
- `docs/ARCHITECTURE.md` for sidecar boundaries, durable indexing, and modes;
- `docs/THIRD_PARTY_LIBRARIES.md` for optional ONNX/tokenizer/NumPy/sqlite-vec roles;
- `docs/testing/README.md` and `docs/testing/TEST_CATALOG.md` for fake-provider,
  real-model, vector, E2E, and performance coverage;
- deployment/startup documentation for optional port 4703 and the no-nginx rule.

## Completion criteria

- Lexical-only installation works with no ML packages, sidecar, model, or vector extension.
- The sidecar is loopback-only, authenticated, bounded, and accepts no paths.
- The pinned local model bundle is checksum-verified and never downloaded automatically.
- Semantic embeddings are durable, fingerprinted, rebuildable, and tied to active assets.
- Accelerated and exact scoped scoring agree on deterministic fixtures.
- Semantic and similar-image Search V2 modes have typed contracts and errors.
- Similar-image search accepts only an existing indexed asset.
- Hybrid uses RRF, remains disabled by default, and meets its relevance gate before enablement.
- UI controls are capability-gated and reuse the canonical search result surface.
- The 100,000-vector and ARM64 latency budgets pass.
- Semantic backfill does not break the 300 ms lexical budget.
- All maintained configuration, architecture, dependency, and testing docs are current.

When complete, move this file to `docs/archived/` and update
`docs/plans/README.md`.

## Execution log

| Date | Phase | Result | Evidence |
| --- | --- | --- | --- |
| - | - | Not started | - |
