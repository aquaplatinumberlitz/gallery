# Archived Documentation

Status: Maintained index

Last reviewed: 2026-07-13

This directory retains completed or superseded plans, historical contracts,
and dated reports. These files preserve implementation context but do not
describe current behavior unless explicitly stated. Use
[Architecture](../ARCHITECTURE.md) and the other maintained references for the
current system.

Notable groups include:

- Completed Backend Audit Findings Remediation Plan — five phase-gated changes covering proxy security and catalog-only paths, metadata/catalog convergence, supervised services, derivative/poster hardening, HTTP semantics, transactional schema v2 migration, and diagnostics.
- Catalog Scan Pipeline and Unified Status — 11-phase implementation with migration, status builder, browse API, and documentation.
- Metadata Lifecycle D Full Clean — durable SQLite-backed metadata queue, DB-claim worker, completion invariants, startup recovery, lifecycle diagnostics, and integrity checker.
- Library Management V1 plan, phase contract, and final implementation status.
- Completed AlbumScroller, VueUse theme, shadcn-vue, Tailwind, sidebar, and TanStack migrations.
- Completed lint/format adoption and frontend adaptation plans.
- Completed Frontend Library Health and Generated Files UI plan — Admin library detail exposes generated-image coverage, live status, and problem counters; Admin Maintenance owns global generated-file actions.
- Completed Immich Missing Adaptations Hardening plan — Gallery adapted the worker lifecycle, read-model/status, contract/UI, and migration/schema hardening gaps; Admin Maintenance now reads the backend file-health report API.
- Completed Immich-Style Derivative Lifecycle Hardening plan — fenced
  SQLite claims, controlled skipped outcomes, lease/dead-worker recovery,
  worker supervision, active/current integrity predicates, and admin
  generated-image queue health.
- Completed Imported Data Maintenance UX Refactor plan — Admin update labels now keep scan endpoints behind update vocabulary, while imported-data clear/rebuild and catalog reset live under maintenance endpoints.
- Utility Library Migration — 12-item, 6-phase migration (clipboard, debounce, device breakpoints, focus trap → Reka FocusScope, column resize, natural sort, Axios interceptor, event listeners, localStorage, formatBytes), plus follow-up deferred cleanups for GalleryGrid intersection observer and scroll visibility mechanics.
- Historical performance comparison and deprecated testing strategy.
- Evolution and upstream-adaptation roadmaps retained for design context.
- [Superseded Semantic Search plan](SEARCH_SEMANTIC_IMPLEMENTATION_PLAN.md) —
  retained as the rejected optional-ML design; active discovery direction now
  uses explainable metadata relations and Pillow-only visual fingerprints
  without a model sidecar or vector database.
- Completed Frontend Test Quality Refactor — 9-phase plan covering: baseline audit, 3 extra test file merges (Phase 1), component test cleanup (Phase 2), Playwright wait refactor (86→8 sleeps, Phase 3), locator refactor with 15 data-testid additions (Phase 4), catalog alignment (Phase 5), residual wait cleanup (22→5, Phase 6), residual selector cleanup (Phase 7), final docs (Phase 8), and test diet (−4 files, −28 tests, Phase 9).
- Completed Search Pattern Adaptation plan — `/api/search` now exposes a
  bounded, cursor-paginated `media` stream; the frontend uses infinite query
  paging for search; fielded search keeps metadata filters scoped to
  filterable media.
- Gallery Browse Lifecycle Manager — deferred frontend browse-lifecycle
  refactor criteria retained as historical tech-debt context.
- Derivative Lifecycle Full Convergence Plan — 7-phase end-to-end
  implementation for desired thumbnail/preview work creation, reconciliation,
  policy-aware status, quota/request lifecycle, generated test-artifact
  exclusions, lease/shutdown resilience, existing-data convergence, and final
  closeout verification.
- Derivative Lifecycle Full Convergence Implementation Status — phase-gated
  execution record and verification results for the derivative lifecycle
  convergence.
- Derivative Lifecycle Audit Fix Handoff Prompt — copy-ready OpenCode handoff
  for the eleven audited scheduler, integrity, quota, HTTP, Admin-state,
  reconciliation, and catalog-hygiene follow-up fixes.
- Derivative Lifecycle d98c741 Re-audit Fix Handoff Prompt — copy-ready
  OpenCode handoff for post-commit eviction finalization, protected unlink,
  bounded linearizable start/stop, exact integrity repair reporting, and
  missing regression/closeout evidence.
