"""Path resolution and path safety root containment checks."""

import os
from pathlib import Path

from .config import PATH_SAFETY_ROOT


class InvalidPathError(ValueError):
    """Raised when an external path cannot be safely resolved."""


def resolve_path(raw_path: str | Path) -> Path:
    """Resolve a user-supplied path.

    Handles Windows extended-length paths to reduce MAX_PATH issues with deep folders.
    """
    raw_text = str(raw_path)
    if "\0" in raw_text:
        raise InvalidPathError("Path contains an embedded NUL byte")
    p = Path(raw_text)
    try:
        return p.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        if os.name == "nt":
            # Add \\?\ prefix to support paths >260 chars
            extended = Path(r"\\?\\" + str(p))
            try:
                return extended.resolve()
            except (OSError, RuntimeError, ValueError) as windows_exc:
                raise InvalidPathError("Path could not be resolved") from windows_exc
        raise InvalidPathError("Path could not be resolved") from exc


def is_path_safe(path: Path) -> bool:
    r"""Check that the resolved path is under PATH_SAFETY_ROOT.

    Resolves symlinks, blocks path traversal (.., \0, symlink escapes).
    """
    try:
        resolved = path.resolve()
        return PATH_SAFETY_ROOT in resolved.parents or resolved == PATH_SAFETY_ROOT
    except (RuntimeError, OSError):
        return False
