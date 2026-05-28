# 📱 OpenCode UI/UX Review — Gallery Mobile App (Post-Refactor)

**Review date:** 2026-05-28  
**Commit base:** 17178d8 (Phase 3 + UIUX fixes, trước khi revert 2 commits gần nhất)  
**Scope:** Vue 3 + TypeScript + SCSS, toàn bộ components mobile + style system  
**Phân loại mức độ:** P0 (hỏng nặng) / P1 (xấu nhưng không hỏng) / P2 (nên sửa)

---

## 🔴 P0 — Lỗi nghiêm trọng, cần sửa ngay

### 1. `--bg-secondary` không được định nghĩa → Breadcrumb dropdown bị nền trắng trong dark mode

- **File:** `frontend/src/components/Breadcrumb.vue` — dòng 353
- **Code:**
  ```css
  background: var(--bg-secondary, #fff);
  ```
- **Vấn đề:** CSS variable `--bg-secondary` KHÔNG tồn tại trong `tokens.css` hay `main.scss`. Fallback là `#fff`, nên trong dark mode, dropdown menu của breadcrumb ellipsis vẫn có nền **trắng** — text màu tối sẽ biến mất trên nền trắng.
- **Dark mode selector** (dòng 452-455) cũng dùng:
  ```css
  background: var(--bg-secondary, #1e1e1e);
  ```
  Fallback `#1e1e1e` đúng cho dark, nhưng vì `--bg-secondary` không tồn tại, light mode cũng rơi vào fallback.
- **Fix:** Thêm `--bg-secondary` vào `tokens.css`:
  ```css
  :root { --bg-secondary: #ffffff; }
  :root[data-theme="dark"] { --bg-secondary: #1e1e1e; }
  ```

---

### 2. FolderTreeItem.vue hardcode `#d6a15d` thay vì CSS variable

- **File:** `frontend/src/components/FolderTreeItem.vue` — dòng 154
- **Code:**
  ```css
  background: #d6a15d;
  ```
- **Vấn đề:** `#d6a15d` là gold (dark mode primary). Trong light mode, `--primary-color` là `#ff6b35` (orange). Indicator active folder sẽ luôn là gold bất kể theme nào. Trong light mode gold rất khó thấy trên nền sáng.
- **Fix:** Đổi thành `background: var(--primary-color);`

---

## 🟠 P1 — Lỗi thẩm mỹ / không nhất quán, cần sửa

### 3. AppHeader toggle-thumb hardcode gradient trắng — không đổi theo dark mode

- **File:** `frontend/src/components/AppHeader.vue` — dòng 219
- **Code:**
  ```css
  background: linear-gradient(180deg, #fff 0%, #f0f0f0 100%);
  ```
- **Vấn đề:** Toggle thumb (nút tròn bên trong theme switch) luôn là gradient trắng → xám nhạt, kể cả trong dark mode. Trông như bị "lỗi" khi phần còn lại của UI tối hết.
- **Dark mode override** (dòng 231-237) chỉ đổi màu khi `.is-dark`, đó là gradient vàng. Nhưng lúc light mode cũng có gradient trắng cứng.
- **Fix:** Dùng `var(--surface-color)` thay `#fff` và `color-mix()` cho phần tối hơn.

### 4. Lightbox navigation button hover hardcode `#ff6b35` — không đồng bộ dark mode

- **File:** `frontend/src/components/Lightbox.vue` — dòng 543
- **Code:**
  ```css
  color: #ff6b35; /* pastel orange from palette */
  ```
- **Vấn đề:** Khi hover vào nút prev/next trong lightbox, màu chuyển thành `#ff6b35` (orange light mode). Trong dark mode, primary color là `#d6a15d` (gold) → hover màu cam không khớp với hệ thống màu gold còn lại.
- **Fix:** Đổi thành `color: var(--primary-color);`

### 5. MobileFloatingBottomBar và BottomNavigationBar có thể chồng lên nhau

- **File:** `frontend/src/App.vue` — dòng 230-247
- **Logic:**
  - `MobileFloatingBottomBar` render khi `isMobile && activeTab === 'photos'`
  - `BottomNavigationBar` render khi `isMobile`
  - **Cả 2 cùng hiển thị khi ở Photos tab trên mobile!**
- **Vị trí:**
  - `MobileFloatingBottomBar`: `position: fixed; bottom: 16px; z-index: 80`
  - `BottomNavigationBar`: `position: fixed; bottom: 0; z-index: 90; height: 56px`
- **Overlap:** Floating bar ở bottom:16px nằm ngay phía trên bottom nav bar. Bottom nav bar cao 56px từ bottom:0 lên. Floating bar bottom edge ở `16px + safe-area` từ bottom → **overlap ~40px** với top của BottomNavigationBar.
- GalleryGrid đã compensate với `padding-bottom: 120px` cho scroller footer (dòng 1223), nhưng 2 UI elements vẫn đè lên nhau về mặt thị giác.
- **Fix:** Tăng `bottom` của MobileFloatingBottomBar lên ~70px (trên nav bar) hoặc giảm z-index của nó xuống dưới BottomNavigationBar và đẩy lên cao hơn.

### 6. Fallback color của `--primary-color` không nhất quán giữa các components

| Component | Fallback value | Light mode primary | Diff? |
|-----------|---------------|-------------------|-------|
| `BottomNavigationBar.vue:95` | `#d6a15d` | `#ff6b35` | ✅ Sai fallback |
| `MobileFloatingBottomBar.vue:118` | `#d4af37` | `#ff6b35` | ✅ Sai fallback |
| `Breadcrumb.vue:401` | `#ff6b35` | `#ff6b35` | ❌ Đúng |
| `AlbumScroller.vue:209` | `#d6a15d` | `#ff6b35` | ✅ Sai fallback |
| `GalleryGrid.vue:1101` | `#d6a15d` | `#ff6b35` | ✅ Sai fallback |

- **Vấn đề:** Nếu CSS variable `--primary-color` bị lỗi (do selector conflict, cascade issue), các component sẽ hiển thị màu khác nhau — BottomNavigationBar sẽ vàng gold còn Breadcrumb sẽ cam. Trông rất kỳ cục.
- **Fix:** Chuẩn hóa tất cả fallback thành `var(--primary-color, #ff6b35)` (dùng light mode primary làm fallback vì app khởi động ở light mode).

### 7. Sort button và Sort Bottom Sheet vẫn hiển thị trên mobile (hậu quả của revert)

- **Context:** Hotfix đã xóa sort button trên mobile, nhưng commit đó đã bị revert về 17178d8.
- **Trạng thái hiện tại:**
  - `GalleryGrid.vue` dòng 398-405: `mobile-sort-trigger` button tồn tại
  - `GalleryGrid.vue` dòng 567-601: Sort Bottom Sheet tồn tại
  - `GalleryGrid.vue` dòng 1188-1191: Desktop sort dropdown bị ẩn trên mobile
  - `GalleryGrid.vue` dòng 1311-1333: Mobile sort trigger được hiển thị trên mobile
- **Kết luận:** Sort button HOÀN TOÀN hiển thị trên mobile. Đây không phải bug nếu user muốn giữ nó. Nhưng cần confirm với user: có muốn giữ sort button trên mobile không? (Trong đề xuất hotfix ban đầu, nó đã bị xóa để đơn giản hóa mobile header.)

### 8. `.scroller` padding-left khác nhau trên mobile vs desktop

- **Desktop:** `.scroller { padding-left: 10px; padding-right: 14px; }` (dòng 667-668)
- **Mobile:** `.virtual-row { padding: 0 4px; }` (dòng 1212-1213)
- **Vấn đề:** Khi album section bị collapse (AlbumScroller `collapsed = true` mặc định), section title "Albums" và chevron vẫn hiển thị. Nhưng album toggle button `padding: 0` và nằm trong `.scroller` có `padding-left: 10px`. Khi album grid wrapper ẩn đi, phần padding này tạo khoảng trống 10px bên trái header. Không nghiêm trọng nhưng hơi lệch.

### 9. Lightbox: Nút nav prev/next quá gần mép trên mobile

- **File:** `frontend/src/components/Lightbox.vue` — dòng 617-618
- **Code:**
  ```css
  .nav-btn.prev { left: 8px; }
  .nav-btn.next { right: 8px; }
  ```
- **Vấn đề:** Chỉ cách mép 8px. Trên thiết bị có safe area hoặc round corners (iPhone), nút sát quá mép, khó bấm.
- **Fix:** Tăng lên `left: 12px; right: 12px;` trên phone breakpoint.

---

## 🟡 P2 — Nên sửa để cải thiện chất lượng

### 10. PhotoCard dark mode dùng `#1c1c1e` hardcode thay vì `var(--surface-color)`

- **File:** `frontend/src/components/PhotoCard.vue` — dòng 184
- **Code:**
  ```css
  background: #1c1c1e;
  ```
- **Vấn đề:** `--surface-color` dark mode là `#11100f`. Photo cards dùng `#1c1c1e` (Apple iOS gray). Không đồng bộ với surface màu của phần còn lại của app. Có thể là intentional (Apple-style), nhưng tạo ra 2 màu nền khác nhau cho "surface" trong cùng app.
- **Gợi ý:** Dùng `var(--surface-color)` hoặc thêm `--card-color` token riêng.

### 11. SkeletonLoader dark mode dùng `:global(html[data-theme="dark"])` — không scale với scoped styles

- **File:** `frontend/src/components/SkeletonLoader.vue` — dòng 118-130
- **Code:**
  ```css
  :global(html[data-theme="dark"]) .skeleton-block,
  :global(html[data-theme="dark"]) .skeleton-line {
    background: linear-gradient(...);
  }
  ```
- **Vấn đề:** Dùng `:global()` để thoát scoped, không phải best practice. Hoạt động nhưng dễ bị side-effect nếu global class thay đổi.
- **Gợi ý:** Dùng `@media (prefers-color-scheme: dark)` hoặc CSS variables.

### 12. EmptyState action button luôn dùng `background: var(--accent-color)` — màu không nhất quán với primary

- **File:** `frontend/src/components/EmptyState.vue` — dòng 400-401
- **Code:**
  ```css
  background: var(--accent-color);
  color: #fff;
  ```
- `--accent-color` được set inline từ `defaults.color` (vd: `#a78bfa`, `#60a5fa`, `#f87171`). Mỗi loại empty state có màu accent riêng. Điều này tốt cho illustration nhưng button action cũng dùng màu đó — button "Clear search" sẽ xanh dương `#60a5fa` thay vì primary orange/gold. Không nhất quán với style buttons khác trong app.
- **Gợi ý:** Action button nên dùng `var(--primary-color)` thay vì `var(--accent-color)`.

### 13. SettingsModal dark mode dùng hardcode `#1e293b` và `#0f172a`

- **File:** `frontend/src/components/SettingsModal.vue`
  - dòng 195: `background: #1e293b;`
  - dòng 346: `background: #0f172a;`
  - dòng 220: `color: #f1f5f9;`
- **Vấn đề:** Không dùng `var(--surface-color)` và `var(--text-color)` — sử dụng màu Tailwind-style cứng. Nếu user customize theme, settings modal sẽ không theo.
- **Gợi ý:** Dùng `var(--surface-color)`, `var(--text-color)`, `var(--bg-color)`.

### 14. Breadcrumb trên mobile: bị ẩn hoàn toàn (`display: none`)

- **File:** `frontend/src/components/GalleryGrid.vue` — dòng 1180-1182
- **Code:**
  ```css
  .breadcrumb-wrap {
    display: none;
  }
  ```
- **Vấn đề:** Trên mobile, breadcrumb path hoàn toàn biến mất. User không thấy đường dẫn hiện tại ở đâu cả. Chỉ có folder name trong MobileFloatingBottomBar (khi ở photos tab), nhưng khi ở albums tab thì không có gì.
- **Gợi ý:** Có thể giữ breadcrumb dạng đơn giản (chỉ 1-2 segment cuối) trên mobile, hoặc hiển thị path trong MobileHeader.

### 15. `home-icon` trong Breadcrumb có `filter: drop-shadow` không cần thiết

- **File:** `frontend/src/components/Breadcrumb.vue` — dòng 492
- **Code:**
  ```css
  filter: drop-shadow(0 0 4px color-mix(in srgb, var(--primary-color) 30%, transparent));
  ```
- **Vấn đề:** Icon Home ở đầu breadcrumb có glow shadow bằng primary color. Trong light mode primary là orange, glow cam trên nền chữ muted trông hơi distracting.
- **Gợi ý:** Chỉ giữ glow trong dark mode, hoặc bỏ hẳn.

---

## ✅ Đã kiểm tra — không có vấn đề

| Kiểm tra | Kết quả |
|----------|---------|
| EmptyState dark mode text màu đen? | ✅ **Không.** `.title` dùng `var(--title-color)` → `#d6a15d` (gold), `.description` dùng `var(--muted-text)` → `#b3b3b3`. Cả 2 đều sáng và readable. |
| content-body màu trắng trong dark mode? | ✅ **Không.** Desktop: `var(--surface-color)` → `#11100f` (tối). Mobile: `transparent` (intentional). |
| Breadcrumb transparent trên mobile? | ✅ **Không cần.** Breadcrumb bị `display: none` trên mobile (ẩn hoàn toàn). |
| Hardcoded colors dùng CSS variables? | ⚠️ **Hầu hết có, nhưng vẫn còn 5+ hardcoded** (đã liệt kê ở P0/P1). |
| Duplicate bottom bars? | ⚠️ **Có nguy cơ overlap** (P1 #5) nhưng không duplicate — 2 bars khác chức năng. |
| Dark mode / light mode toggle hoạt động? | ✅ Hoạt động qua `data-theme` attribute, CSS variables switch correctly. |

---

## 🧮 Tổng hợp

| Mức | Số lượng | Mô tả |
|-----|----------|-------|
| **P0** | 2 | `--bg-secondary` undefined, FolderTreeItem hardcode gold |
| **P1** | 7 | Theme toggle thumb, Lightbox hover color, bar overlap, fallback inconsistency, sort button, padding, nav button proximity |
| **P2** | 5 | PhotoCard bg, Skeleton :global, EmptyState button color, SettingsModal hardcode, Breadcrumb hidden |

**Khuyến nghị:** Sửa P0 trước — thêm `--bg-secondary` vào tokens.css và đổi FolderTreeItem sang `var(--primary-color)`. Sau đó sửa P1 — đặc biệt là bar overlap (#5) và fallback consistency (#6) vì 2 issues này dễ gây lỗi nhất khi CSS cascade thay đổi.
