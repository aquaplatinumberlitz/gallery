# Task: Fix metadata 500 error

The backend refactor broke /api/metadata. The error is:
```
File "backend/metadata_store.py", line 380, in upsert_metadata_result
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
NameError: name 'json' is not defined
```

Read `backend/metadata_store.py` and find what imports are missing.
The function `upsert_metadata_result()` uses `json.dumps()` at line 380 but `json` is not imported.
Also check for any other missing imports in ALL backend files that were just refactored.

Do a complete audit:
1. Check every backend .py file for NameError-causing missing imports
2. Fix ALL missing imports
3. Run `cd /home/ubuntu/gallery-repo && backend/.venv_linux/bin/python -c "
from backend.app import app
from backend.metadata_parse import parse_metadata
from pathlib import Path
result = parse_metadata(Path('/home/ubuntu/gallery-repo/test-images/a1111/civitai_132553033.png'))
print('OK:', result.get('tool'), result.get('width'), result.get('height'))
"` to verify
4. Only after verification: git add -A && git commit -m "fix: add missing imports in refactored backend modules" && git push origin main
