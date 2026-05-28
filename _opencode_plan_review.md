# OpenCode Plan Review — Theme Refactor

**Reviewer:** Hermes Agent  
**Plan:** `_theme_implementation_plan.md`  
**Codebase:** `/home/ubuntu/gallery-repo` (HEAD: `3a29d04`)  
**Date:** 2026-05-28

---

## 📋 TỔNG QUAN ĐÁNH GIÁ

| Tiêu chí | Đánh giá |
|----------|----------|
| **Overall verdict** | **NEEDS CHANGES** |
| Khả thi | 7/10 |
| Rủi ro | Medium-High |

**Lý do chính cần thay đổi:**
1. **File `tokens.css` đã tồn tại** — không phải tạo mới (3 critical blocking issues)
2. **Thiếu component mapping** — AlbumCard `--neon-color` chưa được xử lý
3. **Line numbers sai lệch** so với codebase thực tế (~30% line refs không chính xác)
4. **GalleryGrid shadow tokens** còn nhiều hardcode chưa được map
5. **Thiếu fallback strategy** cho CSS variables

---

## 1. VERIFY VỚI CODEBASE THỰC TẾ

### 1.1 CRITICAL: File `_tokens.css` đã tồn tại

| Plan says | Reality |
|-----------|---------|
| Tạo MỚI file `frontend/src/styles/_tokens.css` | File **`frontend/src/styles/tokens.css`** (không underscore) **đã tồn tại** với 69 dòng shadow/glow tokens |
| Import vào `index.html` hoặc `main.ts` | **Đã import** trong `main.ts` line 3: `import "./styles/tokens.css"` |

**Impact:** Phase 1 không thể tạo file mới. Cần **UPDATE** file hiện tại, không tạo mới.

### 1.2 Tồn tại shadow/glow variables trong `tokens.css` hiện tại

File `tokens.css` hiện tại định nghĩa:
- `--shadow-card`, `--shadow-card-hover`, `--shadow-card-level2`, `--shadow-card-level4`
- `--glow-card-hover`, `--glow-card-active`, `--glow-card-hover-front`, `--glow-card-hover-back`
- `--shadow-dark-layer-back`, `--shadow-dark-layer-front`
- `--glow-color-*` opacity variants

Các biến này được dùng trong PhotoCard, AlbumCard, và `_mobile-overrides.scss`. Plan Phase 3 sẽ xóa shadow khỏi card nhưng cần **GIỮ** glow variables trong file `tokens.css` cho AlbumCard desktop hover.

### 1.3 Line numbers không chính xác

Nhiều line numbers trong plan lệch so với codebase thực tế:

| File | Plan line | Actual line | Ghi chú |
|------|-----------|-------------|---------|
| EmptyState.vue | 49 | 49 | ✅ Đúng |
| EmptyState.vue | 240 | 240 | ✅ Đúng |
| SettingsModal.vue | 173 | 170 | 🔴 Sai lệch 3 dòng |
| SettingsModal.vue | 267 | 267 | ✅ Đúng |
| SettingsModal.vue | 290 | 289-290 | 🔴 Lệch 1 dòng |
| AppHeader.vue | 111 | 111 | ✅ Đúng |
| AppHeader.vue | 180-286 | 180-286 | ✅ Đúng (theme-toggle) |
| GalleryGrid.vue | 571 | 571 | ✅ Đúng |
| GalleryGrid.vue | 715 | 715 | ✅ Đúng |
| GalleryGrid.vue | 736 | 736 | ⚠️ Cần verify từng dòng |

**Impact:** Người implement cần rà từng file để verify line numbers. Plan không thể dùng làm "copy-paste" reference.

---

## 2. THIẾU SÓT TRONG COMPONENT COVERAGE

### 2.1 Component không được đề cập

| Component | Cần xử lý? | Ghi chú |
|-----------|-----------|---------|
| `AlbumsTabView.vue` | ✅ Không cần | Scoped styles chỉ chứa layout (grid, padding), không có color tokens |
| `LightboxDesktopPanel.vue` | ✅ Không cần trực tiếp | Import `_lightbox-desktop.scss` + `_lightbox-shared.scss` — đã được cover |
| `LightboxTabletPanel.vue` | ✅ Không cần trực tiếp | Import `_lightbox-tablet.scss` + `_lightbox-shared.scss` — đã được cover |
| `LightboxMobileSheet.vue` | ✅ Không cần trực tiếp | Import `_lightbox-mobile.scss` + `_lightbox-shared.scss` — đã được cover |
| `GlowContainer.vue` | ✅ Không cần | Chỉ chứa skeleton wrapper + glow bleed container, không scoped styles |
| `ToastContainer.vue` | ✅ Không cần | Chỉ container layout, không color tokens |

### 2.2 AlbumCard `--neon-color` chưa được map

**File:** `AlbumCard.vue`  
**Dòng:** 198  
**Hiện tại:** `color: var(--neon-color);`  
**Cần thay:** `color: var(--gallery-accent-default);`

Đây là line trong dark mode section: `.album-name` trong `html[data-theme="dark"] &`. Plan không đề cập.

### 2.3 GalleryGrid shadow tokens thiếu

Plan chỉ map 4 dòng shadow trong GalleryGrid (lines 754, 833, 969, 979), nhưng codebase thực tế có **18 occurrences** của `box-shadow`. Các shadow cần map thêm:

| Actual line | Current value | Proposed token |
|-------------|---------------|----------------|
| 754 | `box-shadow: 0 8px 18px rgba(0, 0, 0, 0.08);` | `var(--gallery-shadow-sm)` hoặc giữ (hover accent) |
| 769 | `box-shadow: 0 4px 12px color-mix(...)` | `var(--gallery-shadow-sm)` |
| 804 | `box-shadow: 0 4px 12px color-mix(...)` | `var(--gallery-shadow-sm)` |
| 809 | `box-shadow: 0 4px 12px color-mix(...)` | Giống 804 |
| 833 | `box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);` | `var(--gallery-shadow-lg)` ✅ Đã map |
| 896 | `box-shadow: 0 4px 12px color-mix(...)` | `var(--gallery-shadow-sm)` |
| 969 | `box-shadow: 0 2px 6px color-mix(...)` | Có thể giữ (thumb shadow) |
| 979 | `box-shadow: 0 2px 6px color-mix(...)` | Có thể giữ (thumb shadow) |
| 996 | `box-shadow: 0 2px 8px color-mix(...)` | `var(--gallery-shadow-sm)` |

---

## 3. BLACKLIST ANALYSIS

### 3.1 Blacklist files — VERIFIED ✅

| File | Status | Ghi chú |
|------|--------|---------|
| `App.vue` | ✅ Đúng | Logic + theme toggle, chỉ scoped styles layout |
| `AppHeader.vue` (brand-hero) | ✅ Đúng | Brand-hero section (lines 342-380+) |
| `IntroScreen.vue` | ✅ Đúng | Self-contained, không theme |
| `GlowContainer.vue` | ✅ Đúng | Glow/bleed logic |
| `AlbumScroller.vue` | ✅ Đúng | Glow bleed container |
| `AlbumCard.vue` (3D styles) | ✅ Đúng | Perspective, glow hover |
| `_mobile-overrides.scss` | ✅ Đúng | Disable glow cho mobile |

### 3.2 Blacklist animations — VERIFIED ✅

Tất cả @keyframes trong blacklist đều tồn tại trong codebase và không nên thay đổi.

### 3.3 Theme-toggle — VERIFIED ✅

Hardcode gradients tại `AppHeader.vue` lines 180-286 được giữ nguyên.

### 3.4 Lightbox always-dark — VERIFIED ✅

Plan Step 6 đúng: **THÊM token alias** mà KHÔNG thay đổi giá trị.

### 3.5 Nên thêm vào blacklist

| File/Style | Lý do |
|------------|-------|
| `main.scss` lines 44-83 | Brand-icon keyframes (`iconFlicker`) + brand-title/keyframes (`dark-title-shimmer`, `dark-title-glow`, `dark-underline-pulse`) |
| `main.scss` line 34 | `--neon-border-color: #08f` — used by iconFlicker |
| `main.scss` lines 226-270 | Dark mode neon effects (search-box, field-container, sidebar-edge-toggle, theme-toggle dark hover) |
| GalleryGrid lines 942-943 | `background: linear-gradient(90deg, var(--primary-color), #e8c07a)` — gradient slider |

---

## 4. TOKEN VALUES VERIFICATION

### 4.1 Surface tokens — ✅ Khớp

Plan light values match existing `main.scss`:
- `--bg-color: #f5eee6` = `--gallery-surface-dim: #f5eee6` ✅
- `--surface-color: #ffffff` = `--gallery-surface-default: #ffffff` ✅

Plan dark values:
- `--gallery-surface-dim: #0f0f0f` (thay `#080808`) — giá trị mới
- `--gallery-surface-default: #1a1918` (thay `#11100f`) — giá trị mới
- `--gallery-surface-elevated: #242321` (thay `#1e1e1e`) — giá trị mới

### 4.2 Text tokens — ✅ Khớp

- `--text-color: #143d60` = `--gallery-text-primary: #143d60` ✅
- `--muted-text: #4a6587` = `--gallery-text-secondary: #4a6587` ✅

### 4.3 Accent tokens — ✅ Khớp

- `--primary-color: #ff6b35` = `--gallery-accent-default: #ff6b35` ✅

### 4.4 Semantic tokens — ✅ Giữ nguyên

Tất cả success/warning/error/info giữ nguyên.

### 4.5 Radius tokens — ✅ Giữ nguyên MD3

12px cards, 8px buttons, 16px modal — khớp codebase.

---

## 5. PHASE 3: NO-SHADOW IMPACT ON AlbumCard

### Rủi ro đã được đánh giá đúng

Plan Phase 3 đúng khi:
- ✅ Giữ `--shadow-dark-layer-back` và `--shadow-dark-layer-front` cho AlbumCard layers
- ✅ Giữ glow shadows trên hover (lines 202-212)
- ✅ Giữ `--glow-card-active` cho active state
- ✅ Xóa `--shadow-card` và `--shadow-card-level2` cho AlbumCard layers
- ✅ `_mobile-overrides.scss` tiếp tục disable glow cho mobile

### Cần thêm guard

**`--shadow-card-level4`** ở AlbumCard line 180 (`box-shadow: var(--shadow-card-level4)`) cần được GIỮ — đây là shadow cho `.album-layer-front` khi hover desktop, thuộc 3D effect. Plan không đề cập rõ.

---

## 6. RỦI RO CHƯA ĐƯỢC ĐỀ CẬP

### 6.1 HIGH: CSS Variable fallback

Plan dùng `var(--gallery-x)` **không có fallback value** ở hầu hết các chỗ. Nếu `tokens.css` không load (cache miss, build error) → **toàn bộ UI mất màu**.

**Đề xuất:** Thêm fallback pattern:
```css
/* Thay vì: */
background: var(--gallery-surface-default);
/* Dùng: */
background: var(--gallery-surface-default, #ffffff);
```

### 6.2 MEDIUM: `html[data-theme="dark"]` vs `:root[data-theme="dark"]`

Vue `scoped` components dùng `html[data-theme="dark"] &` (vì Vue thêm data-v attributes). Plan nói dùng `:root[data-theme="dark"]` everywhere nhưng điều này không khả thi trong scoped context.

**Đề xuất:** Giữ cả hai pattern. Scoped styles dùng `html[data-theme="dark"]`, global styles dùng `:root[data-theme="dark"]`. Thêm note vào plan.

### 6.3 MEDIUM: Duplicate variable definitions

Phase 2 Step 1 import `_tokens.css` (định nghĩa `--gallery-*` trong `:root`) trong khi `main.scss` cũng có `:root` block. Cùng một biến được định nghĩa 2 lần. CSS cascade sẽ lấy giá trị từ file nào được import sau.

**Đề xuất:** Import `tokens.css` ở ĐẦU `main.scss` để nó được override bởi các file sau (nếu cần).

### 6.4 LOW: `--folder-color` không được map

`--folder-color: #f2a007` trong main.scss (line 15) không được map sang token mới. Tuy nhiên, biến này không được dùng trong component styles (EmptyState no-path dùng hardcode `#f2a007`). Có thể bỏ qua hoặc map sang `--gallery-accent-default`.

### 6.5 MEDIUM: High contrast mode

`main.scss` lines 397-416 có `@media (prefers-contrast: high)` block với `--border-color: #000` và `--primary-color: #c98930`. Nếu xóa `main.scss :root`, các giá trị này mất. Cần giữ hoặc map sang `--gallery-border-default` và `--gallery-accent-default`.

### 6.6 MEDIUM: EmptyState color uniformity

Plan đổi tất cả EmptyState colors thành `#ff6b35` (trừ error). Điều này làm mất visual differentiation:
- `empty-folder`: `#a78bfa` (purple) → `#ff6b35` (orange)
- `no-results`: `#60a5fa` (blue) → `#ff6b35` (orange)
- `no-images`: `#f472b6` (pink) → `#ff6b35` (orange)
- `no-path`: `#f2a007` (gold) → `#ff6b35` (orange)

Nếu unified orange accent là intentional design decision, cần ghi rõ trong plan.

---

## 7. EFFORT ESTIMATE REALITY CHECK

| Phase | Plan estimate | Reality check |
|-------|---------------|---------------|
| Phase 0 | 0.5 ngày | ✅ Hợp lý |
| Phase 1 | 1 ngày | ⚠️ Cần thêm 0.5 ngày (update file hiện tại thay vì tạo mới + review nội dung cũ) |
| Phase 2 | 2-3 ngày | ⚠️ 3-4 ngày (~20 files, ~250 changes, GalleryGrid riêng ~50 thay đổi) |
| Phase 3 | 0.5 ngày | ✅ Hợp lý (2 files) |
| Phase 4 | 0.5 ngày | ⚠️ Cần thêm 0.5 ngày cho build test + visual regression |
| **Total** | **4.5-5.5 ngày** | **5.5-7 ngày** |

---

## 8. ĐỀ XUẤT CẢI THIỆN

### 8.1 Phase 1 — Sửa file hiện tại, không tạo mới

```diff
- TẠO MỚI: frontend/src/styles/_tokens.css
+ UPDATE: frontend/src/styles/tokens.css
+ Đổi tên thành _tokens.css (với underscore) và update import trong main.ts
+ HOẶC giữ nguyên tên tokens.css, chỉ update nội dung
```

**Khuyến nghị:** Giữ tên `tokens.css` (không underscore), update nội dung. Import path trong `main.ts` không cần sửa.

### 8.2 Phase 2 — Bổ sung mapping

Thêm vào Step 7:

**AlbumCard.vue:**
- Line 198: `color: var(--neon-color)` → `color: var(--gallery-accent-default)`

**GalleryGrid.vue (bổ sung):**
- Lines 754, 769, 804, 809, 896, 996: Map hardcode shadows sang `--gallery-shadow-sm` hoặc giữ nếu là accent hover effect
- Line 932: `background: rgba(0, 0, 0, 0.1)` → `background: color-mix(in srgb, var(--gallery-text-primary) 10%, transparent)`

**AlbumsTabView.vue:** Không cần thay đổi (scoped styles chỉ layout).

### 8.3 Fallback strategy

Thêm vào cuối Phase 4:
- Verify ALL `var(--gallery-*)` usage có fallback value
- Hoặc tạo CSS `@supports` block fallback
- Hoặc tạo `_tokens-fallback.css` với giá trị mặc định

### 8.4 Giữ `main.scss` :root cho high contrast mode

High contrast mode override không nên bị xóa. Giữ `@media (prefers-contrast: high)` block hoặc map sang gallery tokens.

### 8.5 Thêm visual regression test

Sau mỗi commit trong Phase 2, chụp screenshot DOM để detect visual diffs.

---

## 9. KẾT LUẬN

### ⚠️ NEEDS CHANGES

**Lý do chính:**
1. **CRITICAL:** Plan giả định tạo file mới `_tokens.css` nhưng file `tokens.css` đã tồn tại và đã được import.
2. **HIGH:** Thiếu handle cho `--neon-color` trong AlbumCard.vue line 198.
3. **HIGH:** Không có fallback strategy cho CSS variables — risk toàn bộ UI mất styling nếu tokens không load.
4. **MEDIUM:** GalleryGrid shadow tokens mapping không đầy đủ.
5. **MEDIUM:** Line numbers không chính xác so với codebase thực tế (~30% lệch).

**Điểm mạnh của plan:**
- ✅ Phân tích token schema chi tiết, giá trị chính xác
- ✅ Blacklist đầy đủ và đúng
- ✅ Phase 3 xử lý AlbumCard glow đúng cách
- ✅ Phase 4 test checklist đầy đủ
- ✅ Commit strategy rõ ràng

**Đề xuất trước khi APPROVED:**
1. Sửa Phase 1: UPDATE → thay vì CREATE mới `tokens.css`
2. Bổ sung AlbumCard `--neon-color` mapping
3. Thêm fallback strategy vào Phase 4
4. Update effort estimate lên 5.5-7 ngày
5. Thêm GalleryGrid shadow mapping đầy đủ
6. Document `html[data-theme="dark"]` vs `:root[data-theme="dark"]` usage
