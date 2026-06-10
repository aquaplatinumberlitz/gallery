from fastapi import HTTPException


class APIError(HTTPException):
    """Custom API error with error type for frontend handling."""
    def __init__(self, status_code: int, error_type: str, detail: str):
        super().__init__(
            status_code=status_code,
            detail={"error": error_type, "message": detail}
        )


class ErrorType:
    NOT_FOUND = "not_found"           # Path/file doesn't exist
    NOT_DIRECTORY = "not_directory"   # Path is not a folder
    PERMISSION_DENIED = "permission"  # No access permission
    INVALID_FILE = "invalid_file"     # Not an image or can't process
    SERVER_ERROR = "server_error"     # Internal server error
