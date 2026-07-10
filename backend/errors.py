"""Shared API error types for structured backend responses."""

from fastapi import HTTPException


class APIError(HTTPException):
    """Custom API error with error type for frontend handling."""

    def __init__(
        self,
        status_code: int,
        error_type: str,
        detail: str,
        *,
        extra: dict | None = None,
    ):
        """Create an HTTP error response with a stable frontend error type."""
        payload: dict = {"error": error_type, "message": detail}
        if extra:
            payload.update(extra)
        super().__init__(status_code=status_code, detail=payload)


class ErrorType:
    """String constants used in APIError payloads."""

    BAD_REQUEST = "bad_request"  # Invalid request parameters
    NOT_FOUND = "not_found"  # Path/file doesn't exist
    NOT_DIRECTORY = "not_directory"  # Path is not a folder
    PERMISSION_DENIED = "permission"  # No access permission
    INVALID_FILE = "invalid_file"  # Not an image or can't process
    VIDEO_TOOL_UNAVAILABLE = "video_tool_unavailable"
    VIDEO_POSTER_FAILED = "video_poster_failed"
    SERVER_ERROR = "server_error"  # Internal server error
    CAPACITY_EXCEEDED = "capacity_exceeded"  # Derivative quota/deferred capacity reached
