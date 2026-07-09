# Immich-Style Derivative Lifecycle Hardening Implementation Status

Status: Complete

Last updated: 2026-07-09

## Delivered

- Durable derivative outcomes: `done`, `skipped`, `failed`, and bounded retry.
- Machine-readable result codes for inactive, missing, changed, invalid,
  exhausted, and internal-error outcomes.
- Exception containment around cache-path calculation, rendering, persistence,
  and the outer worker loop.
- Claim ownership, unique fencing tokens, 15-minute leases, startup recovery,
  expired/dead-worker recovery, and a 30-second worker supervisor.
- One active/current-source predicate across warm, claim, recovery, integrity,
  and status paths.
- Library and global generated-image queue/worker diagnostics.
- Admin polling based on active work, thumbnail-scoped warm action, unhealthy
  worker warning, and Maintenance runtime counters.

## Verification Evidence

Final workspace evidence:

- Scheduler/schema characterization after Phase 3: 15 passed.
- Scheduler/integrity/library alignment after Phase 4: 125 passed.
- Backend status/API slice after Phase 5: 93 passed.
- Full frontend Vitest suite after Phase 5: 1,046 passed.
- Focused frontend admin suite after Phase 5: 39 passed.
- Frontend `vue-tsc --noEmit`: passed.
- `./test.sh lint`: passed.
- `./test.sh docs`: passed.
- `./test.sh backend-api`: 103 passed.
- `./test.sh fast`: backend 925 passed with 90.58% coverage; frontend 1,048
  passed with all coverage thresholds met; typecheck and production build
  passed.
- Playwright library-management and imported-data-maintenance specs: 9 passed.

No commit was created as part of this implementation session. Evidence refers
to the current working tree; unrelated pre-existing changes remain uncommitted.
