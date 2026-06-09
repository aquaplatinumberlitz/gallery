try:
    from .app import app
except ImportError:
    from app import app

if __name__ == "__main__":
    import os as _os

    import uvicorn

    from config import PRODUCTION

    port_env = _os.getenv("PORT")
    try:
        port_val = int(port_env) if port_env else 8000
    except ValueError:
        port_val = 8000

    host = "0.0.0.0" if PRODUCTION else "127.0.0.1"
    reload_flag = not PRODUCTION
    uvicorn.run("backend.main:app", host=host, port=port_val, reload=reload_flag)
