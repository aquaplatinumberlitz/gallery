# TanStack DB Foundation

TanStack DB is installed as a minimal, reversible foundation. It complements TanStack Query rather than replacing the existing state model.

Responsibilities:

- TanStack Query remains responsible for API fetching, cache timing, retries, and refetch behavior.
- TanStack DB collections and live queries are for local reactive querying across data that has been loaded into collections.
- Pinia remains responsible for UI and navigation state such as current folders, history, modal/lightbox state, loading flags, and user interaction state.

Do not migrate the core gallery scan flow, infinite image loading, folder tree, unified search, lightbox metadata, PhotoSwipe integration, virtual grid behavior, or Pinia gallery store shape as part of this foundation.

TanStack DB is beta. Adopt it incrementally behind small, low-risk collection pilots and keep each usage easy to remove.

Current runtime collection:

- Landing pages: safe pilot. `/api/landing-pages` returns the complete scoped list and each row is keyed by stable `url`.

Reviewed but not adopted:

- Folder tree, scan, and infinite loading stay in plain TanStack Query. Folder tree expansion uses path-scoped `/api/folders`, and scan/infinite loading use path-scoped `/api/scan`; these request-specific responses are not safe Query Collection full-state scopes.
- Search stays in plain TanStack Query. Search responses are filtered subsets rather than complete collection state.
- Lightbox metadata stays in plain TanStack Query. It is a per-image document fetch, not a collection/live-query use case.

Possible future collection candidates require stable row keys and a complete state definition for their endpoint scope before implementation: structured settings/preferences, metadata admin tables, duplicate finder results, broken image audits, and import history.
