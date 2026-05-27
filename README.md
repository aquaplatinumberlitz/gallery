# Museum Art Gallery - Local AI Image Viewer

<p align="center">
  <img src="https://img.shields.io/badge/Vue.js-3.5-4FC08D?style=flat-square&logo=vue.js" alt="Vue 3">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vite-Latest-646CFF?style=flat-square&logo=vite" alt="Vite">
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript" alt="TypeScript">
  <img src="https://img.shields.io/badge/License-Personal_Use-orange?style=flat-square" alt="License">
</p>

Ứng dụng web xem ảnh cục bộ (Local Gallery) **chuyên dụng cho ảnh AI** (Stable Diffusion, SwarmUI, ComfyUI). Tập trung vào trải nghiệm người dùng mượt mà, giao diện hiện đại (Glassmorphism/Neon) và khả năng đọc Metadata chi tiết.

> ⚠️ **Lưu ý:** Ứng dụng được thiết kế để chạy **local** trên máy cá nhân, không dành cho deploy public.

---

## 🚀 Tính năng nổi bật

### 📁 Duyệt File & Thư Mục
- **Quét thư mục đệ quy** - Hiển thị cây thư mục (Folder Tree) dạng collapsible
- **Virtual Scrolling** - Xử lý mượt mà hàng nghìn ảnh với `vue-virtual-scroller` (RecycleScroller)
- **Album Preview** - Hiển thị ảnh cover cho mỗi folder, scroll ngang với điều hướng mũi tên
- **Breadcrumb Navigation** - Điều hướng nhanh với dropdown cho đường dẫn dài
- **Infinite Scroll** - Tự động load thêm ảnh khi cuộn xuống (200 ảnh/trang)

### 📱 Device-Optimized UX (480/768/1024 Breakpoints)
- **Breakpoints unified**: `useDevice.ts` là single source of truth — không còn inline `window.innerWidth`
- **4 device tiers**: compact (<480px), phone (480-767px), tablet (768-1023px), desktop (≥1024px)
- **iPhone 6.1" (<480px)**: 1-column grid, compact MobileHeader (8px padding), BottomBar 36px pill, AlbumCard 130px cover, LightboxMobileSheet tighter spacing
- **iPad Mini 8.4" (480-767px)**: 2-column grid, sidebar overlay 240px
- **iPad 10.2" / Pro 11" (768-1023px)**: 3-column grid, sidebar persistent 240px
- **iPad Pro 13" / PC 27" (≥1024px)**: 4+ column grid, sidebar 280px, full desktop AppHeader
- **MobileHeader** - Thanh header riêng cho mobile với hamburger menu, search expandable, theme toggle
- **MobileFloatingBottomBar** - Thanh điều hướng dạng pill nổi: Back/Forward, tên folder, mở Explorer
- **Ẩn/hiện khi scroll** - Dùng rAF-throttled scroll listener (không còn polling 200ms)
- **Sidebar overlay** - Chuyển sang overlay trên mobile (<768px)

### 🔍 Hỗ trợ Metadata AI Mạnh Mẽ
- **Auto-detect Tool**: Tự động nhận diện **A1111, SwarmUI, ComfyUI**
- **Chi tiết đầy đủ**: Prompt, Negative Prompt, Seed, Steps, CFG, Model, Sampler, Scheduler
- **LoRA Support**: Tự động tách và highlight LoRA với trọng số (hỗ trợ cả format cũ/mới của SwarmUI)
- **Copy nhanh**: One-click copy Prompt, Seed và các thông số

### 🎨 Giao Diện Hiện Đại
- **Dual Theme**: 
  - 🌞 **Light Mode** - Museum/Elegant với màu kem ấm
  - 🌙 **Dark Mode** - Neon/Cyberpunk với hiệu ứng glow
- **Lightbox Pro**: 
  - Fullscreen mode
  - Điều hướng bằng phím mũi tên & cuộn chuột
  - 3 biến thể panel theo thiết bị: Desktop (sidebar phải), Tablet (2 cột), Mobile (bottom sheet dạng tab)
  - Preload ảnh kế tiếp để chuyển ảnh mượt mà
- **Material Design 3**: Elevation shadows, smooth transitions
- **Glow Bleed Effect**: Hiệu ứng glow neon cam tràn viền thông qua `GlowContainer` pattern

### ⚡ Performance & UX
- **LRU Cache**: 1GB cho thumbnails, 100MB cho metadata
- **Thumbnail API**: Trả về WebP tối ưu thay vì ảnh gốc
- **Lazy Loading**: Chỉ load ảnh khi vào viewport
- **Lightbox preload → thumbnail**: Preload ảnh kế tiếp dùng thumbnail 800px (tiết kiệm ~80% bandwidth)
- **os.scandir()**: Backend scan dùng iterator thay vì `iterdir()` (không extra stat syscall)
- **Scroll visibility**: rAF-throttled + MutationObserver limited scope (không còn polling 200ms, không còn observer toàn document.body)
- **Natural Sort**: Sắp xếp giống Windows Explorer (1, 2, 10 thay vì 1, 10, 2)
- **Instant Search**: Lọc ảnh theo tên real-time
- **Code Splitting**: Lightbox được lazy-load qua `defineAsyncComponent`

### ♿ Accessibility (WCAG 2.1)
- Screen reader support với ARIA labels
- Keyboard navigation đầy đủ (Tab, Escape, Arrow keys)
- Focus trap cho modals và Lightbox
- Hỗ trợ `prefers-reduced-motion` và `prefers-contrast: high`

### 🎭 Intro Page
- Hiển thị ngẫu nhiên trang chào mừng mỗi lần mở app
- Nút "Enter Gallery" với hiệu ứng Glassmorphism
- Preview mode từ Settings
- Dễ dàng tùy biến bằng cách thêm HTML vào `public/landpage/`

---

## 🛠 Yêu cầu hệ thống

| Yêu cầu | Phiên bản | Ghi chú |
|---------|-----------|---------|
| **Python** | 3.10+ | Chạy Backend API |
| **Node.js** | 18+ | Chạy Frontend |
| **pnpm** (tùy chọn) | Latest | Nhanh hơn npm |

---

## ⚙️ Cài đặt & Khởi động

### 🚀 Cách 1: Tự động (Khuyên dùng)

Script `start.py` sẽ tự động:
- Tạo Python virtual environment (`.venv_win` hoặc `.venv_linux`)
- Cài đặt dependencies (pip & npm/pnpm)
- Khởi động cả Backend và Frontend
- Mở trình duyệt

```powershell
# Windows (PowerShell/CMD)
python start.py

# Linux/macOS
python3 start.py
```

### 🔧 Cách 2: Thủ công

**Terminal 1 - Backend:**
```powershell
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```powershell
cd frontend
npm install   # hoặc: pnpm install
npm run dev   # hoặc: pnpm dev
```

**Truy cập:** http://localhost:5173

---

## 📂 Cấu trúc dự án

```
gallery-app/
├── start.py                      # 🚀 Script khởi động tự động
├── backend/
│   ├── main.py                   # FastAPI server + API endpoints
│   └── requirements.txt          # Python dependencies
├── frontend/
│   ├── public/
│   │   └── landpage/             # 🎭 HTML templates cho intro page
│   └── src/
│       ├── App.vue               # Layout chính (Sidebar + Content + Mobile UI)
│       ├── main.ts               # Entry point
│       ├── components/
│       │   ├── GalleryGrid.vue          # Lưới ảnh + Virtual scroll + Sort
│       │   ├── Lightbox.vue             # Xem ảnh chi tiết + Metadata (lazy-loaded)
│       │   ├── LightboxDesktopPanel.vue # Metadata panel cho desktop
│       │   ├── LightboxTabletPanel.vue  # 2-column sheet cho iPad
│       │   ├── LightboxMobileSheet.vue  # Bottom sheet dạng tab cho phone
│       │   ├── PhotoCard.vue            # Card ảnh với loading placeholder
│       │   ├── AlbumCard.vue            # Card folder với neon glow effect
│       │   ├── AlbumScroller.vue        # Scroll ngang albums + arrow navigation
│       │   ├── GlowContainer.vue        # Wrapper cho hiệu ứng glow bleed
│       │   ├── FolderTreeItem.vue       # Cây thư mục recursive
│       │   ├── Breadcrumb.vue           # Navigation path với dropdown
│       │   ├── AppHeader.vue            # Header cho desktop/tablet
│       │   ├── MobileHeader.vue         # Header riêng cho mobile
│       │   ├── MobileFloatingBottomBar.vue # Thanh điều hướng pill cho mobile
│       │   ├── BottomNavigationBar.vue  # Legacy: bottom nav cũ (không dùng)
│       │   ├── IntroScreen.vue          # Màn hình chào mừng
│       │   ├── SettingsModal.vue        # Hộp thoại cài đặt
│       │   ├── SidebarHeader.vue        # Header của sidebar
│       │   ├── SkeletonLoader.vue       # Loading skeleton
│       │   ├── EmptyState.vue           # Các trạng thái rỗng
│       │   └── Toast*.vue               # Hệ thống notification
│       ├── stores/
│       │   ├── gallery.ts    # State: folders, images, navigation, search
│       │   ├── lightbox.ts   # State: xem ảnh, metadata
│       │   └── toast.ts      # State: notifications
│       ├── services/
│       │   └── api.ts        # Axios client + error handling
│       ├── composables/
│       │   ├── useScrollVisibility.ts  # Ẩn/hiện mobile bars khi scroll
│       │   ├── useDevice.ts            # Breakpoint detection (singleton)
│       │   ├── useColumnResize.ts      # Tính toán cột/resize grid
│       │   ├── useNaturalSort.ts       # Natural sort cho filename
│       │   ├── useClipboard.ts         # Copy to clipboard
│       │   ├── useFocusTrap.ts         # Focus trap cho modals
│       │   └── useToast.ts             # Toast helper
│       ├── directives/
│       │   └── clickOutside.ts         # Click-outside directive
│       ├── styles/
│       │   ├── main.scss               # CSS Variables + Global styles + Theme
│       │   ├── tokens.css              # Design tokens (shadows, glow)
│       │   ├── _lightbox-shared.scss   # Shared lightbox styles
│       │   ├── _lightbox-desktop.scss  # Desktop panel styles
│       │   ├── _lightbox-tablet.scss   # iPad panel styles
│       │   └── _lightbox-mobile.scss   # Phone panel styles
│       ├── types/
│       │   └── index.ts                # TypeScript interfaces
│       └── utils/
│           └── loraHighlighter.ts      # Highlight <lora:...> trong prompt
└── resource/                 # Tài liệu tham khảo (palette, poses)
```

---

## 🔌 API Endpoints

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/api/scan?path=...` | Quét thư mục, trả về folders & images (có pagination) |
| `GET` | `/api/image?path=...` | Serve ảnh gốc |
| `GET` | `/api/thumbnail?path=...&max_size=600` | Serve thumbnail WebP (cached) |
| `GET` | `/api/metadata?path=...` | Đọc metadata AI từ ảnh |
| `GET` | `/api/open-folder` | Mở folder trong Explorer (disabled mặc định trên VPS) |
| `GET` | `/api/health` | Health check: `{\"status\": \"ok\"}` |
| `GET` | `/api/landing-pages` | Lấy danh sách intro pages |

---

## 📊 Tech Stack

| Layer | Technology | Phiên bản | Ghi chú |
|-------|------------|---------|---------|
| **Backend** | FastAPI | Latest | Async, high performance |
| **Image Processing** | Pillow | Latest | Metadata extraction, thumbnail generation |
| **Cache** | cachetools (LRU) | Latest | 1GB thumbnails + 100MB metadata |
| **Frontend** | Vue 3 | 3.5 | Composition API + `<script setup>` |
| **Build Tool** | Vite | Latest | HMR, fast builds |
| **State** | Pinia | Latest | Type-safe stores |
| **HTTP Client** | Axios | Latest | API calls |
| **Virtual Scroll** | vue-virtual-scroller | 2.0 | Large lists (RecycleScroller) |
| **Styling** | SCSS | Latest | CSS Variables for theming |
| **Icons** | Lucide Vue Next | Latest | Feather-style icons |
| **Fonts** | Cinzel, Inter, JetBrains Mono | - | Google Fonts |

---

## 🎨 Theming

Ứng dụng hỗ trợ 2 theme được định nghĩa qua CSS Variables:

```scss
// Light Mode (default)
--bg-color: #f5eee6;        // Kem nhẹ
--surface-color: #ffffff;   // Trắng
--title-color: #143d60;     // Navy đậm
--primary-color: #ff6b35;   // Cam neon

// Dark Mode
--bg-color: #0a0a0a;        // Đen
--surface-color: #111111;   // Xám đậm
--title-color: #ff6b35;     // Cam neon
--neon-border-color: #08f;  // Xanh neon
```

---

## ⌨️ Phím tắt

| Phím | Chức năng |
|------|-----------|
| `←` / `→` | Chuyển ảnh trước/sau trong Lightbox |
| `Esc` | Đóng Lightbox / Sidebar (mobile) |
| `Scroll` | Chuyển ảnh trong Lightbox |
| `Tab` | Focus navigation |
| `F` | Fullscreen (trong Lightbox) |

---

## 📝 Ghi chú kỹ thuật

- **Natural Sort**: Sử dụng `Intl.Collator` với `numeric: true` để sắp xếp `1, 2, 10` thay vì `1, 10, 2`
- **SwarmUI Metadata**: Hỗ trợ cả format cũ (List String) và mới (List Object) cho LoRAs
- **Path Access**: `is_safe_path()` return `True` cho phép truy cập mọi ổ đĩa (Local Use Only)
- **Intro System**: Dùng `iframe` để load HTML từ `public/landpage/`, tách biệt hoàn toàn với app
- **Image Limits**: Max 75MB file size, 100 megapixels để tránh decompression bombs
- **Glow Bleed**: Sử dụng `overflow: clip` (không phải `hidden`) để box-shadow tràn viền, `GlowContainer` wrapper với `pointer-events: none` tránh xung đột hover
- **Mobile Scroll Visibility**: `useScrollVisibility` gắn vào `.vue-recycle-scroller`, dùng `MutationObserver` để re-attach khi DOM thay đổi. Các mobile bars ẩn khi cuộn xuống, hiện khi cuộn lên
- **Sidebar responsive**: Desktop (280px persistent), Tablet (240px persistent), Phone (overlay fixed)

---

## 🛣️ Roadmap (Tương lai)

- [ ] Image comparison mode (side-by-side)
- [ ] Batch metadata export (JSON/CSV)
- [ ] Favorites / Collections
- [ ] Image tagging system
- [ ] WebSocket for real-time folder updates

---

## 📄 License

Personal Use Only - Không dành cho deploy public.

---

<p align="center">
  <i>Made with ❤️ for AI Art enthusiasts</i>
</p>
