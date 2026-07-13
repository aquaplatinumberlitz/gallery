"""Trusted reverse-proxy authentication for backend API routes."""

from __future__ import annotations

import hmac

from fastapi import Request

from . import config
from .errors import APIError, ErrorType

TRUSTED_PROXY_HEADER = "X-Gallery-Proxy-Secret"
MIN_PROXY_SECRET_LENGTH = 32


def validate_trusted_proxy_configuration() -> None:
    """Fail startup closed when production proxy authentication is incomplete."""
    secret = config.GALLERY_TRUSTED_PROXY_SECRET
    if config.PRODUCTION and len(secret) < MIN_PROXY_SECRET_LENGTH:
        raise RuntimeError(
            f"PRODUCTION=1 requires GALLERY_TRUSTED_PROXY_SECRET with at least {MIN_PROXY_SECRET_LENGTH} characters"
        )


def require_trusted_proxy(request: Request) -> None:
    """Require the secret header whenever production or a secret is configured."""
    secret = config.GALLERY_TRUSTED_PROXY_SECRET
    if not config.PRODUCTION and not secret:
        return
    supplied = request.headers.get(TRUSTED_PROXY_HEADER, "")
    if not secret or not hmac.compare_digest(supplied, secret):
        raise APIError(403, ErrorType.PERMISSION_DENIED, "Access denied")
