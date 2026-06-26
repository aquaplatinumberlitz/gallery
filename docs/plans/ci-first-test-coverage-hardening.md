# CI-First Test Coverage Hardening Plan

Status: Proposed

Last reviewed: 2026-06-26

## Summary

This plan hardens the repository's test and coverage gates with CI as the source
of truth. Local commands must mirror CI behavior, backend pytest coverage must
rise above 90%, and frontend Vitest coverage must rise above 90% with meaningful
tests. Do not inflate coverage with empty tests, shallow render-only tests, or
unjustified production-file exclusions. If a target cannot be reached with
quality tests in the implementation window, document the exact blockers and the
remaining files instead of silently lowering standards.

Current audit baseline:

- Backend pytest: 816 tests, 89.47% line coverage.
- Frontend Vitest: 440 tests, 20.27% line coverage.
- Playwright Chromium: 159 tests.
- Test matrix/docs audit: 0 matrix gaps and 0 uncataloged important files.
- Observed risk: `./test.sh unit` once failed order-dependently in
  `test_search_filters_stale_rows_and_triggers_cleanup`, while the test passed
  alone and a later full backend run passed.

## Key Changes

### 1. CI-first command contract

- Keep `./test.sh` as the single local entrypoint for CI-equivalent behavior.
- Make CI jobs call `./test.sh` for lint, unit coverage/build, docs audit, E2E,
  and perf wherever practical.
- Ensure local commands and CI commands do not drift:
  - `./test.sh lint` matches the CI lint job.
  - `./test.sh unit` matches the CI unit/build/coverage job.
  - `./test.sh docs` matches the CI docs/test-matrix job.
  - `./test.sh e2e` and `./test.sh perf` use the same deterministic fixture
    policy as CI.
  - `./test.sh full` remains the local CI-equivalent rollup.
- Acceptance: any CI command change must be reflected in `test.sh` in the same
  PR.

### 2. Fix backend flaky/order-dependent schema init

- Fix the root cause of the observed failure in
  `backend/tests/test_search_coverage.py::test_search_filters_stale_rows_and_triggers_cleanup`.
- In `backend/tests/conftest.py`, make `isolated_metadata_db` deterministic:
  reset `backend.metadata_store._db._DB_INITIALIZED` and
  `_DB_INITIALIZED_PATH`, then initialize the isolated catalog schema before any
  public metadata-store helper can run.
- Add a regression test proving an isolated DB has the catalog tables required
  by `register_library`, including `library_import_paths`.
- Do not bypass the failing path with mocks or by avoiding `register_library`.
- Acceptance:
  - the targeted test passes alone;
  - full backend pytest passes at least twice consecutively;
  - `./test.sh unit` no longer fails due to schema-order dependence.

### 3. Backend pytest coverage above 90%

- Raise the backend coverage gate to `--cov-fail-under=90` after tests meet the
  target.
- Add meaningful tests for modules currently below or near 80%:
  - `backend/library_events.py`: subscriber lifecycle, multi-subscriber
    delivery, disconnect cleanup, queue/error branches.
  - `backend/watcher.py`: disabled mode, missing dependency fallback, path
    filtering, debounce/coalesce, event-to-scan handoff, start/stop idempotency.
  - `backend/indexer.py`: disabled worker paths, recovery branches,
    stale/skip/fail completion branches, batch failure handling.
  - `backend/metadata_store/folder_index.py`: stale/incomplete folder state,
    missing folder fallback, counts, replacement/update behavior.
  - `backend/thumbnails.py`: missing source, invalid cache, stale derivative,
    no-upscale, error mapping.
- Every new test must assert observable behavior, persisted state, response
  shape, or a meaningful state transition.
- Acceptance:
  - backend total line coverage is >90%;
  - no production backend module remains below 80% unless documented with a
    concrete rationale and follow-up.

### 4. Frontend Vitest coverage above 90%

- Fix `scripts/audit_test_matrix.py` to read
  `frontend/coverage/vitest/coverage-summary.json` before older fallback paths.
- Add a frontend coverage threshold checker that reads the Vitest V8 coverage
  summary and fails clearly when thresholds are not met.
- Enforce, once the tests reach the target:
  - lines >= 90%;
  - statements >= 90%;
  - functions >= 85%;
  - branches >= 80%.
- Increase frontend unit/component coverage with high-value tests:
  - composables and query wrappers: loading, success, error, retries, cache
    invalidation, enabled/disabled behavior.
  - stores: state transitions, persistence, edge cases, error/toast behavior.
  - services/API wrappers: endpoint, params, response mapping, error mapping.
  - lib/utils: parsing, formatting, guards, query-key factories, contract
    validators.
  - critical Vue components: Maintenance, Library list/detail, Index status,
    Gallery grid state rendering, Lightbox panels, and user-visible error/empty
    states.
- Avoid low-value tests:
  - no empty tests;
  - no assertion-free mount tests;
  - no broad production-file exclusions just to raise coverage;
  - no tests that only execute lines without checking behavior.
- If frontend >90% cannot be reached with quality tests in this pass, add a
  status note listing the remaining low-coverage files, why a useful test was
  not written, and the follow-up needed.

### 5. Optional Playwright coverage, separate from Vitest gate

- Keep PR CI optimized for deterministic pass/fail: lint, unit coverage, docs,
  E2E shards, and perf.
- Add an optional `coverage-e2e` workflow via `workflow_dispatch` and scheduled
  run:
  - deterministic backend fixture;
  - `VITE_COVERAGE=true`;
  - nyc/html/lcov artifacts uploaded.
- Do not use Playwright coverage to satisfy the Vitest >90% requirement.
- Update docs to distinguish backend pytest coverage, frontend Vitest coverage,
  and optional Playwright browser coverage.

## Test Plan

Run in this order:

1. Script consistency:

   ```bash
   ./test.sh lint
   ./test.sh docs
   ```

2. Backend flake verification:

   ```bash
   backend/venv/bin/python -m pytest \
     backend/tests/test_search_coverage.py::test_search_filters_stale_rows_and_triggers_cleanup -q
   backend/venv/bin/python -m pytest backend/tests/ -q --maxfail=1
   backend/venv/bin/python -m pytest backend/tests/ -q --maxfail=1
   ```

3. Backend coverage:

   ```bash
   backend/venv/bin/python -m pytest backend/tests/ -q \
     --cov=backend \
     --cov-report=term-missing \
     --cov-report=json:backend/coverage.json \
     --cov-fail-under=90
   ```

4. Frontend coverage:

   ```bash
   cd frontend
   pnpm test:unit:coverage
   pnpm run coverage:unit:check
   ```

5. CI-equivalent local gate:

   ```bash
   ./test.sh unit
   ./test.sh full
   ```

If `./test.sh full` is too slow for the implementation loop, run it before final
handoff and document any skipped long-running validation.

## Documentation Updates

- Update `docs/testing/README.md` with the new coverage commands and thresholds.
- Update `docs/testing/TESTING_STRATEGY.md` to mark backend and frontend coverage
  expectations as enforced.
- Regenerate `docs/testing/test-gap-report.md` and `.json` after changing
  `audit_test_matrix.py`.
- Add or update `docs/testing/TEST_CATALOG.md` entries for any new important
  test files.

## Assumptions

- CI quality is prioritized over local convenience.
- Backend threshold means pytest-cov line coverage.
- Frontend threshold means Vitest V8 coverage, not Playwright browser coverage.
- Playwright coverage is useful supplementary signal, not a substitute for
  Vitest coverage.
- Coverage thresholds must be enforced by CI and local `./test.sh unit`; no
  production source may be excluded solely to satisfy coverage.
- Coverage must come from behavior-focused tests. Any unreachable target must be
  documented explicitly instead of hidden by exclusions or weak tests.
