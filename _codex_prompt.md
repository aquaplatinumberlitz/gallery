# Plan: Migrate toàn bộ Lightbox từ custom pipeline sang PhotoSwipe 5

## Context

Gallery project tại `/home/ubuntu/gallery-repo/`
Frontend: Vue 3 + TypeScript + SCSS + Vite
Backend: FastAPI Python

### Hiện trạng Lightbox

File chính: `src/components/Lightbox.vue` (~1045 lines)

Lightbox hiện tại có 3 mode render:
1. **Mobile** (`v-if="isMobile"`): **Đã dùng PhotoSwipe 5** thành công (component `MobilePhotoSwipe.vue`)
2. **Desktop** (`isDesktop`): 3-slide track custom (CSS translate3d + touch handlers + preload)
3. **Tablet** (`isTablet`): 3-slide track custom + bottom sheet metadata

### Các file liên quan

- `src/components/Lightbox.vue` — Component lightbox chính (1045 lines)
- `src/components/MobilePhotoSwipe.vue` — PhotoSwipe 5 wrapper cho mobile (146 lines, đã hoạt động tốt)
- `src/components/LightboxDesktopPanel.vue` — Sidebar metadata cho desktop
- `src/components/LightboxTabletPanel.vue` — Bottom sheet metadata cho tablet
- `src/components/LightboxMobileSheet.vue` — Bottom sheet metadata cho mobile
- `src/stores/lightbox.ts` — Pinia store cho lightbox state
- `src/composables/useDevice.ts` — Device detection (isMobile, isTablet, isDesktop)
- `src/services/api.ts` — API helpers (getImageUrl, getThumbnailUrl)
- `src/styles/_lightbox-mobile.scss` — PhotoSwipe 5 theme overrides + mobile lightbox styles
- `src/styles/_lightbox-desktop.scss` — Desktop lightbox styles (sidebar)
- `src/styles/_lightbox-tablet.scss` — Tablet lightbox styles (bottom sheet)
- `src/styles/_lightbox-shared.scss` — Shared lightbox styles

### PhotoSwipe 5 đã install

```
node_modules/photoswipe/dist/ có sẵn
```

PhotoSwipe 5 API:
```typescript
import PhotoSwipe from "photoswipe";

const pswp = new PhotoSwipe({
  dataSource: items[],  // { src, width, height, alt, ... }
  index: 0,
  pswpModule: () => Promise.resolve(PhotoSwipe),
  appendToEl: containerElement,
  closeOnVerticalDrag: true,
  showHideAnimationType: "zoom",  // "fade" | "zoom" | "none"
  allowPanToNext: true,
  wheelToZoom: false,
  bgOpacity: 1,
  // Có thể custom UI element positioning
});

pswp.on("change", () => { /* index changed */ });
pswp.on("close", () => { /* closed */ });
pswp.init();
pswp.destroy();
```

PhotoSwipe DOM structure:
```
.pswp (fullscreen container)
  .pswp__bg (background)
  .pswp__scroll-wrap
    .pswp__container (slides)
      .pswp__item (slide holder) × 3
    .pswp__ui (default UI — close btn, zoom, counter)
      .pswp__top-bar
      .pswp__button--close
      .pswp__button--zoom
      .pswp__counter
```

PhotoSwipe có thể custom UI bằng cách:
- `.pswp__ui` chỉnh position để nhường chỗ cho sidebar
- Hide default buttons (đã làm: `display: none` cho close/zoom/top-bar)
- Thêm custom elements với z-index > .pswp

### Pipeline custom hiện tại (Desktop + Tablet)

Xử lý ảnh:
- Desktop: 3-slide `translate3d` track + `<link rel="preload">` cho adjacent slides
- Ảnh dùng full-res `getImageUrl(path)` — 4096x6144 gốc
- Touch events tự viết (`handleSwipeStart/Move/End`) + direction lock
- `setTimeout(280)` cho animation timing — KHÔNG dùng `transitionend`
- KHÔNG có `img.decode()` pipeline
- Keyboard navigation (arrow keys)
- Mouse wheel navigation (desktop)

Metadata:
- Desktop: Sidebar `.lightbox-right` với panel `.lightbox-desktop-panel`
- Tablet: Bottom sheet `.lightbox-tablet-sheet`
- Mobile: Bottom sheet `.lightbox-mobile-sheet` (giữ nguyên, chạy trên PhotoSwipe)
- Full metadata: prompt, negative prompt, seed, steps, CFG, model, LoRAs, dates

### Kết quả mobile migration

Mobile đã migrate thành công — không còn swipe flash. Lý do PhotoSwipe thắng:
1. `img.decode()` trước khi append vào DOM
2. Hidden `<img>` preload (renderer cache) thay vì `<link rel="preload">` (HTTP cache)
3. Thumbnail 1600px cho adjacent slides thay vì full-res

## Yêu cầu

### Mục tiêu

Migrate TOÀN BỘ lightbox (desktop, tablet, iPad Mini, iPad 10.2, iPad Pro 11", 13") từ:
- Custom 3-slide track + CSS translate3d + touch handlers + preload
→ PhotoSwipe 5 unified pipeline

### Điều kiện bắt buộc

1. **GIỮ LẠI metadata sidebar cho desktop** (`.lightbox-desktop-panel`) — PhotoSwipe ko có sẵn sidebar
2. **GIỮ LẠI bottom sheet cho tablet + mobile** (`.lightbox-tablet-sheet`, `.lightbox-mobile-sheet`)
3. **PhotoSwipe fullscreen chiếm toàn màn hình**, sidebar đè lên bên phải hoặc bên cạnh
4. **iPad sizing support**: iPad Mini (768×1024), iPad 10.2" (810×1080), iPad Pro 11" (834×1194), iPad Pro 13" (1024×1366)

### Cần phân tích và đưa ra trong plan

#### A. Desktop layout strategy
- PhotoSwipe chiếm toàn màn hình, sidebar `.lightbox-desktop-panel` đặt ở đâu?
  - Option 1: Bên phải PhotoSwipe (giống layout hiện tại) — PhotoSwipe `.pswp__scroll-wrap` co lại
  - Option 2: Overlay trên PhotoSwipe (absolute, right:0, z-index cao) — PhotoSwipe full width
  - Option 3: PhotoSwipe dùng `pswpModule` custom UI để inject panel vào `.pswp__ui`
  - Option 4: Sidebar toggle — nút info mở sidebar overlay

#### B. Tablet layout strategy
- iPad Mini (768px) vs iPad Pro 13" (1024px) — breakpoint nào?
- PhotoSwipe full width, bottom sheet metadata (giống mobile nhưng 2-column layout)
- Giữ nguyên `LightboxTabletPanel.vue` hay tối ưu lại?

#### C. PhotoSwipe configuration per device
- Desktop: `allowPanToNext: false`? (desktop thường dùng nav buttons)
- Tablet: `allowPanToNext: true`, pinch to zoom?
- Same `bgOpacity: 1` cho tất cả?
- Thumbnail size: 1600px cho mobile, 2048px cho tablet, 4096px full-res cho desktop?

#### D. Keyboard/mouse wheel
- PhotoSwipe built-in keyboard navigation (arrow keys, esc)
- Cần thêm mouse wheel? PhotoSwipe ko có sẵn — custom event listener

#### E. Files cần thay đổi
Liệt kê exactly files cần:
- SỬA: `Lightbox.vue` — thay `v-if="isDesktop/isTablet"` section bằng PhotoSwipe
- SỬA: `LightboxDesktopPanel.vue` — adjust layout để đặt bên cạnh/trên PhotoSwipe
- SỬA: CSS files (_lightbox-desktop.scss, _lightbox-shared.scss, _lightbox-mobile.scss)
- THÊM/XÓA: components nào?
- GIỮ NGUYÊN: store, composables, LightboxMobileSheet, LightboxTabletPanel?

#### F. Risks & tradeoffs
- Desktop sidebar position: nếu để PhotoSwipe ko full-width, aspect ratio có bị bóp ko?
- iPad: tablet layout đã tối ưu chưa? Có cần chia thêm breakpoint ko?
- PhotoSwipe default UI (close button, counter) — cần hide/restyle những gì?
- Fullscreen mode trên desktop có còn hoạt động ko?

## Output

Viết plan chi tiết dưới dạng markdown, lưu vào `.hermes/plans/` với filename timestamp + `migrate-photoswipe-full.md`.
