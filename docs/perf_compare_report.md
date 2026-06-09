# Perf Comparison: `evolve/metadata-indexer` vs `main`

> Run: 2026-06-07
> Device: VPS (Linux)
> Frontend: Vite dev (port 4173) via nginx
> Browser: Playwright Chromium (Desktop Chrome viewport 1280×720)
> Backend: `uvicorn backend.main:app`
> Test data: `test mika` album (50 images, 2 subfolders)

## 1. Backend Scan Perf (`scripts/perf_scan.py`, 10 iterations)

| Metric | main (ms) | evolve/metadata-indexer (ms) | Δ (ms) | Verdict |
|--------|-----------|------------------------------|--------|---------|
| min    | 23.8      | 40.08                        | +16.28 | ⚠️ slower |
| p50    | 125.55    | 145.62                       | +20.07 | ⚠️ slower |
| p95    | 394.48    | 3,014.55                     | +2,620 | 🔴 REGRESSION |
| max    | 394.48    | 3,014.55                     | +2,620 | 🔴 REGRESSION |
| Budget | ✅ PASS   | ❌ FAIL (p95 > 500ms)        | —      | — |

**Notes:** The evolve branch has severe tail-latency issues on the scan endpoint. The first few calls were fast (40–100ms), but random calls exceeded 3s. This suggests the background metadata indexer (`metadata_store.py` with SQLite writes) is causing occasional lock contention or I/O blocking on scan requests.

## 2. Frontend Playwright — Album Open Perf

| Metric | main (ms) | evolve/metadata-indexer (ms) | Δ (ms) | Verdict |
|--------|-----------|------------------------------|--------|---------|
| Scan start after click | 131 | 60 | **−71** | ✅ faster |
| Scan duration | 137 | 167 | +30 | ⚠️ slower |
| Scan end after click | 268 | 227 | **−41** | ✅ faster |
| Thumb first start | 316 | 250 | **−66** | ✅ faster |
| Thumb last end | 1,371 | 995 | **−376** | ✅ faster |
| Thumb p50 | 505 | 347 | **−158** | ✅ faster |
| Thumb p95 | 1,042 | 720 | **−322** | ✅ faster |
| Thumb max | 1,048 | 722 | **−326** | ✅ faster |
| **Verdict** | ✅ PASS | ✅ PASS | — | **IMPROVEMENT** |

**Notes:** Despite scan endpoint tail-latency regression, the actual Playwright test shows IMPROVED album open performance. Thumbnail loading is significantly faster (p95 −322ms, max −326ms). The scan itself started earlier (131→60ms) and finished earlier (268→227ms), likely due to the metadata cache warmup.

## 3. Frontend Playwright — Lightbox Open

| Metric | main (ms) | evolve/metadata-indexer (ms) | Δ (ms) | Verdict |
|--------|-----------|------------------------------|--------|---------|
| Lightbox visible | 687 | 482 | **−205** | ✅ faster |
| Main image loaded | 1,666 | 1,383 | **−283** | ✅ faster |
| Image request start | 549 | 409 | **−140** | ✅ faster |
| Image request duration | 411 | 388 | **−23** | ✅ faster |
| Metadata duration | 350 | 382 | +32 | ⚠️ slower |
| Used full image? | ✅ yes | ✅ yes | — | same |
| **Verdict** | ✅ PASS | ✅ PASS | — | **IMPROVEMENT** |

**Notes:** Lightbox opens 205ms faster and full image loads 283ms faster on the evolve branch.

## 4. Frontend Playwright — Lightbox Transition

| Metric | main (ms) | evolve/metadata-indexer (ms) | Δ (ms) | Verdict |
|--------|-----------|------------------------------|--------|---------|
| Next visible | 28 | 15 | **−13** | ✅ faster |
| Next image loaded | 92 | 64 | **−28** | ✅ faster |
| **Verdict** | ✅ PASS | ✅ PASS | — | **IMPROVEMENT** |

## 5. Overall Scorecard

| Area | Verdict | Notes |
|------|---------|-------|
| 🎯 Frontend album open | **✅ IMPROVED** | Thumbnails 322ms faster p95, scan starts 71ms earlier |
| 🎯 Lightbox open | **✅ IMPROVED** | Visible 205ms faster, image 283ms faster |
| 🎯 Lightbox transition | **✅ IMPROVED** | Next image 28ms faster |
| 🔴 Backend scan p50 | ⚠️ +20ms | Acceptable slowdown |
| 🔴 Backend scan p95 | **🔴 REGRESSION (+2,620ms)** | Tail latency blew budget — likely SQLite write contention |
| 📊 All Playwright tests | ✅ 6/6 passed | Both branches pass all budgets |
| 📊 Scan perf budget | ❌ 0/2 passed | evolve branch failed (p95 > 500ms) |

## 6. Recommendations

1. **🔴 Investigate scan tail latency.** The metadata indexer likely performs SQLite writes (`upsert_metadata_batch` / `upsert_scan_cache`) that block or slow the scan endpoint. Options:
   - Move metadata writes to a background thread/queue (run-sync-in-thread)
   - Use WAL mode for SQLite (`PRAGMA journal_mode=WAL`)
   - Reduce write frequency (batch every N images instead of per-scan)
   - Add a timeout/circuit-breaker on metadata writes during scan

2. **✅ Frontend is fine.** All user-facing perf metrics improved. The metadata indexer is helping thumbnail loading (cache warmup).

3. **Don't merge yet.** The scan perf regression needs fixing before merging to main.

## 7. Raw Data

### evolve/metadata-indexer
```
Playwright album-open: scan=167ms(1) thumb={count:48, firstStart:250, lastEnd:995, p50:347, p95:720, max:722}
Playwright lightbox:  visible=482ms, loaded=1383ms, imgRequest=409ms(+388ms), metadata=382ms
Playwright transition: nextVisible=15ms, nextLoaded=64ms, ratioDiff=0
Scan perf (×10):      min=40, p50=145, p95=3014, max=3014
```

### main
```
Playwright album-open: scan=137ms(1) thumb={count:48, firstStart:316, lastEnd:1371, p50:505, p95:1042, max:1048}
Playwright lightbox:  visible=687ms, loaded=1666ms, imgRequest=549ms(+411ms), metadata=350ms
Playwright transition: nextVisible=28ms, nextLoaded=92ms, ratioDiff=0
Scan perf (×10):      min=23, p50=125, p95=394, max=394
```
