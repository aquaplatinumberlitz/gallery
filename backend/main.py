"""Expose the configured FastAPI app for Uvicorn and local execution."""

from .app import app as app  # explicit re-export for uvicorn target backend.main:app

if __name__ == "__main__":
    import os as _os

    import uvicorn

    from .config import LOCAL_MODE, PRODUCTION

    port_env = _os.getenv("PORT")
    try:
        port_val = int(port_env) if port_env else 4701
    except ValueError:
        port_val = 4701

    # Local mode is single-user: never listen beyond loopback and never auto-reload.
    host = "127.0.0.1" if LOCAL_MODE else "0.0.0.0"
    reload_flag = not (PRODUCTION or LOCAL_MODE)
    uvicorn.run("backend.main:app", host=host, port=port_val, reload=reload_flag)
