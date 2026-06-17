"""Path resolution and gallery root containment checks."""

import os
from pathlib import Path

from .config import GALLERY_ROOT


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
    r"""Check that the resolved path is under GALLERY_ROOT.

    Resolves symlinks, blocks path traversal (.., \0, symlink escapes).
    """
    try:
        resolved = path.resolve()
        return GALLERY_ROOT in resolved.parents or resolved == GALLERY_ROOT
    except (RuntimeError, OSError):
        return False
