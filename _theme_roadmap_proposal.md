# 🎨 Theme Roadmap Proposal — Gallery Vue App

**Date:** 2026-05-28  
**Focus:** Root cause của "càng fix càng lỗi" + Đề xuất hướng đi mới

---

## 🔬 1. ROOT CAUSE ANALYSIS

### 1.1 Không có Design System — Chỉ có 'Style Patch Collection'

Sau khi phân tích toàn bộ codebase (24 Vue components + 6 SCSS/CSS files), phát hiện:

| Metric | Value |
|--------|-------|
| Tổng số hardcoded hex colors trong `*.vue` + `*.scss` | **223** |
| Số CSS variables được định nghĩa | ~18 (`--bg-color`, `--text-color`, etc.) |
| Số lần dùng CSS variable đúng cách | ~40% |
| Số file SCSS riêng lẻ cho styles | 6 (tokens.css + main.scss + 4 lightbox SCSS + mobile-overrides) |
| Số components dùng scoped styles | 23/24 (gần như tất cả) |
| Số components có `rgba()` hardcode không fallback | 17 components |

**Vấn đề cốt lõi:** Codebase KHÔNG có design system. Nó có một collection các CSS variables rải rác, không đầy đủ, và được implement theo kiểu "chữa cháy" — mỗi lần fix là một lần thêm variable mới hoặc sửa 1-2 chỗ, nhưng không bao giờ fix toàn bộ.

### 1.2 6 Nguyên Nhân Chính "Càng Fix Càng Lỗi"

#### 🥇 **Nguyên nhân #1: CSS Variables không đầy đủ — thiếu ~15 tokens quan trọng**

Hiện tại chỉ có: `--bg-color`, `--bg-secondary`, `--text-color`, `--title-color`, `--surface-color`, `--border-color`, `--muted-text`, `--neon-color`, `--primary-color`, `--placeholder-bg`, `--folder-color`, `--album-border-color`, `--neon-border-color`.

**Thiếu những tokens này** (đang bị hardcode khắp nơi):
- `--text-inverse` (text trên nền tối/sáng) — hiện `#fff` hardcode ở 30+ chỗ
- `--text-secondary` (text phụ) — hiện `#999`/`#666` hardcode
- `--surface-hover` (hover state) — hiện rgba(255,255,255,0.05-0.08) khắp nơi
- `--surface-raised` (card/modal surface) — hiện #1a1a1a hardcode trong lightbox
- `--overlay-bg` (backdrop) — hiện rgba(0,0,0,0.4) hardcode
- `--border-subtle` — hiện rgba(255,255,255,0.1) hardcode 40+ chỗ
- `--label-color` (prompt labels green/red) — hiện #86efac/#fca5a5 hardcode
- `--icon-muted` — hiện #666/#999 hardcode
- Còn nhiều nữa...

#### 🥈 **Nguyên nhân #2: Theme colors định nghĩa ở 2 nơi + 1 nơi override = cascade hell**

Colors được khai báo ở:
1. **`main.scss`** — `:root` và `:root[data-theme="dark"]` cho colors
2. **`tokens.css`** — shadows, glows, dark mode riêng
3. **`_mobile-overrides.scss`** — override glow + shadows với `!important`
4. **Scoped styles trong từng `.vue`** — mỗi component tự định nghĩa fallback riêng

Khi fix một màu, dev phải kiểm tra 4 layers. Mỗi lần chỉ sửa 1-2 chỗ trong 1 layer — các layer khác vẫn sai → bug mới xuất hiện.

#### 🥉 **Nguyên nhân #3: Scoped CSS + Global CSS xung đột — không có boundaries rõ ràng**

- **Lightbox styles** được tách ra 4 file SCSS riêng (`_lightbox-desktop.scss`, `_lightbox-mobile.scss`, `_lightbox-tablet.scss`, `_lightbox-shared.scss`) nhưng KHÔNG được import trong component — chúng được import trong `main.scss` (global).
- Component `.vue` lại có `scoped` styles riêng cho lightbox.
- Kết quả: global styles và scoped styles cạnh tranh specificity. Một số class được định nghĩa ở cả 2 nơi với giá trị khác nhau.

Ví dụ: `.copy-btn` được định nghĩa ở cả `_lightbox-shared.scss` (global) và `_lightbox-mobile.scss` (global). Khi dev sửa 1 file, file kia vẫn cũ → lỗi.

#### #4: **Hardcoded colors rải rác — 223 hex values trong 24 files**

Phân bố chi tiết:
| File | Hardcoded colors | Mức độ |
|------|-----------------|--------|
| `main.scss` | 57 | Định nghĩa variables (OK) + animations/brand styles (cần refactor) |
| `IntroScreen.vue` | 30 | Gần như standalone — dùng màu gold `#b49650` riêng |
| `ToastItem.vue` | 21 | Toast colors riêng — không dùng theme variables |
| `_lightbox-desktop.scss` | 16 | Toàn bộ lightbox colors hardcode |
| `_lightbox-tablet.scss` | 13 | Như trên |
| `_lightbox-mobile.scss` | 11 | Như trên |
| `_lightbox-shared.scss` | 11 | Như trên |
| `AppHeader.vue` | 10 | Theme toggle gradient hardcode |
| `SidebarHeader.vue` | 10 | Fallback hardcode trong var() |
| `EmptyState.vue` | 9 | Màu accent riêng |
| Còn lại | ~35 | Rải rác |

#### #5: **Không có quy trình test khi fix theme**

Git log cho thấy pattern:
```
commit A: fix 5 mobile UIUX issues
commit B: redesign dark theme (warm Pastel Dreamscape)
commit C: Revert "hotfix: fix 5 mobile UIUX issues"
commit D: Revert "redesign dark theme"
commit E: Implement all UIUX fixes (current HEAD)
```

3 lần fix + 2 lần revert = không ai dám rollback vì sợ mất nhiều thứ. Mỗi lần fix là mò mẫm.

#### #6: **Quá nhiều màu "đặc biệt" không theo theme**

App có ít nhất 4 hệ màu riêng biệt:
1. **Theme colors** (--primary-color, --bg-color...)
2. **Lightbox "dark always" colors** (#1a1a1a, #e0e0e0...)
3. **IntroScreen gold scheme** (#b49650, #d4af37...)
4. **Toast colors** (success/error/warning/info mỗi loại 5 màu)

Lightbox luôn dark bất kể theme — điều này có chủ đích (lightbox tối để focus vào ảnh), nhưng colors bên trong lightbox không dùng CSS variables nên không responsive với theme changes. Khi dev sửa light colors, vô tình ảnh hưởng đến global lightbox styles.

---

## 🧭 2. ĐỀ XUẤT KIẾN TRÚC MỚI

### Quyết định: **REFACTOR THEME — Không viết lại từ đầu, không modular hóa nửa vời**

**Lý do chọn refactor thay vì viết lại:**
- 24 components, ~5000 lines template/script — viết lại mất 2-3 tuần, rủi ro cao
- UI logic (scroll, lightbox, gestures) đã hoạt động — chỉ theme system có vấn đề
- Refactor theme có thể làm trong 3-4 ngày với testing

**Lý do không chọn modular hóa đơn thuần:**
- Modular hóa (tách từng component style ra file riêng) chỉ giải quyết organization, không giải quyết root cause
- Vấn đề là **thiếu design tokens** và **không có single source of truth** — modular hóa không tự động fix điều này

### 2.1 Kiến trúc Theme Mới (File-based)

```
frontend/src/styles/
├── _tokens.css                  # DESIGN TOKENS — TẤT CẢ CSS variables ở 1 chỗ
│   └── :root (light defaults)
│   └── :root[data-theme="dark"] (dark overrides)
│   └── @media (max-width: 767px) (mobile overrides — KHÔNG !important)
│
├── _base.css                    # Reset, typography, accessibility
│   └── body, a, button styles
│   └── scrollbar styles
│   └── focus-visible
│   └── prefers-reduced-motion
│   └── prefers-contrast
│
├── _animations.css              # Keyframes + brand animation
│   └── iconFlicker, dark-title-shimmer, lucide-spin
│   └── brand-icon, brand-title global styles
│
├── _lightbox.css                # ALL lightbox styles — 1 file, KHÔNG global
│   └── desktop, tablet, mobile variants via @media
│   └── Dùng CSS variables từ _tokens.css
│
├── _components.css              # Component-specific global styles (nếu cần)
│   └── search-box, field-container global overrides
│
└── main.scss                    # Chỉ import — KHÔNG định nghĩa CSS ở đây
    └── @use 'tokens';
    └── @use 'base';
    └── @use 'animations';
    └── @use 'components';
```

### 2.2 Design Tokens Cần Thêm

```css
/* HIỆN TẠI: ~18 tokens */
/* CẦN THÊM: ~25 tokens */

--text-secondary: #666;        /* Thay cho #999/#666 hardcode */
--text-inverse: #fff;           /* Text trên nền dark */
--text-label: #86efac;          /* Label green (prompt positive) */
--text-label-negative: #fca5a5; /* Label red (prompt negative) */
--text-meta: #d1d5db;           /* Metadata text */
--text-icon-muted: #a09888;     /* Icon muted color */

--surface-raised: #1a1a1a;      /* Lightbox panel bg (luôn dark) */
--surface-hover: rgba(255,255,255,0.05);  /* Universal hover */
--surface-active: rgba(255,255,255,0.1);   /* Universal active */
--overlay-bg: rgba(0,0,0,0.4);  /* Backdrop universal */
--border-light: rgba(255,255,255,0.1);     /* Universal light border */
--border-subtle: rgba(255,255,255,0.05);   /* Subtle dividers */

--scrollbar-thumb: rgba(255,255,255,0.2);
--scrollbar-track: transparent;

--toast-success-bg: #;
--toast-error-bg: #;
--toast-warning-bg: #;
--toast-info-bg: #;
```

**QUAN TRỌNG:** Tất cả tokens phải có fallback hợp lý. Fallback mặc định là LIGHT MODE value (vì app khởi động ở light mode, nếu variable bị lỗi thì light fallback vẫn visible).

### 2.3 Component Style Strategy

| Loại Style | Nên dùng | Không nên dùng |
|-----------|----------|----------------|
| Layout (grid, flex, spacing) | `scoped` trong `.vue` | Global SCSS |
| Colors, typography | `var(--token)` trong scoped | Hardcode hex |
| Component-specific animations | `scoped` trong `.vue` | Global keyframes |
| Shared component states | CSS variables qua `:deep()` | Global class overrides |
| Brand/global animations | `_animations.css` | Trong component scoped |

---

## 🧩 3. MODULAR HÓA — Component Theme API

### 3.1 Component Props cho Theme (Optional Enhancement)

Cho các component có thể customize màu sắc từ parent:

```vue
<!-- PhotoCard.vue -->
<script setup lang="ts">
interface Props {
  surfaceColor?: string  // fallback: var(--surface-color)
  textColor?: string     // fallback: var(--text-color)
}
</script>
```

**Khi nào cần:** Khi component được render ở nhiều context khác nhau (lightbox vs gallery grid) và cần màu khác.

**Khi nào không cần:** Đa số components chỉ cần CSS variables — không cần props.

### 3.2 CSS Modules vs Scoped

**Giữ nguyên Scoped CSS** (Vue 3 built-in) — không chuyển sang CSS Modules:
- Scoped hoạt động tốt cho 95% cases
- CSS Modules phức tạp hơn, không tương thích với Vue SFC conventions
- Migration cost > benefit

**Cải thiện:** Dùng `:deep()` sparingly. Chỉ dùng khi thực sự cần override child component từ parent.

---

## ⚖️ 4. RỦI RO VS BENEFIT

### Option A: Viết lại theme từ đầu

| Factor | Assessment |
|--------|-----------|
| **Thời gian** | 3-5 ngày cho tokens + viết lại SCSS + test |
| **Rủi ro** | CAO — mất 331 dòng fix từ commit 3a29d04, có thể miss edge cases |
| **Benefit** | Code sạch, nhất quán, dễ maintain |
| **Kết luận** | ⛔ Không nên — quá rủi ro cho benefit không tương xứng |

### Option B: Refactor hệ thống tokens + từ từ thay thế hardcode

| Factor | Assessment |
|--------|-----------|
| **Thời gian** | 2-3 ngày cho tokens + 2-3 ngày cho từng component |
| **Rủi ro** | THẤP — mỗi bước nhỏ, dễ test, dễ revert |
| **Benefit** | Fix root cause, không mất code hiện tại |
| **Kết luận** | ✅ **Khuyến nghị** |

### Option C: Rollback về commit ổn định rồi làm lại

| Factor | Assessment |
|--------|-----------|
| **Thời gian** | 1 ngày rollback + 4-5 ngày làm lại |
| **Rủi ro** | TRUNG BÌNH — mất tính năng mới (pull-to-refresh, spring animation, haptic) |
| **Benefit** | Baseline sạch |
| **Kết luận** | ⚠️ Chỉ nếu baseline thực sự ổn định. Tag `baseline-phase3` (8b40d6b) là baseline trước UIUX fixes — có thể rollback về đó nếu cần. |

**Điểm chuẩn có thể rollback:**
| Tag | Mô tả | Trạng thái |
|-----|-------|-----------|
| `baseline-phase3` (8b40d6b) | Phase 1+2+3 full mobile UX | Đã có bottom nav, search bar, header compact |
| `baseline-pre-ux` (8f3674c) | Trước UX overhaul | Baseline an toàn |

---

## 🗺️ 5. ROADMAP ĐỀ XUẤT

### Phase 0 — Chuẩn bị (1 ngày)

1. **Tạo nhánh `refactor/theme-system`** từ HEAD
2. **Tạo test checklist** (dựa trên 18 issues UIUX đã phát hiện + 223 hardcoded colors)
3. **Setup visual regression test** — chụp screenshot desktop/mobile light/dark trước khi refactor

### Phase 1 — Design Tokens (1 ngày) 🥇 LÀM TRƯỚC

1. **Mở rộng `_tokens.css`** — thêm ~25 tokens (xem section 2.2)
2. **Đảm bảo tất cả tokens có fallback** — dùng light mode value làm default
3. **Xóa `!important` khỏi `_mobile-overrides.scss`** — thay bằng CSS specificity đúng
4. **Hợp nhất `tokens.css` vào `main.scss`** hoặc import đúng thứ tự:
   ```
   tokens.css → main.scss (:root colors) → _mobile-overrides.scss
   ```
5. **Verify:** Tất cả components hiển thị đúng (dùng fallback tokens)

### Phase 2 — Lightbox Styles (1 ngày) 🥈 LÀM THỨ 2

1. **Hợp nhất 4 file lightbox SCSS thành 1 file `_lightbox.css`**
2. **Thay thế tất cả hardcode colors** (51 chỗ) bằng CSS variables
3. **Dùng `@media (max-width: 767px)` và `@media (min-width: 768px) and (max-width: 1024px)`** thay vì file riêng
4. **Import `_lightbox.css` chỉ trong `Lightbox.vue`** (không global)
5. **Verify:** Lightbox hoạt động ở desktop/tablet/mobile cả light và dark mode

### Phase 3 — Component-by-Component (2-3 ngày)

Thứ tự ưu tiên (dựa trên số hardcode + tần suất bug):

1. **IntroScreen.vue** (30 hardcode — nhưng ít ảnh hưởng vì standalone)
2. **ToastItem.vue** (21 hardcode)
3. **AppHeader.vue** (10 hardcode — theme toggle gradient)
4. **SidebarHeader.vue** (10 hardcode — fallback values)
5. **EmptyState.vue** (9 hardcode — accent colors)
6. **GalleryGrid.vue** (6 hardcode — gradient)
7. **Các component còn lại**

Mỗi component:
1. Xác định tất cả hardcode colors
2. Map sang CSS variable (thêm variable mới nếu chưa có)
3. Test light mode + dark mode
4. Test mobile + desktop

### Phase 4 — Global Style Cleanup (0.5 ngày)

1. **Xóa `_lightbox-*.scss`** cũ (đã thay bằng `_lightbox.css`)
2. **Xóa các style không dùng** trong `main.scss`
3. **Xóa `_mobile-overrides.scss`** (đã tích hợp vào tokens)
4. **Kiểm tra không còn style global nào override component không cần thiết**

### Phase 5 — Testing & QA (1 ngày)

1. **Test tất cả 18 issues UIUX gốc** — không còn lỗi
2. **Test theme toggle** — light ↔ dark, không FOUC
3. **Test mobile** — 390px, 480px, 768px viewports
4. **Test lightbox** — desktop/tablet/mobile + all device sizes
5. **Test accessibility** — prefers-reduced-motion, prefers-contrast
6. **Test browser** — Chrome, Firefox, Safari (iOS)

---

## ✅ 6. NGUYÊN TẮC ĐỂ KHÔNG "CÀNG FIX CÀNG LỖI"

### Rule #1: **Một lần sửa = tất cả các chỗ**

Không sửa 1-2 chỗ trong 1 component. Khi sửa `--primary-color`, kiểm tra:
- `rgrep "#ff6b35\|--primary-color"` — tất cả 223 chỗ
- Nếu variable chưa có, thêm variable trước, sau đó replace tất cả cùng lúc

### Rule #2: **Test trước khi commit — 4 scenarios bắt buộc**

```
Light + Desktop  → Light + Mobile
Dark  + Desktop  → Dark  + Mobile
```

Dùng DevTools > Toggle Device Toolbar > kiểm tra cả 4 tổ hợp.

### Rule #3: **Không dùng `!important` trong theme system**

`!important` là nguyên nhân số 1 của "không biết style nào đang thắng".
Dùng specificity đúng:
- Component scoped > Global
- `:root[data-theme="dark"]` > `:root`
- `@media (max-width: 767px)` specificity > none

### Rule #4: **Commit strategy — mỗi commit sửa 1 concept**

```
❌ "fix theme colors" (sửa 10 file, 5 concept)
✅ "feat(tokens): add --text-secondary, --surface-hover, --border-light"
✅ "fix(lightbox): replace 51 hardcoded colors with CSS variables"
✅ "fix(components): replace hardcoded colors in AppHeader, IntroScreen"
```

Mỗi commit có thể REVERT độc lập mà không ảnh hưởng đến commits khác.

### Rule #5: **Dùng CSS custom property inheritance đúng cách**

```css
/* SAI — !important + duplicate declaration */
:root[data-theme="dark"] {
  --bg-color: #080808 !important;
}

/* ĐÚNG — một nguồn truth duy nhất, kế thừa tự nhiên */
:root { --bg-color: #f5eee6; }
:root[data-theme="dark"] { --bg-color: #080808; }
@media (max-width: 767px) {
  :root { --bg-color: #f0e8dd; } /* mobile light */
  :root[data-theme="dark"] { --bg-color: #0a0a0a; } /* mobile dark */
}
```

---

## 📊 TÓM TẮT QUYẾT ĐỊNH

| Câu hỏi | Trả lời |
|---------|---------|
| Viết lại theme từ đầu? | ❌ Không — quá rủi ro, không cần thiết |
| Refactor tiếp kiểu cũ? | ❌ Không — càng fix càng lỗi vì thiếu design system |
| Refactor theme system? | ✅ **CÓ** — thêm tokens → replace hardcode → cleanup |
| Rollback về baseline? | ⚠️ Dự phòng — có thể rollback về `baseline-phase3` nếu cần |
| Thời gian ước tính? | **5-7 ngày** (1 token + 1 lightbox + 2-3 components + 1 test) |
| Rủi ro? | **THẤP** — mỗi phase nhỏ, có thể test, có thể revert |

### Nên làm NGAY:
1. Tạo nhánh `refactor/theme-system`
2. Thêm 25 tokens còn thiếu vào `_tokens.css`
3. Xóa `!important` khỏi mobile overrides
4. Hợp nhất lightbox styles

### KHÔNG nên làm:
- ✗ Viết lại từ đầu
- ✗ Chuyển sang CSS Modules
- ✗ Thêm component theme props (chưa cần)
- ✗ Sửa 1-2 chỗ lẻ tẻ (càng fix càng lỗi)

---

*Generated by Hermes Agent — phân tích codebase + git history + 18 issues UIUX*
