"""Pydantic response models shared by gallery API routes."""

from typing import Literal

from pydantic import BaseModel, Field


class FileNode(BaseModel):
    """Folder or media node returned by browsing, scanning, and search endpoints."""

    name: str
    path: str  # absolute path on disk
    type: Literal["folder", "image", "video"]
    has_children: bool
    cover_images: list[str] = Field(default_factory=list)
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


class SearchMediaResult(BaseModel):
    """Canonical active media row returned by gallery search."""

    asset_id: int
    library_id: int
    library_name: str
    name: str
    path: str
    type: Literal["image", "video"]
    parent_path: str
    relative_path: str
    mtime: float
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    mime_type: str | None = None
    match_type: str
    prompt_snippet: str = ""
    model: str = ""
    sampler: str = ""
    seed: str = ""


class SearchAlbumResult(BaseModel):
    """First-page catalog folder suggestion returned by gallery search."""

    library_id: int
    library_name: str
    name: str
    path: str
    type: Literal["folder"] = "folder"
    parent_path: str
    relative_path: str
    mtime: float
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    mime_type: str | None = None
    cover_images: list[str] = Field(default_factory=list)
    image_count: int = 0
    has_children: bool = False
    match_type: str = "filename"
    prompt_snippet: str = ""
    model: str = ""
    sampler: str = ""
    seed: str = ""


class LegacyMetadataSearchResult(BaseModel):
    """Legacy `/api/search-metadata` result backed by an active image asset."""

    asset_id: int
    library_id: int
    library_name: str
    name: str
    path: str
    type: Literal["file"] = "file"
    mtime: float | None = None
    width: int | None = None
    height: int | None = None
    model: str = ""
    sampler: str = ""
    seed: str = ""
    prompt_snippet: str = ""


class SearchResponse(BaseModel):
    """Typed unified search response with legacy grouped projections."""

    query: str
    scope: Literal["folder", "library", "all"]
    root: str
    albums: list[SearchAlbumResult] = Field(default_factory=list)
    photos: list[SearchMediaResult] = Field(default_factory=list)
    videos: list[SearchMediaResult] = Field(default_factory=list)
    prompt: list[SearchMediaResult] = Field(default_factory=list)
    media: list[SearchMediaResult] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    returned: int = 0
    limit: int


class MetadataSearchResponse(BaseModel):
    """Typed legacy metadata search response."""

    query: str
    total: int
    results: list[LegacyMetadataSearchResult] = Field(default_factory=list)


class FacetValue(BaseModel):
    """One facet value and its active-asset count."""

    value: str
    count: int


class FacetResponse(BaseModel):
    """Typed metadata facet aggregation response."""

    tool: list[FacetValue] = Field(default_factory=list)
    model: list[FacetValue] = Field(default_factory=list)
    sampler: list[FacetValue] = Field(default_factory=list)
    scheduler: list[FacetValue] = Field(default_factory=list)
    folders: list[FacetValue] = Field(default_factory=list)
    orientation: list[FacetValue] = Field(default_factory=list)
    seed_availability: list[FacetValue] = Field(default_factory=list)
    metadata_availability: list[FacetValue] = Field(default_factory=list)
    lora: list[FacetValue] = Field(default_factory=list)


class APIErrorPayload(BaseModel):
    """Stable public error payload nested under FastAPI's detail field."""

    error: str
    message: str


class APIErrorResponse(BaseModel):
    """OpenAPI schema for errors raised through `APIError`."""

    detail: APIErrorPayload
