# Theme Token System Adoption Strategy
## Giữ 100% animations/style PC khi refactor

> **Mục tiêu:** Bổ sung + chuẩn hóa token system cho gallery app, **KHÔNG THAY ĐỔI** bất kỳ style/animation hiện tại nào.
> **Nguyên tắc vàng:** Nếu token mới có giá trị khác → tạo TOKEN MỚI, giữ nguyên giá trị cũ.

---

## 1. PHÂN TÍCH: Có giữ được 100% không?

**→ CÓ.** Hoàn toàn có thể giữ 100% animations và style PC hiện tại.

Lý do: Codebase hiện tại đã được thiết kế khá tốt với:
- CSS custom properties (`--bg-color`, `--text-color`, `--neon-color`, etc.)
- Theme toggle qua `data-theme="dark"` attribute
- Scoped styles trong từng component (Vue `<style scoped>`)
- Shadows/glows đã được tách riêng vào `tokens.css`

Không có xung đột nào buộc phải thay đổi style hiện tại.

---

## 2. DANH SÁCH ĐẦY ĐỦ TẤT CẢ @keyframes TRONG CODEBASE

### 2.1. Trong `main.scss` (global animations — KHÔNG ĐỤNG VÀO)

| # | Keyframe Name | File | Line | Purpose |
|---|---|---|---|---|
| 1 | `iconFlicker` | main.scss | 45 | Brand icon neon flicker (dark mode) |
| 2 | `dark-title-shimmer` | main.scss | 90 | Gold shimmer sweep on brand title |
| 3 | `dark-title-glow` | main.scss | 95 | Pulse glow on dark mode title |
| 4 | `dark-underline-pulse` | main.scss | 110 | Underline glow pulsing |
| 5 | `lucide-spin` | main.scss | 456 | Loading spinner rotation |

### 2.2. Trong component scoped styles

| # | Keyframe Name | Component | Line | Purpose |
|---|---|---|---|---|
| 6 | `underline-grow` | AppHeader.vue | 380 | Hover underline animation |
| 7 | `subtle-float` | AppHeader.vue | 385 | Hover float animation |
| 8 | `icon-spin` | EmptyState.vue | 290 | Loading icon rotation |
| 9 | `pulse-slow` | EmptyState.vue | 438 | Background circle pulse |
| 10 | `float` | EmptyState.vue | 449 | Floating dots animation |
| 11 | `twinkle` | EmptyState.vue | 458 | Sparkle twinkle animation |
| 12 | `shimmer` | PhotoCard.vue | 311 | Shimmer loading effect |
| 13 | `shimmer` | SkeletonLoader.vue | 86 | Skeleton loading shimmer |
| 14 | `fadeIn` | SettingsModal.vue | 381 | Modal fade in |
| 15 | `slideUp` | SettingsModal.vue | 386 | Modal slide up |
| 16 | `sheetContentEnter` | _lightbox-mobile.scss | 287 | Mobile sheet content animation |
| 17 | `fadeSlideIn` | GalleryGrid.vue | 636 | Grid item enter animation |
| 18 | `rotate-gradient` | IntroScreen.vue | 200 | Gradient rotation |
| 19 | `subtle-pulse` | IntroScreen.vue | 205 | Pulse shadow effect |
| 20 | `shimmer-gold` | IntroScreen.vue | 220 | Gold shimmer on intro |

### 2.3. Transition animations (Vue built-in)

| Transition name | Component | Type |
|---|---|---|
| `fade` | Lightbox.vue (line 277) | Opacity 0.2s |
| `toast` enter/leave/move | ToastContainer.vue (lines 50-70) | Slide-in/out |
| `fade` in photo-card preview | PhotoCard.vue (line 108) | Opacity 0.2s |

---

## 3. PHÂN TÍCH CHI TIẾT TỪNG COMPONENT

### 3.1. Brand-hero (AppHeader.vue + main.scss)

**Trạng thái hiện tại:**
- **Brand-icon (light):** `color: var(--title-color)`, `border: 2px solid transparent`, no glow
- **Brand-icon (dark):** `color: #ff6b35`, `border: 0.1rem solid #fff`, glow with `--neon-border-color: #08f`
- **Brand-title (light):** `color: var(--title-color)` (navy #143d60), clean solid
- **Brand-title (dark):** Gold gradient text + multi-layer drop-shadow glow + shimmer animation
- **Brand-title::after (dark):** Gold gradient underline with pulse glow
- **Title-sparkle:** Hidden by default, reveals on hover with gold glow
- **Keyframes sử dụng:** `iconFlicker`, `dark-title-shimmer`, `dark-title-glow`, `dark-underline-pulse`, `underline-grow`, `subtle-float`

**Rủi ro khi refactor:** Trung bình. Nếu token mới có giá trị color khác (vd: `--gallery-primary` khác `#d6a15d`), có thể ảnh hưởng đến `var(--primary-color)` trong brand-icon dark mode.

**Chiến lược:**
- Tạo token mới CHO NHỮNG GIÁ TRỊ MỚI, giữ nguyên `var(--primary-color)` hiện tại
- `#d6a15d` (gold), `#ff6b35` (orange), `#08f` (cyan neon) là các giá trị hardcoded — tạo token riêng cho chúng
- KHÔNG thay đổi bất kỳ `@keyframes` nào
- KHÔNG thay đổi `.brand-title`, `.brand-icon`, `.brand-hero:hover` selectors

### 3.2. Theme-toggle (AppHeader.vue scoped)

**Trạng thái hiện tại:**
```css
.theme-toggle {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); /* Light mode gradient */
  ...
}
.theme-toggle.is-dark {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); /* Dark mode gradient */
}
.toggle-thumb {
  background: var(--surface-color); /* Light: white thumb */
}
.theme-toggle.is-dark .toggle-thumb {
  background: linear-gradient(180deg, #ffd54f 0%, #ffb300 100%); /* Dark: gold thumb */
  box-shadow: ... rgba(255, 213, 79, ...);
}
```

**Rủi ro khi refactor:** Thấp. Theme-toggle hoàn toàn độc lập, sử dụng hardcode gradient và box-shadow riêng.

**Chiến lược:**
- Giữ nguyên hoàn toàn, không thay đổi gì
- Nếu muốn tạo token cho gradient background, tạo token RIÊNG (vd: `--toggle-gradient-light`, `--toggle-gradient-dark`)
- KHÔNG map các giá trị này vào `--gallery-surface-*` tokens chung

### 3.3. Toast-container (ToastContainer.vue + ToastItem.vue)

**Trạng thái hiện tại:**
- **Animations:** `toast-enter-active` (0.3s cubic-bezier), `toast-leave-active` (0.2s)
  - Enter: `translateX(100%) scale(0.95)` → normal
  - Leave: normal → `translateX(100%) scale(0.95)`
  - Move: `transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)`
- **Colors (hardcoded):**
  - success: `#22c55e` (green)
  - error: `#ef4444` (red)
  - warning: `#f59e0b` (amber)
  - info: `#3b82f6` (blue)
- **Dark mode:** `--toast-bg: #1f2937`, `--toast-title: #f9fafb`, `--toast-message: #9ca3af`

**Rủi ro khi refactor:** Thấp. Toast đã dùng CSS vars (`--toast-accent`, `--toast-bg`, etc.) rồi.

**Chiến lược:**
- Có thể thay thế hardcode colors bằng token nhưng PHẢI GIỮ NGUYÊN giá trị hex
- `--toast-accent: #22c55e` → `--gallery-toast-success: #22c55e` (giá trị giống hệt)
- `--toast-bg: #1f2937` → `--gallery-surface-toast: #1f2937` (giá trị giống hệt)
- KHÔNG thay đổi animation timing/cubic-bezier

### 3.4. EmptyState (EmptyState.vue)

**Trạng thái hiện tại:**
- **Icon ring:** `border: 2px solid var(--accent-color)`, `box-shadow: 0 0 0 8px color-mix(...)`
- **Accent colors per type:** `#a78bfa` (purple), `#60a5fa` (blue), `#f472b6` (pink), `#f87171` (red), `#f2a007` (gold)
- **Animations:**
  - `@keyframes pulse-slow` (4s, scale 1→1.05)
  - `@keyframes float` (3-4s, translateY 0→-10px)
  - `@keyframes twinkle` (2-2.5s, opacity/scale)
  - `@keyframes icon-spin` (1.5s, rotate) — loading state only

**Rủi ro khi refactor:** Thấp. Accent colors được truyền qua prop `color` và CSS var `--accent-color`.

**Chiến lược:**
- Giữ nguyên tất cả @keyframes
- Accent colors là per-type semantic colors — có thể tạo token cho chúng (vd: `--gallery-accent-purple: #a78bfa`)
- KHÔNG thay đổi `color-mix()` expressions — browser support khác nhau

### 3.5. Lightbox (Lightbox.vue + 4 SCSS files)

**Trạng thái hiện tại:**
- **Luôn dark:** `.lightbox-overlay { background: rgba(0, 0, 0, 0.95); }`, `.lightbox-left { background: radial-gradient(circle at center, #1a1a1a 0%, #000 100%); }`
- **Nav buttons:** `background: rgba(0, 0, 0, 0.6)`, `border: 1px solid rgba(255, 255, 255, 0.3)`, `color: #f5f7fb`
  - Hover: `background: rgba(255, 255, 255, 0.16)`, `color: var(--primary-color)`
  - Desktop: hidden by default (`opacity: 0`), visible on hover
  - Tablet/mobile: always visible (`opacity: 0.8`)
- **Transitions:** `fade` (opacity 0.2s), `nav-btn` (all 0.2s)
- **Desktop panel (lightbox-desktop.scss):** Dark theme colors — `rgba(20, 20, 20, 0.8)`, `#e0e0e0`, `rgba(255, 255, 255, 0.1)` borders
- **Tablet panel:** `#1a1a1a`, `#fff`, `#86efac` (green labels)
- **Mobile panel:** `#1a1a1a`, `#fff`, `#86efac` labels

**Rủi ro khi refactor:** Rất thấp. Lightbox hoàn toàn dark, không phụ thuộc vào theme variables. Tất cả colors đều hardcoded.

**Chiến lược:**
- Giữ nguyên hoàn toàn — Lightbox KHÔNG ĐƯỢC đụng vào
- Nếu muốn tạo token cho lightbox, tạo token RIÊNG (prefix `--gallery-lightbox-*`)
- KHÔNG ánh xạ lightbox colors vào `--gallery-surface-*` tokens chung

### 3.6. AlbumCard (AlbumCard.vue)

**Trạng thái hiện tại:**
- **3D perspective:** `perspective: 1000px` (desktop only — `@media (max-width: 767px) { perspective: none }`)
- **Layer rotation:**
  - `.album-layer-back`: `rotate(-12deg) translateZ(0)`
  - `.album-layer-front`: `rotate(8deg) translateZ(20px)`
  - Hover: back → `translate(-20px, 5px) rotate(-15deg)`, front → `translate(10px, -5px) rotate(12deg) scale(1.05)`
- **Glow shadow:** Uses CSS variables from `tokens.css`: `--shadow-card`, `--shadow-dark-layer-back`, `--glow-card-hover-front`, etc.
- **Dark mode:** `color: var(--neon-color)` for album name
- **Border:** `border: 4px solid var(--album-border-color)`

**Rủi ro khi refactor:** Trung bình. AlbumCard sử dụng nhiều CSS vars đã có trong `tokens.css`. Nếu token system mới thay đổi shadow/glow vars → ảnh hưởng trực tiếp.

**Chiến lược:**
- Giữ nguyên `tokens.css` (--shadow-card, --glow-*, --shadow-dark-layer-*) — KHÔNG THAY ĐỔI
- Nếu tạo token mới cho glow/shadow, thêm SONG SONG, không xóa cái cũ
- KHÔNG thay đổi `perspective`, `rotate()`, `translateZ()`, `translate()` values

### 3.7. PhotoCard (PhotoCard.vue)

**Trạng thái hiện tại:**
- **Hover scale:** `transform: translateY(-2px) scale(1.02)` (desktop only, `@media (hover: hover)`)
- **Thumbnail zoom:** `.thumbnail-img { transform: scale(1.05); }` on hover
- **Shimmer loading:**
  - `@keyframes shimmer` (1.5s, translateX -100%→100%)
  - `.shimmer-wave` with gradient sweep
  - Light mode: `rgba(255, 255, 255, 0.5)` sweep
  - Dark mode: `rgba(255, 255, 255, 0.2)` sweep
- **Dark mode:** No shadow, `border: 1px solid rgba(255, 255, 255, 0.06)`, hover → `border-color: rgba(255, 255, 255, 0.25)`, `transform: translateY(-4px) scale(1.02)`

**Rủi ro khi refactor:** Thấp. PhotoCard self-contained, sử dụng `var(--surface-color)` và `var(--shadow-card)` từ tokens.css.

**Chiến lược:**
- Giữ nguyên tất cả @keyframes
- Có thể thay thế `var(--shadow-card)` vì giá trị giống nhau
- Giữ nguyên `scale()`, `translateY()` values
- KHÔNG đụng vào `.shimmer-placeholder`, `.shimmer-wave`

---

## 4. ADOPTION STRATEGY — Từng bước cụ thể

### Phase 1: Audit & Baseline (KHÔNG code change)

```
Step 1.1: Chụp screenshot visual regression baseline cho PC theme
  - Light mode: trang chủ, empty state, toast, lightbox, album card, photo card
  - Dark mode: giống vậy
  
Step 1.2: Tạo file _visual_regression_checklist.md với 20+ test cases
  
Step 1.3: Đánh dấu file nào AN TOÀN để refactor, file nào KHÔNG ĐỤNG VÀO
```

### Phase 2: Token Definition Only (thêm mới, không sửa cũ)

```
Step 2.1: Tạo file tokens.css mới — _tokens-new.css
  - Định nghĩa token schema: --gallery-{category}-{modifier}
  - Ví dụ:
    --gallery-surface-default: #ffffff (light) / #11100f (dark)
    --gallery-text-primary: #143d60 (light) / #eaeaea (dark)
  
Step 2.2: Đảm bảo GIÁ TRỊ GIỐNG HỆT main.scss hiện tại
  - --gallery-surface-default = current var(--surface-color)
  - --gallery-text-primary = current var(--text-color)
  - KHÔNG THAY ĐỔI value nào hết
  
Step 2.3: Tạo token CHO NHỮNG GIÁ TRỊ MỚI (nếu có)
  - Phân tích từ best practice research: thêm tokens mới như
    --gallery-elevation-card, --gallery-border-subtle, etc.
  - Các token này KHÔNG được sử dụng trong code hiện tại
```

### Phase 3: Safe Replacements (chỉ hardcode → variable, value GIỐNG NHAU)

```
Step 3.1: Thay thế hardcode colors trong main.scss :root variables
  - var(--bg-color): #f5eee6 → var(--gallery-bg-canvas, #f5eee6)
  - var(--text-color): #143d60 → var(--gallery-text-primary, #143d60)
  - Giá trị fallback giữ nguyên để đảm bảo an toàn
  
Step 3.2: Thay thế trong component scoped styles
  - AppHeader.vue: .settings-btn box-shadow rgba(214, 161, 93, 0.25)
  - ToastItem.vue: #22c55e → var(--gallery-toast-success, #22c55e)
  - EmptyState.vue: accent colors → token variables
```

### Phase 4: Files KHÔNG ĐƯỢC ĐỤNG VÀO

```
❌ main.scss LINES 42-230: ALL brand-hero styles & @keyframes
  - iconFlicker, dark-title-shimmer, dark-title-glow, dark-underline-pulse
  - .brand-icon, .brand-title, .brand-title::after, .title-sparkle
  - All html[data-theme="dark"] selectors in this section

❌ tokens.css: ALL glow/shadow variables
  - --glow-color-*, --glow-card-hover*, --shadow-dark-layer-*

❌ AppHeader.vue LINES 180-285: Theme-toggle styles
  - gradient backgrounds, thumb styles, hover effects

❌ AppHeader.vue LINES 342-447: Brand icon & title base styles

❌ EmptyState.vue LINES 438-467: All @keyframes

❌ PhotoCard.vue LINES 271-318: Shimmer styles & @keyframes

❌ ToastContainer.vue LINES 49-84: Toast enter/leave animations

❌ Lightbox.vue LINES 409-645: ALL lightbox styles (nav-btn, overlay, transitions)

❌ _lightbox-*.scss files: ALL 4 files (shared, desktop, tablet, mobile)

❌ AlbumCard.vue LINES 46-259: 3D transforms, layer positions, glow shadows

❌ _mobile-overrides.scss: ALL content
```

### Phase 5: Visual Regression Testing

```
Step 5.1: Trước mỗi commit, chạy screenshot comparison:
  - Light mode PC: brand-hero, album cards, photo cards, grid
  - Dark mode PC: brand-hero with flicker, toast, empty state, lightbox
  
Step 5.2: Checklist so sánh (phải match 100%):
  [ ] Brand-icon glow & flicker giống hệt
  [ ] Brand-title gold gradient + shimmer + glow giống hệt
  [ ] Title-sparkle hover reveal giống hệt
  [ ] Theme-toggle gradient + thumb position giống hệt
  [ ] Toast slide-in timing/curve giống hệt
  [ ] EmptyState pulse/float/twinkle timing giống hệt
  [ ] Lightbox luôn dark bất kể theme
  [ ] AlbumCard 3D layer rotation + glow giống hệt
  [ ] PhotoCard hover scale + shimmer giống hệt
  
Step 5.3: Kiểm tra @media (prefers-reduced-motion: reduce) behavior
```

### Phase 6: Commit Strategy

```
Commit 1: "chore(theme): add _tokens-new.css schema (value-identical, no-op)"
  - Chỉ tạo file mới, không import, không sử dụng

Commit 2: "refactor(theme): replace hardcode colors in main.scss :root with tokens"
  - Thay var definitions trong :root/:root[data-theme="dark"]
  - Giá trị giữ nguyên

Commit 3: "refactor(theme): add token fallbacks to component vars"
  - AppHeader, EmptyState static colors
  - KHÔNG đụng animation, brand, lightbox

Commit 4: "refactor(theme): gradual adoption in low-risk components"
  - ToastItem colors → token
  - SettingsModal, SkeletonLoader
  - Mỗi component 1 commit riêng

Commit 5+: "feat(theme): add new semantic tokens from research"
  - Chỉ THÊM, không REPLACE
  - Ví dụ: --gallery-elevation-level1, --gallery-border-default
```

---

## 5. RỦI RO & CÁCH TRÁNH

### Rủi ro 1: CSS specificity war
**Vấn đề:** Token mới có cùng tên với var cũ → thay đổi ngoài ý muốn
**Giải pháp:** Đặt tên KHÁC hoàn toàn (prefix `--gallery-*`), không trùng với `--bg-color`, `--text-color`, v.v.

### Rủi ro 2: Animation timing thay đổi
**Vấn đề:** Thay cubic-bezier hoặc duration vô tình
**Giải pháp:** NEVER touch animation properties trong phase 1-3. Animation chỉ được refactor trong phase riêng, có visual regression test.

### Rủi ro 3: Lightbox vô tình nhận theme colors
**Vấn đề:** Lightbox dùng `var(--primary-color)` cho nav-btn hover — nếu primary-color đổi, lightbox đổi theo
**Giải pháp:** Giữ nguyên giá trị hardcode trong Lightbox. Nếu muốn tạo token, tạo `--gallery-lightbox-accent` riêng.

### Rủi ro 4: Color-mix() không tương thích
**Vấn đề:** `color-mix(in srgb, ...)` dùng trong EmptyState icon-ring và body background
**Giải pháp:** KHÔNG thay đổi color-mix() calls — chúng phụ thuộc vào giá trị chính xác.

### Rủi ro 5: Fallback value khác
**Vấn đề:** `var(--primary-color, #d6a15d)` — nếu --primary-color undefined, fallback khác
**Giải pháp:** Luôn giữ fallback giống hệt giá trị hiện tại khi thay thế.

---

## 6. FILE MAPPING — Token cần tạo cho PC theme

### 6.1. Tokens bắt buộc (giá trị GIỐNG HỆT hiện tại)

```css
:root {
  /* Surface & Background */
  --gallery-surface-default: #ffffff;       /* = current --surface-color light */
  --gallery-surface-elevated: #ffffff;      /* = current --bg-secondary light */
  --gallery-bg-canvas: #f5eee6;            /* = current --bg-color light */
  --gallery-surface-card: #ffffff;         /* used by content-body */
  
  /* Text */
  --gallery-text-primary: #143d60;          /* = current --text-color */
  --gallery-text-title: #143d60;           /* = current --title-color */
  --gallery-text-muted: #4a6587;           /* = current --muted-text */
  
  /* Border */
  --gallery-border-default: rgba(0,0,0,0.12);  /* = current --border-color */
  --gallery-border-album: #ffffff;             /* = current --album-border-color */
  
  /* Accent */
  --gallery-accent-primary: #ff6b35;        /* = current --primary-color light */
  --gallery-accent-neon: #ff6b35;           /* = current --neon-color light */
  --gallery-accent-folder: #f2a007;         /* = current --folder-color */
}

:root[data-theme="dark"] {
  --gallery-surface-default: #11100f;       /* = current --surface-color dark */
  --gallery-surface-elevated: #1e1e1e;      /* = current --bg-secondary dark */
  --gallery-bg-canvas: #080808;            /* = current --bg-color dark */
  
  --gallery-text-primary: #eaeaea;          /* = current --text-color dark */
  --gallery-text-title: #d6a15d;           /* = current --title-color dark */
  --gallery-text-muted: #b3b3b3;           /* = current --muted-text dark */
  
  --gallery-accent-primary: #d6a15d;        /* = current --primary-color dark */
  --gallery-accent-neon: #d6a15d;           /* = current --neon-color dark */
}
```

### 6.2. Tokens cho brand-hero (ALWAYS hardcode value, never reference)

```css
/* DO NOT replace these — keep hardcoded for stability */
/* Brand icon dark:  color: #ff6b35; border-color: #fff; --neon-border-color: #08f; */
/* Brand title dark: gradient colors #d6a15d → #e8c07a → #ffd700 → #ffec8b → ... */
/* Title underline: gradient colors #c9a962 → #d4af37 */
```

### 6.3. Tokens cho toast colors

```css
--gallery-toast-success: #22c55e;
--gallery-toast-error: #ef4444;
--gallery-toast-warning: #f59e0b;
--gallery-toast-info: #3b82f6;
--gallery-toast-bg-dark: #1f2937;
--gallery-toast-title-dark: #f9fafb;
--gallery-toast-message-dark: #9ca3af;
```

### 6.4. Tokens cho EmptyState accent colors

```css
--gallery-accent-purple: #a78bfa;
--gallery-accent-blue: #60a5fa;
--gallery-accent-pink: #f472b6;
--gallery-accent-red: #f87171;
--gallery-accent-gold: #f2a007;
--gallery-accent-slate: #94a3b8;
```

---

## 7. SUMMARY — Kết luận

| Câu hỏi | Trả lời |
|---|---|
| Giữ được 100% animations? | ✅ **CÓ** — không cần thay đổi bất kỳ @keyframes nào |
| Giữ được 100% brand-hero style? | ✅ **CÓ** — giữ nguyên main.scss lines 42-230 |
| Giữ được 100% theme-toggle? | ✅ **CÓ** — giữ nguyên AppHeader.vue scoped |
| Giữ được 100% toast animations? | ✅ **CÓ** — giữ nguyên ToastContainer.vue transitions |
| Giữ được 100% EmptyState animations? | ✅ **CÓ** — giữ nguyên @keyframes trong EmptyState.vue |
| Giữ được 100% Lightbox dark? | ✅ **CÓ** — KHÔNG đụng Lightbox files |
| Giữ được 100% AlbumCard 3D/glow? | ✅ **CÓ** — giữ nguyên tokens.css |
| Giữ được 100% PhotoCard shimmer? | ✅ **CÓ** — giữ nguyên @keyframes shimmer |
| Rủi ro chính? | CSS specificity war, vô tình thay đổi fallback value |
| Strategy an toàn nhất? | **THÊM mới → KHÔNG thay thế.** Phase-based, commit-by-commit, visual regression sau mỗi bước. |
