# Archived Documentation

Status: Maintained index

Last reviewed: 2026-06-26

This directory retains completed or superseded plans, historical contracts,
and dated reports. These files preserve implementation context but do not
describe current behavior unless explicitly stated. Use
[Architecture](../ARCHITECTURE.md) and the other maintained references for the
current system.

Notable groups include:

- Catalog Scan Pipeline and Unified Status — 11-phase implementation with migration, status builder, browse API, and documentation.
- Metadata Lifecycle D Full Clean — durable SQLite-backed metadata queue, DB-claim worker, completion invariants, startup recovery, lifecycle diagnostics, and integrity checker.
- Library Management V1 plan, phase contract, and final implementation status.
- Completed AlbumScroller, VueUse theme, shadcn-vue, Tailwind, sidebar, and TanStack migrations.
- Completed lint/format adoption and frontend adaptation plans.
- Completed Frontend Library Health and Generated Files UI plan — Admin library detail exposes generated-image coverage, live status, and problem counters; Admin Maintenance owns global generated-file actions.
- Completed Immich Missing Adaptations Hardening plan — Gallery adapted the worker lifecycle, read-model/status, contract/UI, and migration/schema hardening gaps; Admin Maintenance now reads the backend file-health report API.
- Utility Library Migration — 12-item, 6-phase migration (clipboard, debounce, device breakpoints, focus trap → Reka FocusScope, column resize, natural sort, Axios interceptor, event listeners, localStorage, formatBytes), plus follow-up deferred cleanups for GalleryGrid intersection observer and scroll visibility mechanics.
- Historical performance comparison and deprecated testing strategy.
- Evolution and upstream-adaptation roadmaps retained for design context.
