# Related Assets and Generation Discovery Implementation Plan for OpenCode

Status: Proposed

Last reviewed: 2026-07-13

Owner: OpenCode

Priority: P2-P3

Execution: Sequential and phase-gated

Depends on:

- every acceptance gate in
  [Search Hardening](../archived/SEARCH_HARDENING_IMPLEMENTATION_PLAN.md);
- the canonical request, scope, prompt-group, and observed-model foundations in
  [Search Discovery Evolution](../archived/SEARCH_DISCOVERY_EVOLUTION_IMPLEMENTATION_PLAN.md).

Supersedes the active implementation direction in the archived
[Semantic Search plan](../archived/SEARCH_SEMANTIC_IMPLEMENTATION_PLAN.md).

## Objective

Add explainable AI-art discovery without a machine-learning model, inference
sidecar, vector extension, or second search database.

This plan implements:

- normalized prompt ingredients that can be searched and explored;
- deterministic generation-family and recipe signatures;
- related-asset ranking from prompt, model, LoRA/resource, workflow, and
  generation-setting evidence;
- lightweight visual-variant detection using Pillow-derived perceptual
  fingerprints;
- generation stacks, parameter comparison, and reason-labelled related results;
- optional smart collections built from normal Search V2 filters.

The feature is named **Related Assets**, not semantic search. Metadata overlap
finds related generation intent or recipes. Perceptual fingerprints find
near-duplicates and visually close variants. Neither mechanism claims to
understand arbitrary image concepts from pixels.

The implementation remains local-first and SQLite-only. It reuses the current
catalog, metadata, derivative, durable-job, FastAPI, Vue 3, and TanStack Query
boundaries.

## Why this replaces semantic ML

The superseded semantic plan required an ONNX model bundle, tokenizer runtime,
authenticated loopback sidecar, inference queues, durable embedding storage,
sqlite-vec acceleration, a derived vector database, model lifecycle handling,
and separate operational failure states.

Those costs are disproportionate for the current local/personal gallery and
its reference ARM64 CPU deployment. A 512-dimensional float32 embedding alone
requires 2,048 bytes per asset before indexes or duplicate durable/derived
storage. The related-assets approach instead uses metadata already owned by
the application and small fixed-size image fingerprints.

## Non-goals

- No CLIP, ONNX Runtime, tokenizer, NumPy, sqlite-vec, GPU, or ML sidecar.
- No natural-language understanding of images that have no searchable metadata.
- No claim that a metadata relation proves visual similarity or provenance.
- No user-uploaded query image or arbitrary filesystem-path query.
- No video perceptual fingerprints in v1.
- No synchronous source-image decoding during a related-assets request.
- No unbounded token, raw-workflow, or all-pairs similarity scan.
- No misleading similarity probability or confidence percentage.
- No replacement of lexical Search V2, fielded search, or normal facets.
- No ratings, favorites, destructive duplicate cleanup, or automatic file moves.

## OpenCode execution rules

Apply the repository rules in `AGENTS.md` and the execution rules from the
hardening and discovery plans. Additionally:

1. Verify the required predecessor gates against code and tests before R0.
2. Reuse existing catalog, metadata, derivative, and durable-job primitives.
   Do not introduce a parallel scheduler or a second database.
3. Add only additive schema migrations and use the next unused schema version.
4. Decode and fingerprint images only in bounded background work. A user query
   may read persisted fingerprints but must never generate one synchronously.
5. Prefer an existing current thumbnail or preview derivative as fingerprint
   input. Do not reopen an original when a suitable derivative is available.
6. Version every normalizer, signature, scoring policy, and visual algorithm.
   A version change must make stale rows observable and rebuildable.
7. Filter every candidate through active catalog ownership and the canonical
   folder, library, or all scope before returning it.
8. Never log full prompts, local paths, raw workflows, or sidecar contents in
   public status or error payloads.
9. Keep reason codes stable and user-facing wording honest. Do not rename the
   feature to semantic or AI similarity.
10. Stop and report a blocker if the design requires a model download, external
    service, destructive media mutation, or an unbounded request-time scan.

## R0 - Baseline, vocabulary, and contract lock

**Goal:** Lock current coverage, performance, terminology, and API behavior
before adding derived relation data.

### Baseline tasks

- [x] Record HEAD, dirty files, Python/Node/SQLite versions, and schema version.
- [x] Measure active image count and current coverage for prompt, negative
      prompt, model/hash, LoRA/resources, workflow data, and preview derivatives.
- [x] Record exact duplicate prompt groups and representative generation batches.
- [x] Capture current lexical search and facet p50/p95 on the managed fixture.
- [x] Add deterministic relation fixtures covering:
  - exact recorded generation settings;
  - same family with different seed;
  - same model with unrelated prompts;
  - shared LoRA with unrelated prompts;
  - prompt fragments with common boilerplate;
  - missing and malformed metadata;
  - resize, re-encode, light color change, crop, mirror, and rotation cases;
  - cross-library and inactive-asset leakage guards.

### Product vocabulary

Use these terms consistently:

| Term | Meaning |
| --- | --- |
| Generation family | Assets sharing normalized prompt intent, model identity, and resource set. |
| Recipe | A family plus recorded sampler, scheduler, steps, CFG, dimensions, and other deterministic settings. |
| Visual variant | A near-duplicate or compositionally close image according to fixed perceptual fingerprints. |
| Related asset | An asset supported by one or more explicit metadata or visual reasons. |

Do not use `semantic`, `AI similarity`, `understands`, `same image`, or
`provenance` for these relations.

### Public request contract

Add `POST /api/search/related` with regular Pydantic request and response
models:

```json
{
  "schema_version": 1,
  "reference_asset_id": 123,
  "profile": "related",
  "scope": {
    "kind": "library",
    "library_id": 2
  },
  "limit": 60
}
```

Contract rules:

- [x] `schema_version` is exactly `1`.
- [x] `profile` is `related`, `recipe`, or `visual`.
- [x] Scope reuses the canonical Search V2 discriminated union.
- [x] `reference_asset_id` must identify an active image visible in that scope.
- [x] `limit` defaults to 60 and is bounded to 1-100.
- [x] V1 returns one bounded page with no cursor.
- [x] The reference asset is excluded from its own results.
- [x] Related requests are not stored as saved or recent searches.

Each result adds:

- `relation_tier`;
- `relation_reasons` as stable typed codes;
- nullable `visual_distance`;
- nullable `metadata_score` used for diagnostics, not probability copy;
- the canonical media fields established by Search Hardening.

### Error policy

| Condition | Status |
| --- | ---: |
| Invalid profile, scope, or limit | 422 |
| Reference outside authorized scope | 404 |
| Reference is not an active image | 409 |
| Required relation index is not ready | 409 |
| Required persisted index is unusable | 503 |
| Unexpected failure | Existing sanitized 500 contract |

### Acceptance gates

- [x] Fixtures define the expected relation tier and reason codes.
- [x] Metadata and visual relation terminology is unambiguous in API and UI copy.
- [x] OpenAPI documents request, result, status, and error models completely.
- [x] Baseline evidence is recorded before schema or ranking changes.

### R0 baseline evidence (2026-07-13)

- Baseline commit: `234321051c40950eac2c2aafecbd4f91c1ee8254`; working tree clean.
- Runtime: Python 3.11.15, Node 22.22.2, SQLite 3.50.4 through Python;
  the standalone `sqlite3` CLI is not installed.
- Catalog: schema constant and `PRAGMA user_version` were both 8. The active
  database contained 516 active images, all with current metadata and current
  ready preview derivatives. Coverage counts were 128 positive prompts, 93
  negative prompts, 92 model-name/hash rows, 60 LoRA-bearing assets, and 130
  workflow-bearing assets.
- Prompt/batch evidence: zero exact duplicate indexed prompt groups were
  present. Representative exact recorded-setting batches included groups of
  11 (`er_sde`, 12 steps, CFG 1.1, 1672x944), 10
  (`waiNSFWIllustrious_v120`, Euler ancestral/Karras, 28 steps, CFG 8,
  840x1080), and 10 assets with the same model/sampler/scheduler at CFG 5,
  1024x1024.
- Managed 5,000-row fixture, 20 warmed in-process HTTP iterations: broad
  lexical p50/p95 201.59/211.64 ms; prompt-heavy lexical p50/p95
  222.93/247.69 ms; all-scope facets p50/p95 265.96/339.09 ms.
- Deterministic fixture: `backend/tests/fixtures/related_assets_v1.json`
  covers exact settings, seed-only family changes, unrelated same-model and
  shared-LoRA cases, boilerplate prompts, missing/malformed metadata, resize,
  re-encode, color change, crop/mirror/rotation limitations, cross-library
  scope, and inactive-asset exclusion.

## R1 - Prompt normalization and generation signatures

**Goal:** Build compact, versioned metadata relations that describe recorded
generation intent and settings.

### Prompt normalization

Use one versioned prompt-atom normalizer shared by signature generation,
reference-query construction, bounded candidate scoring, and prompt chips:

1. Unicode NFKC;
2. trim and collapse whitespace;
3. split primarily on comma/newline prompt atoms, not every word;
4. unwrap supported emphasis syntax and retain a bounded parsed weight;
5. casefold for identity while keeping one display form;
6. reject empty, control-heavy, or overlong atoms;
7. cap returned atoms per positive and negative prompt.

Initial limits:

- at most 64 atoms per positive prompt;
- at most 64 atoms per negative prompt;
- at most 160 Unicode characters per atom;
- at most 16 selected atoms in one FTS candidate query.

V1 deliberately does not create a global `prompt_terms` or co-occurrence graph.
The current `image_metadata` FTS tables and the discovery plan's exact prompt
groups provide candidate lookup. The normalizer parses only the reference and
the bounded candidate rows selected for exact scoring. Add a persistent term
index later only if measured query quality cannot meet the acceptance gates
within the storage budget.

### Generation signature schema

```text
asset_generation_signatures
- asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE
- library_id INTEGER REFERENCES libraries(id) ON DELETE CASCADE
- prompt_hash BLOB NULL
- family_hash BLOB NULL
- recipe_hash BLOB NULL
- exact_hash BLOB NULL
- normalizer_version INTEGER
- extractor_version INTEGER
- source_mtime_ns INTEGER
- source_size INTEGER
- indexed_at REAL
```

Indexes:

- `(library_id, prompt_hash, asset_id)`;
- `(library_id, family_hash, asset_id)`;
- `(library_id, recipe_hash, asset_id)`;
- `(library_id, exact_hash, asset_id)`.

Signature inputs:

| Signature | Inputs |
| --- | --- |
| `prompt_hash` | Normalized positive and negative prompt atoms. |
| `family_hash` | Prompt hash, observed model identity, and sorted LoRA/resource identity. |
| `recipe_hash` | Family inputs plus sampler, scheduler, steps, CFG, dimensions, denoising, hires, VAE, and relevant workflow properties. |
| `exact_hash` | Recipe inputs plus recorded seed and other deterministic generation identifiers. |

Rules:

- [x] Missing values are represented explicitly; they are not guessed.
- [x] A model hash wins as identity when present; normalized model name is a
      fallback, not a silent hash alias.
- [x] Resource identity uses resource hash when present, otherwise normalized
      kind/name, with a stable sort order.
- [x] Numeric values have documented canonical formatting before hashing.
- [x] Workflow JSON text is never hashed wholesale into a family. Only typed,
      bounded properties approved by the discovery registry may participate.
- [x] A weak signature containing only a common model, seed, or sampler is not
      eligible to form a relation by itself.

### Lifecycle

- [x] Derive signatures when current normalized metadata is persisted.
- [x] Backfill through existing durable metadata/search lifecycle primitives.
- [x] Key backfill by active `asset_id`; use bounded batches and short writes.
- [x] Source mtime/size or normalizer/extractor version changes invalidate rows.
- [x] Offline, deleted, replaced, or unowned assets cannot remain candidates.
- [x] Failures are counted and observable without failing catalog or lexical search.

### Acceptance gates

- [x] Equivalent normalized prompts produce the same prompt hash.
- [x] A seed-only change preserves family/recipe as designed and changes exact hash.
- [x] A sampler or CFG change preserves family and changes recipe/exact hashes.
- [x] A model or LoRA identity change changes family, recipe, and exact hashes.
- [x] Missing metadata never creates a false strong family from defaults.
- [x] Reindexing is idempotent and produces one current signature per active asset.

## R2 - Explainable metadata-related ranking

**Goal:** Return useful generation relations without an all-pairs scan or an
opaque score.

### Candidate sources

Build a bounded UNION of indexed candidates from:

- exact `exact_hash`, `recipe_hash`, `family_hash`, or `prompt_hash` matches;
- shared model hash or observed model identity;
- shared LoRA/resource hash or normalized resource identity;
- compatible typed workflow properties when that discovery index exists;
- FTS top candidates built from at most 16 distinctive normalized prompt atoms.

Rules:

- [x] A model, sampler, seed, orientation, or folder match alone is insufficient.
- [x] Prompt atoms use deterministic selection based on parsed weight, phrase
      length, duplicate removal, and a versioned common-boilerplate policy.
- [x] FTS prompt candidates are capped before metadata rows are loaded.
- [x] Candidate collection is bounded before exact scoring.
- [x] Metadata scoring happens outside write transactions.
- [x] Scope and active-asset filters apply in every candidate branch.

### Fixed relation tiers

Use these descending tiers before fine ordering:

| Tier | Relation |
| ---: | --- |
| 100 | Same exact recorded signature. |
| 90 | Same recipe with a different exact signature. |
| 80 | Same generation family with strong prompt/resource evidence. |
| 70 | Exact prompt plus compatible model or resource evidence. |
| 60 | Strong weighted prompt overlap plus at least one model/resource/workflow signal. |
| 40 | Bounded weak relation shown only when stronger results are insufficient. |

Within one tier, use:

1. weighted prompt-atom Jaccard using parsed prompt weights and fixed
   normalizer heuristics;
2. resource overlap;
3. model/workflow compatibility;
4. recipe-setting proximity;
5. source `mtime_ns` descending;
6. stable `asset_id` ascending.

Version the complete scoring policy. Tests must use golden fixtures rather than
asserting undocumented implementation details.

### Reason codes

Initial stable reason codes:

- `same_exact_signature`;
- `same_recipe`;
- `same_generation_family`;
- `same_prompt`;
- `strong_prompt_overlap`;
- `same_model_hash`;
- `same_model_name`;
- `shared_lora`;
- `shared_resource`;
- `shared_workflow_property`;
- `similar_generation_settings`.

### Acceptance gates

- [x] Same model with unrelated prompts does not outrank a same-family result.
- [x] Seed alone never creates a relation.
- [x] Common boilerplate cannot dominate rare meaningful prompt atoms.
- [x] Results contain deterministic tiers, order, and reason codes.
- [x] Cross-library, offline, deleted, stale, and unowned candidates are excluded.
- [x] Missing optional workflow indexes degrade to metadata-only results safely.

## R3 - Lightweight visual-variant fingerprints

**Goal:** Find near-duplicates, resizes, re-encodes, upscales, and lightly
modified variants without a model or vector database.

### Algorithm v1

Use Pillow only:

1. read a current thumbnail or preview derivative;
2. apply the documented EXIF transpose and alpha-composite policy;
3. resize to a bounded working image;
4. calculate 64-bit horizontal dHash;
5. calculate 64-bit vertical dHash;
6. calculate a quantized 4x4 RGB color grid;
7. persist the algorithm and derivative-source version.

Do not add pHash/DCT, NumPy, OpenCV, or an image-model dependency in v1.

### Schema

```text
asset_visual_fingerprints
- asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE
- library_id INTEGER REFERENCES libraries(id) ON DELETE CASCADE
- source_mtime_ns INTEGER
- source_size INTEGER
- derivative_role TEXT
- derivative_version INTEGER
- algorithm_version INTEGER
- dhash_horizontal BLOB     # exactly 8 bytes
- dhash_vertical BLOB       # exactly 8 bytes
- color_grid BLOB           # exactly 48 bytes
- indexed_at REAL

asset_visual_hash_bands
- asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE
- library_id INTEGER REFERENCES libraries(id) ON DELETE CASCADE
- hash_kind INTEGER         # horizontal|vertical
- band_no INTEGER           # 0..3
- band_value INTEGER        # unsigned 16-bit value
PRIMARY KEY(asset_id, hash_kind, band_no)
```

Candidate index:

- `(hash_kind, band_no, band_value, library_id, asset_id)`.

### Candidate and distance policy

- [ ] Split each 64-bit dHash into four 16-bit bands.
- [ ] Query indexed band matches and bounded one-bit band probes for the v1
      near-duplicate threshold.
- [ ] Calculate exact Hamming distance with Python `int.bit_count()` only for
      the bounded candidate set.
- [ ] Use color-grid distance and aspect ratio only to break or reject weak
      dHash matches; do not call them semantic features.
- [ ] Keep the visual candidate pool bounded before metadata enrichment.
- [ ] Exclude the reference and apply active catalog/scope filters.

### Lifecycle

- [ ] One bounded background worker computes fingerprints.
- [ ] Prefer an existing current derivative; missing derivatives queue normal
      low-priority derivative work instead of opening originals in the request.
- [ ] Decode and hash outside SQLite write transactions.
- [ ] Persist fingerprint and band rows atomically.
- [ ] Source, derivative, or algorithm version changes invalidate the row.
- [ ] A reference without a current fingerprint returns
      `409 REFERENCE_NOT_INDEXED` with coverage/status context.
- [ ] Visual indexing can be disabled or degraded without affecting lexical or
      metadata-related search.

### Honest quality limits

- dHash is designed for near-duplicate and compositionally close variants.
- Large crops, mirrors, rotations, or generative composition changes may not match.
- Similar colors or layouts can create false positives.
- A visual match does not prove common prompt, recipe, lineage, or source file.

### Acceptance gates

- [ ] Resize and re-encode fixtures match within the documented threshold.
- [ ] Light color changes remain discoverable without admitting unrelated fixtures.
- [ ] Crop, mirror, and rotation limitations are represented in tests and docs.
- [ ] Candidate lookup is index-bounded at the 100,000-asset fixture scale.
- [ ] No related-assets HTTP request decodes an image.
- [ ] Lexical search works unchanged when visual indexing is disabled or failed.

## R4 - Vue related-assets and generation-family UX

**Goal:** Expose relations as transparent navigation aids in the existing
gallery and lightbox surfaces.

### Component map

| Component/composable | Responsibility |
| --- | --- |
| `RelatedAssetsPanel.vue` | One canonical result surface for metadata and visual relations. |
| `RelationReasonList.vue` | Human-readable reason chips from typed backend codes. |
| `GenerationFamilySummary.vue` | Family/recipe counts and recorded-setting comparison. |
| `useRelatedAssetsQuery.ts` | TanStack Query request, retry, and capability/status handling. |
| `useGenerationComparison.ts` | Pure comparison of normalized recorded settings. |

### Required behavior

- [ ] Add `Find related` to image-card and lightbox overflow actions.
- [ ] Default to the combined `related` profile.
- [ ] Offer `Same recipe` and `Visual variants` as explicit filters, not hidden modes.
- [ ] Reuse the canonical gallery result card/grid; do not add a second media viewer.
- [ ] Show relation tier labels and concise reason chips.
- [ ] Never show a probability percentage or AI-generated explanation.
- [ ] A generation-family summary says `same recorded settings`, not same lineage.
- [ ] Compare changed seed, sampler, scheduler, steps, CFG, dimensions, model,
      LoRA/resources, denoising, hires, and VAE fields when present.
- [ ] Preserve successful results during background refresh errors and expose retry.
- [ ] Missing visual coverage still permits metadata-related results.
- [ ] Related sessions are not written to saved/recent-search storage.
- [ ] Desktop, tablet, mobile, keyboard, and screen-reader semantics match.

### Smart collections

Build smart collections only from canonical Search V2 filters and persisted
relation facts. Initial candidates:

- same generation family;
- same recipe;
- assets missing prompt/model metadata;
- assets with visual-variant candidates;
- recently indexed assets for a selected model or LoRA.

Smart collections do not store asset membership. They store or derive a bounded
canonical query so results remain current.

### Acceptance gates

- [ ] Find Related opens the correct reference and scope.
- [ ] Reason codes map to stable, localized, accessible copy.
- [ ] Recipe/family wording never overclaims provenance.
- [ ] Metadata-only, visual-only, combined, building, degraded, and failed
      states render distinctly.
- [ ] Back/Forward and reference changes do not leak prior results.
- [ ] Related-result selection opens the existing lightbox correctly.

## R5 - Reliability, performance, tests, and documentation

### Backend coverage

- Prompt normalization, atom selection, limits, weights, Unicode, and malformed syntax.
- Family, recipe, and exact signature canonicalization.
- Model/resource identity and missing-field behavior.
- Candidate caps, IDF weighting, tier ordering, and reason codes.
- Scope, active ownership, stale source, deletion, and cross-library isolation.
- Fingerprint extraction, fixed byte shapes, algorithm version, and invalidation.
- Hash-band candidate retrieval and exact Hamming filtering.
- Durable backfill interruption, resume, idempotence, and failure accounting.
- Typed request/response/error and capability/status contracts.

### Frontend coverage

- Query enablement, cancellation, retry, reference changes, and stale data.
- Reason copy and no-probability guarantee.
- Family/recipe parameter comparison.
- Metadata-only and missing-visual fallback.
- Card/lightbox actions, responsive layouts, keyboard, and accessibility.
- Smart-collection canonical request round-trips.

### Managed E2E scenarios

- Open an asset and find same-family results with visible reasons.
- Switch to Same Recipe and verify changed seed comparison.
- Find a resized/re-encoded visual variant.
- Verify an unrelated same-model asset does not rank as a strong relation.
- Verify a reference without a fingerprint exposes status without blocking
  metadata-related results.
- Verify inactive and cross-library assets never leak.

### Deterministic performance fixtures

Extend the managed fixture with 100,000 synthetic active assets containing
precomputed metadata signatures, prompt terms, fingerprints, and controlled
near-neighbor groups. Extraction tests use a small real-image fixture set;
normal CI must not generate 100,000 image files.

### Performance budgets

| Measurement | Budget |
| --- | ---: |
| Metadata-related warm request p95 at 100k | <= 150 ms |
| Visual candidate retrieval p95 at 100k | <= 75 ms |
| Combined related request p95 at 100k | <= 200 ms |
| Existing lexical search p95 | <= 300 ms |
| Lexical p95 regression during relation backfill | < 10% |
| Additional visual worker RSS on reference host | < 64 MiB |
| Relation/fingerprint DB growth at 100k | < 100 MiB |

### Required commands

Run focused tests while implementing, then:

```bash
./test.sh backend-api
./test.sh lint
./test.sh e2e
./test.sh perf
./test.sh docs
./test.sh fast
```

Use `./test.sh full` before release-style handoff when time and environment permit.

### Documentation updates

Update:

- `docs/ARCHITECTURE.md` for relation data flow, ownership, and lifecycle;
- `docs/CONFIGURATION.md` only for any bounded worker/feature flags actually added;
- `docs/METADATA_PARSING.md` for prompt normalization and signature inputs;
- `docs/THIRD_PARTY_LIBRARIES.md` to state that no new image/ML dependency is required;
- `docs/UI_UX_GUIDELINES.md` for relation wording and responsive behavior;
- `docs/testing/README.md` and `docs/testing/TEST_CATALOG.md` for fixtures,
  reliability, E2E, and performance coverage.

## Completion criteria

- Normal gallery operation requires no ML packages, model files, sidecar,
  vector extension, or second database.
- Prompt normalization is versioned and bounded; generation signatures are
  durable and tied to active assets.
- Related metadata ranking is deterministic and returns explicit reason codes.
- Same-model or same-seed evidence alone cannot create a strong relation.
- Visual variants use persisted Pillow-only fingerprints and never decode in a
  request path.
- Metadata-related search remains available when visual indexing is disabled,
  building, degraded, or failed.
- UI wording distinguishes generation relations from visual variants and does
  not claim semantic understanding or probability.
- The 100,000-asset performance and storage budgets pass.
- Existing lexical search remains within its 300 ms budget.
- Maintained architecture, metadata, UI, dependency, and testing docs are current.

When complete, move this file to `docs/archived/` and update
`docs/plans/README.md`.

## Execution log

| Date | Phase | Result | Evidence |
| --- | --- | --- | --- |
| 2026-07-13 | R0 | Complete | Pre-change schema/runtime/catalog and managed 5,000-row search/facet baselines recorded; deterministic metadata/visual relation fixture added; versioned `/api/search/related` request/result/status/reason/error models and canonical reference authorization covered by 8 focused contracts. |
| 2026-07-13 | R1 | Complete | Schema v10 adds compact generation signatures with rollback-safe `.v8.bak`; versioned prompt atoms and canonical numeric hashing lock family/recipe/exact boundaries; metadata persistence invalidates and coalesces durable active-only backfill; 15 focused tests plus lifecycle/API regression coverage pass. |
| 2026-07-13 | R2 | Complete | Bounded signature/model/resource/workflow/16-atom FTS candidates feed scoring outside SQLite writes; fixed explainable tiers/reasons and recipe filtering pass the golden fixture; stale, inactive, cross-scope, seed-only, model-only, LoRA-only, and boilerplate-only leakage is rejected. |
