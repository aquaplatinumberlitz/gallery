"""Path resolution and path safety root containment checks."""

import os
from pathlib import Path

from .config import PATH_SAFETY_ROOT


def resolve_path(raw_path: str) -> Path:
    """Resolve a user-supplied path.

    Handles Windows extended-length paths to reduce MAX_PATH issues with deep folders.
    """
    p = Path(raw_path)
    try:
        return p.resolve()
    except OSError:
        if os.name == "nt":
            # Add \\?\ prefix to support paths >260 chars
            extended = Path(r"\\?\\" + str(p))
            return extended.resolve()
        raise


def is_path_safe(path: Path) -> bool:
    r"""Check that the resolved path is under PATH_SAFETY_ROOT.

    Resolves symlinks, blocks path traversal (.., \0, symlink escapes).
    """
    try:
        resolved = path.resolve()
        return PATH_SAFETY_ROOT in resolved.parents or resolved == PATH_SAFETY_ROOT
    except (RuntimeError, OSError):
        return False
