# Documentation

Status: Maintained

Last reviewed: 2026-06-26

Use this page as the entry point for project documentation. Current behavior is
documented in the maintained references below; research and archived documents
provide context but are not sources of truth for the running application.

## Maintained References

- [Architecture](ARCHITECTURE.md) — backend/frontend boundaries, data flow, and runtime contracts.
- [Configuration](CONFIGURATION.md) — backend and frontend environment variables.
- [Metadata Parsing](METADATA_PARSING.md) — supported generators and normalized metadata shape.
- [UI/UX Guidelines](UI_UX_GUIDELINES.md) — responsive layouts, interaction rules, and design tokens.
- [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md) — important integration contracts.
- [Testing](testing/README.md) — test selection, performance testing, catalog, and debug tools.

## Working Documents

- [Active plans](plans/) — proposed, active, or blocked implementation plans only.
- [Reports](reports/README.md) — dated audits and measurement snapshots.
- [Research](research/README.md) — reusable analysis of upstream projects and UX patterns.
- [Archived](archived/README.md) — completed or superseded plans and historical reports.

## Source of truth map

| Topic | Source of truth | Generated? | Check command |
|---|---:|---|---|
| Local/CI test entrypoints | `test.sh` | No | `./test.sh lint`, `./test.sh unit`, `./test.sh docs` |
| Current test counts | `testing/test-gap-report.md` / `.json` | Yes | `./test.sh docs` |
| Test intent/guarantees | `TEST_CATALOG.md` | No | `./test.sh docs` |
| Frontend dependency roles | `THIRD_PARTY_LIBRARIES.md` | No | docs review + `package.json` diff |
| Dependency versions | lockfile / `package.json` | No | package manager |
| Active plans | `docs/plans/` | No | manual review |
| Completed historical plans | `docs/archived/` | No | manual review |

### Rules

- README files are navigation maps, not databases.
- Generated facts (test counts, coverage) live in generated reports.
- Test counts must not be copied into prose docs.
- Dependency versions live in package files, not docs.
- Completed plans must move to `docs/archived/`.
- Archived docs are historical, not current source of truth.

## Lifecycle Rules

- Maintained documents describe current behavior and include a verification date.
- Research documents retain upstream lessons and identify themselves as snapshots.
- Plans use `proposed`, `active`, or `blocked`; completed plans move to `archived/`.
- Reports state whether they are current findings or dated measurement snapshots.
- Archived documents link back to the maintained source of truth when one exists.
