# Perf Comparison: `evolve/metadata-indexer` vs `main`

> Latest validation: 2026-06-10
> Device: VPS (Linux)
> Frontend: Vite dev (`127.0.0.1:5174`)
> Browser: Playwright Chromium (Desktop Chrome viewport 1280x720)
> Backend: `uvicorn backend.main:app` (`127.0.0.1:4181`)
> Test data: `test mika` album (50 images, 2 subfolders)

## 1. Backend Scan Perf (`scripts/perf_scan.py`, 10 iterations)

| Metric | main (ms) | evolve before Option 2 (ms) | evolve after Option 2 + hardening (ms) | Verdict |
|--------|-----------|------------------------------|-----------------------------------------|---------|
| min    | 23.8      | 40.08                        | 30.08                                   | pass |
| p50    | 125.55    | 145.62                       | 51.19                                   | faster than main |
| p95    | 394.48    | 3,014.55                     | 71.50                                   | resolved |
| max    | 394.48    | 3,014.55                     | 71.50                                   | resolved |
| Budget | PASS      | FAIL (p95 > 500ms)           | PASS (p95 <= 500ms)                     | pass |

The pre-hardening evolve branch had a severe `/api/scan` tail-latency regression: p95 reached 3,014ms. The root cause was SQLite lock contention from metadata indexing and repeated DB initialization work overlapping the scan hot path.

After Option 2 plus hardening, scan p95 is back under budget and below the main baseline.

## 2. Frontend Playwright - Album Open Perf

| Metric | main (ms) | evolve after hardening (ms) | Delta vs main | Verdict |
|--------|-----------|------------------------------|---------------|---------|
| Scan start after click | 131 | 65 | -66 | faster |
| Scan duration | 137 | 287 | +150 | within 500ms budget |
| Scan end after click | 268 | 352 | +84 | within budget |
| Thumb first start | 316 | 364 | +48 | within budget |
| Thumb last end | 1,371 | 673 | -698 | faster |
| Thumb p50 | 505 | 199 | -306 | faster |
| Thumb p95 | 1,042 | 296 | -746 | faster |
| Thumb max | 1,048 | 298 | -750 | faster |
| Verdict | PASS | PASS | - | improvement |

## 3. Frontend Playwright - Lightbox Open

| Metric | main (ms) | evolve after hardening (ms) | Delta vs main | Verdict |
|--------|-----------|------------------------------|---------------|---------|
| Lightbox visible | 687 | 165 | -522 | faster |
| Main image loaded | 1,666 | 1,011 | -655 | faster |
| Image request start | 549 | 131 | -418 | faster |
| Image request duration | 411 | 21 | -390 | faster |
| Metadata duration | 350 | 276 | -74 | faster |
| Used full image? | yes | yes | same | pass |
| Verdict | PASS | PASS | - | improvement |

## 4. Frontend Playwright - Lightbox Transition

| Metric | main (ms) | evolve after hardening (ms) | Delta vs main | Verdict |
|--------|-----------|------------------------------|---------------|---------|
| Next visible | 28 | 23 | -5 | faster |
| Next image loaded | 92 | 58 | -34 | faster |
| Verdict | PASS | PASS | - | improvement |

## 5. Overall Scorecard

| Area | Verdict | Notes |
|------|---------|-------|
| Backend scan p95 | PASS | 71.50ms, below the 500ms budget and main baseline |
| Backend scan p50 | PASS | 51.19ms, faster than main |
| Frontend album open | PASS | Thumbnail p95 improved from 1,042ms to 296ms |
| Lightbox open | PASS | Visible at 165ms, image loaded at 1,011ms |
| Lightbox transition | PASS | Next image loaded at 58ms |
| Playwright tests | PASS | 3/3 passed |

## 6. Conclusion

The `/api/scan` tail-latency regression is resolved. Option 2 keeps scan-discovered metadata paths in a RAM staging queue, and the hardening pass adds leak-safe scan accounting, bounded staging max-wait, worker yield before SQLite writes, SQLite busy retry/backoff, and one-time DB initialization.

Branch `evolve/metadata-indexer` can merge if no new blocker appears in review.

## 7. Known Risks

| Risk | Status |
|------|--------|
| Path stager and metadata worker are daemon threads with no explicit shutdown condition | Acceptable for the app process; can be revisited if graceful worker shutdown becomes a requirement |
| SQLite busy retry/backoff is capped | After retries are exhausted, jobs are marked failed with a clear SQLite busy message where possible |
| Forced staging flush during continuous scans can still create a small spike | Bounded by max-wait plus a small batch limit; latest scan p95 remains well under budget |

## 8. Raw Data

### evolve/metadata-indexer after Option 2 + hardening

```text
Backend scan perf (x10): min=30.08ms, p50=51.19ms, p95=71.50ms, max=71.50ms
Playwright album-open: scan=287ms(1) thumb={count:48, firstStart:364, lastEnd:673, p50:199, p95:296, max:298}
Playwright lightbox: visible=165ms, loaded=1011ms, imgRequest=131ms(+21ms), metadata=276ms
Playwright transition: nextVisible=23ms, nextLoaded=58ms, ratioDiff=0
Playwright: 3/3 passed
```

### evolve/metadata-indexer before Option 2 hardening

```text
Backend scan perf (x10): min=40.08ms, p50=145.62ms, p95=3014.55ms, max=3014.55ms
Playwright album-open: scan=167ms(1) thumb={count:48, firstStart:250, lastEnd:995, p50:347, p95:720, max:722}
Playwright lightbox: visible=482ms, loaded=1383ms, imgRequest=409ms(+388ms), metadata=382ms
Playwright transition: nextVisible=15ms, nextLoaded=64ms, ratioDiff=0
```

### main baseline

```text
Backend scan perf (x10): min=23.8ms, p50=125.55ms, p95=394.48ms, max=394.48ms
Playwright album-open: scan=137ms(1) thumb={count:48, firstStart:316, lastEnd:1371, p50:505, p95:1042, max:1048}
Playwright lightbox: visible=687ms, loaded=1666ms, imgRequest=549ms(+411ms), metadata=350ms
Playwright transition: nextVisible=28ms, nextLoaded=92ms, ratioDiff=0
```
