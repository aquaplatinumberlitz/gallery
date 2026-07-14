"""Canonical folder/library/all scope resolution shared by search and facets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import APIError, ErrorType
from .files import is_index_excluded_path
from .metadata_store import _DB_LOCK, _connect, initialize_database, list_libraries
from .metadata_store.identity import active_catalog_file_sql, catalog_import_path_owns_sql
from .metadata_store.path_utils import canonicalize_catalog_path, catalog_path_contains
from .models import SearchAllScopeV1, SearchFolderScopeV1, SearchLibraryScopeV1, SearchScopeV1

CanonicalSearchScope = Literal["folder", "library", "all"]
SearchScopeInput = Literal["current", "folder", "library", "all"]


@dataclass(frozen=True)
class SearchScopeContext:
    """Authorized canonical search/facet scope."""

    kind: CanonicalSearchScope
    library_id: int | None = None
    library_name: str | None = None
    folder_path: str | None = None
    import_path_id: int | None = None
    relative_path: str | None = None


def _library_by_id(libraries: list[dict], library_id: int) -> dict:
    library = next((item for item in libraries if int(item["id"]) == library_id), None)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return library


def _import_paths(library: dict) -> list[str]:
    return [canonicalize_catalog_path(item["path"]) for item in library.get("import_paths", [])]


def _import_path_records(library: dict) -> list[tuple[int, str]]:
    return [(int(item["id"]), canonicalize_catalog_path(item["path"])) for item in library.get("import_paths", [])]


def _relative_catalog_path(import_root: str, folder_path: str) -> str:
    relative = Path(folder_path).relative_to(import_root)
    return "" if str(relative) == "." else relative.as_posix()


def _require_catalog_folder(library_id: int, import_root: str, folder_path: str) -> None:
    """Require a folder represented by an indexed folder row or active descendants."""
    if folder_path == import_root:
        return
    initialize_database()
    active_file = active_catalog_file_sql(fi_alias="descendant")
    import_owned = catalog_import_path_owns_sql(
        library_id_sql="descendant.library_id",
        path_sql="descendant.path",
    )
    prefix = folder_path + os.sep
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            f"""
            SELECT 1
            FROM file_index AS folder
            WHERE folder.library_id = :library_id
              AND folder.path = :folder_path
              AND folder.type = 'folder'
            UNION ALL
            SELECT 1
            FROM file_index AS descendant
            WHERE descendant.library_id = :library_id
              AND substr(descendant.path, 1, :prefix_length) = :prefix
              AND {active_file}
              AND {import_owned}
            LIMIT 1
            """,
            {
                "library_id": library_id,
                "folder_path": folder_path,
                "prefix": prefix,
                "prefix_length": len(prefix),
            },
        ).fetchone()
    if row is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Folder not found in catalog")


def resolve_search_scope(
    scope: SearchScopeInput,
    *,
    library_id: int | None,
    path: str | None,
) -> SearchScopeContext:
    """Resolve legacy/current input into an authorized canonical scope."""
    kind: CanonicalSearchScope = "folder" if scope == "current" else scope
    libraries = list_libraries()

    if kind == "all":
        return SearchScopeContext(kind="all")

    if kind == "library":
        if library_id is None:
            raise APIError(422, ErrorType.BAD_REQUEST, "library_id is required for library scope")
        library = _library_by_id(libraries, library_id)
        return SearchScopeContext(
            kind="library",
            library_id=library_id,
            library_name=str(library["name"]),
        )

    selected_library: dict | None = None
    if library_id is not None:
        selected_library = _library_by_id(libraries, library_id)

    if path is not None and path.strip():
        if not Path(path).is_absolute():
            raise APIError(422, ErrorType.BAD_REQUEST, "Folder path must be absolute")
        folder_path = canonicalize_catalog_path(path)
    else:
        if selected_library is None:
            selected_library = libraries[0] if libraries else None
        roots = _import_paths(selected_library) if selected_library is not None else []
        if not roots:
            raise APIError(422, ErrorType.BAD_REQUEST, "path required for folder scope")
        folder_path = roots[0]

    if selected_library is None:
        candidates = [
            (library, root)
            for library in libraries
            for root in _import_paths(library)
            if catalog_path_contains(root, folder_path)
        ]
        if candidates:
            selected_library, _root = max(candidates, key=lambda item: len(Path(item[1]).parts))

    if selected_library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Folder is outside registered libraries")

    roots = _import_paths(selected_library)
    owning_roots = [root for root in roots if catalog_path_contains(root, folder_path)]
    if not owning_roots:
        raise APIError(404, ErrorType.NOT_FOUND, "Folder is outside the selected library")
    import_root = max(owning_roots, key=lambda root: len(Path(root).parts))
    if is_index_excluded_path(folder_path, import_root, selected_library.get("exclusion_patterns", [])):
        raise APIError(404, ErrorType.NOT_FOUND, "Folder is excluded from the selected library")

    _require_catalog_folder(int(selected_library["id"]), import_root, folder_path)

    import_path_id = next(path_id for path_id, root in _import_path_records(selected_library) if root == import_root)
    return SearchScopeContext(
        kind="folder",
        library_id=int(selected_library["id"]),
        library_name=str(selected_library["name"]),
        folder_path=folder_path,
        import_path_id=import_path_id,
        relative_path=_relative_catalog_path(import_root, folder_path),
    )


def resolve_search_v2_scope(scope: SearchScopeV1) -> SearchScopeContext:
    """Resolve a canonical ID-based request into an authorized catalog scope."""
    libraries = list_libraries()
    if isinstance(scope, SearchAllScopeV1):
        return SearchScopeContext(kind="all")

    library = _library_by_id(libraries, scope.library_id)
    if isinstance(scope, SearchLibraryScopeV1):
        return SearchScopeContext(
            kind="library",
            library_id=scope.library_id,
            library_name=str(library["name"]),
        )

    if not isinstance(scope, SearchFolderScopeV1):  # pragma: no cover - discriminated Pydantic union
        raise APIError(422, ErrorType.BAD_REQUEST, "Unsupported search scope")
    import_path = next(
        (item for item in library.get("import_paths", []) if int(item["id"]) == scope.import_path_id),
        None,
    )
    if import_path is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Import path not found in selected library")
    import_root = canonicalize_catalog_path(import_path["path"])
    folder_path = canonicalize_catalog_path(Path(import_root, *scope.relative_path.split("/")))
    if not catalog_path_contains(import_root, folder_path):
        raise APIError(404, ErrorType.NOT_FOUND, "Folder is outside the selected import path")
    if is_index_excluded_path(folder_path, import_root, library.get("exclusion_patterns", [])):
        raise APIError(404, ErrorType.NOT_FOUND, "Folder is excluded from the selected library")
    _require_catalog_folder(scope.library_id, import_root, folder_path)
    return SearchScopeContext(
        kind="folder",
        library_id=scope.library_id,
        library_name=str(library["name"]),
        folder_path=folder_path,
        import_path_id=scope.import_path_id,
        relative_path=scope.relative_path,
    )
