"""Pydantic response models shared by gallery API routes."""

from typing import Literal

from pydantic import BaseModel


class FileNode(BaseModel):
    """Folder or media node returned by browsing, scanning, and search endpoints."""

    name: str
    path: str  # absolute path on disk
    type: Literal["folder", "image", "video"]
    has_children: bool
    cover_images: list[str] = []
    mtime: float = 0  # Modified time (Unix timestamp)
    image_count: int = 0  # Number of images in folder (applies to "folder" type only)
    width: int | None = None  # Image width in pixels (only for type="image")
    height: int | None = None  # Image height in pixels (only for type="image")
    asset_id: int | None = None
    metadata_state: str | None = None
    derivative_ready: dict[str, bool] | None = None


class VideoFileNode(FileNode):
    """Video node with playback metadata unavailable on image/folder nodes."""

    duration_ms: int | None = None
    mime_type: str | None = None
    poster_ready: bool | None = None
