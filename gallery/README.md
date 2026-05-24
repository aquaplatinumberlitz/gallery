# Museum Art Gallery - Local AI Image Viewer

<p align="center">
  <img src="https://img.shields.io/badge/Vue.js-3.5-4FC08D?style=flat-square&logo=vue.js" alt="Vue 3">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vite-7.2-646CFF?style=flat-square&logo=vite" alt="Vite">
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?style=flat-square&logo=typescript" alt="TypeScript">
  <img src="https://img.shields.io/badge/License-Personal_Use-orange?style=flat-square" alt="License">
</p>

Ứng dụng web xem ảnh cục bộ (Local Gallery) **chuyên dụng cho ảnh AI** (Stable Diffusion, SwarmUI, ComfyUI). Tập trung vào trải nghiệm người dùng mượt mà, giao diện hiện đại (Glassmorphism/Neon) và khả năng đọc Metadata chi tiết.

> ⚠️ **Lưu ý:** Ứng dụng được thiết kế để chạy **local** trên máy cá nhân, không dành cho deploy public.

---

## 🚀 Tính năng nổi bật

### 📁 Duyệt File & Thư Mục
- **Quét thư mục đệ quy** - Hiển thị cây thư mục (Folder Tree) dạng collapsible
- **Virtual Scrolling** - Xử lý mượt mà hàng nghìn ảnh với `vue-virtual-scroller`
- **Album Preview** - Hiển thị 3 ảnh mới nhất làm cover cho mỗi folder
- **Breadcrumb Navigation** - Điều hướng nhanh với dropdown cho đường dẫn dài

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
  - Metadata panel chi tiết
  - Preload ảnh kế tiếp để chuyển ảnh mượt mà
- **Material Design 3**: Elevation shadows, smooth transitions

### ⚡ Performance & UX
- **LRU Cache**: 1GB cho thumbnails, 100MB cho metadata
- **Thumbnail API**: Trả về WebP tối ưu thay vì ảnh gốc
- **Lazy Loading**: Chỉ load ảnh khi vào viewport
- **Natural Sort**: Sắp xếp giống Windows Explorer (1, 2, 10 thay vì 1, 10, 2)
- **Instant Search**: Lọc ảnh theo tên real-time

### ♿ Accessibility (WCAG 2.1)
- Screen reader support với ARIA labels
- Keyboard navigation đầy đủ
- Focus trap cho modals
- Hỗ trợ `prefers-reduced-motion` và `prefers-contrast: high`

### 🎭 Intro Page
- Hiển thị ngẫu nhiên trang chào mừng mỗi lần mở app
- Nút "Enter Gallery" với hiệu ứng Glassmorphism
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
├── start.py                 # 🚀 Script khởi động tự động
├── backend/
│   ├── main.py              # FastAPI server + API endpoints
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── public/
│   │   └── landpage/        # 🎭 HTML templates cho intro page
│   └── src/
│       ├── App.vue          # Layout chính (Sidebar + Content)
│       ├── main.ts          # Entry point
│       ├── components/
│       │   ├── GalleryGrid.vue      # Lưới ảnh + Virtual scroll
│       │   ├── Lightbox.vue         # Xem ảnh chi tiết + Metadata
│       │   ├── PhotoCard.vue        # Card ảnh với shimmer loading
│       │   ├── AlbumCard.vue        # Card folder với 3D effect
│       │   ├── FolderTreeItem.vue   # Cây thư mục recursive
│       │   ├── Breadcrumb.vue       # Navigation path
│       │   ├── EmptyState.vue       # Các trạng thái rỗng
│       │   └── Toast*.vue           # Notification system
│       ├── stores/
│       │   ├── gallery.ts    # State: folders, images, navigation
│       │   ├── lightbox.ts   # State: xem ảnh, metadata
│       │   └── toast.ts      # State: notifications
│       ├── services/
│       │   └── api.ts        # Axios client + error handling
│       ├── composables/
│       │   ├── useAnnouncer.ts   # Screen reader announcements
│       │   ├── useFocusTrap.ts   # Modal focus management
│       │   └── useToast.ts       # Toast helper
│       ├── styles/
│       │   └── main.scss     # CSS Variables + Theme styles
│       └── types/
│           └── index.ts      # TypeScript interfaces
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
| `POST` | `/api/open-folder?path=...` | Mở folder trong Explorer |
| `GET` | `/api/landing-pages` | Lấy danh sách intro pages |

---

## 📊 Tech Stack

| Layer | Technology | Version | Ghi chú |
|-------|------------|---------|---------|
| **Backend** | FastAPI | Latest | Async, high performance |
| **Image Processing** | Pillow | Latest | Metadata extraction, thumbnail generation |
| **Cache** | cachetools (LRU) | Latest | 1GB thumbnails + 100MB metadata |
| **Frontend** | Vue 3 | 3.5.24 | Composition API |
| **Build Tool** | Vite | 7.2.4 | HMR, fast builds |
| **State** | Pinia | 3.0.4 | Type-safe stores |
| **HTTP Client** | Axios | 1.13.2 | API calls |
| **Virtual Scroll** | vue-virtual-scroller | 2.0.0-beta.8 | Large lists |
| **Styling** | SCSS | 1.94.2 | CSS Variables for theming |
| **Icons** | FontAwesome Pro | 7.1 | Duotone, Solid, Regular |
| **Fonts** | Cinzel, Inter, JetBrains Mono | - | Local fonts |

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

---

## 📝 Ghi chú kỹ thuật

- **Natural Sort**: Sử dụng `re.split(r'(\d+)', s)` để sắp xếp `1, 2, 10` thay vì `1, 10, 2`
- **SwarmUI Metadata**: Hỗ trợ cả format cũ (List String) và mới (List Object) cho LoRAs
- **Path Access**: `is_safe_path()` return `True` cho phép truy cập mọi ổ đĩa (Local Use Only)
- **Intro System**: Dùng `iframe` để load HTML từ `public/landpage/`, tách biệt hoàn toàn với app
- **Image Limits**: Max 75MB file size, 100 megapixels để tránh decompression bombs

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
  <i>Made with ❤️ for AI Art enthusiasts</i><br>
  <i>Document generated by GitHub Copilot - November 2025</i>
</p>
