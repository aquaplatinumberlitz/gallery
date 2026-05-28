<script setup lang="ts">
import { Landmark, Search, X, Settings, Menu } from 'lucide-vue-next'

interface Props {
  isMobile: boolean
  isSidebarOpen: boolean
  isDark: boolean
  searchQuery: string
}
defineProps<Props>()

const emit = defineEmits<{
  'update:searchQuery': [value: string]
  'toggle-sidebar': []
  'toggle-theme': []
  'open-settings': []
}>()

function onSearchInput(e: Event) {
  const target = e.target as HTMLInputElement
  emit('update:searchQuery', target.value)
}

function clearSearch() {
  emit('update:searchQuery', '')
}
</script>

<template>
  <header class="content-header">
    <div class="header-left">
      <button 
        v-if="!isMobile"
        class="hamburger-btn"
        @click="emit('toggle-sidebar')"
        title="Toggle sidebar"
      >
        <Menu :size="18" />
      </button>
      <button 
        class="settings-btn" 
        @click="emit('open-settings')"
        title="Change Intro Page"
      >
        <Settings :size="18" />
      </button>
    </div>
    <div class="brand-hero">
      <div class="brand-icon flicker-effect">
        <Landmark :size="40" />
      </div>
      <div class="brand-text">
        <p class="eyebrow">Local collections</p>
        <h1 class="brand-title">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="18" height="18" class="title-sparkle"><path fill="currentColor" d="M480 96L512 24L544 96L616 128L544 160L512 232L480 160L408 128L480 96zM160 256L224 112L288 256L432 320L288 384L224 528L160 384L16 320L160 256zM480 408L512 480L584 512L512 544L480 616L448 544L376 512L448 480L480 408z"/></svg>
          Museum Art Gallery
        </h1>
      </div>
    </div>
    <div class="header-actions">
      <button 
        class="theme-toggle" 
        type="button" 
        @click="emit('toggle-theme')" 
        :title="isDark ? 'Switch to Light mode' : 'Switch to Dark mode'" 
        :class="{ 'is-dark': isDark }"
      >
        <span class="toggle-track">
          <span class="toggle-thumb">
            <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="18" height="18"><path fill="currentColor" d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"/></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="18" height="18"><path fill="currentColor" d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"/></svg>
          </span>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="16" height="16" class="icon-left"><path fill="currentColor" d="M340.8 43.6L396.3 136.2C477.1 115.9 525 104 539.9 100.2C536.2 115.1 524.2 163 503.9 243.8C575.4 286.6 617.7 312 630.9 319.9C617.7 327.8 575.4 353.2 503.9 396C524.2 476.8 536.2 524.7 539.9 539.6C525 535.9 477.1 523.9 396.3 503.6C353.5 575.1 328.1 617.4 320.2 630.6C312.3 617.4 286.9 575.1 244.1 503.6C163.3 523.9 115.5 535.9 100.5 539.6C104.2 524.7 116.2 476.8 136.5 396C65 353.2 22.7 327.8 9.5 319.9C22.7 312 65 286.6 136.5 243.8C116.2 163 104.3 115.2 100.5 100.2C115.4 103.9 163.3 115.9 244.1 136.2C286.9 64.7 312.3 22.4 320.2 9.2L340.8 43.5zM320.2 176C240.7 175.9 176.1 240.3 176 319.8C175.9 399.3 240.3 463.9 319.8 464C399.3 464.1 463.9 399.7 464 320.2C464.1 240.7 399.7 176.1 320.2 176zM319.8 416C266.8 415.9 223.9 372.8 224 319.8C224.1 266.8 267.2 223.9 320.2 224C373.2 224.1 416.1 267.2 416 320.2C415.9 373.2 372.8 416.1 319.8 416z"/></svg>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 640" width="16" height="16" class="icon-right"><path fill="currentColor" d="M423.7 85.9C336.6 107.5 272 186.2 272 280C272 390.4 361.5 480 472 480C490.5 480 508.4 477.5 525.4 472.8C478.8 535.4 404.1 576 320 576C178.6 576 64 461.4 64 320C64 178.6 178.6 64 320 64C356.9 64 392 71.8 423.7 85.9z"/></svg>
        </span>
      </button>
      <div class="search-box">
        <Search :size="18" class="search-icon" />
        <input
          id="gallery-search"
          :value="searchQuery"
          @input="onSearchInput"
          type="search"
          placeholder="Search images..."
          autocomplete="off"
        />
        <button 
          v-if="searchQuery" 
          class="clear-btn" 
          @click="clearSearch"
          type="button"
        >
          <X :size="12" />
        </button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.settings-btn {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: var(--surface-color);
  color: var(--text-color);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease, box-shadow 150ms ease, border-color 120ms ease;
  font-size: 16px;
}

.settings-btn:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  transform: translateY(-1px);
  color: var(--primary-color);
}

.hamburger-btn {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: var(--surface-color);
  color: var(--text-color);
  cursor: pointer;
  display: none;
  align-items: center;
  justify-content: center;
  transition: transform 120ms ease, box-shadow 150ms ease, border-color 120ms ease;
  font-size: 16px;
}

.hamburger-btn:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  transform: translateY(-1px);
  color: var(--primary-color);
}

.content-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: start;
  gap: 12px;
  flex-shrink: 0;
}

.header-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.eyebrow {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
  color: var(--muted-text);
}

h1 {
  margin: 4px 0 0 0;
  font-size: clamp(22px, 3vw, 30px);
  color: var(--title-color);
}

.theme-toggle {
  position: relative;
  width: 72px;
  height: 36px;
  border: none;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 0;
  border-radius: 50px;
  cursor: pointer;
  transition: all 0.4s cubic-bezier(0.68, -0.15, 0.265, 1.35);
  box-shadow: 
    inset 0 2px 4px rgba(0, 0, 0, 0.2),
    0 4px 12px rgba(102, 126, 234, 0.3);
}

.theme-toggle.is-dark {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  box-shadow: 
    inset 0 2px 4px rgba(0, 0, 0, 0.4),
    0 4px 12px rgba(0, 0, 0, 0.4);
}

.toggle-track {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  height: 100%;
  padding: 0 10px;
}

.toggle-thumb {
  position: absolute;
  left: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  height: 28px;
  background: var(--surface-color);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.4s cubic-bezier(0.68, -0.15, 0.265, 1.35);
  box-shadow: 
    0 2px 8px rgba(0, 0, 0, 0.2),
    0 1px 2px rgba(0, 0, 0, 0.1);
  z-index: 2;
}

.theme-toggle.is-dark .toggle-thumb {
  left: calc(100% - 32px);
  background: linear-gradient(180deg, #ffd54f 0%, #ffb300 100%);
  box-shadow: 
    0 2px 8px rgba(255, 213, 79, 0.4),
    0 0 20px rgba(255, 213, 79, 0.3);
}

.toggle-thumb svg {
  width: 18px;
  height: 18px;
  color: #764ba2;
  transition: all 0.3s ease;
}

.theme-toggle.is-dark .toggle-thumb svg {
  color: #1a1a2e;
}

.icon-left,
.icon-right {
  width: 16px;
  height: 16px;
  opacity: 0.6;
  transition: all 0.3s ease;
  z-index: 1;
}

.icon-left {
  color: #ffd54f;
}

.icon-right {
  color: #fff;
}

.theme-toggle:hover {
  transform: scale(1.05);
}

.theme-toggle:hover .toggle-thumb {
  box-shadow: 
    0 4px 12px rgba(0, 0, 0, 0.25),
    0 2px 4px rgba(0, 0, 0, 0.15);
}

.theme-toggle.is-dark:hover .toggle-thumb {
  box-shadow: 
    0 4px 16px rgba(255, 213, 79, 0.5),
    0 0 30px rgba(255, 213, 79, 0.4);
}

.theme-toggle:active {
  transform: scale(0.98);
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  background: var(--surface-color);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  padding: 0 12px;
  min-width: 220px;
  height: 40px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.search-box:hover {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
}

.search-box:focus-within {
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
}

.search-box input {
  flex: 1;
  border: none;
  background: transparent;
  padding: 0 8px;
  font-size: 14px;
  color: var(--text-color);
  outline: none;
  min-width: 0;
}

.search-box input::placeholder {
  color: var(--muted-text);
}

.search-box .clear-btn {
  background: transparent;
  border: none;
  color: var(--muted-text);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.search-box .clear-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text-color);
}

.brand-hero {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
}

/* === Brand icon === */

.brand-icon {
  /* --- 1. CẤU TRÚC CHUNG (Giữ nguyên kích thước cho cả 2 theme) --- */
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 15px;
  border-radius: 50%;
  margin-top: 12px; /* Push icon down to align with main title line */
  
  /* Transition để hiệu ứng chuyển màu mượt mà */
  transition: all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);

  /* --- 2. LIGHT MODE (Mặc định: Đơn sắc, Không viền, Không Glow) --- */
  color: var(--title-color);     /* Dùng màu Navy đậm của tiêu đề cho đồng bộ */
  border: 2px solid transparent; /* Viền trong suốt (giữ chỗ) */
  box-shadow: none;              /* Không bóng */
  filter: none;                  /* Không phát sáng */
}

/* Dark mode styles được chuyển xuống <style> block riêng (không scoped) ở cuối file */

.brand-text {
  text-align: left;
}

/* Keyframes for hover effects only - main animation in main.scss */
@keyframes underline-grow {
  0% { transform: scaleX(0); }
  100% { transform: scaleX(1); }
}

@keyframes subtle-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

.brand-title {
  margin: 0;
  font-family: "Cinzel", serif;
  font-size: clamp(28px, 5vw, 42px);
  font-weight: 600;
  letter-spacing: 0.08em;
  position: relative;
  display: inline-block;
  
  /* Clean solid color - elegant & readable */
  color: var(--title-color);
  
  /* Smooth transitions for hover effects */
  transition: 
    letter-spacing 0.6s cubic-bezier(0.23, 1, 0.32, 1),
    color 0.4s ease;
}

/* Decorative underline with sweep animation */
.brand-title::after {
  content: "";
  position: absolute;
  bottom: -6px;
  left: 0;
  width: 100%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    #c9a962 10%,
    #d4af37 50%,
    #c9a962 90%,
    transparent 100%
  );
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.8s cubic-bezier(0.23, 1, 0.32, 1);
  opacity: 0.85;
}

/* Decorative sparkle icon - styles in main.scss for theme support */

/* Hover effects - elegant reveal */
.brand-hero:hover .brand-title {
  letter-spacing: 0.12em;
}

.brand-hero:hover .brand-title::after {
  transform: scaleX(1);
  transform-origin: left;
}

/* .brand-hero:hover .title-sparkle - styles in main.scss */

/* Base state cho animation - chỉ để tắt trong light mode */
.brand-icon.flicker-effect {
  animation: none;
}

/* =============================================
   RESPONSIVE BREAKPOINTS
   ============================================= */

/* Tablet: 768px - 1024px */
@media (max-width: 1024px) {
  .brand-icon {
    width: 48px;
    height: 48px;
    margin-right: 10px;
  }

  .brand-title {
    font-size: clamp(22px, 4vw, 32px) !important;
  }

  .search-box {
    min-width: 180px;
  }
}

/* NEW: Tablet range (768-1024px) — sidebar 240px persistent + hamburger always visible, edge-toggle hidden */
@media (min-width: 768px) and (max-width: 1024px) {
  .hamburger-btn {
    display: inline-flex;
  }

  .brand-hero {
    transform: scale(0.8);
    transform-origin: left center;
  }
}

/* Phone: <768px — sidebar becomes overlay, hamburger appears */
@media (max-width: 767px) {
  .hamburger-btn {
    display: inline-flex;
    flex-shrink: 0;
    width: 30px;
    height: 30px;
    min-width: 44px;
    min-height: 44px;
  }

  .hamburger-btn svg {
    width: 16px;
    height: 16px;
  }

  .content-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    min-height: 48px;
  }

  /* Explicit flex wrappers for header-left and header-actions (no display:contents) */
  .header-left,
  .header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .header-left {
    flex-shrink: 0;
  }

  .header-actions {
    flex: 1;
    margin-left: auto;
  }

  /* Mobile full-width search bar */
  .search-box {
    flex: 1;
    min-width: 0;
    height: 36px;
    padding: 0 10px;
    display: flex;
    align-items: center;
    gap: 6px;
    border-radius: 10px;
    border: 1px solid rgba(0, 0, 0, 0.12);
    background: var(--surface-color);
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .search-box:hover {
    border-color: var(--primary-color);
    box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  }

  .search-box:focus-within {
    border-color: var(--primary-color);
    box-shadow: 0 4px 12px rgba(214, 161, 93, 0.25);
  }

  .search-box input {
    flex: 1;
    border: none;
    background: transparent;
    padding: 0;
    font-size: 14px;
    color: var(--text-color);
    outline: none;
    min-width: 0;
  }

  .search-box input::placeholder {
    color: var(--muted-text);
  }

  .search-box .clear-btn {
    background: transparent;
    border: none;
    color: var(--muted-text);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .search-box .clear-btn:hover {
    background: rgba(0, 0, 0, 0.05);
    color: var(--text-color);
  }

  .theme-toggle {
    display: none;
  }

  .settings-btn {
    display: none;
  }

  .brand-hero {
    display: none;
  }

  .brand-icon {
    width: 44px;
    height: 44px;
    margin-right: 8px;
    margin-top: 8px;
  }

  .brand-title {
    font-size: clamp(18px, 4vw, 24px) !important;
  }
}

/* Small phone: <480px — compact layout */
@media (max-width: 480px) {
  .content-header {
    padding: 4px 12px;
    min-height: 44px;
    gap: 4px;
  }

  .search-box {
    width: 30px;
    height: 30px;
  }

  .hamburger-btn {
    width: 28px;
    height: 28px;
  }

  .settings-btn {
    width: 28px;
    height: 28px;
  }

  .settings-btn svg {
    width: 14px;
    height: 14px;
  }
}
</style>
