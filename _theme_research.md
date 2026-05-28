# Theme Design Research — Best Practice từ 11 Platform Lớn

> **Mục đích:** Research cho gallery app Vue 3 refactor theme system.
> **Phạm vi:** Facebook, Reddit, Twitter/X, Instagram, YouTube, GitHub (Primer), Discord, Linear, Notion, Material Design 3, Apple HIG.

---

## 1. Bảng So Sánh Token Naming Conventions

| Platform | Prefix | Pattern | Ví dụ |
|---|---|---|---|
| **MD3** | `md-sys-color-` | `{category}-{modifier}` | `md-sys-color-surface-container`, `md-sys-color-on-surface` |
| **GitHub Primer** | `--` | `{category}{Group}-{modifier}` | `--bgColor-default`, `--fgColor-muted`, `--borderColor-accent-emphasis` |
| **Discord** | `--` | `--{context}-{modifier}` | `--bg-surface`, `--bg-elevated`, `--text-normal`, `--text-muted` |
| **Linear** | `--` | `--{context}-{modifier}` | `--bg-primary`, `--bg-secondary`, `--text-primary`, `--text-secondary` |
| **Apple HIG** | — | `{context}{Modifier}` | `systemBackground`, `secondaryLabel`, `separator`, `tertiarySystemFill` |
| **Notion** | `--` | `--{color}-{role}` | `--bg-color`, `--text-color`, `--border-color` (minimal) |
| **Twitter/X** | `--` | `--{context}-{modifier}` | `--bg-primary`, `--bg-secondary`, `--text-primary` |
| **Facebook** | `--` | `--{context}-{modifier}` | `--surface-background`, `--secondary-text`, `--card-background` |
| **YouTube** | `--` | `--{context}-{modifier}` | `--yt-spec-base-background`, `--yt-spec-text-primary` |
| **Reddit** | `--` | `--{context}-{modifier}` | `--color-default-background`, `--color-secondary-text` |

### Nhận xét Token Naming

- **MD3** có hệ thống token đầy đủ nhất, chia rõ: `sys` (system), `ref` (reference palette), `surface-container-{level}`
- **Primer (GitHub)** dùng convention `{category}{Group}-{modifier}` với 3 cấp: category (bg/fg/border) → group (accent/danger/success) → modifier (default/muted/emphasis)
- **Apple HIG** dùng semantic naming không có prefix, dễ đọc nhưng khó mở rộng
- **Linear/Notion** — tối giản, chỉ vài token semantic
- **Đề xuất cho Gallery:** Dùng MD3-inspired naming nhưng simplified: `--gallery-{category}-{modifier}` (vd: `--gallery-surface-default`, `--gallery-text-primary`)

---

## 2. Bảng So Sánh Dark Mode Colors

### 2.1 Background Colors (Page/Canvas)

| Platform | Dark BG | Hex | Ghi chú |
|---|---|---|---|
| **MD3** | `surface-dim` | **#141218** | Purple-ish tint |
| **GitHub** | `bgColor-default` | **#0d1117** | Blue-ish dark |
| **Discord** | `bg-primary` | **#313338** | Warm dark gray |
| **Twitter Dim** | `bg-primary` | **#15202b** | Blue-ish |
| **Twitter Dark** | — | **#000000** | Pure black (Lights Out) |
| **Facebook** | `surface-background` | **#18191A** | Near-black |
| **Instagram** | — | **#000000** | Pure black |
| **YouTube** | `base-background` | **#0F0F0F** | Near-black |
| **Reddit** | `default-background` | **#0E1113** | Near-black |
| **Linear** | `bg-primary` | **#0E0E0E** | Near-black |
| **Notion** | `bg-color` | **#191919** | Warm dark |
| **Apple iOS** | `systemBackground` | **#000000** | Pure black |
| **Apple macOS** | `systemBackground` | **#1E1E1E** | Dark gray |

### 2.2 Surface Colors (Cards, Sidebars, Elevated)

| Platform | Surface 1 | Surface 2 | Surface 3 | Elevated |
|---|---|---|---|---|
| **MD3** | #211f26 (low) | #27252c (container) | #2c2a31 (high) | #38343c (highest) |
| **GitHub** | #151b23 (muted) | — | — | (uses shadow) |
| **Discord** | #2b2d31 (secondary) | #1e1f22 (tertiary) | — | #111214 (elevated) |
| **Twitter Dim** | #1e2732 | — | — | (uses shadow) |
| **Facebook** | #242526 | #3A3B3C | — | — |
| **YouTube** | #212121 | #272727 | — | — |
| **Reddit** | #1A1A1B | #272729 | — | #343536 (hover) |
| **Linear** | #1A1A1A | #232323 | — | #2A2A2A (hover) |
| **Notion** | #202020 | #2B2B2B | — | — |

### 2.3 Text Colors

| Platform | Text Primary | Text Secondary | Text Muted/Disabled | Link |
|---|---|---|---|---|
| **MD3** | #e6e1e5 | #cac4d0 | — | #d0bcff |
| **GitHub** | #f0f6fc | #9198a1 | #656c76 | #4493f8 |
| **Discord** | #dbdee1 | #949ba4 | #5c5e66 | #00a8fc |
| **Twitter** | #e7e9ea | #71767b | — | #1d9bf0 |
| **Facebook** | #e4e6eb | #b0b3b8 | — | #1877f2 |
| **Instagram** | #f5f5f5 | #8e8e8e | — | #0095f6 |
| **YouTube** | #f1f1f1 | #aaaaaa | #717171 | #3ea6ff |
| **Reddit** | #d7dadc | #818384 | — | #4fbcff |
| **Linear** | #ededed | #8a8a8a | — | #5e6ad2 |
| **Apple** | #ffffff | rgba(235,235,245,0.6) | rgba(235,235,245,0.3) | #0a84ff |

### 2.4 Accent / Primary Colors

| Platform | Accent Color | Ghi chú |
|---|---|---|
| **MD3** | #d0bcff (primary) | Purple tint, tone-based |
| **GitHub** | #4493f8 / #1f6feb | Blue |
| **Discord** | #5865f2 | Blurple |
| **Twitter/X** | #1d9bf0 | Blue |
| **Facebook** | #1877f2 | Blue |
| **Instagram** | #0095f6 (action) | Blue (gradient accent: pink→orange→purple) |
| **YouTube** | #ff0000 | Red |
| **Reddit** | #ff4500 | Orange |
| **Linear** | #5e6ad2 | Blue-purple |
| **Notion** | #2383e2 | Blue |
| **Apple** | #0a84ff | Blue |

### 2.5 Border Colors

| Platform | Default Border | Subtle Border | Ghi chú |
|---|---|---|---|
| **MD3** | #938f99 (outline) | #49454f (outline-variant) | — |
| **GitHub** | #3d444d | #3d444db3 | Có alpha |
| **Discord** | #3f4147 | — | — |
| **Twitter** | #2f3336 | — | — |
| **Facebook** | #3e4042 | — | — |
| **YouTube** | #303030 | — | — |
| **Reddit** | #343536 | — | — |
| **Linear** | #2e2e2e | — | — |
| **Notion** | #373737 | — | Rất subtle |
| **Apple** | rgba(84,84,88,0.65) | — | Semi-transparent |

---

## 3. Surface Layers & Elevation

### 3.1 So Sánh Số Lượng Surface Level

| Platform | Levels | Tên các level |
|---|---|---|
| **MD3** | 6 | `dim` (0), `container-lowest` (1), `container-low` (2), `container` (3), `container-high` (4), `container-highest` (5) |
| **GitHub** | 3 | `default` (page), `muted` (secondary), `inset` (recessed) |
| **Discord** | 3+ | `primary` (page), `secondary` (sidebar), `tertiary` (darkest), `elevated` (modal) |
| **Apple** | 3 | `systemBackground`, `secondarySystemBackground`, `tertiarySystemBackground` |
| **Twitter** | 2 | `primary`, `secondary` (dim: #15202b / #1e2732) |
| **Linear** | 3-4 | `bg-primary` (#0E0E0E), `bg-secondary` (#1A1A1A), elevated (#232323), hover (#2A2A2A) |
| **Facebook** | 3 | `bg` (#18191A), `surface` (#242526), `comment-bg` (#3A3B3C) |

### 3.2 Elevation (Shadow) Systems

| Platform | Shadow Style | Card Shadow |
|---|---|---|
| **MD3** | Multi-layer shadow | 5 levels: từ 1px đến 24px blur |
| **Twitter** | Subtle shadow | Soft shadow trên card |
| **GitHub** | Minimal shadow | Chủ yếu dùng border, shadow rất nhẹ |
| **Reddit** | No shadow | Dùng border (#343536) để phân cách |
| **Facebook** | No shadow | Dùng surface color differentiation |
| **Notion** | No shadow | Pure flat design |
| **Linear** | Minimal shadow | Thích border hơn shadow |
| **YouTube** | Subtle shadow | Card có shadow nhẹ |

### 3.3 Surface Layer Pattern — Đề xuất cho Gallery

```css
/* Gallery surface layers — inspired by MD3 + Linear */
--gallery-surface-dim:        /* Nền tối nhất (0) */
--gallery-surface-low:        /* Card/surface level 1 */
--gallery-surface-default:    /* Surface chính (1) */
--gallery-surface-high:       /* Surface nổi bật (2) */
--gallery-surface-elevated:   /* Modal/dialog (3) */
```

---

## 4. Card Design Patterns

### 4.1 Border Radius So Sánh

| Platform | Card Radius | Button Radius | Notes |
|---|---|---|---|
| **MD3** | 12px (medium), 16px (large), 28px (extra-large) | 20px (full) | Shape-based tokens |
| **Twitter/X** | 16px | 9999px (pill) | Bo tròn nhiều |
| **Discord** | 8px | 3px (sharp) | Bo tròn vừa phải |
| **GitHub** | 6px | 6px | Đồng bộ |
| **Reddit** | 0-4px | 4px | Gần như vuông |
| **Facebook** | 8px | 6px | — |
| **YouTube** | 12px (thumbnail) | 4px (text), 18px (pill) | — |
| **Linear** | 8-12px | 6-8px | — |
| **Notion** | 8px | 8px | Đồng bộ |
| **Apple** | 10px (iOS), 5px (macOS) | 8-10px | — |
| **Instagram** | 8px | 8px | — |

### 4.2 Hover State Patterns

| Platform | Hover Effect | Timing |
|---|---|---|
| **Twitter** | Background change + shadow deepen | ~200ms ease |
| **GitHub** | Background change (muted→emphasis) | 80ms linear |
| **Discord** | Background tint (#35373c) | 150ms ease |
| **Facebook** | Background tint | ~200ms |
| **YouTube** | Background lighten (#3d3d3d) + shadow | ~200ms |
| **Linear** | Background lighten (#2A2A2A) | 150ms ease |
| **MD3** | Elevation increase + state layer overlay | 200ms ease |

### 4.3 Card Design Patterns — Best Practices

1. **Border radius:** 12px là sweet spot cho gallery app (giữa MD3 12px và Twitter 16px)
2. **Surface separation:** Dùng `surface-low` (nền card) trên `surface-dim` (nền page) — không cần shadow
3. **Elevation hint:** Shadow nhẹ (1px + 4px blur) cho card nổi bật
4. **Hover:** Tăng surface lên 1 level + border highlight hoặc shadow deepen
5. **Active/Selected:** Accent border hoặc background tint

---

## 5. Typography Scale

### 5.1 Base Sizes

| Platform | Base Size | Scale System |
|---|---|---|
| **MD3** | 16px | System scale 1.0 / 1.14 (minor second) |
| **GitHub** | 14px | — |
| **Reddit** | 14px | — |
| **Twitter** | 15px | — |
| **Discord** | 16px | — |
| **Apple** | 17px (body) | — |
| **Linear** | 14px | — |

### 5.2 Đề xuất cho Gallery

- **Base size:** 16px (MD3 + Discord standard)
- **Scale:** 1.25 (major third) cho headings
  - `h1`: 32px (2rem)
  - `h2`: 24px (1.5rem)
  - `h3`: 20px (1.25rem)
  - `body`: 16px (1rem)
  - `caption/small`: 12px (0.75rem)
  - `micro`: 10px (0.625rem) — photo date, metadata

---

## 6. Đề Xuất Token System Mới cho Gallery App

### 6.1 Naming Convention

```
--gallery-{category}-{group}-{modifier}
```

Categories: `surface`, `text`, `border`, `accent`, `elevation`, `radius`
Modifiers: `default`, `muted`, `emphasis`, `dim`, `low`, `high`, `elevated`

### 6.2 Color Tokens — Light Mode

```css
/* Surface — 6 levels (MD3-inspired) */
--gallery-surface-dim:              #f5f5f5   /* Nền page chính */
--gallery-surface-low:              #fafafa   /* Container low */
--gallery-surface-default:          #ffffff   /* Surface chính (card) */
--gallery-surface-high:             #ffffff   /* Surface nổi */
--gallery-surface-elevated:         #ffffff   /* Modal */
--gallery-surface-hover:            #f0f0f0   /* Hover state */

/* Text */
--gallery-text-primary:             #1a1a1a   /* Nội dung chính */
--gallery-text-secondary:           #666666   /* Phụ */
--gallery-text-tertiary:            #999999   /* Muted */
--gallery-text-disabled:            #cccccc   /* Disabled */
--gallery-text-inverse:             #ffffff   /* Text trên nền tối */

/* Border */
--gallery-border-default:           #e0e0e0   /* Border thường */
--gallery-border-subtle:            #eeeeee   /* Border nhẹ */
--gallery-border-hover:             #cccccc   /* Hover */

/* Accent (primary) */
--gallery-accent-default:           #6366f1   /* Indigo */
--gallery-accent-hover:             #4f46e5   /* Hover */
--gallery-accent-muted:             #eef2ff   /* BG accent nhẹ */
--gallery-accent-text:              #4338ca   /* Text accent */

/* Semantic */
--gallery-success:                  #22c55e
--gallery-warning:                  #f59e0b
--gallery-error:                    #ef4444
--gallery-info:                     #3b82f6
```

### 6.3 Color Tokens — Dark Mode

```css
/* Surface — 6 levels */
--gallery-surface-dim:              #0c0c0c   /* Nền page chính (near-black) */
--gallery-surface-low:              #141414   /* Container low */
--gallery-surface-default:          #1c1c1c   /* Surface chính (card) */
--gallery-surface-high:             #242424   /* Surface nổi */
--gallery-surface-elevated:         #2c2c2c   /* Modal */
--gallery-surface-hover:            #2a2a2a   /* Hover state */

/* Text */
--gallery-text-primary:             #f0f0f0   /* Nội dung chính */
--gallery-text-secondary:           #a0a0a0   /* Phụ */
--gallery-text-tertiary:            #707070   /* Muted */
--gallery-text-disabled:            #505050   /* Disabled */
--gallery-text-inverse:             #1a1a1a   /* Text trên nền sáng */

/* Border */
--gallery-border-default:           #333333   /* Border thường */
--gallery-border-subtle:            #282828   /* Border nhẹ */
--gallery-border-hover:             #444444   /* Hover */

/* Accent */
--gallery-accent-default:           #818cf8   /* Indigo sáng hơn cho dark */
--gallery-accent-hover:             #6366f1   /* Hover */
--gallery-accent-muted:             #1e1b4b   /* BG accent nhẹ */
--gallery-accent-text:              #a5b4fc   /* Text accent */

/* Semantic */
--gallery-success:                  #4ade80
--gallery-warning:                  #fbbf24
--gallery-error:                    #f87171
--gallery-info:                     #60a5fa
```

### 6.4 Elevation Shadows

```css
/* Light Mode */
--gallery-shadow-sm:   0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.08)
--gallery-shadow-md:   0 2px 4px rgba(0,0,0,0.05), 0 4px 8px rgba(0,0,0,0.08)
--gallery-shadow-lg:   0 4px 8px rgba(0,0,0,0.06), 0 8px 16px rgba(0,0,0,0.06)
--gallery-shadow-xl:   0 8px 16px rgba(0,0,0,0.08), 0 16px 32px rgba(0,0,0,0.06)

/* Dark Mode — shadows tối hơn, dùng opacity higher */
--gallery-shadow-sm:   0 1px 2px rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.15)
--gallery-shadow-md:   0 2px 4px rgba(0,0,0,0.35), 0 4px 8px rgba(0,0,0,0.15)
--gallery-shadow-lg:   0 4px 8px rgba(0,0,0,0.4), 0 8px 16px rgba(0,0,0,0.15)
--gallery-shadow-xl:   0 8px 16px rgba(0,0,0,0.45), 0 16px 32px rgba(0,0,0,0.15)
```

### 6.5 Border Radius

```css
--gallery-radius-sm:    4px    /* Tags, badges */
--gallery-radius-md:    8px    /* Cards, buttons */
--gallery-radius-lg:    12px   /* Thumbnails, modals */
--gallery-radius-xl:    16px   /* Hero card, full-width */
--gallery-radius-full:  9999px /* Pill, avatar */
```

### 6.6 Typography

```css
--gallery-font-family: system-ui, -apple-system, sans-serif
--gallery-font-size-xs:    0.625rem   /* 10px — micro */
--gallery-font-size-sm:    0.75rem    /* 12px — caption */
--gallery-font-size-base:  1rem       /* 16px — body */
--gallery-font-size-lg:    1.25rem    /* 20px — h3 */
--gallery-font-size-xl:    1.5rem     /* 24px — h2 */
--gallery-font-size-2xl:   2rem       /* 32px — h1 */
--gallery-font-size-3xl:   2.5rem     /* 40px — hero */
--gallery-line-height:     1.5
--gallery-line-height-sm:  1.25       /* Headings */
--gallery-font-weight-normal: 400
--gallery-font-weight-medium: 500
--gallery-font-weight-bold:   600
```

---

## 7. UI/UX Patterns Có Thể Áp Dụng cho Gallery App

### 7.1 Photo Thumbnail Grid

| Pattern | Source | Áp dụng |
|---|---|---|
| **Border radius 12px** | YouTube thumbnails + MD3 | Thumbnail card gallery |
| **Hover: scale 1.02 + shadow** | YouTube hover | Preview khi hover |
| **Selection: accent border** | GitHub + Linear | Selected photo indicator |
| **Surface differentiation** | Facebook (no border) | Card dùng surface khác page |
| **Minimal chrome** | Notion + Linear | Giảm border, focus vào nội dung |

### 7.2 Navigation / Sidebar

| Pattern | Source | Áp dụng |
|---|---|---|
| **Surface tint navigation** | Discord sidebar | Navigation darker than content |
| **Icon + label** | Linear | Sidebar item |
| **Active indicator** | Linear (accent bar bên trái) | Active nav state |
| **Bottom tab bar** | Instagram + Twitter | Mobile navigation |

### 7.3 Photo Detail / Viewer

| Pattern | Source | Áp dụng |
|---|---|---|
| **Full-screen immersive** | Instagram | Photo viewer |
| **Dark overlay trên image** | YouTube ambient mode | Metadata overlay |
| **Bottom sheet info** | Apple Photos + Twitter | Photo info panel |
| **Gesture-based** | Instagram | Swipe, pinch zoom |

### 7.4 Micro-interactions

| Pattern | Source | Timing |
|---|---|---|
| **Like animation** | Instagram heart | 300ms spring |
| **Surface transition** | Linear | 150ms ease |
| **Focus ring** | GitHub (2px accent border) | 80ms |
| **Loading skeleton** | Facebook/YouTube | Shimmer effect |

---

## 8. Tham Khảo

### Design Systems & Docs
- **MD3 Color System:** https://m3.material.io/styles/color
- **MD3 Elevation:** https://m3.material.io/styles/elevation
- **GitHub Primer:** https://primer.style/foundations/color
- **Apple HIG Color:** https://developer.apple.com/design/human-interface-guidelines/color
- **Linear Design:** https://linear.app/docs/design-system

### Code References
- Primer Primitives (CSS): `@primer/primitives@11.9.0`
- Material Web Components: `@material/web@2.4.1`
- MD3 SCSS tokens: `_md-sys-color.scss`

### Color Palette References per Platform
- **Discord:** `#313338` (primary), `#2b2d31` (secondary), `#1e1f22` (tertiary), `#5865f2` (accent)
- **Twitter/X:** `#15202b` (dim), `#000000` (dark), `#1d9bf0` (accent)
- **Facebook:** `#18191A` (bg), `#242526` (card), `#1877F2` (accent)
- **YouTube:** `#0F0F0F` (bg), `#212121` (sidebar), `#FF0000` (accent)
- **Reddit:** `#0E1113` (bg), `#1A1A1B` (card), `#FF4500` (accent)
- **Notion:** `#191919` (bg), `#202020` (card), `#2383E2` (accent)
- **Instagram:** `#000000` (bg), `#1a1a1a` (surface), `#0095F6` (accent)

---

## 9. Tổng Kết & Recommendations

### Token System: Gallery-specific recommendations

1. **Inspired by MD3** — Dùng surface container levels (5-6 levels) như MD3
2. **Semantic naming như Primer** — Dễ đọc, dễ maintain: `--gallery-surface-default`
3. **3 accent colors tối đa** — primary, semantic (success/warning/error)
4. **Dark mode: near-black (#0c0c0c) thay vì pure black** — Instagram dùng pure black, nhưng MD3/Discord dùng near-black cho mắt đỡ mỏi
5. **Card radius: 12px** — Sweet spot giữa MD3 (12px) và Twitter (16px)
6. **Shadow: 2-layer MD3-style** — Realistic hơn single shadow
7. **Border radius tokens: 3 level** — sm (4px), md (8px), lg (12px)
8. **Minimal border, ưu tiên surface differentiation** — Facebook/Notion approach

### Key Differences from MD3 — Gallery-specific adjustments

| Aspect | MD3 | Gallery (đề xuất) | Lý do |
|---|---|---|---|
| Primary color | Purple (#d0bcff) | Indigo (#6366f1 / #818cf8) | Trung tính, không gây distraction với ảnh |
| Surface tints | Purple-ish | Neutral (cool gray) | Ảnh cần nền trung tính |
| Font scale | 1.0 system | Major third 1.25 | Rõ hierarchy cho album/photo titles |
| Shadow | Multi-layer complex | Simplified 2-layer | Performance trên nhiều thumbnails |
| Border radius tokens | Many shapes | 4 sizes | Simpler cho gallery |
