# Implement: Responsive Breakpoint Cleanup

Project tại /home/ubuntu/gallery-repo/frontend/
Git ready với tag baseline-pre-photoswipe (hoặc commit mới hơn).

## KHÔNG được làm
- KHÔNG redesign PhotoSwipe UI, metadata sheet, sidebar, grid, bottom nav, header
- KHÔNG thay đổi visual design intentionally
- KHÔNG chạy dev server (chỉ build)
- KHÔNG implement container queries (quá lớn cho task này)
- KHÔNG sửa LightboxDesktopPanel.vue, LightboxTabletPanel.vue, LightboxMobileSheet.vue

## Target breakpoint system (source of truth)

JS (useDevice.ts):
```typescript
BREAKPOINTS = {
  compact: 480,
  mobile: 768,
  desktop: 1200,
  wide: 1440,
}
```
- isCompact: width < 480
- isMobile: width < 768
- isTablet: width >= 768 && width < 1200
- isDesktop: width >= 1200
- isWide: width >= 1440

SCSS (_breakpoints.scss - file mới):
```scss
$bp-compact: 480px;
$bp-mobile: 768px;
$bp-desktop: 1200px;
$bp-wide: 1440px;

@mixin compact { @media (max-width: 479px) { @content; } }
@mixin mobile { @media (max-width: 767px) { @content; } }
@mixin tablet { @media (min-width: 768px) and (max-width: 1199px) { @content; } }
@mixin below-desktop { @media (max-width: 1199px) { @content; } }
@mixin desktop { @media (min-width: 1200px) { @content; } }
@mixin wide { @media (min-width: 1440px) { @content; } }
```

## Step-by-step

### Step 1: Tạo _breakpoints.scss
Tạo file src/styles/_breakpoints.scss với đầy đủ variables + mixins như trên.

### Step 2: Import _breakpoints.scss vào main.scss
Thêm `@import 'breakpoints';` vào main.scss sau dòng `@import 'mobile-overrides';` (hoặc đầu file).

### Step 3: Sửa useDevice.ts
Mở rộng BREAKPOINTS thêm `wide: 1440`.
Thêm `isWide` computed.
Cập nhật comments cho rõ ràng.

### Step 4: Fix CSS docs trong main.scss
Tìm block comment:
```
Desktop:  >1024px
Tablet:   768-1024px
Phone:    <=767px
Small:    <480px (390px iPhone viewport)
```
Đổi thành:
```
Desktop:  >=1200px
Tablet:   768-1199px
Phone:    <=767px
Compact:  <480px (iPhone viewport)
```

### Step 5: Fix App.vue media queries
Đọc App.vue style scoped section.
Tìm `@media (max-width: 1024px)` — những rule nào thực sự là "tablet & below" thì nên giữ hoặc chuyển sang @include below-desktop.
Xác định: Nếu 1025-1199px cần layout này, giữ. Nếu ko, chuyển.

Các vị trí:
- Dòng ~405: `@media (max-width: 1024px)` — sidebar/grid layout
  → Đánh giá: Có cần cho 1025-1199 ko? App.vue render theo `isMobile`/`isTablet`/`isDesktop` của JS, CSS chỉ là style refinement. Các style sidebar fixed, grid columns... Ở 1100px (tablet theo JS), CSS này nên active. Vậy **đổi thành `@media (max-width: 1199px)`**.
- Dòng ~428: `@media (min-width: 768px) and (max-width: 1024px)` — sidebar persistent
  → Đây rõ ràng là tablet range. **Đổi max-width thành 1199px và import _breakpoints.scss, dùng @include tablet.**

### Step 6: Fix _lightbox-tablet.scss
- Tìm `min-width: 900px` — đây là spacing refinement cho tablet-wide. Giữ lại nhưng thêm comment: "// Tablet-wide spacing refinement, not a device breakpoint"
- Tìm `max-height: 800px` — đây là viewport-height refinement. Giữ lại với comment: "// Short viewport tablet refinement"

### Step 7: Fix AlbumScroller.vue
Tìm `window.matchMedia("(max-width: 767px)")` hoặc `"(max-width: 767px)"`.
Thay bằng dùng `useDevice()` composable.
Cụ thể:
- Import `useDevice` từ `"../../composables/useDevice"` (hoặc đường dẫn đúng)
- Xoá `isMobile` ref riêng
- Xoá `matchMedia` listener riêng
- Xoá resize listener riêng (nếu chỉ để detect mobile)
- Dùng `const { isMobile } = useDevice()` thay thế

### Step 8: Fix useColumnResize.ts 460
Tìm `460`. Giải pháp: đặt tên constant:
```typescript
// Grid density threshold — not a device breakpoint.
// At this width the grid can fit 3 columns without overflow.
const GRID_THREE_COL_MIN_WIDTH = 460;
```
Hoặc chuyển thành 480 nếu visual không bị ảnh hưởng.

PREFER: đặt tên + comment. Không đổi giá trị để tránh thay đổi visual.

### Step 9: Fix AppHeader.vue
Tìm `@media (max-width: 1024px)` — dòng ~454.
Nếu style là "tablet trở xuống" → đổi thành `@include below-desktop` hoặc `@media (max-width: 1199px)`.
Tìm `@media (min-width: 768px) and (max-width: 1024px)` — dòng ~471.
→ Đổi thành `@include tablet` (max-width: 1199px).

### Step 10: Fix MobileHeader.vue
Tìm `min-width: 481px` và `max-width: 1024px` — dòng ~578.
→ Đổi max-width thành 1199px. Comment: "// Tablet-range search input sizing".

### Step 11: Fix GalleryGrid.vue
Tìm `@media (max-width: 1024px)` — dòng ~1127.
→ Nếu là tablet/below, đổi thành `@media (max-width: 1199px)` hoặc `@include below-desktop`.

### Step 12: Fix GalleryGrid.vue tablet lock
Tìm `@media (max-width: 767px)` — 15 locations. Đây là mobile range, KHÔNG cần đổi (767px = mobile).
Tìm `@media (max-width: 480px)` — compact. Giữ nguyên.
Tìm `@media (max-width: 360px)` — tiny phone. Giữ nguyên.

### Step 13: Fix main.scss utility classes
Tìm `.hide-tablet`, `.show-tablet`, `.hide-phone`, `.show-phone`, `.hide-desktop` (dòng ~440-449).
Đổi `@media (max-width: 1024px)` → `@include below-desktop` hoặc `@media (max-width: 1199px)`.
Đổi `@media (min-width: 1025px)` → `@include desktop` hoặc `@media (min-width: 1200px)`.

### Step 14: Kiểm tra các file còn lại
Scan toàn bộ .vue, .scss, .ts, .css trong src/ cho:
- `max-width: 1024` — đã xử lý hết chưa? Nếu còn, đánh giá từng cái.
- `max-width: 1023` — cái nào còn?
- `min-width: 1025` — cái nào còn?

### Step 15: Build
Chạy `cd /home/ubuntu/gallery-repo/frontend && npx vite build`

## Sau khi hoàn thành
Chạy: `cd /home/ubuntu/gallery-repo/frontend && npx vite build`
Kiểm tra build ko lỗi.
