Task: Update backend library replacement research docs based on final project decisions, and propose a separate backend refactor plan for review.

Repo: /home/ubuntu/gallery-repo

Context:
docs/BACKEND_LIBRARY_REPLACEMENT_RESEARCH.md exists from previous research. After review, final decisions were made. Update the doc to reflect them.

Important:
- This is docs/planning only.
- Do NOT refactor backend code.
- Do NOT install dependencies.
- Do NOT modify runtime behavior.

Final agreed decisions to document:

1. Backend refactor + pydantic-settings is Phase 1 priority. Propose module split plan in doc only - do not implement.

2. Tests before replacing logic: path safety, natural sort, metadata parser fixtures, thumbnail guardrails.

3. Search decision: Fuse.js frontend first. SQLite FTS5 only if needed later for large scale. Do NOT prioritize backend search yet.

4. Remove sd-parsers from recommended path. Keep custom parser. It supports more formats (SwarmUI, EasyDiffusion, sidecar) and is project-specific.

5. Cache: keep cachetools. diskcache optional later only if persistent cache needed.

6. pyvips: do NOT prioritize. Keep Pillow unless bottleneck measured.

7. FastAPI: keep. Framework is not the problem.

8. PATH_SAFETY_ROOT safety: preserve current behavior. Document production hardening note.

Required changes to docs/BACKEND_LIBRARY_REPLACEMENT_RESEARCH.md:

1. Update Executive summary to reflect final decisions.
2. Update migration plan to new Phase 1-4 structure.
3. Add "Refactor plan required before implementation" section proposing future module layout.
4. Remove/downgrade sd-parsers from prototype path.
5. Update search section to recommend Fuse.js first, SQLite FTS5 optional later.
6. Add "Final project decision" notes where useful.
7. Add Last reviewed: 2026-06-07.

Proposed module layout for refactor plan (document only, do not implement):

backend/
  main.py (app factory, middleware, startup)
  config.py (pydantic-settings)
  security.py (path safety, PATH_SAFETY_ROOT containment)
  scanner.py (os.scandir, pagination, natural sort)
  thumbnails.py (Pillow rendering, cache helpers)
  metadata_parser.py (SD parsers, EXIF, sidecar)
  cache.py (cachetools wrappers, in-flight dedup)
  routers/
    __init__.py
    scan.py
    image.py
    thumbnail.py
    metadata.py
    open_folder.py
    static.py
  tests/
    test_security.py
    test_scanner.py
    test_metadata_parser.py
    test_thumbnails.py
    test_sort.py

Migration steps (document only):
1. Extract config.py with pydantic-settings, keep same env names.
2. Extract security.py, move is_path_safe, resolve_path.
3. Extract cache.py, move cache objects/locks.
4. Extract scanner.py with scan_directory, helper functions.
5. Extract metadata_parser.py with parser functions.
6. Extract thumbnails.py with render/cache helpers.
7. Create routers/, move route functions.
8. Create tests/, write before each move.
9. In each step: zero behavior change, import from new module, old import path still works.

Risk areas: metadata parser internal structure, cache lock ordering, import cycles, CORS/production middleware.

Do NOT implement this plan now. Only document it.

Verification:
- Docs-only diff expected.
- No backend code changes.
- No new dependencies.
