# Refactor Plan Mobile/Tablet UI cho Gallery Vue

## Phần A: Phân tích hiện trạng

### 1. Tất cả `@media` queries trong `frontend/src`

| File | Dòng | Query | Phạm vi tác động |
| --- | ---: | --- | --- |
| `frontend/src/styles/main.scss` | 391 | `(prefers-contrast: high)` | Global high contrast: biến màu, border/focus bằng `!important` |
| `frontend/src/styles/main.scss` | 413 | `(prefers-reduced-motion: reduce)` | Global tắt animation/transition bằng `!important` |
| `frontend/src/styles/main.scss` | 425 | `(pointer: coarse)` | Global touch target: mọi `button`, link, input có `min-width/min-height: 44px` |
| `frontend/src/styles/main.scss` | 471 | `(max-width: 1024px)` | Utility `.hide-tablet`, `.show-tablet` |
| `frontend/src/styles/main.scss` | 476 | `(max-width: 640px)` | Utility `.hide-phone`, `.show-phone`, `.hide-desktop` |
| `frontend/src/styles/main.scss` | 483 | `(pointer: coarse)` | Global touch refinement cho `.nav-btn`, `[class*="btn"]`, `.crumb` |
| `frontend/src/App.vue` | 766 | `(max-width: 1024px)` | Layout tablet chung: sidebar 240px, content padding, brand/search sizing |
| `frontend/src/App.vue` | 803 | `(min-width: 641px) and (max-width: 1024px)` | Tablet riêng: hamburger hiện, edge-toggle ẩn, sidebar persistent |
| `frontend/src/App.vue` | 827 | `(max-width: 640px)` | Phone shell/header/sidebar overlay/search/theme/settings |
| `frontend/src/App.vue` | 1044 | `(max-width: 480px)` | Small phone compact header/content/sidebar |
| `frontend/src/components/GalleryGrid.vue` | 1103 | `(max-width: 640px)` | Album grid 160px |
| `frontend/src/components/GalleryGrid.vue` | 1110 | `(max-width: 480px)` | Album grid 140px |
| `frontend/src/components/GalleryGrid.vue` | 1133 | `(max-width: 1024px)` | Grid header gap, breadcrumb max width |
| `frontend/src/components/GalleryGrid.vue` | 1144 | `(max-width: 640px)` | Mobile grid header, hide breadcrumb/open-folder, compact sort/slider, folder bar |
| `frontend/src/components/GalleryGrid.vue` | 1302 | `(max-width: 480px)` | Small phone grid controls |
| `frontend/src/components/GalleryGrid.vue` | 1345 | `(prefers-reduced-motion: reduce)` | Tắt fade/dropdown transitions |
| `frontend/src/components/Lightbox.vue` | 882 | nested `(max-width: 1024px)` | `.lightbox-right` width 350px inside base selector |
| `frontend/src/components/Lightbox.vue` | 1217 | `(prefers-contrast: high)` | Lightbox high contrast |
| `frontend/src/components/Lightbox.vue` | 1237 | `(prefers-reduced-motion: reduce)` | Tắt lightbox transitions |
| `frontend/src/components/Lightbox.vue` | 1286 | `(max-width: 1024px)` | `.lightbox-right` width 320px, min 280px |
| `frontend/src/components/Lightbox.vue` | 1294 | `(max-width: 640px)` | Phone lightbox: column shell, hide right panel, show info button |
| `frontend/src/components/Lightbox.vue` | 1334 | `(max-width: 480px)` | Small phone nav/meta compact |
| `frontend/src/components/Lightbox.vue` | 1566 | `(pointer: coarse)` | Lightbox nav tap targets |
| `frontend/src/components/AlbumCard.vue` | 64 | nested `(max-width: 640px)` | Album cover height 200px |
| `frontend/src/components/AlbumCard.vue` | 70 | nested `(max-width: 480px)` | Album cover 160px, text compact |
| `frontend/src/components/SidebarHeader.vue` | 170 | `(max-width: 480px)` | Sidebar input/header compact |
| `frontend/src/components/Breadcrumb.vue` | 475 | `(prefers-reduced-motion: reduce)` | Tắt breadcrumb dropdown transition |
| `frontend/src/components/Breadcrumb.vue` | 502 | `(max-width: 480px)` | Breadcrumb compact, dù breadcrumb đang bị ẩn trên phone trong grid |
| `frontend/src/components/ToastContainer.vue` | 40 | `(max-width: 480px)` | Toast full-width inset |
| `frontend/src/components/ToastContainer.vue` | 73 | `(prefers-reduced-motion: reduce)` | Toast animation reduced |
| `frontend/src/components/ToastItem.vue` | 337 | `(prefers-contrast: high)` | Toast border contrast |
| `frontend/src/components/ToastItem.vue` | 344 | `(prefers-reduced-motion: reduce)` | Tắt progress transition |
| `frontend/src/components/EmptyState.vue` | 479 | `(prefers-reduced-motion: reduce)` | Tắt decorative animations |

Không thấy `@media print` trong `frontend/src` hiện tại. Nếu từng tồn tại, nó đã bị xoá hoặc nằm ngoài phạm vi file Vue/SCSS được yêu cầu.

### 2. Specificity và override đang có rủi ro

- `frontend/src/styles/main.scss:425` đặt `button { min-width: 44px; min-height: 44px; }` trên touch device. Mobile `.theme-toggle` ở `frontend/src/App.vue:962` chỉ đặt `width: 28px; height: 28px`, không reset `min-width/min-height`. Vì vậy computed size trên điện thoại có thể là 44x44 thay vì 28x28, làm `.toggle-track` 100% lớn hơn thumb 28x28 và tạo cảm giác SVG/thumb lệch center.
- `frontend/src/styles/main.scss:483` tiếp tục đặt min target cho `.nav-btn`, `[class*="btn"]`, `[class*="button"]`. Rule này có thể override ý đồ compact 30-34px ở `App.vue:993`, `App.vue:1049`, `GalleryGrid.vue:1176`, `GalleryGrid.vue:1307`. Đây là quyết định UX hợp lý cho touch target, nhưng cần tách “visual size” khỏi “hit area” thay vì ép chính element phình ra.
- Breakpoint JS/CSS không thống nhất: `App.vue:74` dùng `width < 640`, nhưng CSS phone dùng `max-width: 640px` ở `App.vue:827`; `Lightbox.vue:221` dùng `matchMedia("(max-width: 640px)")`; `GalleryGrid.vue:196-198` dùng `w >= 640` là tablet 3 cột. Tại đúng 640px, App JS không mobile, CSS phone có hiệu lực, lightbox mobile có hiệu lực, grid default lại tablet.
- `isTablet` ở `App.vue:53` được set tại `App.vue:75` nhưng không được dùng trong template/CSS. Tablet hiện chủ yếu là CSS, không có state-driven behavior rõ ràng.
- `display: contents` ở `App.vue:877-880` làm `.header-left` và `.header-actions` mất box layout trên mobile. Kết hợp với `order` ở `App.vue:832`, `App.vue:884`, `App.vue:962`, `App.vue:993` khiến header khó maintain và dễ lỗi accessibility/styling vì wrapper không còn layout box.
- `.mobile-header-title` được khai báo desktop hidden ở `App.vue:663`, rồi vẫn `display: none` trong phone `App.vue:958` và small phone `App.vue:1069`. Đây là dead UI path.
- `GalleryGrid.vue` có 2 block album responsive riêng ở `1103` và `1110`, rồi lại có block phone lớn ở `1144`. Các rule mobile nằm tách đoạn nên khó kiểm soát thứ tự override.
- `Lightbox.vue` có rule `.lightbox-right` nested tablet ở `882` và rule tablet ngoài ở `1286`. Rule ngoài đến sau nên width 320px thắng width 350px cho cùng breakpoint. Nên hợp nhất để tránh hiểu sai.
- Global utilities trong `main.scss:457-463` ghi comment Phone `<768px`, nhưng implementation thực tế dùng `640px` ở `main.scss:476`. Comment và code lệch nhau.
- Global dark selectors như `html[data-theme="dark"] .theme-toggle` ở `main.scss:255` tác động xuyên scoped component. Hiện chưa phải nguyên nhân chính của mobile toggle, nhưng cần tránh thêm responsive override global cho component-local element nếu không cần.

### 3. Component tree liên quan mobile/tablet

- `App.vue`
  - `IntroScreen`
  - `.layout`
    - `aside.sidebar`
      - `SidebarHeader`
      - `FolderTreeItem` list
    - `.sidebar-edge-toggle`
    - `.sidebar-backdrop` mobile
    - `section.content`
      - `header.content-header`
        - `.header-left`: hamburger, settings
        - `.brand-hero`
        - `.mobile-header-title`
        - `.header-actions`: theme toggle, search box, search backdrop
      - `.content-body`
        - `GalleryGrid`
  - `Lightbox`
  - `ToastContainer`
  - `SettingsModal`

Components cần sửa cho responsive layer:

- `App.vue`: shell layout, sidebar behavior, mobile/tablet header, theme toggle, search expansion.
- `GalleryGrid.vue`: gallery toolbar, folder bar, grid slider, column defaults, album grid spacing.
- `Lightbox.vue`: mobile detection, bottom sheet, tablet metadata width, nav tap targets.
- `AlbumCard.vue`: album cover sizing should align with gallery grid breakpoints.
- `SidebarHeader.vue`: mobile sidebar form sizing.
- `Breadcrumb.vue`: only if breadcrumb returns on tablet/mobile; currently hidden in phone gallery header.
- `ToastContainer.vue`: ensure bottom sheet/lightbox do not conflict with toast z-index/position.

## Phần B: Đề xuất kiến trúc responsive mới

### 1. Breakpoints chuẩn

Dùng đúng 2 breakpoint sản phẩm:

```scss
$bp-phone: 640px;
$bp-tablet: 1024px;

/* Desktop/default: >= 1025px */
@media (min-width: 641px) and (max-width: 1024px) { /* tablet */ }
@media (max-width: 640px) { /* phone */ }
```

Quy ước:

- Base CSS là desktop hiện tại, hạn chế đụng vì desktop đang tốt.
- Tablet là range riêng `641-1024px`, không chỉ kế thừa phone.
- Phone là `<=640px`.
- JS phải dùng cùng logic: phone `matchMedia("(max-width: 640px)")`, tablet `matchMedia("(min-width: 641px) and (max-width: 1024px)")`.
- Grid default: desktop 5, tablet 3, phone 2. Tại 640px phải là phone 2 để khớp CSS.

### 2. Tổ chức file

Không nên dồn toàn bộ responsive vào một `_responsive.scss` lớn ngay lập tức, vì phần lớn style đang scoped trong SFC. Đề xuất:

- Tạo hoặc chuẩn hoá token/mixin breakpoint trong `frontend/src/styles/main.scss` hoặc file SCSS shared nếu build đã import được SCSS partial.
- Giữ responsive component-local trong component sở hữu markup: `App.vue`, `GalleryGrid.vue`, `Lightbox.vue`.
- Chỉ đưa utility/global thật sự dùng chung vào global SCSS: breakpoint comments, `.show-*`, `.hide-*`, touch target policy.
- Trong mỗi component, gom media theo thứ tự cuối file: tablet block trước, phone block sau, small phone chỉ nếu thật cần. Tránh nhiều block cùng breakpoint rải rác.

### 3. Mobile header layout đề xuất

Mục tiêu là bỏ layout 3-row chắp vá và giảm `order`.

Đề xuất 2 vùng rõ ràng:

- App header row: hamburger, title compact hoặc brand mark, spacer, search icon, theme toggle, settings.
- Gallery toolbar row: back/forward, sort, grid slider. Folder/current album hiển thị trong cùng toolbar hoặc ngay dưới dạng text nhỏ, không dùng icon folder tách rời như một row độc lập.

Implementation direction:

- Không dùng `display: contents` cho `.header-left`/`.header-actions`.
- Dùng CSS grid cho `.content-header` trên phone: `grid-template-columns: auto minmax(0, 1fr) auto auto auto`.
- Tạo wrapper rõ cho control groups thay vì reorder từng child.
- Theme toggle trên mobile nên là icon button 34-36px visual với track/thumb nội bộ center tuyệt đối, hoặc chuyển thành button tròn chỉ chứa sun/moon icon. Nếu giữ track, visual 28px có hit area bằng pseudo-element/wrapper 44px, không để global `min-width` làm méo track.
- Folder bar: thay `.mobile-folder-bar` bằng `.gallery-context` nhỏ, nằm trong `GalleryGrid` toolbar area, chỉ text ellipsis + count; open-folder action nếu cần nằm trong overflow/menu hoặc chỉ ở tablet/desktop.

## Phần C: Kế hoạch thực hiện từng bước

### Step 1: Fix theme toggle trước

1. Kiểm tra computed styles thật trên Chrome DevTools/Playwright ở 390px, 430px, 640px và touch emulation:
   - `.theme-toggle`: `width`, `height`, `min-width`, `min-height`, `padding`, `display`.
   - `.toggle-track`: content size, padding.
   - `.toggle-thumb`: `left/top/transform`, width/height.
   - SVG inside thumb: bounding box and line-height.
2. Sửa theo hướng ít rủi ro:
   - Mobile `.theme-toggle` visual size 34-36px hoặc giữ 28px nhưng thêm `min-width: 28px; min-height: 28px;`.
   - Nếu cần touch target 44px, bọc bằng hit area/pseudo-element, không để chính track bị phình.
   - `.toggle-track { position: relative; width: 100%; height: 100%; padding: 0; display: block; }`.
   - `.toggle-thumb { inset: 0; margin: auto; display: grid; place-items: center; }` cho mobile icon-only mode.
   - `.toggle-thumb svg { display: block; width: 18px; height: 18px; flex: none; }`.
3. Xác nhận light/dark state không làm thumb nhảy: mobile dark không dùng `left: calc(100% - 32px)` nếu toggle là icon-only.
4. Chụp screenshot trước/sau mobile để xác nhận icon center bằng pixel, không chỉ nhìn thủ công.

### Step 2: Sắp xếp lại media queries

1. Đồng bộ breakpoint JS/CSS:
   - `App.vue` mobile `<=640` bằng `matchMedia`.
   - `Lightbox.vue` giữ cùng query.
   - `GalleryGrid.vue` default cols đổi điều kiện để `<=640` là 2 cột.
2. Sửa comment breakpoint trong `main.scss` cho đúng: desktop `>1024`, tablet `641-1024`, phone `<=640`.
3. Rà global coarse pointer:
   - Không áp `min-width/min-height: 44px` mù cho mọi `button`.
   - Chỉ áp cho control cần touch target hoặc dùng CSS variable `--tap-target`.
   - Các control compact có visual size riêng và hit area riêng.
4. Trong từng component, gom block responsive:
   - `App.vue`: base, tablet, phone, optional small phone.
   - `GalleryGrid.vue`: base, tablet, phone, optional small phone; hợp nhất album grid block vào cụm này.
   - `Lightbox.vue`: hợp nhất 2 tablet rules của `.lightbox-right`.
5. Xoá hoặc thay dead CSS/markup sau khi có xác nhận: `.mobile-header-title` nếu không dùng, comments cũ, duplicate rules.

### Step 3: Refactor mobile header layout

1. Đổi `content-header` mobile từ flex + `display: contents` + `order` sang CSS grid hoặc explicit wrappers.
2. Giữ App header chỉ cho app-level actions:
   - hamburger/sidebar
   - compact brand/title
   - search
   - theme
   - settings
3. Chuyển gallery-level actions nằm trong `GalleryGrid`:
   - back/forward
   - sort
   - grid slider
   - current folder/count
4. Với folder/current path:
   - Phone: text ellipsis + count trong toolbar/context line.
   - Tablet: breadcrumb có thể còn visible nhưng giới hạn width hợp lý.
   - Desktop: giữ nguyên hiện trạng.
5. Search expanded overlay cần kiểm z-index với sidebar backdrop, lightbox, toast:
   - search overlay `z-index` thấp hơn lightbox/toast, cao hơn content/sidebar backdrop khi mở.

### Step 4: Thêm tablet breakpoint đúng nghĩa

1. App shell tablet:
   - Sidebar persistent 240px hoặc collapsible có trạng thái rõ, không overlay.
   - Hamburger nếu giữ phải thực sự toggle collapsed state; nếu sidebar persistent thì không cần hamburger.
   - Edge toggle ẩn hoặc thay bằng một pattern duy nhất, tránh vừa hamburger vừa sidebar cố định.
2. Header tablet:
   - Brand nhỏ hơn desktop nhưng không biến thành phone.
   - Search vẫn inline, không icon-only nếu đủ rộng.
   - Theme toggle giữ desktop pill hoặc compact pill, không icon-only phone.
3. Gallery grid tablet:
   - Default 3 columns.
   - Album cards min width khoảng 180-200px, không dùng phone 160px.
   - Breadcrumb max width theo container, không hard-code 300px nếu gây truncate quá sớm.
4. Lightbox tablet:
   - Metadata sidebar 320px hoặc responsive `clamp(300px, 34vw, 380px)`.
   - Không dùng mobile bottom sheet trên tablet.
5. Test tablet widths cụ thể: 768, 820, 1024.

### Step 5: Verify grid slider + lightbox

Grid slider:

- Verify thumb visual 28px và hit area tối thiểu 44px không làm layout phình.
- Verify slider vẫn thao tác được ở 360/390/430/640/768/1024px.
- Confirm cột: phone 2, tablet 3, desktop 5 default, localStorage override không tạo layout vỡ khi người dùng từng lưu 8 cột trên phone. Có thể clamp displayed columns per breakpoint hoặc reset default theo breakpoint nếu stored value quá lớn.

Lightbox:

- Verify `isMobile` sync với CSS ở 640px.
- Verify bottom sheet open/close, tab Prompt/Params/Model, drag up/down, backdrop close.
- Verify focus trap không bắt focus vào hidden desktop `.lightbox-right` trên mobile.
- Verify nav buttons touch size, disabled opacity, image remains contained.
- Verify fullscreen: hiện tại selector `.lightbox-shell:fullscreen` có thể không match vì fullscreen request gọi trên `lightboxRef` (`.lightbox-overlay`) ở `Lightbox.vue:271`, không phải `.lightbox-shell`. Cần test và sửa selector nếu cần.

## Phần D: Rủi ro và lưu ý

- Không đụng desktop trước khi có baseline screenshot. Base CSS hiện là desktop; mọi thay đổi nên nằm trong tablet/phone media hoặc token global thật sự cần.
- Rủi ro lớn nhất là global touch-target rules trong `main.scss`; sửa nó có thể ảnh hưởng tất cả buttons, nav, toast dismiss, sidebar controls.
- `App.vue` header đang phụ thuộc DOM order và `display: contents`; refactor có thể ảnh hưởng keyboard/focus order nếu đổi markup không cẩn thận.
- `GalleryGrid.vue` dùng virtual scroller và `rowHeight` tính theo `columnCount`; đổi column breakpoint/storage phải kiểm row height và infinite scroll.
- `Lightbox.vue` dùng Teleport, fullscreen, focus trap, keyboard, wheel navigation và mobile sheet. Đây là component dễ side-effect nhất sau `App.vue`.
- `Breadcrumb.vue` phone CSS hiện ít tác dụng vì breadcrumb bị ẩn trong `GalleryGrid.vue` phone. Chỉ sửa nếu quyết định hiển thị breadcrumb lại.
- Cần test thiết bị thật hoặc remote debugging ít nhất trên iPhone Safari/Chrome Android vì `pointer: coarse`, range input thumb, viewport units và bottom sheet touch behavior thường khác desktop emulation.
- Cần test cả light/dark theme. Theme toggle và global dark selectors có thể tạo khác biệt giữa hai theme.

## Checklist nghiệm thu đề xuất

- 390px phone: header không overlap, theme icon center, grid toolbar nằm trong một hàng hoặc hai hàng rõ ràng, folder text ellipsis đúng.
- 640px exact: JS/CSS cùng nhận là phone; grid default 2 cột; lightbox dùng bottom sheet.
- 768px/820px tablet: sidebar/header/gallery không dùng phone layout; grid default 3 cột; lightbox dùng sidebar metadata.
- 1024px tablet: không vỡ breadcrumb/search/slider; sidebar policy rõ ràng.
- 1025px desktop: UI giữ nguyên so với baseline.
- Touch target: controls có hit area >=44px nhưng visual không bị phình méo.
