"""Pydantic request and response models shared by gallery API routes."""

import json
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictSearchModel(BaseModel):
    """Forbid unknown fields on canonical search request contracts."""

    model_config = ConfigDict(extra="forbid")


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


class SearchFolderScopeV1(StrictSearchModel):
    """ID-based folder scope that never accepts an absolute client path."""

    kind: Literal["folder"]
    library_id: int = Field(ge=1)
    import_path_id: int = Field(ge=1)
    relative_path: str = Field(default="", max_length=4096)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        """Normalize separators and reject absolute or traversing paths."""
        if "\x00" in value or value.startswith(("/", "\\")):
            raise ValueError("relative_path must be a relative catalog path")
        normalized = value.replace("\\", "/")
        if any(part in {".", ".."} for part in normalized.split("/") if part):
            raise ValueError("relative_path must not contain traversal segments")
        return normalized.strip("/")


class SearchLibraryScopeV1(StrictSearchModel):
    """One registered library search scope."""

    kind: Literal["library"]
    library_id: int = Field(ge=1)


class SearchAllScopeV1(StrictSearchModel):
    """All registered libraries search scope."""

    kind: Literal["all"]


SearchScopeV1 = Annotated[
    SearchFolderScopeV1 | SearchLibraryScopeV1 | SearchAllScopeV1,
    Field(discriminator="kind"),
]


class SearchPromptGroupV1(StrictSearchModel):
    """Stable prompt-group identity used by the D2 index."""

    kind: Literal["positive", "negative"]
    value_id: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")


class PromptUsageQueryRequestV1(StrictSearchModel):
    """Canonical normalized prompt-usage request."""

    polarity: Literal["positive", "negative"]
    scope: SearchScopeV1
    prefix: str | None = Field(default=None, max_length=512)
    text: str | None = Field(default=None, max_length=512)
    sort: Literal["usage", "recent"] = "usage"
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=60, ge=1, le=100)

    @model_validator(mode="after")
    def validate_text_mode(self) -> "PromptUsageQueryRequestV1":
        """Allow at most one normalized prompt-text predicate."""
        if self.prefix is not None and self.text is not None:
            raise ValueError("prefix and text are mutually exclusive")
        return self


class PromptUsageSampleAssetV1(BaseModel):
    """Authorized active-catalog sample for a prompt group."""

    asset_id: int
    library_id: int
    path: str


class PromptUsageItemV1(BaseModel):
    """One normalized positive or negative prompt usage group."""

    value_id: str
    kind: Literal["positive", "negative"]
    text: str
    asset_count: int
    last_asset_mtime_ns: int
    sample_asset: PromptUsageSampleAssetV1


class PromptUsageResponseV1(BaseModel):
    """One opaque keyset page of prompt usage groups."""

    items: list[PromptUsageItemV1]
    next_cursor: str | None = None
    has_more: bool
    returned: int


class RawWorkflowSearchRequestV1(StrictSearchModel):
    """Bounded opt-in raw workflow literal-search request."""

    query: str = Field(min_length=3, max_length=128)
    scope: SearchScopeV1
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=50, ge=1, le=50)


class RawWorkflowSearchItemV1(BaseModel):
    """One authorized active asset matching canonical raw workflow JSON."""

    asset_id: int
    library_id: int
    library_name: str
    path: str
    name: str
    mtime_ns: int


class RawWorkflowSearchResponseV1(BaseModel):
    """One deadline-bounded raw workflow result page and warning metadata."""

    query: str
    items: list[RawWorkflowSearchItemV1]
    next_cursor: str | None = None
    has_more: bool
    returned: int
    warning: str
    capability: dict[str, int]


class SearchWorkflowPredicateV1(StrictSearchModel):
    """Typed workflow predicate shape validated against the D3 registry later."""

    property: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    op: Literal["eq", "prefix", "contains", "gt", "gte", "lt", "lte"]
    value: str | int | float | bool

    @field_validator("value")
    @classmethod
    def validate_scalar_value(cls, value: str | int | float | bool) -> str | int | float | bool:
        """Keep text predicates within the public request bound."""
        if isinstance(value, str) and len(value) > 512:
            raise ValueError("workflow predicate text values are limited to 512 characters")
        return value


class SearchWorkflowGroupV1(StrictSearchModel):
    """Same-node workflow predicate group."""

    node_type: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    predicates: list[SearchWorkflowPredicateV1] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_registry_contract(self) -> "SearchWorkflowGroupV1":
        """Validate the code-owned node/property/type/operator registry."""
        from .workflow_discovery import validate_workflow_groups

        validate_workflow_groups([self])
        return self


class SearchFiltersV1(StrictSearchModel):
    """Structured discovery filters carried by the canonical request."""

    prompt_groups: list[SearchPromptGroupV1] = Field(default_factory=list, max_length=8)
    workflow_groups: list[SearchWorkflowGroupV1] = Field(default_factory=list, max_length=4)


class SearchQueryRequestV1(StrictSearchModel):
    """Canonical Search V2 request shared by API, URLs, and saved searches."""

    schema_version: Literal[1] = 1
    mode: Literal["lexical", "workflow"] = "lexical"
    text: str = Field(default="", max_length=512)
    scope: SearchScopeV1
    filters: SearchFiltersV1 = Field(default_factory=SearchFiltersV1)
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=60, ge=1, le=100)

    @field_validator("cursor")
    @classmethod
    def validate_opaque_cursor(cls, value: str | None) -> str | None:
        """Canonical POST requests only accept opaque keyset cursors."""
        if value is not None and value.isdecimal():
            raise ValueError("decimal search cursors are only supported by the legacy GET adapter")
        return value

    @model_validator(mode="after")
    def validate_decoded_size(self) -> "SearchQueryRequestV1":
        """Reject canonical decoded requests larger than 32 KiB."""
        encoded = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 32 * 1024:
            raise ValueError("decoded search request exceeds 32 KiB")
        return self

    def persistable(self) -> dict:
        """Return the versioned request shape that may be stored or shared."""
        return self.model_dump(mode="json", exclude={"cursor", "limit"})


class RelationReasonCodeV1(str, Enum):
    """Stable, non-probabilistic evidence codes for related assets."""

    SAME_EXACT_SIGNATURE = "same_exact_signature"
    SAME_RECIPE = "same_recipe"
    SAME_GENERATION_FAMILY = "same_generation_family"
    SAME_PROMPT = "same_prompt"
    STRONG_PROMPT_OVERLAP = "strong_prompt_overlap"
    SAME_MODEL_HASH = "same_model_hash"
    SAME_MODEL_NAME = "same_model_name"
    SHARED_LORA = "shared_lora"
    SHARED_RESOURCE = "shared_resource"
    SHARED_WORKFLOW_PROPERTY = "shared_workflow_property"
    SIMILAR_GENERATION_SETTINGS = "similar_generation_settings"
    VISUAL_VARIANT = "visual_variant"


class RelatedSearchRequestV1(BaseModel):
    """Versioned, reference-based request that is never persisted as a search."""

    schema_version: Literal[1] = 1
    reference_asset_id: int = Field(ge=1)
    profile: Literal["related", "recipe", "visual"] = "related"
    scope: SearchScopeV1
    limit: int = Field(default=60, ge=1, le=100)


class RelatedIndexComponentStatusV1(BaseModel):
    """Readiness of one persisted relation component."""

    index_name: Literal["generation_signatures", "visual_fingerprints"]
    state: Literal["not_ready", "ready", "building", "degraded", "failed", "disabled", "unavailable"]
    usable: bool
    indexed_count: int = Field(default=0, ge=0)
    target_count: int = Field(default=0, ge=0)


class RelatedSearchStatusV1(BaseModel):
    """Metadata and visual readiness returned without semantic claims."""

    metadata: RelatedIndexComponentStatusV1
    visual: RelatedIndexComponentStatusV1


class RelatedSearchResultV1(SearchMediaResult):
    """Canonical image row plus explicit metadata or visual relation evidence."""

    relation_tier: Literal[100, 90, 80, 70, 60, 40]
    relation_reasons: list[RelationReasonCodeV1]
    visual_distance: float | None = Field(default=None, ge=0)
    metadata_score: float | None = Field(default=None, ge=0)


class RelatedSearchResponseV1(BaseModel):
    """One bounded related-assets page; v1 deliberately has no cursor."""

    schema_version: Literal[1] = 1
    reference_asset_id: int
    profile: Literal["related", "recipe", "visual"]
    scope: SearchScopeV1
    items: list[RelatedSearchResultV1] = Field(default_factory=list)
    returned: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    status: RelatedSearchStatusV1


class RelatedAPIErrorPayloadV1(BaseModel):
    """Related-assets error detail with optional typed readiness context."""

    error: str
    message: str
    status: RelatedSearchStatusV1 | None = None


class RelatedAPIErrorResponseV1(BaseModel):
    """Typed related-assets error envelope."""

    detail: RelatedAPIErrorPayloadV1


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
