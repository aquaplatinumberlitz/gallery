<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import { useLibraryMutations } from "@/composables/admin/useLibraryMutations";
import { GalleryAPIError } from "@/services/api";
import type { LibraryUpdateRequest, LibraryValidationResult, RegisteredLibrary } from "@/types";

const props = defineProps<{
  library?: RegisteredLibrary | null;
  libraries?: RegisteredLibrary[];
}>();
const emit = defineEmits<{ saved: [library: RegisteredLibrary]; cancel: [] }>();

const name = ref("");
const importPaths = ref<string[]>([""]);
const exclusionPatterns = ref<string[]>([]);
const serverError = ref("");
const validation = ref<LibraryValidationResult | null>(null);
const submitAndScan = ref(false);
const { createMutation, updateMutation, validateMutation, scanMutation } = useLibraryMutations();

watch(
  () => props.library,
  (library) => {
    name.value = library?.name ?? "";
    importPaths.value = library?.import_paths.map((item) => item.path) ?? [""];
    exclusionPatterns.value = [...(library?.exclusion_patterns ?? [])];
    serverError.value = "";
    validation.value = null;
  },
  { immediate: true },
);

const pending = computed(
  () =>
    createMutation.isPending.value ||
    updateMutation.isPending.value ||
    validateMutation.isPending.value ||
    scanMutation.isPending.value,
);

function cleanValue(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length >= 2 && trimmed[0] === trimmed.at(-1) && (trimmed[0] === '"' || trimmed[0] === "'")) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

const normalizedPaths = computed(() => importPaths.value.map(cleanValue).filter(Boolean));
const normalizedPatterns = computed(() => exclusionPatterns.value.map(cleanValue).filter(Boolean));
const clientErrors = computed(() => {
  const errors: string[] = [];
  if (normalizedPaths.value.length === 0) errors.push("Add at least one import path.");
  if (normalizedPaths.value.some((path) => !path.startsWith("/") && !/^[A-Za-z]:[\\/]/.test(path))) {
    errors.push("Every import path must be absolute.");
  }
  if (new Set(normalizedPaths.value).size !== normalizedPaths.value.length) errors.push("Import paths must be unique.");
  if (normalizedPatterns.value.length > 128) errors.push("Use no more than 128 exclusion patterns.");
  if (new Set(normalizedPatterns.value).size !== normalizedPatterns.value.length) {
    errors.push("Exclusion patterns must be unique.");
  }
  return errors;
});

const overlapWarnings = computed(() => {
  const warnings: string[] = [];
  const normalize = (value: string) => value.replace(/\\/g, "/").replace(/\/+$/, "");
  for (const path of normalizedPaths.value) {
    const candidate = normalize(path);
    for (const library of props.libraries ?? []) {
      if (library.id === props.library?.id) continue;
      for (const item of library.import_paths) {
        const existing = normalize(item.path);
        if (candidate === existing || candidate.startsWith(`${existing}/`) || existing.startsWith(`${candidate}/`)) {
          warnings.push(`${path} overlaps ${library.name}: ${item.path}`);
        }
      }
    }
  }
  return warnings;
});

function addPath() {
  importPaths.value.push("");
}
function removePath(index: number) {
  if (importPaths.value.length > 1) importPaths.value.splice(index, 1);
}
function movePath(index: number, offset: number) {
  const target = index + offset;
  if (target < 0 || target >= importPaths.value.length) return;
  [importPaths.value[index], importPaths.value[target]] = [importPaths.value[target], importPaths.value[index]];
}
function addPattern() {
  exclusionPatterns.value.push("");
}

function payload(): LibraryUpdateRequest {
  return {
    name: cleanValue(name.value),
    import_paths: normalizedPaths.value,
    exclusion_patterns: normalizedPatterns.value,
  };
}

function describeError(error: unknown): string {
  return error instanceof GalleryAPIError ? `${error.userMessage}. ${error.suggestion}` : "The request failed.";
}

async function validate(): Promise<boolean> {
  serverError.value = "";
  validation.value = null;
  if (clientErrors.value.length > 0) return false;
  try {
    validation.value = await validateMutation.mutateAsync({ id: props.library?.id, payload: payload() });
    return validation.value.is_valid;
  } catch (error) {
    serverError.value = describeError(error);
    return false;
  }
}

async function submit(scanAfterCreate = false) {
  submitAndScan.value = scanAfterCreate;
  if (!(await validate())) return;
  try {
    const saved = props.library
      ? await updateMutation.mutateAsync({ id: props.library.id, payload: payload() })
      : await createMutation.mutateAsync(payload());
    if (scanAfterCreate) await scanMutation.mutateAsync(saved.id);
    emit("saved", saved);
  } catch (error) {
    serverError.value = describeError(error);
  } finally {
    submitAndScan.value = false;
  }
}
</script>

<template>
  <form class="space-y-5" @submit.prevent="submit(false)">
    <div class="space-y-2">
      <label class="text-sm font-medium" for="library-name">Display name</label>
      <Input id="library-name" v-model="name" placeholder="Derived from the first path when empty" />
    </div>

    <fieldset class="space-y-3">
      <div class="flex items-center justify-between gap-3">
        <legend class="text-sm font-medium">Import paths</legend>
        <Button type="button" variant="outline" size="sm" @click="addPath"><Plus /> Add path</Button>
      </div>
      <div v-for="(_path, index) in importPaths" :key="index" class="flex items-center gap-2">
        <Input v-model="importPaths[index]" class="font-mono text-xs" placeholder="/absolute/path/to/library" />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          :disabled="index === 0"
          aria-label="Move path up"
          @click="movePath(index, -1)"
        >
          <ArrowUp />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          :disabled="index === importPaths.length - 1"
          aria-label="Move path down"
          @click="movePath(index, 1)"
        >
          <ArrowDown />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          :disabled="importPaths.length === 1"
          aria-label="Remove path"
          @click="removePath(index)"
        >
          <Trash2 />
        </Button>
      </div>
    </fieldset>

    <fieldset class="space-y-3">
      <div class="flex items-center justify-between gap-3">
        <legend class="text-sm font-medium">Exclusion patterns</legend>
        <Button type="button" variant="outline" size="sm" @click="addPattern"><Plus /> Add pattern</Button>
      </div>
      <p class="text-xs text-muted-foreground">Relative glob patterns, for example <code>**/.cache/**</code>.</p>
      <div v-for="(_pattern, index) in exclusionPatterns" :key="index" class="flex items-center gap-2">
        <Input v-model="exclusionPatterns[index]" class="font-mono text-xs" placeholder="**/private/**" />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Remove pattern"
          @click="exclusionPatterns.splice(index, 1)"
        >
          <Trash2 />
        </Button>
      </div>
    </fieldset>

    <div v-if="clientErrors.length || overlapWarnings.length || validation || serverError" class="space-y-2 text-sm">
      <p v-for="error in clientErrors" :key="error" class="text-destructive">{{ error }}</p>
      <p v-for="warning in overlapWarnings" :key="warning" class="text-amber-700 dark:text-amber-400">{{ warning }}</p>
      <template v-if="validation">
        <p :class="validation.is_valid ? 'text-emerald-700 dark:text-emerald-400' : 'text-destructive'">
          {{ validation.is_valid ? "Server validation passed." : "Server validation found errors." }}
        </p>
        <p
          v-for="item in [...validation.import_paths, ...validation.exclusion_patterns].filter(
            (item) => !item.is_valid || item.warnings.length,
          )"
          :key="item.value"
          class="text-muted-foreground"
        >
          <span class="font-mono">{{ item.value }}</span
          >: {{ item.message || item.warnings.join(" ") }}
        </p>
      </template>
      <p v-if="serverError" class="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-destructive">
        {{ serverError }}
      </p>
    </div>

    <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <Button type="button" variant="ghost" :disabled="pending" @click="emit('cancel')">Cancel</Button>
      <Button type="button" variant="outline" :disabled="pending" @click="validate">Validate</Button>
      <Button v-if="!library" type="button" variant="secondary" :disabled="pending" @click="submit(true)">
        {{ submitAndScan && pending ? "Adding…" : "Add and scan" }}
      </Button>
      <Button type="submit" :disabled="pending">
        {{ pending ? "Saving…" : library ? "Save changes" : "Add library" }}
      </Button>
    </div>
  </form>
</template>
