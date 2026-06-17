"""Pydantic response models shared by gallery API routes."""

from typing import Literal

from pydantic import BaseModel


class FileNode(BaseModel):
    """Folder or image node returned by browsing, scanning, and search endpoints."""

    name: str
    path: str  # absolute path on disk
    type: Literal["folder", "image"]
    has_children: bool
    cover_images: list[str] = []
    mtime: float = 0  # Modified time (Unix timestamp)
    image_count: int = 0  # Number of images in folder (applies to "folder" type only)
    width: int | None = None  # Image width in pixels (only for type="image")
    height: int | None = None  # Image height in pixels (only for type="image")
