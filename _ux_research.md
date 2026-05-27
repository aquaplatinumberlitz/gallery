# Nghiên cứu UI/UX Mobile Photo Gallery App — Header, Navigation, Layout

> Ngày: 2026-05-25  
> Mục tiêu: So sánh pattern mobile gallery app hiện đại với gallery Vue hiện tại

---

## 1. Khảo sát Header của các App Ảnh Hiện Đại

### 1.1 Google Photos (iOS & Android)

| Thuộc tính | Giá trị |
|---|---|
| **Header type** | Single-row collapsible (ẩn khi scroll xuống, hiện khi scroll lên) |
| **Chiều cao** | ~56dp (Android) / ~44pt + status bar (iOS) |
| **Nội dung** | Search bar (chiếm gần hết width) + profile avatar (góc phải) |
| **Bottom nav** | Photos · Search · Sharing · Library |
| **Điểm đặc biệt** | Thanh search là element chính của header, không có title/brand text. Khi scroll xuống, header + bottom nav đều collapsed, chỉ giữ lại FAB. |

### 1.2 Apple Photos (iOS)

| Thuộc tính | Giá trị |
|---|---|
| **Header type** | Single-row navigation bar (navigation bar tiêu chuẩn iOS) |
| **Chiều cao** | ~44pt + status bar (~56pt total) |
| **Nội dung** | Title "Photos" (left) + Edit/Select buttons (right) |
| **Bottom nav** | Photos · For You · Albums · Search |
| **Điểm đặc biệt** | Thanh navigation rất tối giản. Trong tab Albums có thể có thêm segment control. Search là một tab riêng ở bottom nav, không phải icon trong header. |

### 1.3 Pinterest

| Thuộc tính | Giá trị |
|---|---|
| **Header type** | Single-row với search bar chiếm ưu thế |
| **Chiều cao** | ~56dp |
| **Nội dung** | Search bar (full width) + notification bell + profile |
| **Bottom nav** | Home · Search · Saved · Profile |
| **Điểm đặc biệt** | Search bar ở header là element chính, gần như chiếm toàn bộ header. Không có brand text. |

### 1.4 Instagram

| Thuộc tính | Giá trị |
|---|---|
| **Header type** | Single-row, chia 3 cột |
| **Chiều cao** | ~44pt + status bar |
| **Nội dung** | Logo/brand (left) · Search/Explore (center) · Actions (right: like, DM) |
| **Bottom nav** | Home · Search · Reels · Shop · Profile |
| **Điểm đặc biệt** | Header rất gọn. Logo được giữ nhưng nhỏ. Các action buttons tối giản. |

### 1.5 Behance

| Thuộc tính | Giá trị |
|---|---|
| **Header type** | Single-row minimal |
| **Chiều cao** | ~48dp |
| **Nội dung** | Logo + Search icon + Notifications |
| **Bottom nav** | Home · Search · Following · Profile |
| **Điểm đặc biệt** | Header rất minimal. Search là icon nhỏ, không phải text input. |

### 1.6 Flickr

| Thuộc tính | Giá trị |
|---|---|
| **Header type** | Single-row |
| **Chiều cao** | ~48dp |
| **Nội dung** | Logo (left) · Upload (right) |
| **Bottom nav** | Home · Explore · Albums · Notifications · Profile |

### 1.7 500px

| Thuộc tính | Giá trị |
|---|---|
| **Header type** | Single-row minimal |
| **Chiều cao** | ~44pt |
| **Nội dung** | Logo + Search icon |
| **Bottom nav** | Home · Popular · Following · Profile |

---

## 2. Tổng Kết Pattern Chung

### Header Design — Single Row là Chuẩn

| Pattern | App áp dụng |
|---|---|
| **Single row + search bar dominant** | Google Photos, Pinterest |
| **Single row + logo + actions** | Instagram, Behance, Flickr, 500px |
| **Single row + title + edit buttons** | Apple Photos |
| **Multi-row header** | ❌ Không app nào dùng |

**Kết luận:** 100% các app ảnh hiện đại dùng **single-row header**. Không có app nào dùng multi-row header với brand hero, subtitle, eyebrow text như gallery Vue hiện tại.

### Chiều Cao Header

| Platform | Chiều cao điển hình |
|---|---|
| **Android Material Design** | 56dp (standard) / 48dp (compact) |
| **iOS** | 44pt + status bar (20pt) = ~64pt total |
| **Minimum touch target** | 48dp (Material) / 44pt (iOS HIG) |

### Bottom Navigation — Pattern Bắt Buộc

| App | Bottom Nav Items |
|---|---|
| Google Photos | 4 items |
| Apple Photos | 4 items |
| Pinterest | 4 items |
| Instagram | 5 items |
| Behance | 4 items |
| Flickr | 5 items |
| 500px | 4 items |

**Không có app ảnh hiện đại nào dùng hamburger menu làm navigation chính.**  
Tất cả đều dùng bottom navigation bar với 4-5 items.

### Collapsible Header Pattern

- **Google Photos-style:** Header + bottom nav đều ẩn khi scroll xuống, hiện khi scroll lên. Search bar vẫn accessible qua FAB hoặc tap.
- **Standard scroll:** Header fixed, bottom nav fixed (Apple Photos, Instagram).
- **Search-on-scroll:** Khi scroll xuống, search bar thu gọn thành icon (Apple Mail pattern).

---

## 3. So Sánh với Gallery Vue Hiện Tại

### Phân tích Header Mobile Hiện Tại (App.vue @ <640px)

```
┌────────────────────────────────────────────┐
│ [☰] [⚙️]      [🌙] [🔍]                   │
│                                            │  ← content-header
│         🏛️ Museum Art Gallery               │  ← brand-hero (display:none trên mobile)
│         Local collections                  │
└────────────────────────────────────────────┘
```

**Các element trên mobile header (theo thứ tự):**

| Element | Hiện tại | Ghi chú |
|---|---|---|
| Hamburger menu | ✅ | 30x30px icon, toggle sidebar overlay |
| Settings button | ✅ | 30x30px icon, mở SettingsModal |
| Brand hero | ❌ (display:none) | Ẩn trên mobile, nhưng chiếm DOM |
| Theme toggle | ✅ | 28x28px, thu gọn |
| Search | ✅ | Icon thu gọn 30x30px, expand overlay |

### Vấn Đề Chính

1. **Không có bottom navigation** — Navigation hiện tại dựa vào hamburger menu + sidebar overlay. Pattern này đã lỗi thời trên mobile, đặc biệt là với photo gallery app.

2. **Header chưa thực sự single-row** — Trên mobile content-header dùng flex, brand hero ẩn (display:none), nhưng vẫn có mặt trong DOM. Các button còn rải rác.

3. **Thiếu các gesture thông dụng** — Không có pull-to-refresh, swipe để navigate, pinch-to-zoom trong grid.

4. **Search UX chưa tối ưu** — Search expand overlay che toàn màn hình, không có animation mượt, không có search suggestions.

5. **Theme toggle chiếm space quý giá** — Trên mobile, theme toggle 28x28px vẫn chiếm vị trí trong header action bar. Các app khác thường đặt theme/settings trong profile/settings screen.

6. **Hamburger menu cho folder tree** — Trên mobile, sidebar là overlay drawer với folder tree. Pattern này phù hợp cho file manager nhưng không phải chuẩn của photo gallery app.

### So Sánh Chi Tiết

| Tiêu chí | Gallery Vue (mobile) | Google Photos | Apple Photos | Pinterest |
|---|---|---|---|---|
| **Số hàng header** | 1 (flex, ẩn brand) | 1 | 1 | 1 |
| **Bottom nav** | ❌ Không có | ✅ 4 items | ✅ 4 items | ✅ 4 items |
| **Hamburger menu** | ✅ Sidebar drawer | ❌ | ❌ | ❌ |
| **Search** | Icon → expand overlay | Full-width bar | Tab riêng | Full-width bar |
| **Brand/title** | Ẩn trên mobile | Logo nhỏ ở góc | Title text | Logo nhỏ |
| **Chiều cao header** | ~48px | ~56dp | ~44pt | ~56dp |
| **Settings access** | Icon trong header | Profile → Settings | Profile → Settings | Profile → Settings |
| **Theme toggle** | Icon trong header | System-wide auto | System-wide auto | System-wide auto |
| **Collapsible scroll** | ❌ | ✅ | ❌ | ❌ |

---

## 4. Đề Xuất Gallery Mobile Ideal

### 4.1 Header Mobile Đề Xuất

```
┌────────────────────────────────────────────┐
│  [🔍 Search photos...]     [👤]           │  ← single-row header
│                                            │
└────────────────────────────────────────────┘
```

**Kích thước:** 56px (gồm padding 8px trên/dưới)  
**Nội dung:** Search bar chiếm hết width trừ profile icon

### 4.2 Bottom Navigation Đề Xuất

```
┌──────────────┬──────────┬─────────────┬───────┐
│  🖼️ Photos   │ 📁 Albums │ 🔍 Search  │ ⚙️ More │
└──────────────┴──────────┴─────────────┴───────┘
```

- 4 tabs: Photos · Albums · Search · Settings/Profile
- Icon + label (label ẩn trên màn hình rất nhỏ, chỉ giữ icon)
- Chiều cao: 56dp (Material Design guideline)

### 4.3 Element Cần Giữ / Bỏ / Gộp

| Element | Quyết định | Lý do |
|---|---|---|
| **Hamburger menu** | ❌ Bỏ | Thay bằng bottom navigation + folder tree gộp vào tab Albums |
| **Settings button** | ❌ Bỏ khỏi header | Settings → tab More/Settings ở bottom nav hoặc profile screen |
| **Brand hero** | ❌ Bỏ hoàn toàn | Chiếm quá nhiều space, không cần thiết trên mobile |
| **Search** | ✅ Giữ, cải tiến | Search bar full-width trong header thay vì icon expand |
| **Theme toggle** | ❌ Bỏ khỏi header | Chuyển vào Settings screen |
| **Top nav (back/forward)** | ❌ Bỏ khỏi mobile header | Thay bằng swipe gestures hoặc bottom sheet navigation |
| **Breadcrumb** | ❌ Bỏ | Thay bằng current folder name + back chevron |
| **Grid slider** | ❌ Bỏ | Mặc định 2-3 cột trên mobile, không cần tùy chỉnh |
| **Sort dropdown** | ❌ Bỏ khỏi header | Chuyển vào action sheet hoặc overflow menu |

### 4.4 Layout Tối Ưu cho Mobile

```
┌────────────────────────────────────────────┐
│  [🔍 Search...                  ] [👤]     │  ← Header (56px)
├────────────────────────────────────────────┤
│                                            │
│  ┌─────┐ ┌─────┐ ┌─────┐                   │
│  │ 📸  │ │ 📸  │ │ 📸  │                   │  ← Gallery Grid
│  └─────┘ └─────┘ └─────┘                   │    (2-3 columns)
│  ┌─────┐ ┌─────┐ ┌─────┐                   │
│  │ 📸  │ │ 📸  │ │ 📸  │                   │
│  └─────┘ └─────┘ └─────┘                   │
│  ...                                       │
│                                            │
├────────────────────────────────────────────┤
│  🖼️ Photos  📁 Albums  🔍 Search  ⚙️ More  │  ← Bottom Nav (56dp)
└────────────────────────────────────────────┘
```

**Điểm chính:**
- Header fixed top, bottom nav fixed bottom
- Grid scroll ở giữa (full height, không padding lớn)
- Grid 2 cột trên phone nhỏ (<360px), 3 cột trên phone lớn
- Không padding/gap quá lớn (8px thay vì 20px)

### 4.5 Search UX Cải Tiến

**Trạng thái thu gọn (mặc định):**
```
[🔍 Search photos...              ] [👤]
```
- Search bar luôn visible, placeholder text
- Tap vào search bar → keyboard + search results overlay
- Profile icon ở góc phải (user settings)

**Trạng thái mở rộng (khi focus):**
```
┌────────────────────────────────────────────┐
│ [◀ Back] [🔍] [_____________] [✕]         │
├────────────────────────────────────────────┤
│  Recent searches                           │
│  Suggestions                               │
│                                            │
│  Search results overlay                    │
└────────────────────────────────────────────┘
```

### 4.6 Navigation & Gestures

| Gesture | Chức năng |
|---|---|
| **Swipe left/right** | Navigate giữa các folder trong cùng cấp |
| **Swipe down** | Pull-to-refresh (reload current folder) |
| **Tap photo** | Open lightbox |
| **Long press photo** | Multi-select mode |
| **Pinch** | Zoom in/out grid (thay cho grid slider) |
| **Scroll down** | Ẩn header (tùy chọn) |
| **Scroll up** | Hiện header (tùy chọn) |

---

## 5. Kết Luận & Ưu Tiên

### Những thay đổi quan trọng nhất

1. **🔴 Bỏ hamburger menu + sidebar overlay** — Thay bằng bottom navigation bar với 4 tabs: Photos, Albums, Search, More/Settings
2. **🔴 Chuyển search thành element chính của header** — Search bar full-width thay vì icon expand hiện tại
3. **🟡 Đưa brand hero xuống chỉ còn logo/text nhỏ** — Bỏ "Museum Art Gallery" title + "Local collections" eyebrow
4. **🟡 Chuyển theme toggle vào Settings screen** — Giải phóng không gian header quý giá
5. **🟢 Thêm collapsible header pattern** — Header tự động ẩn khi scroll xuống để tối đa không gian xem ảnh
6. **🟢 Thêm grid gesture controls** — Pinch-to-zoom thay cho grid slider

### Header Mobile Lý Tưởng cho Gallery Vue

```
┌────────────────────────────────────────────┐
│  [🔍 Search images...            ] [👤]    │  (56px)
├────────────────────────────────────────────┤
│                                           │
│  (Grid content — full height scroll)      │
│                                           │
├────────────────────────────────────────────┤
│  🖼️ Photos  📁 Albums  🔍 Search  ⚙️ More  │  (56px)
└────────────────────────────────────────────┘
```

---

## 6. Tham Khảo

- Material Design 3 — Bottom Navigation: https://m3.material.io/components/navigation-bar
- Apple HIG — Tab Bars: https://developer.apple.com/design/human-interface-guidelines/tab-bars
- Material Design — Search: https://m3.material.io/components/search
- Google Photos mobile app (iOS & Android)
- Apple Photos mobile app (iOS)
- Pinterest mobile app (iOS & Android)
- Instagram mobile app (iOS & Android)
- Behance mobile app (iOS & Android)
- UX Design Best Practices for Mobile Photo Galleries (2024-2025)
