# Implement Album Horizontal Scroll

Gallery Vue 3 app at `/home/ubuntu/gallery-repo/gallery/frontend/`
Git tag `baseline-pre-album-scroll` for rollback.

## Mục tiêu

Chuyển album grid từ layout dạng grid (nhiều hàng) sang horizontal scroll (1 hàng duy nhất), giống Google Photos pattern.

## Chi tiết thay đổi

### 1. Template — GalleryGrid.vue

Có **2 chỗ** trong template cần thay đổi.

**Chỗ 1: Trong RecycleScroller `#before` slot** (tìm `<section v-if="folders.length" class="albums-section">`)

Thêm `.album-grid-wrapper` bao ngoài `.album-grid`:
```html
<section v-if="folders.length" class="albums-section">
  <div class="section-title">
    <h3>Albums</h3>
    <span>{{ folders.length }}</span>
  </div>
  <div class="album-grid-wrapper">
    <div class="album-grid">
      <AlbumCard
        v-for="item in folders"
        :key="item.path"
        :node="item"
        @click="handleOpenFolder(item.path)"
      />
    </div>
  </div>
</section>
```

**Chỗ 2: Trong `.folders-only-container`** (tìm chỗ thứ 2 có `v-for="item in folders"` với AlbumCard)

Áp dụng tương tự — thêm `.album-grid-wrapper` bao ngoài `.album-grid`.

### 2. CSS — GalleryGrid.vue

**Xoá:** Tất cả CSS cũ cho `.album-grid` (base style + responsive blocks) — tìm từ `.album-grid { display: grid...` đến hết các @media cho album-grid.

**Thêm CSS mới:**
```css
/* ── Album Horizontal Scroll ── */
.album-grid-wrapper {
  position: relative;
  margin: 0 -12px;          /* bleed để gradient fade lộ ra */
}

/* Gradient fade 2 đầu */
.album-grid-wrapper::before,
.album-grid-wrapper::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  width: 48px;
  z-index: 2;
  pointer-events: none;
}
.album-grid-wrapper::before {
  left: 0;
  background: linear-gradient(to right, var(--bg-color) 0%, transparent 100%);
}
.album-grid-wrapper::after {
  right: 0;
  background: linear-gradient(to left, var(--bg-color) 0%, transparent 100%);
}

.album-grid {
  display: flex;
  flex-wrap: nowrap;
  gap: 24px;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 8px 4px 16px;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  -webkit-overflow-scrolling: touch;
  
  /* Ẩn scrollbar */
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.album-grid::-webkit-scrollbar {
  display: none;
}

.album-grid > * {
  scroll-snap-align: start;
  flex-shrink: 0;
  min-width: 180px;
  max-width: 240px;
}

@media (max-width: 640px) {
  .album-grid { gap: 12px; padding: 4px 0 12px; }
  .album-grid > * { min-width: 130px; max-width: 170px; }
  .album-grid-wrapper::before,
  .album-grid-wrapper::after { display: none; }
}

@media (max-width: 480px) {
  .album-grid { gap: 8px; }
  .album-grid > * { min-width: 110px; max-width: 140px; }
}
```

**Giảm spacing albums-section:**
```css
.albums-section {
  margin-bottom: 8px;
}

.scroller-header {
  padding-top: 10px;
  padding-bottom: 8px;
}
```

### 3. Xoá CSS cũ không còn dùng

Xoá các block sau:
- `.album-grid { display: grid; ... }` — base style
- `@media (min-width: 641px) and (max-width: 1024px) { .album-grid { ... } }`
- `@media (max-width: 640px) { .album-grid { ... } }` — chỉ phần album-grid, giữ các rule khác
- `@media (max-width: 480px) { .album-grid { ... } }` — chỉ phần album-grid

### 4. Clean up — xoá dead code/residual

Sau khi thay đổi, search file để xoá:
- Xoá `.album-grid` gap rules cũ nếu còn sót
- Xoá `grid-template-columns` references cũ cho album-grid
- Nếu có cả `.album-grid-wrapper` và gradient CSS song song, gom lại

## Verify

```bash
cd /home/ubuntu/gallery-repo/gallery/frontend && npm run build 2>&1
```
0 errors.

## RULES

- KHÔNG đụng desktop CSS không liên quan
- KHÔNG đụng AlbumCard.vue
- KHÔNG thay đổi JS logic
- Chỉ sửa GalleryGrid.vue
