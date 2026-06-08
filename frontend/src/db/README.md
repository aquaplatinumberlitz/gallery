# TanStack DB Foundation

TanStack DB is installed as a minimal, reversible foundation. It complements TanStack Query rather than replacing the existing state model.

Responsibilities:

- TanStack Query remains responsible for API fetching, cache timing, retries, and refetch behavior.
- TanStack DB collections and live queries are for local reactive querying across data that has been loaded into collections.
- Pinia remains responsible for UI and navigation state such as current folders, history, modal/lightbox state, loading flags, and user interaction state.

Do not migrate the core gallery scan flow, infinite image loading, folder tree, unified search, lightbox metadata, PhotoSwipe integration, virtual grid behavior, or Pinia gallery store shape as part of this foundation.

TanStack DB is beta. Adopt it incrementally behind small, low-risk collection pilots and keep each usage easy to remove.

