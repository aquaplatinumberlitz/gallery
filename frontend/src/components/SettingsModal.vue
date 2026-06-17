<script setup lang="ts">
import { computed, ref, onMounted, watch } from "vue";
import { useLandingPagesLiveQuery } from "../db/composables/useLandingPagesLiveQuery";
import { LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY } from "../utils/lightbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "preview", url: string): void;
}>();

const INTRO_MODES = ["auto", "disabled", "manual"] as const;
type IntroMode = (typeof INTRO_MODES)[number];

const isIntroMode = (value: string | null): value is IntroMode =>
  value !== null && (INTRO_MODES as readonly string[]).includes(value);

const introMode = ref<IntroMode>("auto");
const selectedTheme = ref("");
const alwaysLoadOriginal = ref(false);
const landingPagesQuery = useLandingPagesLiveQuery();
const availableThemes = computed(() => (landingPagesQuery.data.value ?? []).map((page) => page.url));
const isLoadingThemes = computed(() => landingPagesQuery.isLoading.value);

const formatThemeName = (path: string) => {
  const parts = path.split("/").filter((p) => p && p !== "landpage" && !p.endsWith(".html"));
  if (parts.length > 0) {
    const name = parts[0];
    return name
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  }
  return "Unknown Theme";
};

const loadSettings = () => {
  const savedMode = localStorage.getItem("intro_mode");
  if (isIntroMode(savedMode)) {
    introMode.value = savedMode;
  }

  const savedTheme = localStorage.getItem("intro_theme");
  if (savedTheme) {
    selectedTheme.value = savedTheme;
  }

  alwaysLoadOriginal.value = localStorage.getItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY) === "true";
};

const saveSettings = () => {
  localStorage.setItem("intro_mode", introMode.value);
  if (selectedTheme.value) {
    localStorage.setItem("intro_theme", selectedTheme.value);
  }
  localStorage.setItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY, String(alwaysLoadOriginal.value));
};

onMounted(() => {
  loadSettings();
});

watch([introMode, selectedTheme, alwaysLoadOriginal], () => {
  saveSettings();
});

watch(
  availableThemes,
  (pages) => {
    if (!selectedTheme.value && pages.length > 0) {
      selectedTheme.value = pages[0];
    }
  },
  { immediate: true },
);

watch(landingPagesQuery.isError, (isError) => {
  if (isError) {
    console.error("Failed to load themes");
  }
});

const handlePreview = () => {
  if (selectedTheme.value) {
    emit("preview", selectedTheme.value);
  }
};

function onOpenChange(open: boolean) {
  if (!open) {
    emit("close");
  }
}
</script>

<template>
  <Dialog :open="isOpen" @update:open="onOpenChange">
    <DialogContent class="sm:max-w-[400px]">
      <DialogHeader>
        <DialogTitle class="font-[Cinzel] tracking-wider uppercase text-base">Settings</DialogTitle>
        <DialogDescription class="sr-only">Configure gallery intro and viewer settings</DialogDescription>
      </DialogHeader>

      <div class="space-y-6">
        <section class="space-y-4">
          <h3 class="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Intro Screen</h3>

          <div class="flex flex-col gap-2">
            <label
              class="flex items-center rounded-md border px-4 py-3 cursor-pointer transition-colors hover:bg-accent hover:text-accent-foreground"
              :class="{ 'border-primary bg-accent text-accent-foreground': introMode === 'auto' }"
            >
              <input type="radio" v-model="introMode" value="auto" class="sr-only" />
              <div class="flex flex-col gap-0.5">
                <span class="text-sm font-medium">Automatic</span>
                <span class="text-xs text-muted-foreground">Random themes, prioritizing holidays</span>
              </div>
            </label>

            <label
              class="flex items-center rounded-md border px-4 py-3 cursor-pointer transition-colors hover:bg-accent hover:text-accent-foreground"
              :class="{ 'border-primary bg-accent text-accent-foreground': introMode === 'disabled' }"
            >
              <input type="radio" v-model="introMode" value="disabled" class="sr-only" />
              <div class="flex flex-col gap-0.5">
                <span class="text-sm font-medium">Disabled</span>
                <span class="text-xs text-muted-foreground">Skip intro and enter gallery directly</span>
              </div>
            </label>

            <label
              class="flex items-center rounded-md border px-4 py-3 cursor-pointer transition-colors hover:bg-accent hover:text-accent-foreground"
              :class="{ 'border-primary bg-accent text-accent-foreground': introMode === 'manual' }"
            >
              <input type="radio" v-model="introMode" value="manual" class="sr-only" />
              <div class="flex flex-col gap-0.5">
                <span class="text-sm font-medium">Manual Selection</span>
                <span class="text-xs text-muted-foreground">Always show a specific theme</span>
              </div>
            </label>
          </div>

          <div v-if="introMode === 'manual'" class="space-y-3 pt-3 border-t">
            <div v-if="isLoadingThemes" class="text-sm text-muted-foreground">Loading themes...</div>
            <div v-else class="flex flex-col gap-3">
              <select
                v-model="selectedTheme"
                class="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring cursor-pointer"
              >
                <option v-for="theme in availableThemes" :key="theme" :value="theme">
                  {{ formatThemeName(theme) }}
                </option>
              </select>
              <button
                class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring h-9 px-4 py-2 border border-primary text-primary hover:bg-primary hover:text-primary-foreground uppercase tracking-wider"
                @click="handlePreview"
              >
                Preview
              </button>
            </div>
          </div>
        </section>

        <section class="space-y-4">
          <h3 class="text-xs uppercase tracking-wider text-muted-foreground font-semibold">Viewer Images</h3>

          <label
            class="flex items-center rounded-md border px-4 py-3 cursor-pointer transition-colors hover:bg-accent hover:text-accent-foreground"
            :class="{ 'border-primary bg-accent text-accent-foreground': alwaysLoadOriginal }"
          >
            <input type="checkbox" v-model="alwaysLoadOriginal" class="sr-only" />
            <div class="flex flex-col gap-0.5">
              <span class="text-sm font-medium">Always load original</span>
              <span class="text-xs text-muted-foreground">Use source files immediately in the viewer</span>
            </div>
          </label>
        </section>
      </div>
    </DialogContent>
  </Dialog>
</template>
