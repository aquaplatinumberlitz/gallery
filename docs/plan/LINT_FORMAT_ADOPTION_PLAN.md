# Lint/Format Adoption Plan

> **Status:** Complete — all phases implemented (Phase 4 remaining)
> **Date:** 2026-06-07
> **Scope:** `frontend/` (ESLint + Prettier), `backend/` + `scripts/` (Ruff)

---

## Measurement Results (Phase 0 Complete)

### Frontend — ESLint

| Metric | Value |
|--------|-------|
| Config | `eslint.config.js` — `@eslint/js`, `typescript-eslint`, `eslint-plugin-vue` (`flat/essential`) |
| Lint command | `pnpm lint` = `eslint "src/**/*.{ts,vue}" "tests/**/*.ts" vite.config.ts playwright.config.ts --max-warnings=0` |
| **Errors** | **0** ✅ — all clean |
| Disabled rules | `no-undef`, `no-unused-vars`, `prefer-const`, `prefer-rest-params`, `@typescript-eslint/no-explicit-any`, `@typescript-eslint/no-empty-object-type`, `@typescript-eslint/no-this-alias` (all `"off"`) |
| Active TS errors | `@typescript-eslint/no-unused-vars` (`"error"` with underscore ignore) |
| Active Vue errors | `vue/multi-word-component-names` (`"off"`) |

**Verdict:** ESLint already clean. The many `"off"` rules mean we're only catching unused-vars. Plenty of room to tighten, but zero noise today.

### Frontend — Prettier

| Metric | Value |
|--------|-------|
| Config | `prettierrc.json` — `printWidth: 120`, `semi: true`, `singleQuote: false`, `trailingComma: "all"` |
| Format command | `pnpm format` = `prettier --write ...` |
| Check command | `bash scripts/check_prettier_changed.sh` |
| **Files differing from format** | **234** |
| Breakdown | 141 `.vue`, 81 `.ts`, 7 `.scss`, 3 `.css`, 1 `.js`, 1 `.html` |

**Verdict:** Mass format would touch 234 files. This is a **huge diff** and must be done in a dedicated commit with zero logic changes.

### Backend — Ruff Lint

| Metric | Value |
|--------|-------|
| Config | `pyproject.toml` — `target-version = "py311"`, `line-length = 120` |
| Select rules | `E4`, `E7`, `E9`, `F`, `B`, `UP`, `I` |
| **Errors** | **89** (79 fixable with `--fix`) |
| Rule breakdown | |

| Rule | Count | Fixable | Type | Notes |
|------|-------|---------|------|-------|
| `F401` | 33 | ✅ | Unused import | Tests heavily affected |
| `I001` | 33 | ✅ | Import unsorted | Most files need import reorg |
| `F841` | 7 | ✅ | Unused variable | All in test files |
| `B904` | 5 | ❓ | raise without `from` | Real bug risk in `thumbnails.py` |
| `B007` | 2 | ❓ | Loop var unused | Tests |
| `B023` | 2 | ❓ | Function var in loop | Tests |
| `E402` | 2 | ❓ | Import not top-level | Test files |
| `UP035` | 2 | ✅ | Deprecated typing | Test files |
| `UP037` | 1 | ✅ | Quoted annotation | Test file |
| `F541` | 1 | ✅ | F-string no placeholder | Test file |
| `E741` | 1 | ❓ | Ambiguous variable | Production file |
| `BLE001` | 1 | ❓ | Blind except | Production file |

**Breakdown by area:**
- Unused imports (`F401`): mostly test boilerplate (pytest, conftest helpers, config constants)
- Import unsorted (`I001`): every test file has mixed stdlib/third-party/local imports
- Unused variable (`F841`): test variable assignments never read
- Production bugs: `B904` (5 locations — missing `raise from` chains), `BLE001` (1 blind `except:`), `E741` (1 ambiguous `l` variable)

### Backend — Ruff Format

| Metric | Value |
|--------|-------|
| **Files to reformat** | **35** (23 app files + 10 test files + 2 scripts) |
| Already formatted | 12 files |
| Formatting scope | All backend `.py`, scripts |

---

## Proposed Plan

### Phase 1 — Quick Wins, Low Noise (Fix Real Bugs)

✅ DONE: commit `5d7061e`

**Goal:** Fix production bugs with minimal diff, no reformatting.

**Changes:**
1. `B904` — Add `raise ... from exc` / `from None` to 5 bare raises in `backend/thumbnails.py`, `backend/watcher.py`, `backend/tests/` (only production locations)
2. `BLE001` — Convert bare `except:` in production file to `except Exception:`
3. `E741` — Rename ambiguous `l` variable

**Files to change:**
- `backend/thumbnails.py` — 1 B904
- `backend/watcher.py` — 1 B904 (if production)
- Possibly 1-2 production files for BLE001/E741

**Commands:**
```bash
ruff check --fix --select B904,BLE001,E741 backend/ start.py
```

**Risk:** Low — these are legitimate bugs. Testing should catch any regression.

**Rollback:** `git checkout -- <files>` if tests fail.

**Move to Phase 2:** Complete.

---

### Phase 2 — Test-Only Unused Import Cleanup

✅ DONE: commit `4b75b7d`

**Goal:** Remove dead imports from test files to reduce noise. Tests only — no production changes.

**Changes:**
- Remove unused `pytest` imports where tests don't use fixtures
- Remove unused config constants (`SCHEDULED_REFRESH_ALLOW_ALL_INDEXED`, `SCHEDULED_REFRESH_MAX_FOLDERS_PER_TICK`, `WATCHER_ROOTS`, etc.)
- Remove unused helpers (`is_image`, `initialize_database` from test imports, etc.)

**Files to change:**
All test files in `backend/tests/` and `scripts/`

**Commands:**
```bash
ruff check --fix --select F401 backend/tests/ scripts/
```

**Risk:** Low. Removing unused test imports can't affect production. Some test files may import fixtures implicitly — verify `pytest` usage before removal.

**Rollback:** `git checkout -- backend/tests/ scripts/`

**Move to Phase 3:** Complete.

---

### Phase 3 — Import Sort + Format (Per-Phase: Advisory → Bulk)

#### Phase 3a — Advisory (Changed-Files-Only Pre-commit)

✅ DONE: commit `674439b` — Prettier bulk format, 234 files

**Goal:** Auto-sort imports and format only files touched by logic changes. Uses pre-commit hook or a script in CI.

**Implementation:**
1. Add a `ruff check --fix --select I001` + `ruff format` step in CI that runs on changed files
2. Or install `pre-commit` with ruff hooks

**Risk:** Minimal — only touches files already being changed. No mass diff.

**Move to Phase 3b:** Complete.

#### Phase 3b — Bullet-Format Commit (Optional)

✅ DONE: commits `2b30775` (Ruff format), `f6133ff` (Ruff lint fix)

**Goal:** One dedicated commit that reformats all remaining files with zero logic changes.

**Commands:**
```bash
# Frontend
cd frontend && pnpm format

# Backend
cd .. && ruff format backend/ scripts/ start.py
ruff check --fix --select I001,F401 backend/ scripts/ start.py
```

**Changeset estimate:**
- Prettier: 234 files (large but mechanical)
- Ruff format: 35 files
- Ruff import sort: ~33 files (overlap with above)
- Ruff unused import removal: ~33 files (overlap)

**Risk:** Git blame pollution for every function in the repo. Use `.git-blame-ignore-revs`:

```bash
echo $(git rev-parse HEAD) >> .git-blame-ignore-revs
```

**Blame ignore note:** `.git-blame-ignore-revs` was added in commit `78d786e`, then later amended/rebased into `40a2a16`.

**Rollback:** `git revert <commit-hash>` — single commit, easy.

**Move to Phase 4:** Complete.

---

### Phase 4 — Tighter Rules

**Goal:** Gradually enable stricter rules once noise baseline is low.

| Rule | When | Reason |
|------|------|--------|
| `@typescript-eslint/no-explicit-any` | Advisory → Phase 4a | Many `any` uses, needs manual audit |
| `vue/component-name-in-template-casing` | Phase 4b | Good practice but touches many files |
| `prefer-const` | Phase 4b | Mechanical fix, but 100+ occurrences |
| `F841` (all files) | Phase 4a | Unused variables in tests already removed |
| `D` (pydocstyle) | Phase 4c | Python docstring enforcement — very noisy |

Each substep follows the same pattern: enable → CI passes with existing code → fix any new errors.

---

### Phase 5 — Enforce in CI

✅ DONE: commit `40a2a16` — added to `scripts/test_all.sh` and `.github/workflows/ci.yml`

**Goal:** Block PRs that introduce lint/format violations.

**Files to create/change:**
- `.github/workflows/lint.yml` (or add to existing)
- In parallel: update `scripts/test_all.sh` to run lint checks

**Commands to add:**
```bash
# Frontend
pnpm lint
pnpm format:check

# Backend
ruff check backend/ scripts/ start.py
ruff format --check backend/ scripts/ start.py
```

**Entry criteria:** Complete for Phase 0–3 and Phase 5. Phase 4 remains separate follow-up work.

**Rollback:** Revert the CI config change — no production impact.

---

## Summary

| Metric | Value |
|--------|-------|
| Frontend ESLint errors | **0** ✅ |
| Frontend Prettier | **All clean** ✅ |
| Backend Ruff lint errors | **0** ✅ |
| Backend Ruff format | **All clean** ✅ |
| Production bugs fixed | **Yes** — Phase 1 complete |
| CI enforcement | **Enabled** — `scripts/test_all.sh` + `.github/workflows/ci.yml` |
| Remaining work | **Phase 4 only** — tighter rules |
| Supporting commits | `bc47c5e` (rename to `docs/plan/`), `c9c0612` (`main.py` import fix), `b38c1e3` (audit follow-up), `40a2a16` (Phase 5 + rebased) |

## Commands Executed

| Command | Result |
|---------|--------|
| `ruff check --fix --select B904,BLE001,E741 backend/ start.py` | ✅ Phase 1 implementation — production bug fixes |
| `ruff check --fix --select F401 backend/tests/ scripts/` | ✅ Phase 2 implementation — test-only unused import cleanup |
| `ruff format backend/ scripts/ start.py` | ✅ Phase 3b implementation — backend/scripts formatting |
| `ruff check --fix --select I001,F401 backend/ scripts/ start.py` | ✅ Phase 3b implementation — import sorting and lint cleanup |
| `cd frontend && pnpm format` | ✅ Phase 3a implementation — Prettier bulk format, 234 files |
| `echo $(git rev-parse HEAD) >> .git-blame-ignore-revs` | ✅ Blame ignore setup added in `78d786e`, later amended/rebased into `40a2a16` |
| `pnpm lint` | ✅ Verification — 0 ESLint errors |
| `pnpm format:check` / `bash scripts/check_prettier_changed.sh` | ✅ Verification — Prettier all clean |
| `ruff check backend/ scripts/ start.py` | ✅ Verification — 0 Ruff lint errors |
| `ruff format --check backend/ scripts/ start.py` | ✅ Verification — Ruff format all clean |
| `scripts/test_all.sh` | ✅ Phase 5 enforcement path updated |
| GitHub Actions `.github/workflows/ci.yml` lint/format steps | ✅ Phase 5 CI enforcement updated |

## Phase 4 (remaining)

Phase 4 is the only remaining work. The baseline is now clean, so tighter ESLint/Ruff rules can be enabled incrementally with focused manual fixes and normal CI enforcement.
