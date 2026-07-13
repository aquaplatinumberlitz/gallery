"""Canonical folder/library/all scope resolution shared by search and facets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .errors import APIError, ErrorType
from .files import is_index_excluded_path
from .metadata_store import list_libraries
from .metadata_store.path_utils import canonicalize_catalog_path, catalog_path_contains

CanonicalSearchScope = Literal["folder", "library", "all"]
SearchScopeInput = Literal["current", "folder", "library", "all"]


@dataclass(frozen=True)
class SearchScopeContext:
    """Authorized canonical search/facet scope."""

    kind: CanonicalSearchScope
    library_id: int | None = None
    library_name: str | None = None
    folder_path: str | None = None


def _library_by_id(libraries: list[dict], library_id: int) -> dict:
    library = next((item for item in libraries if int(item["id"]) == library_id), None)
    if library is None:
        raise APIError(404, ErrorType.NOT_FOUND, "Library not found")
    return library


def _import_paths(library: dict) -> list[str]:
    return [canonicalize_catalog_path(item["path"]) for item in library.get("import_paths", [])]


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

    return SearchScopeContext(
        kind="folder",
        library_id=int(selected_library["id"]),
        library_name=str(selected_library["name"]),
        folder_path=folder_path,
    )
