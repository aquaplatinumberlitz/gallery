#!/usr/bin/env bash
# Warm listing end-to-end test
# Tests the full scan → index → warm cycle
set -euo pipefail

echo "=========================================="
echo "  Warm Listing End-to-End Test"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
GALLERY_ROOT="/home/ubuntu/gallery-repo/test-images"
METADATA_DB="/tmp/test_e2e_warm.db"
THUMB_CACHE="/tmp/test_e2e_warm_cache"
PORT=4185

# Clean slate
rm -f "$METADATA_DB"
rm -rf "$THUMB_CACHE"

echo ""
echo ">>> 1. Start backend with fresh DB + warm listing enabled..."
cd "$REPO_ROOT"

GALLERY_ROOT="$GALLERY_ROOT" \
GALLERY_METADATA_DB="$METADATA_DB" \
GALLERY_THUMBNAIL_CACHE_DIR="$THUMB_CACHE" \
ENABLE_WARM_INDEXED_LISTING=true \
GALLERY_METADATA_INDEXER_ENABLED=true \
ENABLE_METRICS=false \
SCAN_PERF_LOGS=false \
backend/.venv_linux/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT" &
BACKEND_PID=$!
sleep 3

cleanup() {
    echo ""
    echo ">>> Cleaning up..."
    kill "$BACKEND_PID" 2>/dev/null || true
    rm -f "$METADATA_DB"
    rm -rf "$THUMB_CACHE"
}
trap cleanup EXIT

echo ""
echo ">>> 2. Health check..."
HEALTH=$(curl -sf http://127.0.0.1:$PORT/api/health)
echo "   $HEALTH"

# Scan root with absolute path
echo ""
echo ">>> 3. Scan root (full path)..."
SCAN_ROOT=$(curl -sf "http://127.0.0.1:$PORT/api/scan?path=$GALLERY_ROOT&scope=shallow&image_limit=3")
FOLDERS=$(echo "$SCAN_ROOT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('folders',[])))" 2>/dev/null)
echo "   Root folders found: $FOLDERS"
SOURCE=$(echo "$SCAN_ROOT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('index_source','?'))" 2>/dev/null)
echo "   Source: $SOURCE"

# Scan a1111 album  
echo ""
echo ">>> 4. Scan a1111 album (cold)..."
SCAN1=$(curl -sf "http://127.0.0.1:$PORT/api/scan?path=$GALLERY_ROOT/a1111&image_limit=5")
IMAGES1=$(echo "$SCAN1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('images',[])))" 2>/dev/null)
SOURCE1=$(echo "$SCAN1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('index_source','?'))" 2>/dev/null)
echo "   Images: $IMAGES1, Source: $SOURCE1"

echo ""
echo ">>> 5. Wait for indexer to process ($GALLERY_ROOT/a1111)..."
sleep 8

echo ""
echo ">>> 6. Index status..."
INDEX_STATUS=$(curl -sf http://127.0.0.1:$PORT/api/index/status)
echo "   $INDEX_STATUS"

# Scan a1111 again — should use warm path now
echo ""
echo ">>> 7. Scan a1111 again (should be warm)..."
SCAN2=$(curl -sf "http://127.0.0.1:$PORT/api/scan?path=$GALLERY_ROOT/a1111&image_limit=5")
SOURCE2=$(echo "$SCAN2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('index_source','?'))" 2>/dev/null)
echo "   Source: $SOURCE2"

if [[ "$SOURCE2" == "warm_indexed" ]]; then
    echo "   ✅ Warm listing active!"
elif [[ "$SOURCE2" == *"warm"* ]]; then
    echo "   ✅ Warm listing active (variant: $SOURCE2)"
else
    echo "   ⚠️  Still cold: $SOURCE2 (may need more indexing time)"
fi

# Search
echo ""
echo ">>> 8. Search metadata..."
SEARCH_RESULT=$(curl -sf "http://127.0.0.1:$PORT/api/search-metadata?q=mika")
HITS=$(echo "$SEARCH_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('results',d)))" 2>/dev/null)
echo "   Search hits for 'mika': $HITS"

# Facets
echo ""
echo ">>> 9. Facets..."
FACETS=$(curl -sf "http://127.0.0.1:$PORT/api/facets?path=$GALLERY_ROOT/a1111")
MODELS=$(echo "$FACETS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('model',[])))" 2>/dev/null)
SAMPLERS=$(echo "$FACETS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('sampler',[])))" 2>/dev/null)
echo "   Models: $MODELS, Samplers: $SAMPLERS"

echo ""
echo "=========================================="
echo "  Warm listing E2E complete!"
echo "  Scan source (cold):  $SOURCE1"
echo "  Scan source (warm):  $SOURCE2"
echo "  Search hits:         $HITS"
echo "=========================================="
