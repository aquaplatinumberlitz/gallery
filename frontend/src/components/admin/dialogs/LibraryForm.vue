<script setup lang="ts">
import { computed, ref, shallowRef, watch } from "vue";
import { ArrowDown, ArrowUp, CircleCheck, Info, Plus, TriangleAlert, Trash2 } from "lucide-vue-next";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import Button from "@/components/ui/Button.vue";
import { Checkbox } from "@/components/ui/checkbox";
import IconTooltipButton from "@/components/ui/IconTooltipButton.vue";
import Input from "@/components/ui/Input.vue";
import { Separator } from "@/components/ui/separator";
import { Field, FieldContent, FieldError, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
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
const warmEnabled = ref(true);
const serverError = ref("");
const validation = ref<LibraryValidationResult | null>(null);
const scanAfterAdd = shallowRef(true);
const { createMutation, updateMutation, validateMutation, scanMutation } = useLibraryMutations();

watch(
  () => props.library,
  (library) => {
    name.value = library?.name ?? "";
    importPaths.value = library?.import_paths.map((item) => item.path) ?? [""];
    exclusionPatterns.value = [...(library?.exclusion_patterns ?? [])];
    warmEnabled.value = library?.warm_enabled !== 0;
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

const submitLabel = computed(() => {
  if (validateMutation.isPending.value) return "Checking…";
  if (createMutation.isPending.value) return "Adding…";
  if (updateMutation.isPending.value) return "Saving…";
  if (scanMutation.isPending.value) return "Starting scan…";
  if (!props.library && scanAfterAdd.value) return "Add and update";
  return props.library ? "Save changes" : "Add library";
});

function cleanValue(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length >= 2 && trimmed[0] === trimmed.at(-1) && (trimmed[0] === '"' || trimmed[0] === "'")) {
    return trimmed.slice(1, -1).trim();
  }
  return trimmed;
}

const normalizedPaths = computed(() => importPaths.value.map(cleanValue).filter(Boolean));
const normalizedPatterns = computed(() => exclusionPatterns.value.map(cleanValue).filter(Boolean));
const normalizedPathRows = computed(() => importPaths.value.map(cleanValue));
const normalizedPatternRows = computed(() => exclusionPatterns.value.map(cleanValue));

interface RowIssue {
  message: string;
  tone: "error" | "warning" | "muted";
}

function duplicateValues(values: string[]): Set<string> {
  const counts = new Map<string, number>();
  for (const value of values.filter(Boolean)) counts.set(value, (counts.get(value) ?? 0) + 1);
  return new Set([...counts.entries()].filter(([, count]) => count > 1).map(([value]) => value));
}

function isAbsolutePath(value: string): boolean {
  return value.startsWith("/") || /^[A-Za-z]:[\\/]/.test(value);
}

const importPathErrors = computed(() => {
  const errors: string[] = [];
  if (normalizedPaths.value.length === 0) errors.push("Add at least one import path.");
  if (normalizedPaths.value.some((path) => !isAbsolutePath(path))) {
    errors.push("Every import path must be absolute.");
  }
  if (new Set(normalizedPaths.value).size !== normalizedPaths.value.length) errors.push("Folders must be unique.");
  return errors;
});
const exclusionPatternErrors = computed(() => {
  const errors: string[] = [];
  if (normalizedPatterns.value.length > 128) errors.push("Use no more than 128 exclusion patterns.");
  if (new Set(normalizedPatterns.value).size !== normalizedPatterns.value.length) {
    errors.push("Exclusion patterns must be unique.");
  }
  return errors;
});
const exclusionPatternGroupErrors = computed(() =>
  normalizedPatterns.value.length > 128 ? ["Use no more than 128 exclusion patterns."] : [],
);
const clientErrors = computed(() => [...importPathErrors.value, ...exclusionPatternErrors.value]);

function pathOverlapWarnings(path: string): string[] {
  const warnings: string[] = [];
  const normalize = (value: string) => value.replace(/\\/g, "/").replace(/\/+$/, "");
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
  return warnings;
}

const importPathValidationIssues = computed(
  () => validation.value?.import_paths.filter((item) => !item.is_valid || item.warnings.length) ?? [],
);
const exclusionPatternValidationIssues = computed(
  () => validation.value?.exclusion_patterns.filter((item) => !item.is_valid || item.warnings.length) ?? [],
);
const duplicatePathValues = computed(() => duplicateValues(normalizedPathRows.value));
const duplicatePatternValues = computed(() => duplicateValues(normalizedPatternRows.value));

const importPathRowIssues = computed(() =>
  normalizedPathRows.value.map((path) => {
    const issues: RowIssue[] = [];
    if (!path) {
      if (normalizedPaths.value.length === 0) issues.push({ message: "Folder path is required.", tone: "error" });
      return issues;
    }
    if (!isAbsolutePath(path)) issues.push({ message: "Use an absolute folder path.", tone: "error" });
    if (duplicatePathValues.value.has(path)) issues.push({ message: "This folder is duplicated.", tone: "error" });
    for (const warning of pathOverlapWarnings(path)) issues.push({ message: warning, tone: "warning" });
    for (const item of importPathValidationIssues.value.filter((issue) => issue.value === path)) {
      if (!item.is_valid && item.message) issues.push({ message: item.message, tone: "error" });
      for (const warning of item.warnings) issues.push({ message: warning, tone: "warning" });
    }
    return issues;
  }),
);

const exclusionPatternRowIssues = computed(() =>
  normalizedPatternRows.value.map((pattern) => {
    const issues: RowIssue[] = [];
    if (!pattern) return issues;
    if (duplicatePatternValues.value.has(pattern)) {
      issues.push({ message: "This exclusion pattern is duplicated.", tone: "error" });
    }
    for (const item of exclusionPatternValidationIssues.value.filter((issue) => issue.value === pattern)) {
      if (!item.is_valid && item.message) issues.push({ message: item.message, tone: "error" });
      for (const warning of item.warnings) issues.push({ message: warning, tone: "warning" });
    }
    return issues;
  }),
);

function rowIssueClass(issue: RowIssue): string | undefined {
  if (issue.tone === "warning") return "text-amber-700 dark:text-amber-400";
  if (issue.tone === "muted") return "text-muted-foreground";
  return undefined;
}

function importPathIssues(index: number): RowIssue[] {
  return importPathRowIssues.value[index] ?? [];
}

function exclusionPatternIssues(index: number): RowIssue[] {
  return exclusionPatternRowIssues.value[index] ?? [];
}

function hasRowError(issues: RowIssue[]): boolean {
  return issues.some((issue) => issue.tone === "error");
}

const validationHasIssues = computed(() => validation.value?.is_valid === false);

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
    warm_enabled: warmEnabled.value,
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

async function submit() {
  if (!(await validate())) return;
  try {
    const saved = props.library
      ? await updateMutation.mutateAsync({ id: props.library.id, payload: payload() })
      : await createMutation.mutateAsync(payload());
    if (!props.library && scanAfterAdd.value) await scanMutation.mutateAsync({ id: saved.id });
    emit("saved", saved);
  } catch (error) {
    serverError.value = describeError(error);
  }
}
</script>

<template>
  <form @submit.prevent="submit">
    <FieldGroup class="gap-6">
      <Field>
        <div class="flex items-center gap-2">
          <FieldLabel for="library-name">Display name</FieldLabel>
          <IconTooltipButton
            type="button"
            size="icon-sm"
            variant="ghost"
            class="-my-1 text-muted-foreground"
            label="Display name help"
            tooltip="Optional. Leave empty to use the first folder name."
          >
            <Info />
          </IconTooltipButton>
        </div>
        <Input id="library-name" v-model="name" placeholder="Derived from the first folder when empty" />
      </Field>

      <Separator />

      <FieldSet>
        <FieldLegend variant="label" class="flex items-center gap-2">
          Folders
          <IconTooltipButton
            type="button"
            size="icon-sm"
            variant="ghost"
            class="-my-1 text-muted-foreground"
            label="Folders help"
            tooltip="Use absolute paths. Folder order controls the import priority."
          >
            <Info />
          </IconTooltipButton>
        </FieldLegend>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="outline"
            size="sm"
            class="h-8 gap-1.5 self-start px-2.5 sm:self-auto"
            @click="addPath"
          >
            <Plus data-icon="inline-start" class="-ms-1 opacity-60" /> Add folder
          </Button>
        </div>
        <FieldGroup class="gap-3">
          <Field
            v-for="(_path, index) in importPaths"
            :key="index"
            :data-invalid="hasRowError(importPathIssues(index))"
          >
            <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
              <FieldLabel
                :for="`library-import-path-${index}`"
                class="pt-2 text-muted-foreground tabular-nums sm:w-20 sm:shrink-0"
              >
                Folder {{ index + 1 }}
              </FieldLabel>
              <FieldContent class="min-w-0 gap-2">
                <div class="flex min-w-0 items-center gap-2">
                  <Input
                    :id="`library-import-path-${index}`"
                    v-model="importPaths[index]"
                    class="min-w-0 flex-1 font-mono text-xs"
                    placeholder="/absolute/path/to/library"
                    :aria-invalid="hasRowError(importPathIssues(index))"
                  />
                  <div class="flex shrink-0 items-center gap-1">
                    <div class="flex items-center gap-0.5">
                      <IconTooltipButton
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        class="text-foreground"
                        :disabled="index === 0"
                        label="Move folder up"
                        @click="movePath(index, -1)"
                      >
                        <ArrowUp />
                      </IconTooltipButton>
                      <IconTooltipButton
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        class="text-foreground"
                        :disabled="index === importPaths.length - 1"
                        label="Move folder down"
                        @click="movePath(index, 1)"
                      >
                        <ArrowDown />
                      </IconTooltipButton>
                    </div>
                    <IconTooltipButton
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      class="text-destructive hover:text-destructive"
                      :disabled="importPaths.length === 1"
                      label="Remove folder"
                      @click="removePath(index)"
                    >
                      <Trash2 />
                    </IconTooltipButton>
                  </div>
                </div>
                <FieldError v-for="issue in importPathIssues(index)" :key="issue.message" :class="rowIssueClass(issue)">
                  {{ issue.message }}
                </FieldError>
              </FieldContent>
            </div>
          </Field>
        </FieldGroup>
      </FieldSet>

      <Separator />

      <FieldSet>
        <FieldLegend variant="label" class="flex items-center gap-2">
          Exclusion patterns
          <IconTooltipButton
            type="button"
            size="icon-sm"
            variant="ghost"
            class="-my-1 text-muted-foreground"
            label="Exclusion patterns help"
            tooltip="Relative glob patterns, for example **/.cache/**."
          >
            <Info />
          </IconTooltipButton>
        </FieldLegend>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="outline"
            size="sm"
            class="h-8 gap-1.5 self-start px-2.5 sm:self-auto"
            @click="addPattern"
          >
            <Plus data-icon="inline-start" class="-ms-1 opacity-60" /> Add pattern
          </Button>
        </div>
        <FieldGroup class="gap-3">
          <Field
            v-for="(_pattern, index) in exclusionPatterns"
            :key="index"
            :data-invalid="hasRowError(exclusionPatternIssues(index))"
          >
            <div class="flex flex-col gap-2 sm:flex-row sm:items-start">
              <FieldLabel
                :for="`library-exclusion-pattern-${index}`"
                class="pt-2 text-muted-foreground tabular-nums sm:w-32 sm:shrink-0"
              >
                Pattern {{ index + 1 }}
              </FieldLabel>
              <FieldContent class="min-w-0 gap-2">
                <div class="flex min-w-0 items-center gap-2">
                  <Input
                    :id="`library-exclusion-pattern-${index}`"
                    v-model="exclusionPatterns[index]"
                    class="min-w-0 flex-1 font-mono text-xs"
                    placeholder="**/private/**"
                    :aria-invalid="hasRowError(exclusionPatternIssues(index))"
                  />
                  <IconTooltipButton
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    class="text-destructive hover:text-destructive"
                    label="Remove pattern"
                    @click="exclusionPatterns.splice(index, 1)"
                  >
                    <Trash2 />
                  </IconTooltipButton>
                </div>
                <FieldError
                  v-for="issue in exclusionPatternIssues(index)"
                  :key="issue.message"
                  :class="rowIssueClass(issue)"
                >
                  {{ issue.message }}
                </FieldError>
              </FieldContent>
            </div>
          </Field>
        </FieldGroup>
        <FieldError v-for="error in exclusionPatternGroupErrors" :key="error">{{ error }}</FieldError>
      </FieldSet>

      <Separator />

      <FieldSet>
        <FieldLegend variant="label">Processing options</FieldLegend>
        <FieldGroup class="gap-3">
          <Field>
            <label
              for="library-warm-enabled"
              class="flex cursor-pointer items-start justify-between gap-4 rounded-md border border-border bg-muted/30 p-3 transition-colors hover:bg-muted/50 has-[[aria-checked=true]]:border-primary/40 has-[[aria-checked=true]]:bg-primary/5"
            >
              <span class="min-w-0">
                <span class="block text-sm font-medium text-foreground">Prepare image cache in background</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">
                  Creates thumbnails and previews after updates. This uses storage and CPU in the background.
                </span>
              </span>
              <Checkbox id="library-warm-enabled" v-model="warmEnabled" class="mt-0.5" />
            </label>
          </Field>

          <Field v-if="!library">
            <label
              for="library-scan-after-add"
              class="flex cursor-pointer items-start justify-between gap-4 rounded-md border border-border bg-muted/30 p-3 transition-colors hover:bg-muted/50 has-[[aria-checked=true]]:border-primary/40 has-[[aria-checked=true]]:bg-primary/5"
            >
              <span class="min-w-0">
                <span class="block text-sm font-medium text-foreground">Scan library after adding</span>
                <span class="mt-0.5 block text-xs text-muted-foreground">
                  Queues the initial file catalog and metadata update as soon as the library is registered.
                </span>
              </span>
              <Checkbox id="library-scan-after-add" v-model="scanAfterAdd" class="mt-0.5" />
            </label>
          </Field>
        </FieldGroup>
      </FieldSet>

      <Alert v-if="serverError" variant="destructive">
        <TriangleAlert class="size-4" />
        <AlertTitle>Request failed</AlertTitle>
        <AlertDescription>{{ serverError }}</AlertDescription>
      </Alert>
      <Alert
        v-else-if="validation"
        :variant="validationHasIssues ? 'destructive' : 'default'"
        :class="!validationHasIssues ? 'border-success/40 bg-success-bg text-success [&>svg]:text-success' : undefined"
      >
        <TriangleAlert v-if="validationHasIssues" class="size-4" />
        <CircleCheck v-else class="size-4" />
        <AlertTitle>
          {{ validationHasIssues ? "Server validation found errors" : "Server validation passed" }}
        </AlertTitle>
        <AlertDescription>
          {{
            validationHasIssues
              ? "Review the highlighted folder or pattern rows before saving."
              : "These library settings are ready to save."
          }}
        </AlertDescription>
      </Alert>

      <Separator />

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Button
          type="button"
          variant="outline"
          :disabled="pending"
          class="self-start sm:min-w-24"
          @click="emit('cancel')"
        >
          Cancel
        </Button>
        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="submit" :disabled="pending" class="sm:min-w-32">
            {{ submitLabel }}
          </Button>
        </div>
      </div>
    </FieldGroup>
  </form>
</template>
