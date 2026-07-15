<script setup lang="ts">
import { computed } from "vue";
import { Ban, CircleAlert, CircleHelp, LoaderCircle, RefreshCw, Square } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useSearchIndexStatusQuery } from "@/composables/useSearchIndexStatusQuery";
import type { SearchIndexStateV1 } from "@/types";

const props = defineProps<{ libraryId: number | null; open: boolean }>();
const indexQuery = useSearchIndexStatusQuery(
  computed(() => props.libraryId),
  computed(() => props.open),
);
const rows = computed(() => indexQuery.statuses.data.value ?? []);
const tone = (state: string, usable: boolean, warning?: string | null) =>
  warning === "version_mismatch" || (state === "building" && usable) ? "usable-stale" : state;
const label = (state: string, usable: boolean, warning?: string | null) => {
  const resolved = tone(state, usable, warning);
  return resolved === "usable-stale" ? "Usable · rebuilding" : resolved.replaceAll("_", " ");
};

const INDEX_HELP: Record<string, string> = {
  generation_signatures:
    "Contributes metadata evidence to Related assets by comparing prompts, models, resources, and generation settings.",
  prompt_values: "Indexes normalized positive and negative prompts for prompt discovery and exact prompt filters.",
  visual_fingerprints:
    "Contributes visual evidence to Related assets by comparing near-duplicate image fingerprints built from cached previews. It does not infer prompts or workflow lineage.",
  workflow_properties: "Indexes supported ComfyUI node properties for structured workflow filters in Advanced Search.",
  workflow_raw:
    "Indexes compact raw workflow JSON for text search. It is disabled by default because it uses a separate storage budget.",
};

function indexHelp(row: SearchIndexStateV1): string | null {
  if (row.index_name === "workflow_raw" && !row.enabled) {
    return "Raw workflow search is off in server configuration, so there is nothing to index.";
  }
  return INDEX_HELP[row.index_name] ?? null;
}

function indexHelpLabel(row: SearchIndexStateV1): string {
  if (row.index_name === "workflow_raw" && !row.enabled) return "Why workflow raw is disabled";
  return `About ${row.index_name.replaceAll("_", " ")}`;
}

function rebuild(indexName: string, libraryId: number) {
  if (!window.confirm(`Rebuild ${indexName} for this library? Existing usable rows remain available.`)) return;
  indexQuery.rebuild.mutate({ indexName, libraryId, mode: "missing" });
}
</script>

<template>
  <section class="index-panel" aria-labelledby="index-panel-title">
    <div>
      <p id="index-panel-title" class="index-title">Search indexes</p>
      <p class="index-copy">Derived discovery data builds in the background and can remain usable while refreshing.</p>
    </div>
    <div v-if="indexQuery.statuses.isPending.value" class="index-state">
      <LoaderCircle class="spin" /> Loading index status…
    </div>
    <div v-else-if="indexQuery.statuses.isError.value" class="index-state error">
      <CircleAlert /> Index status unavailable.
    </div>
    <ul v-else class="index-list">
      <li v-for="row in rows" :key="`${row.library_id}:${row.index_name}`" class="index-row">
        <div class="index-main">
          <p>{{ row.index_name.replaceAll("_", " ") }}</p>
          <span :data-tone="tone(row.state, row.usable, row.warning)">{{
            label(row.state, row.usable, row.warning)
          }}</span>
          <Tooltip v-if="indexHelp(row)">
            <TooltipTrigger as-child>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                class="size-8 text-muted-foreground"
                :aria-label="indexHelpLabel(row)"
              >
                <CircleHelp />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="top" align="start" class="max-w-[280px] text-pretty">
              {{ indexHelp(row) }}
              <template v-if="row.index_name === 'workflow_raw' && !row.enabled">
                Enable
                <code class="break-all font-mono text-[11px]">GALLERY_SEARCH_WORKFLOW_RAW_ENABLED</code>, restart the
                backend, then rebuild this index.
              </template>
            </TooltipContent>
          </Tooltip>
        </div>
        <p class="index-progress">
          {{ row.indexed_count }} / {{ row.target_count }} indexed<span v-if="row.failed_count">
            · {{ row.failed_count }} failed</span
          ><span v-if="row.skipped_count"> · {{ row.skipped_count }} skipped</span>
        </p>
        <p v-if="Object.keys(row.skip_reasons).length" class="index-detail">
          {{
            Object.entries(row.skip_reasons)
              .map(([reason, count]) => `${reason}: ${count}`)
              .join(" · ")
          }}
        </p>
        <p v-if="row.error_summary" class="index-detail error">{{ row.error_summary }}</p>
        <div class="index-actions">
          <Button
            v-if="row.active_job_id"
            type="button"
            variant="outline"
            size="sm"
            :disabled="indexQuery.cancel.isPending.value"
            @click="indexQuery.cancel.mutate(row.active_job_id)"
          >
            <Square /> Cancel
          </Button>
          <Button
            v-else-if="row.enabled"
            type="button"
            variant="outline"
            size="sm"
            :disabled="indexQuery.rebuild.isPending.value"
            @click="rebuild(row.index_name, row.library_id)"
          >
            <RefreshCw /> Rebuild
          </Button>
          <span v-else class="disabled-label"><Ban /> Disabled</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.index-panel {
  display: grid;
  gap: 12px;
}
.index-title {
  font-size: 14px;
  font-weight: 650;
}
.index-copy,
.index-progress,
.index-detail,
.disabled-label {
  color: var(--muted-foreground);
  font-size: 12px;
}
.index-state {
  display: flex;
  min-height: 60px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px dashed var(--border);
  border-radius: 8px;
  color: var(--muted-foreground);
  font-size: 12px;
}
.index-state svg {
  width: 15px;
}
.error {
  color: var(--destructive);
}
.index-list {
  display: grid;
  gap: 7px;
}
.index-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 9px 10px;
}
.index-main {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}
.index-main p {
  overflow: hidden;
  font-size: 12px;
  font-weight: 650;
  text-transform: capitalize;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.index-main span {
  border-radius: 999px;
  padding: 2px 7px;
  background: var(--muted);
  color: var(--muted-foreground);
  font-size: 10px;
  text-transform: capitalize;
}
.index-main span[data-tone="ready"] {
  background: color-mix(in srgb, #2f855a 15%, var(--background));
  color: #2f855a;
}
.index-main span[data-tone="degraded"],
.index-main span[data-tone="failed"] {
  color: var(--destructive);
}
.index-main span[data-tone="building"],
.index-main span[data-tone="usable-stale"] {
  color: #b7791f;
}
.index-progress,
.index-detail {
  grid-column: 1;
}
.index-actions {
  grid-column: 2;
  grid-row: 1 / span 3;
  display: flex;
  align-items: center;
}
.disabled-label {
  display: flex;
  align-items: center;
  gap: 5px;
}
.disabled-label svg {
  width: 14px;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
