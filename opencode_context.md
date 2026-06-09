# Task: Fix start.py + main.py import mode + cleanup private imports

## Critical Issues

### Issue 1: start.py runs uvicorn from BACKEND_DIR with "main:app"
`start.py:215-216`:
```python
backend_cmd = [str(python_exec), "-m", "uvicorn", "main:app", "--reload", "--host", "127.0.0.1", "--port", str(backend_port)]
backend_process = subprocess.Popen(backend_cmd, cwd=BACKEND_DIR, env=backend_env)
```

Problem: When cwd=BACKEND_DIR and running `uvicorn main:app`, Python imports main.py as a top-level module. main.py tries `from .app import app` (relative import) which fails. Falls back to `from app import app`. But app.py has `from .config import ...` and other relative imports that ONLY work when app.py is imported as part of the `backend` package.

Fix: Change to use package import from ROOT_DIR:
```python
backend_cmd = [str(python_exec), "-m", "uvicorn", "backend.main:app", "--reload", "--host", "127.0.0.1", "--port", str(backend_port)]
backend_process = subprocess.Popen(backend_cmd, cwd=ROOT_DIR, env=backend_env)
```

### Issue 2: backend/main.py __main__ block also uses "main:app"
`backend/main.py:20`:
```python
uvicorn.run("main:app", host=host, port=port_val, reload=reload_flag)
```

When running `python backend/main.py`, this tries to find "main:app" which refers to itself as a module, but relative imports may fail. Fix:
```python
uvicorn.run("backend.main:app", host=host, port=port_val, reload=reload_flag)
```

### Issue 3: metadata_store imports private (_prefixed) helpers from metadata_extract
Read both files and rename the private helpers that metadata_store imports to public names (remove underscore prefix), or create public wrapper functions. Specifically check what `_prefixed` functions/constants are imported from metadata_extract into metadata_store and make them public.

## Files to read
- backend/start.py (lines 215-216)
- backend/main.py (line 20)
- backend/metadata_extract.py
- backend/metadata_store.py

## Verification
After fixing:
```bash
# Test package import from ROOT_DIR (start.py mode)
cd /home/ubuntu/gallery-repo && backend/.venv_linux/bin/python -c "from backend.main import app; print('package import OK')"

# Test metadata endpoint still works
cd /home/ubuntu/gallery-repo && backend/.venv_linux/bin/python -c "
from backend.metadata_parse import parse_metadata
from pathlib import Path
result = parse_metadata(Path('test-images/a1111/civitai_132553033.png'))
print('metadata OK:', result.get('tool'), result.get('width'), result.get('height'))
"

# Run pytest
backend/.venv_linux/bin/python -m pytest backend/tests/ -v
```

## Do NOT change
- API behavior
- Frontend
- Any file not listed above or the verification finds

## After verification
```bash
git add -A && git commit -m "fix: use package import mode and cleanup private imports" && git push origin main
```
