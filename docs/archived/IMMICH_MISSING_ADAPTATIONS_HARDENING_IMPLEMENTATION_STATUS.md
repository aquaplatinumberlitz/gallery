# Immich Missing Adaptations Hardening — Implementation Status

Status: Completed and archived

Last reviewed: 2026-06-26

Plan ref:
[Immich adaptations hardening plan](IMMICH_MISSING_ADAPTATIONS_HARDENING_PLAN.md)

Current source of truth:
[Architecture](../ARCHITECTURE.md), backend tests, and frontend contract tests.

## Summary

The Immich-derived hardening plan is complete. Gallery adapted the four intended
bug classes without adopting Immich's Redis/BullMQ, PostgreSQL, microservice, or
generated-SDK architecture.

## Adapted Bug Classes

| Immich-style bug class | Gallery adaptation |
| --- | --- |
| Worker lifecycle | SQLite remains the runtime queue; metadata and derivative completion materialize durable DB state. Integrity checks now persist run summaries instead of only mutating rows. |
| Read-model/status | Metadata identity SQL is centralized in `backend/metadata_store/identity.py`; browse/status/indexer/integrity paths share tolerant `mtime_ns` semantics where applicable. Browse uses a deterministic closest-row tie-break. |
| Contract/UI | Maintenance file-health has GET/POST API endpoints, frontend query/mutation wiring, JSON schema, backend fixtures, frontend contract tests, and composable tests. The concurrent-run response uses the stable `{"run": null, "error": "check already running"}` envelope. |
| Migration/schema | The catalog schema creates `integrity_check_runs` and `idx_integrity_check_runs_finished`; `schema_check.py` validates lifecycle-required tables, columns, and indexes. Legacy additive-schema behavior remains SQLite-first. |

## Implemented Runtime Surface

- `GET /api/maintenance/file-health` returns the latest persisted file-health
  run, or `{"run": null}` when no run exists.
- `POST /api/maintenance/file-health/check` runs the integrity checker,
  persists the manual run, and returns the same response envelope.
- A concurrent POST returns HTTP 409 with `{"run": null, "error": "check already running"}`.
- The Maintenance page reads real file-health issue and repair counts instead of
  rendering backend-unavailable placeholders.
- Integrity checker run summaries persist issue counts, repair counts, trigger,
  timestamps, status, and error text.

## Key Files

Backend:

- `backend/metadata_store/identity.py`
- `backend/metadata_store/maintenance_store.py`
- `backend/metadata_store/schema_check.py`
- `backend/maintenance.py`
- `backend/integrity_checker.py`
- `backend/metadata_store/_schema.py`

Frontend:

- `frontend/src/composables/admin/useFileHealthQuery.ts`
- `frontend/src/contracts/schemas/file-health-response.schema.json`
- `frontend/src/contracts/__tests__/maintenanceFileHealthContract.test.ts`
- `frontend/src/composables/admin/__tests__/useFileHealthQuery.test.ts`
- `frontend/src/components/admin/MaintenancePage.vue`

## Verification

The post-fix audit verified the targeted backend integrity/maintenance suites,
metadata identity/lifecycle suites, frontend file-health contract/composable
tests, and frontend typecheck. A temporary catalog probe also confirmed that a
derivative job marked done without a ready derivative and without a cache file is
reported as a failed repair result rather than a repaired row.

This document records the completed implementation baseline. Future changes
should update maintained docs and tests, not reopen this archived plan.
