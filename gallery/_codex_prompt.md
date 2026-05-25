# IMPLEMENT PHASE 1 + 2 + 3: Full Mobile UI/UX Overhaul

Gallery Vue 3 app at `/home/ubuntu/gallery-repo/gallery/frontend/`.
Git tag `baseline-pre-ux` at `/home/ubuntu/gallery-repo/gallery/`.

## RULE TỐI THƯỢNG: KHÔNG đụng desktop CSS (>1024px). KHÔNG đụng base CSS không liên quan đến mobile.

## FILE STRUCTURE
- `frontend/src/App.vue` — shell layout, header, sidebar, theme toggle, search
- `frontend/src/components/GalleryGrid.vue` — grid/main content
- `frontend/src/components/Lightbox.vue` — lightbox
- `frontend/src/styles/main.scss` — global styles

---

## PHASE 1: CSS-ONLY (ưu tiên làm TRƯỚC, không đụng HTML)

### 1.1 Touch target mobile (@media max-width: 640px)
Trong App.vue, thêm vào các nút trong phone block:
```css
.hamburger-btn,
.settings-btn,
.search-box,
.theme-toggle {
  min-width: 44px;
  min-height: 44px;
}
```
(Không làm button bị phình — dùng padding/box-shadow để mở rộng hit area)

### 1.2 Grid density tối đa (GalleryGrid.vue)
Trong `@media (max-width: 640px)` block:
- `.gallery-grid` gap: 6px
- `.photo-grid` hoặc container ảnh: gap 6px, padding 0 4px
- Album grid: gap 8px

### 1.3 De-emphasize grid slider (GalleryGrid.vue)
Trong phone block, `.grid-slider`:
- Ẩn slider-tooltip
- Ẩn slider-count-badge
- Chỉ giữ input[type=range] + LayoutGrid icon

---

## PHASE 2: STRUCTURAL (sửa HTML + CSS, không tạo component mới)

### 2.1 Search full-width bar (App.vue)

**Thay đổi HTML:**
Trong `.header-actions`, thay `.search-box` hiện tại (icon expand) bằng search bar luôn visible trên mobile:

```html
<div class="search-box mobile">
  <Search :size="16" class="search-icon" />
  <input
    v-model="galleryStore.searchQuery"
    type="search"
    placeholder="Search images..."
    autocomplete="off"
  />
  <button v-if="galleryStore.searchQuery" class="clear-btn" @click="galleryStore.clearSearch()" type="button">
    <X :size="14" />
  </button>
</div>
```

**CSS mobile:**
```css
.search-box.mobile {
  flex: 1;
  min-width: 0;
  height: 36px;
  padding: 0 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 10px;
  border: 1px solid var(--border-color, rgba(0,0,0,0.12));
  background: var(--surface-color);
}

.search-box.mobile input {
  flex: 1;
  border: none;
  background: transparent;
  padding: 0;
  font-size: 14px;
  color: var(--text-color);
  outline: none;
  min-width: 0;
}
.search-box.mobile input::placeholder {
  color: var(--muted-text);
}
```

Xoá class `.expanded` và `.search-backdrop` logic (ko cần overlay nếu search bar always visible).

### 2.2 Theme toggle → Ẩn khỏi mobile header

Trên mobile (640px), ẩn `.theme-toggle`:
```css
.theme-toggle {
  display: none;
}
```
(Giữ nguyên cho desktop & tablet)

### 2.3 Settings btn → Ẩn khỏi mobile header

```css
.settings-btn {
  display: none;
}
```
(Chuyển vào More tab sau này)

### 2.4 Breadcrumb → Back button (GalleryGrid.vue)

Trên mobile, breadcrumb dài bị ẩn. Thay bằng simple back button + folder name:
- Giữ `.nav-btn.back` (đã có) nhưng to hơn
- Ẩn breadcrumb-wrap hoàn toàn trên mobile
- Thêm `.current-folder-name` text bên cạnh back button

CSS mobile:
```css
.breadcrumb-wrap {
  display: none;
}

.nav-btn.back {
  display: inline-flex;
  width: 32px;
  height: 32px;
}
```

### 2.5 Hide grid controls (sort, grid slider) vào overflow (GalleryGrid.vue)

Trên mobile, sort và grid slider không cần visible. Ẩn chúng:
```css
.sort-trigger {
  display: none;
}
.grid-slider {
  display: none;
}
```

### 2.6 Mobile header mới — chỉ search bar

Sau Phase 2, mobile header sẽ chỉ gồm:
```
┌──────────────────────────────────┐
│ [← Back] [🔍 Search...] [X]     │ → 48-56px
├──────────────────────────────────┤
│ (grid content)                    │
└──────────────────────────────────┘
```

---

## PHASE 3: BOTTOM NAVIGATION + NEW COMPONENTS

### 3.1 Tạo BottomNavigationBar.vue

**File mới:** `frontend/src/components/BottomNavigationBar.vue`

```vue
<template>
  <nav class="bottom-nav">
    <button 
      v-for="tab in tabs" :key="tab.id"
      class="nav-item" 
      :class="{ active: activeTab === tab.id }"
      @click="$emit('navigate', tab.id)"
    >
      <component :is="tab.icon" :size="22" />
      <span class="nav-label">{{ tab.label }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { Home, FolderOpen, Search, Settings } from 'lucide-vue-next'

defineProps<{
  activeTab: string
}>()

defineEmits<{
  navigate: [tabId: string]
}>()

const tabs = [
  { id: 'photos', icon: Home, label: 'Photos' },
  { id: 'albums', icon: FolderOpen, label: 'Albums' },
  { id: 'search', icon: Search, label: 'Search' },
  { id: 'more', icon: Settings, label: 'More' },
]
</script>

<style scoped>
.bottom-nav {
  display: flex;
  align-items: center;
  justify-content: space-around;
  height: 56px;
  background: var(--surface-color);
  border-top: 1px solid var(--border-color, rgba(0,0,0,0.08));
  padding: 4px 0;
  flex-shrink: 0;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border: none;
  background: transparent;
  color: var(--muted-text);
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 8px;
  transition: color 0.2s;
  flex: 1;
}

.nav-item.active {
  color: var(--primary-color, #d6a15d);
}

.nav-label {
  font-size: 10px;
  line-height: 1;
}

@media (max-width: 360px) {
  .nav-label {
    display: none;
  }
}
</style>
```

### 3.2 Tích hợp vào App.vue

Trong template, thêm `<BottomNavigationBar />` SAU `.content` và TRƯỚC `<Lightbox />`:

```html
  </section> <!-- end .content -->
</div> <!-- end .layout -->

<!-- Bottom nav - only on mobile/tablet -->
<BottomNavigationBar 
  v-if="isMobile"
  active-tab="photos"
  @navigate="handleBottomNav"
/>

<Lightbox />
```

**Chỉ hiện trên mobile** — desktop giữ nguyên sidebar.

Thêm state:
```ts
const activeBottomTab = ref('photos')

function handleBottomNav(tabId: string) {
  activeBottomTab.value = tabId
  // TODO: implement tab switching
}
```

**CSS cho mobile:** khi bottom nav visible, content cần có `padding-bottom`:
```css
@media (max-width: 640px) {
  .content {
    padding-bottom: 0;  /* bottom nav thay thế padding */
  }
}
```

### 3.3 Albums Tab (thay thế mobile sidebar)

Tạo state trong App.vue: khi `activeBottomTab === 'albums'`, thay vì show sidebar overlay, show albums view inline.

Đơn giản nhất: giữ sidebar drawer pattern nhưng trigger từ bottom nav Albums tab thay vì hamburger.

### 3.4 Bỏ hamburger menu

Xoá hamburger-btn khỏi mobile header HTML (chỉ trên mobile, desktop giữ).

Trong template, wrapper hamburger-btn với `v-if="!isMobile"`:
```html
<button v-if="!isMobile" class="hamburger-btn" ...>
```

### 3.5 More tab → SettingsModal

Khi bấm More tab, mở SettingsModal. Trong App.vue:
```ts
function handleBottomNav(tabId: string) {
  if (tabId === 'more') {
    isSettingsOpen.value = true
  }
}
```

### 3.6 Full mobile header mới (sau Phase 3)

```
┌──────────────────────────────────┐
│ [🔍 Search images...]            │ 48px
├──────────────────────────────────┤
│ (grid content — full height)     │
├──────────────────────────────────┤
│ 🖼️  📁  🔍  ⚙️                │ 56px bottom nav
└──────────────────────────────────┘
```

---

## VERIFICATION

Sau mỗi phase, chạy:
```bash
cd /home/ubuntu/gallery-repo/gallery/frontend && npm run build 2>&1
```
Build phải 0 lỗi.

## IMPORTANT NOTES

- Desktop (>1024px) KHÔNG được thay đổi
- Tablet (641-1024px) chỉ thay đổi nếu cần cho consistency
- KHÔNG format code không liên quan
- KHÔNG thay đổi JS logic không cần thiết
- Back/forward navigation, lightbox, gallery grid content — giữ nguyên
