# Phase 4c — Pydocstyle Audit Report

> **Status:** Measurement only. No D rules enabled in `pyproject.toml`. No code changed.

---

## Measurement

### Commands Run

```bash
ruff check --select D backend/ scripts/ start.py
ruff check --select D backend/tests/ --output-format json
```

### Full Results (`backend/` + `scripts/` + `start.py`)

| Metric | Value |
|--------|-------|
| **Total D errors** | **455** |
| Fixable with `--fix` | 35 (7.7%) |

### Breakdown by Rule

| Rule | Count | Description | Verdict |
|------|-------|-------------|---------|
| `D103` | 191 | Missing function docstring | ❌ Too noisy for mid-stage |
| `D102` | 147 | Missing method docstring | ❌ Too noisy for mid-stage |
| `D212` | 28 | Multi-line docstring style | ❌ Style-only |
| `D101` | 27 | Missing class docstring | ⚠️  Maybe enable for public classes |
| `D205` | 27 | Blank line after docstring summary | ❌ Style-only |
| `D100` | 26 | Missing module docstring | ⚠️  Maybe enable for public modules |
| `D403` | 4 | First word capitalization | ❌ Trivial |
| `D104` | 1 | Missing docstring in package `__init__` | ⚠️  Low noise |
| `D107` | 1 | Missing `__init__` docstring | ⚠️  Low noise |
| `D301` | 1 | Use `r"""` for raw docstring | ❌ Trivial |
| `D400` | 1 | Docstring ends with period | ❌ Style-only |
| `D415` | 1 | Docstring first line ends with period | ❌ Style-only |

### Top 15 Noisiest Files

| File | Errors | Type |
|------|--------|------|
| `backend/tests/test_fielded_search_parser.py` | 77 | Test |
| `backend/tests/test_api_integration_metadata_search_facets.py` | 27 | Test |
| `backend/metadata_store.py` | 24 | **Production** |
| `backend/tests/test_api_integration_derivatives.py` | 22 | Test |
| `backend/tests/test_api_integration_scan.py` | 20 | Test |
| `backend/tests/test_warm_folder_listing.py` | 19 | Test |
| `backend/tests/test_library_inspector.py` | 17 | Test |
| `backend/tests/test_derivatives.py` | 15 | Test |
| `backend/tests/test_scheduled_refresh.py` | 15 | Test |
| `backend/tests/test_api_integration_health_and_safety.py` | 14 | Test |
| `backend/tests/test_app.py` | 13 | Test |
| `backend/tests/test_facets.py` | 13 | Test |
| `backend/tests/test_watcher.py` | 13 | Test |
| `backend/tests/test_api_integration_index_status.py` | 12 | Test |
| `backend/tests/test_indexer_staging.py` | 12 | Test |

**Test files** account for **~90%** of all D errors.

### Production-Only Noise (excluding `backend/tests/`)

Without tests, most D rules produce <30 errors total. Module docstrings (`D100`) and class docstrings (`D101`) are the largest remaining noise sources.

---

## Analysis

### 1. Do NOT enable `D` globally

- 455 errors is massive noise for a mid-stage project
- 90%+ are in test files — forcing docstrings on tests is value-negative
- Many are auto-generated test functions (parameterized tests, fixtures) where docstrings add no value

### 2. Tests should be excluded from any D enforcement

Test function names are often self-documenting (e.g. `test_search_returns_200_for_valid_query`). Adding `"""Test search returns 200 for valid query."""` is cargo-cult documentation.

### 3. The 3 production errors worth considering

Without tests, the most impactful rules are:

| File | Issue | Worth fixing? |
|------|-------|---------------|
| `app.py` | Missing module docstring | ⚠️  Low — one-liner `"""FastAPI application entry point."""` |
| `config.py` | Missing module docstring | ⚠️  Low — one-liner `"""Application configuration and constants."""` |
| `app.py` | `profile_middleware` | ⚠️  Medium — a 1-line description would help |

### 4. Recommended minimal subset (if any)

If enforcement is desired at all, the only sane subset is:

```toml
[tool.ruff.lint.per-file-ignores]
"backend/tests/*" = ["D"]

[tool.ruff.lint]
select = ["D"]  # only if combined with per-file-ignores
ignore = ["D10[0-9]", "D20[0-9]", "D3[0-9][0-9]", "D40[0-9]"]  # ignore almost everything
```

But even this is not recommended for mid-stage.

---

## Low-Noise Policy Recommendation

### Do

- Add module-level docstrings *opportunistically* when working on a file (no dedicated pass)
- Add class/function docstrings for complex public APIs when the purpose is non-obvious
- Use `# noqa: D100` / `# noqa: D103` for functions where the name is self-documenting

### Don't

- Do NOT add `"""Test ..."""` on every test function
- Do NOT add docstrings that merely repeat the function name (`"""Get the root path."""` on `get_root_path()`)
- Do NOT enable D rules in CI/pyproject.toml now

### Future

- If/when the project stabilizes and grows contributors, enable a very narrow subset:
  - `D100` (module docstring) for public API modules
  - `D101` (class docstring) for public data models
  - `D107` (init docstring) for complex constructors
  - Exclude `backend/tests/*` entirely

---

## Summary

| Item | Value |
|------|-------|
| Total D errors | 455 |
| Test file noise | ~410 (90%) |
| Production noise | ~45 (10%) |
| Fixable | 35 (7.7%) |
| Enable D now? | **No** |
| Code changed | **No** — measurement only |

## Appendix: Test-only noise example

```bash
ruff check --select D backend/tests/ 2>&1 | wc -l
# ~410 errors, mostly D103/D102 on test functions
```
