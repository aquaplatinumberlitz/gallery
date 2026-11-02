<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useLandingPagesQuery } from "../composables/useLandingPagesQuery";
import { LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY } from "../utils/lightbox";
import { AlertTriangle, ArrowUpRight, Trash2 } from "lucide-vue-next";
import { useCatalogResetMutation } from "@/composables/admin/useCatalogResetMutation";
import Button from "@/components/ui/Button.vue";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Field, FieldDescription, FieldGroup, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    canResetCatalogDatabase?: boolean;
  }>(),
  {
    canResetCatalogDatabase: true,
  },
);

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
const resetConfirmPhrase = "RESET CATALOG DATABASE";
const resetConfirmInput = ref("");
const landingPagesQuery = useLandingPagesQuery();
const availableThemes = computed(() => (landingPagesQuery.data.value ?? []).map((page) => page.url));
const isLoadingThemes = computed(() => landingPagesQuery.isLoading.value);
const canSubmitReset = computed(() => resetConfirmInput.value === resetConfirmPhrase);
const resetMutation = useCatalogResetMutation();

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
  introMode.value = isIntroMode(savedMode) ? savedMode : "auto";

  const savedTheme = localStorage.getItem("intro_theme");
  selectedTheme.value = savedTheme || availableThemes.value[0] || "";

  alwaysLoadOriginal.value = localStorage.getItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY) === "true";
};

const saveSettings = () => {
  localStorage.setItem("intro_mode", introMode.value);
  if (selectedTheme.value) {
    localStorage.setItem("intro_theme", selectedTheme.value);
  }
  localStorage.setItem(LIGHTBOX_ALWAYS_LOAD_ORIGINAL_KEY, String(alwaysLoadOriginal.value));
};

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      loadSettings();
    }
  },
  { immediate: true },
);

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

const optionCardClass = (active: boolean) =>
  cn(
    "group relative flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card/80 p-4 shadow-sm transition-all duration-200 ease-[cubic-bezier(0.32,0.72,0,1)] hover:-translate-y-0.5 hover:border-primary/35 hover:bg-accent/40",
    active && "border-primary/60 bg-accent/60 shadow-sm",
  );

const optionMarkClass = (active: boolean) =>
  cn(
    "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-border bg-background transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
    active && "border-primary bg-primary/15 shadow-[0_0_0_4px_hsl(var(--primary)/0.10)]",
  );

function onOpenChange(open: boolean) {
  if (!open) {
    // Clear the reset input so it can't be accidentally triggered on re-open
    resetConfirmInput.value = "";
    emit("close");
  }
}

async function handleResetCatalog() {
  if (!canSubmitReset.value || resetMutation.isPending.value) return;
  try {
    await resetMutation.mutateAsync(resetConfirmInput.value);
    resetConfirmInput.value = "";
    emit("close");
  } catch {
    // Toast handled by mutation onError.
  }
}
</script>

<template>
  <Dialog :open="isOpen" @update:open="onOpenChange">
    <DialogContent
      class="settings-dialog max-h-[min(92dvh,760px)] gap-0 overflow-hidden border-border bg-background p-0 shadow-xl sm:max-w-[620px] sm:rounded-2xl"
    >
      <DialogHeader class="settings-dialog-header border-b border-border bg-muted/40 px-5 py-4 text-left sm:px-6">
        <div class="flex items-start justify-between gap-4 pr-9">
          <div class="flex min-w-0 flex-col gap-0.5">
            <DialogTitle class="text-base font-semibold leading-tight tracking-tight text-foreground">
              Settings
            </DialogTitle>
            <DialogDescription class="text-xs text-muted-foreground">
              Configure gallery intro and viewer settings
            </DialogDescription>
          </div>
        </div>
      </DialogHeader>

      <div
        class="settings-dialog-body flex max-h-[calc(min(92dvh,760px)-74px)] flex-col gap-4 overflow-y-auto px-4 py-4 sm:px-5"
      >
        <FieldSet class="gap-4 rounded-xl border border-border bg-card/65 p-4 shadow-sm">
          <div class="flex flex-col gap-1">
            <FieldLegend class="mb-0 text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/65">
              Landing Page
            </FieldLegend>
            <FieldDescription class="text-xs text-muted-foreground">
              Configure the landing page shown before entering the main gallery.
            </FieldDescription>
          </div>

          <FieldGroup class="gap-3">
            <label :class="optionCardClass(introMode === 'auto')">
              <input
                id="settings-intro-auto"
                v-model="introMode"
                type="radio"
                name="intro-mode"
                value="auto"
                class="sr-only"
              />
              <span :class="optionMarkClass(introMode === 'auto')" aria-hidden="true">
                <span v-if="introMode === 'auto'" class="size-2 rounded-full bg-primary"></span>
              </span>
              <span class="flex min-w-0 flex-col gap-1">
                <span class="text-sm font-semibold text-foreground">Automatic</span>
                <span class="text-xs text-muted-foreground">Random themes, prioritizing holidays</span>
              </span>
            </label>

            <label :class="optionCardClass(introMode === 'disabled')">
              <input
                id="settings-intro-disabled"
                v-model="introMode"
                type="radio"
                name="intro-mode"
                value="disabled"
                class="sr-only"
              />
              <span :class="optionMarkClass(introMode === 'disabled')" aria-hidden="true">
                <span v-if="introMode === 'disabled'" class="size-2 rounded-full bg-primary"></span>
              </span>
              <span class="flex min-w-0 flex-col gap-1">
                <span class="text-sm font-semibold text-foreground">Disabled</span>
                <span class="text-xs text-muted-foreground">Skip intro and enter gallery directly</span>
              </span>
            </label>

            <label :class="optionCardClass(introMode === 'manual')">
              <input
                id="settings-intro-manual"
                v-model="introMode"
                type="radio"
                name="intro-mode"
                value="manual"
                class="sr-only"
              />
              <span :class="optionMarkClass(introMode === 'manual')" aria-hidden="true">
                <span v-if="introMode === 'manual'" class="size-2 rounded-full bg-primary"></span>
              </span>
              <span class="flex min-w-0 flex-col gap-1">
                <span class="text-sm font-semibold text-foreground">Manual Selection</span>
                <span class="text-xs text-muted-foreground">Always show a specific theme</span>
              </span>
            </label>
          </FieldGroup>

          <Transition
            enter-active-class="transition-all duration-200 ease-out"
            enter-from-class="opacity-0 -translate-y-1"
            leave-active-class="transition-all duration-150 ease-in"
            leave-to-class="opacity-0 -translate-y-1"
          >
            <div
              v-if="introMode === 'manual'"
              class="rounded-xl border border-border bg-muted/60 p-4"
            >
              <div class="flex flex-col gap-3">
                <div class="flex flex-col gap-1">
                  <span class="text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/65">Theme Override</span>
                  <span class="text-xs text-muted-foreground">Preview before applying it to launch.</span>
                </div>
                <div v-if="isLoadingThemes" class="text-sm text-muted-foreground">Loading themes...</div>
                <div v-else class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <div class="flex flex-col gap-1">
                    <label for="theme-select" class="sr-only">Intro theme</label>
                    <Select v-model="selectedTheme">
                      <SelectTrigger id="theme-select" class="h-11 rounded-lg bg-background/80 px-4 shadow-sm">
                        <SelectValue placeholder="Select intro theme" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem v-for="theme in availableThemes" :key="theme" :value="theme">
                            {{ formatThemeName(theme) }}
                          </SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    class="h-11 rounded-lg px-5 transition-all duration-200 ease-[cubic-bezier(0.32,0.72,0,1)] hover:-translate-y-0.5"
                    @click="handlePreview"
                  >
                    Preview
                    <ArrowUpRight data-icon="inline-end" />
                  </Button>
                </div>
              </div>
            </div>
          </Transition>
        </FieldSet>

        <FieldSet class="gap-4 rounded-xl border border-border bg-card/65 p-4 shadow-sm">
          <div class="flex flex-col gap-1">
            <FieldLegend class="mb-0 text-[11px] font-bold uppercase tracking-[0.14em] text-foreground/65">
              Viewer Images
            </FieldLegend>
            <FieldDescription class="text-xs text-muted-foreground">Control the image source used inside the lightbox.</FieldDescription>
          </div>

          <!-- Switch replaces checkbox — binary setting, not a selection from a list -->
          <div class="flex items-center justify-between gap-4 rounded-xl border border-border bg-card/80 px-4 py-3">
            <div class="flex min-w-0 flex-col gap-0.5">
              <span class="text-sm font-semibold text-foreground">Always load original</span>
              <span class="text-xs text-muted-foreground">Use source files immediately in the viewer</span>
            </div>
            <Switch
              id="settings-always-load-original"
              :checked="alwaysLoadOriginal"
              aria-label="Always load original image"
              @update:checked="alwaysLoadOriginal = $event"
            />
          </div>
        </FieldSet>

        <Alert
          v-if="props.canResetCatalogDatabase"
          variant="destructive"
          class="rounded-xl border-destructive/60 bg-destructive/8 p-4"
        >
          <div class="flex min-w-0 flex-1 flex-col gap-4">
            <div class="flex items-start gap-2.5">
              <AlertTriangle class="mt-px size-[18px] shrink-0 text-destructive" aria-hidden="true" />
              <div class="flex flex-col gap-1">
                <AlertTitle class="mb-0 text-xs font-bold leading-4 uppercase tracking-[0.14em]">
                  Danger Zone
                </AlertTitle>
                <AlertDescription class="text-xs text-muted-foreground">
                  Reset app data removes library registrations, imported catalog data, extracted metadata, thumbnails,
                  previews, job history, and local gallery state. Source photos and videos are not deleted.
                  Use this before handing the app to another user. Embedded metadata remains in any source files you
                  keep or share.
                </AlertDescription>
              </div>
            </div>

            <Field class="gap-2">
              <label for="catalog-reset-confirm" class="text-xs font-medium text-muted-foreground">
                Type <strong class="font-bold text-destructive">{{ resetConfirmPhrase }}</strong> to confirm
              </label>
              <Input
                id="catalog-reset-confirm"
                v-model="resetConfirmInput"
                autocomplete="new-password"
                data-form-type="other"
                spellcheck="false"
                :disabled="resetMutation.isPending.value"
                class="h-11 rounded-lg bg-background/80"
              />
            </Field>

            <Button
              variant="destructive"
              class="h-11 w-full rounded-lg transition-opacity"
              :class="{ 'opacity-40': !canSubmitReset && !resetMutation.isPending.value }"
              :disabled="!canSubmitReset || resetMutation.isPending.value"
              @click="handleResetCatalog"
            >
              <Trash2 data-icon="inline-start" />
              {{ resetMutation.isPending.value ? "Resetting..." : "Reset app data" }}
            </Button>
          </div>
        </Alert>
      </div>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
@media (max-width: 639px) {
  .settings-dialog {
    padding: 0;
  }

  .settings-dialog-header,
  .settings-dialog-body {
    padding-inline: 1rem;
  }
}
</style>
