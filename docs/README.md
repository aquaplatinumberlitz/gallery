# Documentation

Status: Maintained

Last reviewed: 2026-06-28

Use this page as the entry point for project documentation. It gives the
project mental model first, then points to maintained references for details.
Current behavior is documented in the maintained references below; research and
archived documents provide context but are not sources of truth for the running
application.

## Project Snapshot

AI Art Gallery is a local-first browser for AI image/video collections. The
backend is FastAPI plus SQLite; it registers local folders as libraries,
discovers media into a catalog, extracts AI generation metadata, builds search
indexes, generates cached WebP derivatives, and reports catalog/file health.
The frontend is Vue 3; it renders the gallery, lightbox, Library Inspector,
library admin, and maintenance workflows through registered-library APIs.

Core runtime services are durable where correctness matters: catalog scan jobs,
metadata indexing jobs, derivative jobs, and integrity-check summaries are
persisted in SQLite so startup recovery can repair or resume interrupted work.
Frontend server state belongs in TanStack Query; Pinia owns UI/navigation
state.

## Mental Model

| Concept | Meaning |
|---|---|
| Library | User-registered collection with one or more ordered import paths and exclusion patterns. |
| Import path | Absolute local folder root scanned as part of a library. |
| Asset | Catalog row for an image or video discovered under a registered import path. |
| Metadata | Normalized AI-generation data extracted from embedded fields or sidecars and stored in SQLite. |
| Metadata job | Durable `metadata_index_jobs` row claimed directly from SQLite by the metadata lifecycle worker. |
| Generated image | User-facing name for thumbnail/preview derivative files backed by derivative jobs/cache rows. |
| Status/health | Catalog status, metadata readiness, derivative coverage, and file-health consistency checks. |

Main flow:

```text
Register library
-> update/rebuild queues catalog jobs
-> catalog writes assets/folders
-> metadata jobs extract prompts/models/resources
-> derivatives warm thumbnail/preview cache
-> browse/search/inspector/status APIs serve the frontend
-> integrity checker records file-health issues and repairs
```

## Where To Go Next

| Need | Read |
|---|---|
| Runtime architecture, routes, data flow, frontend state ownership | [Architecture](ARCHITECTURE.md) |
| Environment variables and defaults | [Configuration](CONFIGURATION.md) |
| Parser precedence, supported generators, normalized metadata shape | [Metadata Parsing](METADATA_PARSING.md) |
| Responsive layout, lightbox, tokens, interaction constraints | [UI/UX Guidelines](UI_UX_GUIDELINES.md) |
| Library/framework integration contracts | [Third-Party Libraries](THIRD_PARTY_LIBRARIES.md) |
| What to test, commands, perf, debug helpers | [Testing](testing/README.md) |

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
