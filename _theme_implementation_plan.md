# Theme Refactor Implementation Plan — Facebook 3-Level Warm No-Shadow

> **Repository:** `/home/ubuntu/gallery-repo`  
> **Branch:** `refactor/theme-system`  
> **Design:** Facebook-inspired (3 surface levels, warm near-black, no shadow) + Reddit accent (orange) + Primer naming  
> **Base commit for this plan:** `3a29d04` (HEAD)

---

## Schema Tokens Đầy Đủ — Light & Dark Values

### 1. Surface Tokens (3 Levels + Hover)

```css
/* LIGHT */
--gallery-surface-dim:        #f5eee6   /* Page bg (cream) — GIỮ NGUYÊN so với --bg-color hiện tại */
--gallery-surface-default:    #ffffff   /* Card bg (white) — GIỮ NGUYÊN so với --surface-color hiện tại */
--gallery-surface-elevated:   #ffffff   /* Modal/dropdown */
--gallery-surface-hover:      #faf5ef   /* Hover state */

/* DARK — warm near-black (Facebook-inspired) */
--gallery-surface-dim:        #0f0f0f   /* Page bg — warm near-black (thay #080808) */
--gallery-surface-default:    #1a1918   /* Card/surface chính — warm (thay #11100f) */
--gallery-surface-elevated:   #242321   /* Modal/dropdown — warm elevated (thay #1e1e1e) */
--gallery-surface-hover:      #2a2826   /* Hover state — warm (replaces --bg-secondary) */
```

### 2. Text Tokens

```css
/* LIGHT */
--gallery-text-primary:       #143d60   /* Navy đậm — GIỮ NGUYÊN (--text-color) */
--gallery-text-secondary:     #4a6587   /* Muted — GIỮ NGUYÊN (--muted-text) */
--gallery-text-tertiary:      #8ba0b8   /* Thấp hơn secondary */
--gallery-text-disabled:      #bcc8d6   /* Disabled */
--gallery-text-inverse:       #ffffff   /* Text trên nền tối */
--gallery-text-placeholder:   #8ba0b8   /* Placeholder (thay rgba(0,0,0,0.06)) */

/* DARK — Facebook-inspired warm */
--gallery-text-primary:       #e4e6eb   /* Chính (thay #eaeaea) */
--gallery-text-secondary:     #b0b3b8   /* Phụ (thay #b3b3b3) */
--gallery-text-tertiary:      #7a7f85   /* Muted thấp */
--gallery-text-disabled:      #505459   /* Disabled */
--gallery-text-inverse:       #1a1918   /* Text trên nền sáng (dùng surface-default) */
--gallery-text-placeholder:   #5c6065   /* Placeholder (thay rgba(255,255,255,0.06)) */
```

### 3. Accent Tokens (Reddit-inspired ORANGE — brand = primary)

```css
/* LIGHT */
--gallery-accent-default:     #ff6b35   /* Brand/primary chính — GIỮ NGUYÊN (--primary-color) */
--gallery-accent-hover:       #e85a26   /* Hover */
--gallery-accent-muted:       #fff0ea   /* BG accent nhẹ */
--gallery-accent-text:        #d45420   /* Text accent */
--gallery-accent-border:      #ff8f66   /* Border accent */

/* DARK — warm gold (thay #d6a15d) */
--gallery-accent-default:     #d6a15d   /* Brand/primary dark — GIỮ NGUYÊN (--primary-color dark) */
--gallery-accent-hover:       #e0b070   /* Hover sáng hơn */
--gallery-accent-muted:       #2a2218   /* BG accent nhẹ */
--gallery-accent-text:        #e8c07a   /* Text accent */
--gallery-accent-border:      #c49040   /* Border accent */
```

### 4. Border Tokens

```css
/* LIGHT — subtle, gần như không thấy (Facebook-inspired) */
--gallery-border-default:     #e5ddd4   /* Default border (thay rgba(0,0,0,0.12)) — warm cream */
--gallery-border-subtle:      #ede7e0   /* Subtle border (chỉ cho sidebar/UI structural) */
--gallery-border-hover:       #d6cec4   /* Hover border */

/* DARK — warm subtle */
--gallery-border-default:     #2d2b28   /* Default (thay rgba(255,255,255,0.075)) */
--gallery-border-subtle:      #262422   /* Subtle */
--gallery-border-hover:       #3a3734   /* Hover */
--gallery-border-accent:      #3d3528   /* Accent border (thay #343536 Reddit-style) only for sidebar/UI */
```

### 5. Semantic Tokens

```css
/* Cả light & dark */
--gallery-success:            #22c55e   /* Giữ nguyên */
--gallery-success-bg:         rgba(34, 197, 94, 0.1)
--gallery-warning:            #f59e0b   /* Giữ nguyên */
--gallery-warning-bg:         rgba(245, 158, 11, 0.1)
--gallery-error:              #ef4444   /* Giữ nguyên */
--gallery-error-bg:           rgba(239, 68, 68, 0.1)
--gallery-info:               #3b82f6   /* Giữ nguyên */
--gallery-info-bg:            rgba(59, 130, 246, 0.1)
```

### 6. Radius Tokens (giữ nguyên giá trị — MD3)

```css
--gallery-radius-sm:          4px      /* Tags, badges */
--gallery-radius-md:          8px      /* Buttons, option items */
--gallery-radius-lg:          12px     /* Cards, thumbnails */
--gallery-radius-xl:          16px     /* Modal */
--gallery-radius-full:        9999px   /* Pill, avatar */
```

### 7. Shadow/Elevation Tokens (chỉ cho modal, KHÔNG cho card)

```css
/* LIGHT */
--gallery-shadow-sm:    0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.08)
--gallery-shadow-md:    0 2px 4px rgba(0,0,0,0.05), 0 4px 8px rgba(0,0,0,0.08)
--gallery-shadow-lg:    0 4px 8px rgba(0,0,0,0.06), 0 8px 16px rgba(0,0,0,0.06)
--gallery-shadow-xl:    0 8px 16px rgba(0,0,0,0.08), 0 16px 32px rgba(0,0,0,0.06)

/* DARK */
--gallery-shadow-sm:    0 1px 2px rgba(0,0,0,0.30), 0 1px 3px rgba(0,0,0,0.15)
--gallery-shadow-md:    0 2px 4px rgba(0,0,0,0.35), 0 4px 8px rgba(0,0,0,0.15)
--gallery-shadow-lg:    0 4px 8px rgba(0,0,0,0.40), 0 8px 16px rgba(0,0,0,0.15)
--gallery-shadow-xl:    0 8px 16px rgba(0,0,0,0.45), 0 16px 32px rgba(0,0,0,0.15)
```

### 8. Lightbox Tokens (always dark — giữ nguyên hardcode) — CHỈ mapping token

```css
--gallery-lightbox-overlay:        rgba(0, 0, 0, 0.95)
--gallery-lightbox-bg:             #000
--gallery-lightbox-surface:        rgba(20, 20, 20, 0.8)
--gallery-lightbox-surface-solid:  #1a1a1a
--gallery-lightbox-text:           #e0e0e0
--gallery-lightbox-text-primary:   #fff
--gallery-lightbox-text-secondary: #999
--gallery-lightbox-text-muted:     #666
--gallery-lightbox-border:         rgba(255, 255, 255, 0.1)
--gallery-lightbox-prompt-label:   #86efac
--gallery-lightbox-prompt-negative:#fca5a5
--gallery-lightbox-tool-label:     #fb7185
--gallery-lightbox-code-text:      #d1d5db
```

### 9. Timing Tokens

```css
--gallery-timing-fast:    80ms
--gallery-timing-normal:  200ms
--gallery-timing-slow:    400ms
```

### 10. Typography Tokens (giữ nguyên — chỉ mapping)

```css
--gallery-font-family:    "InterVariable", "Segoe UI", "SF Pro Display", system-ui, -apple-system, sans-serif
--gallery-font-mono:      "JetBrains Mono", monospace
--gallery-font-size-xs:   0.625rem   /* 10px */
--gallery-font-size-sm:   0.75rem    /* 12px */
--gallery-font-size-base: 1rem       /* 16px */
--gallery-font-size-lg:   1.25rem    /* 20px */
--gallery-font-size-xl:   1.5rem     /* 24px */
--gallery-font-size-2xl:  2rem       /* 32px */
--gallery-font-size-3xl:  2.5rem     /* 40px */
--gallery-line-height:    1.5
--gallery-line-height-sm: 1.25
--gallery-font-weight-normal: 400
--gallery-font-weight-medium: 500
--gallery-font-weight-bold:   600
```

### 11. Theme-Toggle Tokens (giữ nguyên gradient — chỉ mapping)

```css
--gallery-toggle-gradient-light:   linear-gradient(135deg, #667eea 0%, #764ba2 100%)
--gallery-toggle-gradient-dark:    linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)
--gallery-toggle-thumb-bg-light:   var(--gallery-surface-default)
--gallery-toggle-thumb-bg-dark:    linear-gradient(180deg, #ffd54f 0%, #ffb300 100%)
```

---

## BLACKLIST — KHÔNG được đụng

Các file và styles sau được giữ NGUYÊN 100%:

### Files
| File | Lý do |
|------|-------|
| `App.vue` | Logic theme toggle, not styling. Chỉ giữ. |
| `AppHeader.vue` (brand-hero section) | Brand-hero iconFlicker, dark-title-shimmer, brand-icon, brand-title styles. KHÔNG THAY ĐỔI. |
| `IntroScreen.vue` | Self-contained intro page, không liên quan theme. |
| `GlowContainer.vue` | Glow/bleed logic giữ nguyên cho AlbumCard desktop 3D. |
| `AlbumScroller.vue` | Glow bleed container. |
| `AlbumCard.vue` (3D styles) | Perspective, layer rotation, glow hover — giữ nguyên cho desktop. |
| `_mobile-overrides.scss` | Chỉ disable glow/shadow cho mobile. Giữ nguyên. |

### Animations & Effects (@keyframes)
- `iconFlicker` (main.scss)
- `dark-title-shimmer` (main.scss)
- `dark-title-glow` (main.scss)
- `dark-underline-pulse` (main.scss)
- `shimmer` (PhotoCard.vue, SkeletonLoader.vue)
- `lucide-spin` (main.scss)
- `fadeIn`, `slideUp`, `fadeSlideIn`, `dropdown-*` (GalleryGrid)
- `pulse-slow`, `float`, `twinkle`, `icon-spin` (EmptyState.vue)
- `sheetContentEnter` (LightboxMobileSheet)
- Tất cả animation trong `Lightbox.vue` (swipe, transition)

### Theme-toggle button
- Gradient: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` và `linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)` — GIỮ NGUYÊN.
- Thumb, track, icons, hover shadows — KHÔNG ĐỤNG.

### Lightbox — always-dark styles
- Tất cả hardcode `#fff`, `rgba(255,255,255,...)`, `#1a1a1a`, `rgba(0,0,0,0.95)` trong `Lightbox.vue`, `_lightbox-*.scss` — CHỈ thêm token alias, KHÔNG thay đổi giá trị.

### EmptyState
- Animations (pulse, float, twinkle) — giữ nguyên.
- `--accent-color` via style binding — giữ nguyên (mỗi type có màu riêng).

---

## Phase 0: Chuẩn Bị (0.5 ngày)

### Steps
1. Kiểm tra git status sạch, stash nếu cần
2. Tạo branch `refactor/theme-system` từ HEAD
3. Setup visual test checklist (xem Phase 4)

### Git
```bash
git checkout -b refactor/theme-system
```

### Visual Test Checklist (dùng cho Phase 4)
- [ ] Light mode desktop: page bg (cream), card bg (white), no shadow
- [ ] Dark mode desktop: warm #0f0f0f bg, warm #1a1918 card
- [ ] Light mode mobile: bottom nav bar, sidebar
- [ ] Dark mode mobile: bottom nav bar, overlay, sheet
- [ ] Toast colors (success/error/warning/info) — giống hệt
- [ ] EmptyState colors + animations — giống hệt
- [ ] Brand-hero (light: no glow, dark: shimmer+glow) — giống hệt
- [ ] Theme-toggle gradient — giống hệt
- [ ] AlbumCard desktop hover (3D, glow) — giống hệt
- [ ] PhotoCard hover (scale, border) — không còn shadow
- [ ] SkeletonLoader shimmer — giống hệt
- [ ] Lightbox — always dark, giống hệt
- [ ] Focus ring — vẫn hoạt động

---

## Phase 1: Token System (1 ngày) — `_tokens.css`

### File mới: `frontend/src/styles/_tokens.css`

TẠO MỚI — file CSS thuần (không SCSS) để đảm bảo không cần build chain.

### Nội dung file

```css
/* ==========================================================================
   Gallery Design Tokens — v2 (Facebook-inspired warm, no-shadow)
   Naming: Primer-inspired --gallery-{category}-{group?}-{modifier}
   ========================================================================== */

:root {
  /* ── Surface (3 levels, warm, no shadow) ── */
  --gallery-surface-dim:        #f5eee6;
  --gallery-surface-default:    #ffffff;
  --gallery-surface-elevated:   #ffffff;
  --gallery-surface-hover:      #faf5ef;

  /* ── Text ── */
  --gallery-text-primary:       #143d60;
  --gallery-text-secondary:     #4a6587;
  --gallery-text-tertiary:      #8ba0b8;
  --gallery-text-disabled:      #bcc8d6;
  --gallery-text-inverse:       #ffffff;
  --gallery-text-placeholder:   #8ba0b8;

  /* ── Accent (orange — Reddit-inspired, brand = primary) ── */
  --gallery-accent-default:     #ff6b35;
  --gallery-accent-hover:       #e85a26;
  --gallery-accent-muted:       #fff0ea;
  --gallery-accent-text:        #d45420;
  --gallery-accent-border:      #ff8f66;

  /* ── Border ── */
  --gallery-border-default:     #e5ddd4;
  --gallery-border-subtle:      #ede7e0;
  --gallery-border-hover:       #d6cec4;
  --gallery-border-accent:      #ede7e0;

  /* ── Semantic ── */
  --gallery-success:            #22c55e;
  --gallery-success-bg:         rgba(34, 197, 94, 0.1);
  --gallery-warning:            #f59e0b;
  --gallery-warning-bg:         rgba(245, 158, 11, 0.1);
  --gallery-error:              #ef4444;
  --gallery-error-bg:           rgba(239, 68, 68, 0.1);
  --gallery-info:               #3b82f6;
  --gallery-info-bg:            rgba(59, 130, 246, 0.1);

  /* ── Radius ── */
  --gallery-radius-sm:          4px;
  --gallery-radius-md:          8px;
  --gallery-radius-lg:          12px;
  --gallery-radius-xl:          16px;
  --gallery-radius-full:        9999px;

  /* ── Shadow (modal only) ── */
  --gallery-shadow-sm:  0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.08);
  --gallery-shadow-md:  0 2px 4px rgba(0,0,0,0.05), 0 4px 8px rgba(0,0,0,0.08);
  --gallery-shadow-lg:  0 4px 8px rgba(0,0,0,0.06), 0 8px 16px rgba(0,0,0,0.06);
  --gallery-shadow-xl:  0 8px 16px rgba(0,0,0,0.08), 0 16px 32px rgba(0,0,0,0.06);

  /* ── Lightbox (always dark — giá trị giữ nguyên) ── */
  --gallery-lightbox-overlay:         rgba(0, 0, 0, 0.95);
  --gallery-lightbox-bg:              #000;
  --gallery-lightbox-surface:         rgba(20, 20, 20, 0.8);
  --gallery-lightbox-surface-solid:   #1a1a1a;
  --gallery-lightbox-text:            #e0e0e0;
  --gallery-lightbox-text-primary:    #fff;
  --gallery-lightbox-text-secondary:  #999;
  --gallery-lightbox-text-muted:      #666;
  --gallery-lightbox-border:          rgba(255, 255, 255, 0.1);
  --gallery-lightbox-prompt-label:    #86efac;
  --gallery-lightbox-prompt-negative: #fca5a5;
  --gallery-lightbox-tool-label:      #fb7185;
  --gallery-lightbox-code-text:       #d1d5db;

  /* ── Timing ── */
  --gallery-timing-fast:   80ms;
  --gallery-timing-normal: 200ms;
  --gallery-timing-slow:   400ms;

  /* ── Typography ── */
  --gallery-font-family:    "InterVariable", "Segoe UI", "SF Pro Display", system-ui, -apple-system, sans-serif;
  --gallery-font-mono:      "JetBrains Mono", monospace;
  --gallery-font-size-xs:   0.625rem;
  --gallery-font-size-sm:   0.75rem;
  --gallery-font-size-base: 1rem;
  --gallery-font-size-lg:   1.25rem;
  --gallery-font-size-xl:   1.5rem;
  --gallery-font-size-2xl:  2rem;
  --gallery-font-size-3xl:  2.5rem;
  --gallery-line-height:    1.5;
  --gallery-line-height-sm: 1.25;
  --gallery-font-weight-normal: 400;
  --gallery-font-weight-medium: 500;
  --gallery-font-weight-bold:   600;

  /* ── Theme-toggle (giữ nguyên gradient) ── */
  --gallery-toggle-gradient-light:   linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  --gallery-toggle-gradient-dark:    linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  --gallery-toggle-thumb-bg-dark:    linear-gradient(180deg, #ffd54f 0%, #ffb300 100%);
}

:root[data-theme="dark"] {
  /* ── Surface (warm near-black — Facebook-inspired) ── */
  --gallery-surface-dim:        #0f0f0f;
  --gallery-surface-default:    #1a1918;
  --gallery-surface-elevated:   #242321;
  --gallery-surface-hover:      #2a2826;

  /* ── Text ── */
  --gallery-text-primary:       #e4e6eb;
  --gallery-text-secondary:     #b0b3b8;
  --gallery-text-tertiary:      #7a7f85;
  --gallery-text-disabled:      #505459;
  --gallery-text-inverse:       #1a1918;
  --gallery-text-placeholder:   #5c6065;

  /* ── Accent (warm gold) ── */
  --gallery-accent-default:     #d6a15d;
  --gallery-accent-hover:       #e0b070;
  --gallery-accent-muted:       #2a2218;
  --gallery-accent-text:        #e8c07a;
  --gallery-accent-border:      #c49040;

  /* ── Border (warm subtle) ── */
  --gallery-border-default:     #2d2b28;
  --gallery-border-subtle:      #262422;
  --gallery-border-hover:       #3a3734;
  --gallery-border-accent:      #3d3528;

  /* ── Shadow (dark mode) ── */
  --gallery-shadow-sm:  0 1px 2px rgba(0,0,0,0.30), 0 1px 3px rgba(0,0,0,0.15);
  --gallery-shadow-md:  0 2px 4px rgba(0,0,0,0.35), 0 4px 8px rgba(0,0,0,0.15);
  --gallery-shadow-lg:  0 4px 8px rgba(0,0,0,0.40), 0 8px 16px rgba(0,0,0,0.15);
  --gallery-shadow-xl:  0 8px 16px rgba(0,0,0,0.45), 0 16px 32px rgba(0,0,0,0.15);

  /* Lightbox, semantic, radius, typography, timing — giữ nguyên từ :root */
  /* Theme-toggle giữ nguyên gradient */
}
```

### Import vào `index.html` hoặc `main.ts`
Thêm `<link rel="stylesheet" href="./styles/_tokens.css" />` vào `index.html` trước `main.scss` import.

### Giải pháp thay thế nếu không muốn sửa index.html
Thêm `@import './styles/_tokens.css';` ở đầu `main.scss`.

### Commit
```
git add frontend/src/styles/_tokens.css
git commit -m "feat(theme): add token system v2 — Facebook warm 3-level + Primer naming"
```

---

## Phase 2: Replace Hardcode Colors (2-3 ngày)

Chiến lược từng bước: THÊM token mapping vào file, KHÔNG xóa CSS variables cũ.

### Step 1 — main.scss (:root mapping) [~30 phút]

Trong `main.scss`, **thêm** mapping tokens vào `:root` block:

```css
:root {
  /* Existing CSS variables — GIỮ NGUYÊN */
  --bg-color: #f5eee6;
  --bg-secondary: #ffffff;
  --text-color: #143d60;
  --title-color: #143d60;
  --surface-color: #ffffff;
  --album-border-color: #ffffff;
  --border-color: rgba(0, 0, 0, 0.12);
  --muted-text: #4a6587;
  --neon-color: #ff6b35;
  --primary-color: #ff6b35;
  --placeholder-bg: rgba(0,0,0,0.06);
  --folder-color: #f2a007;
  
  /* NEW: Token mapping — thêm vào cuối */
  --gallery-surface-dim:        #f5eee6;
  --gallery-surface-default:    #ffffff;
  /* ... rest of tokens from _tokens.css ... */
}
```

**Lưu ý:** Ở Phase 2 này, `_tokens.css` đã tồn tại với giá trị. Trong main.scss chúng ta CHỈ cần đảm bảo mapping giữa biến cũ và token mới không xung đột. Có 2 option:

**Option A (RECOMMENDED):** Import `_tokens.css` ở đầu `main.scss` — giữ `:root` definitions hiện tại. Token mới nằm trong file riêng.

**Option B:** Merge token definitions vào `main.scss` `:root`. Dùng Option A.

### Step 2 — ToastItem.vue [~1 giờ]

**File:** `frontend/src/components/ToastItem.vue`

**Thay đổi:**

| Dòng | Old | New |
|------|-----|-----|
| 149 | `background: var(--toast-bg, #ffffff);` | `background: var(--toast-bg, var(--gallery-surface-default));` |
| 162 | `--toast-accent: #22c55e;` | `--toast-accent: var(--gallery-success);` |
| 163 | `--toast-icon-color: #22c55e;` | `--toast-icon-color: var(--gallery-success);` |
| 164 | `--toast-icon-bg: rgba(34, 197, 94, 0.1);` | `--toast-icon-bg: var(--gallery-success-bg);` |
| 168 | `--toast-accent: #ef4444;` | `--toast-accent: var(--gallery-error);` |
| 169 | `--toast-icon-color: #ef4444;` | `--toast-icon-color: var(--gallery-error);` |
| 170 | `--toast-icon-bg: rgba(239, 68, 68, 0.1);` | `--toast-icon-bg: var(--gallery-error-bg);` |
| 174 | `--toast-accent: #f59e0b;` | `--toast-accent: var(--gallery-warning);` |
| 175 | `--toast-icon-color: #f59e0b;` | `--toast-icon-color: var(--gallery-warning);` |
| 176 | `--toast-icon-bg: rgba(245, 158, 11, 0.1);` | `--toast-icon-bg: var(--gallery-warning-bg);` |
| 181 | `--toast-accent: #3b82f6;` | `--toast-accent: var(--gallery-info);` |
| 182 | `--toast-icon-color: #3b82f6;` | `--toast-icon-color: var(--gallery-info);` |
| 183 | `--toast-icon-bg: rgba(59, 130, 246, 0.1);` | `--toast-icon-bg: var(--gallery-info-bg);` |
| 208 | `color: var(--toast-title, #1f2937);` | `color: var(--toast-title, var(--gallery-text-primary));` |
| 214 | `color: var(--toast-message, #6b7280);` | `color: var(--toast-message, var(--gallery-text-secondary));` |
| 228 | `color: #8b5cf6;` | `color: var(--gallery-accent-default);` |
| 229 | `background: rgba(139, 92, 246, 0.12);` | `background: var(--gallery-accent-muted);` |
| 233 | `color: #f59e0b;` | `color: var(--gallery-warning);` |
| 234 | `background: rgba(245, 158, 11, 0.12);` | `background: var(--gallery-warning-bg);` |
| 238 | `color: #a78bfa;` | `color: var(--gallery-accent-default);` |
| 239 | `background: rgba(167, 139, 250, 0.2);` | `background: var(--gallery-accent-muted);` |
| 243 | `color: #fbbf24;` | `color: var(--gallery-warning);` |
| 244 | `background: rgba(251, 191, 36, 0.2);` | `background: var(--gallery-warning-bg);` |
| 281 | `color: var(--toast-dismiss, #9ca3af);` | `color: var(--toast-dismiss, var(--gallery-text-tertiary));` |
| 292 | `color: var(--toast-title, #1f2937);` | `color: var(--toast-title, var(--gallery-text-primary));` |
| 318 | `--toast-bg: #1f2937;` | `--toast-bg: var(--gallery-surface-elevated);` |
| 319 | `--toast-title: #f9fafb;` | `--toast-title: var(--gallery-text-primary);` |
| 320 | `--toast-message: #9ca3af;` | `--toast-message: var(--gallery-text-secondary);` |
| 321 | `--toast-dismiss: #6b7280;` | `--toast-dismiss: var(--gallery-text-tertiary);` |

**Giữ nguyên:** `box-shadow` của toast (là shadow thực cho toast notification, không phải card shadow).

### Commit
```
git add frontend/src/components/ToastItem.vue
git commit -m "refactor(theme): replace ToastItem hardcode with gallery tokens"
```

### Step 3 — EmptyState.vue [~30 phút]

**File:** `frontend/src/components/EmptyState.vue`

**Thay đổi:**

| Dòng | Old | New |
|------|-----|-----|
| 49 | `color: '#a78bfa',` | `color: '#ff6b35',` (ĐỔI sang orange accent cho empty-folder) |
| 56 | `color: '#60a5fa',` | `color: '#ff6b35',` (no-results → orange) |
| 63 | `color: '#f472b6',` | `color: '#ff6b35',` (no-images → orange) |
| 70 | `color: '#f87171',` | Giữ nguyên (error là semantic) |
| 77 | `color: '#f2a007',` | `color: '#ff6b35',` (no-path → orange) |
| 84 | `color: '#a78bfa',` | Giữ nguyên (loading) |
| 240 | `background: rgba(255,255,255,0.1);` | `background: color-mix(in srgb, var(--accent-color) 10%, transparent);` |
| 243 | `border: 2px solid var(--accent-color);` | Giữ nguyên |
| 246 | `0 0 0 8px color-mix(in srgb, var(--accent-color) 15%, transparent);` | Giữ nguyên |
| 402 | `background: var(--primary-color);` | `background: var(--gallery-accent-default);` |
| 403 | `color: #fff;` | `color: var(--gallery-text-inverse);` |
| 434 | `color: #fff;` | `color: var(--gallery-text-inverse);` |

**Giữ nguyên 100%:** Animations (pulse-slow, float, twinkle, icon-spin).

### Commit
```
git add frontend/src/components/EmptyState.vue
git commit -m "refactor(theme): replace EmptyState hardcode with gallery accent tokens"
```

### Step 4 — SettingsModal.vue [~30 phút]

**File:** `frontend/src/components/SettingsModal.vue`

**Thay đổi:**

| Dòng | Old | New |
|------|-----|-----|
| 173 | `background: rgba(0, 0, 0, 0.4);` | `background: rgba(0, 0, 0, 0.4);` (giữ nguyên — backdrop) |
| 183 | `background: var(--surface-color);` | `background: var(--gallery-surface-elevated);` |
| 187 | `0 20px 50px rgba(0, 0, 0, 0.2);` | `var(--gallery-shadow-xl)` |
| 189 | `border: 1px solid rgba(0, 0, 0, 0.08);` | `border: 1px solid var(--gallery-border-subtle);` |
| 194 | `border: 1px solid rgba(255, 255, 255, 0.1);` | `border: 1px solid var(--gallery-border-default);` |
| 195 | `background: var(--surface-color);` | `background: var(--gallery-surface-elevated);` |
| 200 | `border-bottom: 1px solid rgba(0, 0, 0, 0.06);` | `border-bottom: 1px solid var(--gallery-border-subtle);` |
| 207 | `border-bottom-color: rgba(255, 255, 255, 0.06);` | `border-bottom-color: var(--gallery-border-subtle);` |
| 216 | `color: var(--title-color);` | `color: var(--gallery-text-primary);` |
| 220 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 229 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 237 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 248 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 267 | `background: rgba(0, 0, 0, 0.02);` | `background: color-mix(in srgb, var(--gallery-surface-dim) 98%, var(--gallery-surface-default));` |
| 271 | `background: rgba(255, 255, 255, 0.03);` | `background: color-mix(in srgb, var(--gallery-surface-default) 50%, var(--gallery-surface-elevated));` |
| 275 | `background: rgba(0, 0, 0, 0.04);` | `background: var(--gallery-surface-hover);` |
| 279 | `background: rgba(255, 255, 255, 0.06);` | `background: var(--gallery-surface-hover);` |
| 283 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 284 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 285 | `0 2px 8px rgba(0, 0, 0, 0.05);` | `var(--gallery-shadow-sm)` |
| 290 | `background: var(--gallery-accent-muted);` | Giữ (đã dùng token mới) |
| 291 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 302 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 306 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 312 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 318 | `border-top: 1px solid rgba(0, 0, 0, 0.06);` | `border-top: 1px solid var(--gallery-border-subtle);` |
| 323 | `border-top-color: rgba(255, 255, 255, 0.06);` | `border-top-color: var(--gallery-border-subtle);` |
| 336 | `border: 1px solid rgba(0, 0, 0, 0.1);` | `border: 1px solid var(--gallery-border-default);` |
| 337 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 338 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 347 | `border-color: rgba(255, 255, 255, 0.2);` | `border-color: var(--gallery-border-default);` |
| 353 | `background-color: var(--bg-color);` | `background-color: var(--gallery-surface-dim);` |
| 354 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 358 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 365 | `border: 1px solid var(--primary-color);` | `border: 1px solid var(--gallery-accent-default);` |
| 366 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 377 | `background: var(--primary-color);` | `background: var(--gallery-accent-default);` |
| 378 | `color: #fff;` | `color: var(--gallery-text-inverse);` |

**Rủi ro:** Modal shadow dùng `--gallery-shadow-xl` — cần đảm bảo không bị nhầm với card shadow.

### Commit
```
git add frontend/src/components/SettingsModal.vue
git commit -m "refactor(theme): replace SettingsModal hardcode with gallery tokens"
```

### Step 5 — SkeletonLoader.vue [~20 phút]

**File:** `frontend/src/components/SkeletonLoader.vue`

| Dòng | Old | New |
|------|-----|-----|
| 46 | `background: linear-gradient(90deg, rgba(0, 0, 0, 0.05), rgba(0, 0, 0, 0.035), rgba(0, 0, 0, 0.05));` | `background: linear-gradient(90deg, color-mix(in srgb, var(--gallery-surface-default) 95%, var(--gallery-surface-dim)), color-mix(in srgb, var(--gallery-surface-default) 97%, var(--gallery-surface-dim)), color-mix(in srgb, var(--gallery-surface-default) 95%, var(--gallery-surface-dim)));` |
| 61 | Same as 46 | Same as above |
| 79 | `rgba(255, 255, 255, 0.22)` | Giữ nguyên (shimmer wave là hiệu ứng quang học, không cần token) |
| 120 | `background: linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.08));` | `background: linear-gradient(90deg, color-mix(in srgb, var(--gallery-surface-elevated) 95%, var(--gallery-surface-dim)), color-mix(in srgb, var(--gallery-surface-elevated) 97%, var(--gallery-surface-dim)), color-mix(in srgb, var(--gallery-surface-elevated) 95%, var(--gallery-surface-dim)));` |

**Giữ nguyên:** `@keyframes shimmer`, `rgba(255, 255, 255, ...)` trong `.shimmer-wave` (là highlight overlay, cần absolute white).

### Commit
```
git add frontend/src/components/SkeletonLoader.vue
git commit -m "refactor(theme): replace SkeletonLoader bg with gallery tokens"
```

### Step 6 — Lightbox components (4 files) [~1.5 giờ]

**Mục tiêu:** THÊM token alias mapping, KHÔNG thay đổi giá trị hiển thị.

**File: `Lightbox.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 431 | `background: rgba(0, 0, 0, 0.95);` | `background: var(--gallery-lightbox-overlay);` |
| 458 | `border: 1px solid rgba(255, 255, 255, 0.3);` | `border: 1px solid var(--gallery-lightbox-border);` |
| 459 | `background: rgba(0, 0, 0, 0.4);` | `background: var(--gallery-lightbox-bg);` |
| 460 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 468 | `background: rgba(255, 255, 255, 0.12);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 12%, transparent);` |
| 470 | `border-color: rgba(255, 255, 255, 0.5);` | `border-color: color-mix(in srgb, var(--gallery-lightbox-text-primary) 50%, transparent);` |
| 485 | `background: radial-gradient(circle at center, #1a1a1a 0%, #000 100%);` | `background: radial-gradient(circle at center, var(--gallery-lightbox-surface-solid) 0%, var(--gallery-lightbox-bg) 100%);` |
| 504 | `color: rgba(255, 255, 255, 0.7);` | `color: color-mix(in srgb, var(--gallery-lightbox-text-primary) 70%, transparent);` |
| 512 | `color: rgba(255, 255, 255, 0.8);` | `color: color-mix(in srgb, var(--gallery-lightbox-text-primary) 80%, transparent);` |
| 518 | `color: rgba(255, 255, 255, 0.2);` | `color: color-mix(in srgb, var(--gallery-lightbox-text-primary) 20%, transparent);` |
| 526 | `border: 1px solid rgba(255, 255, 255, 0.3);` | `border: 1px solid var(--gallery-lightbox-border);` |
| 527 | `color: #f5f7fb;` | `color: var(--gallery-lightbox-text-primary);` |
| 544 | `text-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);` | `text-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);` (giữ nguyên) |
| 577 | `border: 1px solid rgba(255, 255, 255, 0.3);` | `border: 1px solid var(--gallery-lightbox-border);` |
| 578 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |

**File: `_lightbox-desktop.scss`**

| Dòng | Old | New |
|------|-----|-----|
| 12 | `background: rgba(20, 20, 20, 0.8);` | `background: var(--gallery-lightbox-surface);` |
| 14 | `border-left: 1px solid rgba(255, 255, 255, 0.1);` | `border-left: 1px solid var(--gallery-lightbox-border);` |
| 17 | `color: #e0e0e0;` | `color: var(--gallery-lightbox-text);` |
| 24 | `border-bottom: 1px solid rgba(255, 255, 255, 0.1);` | `border-bottom: 1px solid var(--gallery-lightbox-border);` |
| 25 | `background: rgba(0, 0, 0, 0.2);` | `background: color-mix(in srgb, var(--gallery-lightbox-bg) 20%, transparent);` |
| 39 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 54 | `color: #999;` | `color: var(--gallery-lightbox-text-secondary);` |
| 60 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 81 | `color: #999;` | `color: var(--gallery-lightbox-text-secondary);` |
| 85 | `background: rgba(255, 255, 255, 0.05);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 5%, transparent);` |
| 90 | `background: #3b82f6;` | `background: var(--gallery-info);` |
| 91 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 113 | `background: rgba(255, 255, 255, 0.2);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 20%, transparent);` |
| 120 | `background: rgba(0, 0, 0, 0.3);` | `background: color-mix(in srgb, var(--gallery-lightbox-bg) 30%, transparent);` |
| 121 | `border: 1px solid rgba(74, 222, 128, 0.35);` | `border: 1px solid color-mix(in srgb, var(--gallery-lightbox-prompt-label) 35%, transparent);` |
| 125 | `border-color: rgba(239, 68, 68, 0.3);` | `border-color: color-mix(in srgb, var(--gallery-lightbox-prompt-negative) 30%, transparent);` |
| 126 | `color: #fca5a5;` | `color: var(--gallery-lightbox-prompt-negative);` |
| 135 | `background: rgba(255, 255, 255, 0.03);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 3%, transparent);` |
| 136 | `border-bottom: 1px solid rgba(255, 255, 255, 0.05);` | `border-bottom: 1px solid color-mix(in srgb, var(--gallery-lightbox-text-primary) 5%, transparent);` |
| 144 | `color: #86efac;` | `color: var(--gallery-lightbox-prompt-label);` |
| 154 | `color: #666;` | `color: var(--gallery-lightbox-text-muted);` |
| 159 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 167 | `color: #d1d5db;` | `color: var(--gallery-lightbox-code-text);` |
| 179 | `border: 1px solid rgba(255, 255, 255, 0.1);` | `border: 1px solid var(--gallery-lightbox-border);` |
| 185 | `background: rgba(255, 255, 255, 0.05);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 5%, transparent);` |
| 194 | `background: rgba(255, 255, 255, 0.08);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 8%, transparent);` |
| 200 | `color: #e5e7eb;` | `color: var(--gallery-lightbox-text-primary);` |
| 209 | `background: rgba(0, 0, 0, 0.2);` | `background: color-mix(in srgb, var(--gallery-lightbox-bg) 20%, transparent);` |
| 210 | `border-top: 1px solid rgba(255, 255, 255, 0.05);` | `border-top: 1px solid color-mix(in srgb, var(--gallery-lightbox-text-primary) 5%, transparent);` |
| 225 | `background: rgba(255, 255, 255, 0.03);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 3%, transparent);` |
| 235 | `color: #666;` | `color: var(--gallery-lightbox-text-muted);` |
| 241 | `color: #e5e7eb;` | `color: var(--gallery-lightbox-text-primary);` |
| 247 | `color: #999;` | `color: var(--gallery-lightbox-text-secondary);` |
| 248 | `background: rgba(255, 255, 255, 0.1);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 10%, transparent);` |

**File: `_lightbox-mobile.scss`**

| Dòng | Old | New |
|------|-----|-----|
| 14 | `background: rgba(0, 0, 0, 0.6);` | `background: color-mix(in srgb, var(--gallery-lightbox-bg) 60%, transparent);` |
| 15 | `border: 1px solid rgba(255, 255, 255, 0.3);` | `border: 1px solid var(--gallery-lightbox-border);` |
| 16 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 26 | `background: rgba(255, 255, 255, 0.16);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 16%, transparent);` |
| 27 | `border-color: rgba(255, 255, 255, 0.5);` | `border-color: color-mix(in srgb, var(--gallery-lightbox-text-primary) 50%, transparent);` |
| 50 | `background: rgba(0, 0, 0, 0.4);` | `background: color-mix(in srgb, var(--gallery-lightbox-bg) 40%, transparent);` |
| 55 | `background: #1a1a1a;` | `background: var(--gallery-lightbox-surface-solid);` |
| 81 | `background: rgba(255, 255, 255, 0.3);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 30%, transparent);` |
| 88 | `border-bottom: 1px solid rgba(255, 255, 255, 0.1);` | `border-bottom: 1px solid var(--gallery-lightbox-border);` |
| 97 | `color: #a09888;` | Giữ nguyên (màu đặc thù, khác lightbox text) |
| 127 | `background: rgba(255, 255, 255, 0.2);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 20%, transparent);` |
| 148 | `color: #86efac;` | `color: var(--gallery-lightbox-prompt-label);` |
| 152 | `color: #fca5a5;` | `color: var(--gallery-lightbox-prompt-negative);` |
| 160 | `color: #d1d5db;` | `color: var(--gallery-lightbox-code-text);` |
| 173 | `background: rgba(255, 255, 255, 0.07);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 7%, transparent);` |
| 174 | `border: 1px solid rgba(255, 255, 255, 0.12);` | `border: 1px solid color-mix(in srgb, var(--gallery-lightbox-text-primary) 12%, transparent);` |
| 178 | `color: #e5e7eb;` | `color: var(--gallery-lightbox-text-primary);` |
| 194 | `color: #a09888;` | Giữ nguyên |
| 215 | `color: #a09888;` | Giữ nguyên |
| 228 | `color: #fb7185;` | `color: var(--gallery-lightbox-tool-label);` |
| 235 | `color: #f43f5e;` | Giữ nguyên (màu comment đặc thù) |

**File: `_lightbox-tablet.scss`**

| Dòng | Old | New |
|------|-----|-----|
| 20 | `background: rgba(0, 0, 0, 0.4);` | `background: color-mix(in srgb, var(--gallery-lightbox-bg) 40%, transparent);` |
| 25 | `background: #1a1a1a;` | `background: var(--gallery-lightbox-surface-solid);` |
| 53 | `background: rgba(255, 255, 255, 0.35);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 35%, transparent);` |
| 59 | `border-bottom: 1px solid rgba(255, 255, 255, 0.08);` | `border-bottom: 1px solid var(--gallery-lightbox-border);` |
| 75 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 92 | `color: #999;` | `color: var(--gallery-lightbox-text-secondary);` |
| 101 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 127 | `border-right: 1px solid rgba(255, 255, 255, 0.08);` | `border-right: 1px solid var(--gallery-lightbox-border);` |
| 134 | `background: rgba(255, 255, 255, 0.2);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 20%, transparent);` |
| 153 | `color: #86efac;` | `color: var(--gallery-lightbox-prompt-label);` |
| 156 | `color: #fca5a5;` | `color: var(--gallery-lightbox-prompt-negative);` |
| 166 | `color: #d1d5db;` | `color: var(--gallery-lightbox-code-text);` |
| 186 | `color: #a09888;` | Giữ nguyên |
| 200 | `color: #fb7185;` | `color: var(--gallery-lightbox-tool-label);` |
| 203 | `color: #f43f5e;` | Giữ nguyên |
| 230 | `color: #e5e7eb;` | `color: var(--gallery-lightbox-text-primary);` |
| 235 | `color: #666;` | `color: var(--gallery-lightbox-text-muted);` |
| 244 | `color: #999;` | `color: var(--gallery-lightbox-text-secondary);` |
| 245 | `background: rgba(255, 255, 255, 0.1);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 10%, transparent);` |

**File: `_lightbox-shared.scss`**

| Dòng | Old | New |
|------|-----|-----|
| 15 | `color: #999;` | `color: var(--gallery-lightbox-text-secondary);` |
| 21 | `color: #c084fc;` | Giữ nguyên (màu pill đặc thù) |
| 36 | `background: rgba(255, 255, 255, 0.05);` | `background: color-mix(in srgb, var(--gallery-lightbox-text-primary) 5%, transparent);` |
| 37 | `border: 1px solid rgba(255, 255, 255, 0.1);` | `border: 1px solid var(--gallery-lightbox-border);` |
| 43 | `color: #999;` | `color: var(--gallery-lightbox-text-secondary);` |
| 50 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |
| 57 | `color: #666;` | `color: var(--gallery-lightbox-text-muted);` |
| 62 | `color: #fff;` | `color: var(--gallery-lightbox-text-primary);` |

### Commit
```
git add frontend/src/components/Lightbox.vue frontend/src/styles/_lightbox-*.scss
git commit -m "refactor(theme): replace lightbox hardcode with gallery-lightbox tokens"
```

### Step 7 — Các component còn lại [~2 giờ]

**File: `GalleryGrid.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 571 | `background: color-mix(in srgb, var(--primary-color) 12%, transparent);` | `background: var(--gallery-accent-muted);` |
| 572 | `border: 1px solid color-mix(in srgb, var(--primary-color) 40%, transparent);` | `border: 1px solid var(--gallery-accent-border);` |
| 573 | `color: var(--title-color);` | `color: var(--gallery-text-primary);` |
| 597 | `background: rgba(0, 0, 0, 0.05);` | `background: var(--gallery-surface-hover);` |
| 715 | `background: rgba(0, 0, 0, 0.04);` | `background: color-mix(in srgb, var(--gallery-surface-default) 96%, var(--gallery-surface-dim));` |
| 716 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 732 | `border: 1px solid rgba(0, 0, 0, 0.12);` | `border: 1px solid var(--gallery-border-default);` |
| 734 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 752 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 753 | `background: rgba(0, 0, 0, 0.04);` | `background: var(--gallery-surface-hover);` |
| 760 | `background: color-mix(in srgb, var(--primary-color) 10%, transparent);` | `background: var(--gallery-accent-muted);` |
| 761 | `border: 1px solid color-mix(in srgb, var(--primary-color) 20%, transparent);` | `border: 1px solid var(--gallery-accent-border);` |
| 762 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 767 | `background: color-mix(in srgb, var(--primary-color) 16%, transparent);` | `background: color-mix(in srgb, var(--gallery-accent-default) 16%, transparent);` |
| 768 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 792 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 793 | `border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));` | `border: 1px solid var(--gallery-border-default);` |
| 795 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 803 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 808 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 830 | `background: var(--surface-color);` | `background: var(--gallery-surface-elevated);` |
| 831 | `border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));` | `border: 1px solid var(--gallery-border-default);` |
| 833 | `box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);` | `box-shadow: var(--gallery-shadow-lg);` |
| 848 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 857 | `background: rgba(0, 0, 0, 0.05);` | `background: var(--gallery-surface-hover);` |
| 861 | `background: color-mix(in srgb, var(--primary-color) 10%, transparent);` | `background: var(--gallery-accent-muted);` |
| 862 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 887 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 888 | `border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));` | `border: 1px solid var(--gallery-border-default);` |
| 896 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 912 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 918 | `background: color-mix(in srgb, var(--primary-color) 12%, transparent);` | `background: var(--gallery-accent-muted);` |
| 919 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 932 | `background: rgba(0, 0, 0, 0.1);` | `background: color-mix(in srgb, var(--gallery-text-primary) 10%, transparent);` |
| 942 | `background: linear-gradient(90deg, var(--primary-color), #e8c07a);` | Giữ nguyên (gradient slider) |
| 965 | `background: var(--primary-color);` | `background: var(--gallery-accent-default);` |
| 966 | `border: 3px solid #fff;` | `border: 3px solid var(--gallery-text-inverse);` |
| 975 | `background: var(--primary-color);` | `background: var(--gallery-accent-default);` |
| 976 | `border: 3px solid #fff;` | `border: 3px solid var(--gallery-text-inverse);` |
| 989 | `background: linear-gradient(135deg, var(--primary-color), #e8c07a);` | Giữ nguyên (tooltip gradient) |
| 991 | `color: #fff;` | `color: var(--gallery-text-inverse);` |

...còn nhiều dòng tương tự ở GalleryGrid (file lớn 1271 dòng). Phải kiểm tra từng dòng có chứa hardcode.

**File: `AppHeader.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 111 | `border: 1px solid rgba(0, 0, 0, 0.12);` | `border: 1px solid var(--gallery-border-default);` |
| 113 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 114 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 123 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 126 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 133 | `border: 1px solid rgba(0, 0, 0, 0.12);` | `border: 1px solid var(--gallery-border-default);` |
| 135 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 136 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 145 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 148 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 171 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 177 | `color: var(--title-color);` | `color: var(--gallery-text-primary);` |
| 289 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 292 | `border: 1px solid rgba(0, 0, 0, 0.1);` | `border: 1px solid var(--gallery-border-default);` |
| 301 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 307 | `border-color: var(--primary-color);` | `border-color: var(--gallery-accent-default);` |
| 316 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 322 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 328 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 338 | `background: rgba(0, 0, 0, 0.05);` | `background: var(--gallery-surface-hover);` |
| 339 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 367 | `color: var(--title-color);` | `color: var(--gallery-text-primary);` |

**KHÔNG ĐỤNG:** Theme-toggle gradient, thumb, icons (dòng 180-286). Brand-hero, brand-icon, brand-title (dòng 342-380+).

**File: `SidebarHeader.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 73 | `background-color: var(--surface-color, #fff);` | `background-color: var(--gallery-surface-default);` |
| 74 | `border-bottom: 1px solid rgba(0, 0, 0, 0.06);` | `border-bottom: 1px solid var(--gallery-border-subtle);` |
| 94 | `border: 1px solid rgba(0, 0, 0, 0.1);` | `border: 1px solid var(--gallery-border-default);` |
| 98 | `border-color: var(--primary-color, #ff6b35);` | `border-color: var(--gallery-accent-default);` |
| 103 | `border-color: var(--primary-color, #ff6b35);` | `border-color: var(--gallery-accent-default);` |
| 153 | `color: var(--text-color, #000);` | `color: var(--gallery-text-primary);` |

**File: `FolderTreeItem.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 161 | `border: 1px solid rgba(0, 0, 0, 0.08);` | `border: 1px solid var(--gallery-border-subtle);` |
| 196 | `border-left: 1px dashed rgba(0, 0, 0, 0.06);` | `border-left: 1px dashed var(--gallery-border-subtle);` |

**File: `Breadcrumb.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 277 | `background-color: rgba(0, 0, 0, 0.05);` | `background-color: var(--gallery-surface-hover);` |
| 354 | `border: 1px solid var(--border-color, rgba(0, 0, 0, 0.1));` | `border: 1px solid var(--gallery-border-default);` |
| 454 | `border-color: rgba(255, 255, 255, 0.1);` | `border-color: var(--gallery-border-default);` |
| 471 | `background-color: rgba(255, 255, 255, 0.08);` | `background-color: var(--gallery-surface-hover);` |

**File: `MobileHeader.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 103 | `border-bottom: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.08)) 50%, transparent);` | `border-bottom: 1px solid color-mix(in srgb, var(--gallery-border-subtle) 50%, transparent);` |
| 155 | `border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.12)) 60%, transparent);` | `border: 1px solid color-mix(in srgb, var(--gallery-border-default) 60%, transparent);` |

**File: `AlbumScroller.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 274 | `border: 1px solid var(--border-color, rgba(0,0,0,0.12));` | `border: 1px solid var(--gallery-border-default);` |

**File: `BottomNavigationBar.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 53 | `border-top: 1px solid color-mix(in srgb, var(--border-color, rgba(0,0,0,0.08)) 50%, transparent);` | `border-top: 1px solid color-mix(in srgb, var(--gallery-border-subtle) 50%, transparent);` |
| 95 | `color: var(--primary-color, #d6a15d);` | `color: var(--gallery-accent-default);` |

**File: `MobileFloatingBottomBar.vue`**

| Dòng | Old | New |
|------|-----|-----|
| 64 | `border: 1px solid color-mix(in srgb, var(--border-color, rgba(0, 0, 0, 0.08)) 50%, transparent);` | `border: 1px solid color-mix(in srgb, var(--gallery-border-subtle) 50%, transparent);` |

**File: `App.vue` (scoped styles)**

| Dòng | Old | New |
|------|-----|-----|
| 228 | `background: var(--bg-color);` | `background: var(--gallery-surface-dim);` |
| 229 | `color: var(--text-color);` | `color: var(--gallery-text-primary);` |
| 241 | `background: linear-gradient(180deg, rgba(0, 0, 0, 0.02), rgba(0, 0, 0, 0.04)), var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 268 | `color: var(--title-color);` | `color: var(--gallery-text-primary);` |
| 278 | `background: rgba(0, 0, 0, 0.04);` | `background: var(--gallery-surface-hover);` |
| 306 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 335 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 336 | `color: var(--muted-text);` | `color: var(--gallery-text-secondary);` |
| 341 | `box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);` | `box-shadow: var(--gallery-shadow-sm);` |
| 346 | `color: var(--primary-color);` | `color: var(--gallery-accent-default);` |
| 347 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 357 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 360 | `box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.04);` | `box-shadow: 0 0 0 1px var(--gallery-border-subtle);` |

### Commit cho Step 7
```
git add frontend/src/components/GalleryGrid.vue frontend/src/components/AppHeader.vue frontend/src/components/SidebarHeader.vue frontend/src/components/FolderTreeItem.vue frontend/src/components/Breadcrumb.vue frontend/src/components/MobileHeader.vue frontend/src/components/AlbumScroller.vue frontend/src/components/BottomNavigationBar.vue frontend/src/components/MobileFloatingBottomBar.vue frontend/src/App.vue
git commit -m "refactor(theme): replace remaining component hardcode with gallery tokens"
```

---

## Phase 3: No-Shadow Card Adoption (0.5 ngày)

### Step 1 — PhotoCard: bỏ box-shadow trên card

**File:** `frontend/src/components/PhotoCard.vue`

Thay đổi:

| Dòng | Old | New |
|------|-----|-----|
| 137-139 | `background: var(--surface-color, #fff);` + `box-shadow: var(--shadow-card);` | `background: var(--gallery-surface-default);` (KHÔNG có box-shadow) |
| 155-156 | `transform: translateY(-2px) scale(1.02);` + `box-shadow: var(--shadow-card-hover);` | `transform: translateY(-2px) scale(1.02);` (KHÔNG có box-shadow) |
| 167 | `box-shadow: var(--shadow-card-level2);` | Xóa dòng |
| 183-189 | `html[data-theme="dark\"] & { background: var(--surface-color); border: 1px solid rgba(255, 255, 255, 0.06); box-shadow: none;` | `html[data-theme="dark\"] & { background: var(--gallery-surface-default); border: 1px solid var(--gallery-border-default);` |

**Kết quả:** PhotoCard chỉ dùng surface differentiation để phân biệt với page bg, không cần shadow.

### Step 2 — AlbumCard: bỏ box-shadow cho mobile (desktop giữ glow cho hover)

**File:** `frontend/src/components/AlbumCard.vue`

| Dòng | Old | New |
|------|-----|-----|
| 56-58 | `box-shadow: none;` (đã không có shadow) | Giữ nguyên |
| 94 | `border: 4px solid var(--album-border-color);` | `border: 4px solid var(--gallery-surface-default);` |
| 95 | `background: var(--surface-color);` | `background: var(--gallery-surface-default);` |
| 106 | `background: var(--placeholder-bg);` | `background: var(--gallery-surface-hover);` |
| 120 | `box-shadow: var(--shadow-card);` | Xóa (surface diff) |
| 128 | `box-shadow: var(--shadow-card-level2);` | Xóa (surface diff) |
| 186 | `box-shadow: none;` | Giữ nguyên |
| 189 | `box-shadow: var(--shadow-dark-layer-back);` | Giữ nguyên (dark mode layer shadow là design choice cho album layers) |
| 193 | `box-shadow: var(--shadow-dark-layer-front);` | Giữ nguyên |
| 202-212 | glow shadows | Giữ nguyên 100% (desktop hover glow) |
| 216 | `box-shadow: var(--glow-card-active);` | Giữ nguyên |
| 222 | `box-shadow: var(--shadow-card-level2);` | Xóa |
| 231 | `box-shadow: none;` (mobile) | Giữ nguyên |

### Commit
```
git add frontend/src/components/PhotoCard.vue frontend/src/components/AlbumCard.vue
git commit -m "feat(theme): adopt no-shadow card — PhotoCard surface diff, AlbumCard mobile no-shadow"
```

---

## Phase 4: Cleanup + Test (0.5 ngày)

### Step 1 — Xóa file thừa
- `_mobile-overrides.scss`: Có thể GIỮ (vẫn disable glow/shadow cho mobile — cần cho AlbumCard glow)

**Không xóa gì cả — mọi file SCSS đều còn dùng.**

### Step 2 — Test 4 Scenarios
1. **Light + Desktop:** Load gallery, check all surfaces, cards, modals
2. **Dark + Desktop:** Toggle theme, verify warm near-black, cards, glow
3. **Light + Mobile:** Check sidebar overlay, bottom nav, sheet
4. **Dark + Mobile:** Check all mobile-specific surfaces

### Step 3 — Verify Animations
Check từng animation trong blacklist:
- [ ] `iconFlicker` — brand-icon dark mode
- [ ] `dark-title-shimmer` — brand-title dark mode
- [ ] `shimmer` — PhotoCard, SkeletonLoader
- [ ] EmptyState animations
- [ ] Theme-toggle transition
- [ ] PhotoCard hover scale
- [ ] AlbumCard 3D desktop hover
- [ ] Toast enter/leave

### Step 4 — Verify Focus Ring
- [ ] `--focus-ring-shadow` vẫn định nghĩa và hoạt động
- [ ] Keyboard navigation: Tab qua các element

### Step 5 — Build
```bash
cd /home/ubuntu/gallery-repo/frontend
npm run build
```
Verify không có lỗi build, không có undefined CSS variables.

### Commit
```
git commit -m "chore: cleanup, final visual test pass"
```

---

## Commit Strategy Tổng Quan

| # | Commit Message | Files | Phase |
|---|---------------|-------|-------|
| 1 | `feat(theme): create _tokens.css with all design tokens` | `_tokens.css` | 1 |
| 2 | `refactor(theme): replace ToastItem hardcode with gallery tokens` | `ToastItem.vue` | 2 |
| 3 | `refactor(theme): replace EmptyState accent colors with gallery tokens` | `EmptyState.vue` | 2 |
| 4 | `refactor(theme): replace SettingsModal hardcode with gallery tokens` | `SettingsModal.vue` | 2 |
| 5 | `refactor(theme): replace SkeletonLoader bg with gallery tokens` | `SkeletonLoader.vue` | 2 |
| 6 | `refactor(theme): replace lightbox hardcode with gallery-lightbox tokens` | `Lightbox.vue`, `_lightbox-*.scss` | 2 |
| 7 | `refactor(theme): replace remaining component hardcode with tokens` | GalleryGrid, AppHeader, SidebarHeader, FolderTreeItem, Breadcrumb, MobileHeader, AlbumScroller, BottomNav, MobileBottomBar, App.vue | 2 |
| 8 | `feat(theme): adopt no-shadow PhotoCard — surface diff only` | `PhotoCard.vue` | 3 |
| 9 | `feat(theme): adopt no-shadow AlbumCard — mobile surface diff only` | `AlbumCard.vue` | 3 |
| 10 | `chore: final cleanup and visual test pass` | — | 4 |

**Tổng cộng: 10 commits.** Có thể squash thành 4-5 commit lớn hơn nếu muốn (1 commit/phase).

---

## Rủi Ro & Mitigation

| Rủi ro | Impact | Mitigation |
|---------|--------|------------|
| CSS variable undefined (browser fallback) | Medium | Dùng `var(--gallery-x, fallback-value)` pattern trong _tokens.css |
| Xung đột khi import _tokens.css | Low | Import ở đầu main.scss, trước :root definitions |
| Quên thay hardcode ở component nào đó | Medium | Phase 4 visual test checklist bắt được |
| AlbumCard glow/shadow bị ảnh hưởng | High | **Blacklist AlbumCard glow styles** — không được đụng |
| Theme-toggle gradient bị thay | High | **Blacklist theme-toggle** — không được đụng |
| Build fail vì undefined CSS var | High | Build thử sau mỗi phase |
| `:global(html[data-theme="dark"])` not matching `:root[data-theme="dark"]` | Low | Kiểm tra consistent selector — dùng `:root[data-theme="dark"]` everywhere |

---

## Effort Summary

| Phase | Effort | Mô tả |
|-------|--------|-------|
| Phase 0 | 0.5 ngày | Branch + checklist |
| Phase 1 | 1 ngày | `_tokens.css` ~300 dòng |
| Phase 2 | 2-3 ngày | ~20 files, ~200 changes |
| Phase 3 | 0.5 ngày | 2 files, ~15 changes |
| Phase 4 | 0.5 ngày | Test + build |
| **Total** | **4.5-5.5 ngày** | ~20 files, ~250 changes |

---

## Token Schema References (Quick Lookup)

### Light Mode
```
Surface: dim=#f5eee6  default=#ffffff  elevated=#ffffff  hover=#faf5ef
Text:    primary=#143d60  secondary=#4a6587  tertiary=#8ba0b8  disabled=#bcc8d6
Accent:  default=#ff6b35  hover=#e85a26  muted=#fff0ea  text=#d45420
Border:  default=#e5ddd4  subtle=#ede7e0  hover=#d6cec4
```

### Dark Mode
```
Surface: dim=#0f0f0f  default=#1a1918  elevated=#242321  hover=#2a2826
Text:    primary=#e4e6eb  secondary=#b0b3b8  tertiary=#7a7f85  disabled=#505459
Accent:  default=#d6a15d  hover=#e0b070  muted=#2a2218  text=#e8c07a
Border:  default=#2d2b28  subtle=#262422  hover=#3a3734  accent=#3d3528
```
