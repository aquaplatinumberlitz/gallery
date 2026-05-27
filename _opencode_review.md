# OpenCode Review: Extended Mobile UX Proposal (Codex)

**File reviewed:** `_mobile_ux_proposal_extended.md` (1529 dòng)  
**Proposal cơ sở:** `_mobile_refactor_proposal.md` (318 dòng)  
**Codebase đối chiếu:** AlbumCard, PhotoCard, AlbumScroller, GalleryGrid, GlowContainer, tokens.css, main.scss, useDevice, MobileHeader, MobileFloatingBottomBar, BottomNavigationBar, LightboxMobileSheet, SkeletonLoader  
**Ngày review:** 2026-05-27

---

## 1. TỔNG QUAN

Codex đã phân tích kỹ lưỡng và đưa ra proposal chất lượng cao. 85% nội dung là chính xác và khả thi. Tuy nhiên có **6 vấn đề thiếu sót/mâu thuẫn quan trọng** và **4 đề xuất cần cải tiến** được trình bày dưới đây.

---

## 2. XÁC NHẬN ĐÚNG & KHẢ THI

### ✅ Architecture: Không tách component riêng
**Quyết định đúng.** Template giống nhau hoàn toàn giữa desktop và mobile (xác nhận qua đọc code AlbumCard.vue, PhotoCard.vue). Media queries + `_mobile-overrides.scss` là phương án tối ưu. Không tạo `MobileAlbumCard.vue` riêng.

### ✅ Hex palette: Giữ nguyên
**Đúng.** `tokens.css` + `main.scss` có palette Pastel Dreamscape phù hợp mobile. Không cần token riêng.

### ✅ Bỏ glow 6-layer trên mobile
**Đúng.** `tokens.css` lines 36-59 xác nhận 6-layer glow (`--glow-card-hover`). Trên OLED mobile đây là GPU killer.

### ✅ Touch targets 44px
**Đúng.** Xác nhận codebase:
- `mh-btn`: 38px (line 116-117 MobileHeader.vue) → dưới spec
- `mbb-btn`: 36px (line 77-78 MobileFloatingBottomBar.vue) → dưới spec
- GalleryGrid `nav-btn`: 32px tại 767px (line 1044-1045) → dưới spec
- `AlbumScroller` scroll-btn: 42px (line 270-271) → borderline

### ✅ main.scss đã có touch-target rules (lines 425-443) nhưng loại trừ `.hamburger-btn` và `.settings-btn`
Codex đúng khi yêu cầu loại bỏ exclusion này.

### ✅ BottomNavigationBar chưa được tích hợp
Xác nhận: `grep BottomNavigationBar App.vue` = 0 kết quả. Chưa được import.

### ✅ `_mobile-overrides.scss` chưa tồn tại
Xác nhận: file không có trong `frontend/src/styles/`.

---

## 3. VẤN ĐỀ THIẾU SÓT NGHIÊM TRỌNG

### 🚨 P0: Bỏ sót PhotoCard JS hover handlers (không fix bằng CSS được)

**File:** `PhotoCard.vue` lines 30-50  
**Code phát hiện:**
```typescript
const onMouseEnter = () => {
  isHovering.value = true;
  if (!isAnimated.value) return;
  hoverTimer = setTimeout(() => {
    shouldPlay.value = true;
    previewSrc.value = props.src ? getImageUrl(props.src) : "";
  }, 150);
};
```

- `@mouseenter` và `@mouseleave` **fire trên mobile touch** (touch devices thường emit mouse events sau touch).
- Hàm `onMouseEnter` gọi `getImageUrl()` (tải full-resolution image) trên touch — **gây lãng phí băng thông và bộ nhớ di động**.
- **Codex không đề cập vấn đề này.** Chỉ fix CSS hover là không đủ — cần JS guard.

**Fix cần thiết:** Thêm `if (window.matchMedia('(hover: none)').matches) return;` ở đầu `onMouseEnter`, hoặc dùng `useDevice()` composable.

### 🚨 P1: Bỏ sót SkeletonLoader.vue

**File:** `SkeletonLoader.vue` lines 70-84  
**Code phát hiện:**
```scss
.shimmer-wave {
  animation: shimmer 1.5s infinite;
}
```

- `SkeletonLoader` có `@keyframes shimmer` riêng (khác với PhotoCard's shimmer-wave).
- Được dùng trong `GalleryGrid.vue` lines 329-337 cho skeleton loading state.
- **Codex không đề cập.** Skeleton shimmer cũng cần tắt trên mobile.
- SkeletonLoader không hề nằm trong danh sách file cần modify của Codex.

### 🚨 P1: `prefers-reduced-motion` đã có global — proposal đề xuất thừa

**File:** `main.scss` lines 413-422  
**Code phát hiện:**
```scss
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- Codex đề xuất thêm `prefers-reduced-motion` vào từng component (Section 5.3).
- **Không cần** — global rule đã dùng `*` selector bao phủ mọi element.
- Gây confusion và code duplication.

### 🚨 P2: `albumScrollerIn` animation gây jank khi snap-scroll

**Proposal:** Section 10.3, `AlbumScroller.vue`:
```scss
.album-grid > * {
  animation: albumScrollerIn 350ms ease both;
}
```

- Animation này chạy **mỗi lần element mount**. Với `RecycleScroller` (virtual scrolling), items mount/unmount khi scroll → mỗi lần snap scroll sẽ trigger animation lại → **giật, jank**.
- **Chỉ nên dùng cho initial load**, không phải cho mỗi item. Cần guard bằng class `animation-played` hoặc dùng `animation` chỉ khi item visible lần đầu.

### 🚨 P2: `--shadow-card` proposed quá tối thiểu

**Proposal:** Section 10.4 → `--shadow-card: 0 1px 2px rgba(0,0,0,0.10)`

- Current (tokens.css line 5): `0 1px 2px rgba(0,0,0,0.3), 0 1px 3px 1px rgba(0,0,0,0.15)`
- Proposed opacity 0.10 là **rất nhẹ**. Trên màn hình OLED với background `#080808` (dark mode), shadow 0.10 gần như vô hình.
- **Đề xuất thay thế:** `0 1px 3px rgba(0,0,0,0.20)` cho light mode và `0 1px 3px rgba(0,0,0,0.50)` cho dark mode.
- Giữ MD3 Level 1 aesthetics nhưng vẫn có depth cảm nhận được.

---

## 4. VẤN ĐỀ CẢI TIẾN & TRANH LUẬN

### ⚡ 4.1 Bỏ glow hoàn toàn — Nên giữ glow rất nhẹ

**Codex:** "Zero glow on mobile"

**OpenCode:** Cơ bản đồng ý, nhưng đề xuất **giữ 1-layer glow rất nhẹ** (4px spread thay vì 50px):
```css
:root[data-theme="dark"] {
  /* Thay vì none */
  --glow-card-hover: 0 0 4px var(--glow-color-20);
}
```

Lý do:
- 6-layer glow (50px spread) → GPU killer ✅ BỎ
- 1-layer glow (4px spread, opacity 0.2) → GPU cost ~ tương đương 1 `box-shadow` thường ✅ GIỮ
- Brand identity: Dark mode gallery KHÔNG có glow sẽ quá flat so với bản PC
- Không phải "tất cả hoặc không có gì" — có thể tối ưu thay vì xóa bỏ

### ⚡ 4.2 Media query selector quá phức tạp

**Proposal:** `@media (hover: none) and (pointer: coarse), (max-width: 767px)`

Vấn đề:
- `(hover: none)` bao gồm tablets (iPad, iPad Pro) — có thể không mong muốn
- `(pointer: coarse)` loại trừ stylus devices
- **Giải pháp đơn giản hơn:** Dùng `(max-width: 767px)` cho layout overrides, và `@media (hover: none)` riêng cho hover-specific fixes. Tránh kết hợp phức tạp không cần thiết.

Hoặc đơn giản nhất: chỉ dùng `(max-width: 767px)` — nó bao phủ tất cả điện thoại, tablets nhỏ.

### ⚡ 4.3 GlowContainer auto-disable strategy

**Proposal:** Import `useDevice` vào GlowContainer để auto-disable.

**OpenCode:** Cách này tạo dependency không cần thiết. GalleryGrid.vue đã có `props.isMobile` — chỉ cần:
```vue
<GlowContainer :disabled="isMobile" :bleed="0">
```
Thay vì:
```vue
<GlowContainer :bleed="16">
```

Hiện tại GalleryGrid dùng `:bleed="props.isMobile ? 16 : 50"` — bleed 16px vẫn gây horizontal scroll nguy hiểm. Nên chuyển sang `disabled` prop với bleed=0.

### ⚡ 4.4 BottomNavigationBar — thiếu animation spec

Proposal nói sẽ tích hợp BottomNavigationBar nhưng không đề cập animation khi chuyển tab. Cần spec:
- Tab transition mượt (opacity cross-fade 200ms)
- Icon + label highlight animation
- Scroll-to-top khi chuyển tab

---

## 5. BREAKPOINT INCONSISTENCY — Còn tồn tại

Codex's `_mobile_refactor_proposal.md` (Section 1.6) đã phát hiện:

| Location | Breakpoints |
|----------|-------------|
| `useDevice.ts` | compact <480, phone <768, tablet <1024 |
| `_mobile_ux_plan.md` | 640px (outdated) |
| AlbumScroller.vue | 767px, 480px |
| AlbumCard.vue | 767px, 480px |
| GalleryGrid.vue | 1024px, 767px, 480px |
| main.scss | 1024px, 767px |

**Trạng thái hiện tại:** Extended proposal vẫn dùng raw pixel values (767px, 480px). **Không** giải quyết vấn đề dùng `useDevice` constants trong media queries (vì SCSS không thể đọc JS runtime constants).  
**Giải pháp thực tế:** Chấp nhận raw pixel values nhưng chuẩn hóa thành SCSS variables/mixins:
```scss
$bp-phone: 767px;
$bp-compact: 480px;
$bp-tablet: 1024px;
```

---

## 6. COMPONENT COVERAGE GAP ANALYSIS

| Component | Codex đề cập? | Mức độ | Ghi chú |
|-----------|--------------|--------|---------|
| AlbumCard.vue | ✅ Có | Đầy đủ | Flat stack, 0 glow, 0 hover |
| PhotoCard.vue | ✅ Có | **Thiếu JS** | CSS đúng, nhưng bỏ sót JS hover handlers |
| AlbumScroller.vue | ✅ Có | Khá tốt | Cần guard mount animation |
| GalleryGrid.vue | ✅ Có | Tốt | Nav-btn touch targets, sort sheet |
| GlowContainer.vue | ✅ Có | Tốt | Disable strategy OK |
| MobileHeader.vue | ✅ Có | Tốt | 44px touch target fix |
| MobileFloatingBottomBar.vue | ✅ Có | Tốt | 44px fix |
| BottomNavigationBar.vue | ✅ Có | Tốt | Integration spec |
| **SkeletonLoader.vue** | ❌ **KHÔNG** | **Bỏ sót** | Shimmer animation cần tắt |
| **AppHeader.vue** | ⚠️ Có (trong refactor proposal) | Cơ bản | Brand animation removal |
| **Breadcrumb.vue** | ❌ KHÔNG | Thấp | Ít impact |
| **EmptyState.vue** | ❌ KHÔNG | Thấp | Kiểm tra nhanh |
| **LightboxMobileSheet.vue** | ⚠️ Có (Phase 3) | Cơ bản | Spring animation pending |
| **SkeletonLoader** shimmer | ❌ **KHÔNG** | **CAO** | Cần fix |

---

## 7. PHASE PRIORITY — ĐÁNH GIÁ & ĐỀ XUẤT SỬA

### Phase hiện tại của Codex:

| Phase | Nội dung | Effort |
|-------|----------|--------|
| 1 | CSS resets, hover guards, glow kill | ~2h |
| 2 | Bottom nav, albums tab, sort sheet | ~4-6h |
| 3 | Gestures, polish, reduced-motion | ~4-6h |

### Đề xuất sửa:

**Phase 1 — Zero-Touch Resets (2.5h)** ← +30 phút

| # | File | Thay đổi | Time |
|---|------|----------|------|
| 1 | `_mobile-overrides.scss` (NEW) | Global hover/glow/touch resets | 45min |
| 2 | `main.scss` | Import overrides, body gradient | 15min |
| 3 | `AlbumCard.vue` | Mobile block — kill 3D, glow | 30min |
| 4 | `PhotoCard.vue` | Mobile block — kill hover + **JS guard** | 30min |
| 5 | `PhotoCard.vue` | **JS: Guard onMouseEnter với `(hover: none)`** | 10min |
| 6 | `AlbumScroller.vue` | Zero glow bleed, **fix mount animation** | 20min |
| 7 | `GalleryGrid.vue` | Nav-btn touch targets, footer | 15min |
| 8 | `GlowContainer.vue` | `disabled` prop usage | 10min |

**Phase 1a — Bổ sung SkeletonLoader (10 phút)**

| # | File | Thay đổi | Time |
|---|------|----------|------|
| 9 | `SkeletonLoader.vue` | Static gradient thay vì shimmer trên mobile | 10min |

**Phase 2 — UX Enhancement (4-6h)** ← giữ nguyên

| # | File | Thay đổi | Time |
|---|------|----------|------|
| 10 | `BottomNavigationBar.vue` | Integrate App.vue | 2h |
| 11 | `AlbumsTabView.vue` (NEW) | Albums tab component | 1.5h |
| 12 | `GalleryGrid.vue` | Sort bottom sheet | 1.5h |
| 13 | `main.scss` | Touch-target exclusion fix | 30min |

**Phase 3 — Polish (3-4h)** ← giảm do redundant prefers-reduced-motion

| # | File | Thay đổi | Time |
|---|------|----------|------|
| 14 | `LightboxMobileSheet.vue` | Spring animation | 1h |
| 15 | `GalleryGrid.vue` | Pull-to-refresh | 2h |
| 16 | `Lightbox.vue` | Swipe dismiss | 2h |
| 17 | **Bỏ** | prefers-reduced-motion per component | **0h** (global đã có) |

### Thay đổi mấu chốt:
- **Bỏ** Phase 3.17 (prefers-reduced-motion per component) — global rule đã đủ
- **Thêm** PhotoCard JS guard vào Phase 1 (P0)
- **Thêm** SkeletonLoader shimmer fix (Phase 1a)
- **Sửa** AlbumScroller mount animation thành initial-only

---

## 8. KẾT LUẬN

### Khả thi tổng thể: ✅ **95%** — Proposal chất lượng, có thể implement.

### Các vấn đề cần sửa trước khi merge:

| Mức độ | Vấn đề | File | Fix |
|--------|--------|------|-----|
| 🔴 **P0** | PhotoCard JS hover touch leak | `PhotoCard.vue` | Guard `onMouseEnter` với `matchMedia('(hover: none)')` |
| 🟠 **P1** | SkeletonLoader shimmer | `SkeletonLoader.vue` | Static gradient trên mobile |
| 🟠 **P1** | prefers-reduced-motion redundant | proposal | Bỏ Section 5.3 khỏi implementation plan |
| 🟡 **P2** | albumScrollerIn gây jank | `AlbumScroller.vue` | Chạy 1 lần khi mount, không phải mỗi item |
| 🟡 **P2** | `--shadow-card` quá tối | `_mobile-overrides.scss` | Tăng opacity 0.10 → 0.20 light / 0.50 dark |
| ⚪ **P3** | GlowContainer strategy | `GlowContainer.vue` | Dùng `disabled` prop thay vì `useDevice` import |

### Điểm mạnh của proposal:
1. ✨ Kiến trúc hybrid (SFC media queries + global overrides) — **tối ưu**
2. ✨ Flat card design cho AlbumCard — **đúng, giảm GPU đáng kể**
3. ✨ Hex palette giữ nguyên — **đúng, tiết kiệm effort**
4. ✨ Phase priority hợp lý — **CSS trước, UX sau**
5. ✨ Touch target 44px analysis — **chính xác đến từng pixel**

### Điểm yếu:
1. ❌ Bỏ sót JS hover handlers (PhotoCard) — **cần sửa ngay**
2. ❌ Bỏ sót SkeletonLoader — **component animation tương tự cần xử lý**
3. ❌ Không phát hiện global prefers-reduced-motion đã tồn tại
4. ❌ Thiếu initial-only guard cho albumScrollerIn animation
5. ❌ Shadow opacity đề xuất quá thấp cho OLED

---

*Review hoàn thành lúc 2026-05-27. Tổng cộng đã đọc: 2 proposal files + 14 source files (component, style, composable).*
