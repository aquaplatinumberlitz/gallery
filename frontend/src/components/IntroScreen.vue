<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { fetchLandingPages } from "../services/api";
import { ArrowRight } from "lucide-vue-next";

const props = defineProps<{
  visible: boolean;
  forceUrl?: string | null;
}>();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  (e: "enter"): void;
}>();

const introUrl = ref("");
const hasIntroContent = computed(() => !!introUrl.value);
const introFallbackMessage =
  "Welcome to Museum Art Gallery — intro page unavailable, you can enter the gallery now.";

const setVisible = (value: boolean) => emit("update:visible", value);

const isLunarNewYear = (): boolean => {
  try {
    const formatter = new Intl.DateTimeFormat("en-u-ca-chinese", {
      month: "numeric",
      day: "numeric",
    });
    const parts = formatter.formatToParts(new Date());
    const month = Number(parts.find((p) => p.type === "month")?.value);
    const day = Number(parts.find((p) => p.type === "day")?.value);
    const isYearEnd = month === 12 && day >= 30;
    const isNewYear = month === 1 && day <= 3;
    return isYearEnd || isNewYear;
  } catch {
    return false;
  }
};

const isBirthday = (): boolean => {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-based
  const day = now.getDate();
  return month === 9 && day === 3;
};

const isChristmas = (): boolean => {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-based
  const day = now.getDate();
  return month === 12 && (day === 24 || day === 25);
};

const pickIntroPage = (pages: string[]): string | undefined => {
  const lower = pages.map((p) => p.toLowerCase());
  const findBySlug = (slug: string) => {
    const idx = lower.findIndex((p) => p.includes(slug));
    return idx >= 0 ? pages[idx] : undefined;
  };

  const birthdayPage = findBySlug("/landpage/birthday/");
  const christmasPage = findBySlug("/landpage/noel/");
  const lunarPage = findBySlug("/landpage/lunar_newyear/");

  if (isBirthday() && birthdayPage) return birthdayPage;
  if (isChristmas() && christmasPage) return christmasPage;
  if (isLunarNewYear() && lunarPage) return lunarPage;

  if (pages.length > 0) {
    return pages[Math.floor(Math.random() * pages.length)];
  }
  return undefined;
};

const loadIntro = async () => {
  if (!props.visible) return;

  if (props.forceUrl) {
    introUrl.value = props.forceUrl;
    return;
  }

  const savedMode = localStorage.getItem("intro_mode");
  const savedTheme = localStorage.getItem("intro_theme");

  if (savedMode === "disabled") {
    setVisible(false);
    return;
  }

  if (savedMode === "manual" && savedTheme) {
    introUrl.value = savedTheme;
    return;
  }

  try {
    const pages = await fetchLandingPages();
    const picked = pickIntroPage(pages || []);
    if (picked) {
      introUrl.value = picked;
      return;
    }
  } catch {
    // ignore and fall through to close
  }

  setVisible(false);
};

const enterApp = () => {
  setVisible(false);
  emit("enter");
};

watch(
  () => props.forceUrl,
  (url) => {
    if (url) {
      introUrl.value = url;
      setVisible(true);
    }
  }
);

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      loadIntro();
    }
  }
);

onMounted(() => {
  if (props.visible) {
    loadIntro();
  }
});
</script>

<template>
  <div v-if="visible" class="intro-screen">
    <iframe
      v-if="hasIntroContent"
      :src="introUrl"
      class="intro-iframe"
      title="Intro"
    ></iframe>
    <div v-else class="intro-fallback">
      <p class="fallback-text">{{ introFallbackMessage }}</p>
    </div>
    <div class="enter-overlay">
      <button 
        class="enter-btn" 
        @click="enterApp"
        autofocus
      >
        <span class="btn-text">ENTER GALLERY</span>
        <span class="btn-icon"><ArrowRight :size="16" /></span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.intro-screen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: var(--gallery-lightbox-bg, #000);
  display: flex;
  flex-direction: column;
}

.intro-iframe {
  flex: 1;
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}

.enter-overlay {
  position: absolute;
  bottom: 80px;
  left: 0;
  width: 100%;
  display: flex;
  justify-content: center;
  pointer-events: none;
}

/* CSS Custom Properties for animated gradient */
@property --gradient-angle {
  syntax: "<angle>";
  initial-value: 0deg;
  inherits: false;
}

@keyframes rotate-gradient {
  0% { --gradient-angle: 0deg; }
  100% { --gradient-angle: 360deg; }
}

@keyframes subtle-pulse {
  0%, 100% { 
    box-shadow: 
      0 4px 20px rgba(180, 150, 80, 0.15),
      0 8px 40px rgba(180, 150, 80, 0.08),
      inset 0 1px 0 rgba(255, 255, 255, 0.9);
  }
  50% { 
    box-shadow: 
      0 6px 30px rgba(180, 150, 80, 0.25),
      0 12px 50px rgba(180, 150, 80, 0.12),
      inset 0 1px 0 rgba(255, 255, 255, 0.95);
  }
}

@keyframes shimmer-gold {
  0% { background-position: -200% center; }
  100% { background-position: 200% center; }
}

.enter-btn {
  pointer-events: auto;
  position: relative;
  
  /* Elegant transparent/frosted glass effect for light background */
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.95) 0%,
    rgba(255, 252, 245, 0.9) 50%,
    rgba(255, 255, 255, 0.95) 100%
  );
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  
  /* Subtle gold border */
  border: 2px solid rgba(180, 150, 80, 0.4);
  
  /* Dark text for readability on light background */
  color: #2c2c2c;
  padding: 22px 56px;
  font-family: "Cinzel", serif;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.4em;
  text-transform: uppercase;
  border-radius: 0; /* Sharp edges - museum aesthetic */
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 20px;
  transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  overflow: hidden;
  
  /* Elegant soft shadow */
  box-shadow: 
    0 4px 20px rgba(180, 150, 80, 0.15),
    0 8px 40px rgba(180, 150, 80, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  
  animation: subtle-pulse 4s ease-in-out infinite;
}

/* Animated gold border line */
.enter-btn::before {
  content: "";
  position: absolute;
  inset: -2px;
  padding: 2px;
  background: conic-gradient(
    from var(--gradient-angle),
    #c9a962 0%,
    #e8d5a3 20%,
    #b8956e 40%,
    #d4b896 60%,
    #c9a962 80%,
    #e8d5a3 100%
  );
  -webkit-mask: 
    linear-gradient(#fff 0 0) content-box, 
    linear-gradient(#fff 0 0);
  mask: 
    linear-gradient(#fff 0 0) content-box, 
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  animation: rotate-gradient 6s linear infinite;
  opacity: 0.6;
  z-index: 0;
  transition: opacity 0.5s ease;
}

/* Text with subtle gold shimmer */
.btn-text {
  position: relative;
  z-index: 2;
  background: linear-gradient(
    90deg,
    #1a1a1a 0%,
    #3d3d3d 20%,
    #8b7355 50%,
    #3d3d3d 80%,
    #1a1a1a 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer-gold 5s ease-in-out infinite;
}

.btn-icon {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: #8b7355;
  transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
  background: transparent;
  width: auto;
  height: auto;
  border-radius: 0;
}

/* Hover: Transform to gold filled button */
.enter-btn:hover {
  background: linear-gradient(
    135deg,
    #c9a962 0%,
    #d4b896 30%,
    #c9a962 70%,
    #b8956e 100%
  );
  border-color: #b8956e;
  color: #ffffff;
  transform: translateY(-3px);
  box-shadow: 
    0 8px 30px rgba(180, 150, 80, 0.35),
    0 15px 50px rgba(180, 150, 80, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
  animation: none;
}

.enter-btn:hover::before {
  opacity: 0;
}

.enter-btn:hover .btn-text {
  background: linear-gradient(
    90deg,
    #ffffff 0%,
    #fff8e7 50%,
    #ffffff 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer-gold 2s ease-in-out infinite;
}

.enter-btn:hover .btn-icon {
  transform: translateX(8px);
  color: #ffffff;
}

/* Shine sweep effect */
.enter-btn::after {
  content: "";
  position: absolute;
  top: -50%;
  left: -100%;
  width: 60%;
  height: 200%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.4),
    rgba(255, 255, 255, 0.6),
    transparent
  );
  transform: skewX(-25deg);
  transition: left 0.7s ease-in-out;
  z-index: 1;
}

.enter-btn:hover::after {
  left: 150%;
}

/* Active/Click state */
.enter-btn:active {
  transform: translateY(-1px);
  box-shadow: 
    0 4px 15px rgba(180, 150, 80, 0.3),
    0 8px 30px rgba(180, 150, 80, 0.15),
    inset 0 2px 4px rgba(0, 0, 0, 0.1);
}

/* Focus state for accessibility */
.enter-btn:focus-visible {
  outline: 2px solid #c9a962;
  outline-offset: 4px;
}

.intro-fallback {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--gallery-text-inverse, #ffffff);
  font-size: 16px;
  padding: 24px;
  background: radial-gradient(circle at center, rgba(255, 255, 255, 0.06), rgba(0, 0, 0, 0.9));
}

.fallback-text {
  max-width: 520px;
  text-align: center;
  line-height: 1.5;
  letter-spacing: 0.02em;
  margin: 0;
}
</style>
