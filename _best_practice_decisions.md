# Best Practice Decisions for Gallery App

> **Evaluated:** 2026-05-28
> **Scope:** Từng best practice từ research trên 11 platforms — quyết định GIỮ, BỎ, hay ÁP DỤNG CÓ ĐIỀU CHỈNH cho gallery app.
> **Codebase state:** Vue 3 + TypeScript + SCSS, repo tại `/home/ubuntu/gallery-repo`

---

## A. Token Naming Convention

| Aspect | Detail |
|---|---|
| **MD3** | `md-sys-color-surface-container` (6 levels, hierarchical) |
| **Primer (GitHub)** | `--bgColor-default` (category+group+modifier, 3 levels) |
| **Gallery đề xuất** | `--gallery-surface-default` (2 levels) |
| **Hiện tại** | Flat: `--bg-color`, `--surface-color`, `--text-color`, `--primary-color` |

### Quyết định: ✅ ÁP DỤNG CÓ ĐIỀU CHỈNH

**Chọn:** `--gallery-{category}-{group?}-{modifier}` — inspired by Primer (3 levels) nhưng simplified.

**Lý do:**
- MD3 6-level quá nặng cho gallery app nhỏ — gây cognitive overload
- Primer 3-level `{category}{Group}-{modifier}` là sweet spot — đủ semantic, dễ mở rộng
- Gallery prefix `--gallery-*` tránh conflict với CSS vars hiện tại
- KHÔNG xoá vars cũ (`--bg-color`, `--surface-color`) — chỉ THÊM token mới

**Token naming schema:**

```css
--gallery-{category}-{group}-{modifier}
```

| Level | Ví dụ | Ý nghĩa |
|---|---|---|
| category | `surface`, `text`, `border`, `accent`, `radius`, `elevation` | Nhóm chính |
| group (optional) | `album`, `card`, `toast`, `lightbox` | Ngữ cảnh cụ thể |
| modifier | `default`, `dim`, `low`, `high`, `elevated`, `muted`, `hover` | Trạng thái |

**Token examples:**

```css
--gallery-surface-dim              /* Nền page */
--gallery-surface-default          /* Surface chính (card) */
--gallery-surface-elevated         /* Modal/dialog */
--gallery-text-primary             /* Text chính */
--gallery-text-secondary           /* Text phụ */
--gallery-border-default           /* Border thường */
--gallery-accent-primary           /* Accent màu chính */
```

---

## B. Dark Mode Background

| Platform | Color | Ghi chú |
|---|---|---|
| MD3 | #141218 | Purple-ish tint |
| Instagram/Apple | #000000 | Pure black |
| Discord | #313338 | Warm dark gray |
| Gallery hiện tại | **#080808** | Near-black |

### Quyết định: ✅ GIỮ NGUYÊN — #080808

**Lý do:**
- Gallery hiện tại `#080808` là near-black, gần nhất với YouTube (#0F0F0F) và Linear (#0E0E0E)
- Near-black tốt hơn pure black cho mắt khi xem ảnh lâu — giảm ghosting, giảm eye strain
- Không cần đổi sang #0c0c0c (MD3) vì sự khác biệt 4 steps (#080808 → #0c0c0c) là không đáng kể
- Giữ `--bg-color: #080808` — chỉ cần tạo token `--gallery-surface-dim: #080808` ánh xạ đúng giá trị

**Token mới:**
```css
--gallery-surface-dim: #080808   /* = current --bg-color dark */
```

---

## C. Surface Layers

| Platform | Levels | Tên |
|---|---|---|
| MD3 | 6 | dim, container-lowest, container-low, container, container-high, container-highest |
| Discord | 3+ | primary, secondary, tertiary, elevated |
| Gallery hiện tại | **2** | `--surface-color`, `--bg-secondary` |

### Quyết định: ✅ ÁP DỤNG CÓ ĐIỀU CHỈNH — 5 levels

**Chọn:** 5 surface levels (không phải 6 như MD3, không phải 2 như hiện tại).

**Lý do:**
- 2 levels hiện tại quá ít — không có surface cho elevated states (modal, hover)
- 6 levels như MD3 là overkill cho gallery app đơn giản
- 5 levels là sweet spot: đủ cho page → card → hover → modal → tooltip

**Token surface levels:**

```css
--gallery-surface-dim:        #080808  /* Nền page tối nhất — = current --bg-color */
--gallery-surface-low:        #141414  /* Container thấp — container bên trong sidebar */
--gallery-surface-default:    #11100f  /* Surface chính — = current --surface-color */
--gallery-surface-high:       #1c1c1c  /* Surface nổi bật — card hover, elevated items */
--gallery-surface-elevated:   #242424  /* Modal, dialog — = current --bg-secondary-ish */
```

> **Lưu ý:** Các giá trị trên là dark mode. Light mode sẽ có mapping tương ứng với giá trị sáng hơn. KHÔNG thay đổi `--surface-color` hiện tại — token mới chỉ là THÊM.

---

## D. Card Design

### D.1 Border Radius

| Platform | Card Radius |
|---|---|
| MD3 | 12px |
| Twitter | 16px |
| Reddit | 0-4px |
| Linear | 8-12px |
| **Gallery hiện tại** | **12px** (PhotoCard + AlbumCard) |

### Quyết định: ✅ GIỮ NGUYÊN — 12px

**Lý do:**
- Gallery ĐÃ dùng 12px cho cả PhotoCard và AlbumCard — trùng với MD3 sweet spot
- 12px là giá trị tối ưu cho gallery: đủ bo tròn để mềm mại, không quá nhiều để giữ ảnh vuông vức
- Chỉ cần THÊM token: `--gallery-radius-card: 12px` ánh xạ đúng giá trị hiện tại

**Token mới (giá trị giống hệt hiện tại):**
```css
--gallery-radius-sm:    4px    /* Tags, badges — as used */
--gallery-radius-md:    8px    /* Buttons, sidebar items */
--gallery-radius-lg:    12px   /* PhotoCard, AlbumCard — SWEET SPOT */
--gallery-radius-xl:    16px   /* Hero elements */
--gallery-radius-full:  9999px /* Pill/avatar */
```

### D.2 Shadow

| Platform | Shadow Style |
|---|---|
| MD3 | Multi-layer shadow (1px→24px blur) |
| Reddit/Facebook | No shadow — dùng border |
| Linear | Minimal border > shadow |
| **Gallery hiện tại** | **MD3 multi-layer** (trong tokens.css) |

### Quyết định: ✅ GIỮ NGUYÊN shadow hiện tại

**Lý do:**
- Gallery ĐÃ dùng MD3-inspired multi-layer shadow (2 lớp) trong `tokens.css`
- Shadow hiện tại rất tốt: `--shadow-card: 0 1px 2px rgba(...), 0 1px 3px 1px rgba(...)`
- KHÔNG chuyển sang no-shadow (Reddit/Facebook) vì gallery cần elevation để phân biệt card trên surface
- Chỉ THÊM token elevation levels: `--gallery-elevation-sm`, `--gallery-elevation-md`, etc.

---

## E. Navigation Pattern

| Platform | Mobile Navigation |
|---|---|
| Instagram/Twitter | Bottom tab bar |
| Discord/Linear | Sidebar |
| **Gallery hiện tại** | **Desktop: sidebar. Mobile: MobileFloatingBottomBar** |

### Quyết định: ✅ GIỮ NGUYÊN pattern hiện tại

**Lý do:**
- User đã bỏ BottomNavigationBar, giữ MobileFloatingBottomBar — đây là quyết định đã approved
- Pattern hiện tại đúng best practice: **sidebar cho desktop** (Discord/Linear), **floating bottom bar cho mobile** (Instagram-inspired nhưng floating thay vì docked)
- MobileFloatingBottomBar dùng CSS `transition: transform 0.3s cubic-bezier(...)` — timing phù hợp
- Không cần thay đổi. Navigation pattern đã được research và quyết định kỹ.

---

## F. Typography Base Size

| Platform | Base Size | Notes |
|---|---|---|
| MD3 | 16px | Standard |
| Discord | 16px | Standard |
| GitHub | 14px | Dense UI |
| Reddit | 14px | Dense UI |
| Linear | 14px | Dense UI |
| **Gallery hiện tại** | **~16px** (body không có font-size, mặc định browser 16px) | Cinzel cho brand, InterVariable cho body |

### Quyết định: ✅ GIỮ 16px BASE — THÊM token scale

**Lý do:**
- Gallery đã dùng 16px implicit (body không set font-size → browser default 16px)
- 16px phù hợp cho gallery: xem metadata ảnh, tên album — cần dễ đọc
- 14px (GitHub/Linear) quá nhỏ cho gallery vì user đọc tên ảnh, model info
- Cinzel là brand font — **GIỮ NGUYÊN** (không thay bằng system font)
- THÊM typography tokens nhưng KHÔNG thay đổi hardcoded font-size trong components

**Token mới:**
```css
--gallery-font-size-xs:    0.625rem   /* 10px — micro metadata */
--gallery-font-size-sm:    0.75rem    /* 12px — caption */
--gallery-font-size-base:  1rem       /* 16px — body */
--gallery-font-size-lg:    1.25rem    /* 20px — h3 */
--gallery-font-size-xl:    1.5rem     /* 24px — h2 */
--gallery-font-size-2xl:   2rem       /* 32px — h1 */
```

> KHÔNG thay đổi hardcoded `font-size: 13px` trong GalleryGrid.vue, `font-size: 11px` trong SidebarHeader.vue, v.v.

---

## G. Border vs Surface Differentiation

| Approach | Represented by | Cách hoạt động |
|---|---|---|
| **No border** | Facebook | Không dùng border, phân cách bằng surface color khác nhau |
| **Border-based** | Reddit/GitHub | Dùng border để phân cách các section |
| **Kết hợp** | Linear/Discord | Surface differentiation chính + border subtle phụ |

### Quyết định: ✅ KẾT HỢP — ưu tiên surface differentiation, border là secondary

**Lý do:**
- Gallery HIỆN TẠI đã dùng cả hai: surface differentiation (card trên nền page) + border subtle
- Light mode: `--border-color: rgba(0,0,0,0.12)` — rất nhẹ
- Dark mode: `--border-color: rgba(255,255,255,0.075)` — gần như vô hình
- PhotoCard dark: `border: 1px solid rgba(255,255,255,0.06)` — rất subtle
- Facebook approach (no border) không phù hợp vì gallery cần phân biệt photo cards trong grid
- **Chiến lược:** surface differentiation là primary (card surface ≠ page surface), border là secondary để define edges khi cần (card grids, sidebar sections)

---

## H. Lightbox Luôn Dark

### Quyết định: ✅ GIỮ LUÔN DARK — CÓ token hóa

**Lý do:**
- Lightbox luôn dark là quyết định đã approved (Instagram style)
- Hiện tại lightbox dùng hardcode values: `rgba(0, 0, 0, 0.95)`, `#1a1a1a`, `#e0e0e0`, `rgba(255,255,255,0.1)`, etc.
- Nên **token hóa** để maintain dễ hơn, nhưng GIỮ NGUYÊN giá trị
- Token prefix riêng: `--gallery-lightbox-*` — KHÔNG dùng `--gallery-surface-*` chung

**Token mới (giá trị giống hệt hiện tại):**
```css
--gallery-lightbox-overlay:    rgba(0, 0, 0, 0.95)   /* background overlay */
--gallery-lightbox-bg:         #1a1a1a               /* panel background */
--gallery-lightbox-text:       #f5f7fb               /* primary text */
--gallery-lightbox-text-muted: #999                  /* muted text */
--gallery-lightbox-border:     rgba(255, 255, 255, 0.1) /* border */
--gallery-lightbox-accent:     #86efac               /* labels (green) */
```

---

## I. Brand Identity Colors

| Approach | Palette | Platforms |
|---|---|---|
| **Trend: Blue accent** | Blue (#1d9bf0, #4493f8, #5865f2) | GitHub, Twitter, Discord, Facebook, Notion |
| **Gallery hiện tại** | Warm gold/orange | `#d6a15d` gold, `#ff6b35` orange, Pastel Dreamscape |

### Quyết định: ✅ GIỮ PASTEL DREAMSCAPE — KHÔNG theo trend blue

**Lý do:**
- Pastel Dreamscape (warm gold #d6a15d, orange #ff6b35, cream #f5eee6) LÀ identity của gallery
- Đổi sang blue accent sẽ làm mất bản sắc — gallery sẽ trông như 1000 app khác
- Gold/orange palette có research backing: warm colors tạo cảm giác "nostalgia" và "premium" cho photo gallery
- Các blue-accent platforms (GitHub, Twitter, Discord) là app công cụ — gallery là app cảm xúc, cần palette ấm áp
- **Tuy nhiên:** accent indicator (selected state, active link) có thể dùng indigo (#6366f1) như research đề xuất — vì nó trung tính, không gây distraction với ảnh
- Pastel Dreamscape đã được thể hiện qua: `--bg-color: #f5eee6` (cream light), `--primary-color: #ff6b35` (orange), gold gradient dark title

**Chiến lược:**
- **Primary brand (gold/orange):** Giữ nguyên — `--gallery-accent-brand: #d6a15d` / `#ff6b35`
- **Interactive accent (indigo):** Thêm mới — `--gallery-accent-interactive: #6366f1` (cho buttons, links, selected states) — như research đề xuất
- **Neutral background:** Giữ cream `#f5eee6` light, near-black `#080808` dark

---

## J. Micro-interactions Timing

| Platform | Timing | Style |
|---|---|---|
| MD3 | 300ms | Spring animation |
| Linear | 150ms | Linear ease |
| GitHub | 80ms | Fast linear |
| **Gallery hiện tại** | **120ms → 350ms** (không đồng nhất) |

### Quyết định: ✅ CHUẨN HÓA TIMING — tạo token nhưng KHÔNG thay đổi giá trị hiện tại

**Lý do:**
- Gallery hiện tại dùng nhiều timing khác nhau:
  - FolderTreeItem: 120ms ease
  - AppHeader buttons: 120ms ease
  - PhotoCard scale: 280ms cubic-bezier(0.4, 0, 0.2, 1)
  - GalleryGrid fadeSlideIn: 260ms ease
  - MobileFloatingBottomBar: 300ms cubic-bezier(0.4, 0, 0.2, 1)
  - Body transition: 200ms ease
- Timing khác nhau KHÔNG sai — mỗi interaction có nhịp điệu riêng
- Tuy nhiên, nên chuẩn hóa thành **class-based timing tokens** cho dễ maintain

**Token timing mới (THÊM, không thay đổi):**
```css
--gallery-duration-instant:  80ms    /* Focus ring, border color (GitHub-inspired) */
--gallery-duration-fast:    120ms   /* Hover state, icon color (Linear-inspired) */
--gallery-duration-normal:  200ms   /* Default interaction */
--gallery-duration-slow:    300ms   /* Enter/leave, spring animation */
--gallery-duration-loading: 1500ms  /* Shimmer, skeleton */
--gallery-easing-default:   cubic-bezier(0.4, 0, 0.2, 1)  /* Standard ease */
--gallery-easing-spring:    cubic-bezier(0.34, 1.56, 0.64, 1) /* Spring-like */
```

> KHÔNG thay đổi bất kỳ `transition: ...` hoặc `animation: ...` timing hiện tại.
> Token mới CHỈ dùng cho components/code mới.

---

## TỔNG KẾT: Danh sách "Sẽ áp dụng" và "Sẽ không áp dụng"

### ✅ SẼ ÁP DỤNG (có điều chỉnh)

| # | Best Practice | Cách áp dụng | Giá trị cụ thể |
|---|---|---|---|
| 1 | **Token naming convention** | `--gallery-{category}-{group?}-{modifier}` — Primer-inspired | `--gallery-surface-default`, `--gallery-text-primary` |
| 2 | **Surface layers (5 levels)** | Thêm token mới: dim, low, default, high, elevated | `--gallery-surface-dim: #080808`, `--gallery-surface-low: #141414`, `--gallery-surface-default: #11100f`, `--gallery-surface-high: #1c1c1c`, `--gallery-surface-elevated: #242424` |
| 3 | **Typography scale** | Tạo font-size tokens | `--gallery-font-size-xs: 0.625rem`, `...sm: 0.75rem`, `...base: 1rem`, `...lg: 1.25rem`, `...xl: 1.5rem`, `...2xl: 2rem` |
| 4 | **Border radius tokens** | Tạo radius tokens từ sm→full | `--gallery-radius-sm: 4px`, `...md: 8px`, `...lg: 12px`, `...xl: 16px`, `...full: 9999px` |
| 5 | **Elevation shadow tokens** | Tạo shadow tokens (giá trị giống tokens.css hiện tại) | `--gallery-shadow-sm`, `--gallery-shadow-md`, `--gallery-shadow-lg`, `--gallery-shadow-xl` |
| 6 | **Lightbox token hóa** | Token riêng `--gallery-lightbox-*` | Giữ nguyên giá trị hardcode hiện tại |
| 7 | **Micro-interaction timing tokens** | Class-based timing tokens | `--gallery-duration-fast: 120ms`, `...normal: 200ms`, `...slow: 300ms` |
| 8 | **Interactive accent** | Thêm indigo accent cho interactive elements | `--gallery-accent-interactive: #6366f1` (light) / `#818cf8` (dark) |
| 9 | **Border + surface differentiation** | Giữ kết hợp cả hai (current approach) | Surface diff primary, border subtle secondary |

### ❌ SẼ KHÔNG ÁP DỤNG

| # | Best Practice | Lý do từ chối |
|---|---|---|
| 1 | **MD3 6-level token naming** | Quá nặng, overkill cho gallery app. Primer 3-level là đủ. |
| 2 | **Pure black background (#000000)** | #080808 (current) là near-black tốt cho mắt, pure black gây ghosting trên OLED |
| 3 | **MD3 6 surface levels** | 5 levels là đủ. Gallery không cần `container-lowest` và `container-low` riêng biệt. |
| 4 | **Blue accent color trend** | Pastel Dreamscape (warm gold/orange) là brand identity — không đổi |
| 5 | **14px base typography** | 16px phù hợp hơn cho gallery — đọc metadata dễ hơn |
| 6 | **No-shadow card design (Reddit/Facebook)** | Gallery cần shadow để phân biệt card trong grid ảnh |
| 7 | **Pure border-based separation (Reddit/GitHub)** | Surface differentiation là primary, border là secondary |
| 8 | **Bottom tab bar docked (Instagram/Twitter)** | Floating bottom bar (current) đẹp hơn, approved rồi |
| 9 | **300ms spring cho mọi animation** | Timing hiện tại (120ms-300ms) đã tốt, mỗi interaction có nhịp riêng |
| 10 | **Thay đổi animation/keyframes hiện tại** | Adoption strategy đã xác nhận GIỮ NGUYÊN 100% animations |

### ⚠️ ĐÃ CÓ SẴN — chỉ cần tạo token ánh xạ

| # | Item | Giá trị hiện tại | Token mới |
|---|---|---|---|
| 1 | Card radius 12px | PhotoCard: 12px, AlbumCard: 12px | `--gallery-radius-lg: 12px` |
| 2 | Card shadow multi-layer | tokens.css: 2-layer MD3 style | `--gallery-shadow-card` |
| 3 | Lightbox luôn dark | Hardcode rgba(#000, 0.95) | `--gallery-lightbox-overlay` |
| 4 | Pastel Dreamscape palette | `#f5eee6`, `#d6a15d`, `#ff6b35` | `--gallery-bg-canvas`, `--gallery-accent-brand` |

---

## Kết luận

Gallery app hiện tại ĐÃ ở trạng thái tốt — nhiều best practice đã được áp dụng implicit (12px radius, MD3 multi-layer shadow, surface differentiation, dark lightbox). Công việc chính là:

1. **THÊM token schema** (`--gallery-*`) để chuẩn hóa naming
2. **THÊM surface level tokens** (từ 2 lên 5 levels)
3. **Token hóa lightbox** (giữ giá trị)
4. **THÊM timing/typography/radius/elevation tokens** cho future use
5. **KHÔNG thay đổi** bất kỳ giá trị hiện tại, animation, hoặc brand identity
