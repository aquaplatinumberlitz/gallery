<script setup lang="ts">
import { computed, nextTick, shallowRef, useTemplateRef, watch } from "vue";
import { storeToRefs } from "pinia";
import { CircleHelp, DatabaseZap, ImageOff, Loader, RefreshCw, ScanSearch, TriangleAlert } from "lucide-vue-next";
import PhotoCard from "@/components/PhotoCard.vue";
import RelationReasonList from "@/components/RelationReasonList.vue";
import Button from "@/components/ui/Button.vue";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  useRelatedAssetsIndexRecovery,
  type RelatedIndexKind,
  type RelatedIndexRecoveryStatus,
} from "@/composables/useRelatedAssetsIndexRecovery";
import { useRelatedAssetsQuery } from "@/composables/useRelatedAssetsQuery";
import { GalleryAPIError } from "@/services/api";
import { useLightboxStore } from "@/stores/lightbox";
import { useRelatedAssetsStore } from "@/stores/relatedAssets";
import type { FileNode, RelatedSearchRequestV1, RelatedSearchResultV1, RelatedSearchStatusV1 } from "@/types";
import { normalizeRelatedResults } from "@/utils/relatedAssets";

type ReadinessAction = "build" | "retry_build" | null;

interface ReadinessNotice {
  kind: RelatedIndexKind;
  title: string;
  message: string;
  role: "status" | "alert";
  action: ReadinessAction;
  status: RelatedIndexRecoveryStatus;
}

const relatedStore = useRelatedAssetsStore();
const lightboxStore = useLightboxStore();
const { isOpen, reference, scope } = storeToRefs(relatedStore);
const relatedContentRef = useTemplateRef<HTMLElement>("relatedContent");
const returnToResults = shallowRef(false);
const returnScrollTop = shallowRef(0);
const returnReferenceId = shallowRef<number | null>(null);

const request = computed<RelatedSearchRequestV1 | null>(() => {
  if (!isOpen.value || !reference.value || !scope.value) return null;
  return {
    schema_version: 1,
    reference_asset_id: reference.value.assetId,
    profile: "related",
    scope: scope.value,
    limit: 60,
  };
});
const relatedQuery = useRelatedAssetsQuery(request);
const response = computed(() => relatedQuery.data.value ?? null);
const results = computed(() => normalizeRelatedResults(response.value?.items ?? []));

const error = computed(() => (relatedQuery.error.value instanceof GalleryAPIError ? relatedQuery.error.value : null));
const hasStaleError = computed(() => Boolean(error.value && response.value));
const isReadinessError = computed(() =>
  Boolean(error.value && ["relation_index_not_ready", "reference_not_indexed"].includes(error.value.type)),
);
const displayStatus = computed<RelatedSearchStatusV1 | null>(
  () => response.value?.status ?? error.value?.relatedStatus ?? null,
);
const referenceLibraryId = computed(() => {
  if (reference.value?.libraryId) return reference.value.libraryId;
  return scope.value?.kind === "folder" || scope.value?.kind === "library" ? scope.value.library_id : null;
});
const indexRecovery = useRelatedAssetsIndexRecovery({
  libraryId: referenceLibraryId,
  panelOpen: isOpen,
  relatedStatus: displayStatus,
  onReady: () => relatedQuery.refetch(),
});

function indexLabel(kind: RelatedIndexKind) {
  return kind === "metadata" ? "Metadata" : "Visual";
}

function indexStatus(kind: RelatedIndexKind) {
  return kind === "metadata" ? indexRecovery.metadataStatus.value : indexRecovery.visualStatus.value;
}

function normalizedState(status: RelatedIndexRecoveryStatus) {
  return status.state === "pending" ? "not_ready" : status.state;
}

const readinessNotices = computed<ReadinessNotice[]>(() => {
  const notices: ReadinessNotice[] = [];
  for (const kind of ["metadata", "visual"] as const) {
    const status = indexStatus(kind);
    if (!status) continue;
    const state = normalizedState(status);
    const buildFailed = indexRecovery.buildErrorKind.value === kind;
    if (state === "ready") continue;

    if (state === "building") {
      notices.push({
        kind,
        title: `${indexLabel(kind)} index is building`,
        message:
          kind === "visual"
            ? "Visual matches are still indexing. Results will update automatically."
            : "Metadata matches are still indexing. Results will update automatically.",
        role: "status",
        action: null,
        status,
      });
      continue;
    }

    if (state === "failed" || buildFailed) {
      notices.push({
        kind,
        title: `${indexLabel(kind)} index build failed`,
        message:
          ("error_summary" in status && status.error_summary) ||
          "The previous background build did not finish. Existing results remain available.",
        role: "alert",
        action: "retry_build",
        status,
      });
      continue;
    }

    if (state === "not_ready") {
      notices.push({
        kind,
        title: kind === "metadata" ? "Metadata relationships aren’t built yet" : "Visual matching isn’t built yet",
        message:
          kind === "metadata"
            ? "Build the metadata index to compare prompts, models, resources, and generation settings."
            : "Build visual fingerprints to add pixel-similarity matches.",
        role: "status",
        action: "build",
        status,
      });
      continue;
    }

    if (state === "degraded") {
      notices.push({
        kind,
        title: `${indexLabel(kind)} coverage is partial`,
        message: "Available matches are shown now. Coverage will improve when indexing recovers.",
        role: "status",
        action: null,
        status,
      });
      continue;
    }

    notices.push({
      kind,
      title: `${indexLabel(kind)} matching is ${state}`,
      message: "Available matches from the other index are still shown.",
      role: state === "unavailable" ? "alert" : "status",
      action: null,
      status,
    });
  }
  return notices;
});

const tierLabel = (item: RelatedSearchResultV1) => {
  if (item.relation_reasons.includes("same_exact_signature")) return "Exact settings";
  if (item.relation_reasons.includes("same_recipe")) return "Same recipe";
  if (item.relation_reasons.includes("same_generation_family")) return "Same family";
  if (item.relation_reasons.includes("visual_variant")) return "Visual match";
  return {
    100: "Exact settings",
    90: "Same recipe",
    80: "Same family",
    70: "Same prompt",
    60: "Strong relation",
    40: "Related",
  }[item.relation_tier];
};

/** Maps a result's highest-priority reason to its semantic color tier name */
const tierColorTier = (item: RelatedSearchResultV1): string => {
  if (item.relation_reasons.includes("same_exact_signature")) return "exact";
  if (item.relation_reasons.includes("same_recipe") || item.relation_reasons.includes("same_generation_family"))
    return "recipe";
  if (item.relation_reasons.includes("same_prompt") || item.relation_reasons.includes("strong_prompt_overlap"))
    return "prompt";
  if (item.relation_reasons.includes("visual_variant")) return "visual";
  return "model";
};

const stateLabel = (state: string) => state.replace(/_/g, " ");

const resultNodes = computed<FileNode[]>(() =>
  results.value.map((item) => ({
    asset_id: item.asset_id,
    library_id: item.library_id,
    library_name: item.library_name,
    name: item.name,
    path: item.path,
    type: "image",
    has_children: false,
    mtime: item.mtime,
    width: item.width,
    height: item.height,
    // Spread to plain object — response.value?.scope is a reactive TanStack Query
    // reference. Assigning it directly would carry the Proxy into FileNode, causing
    // DataCloneError if structuredClone() is called downstream (e.g. relatedAssets store).
    relation_scope: response.value?.scope ? { ...response.value.scope } : undefined,
  })),
);

async function openResult(item: RelatedSearchResultV1) {
  const nodes = resultNodes.value.map((node) => ({ ...node }));
  const index = nodes.findIndex((node) => node.asset_id === item.asset_id);
  const node = nodes[index];
  if (!node) return;
  returnToResults.value = true;
  returnScrollTop.value = relatedContentRef.value?.scrollTop ?? 0;
  returnReferenceId.value = reference.value?.assetId ?? null;
  relatedStore.close();
  await nextTick();
  lightboxStore.open(node, nodes, index);
}

watch(
  () => lightboxStore.isOpen,
  async (open, wasOpen) => {
    if (open || !wasOpen || !returnToResults.value) return;
    await nextTick();
    await nextTick();
    if (reference.value?.assetId !== returnReferenceId.value) {
      returnToResults.value = false;
      returnReferenceId.value = null;
      return;
    }
    relatedStore.reopen();
    await nextTick();
    relatedContentRef.value?.scrollTo?.({ top: returnScrollTop.value });
    returnToResults.value = false;
    returnReferenceId.value = null;
  },
);
</script>

<template>
  <Sheet :open="isOpen" @update:open="!$event && relatedStore.close()">
    <SheetContent
      side="right"
      class="related-sheet flex h-dvh min-h-0 w-full flex-col gap-0 overflow-hidden bg-background p-0 sm:max-w-[760px]"
      data-testid="related-assets-panel"
    >
      <SheetHeader class="shrink-0 border-b border-border px-5 py-4 pr-14 text-left">
        <div class="flex items-start gap-3">
          <div class="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <ScanSearch class="size-5" />
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-1">
              <SheetTitle class="truncate">Related assets</SheetTitle>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    class="size-11 shrink-0 text-muted-foreground"
                    aria-label="How Related assets matches are found"
                  >
                    <CircleHelp />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom" align="start" class="max-w-[340px] space-y-1.5 text-pretty">
                  <p>
                    The backend combines indexed generation metadata with visual fingerprints, deduplicates by asset ID,
                    and returns the ranked order.
                  </p>
                  <p>
                    Reason badges show only evidence present in the API, such as matching recipe, prompt, model, or
                    near-duplicate pixels. They do not claim generation lineage.
                  </p>
                </TooltipContent>
              </Tooltip>
            </div>
            <SheetDescription class="truncate">
              {{ reference?.name || "Selected image" }} · metadata, recipe, and visual evidence
            </SheetDescription>
          </div>
        </div>
      </SheetHeader>

      <div ref="relatedContent" class="related-content" aria-live="polite">
        <div v-if="displayStatus" class="coverage-row" aria-label="Related assets index coverage">
          <span :data-state="displayStatus.metadata.state">
            Metadata: {{ stateLabel(displayStatus.metadata.state) }}
          </span>
          <span :data-state="displayStatus.visual.state">Visual: {{ stateLabel(displayStatus.visual.state) }}</span>
        </div>

        <div v-if="hasStaleError" class="state-banner state-banner-warning" role="alert">
          <TriangleAlert class="size-4" />
          <span>Refresh failed. Showing the last successful related results.</span>
          <Button class="min-h-11" variant="outline" @click="relatedQuery.refetch()">
            <RefreshCw /> Retry query
          </Button>
        </div>

        <div v-if="relatedQuery.isPending.value && !response" class="state-card" role="status">
          <Loader class="size-5 animate-spin" />
          <div><strong>Finding related assets…</strong><span>Reading available relation indexes.</span></div>
        </div>

        <div v-else-if="error && !response && !isReadinessError" class="state-card" role="alert">
          <TriangleAlert class="size-5" />
          <div>
            <strong>{{ error.userMessage }}</strong>
            <span>{{ error.suggestion }}</span>
          </div>
          <Button v-if="error.canRetry" class="min-h-11" variant="outline" @click="relatedQuery.refetch()">
            <RefreshCw /> Retry query
          </Button>
        </div>

        <template v-else>
          <div v-if="indexRecovery.statusError.value && readinessNotices.length" class="state-banner" role="alert">
            <TriangleAlert class="size-4" />
            <span>Latest index progress is unavailable. The last known coverage is shown.</span>
            <Button class="min-h-11" variant="outline" @click="indexRecovery.refreshStatus()">
              <RefreshCw /> Check status
            </Button>
          </div>

          <div v-if="readinessNotices.length" class="readiness-list" aria-label="Related assets coverage details">
            <div
              v-for="notice in readinessNotices"
              :key="notice.kind"
              class="readiness-notice"
              :data-kind="notice.kind"
              :role="notice.role"
            >
              <Loader v-if="normalizedState(notice.status) === 'building'" class="size-5 shrink-0 animate-spin" />
              <TriangleAlert v-else-if="notice.role === 'alert'" class="size-5 shrink-0" />
              <ImageOff v-else class="size-5 shrink-0" />
              <div class="readiness-copy">
                <strong>{{ notice.title }}</strong>
                <span>{{ notice.message }}</span>
                <template v-if="normalizedState(notice.status) === 'building' && notice.status.target_count">
                  <Progress
                    :model-value="indexRecovery.progressPercent(notice.kind)"
                    class="mt-2 h-1.5"
                    :aria-label="`${notice.kind} index build progress`"
                  />
                  <span>{{ notice.status.indexed_count }} / {{ notice.status.target_count }} indexed</span>
                </template>
              </div>
              <Button
                v-if="notice.action"
                class="readiness-action"
                :disabled="indexRecovery.startingKind.value !== null"
                :aria-label="`${notice.action === 'retry_build' ? 'Retry build' : 'Build'} ${notice.kind} index`"
                :data-testid="`build-${notice.kind}-index`"
                @click="indexRecovery.startBuild(notice.kind)"
              >
                <Loader
                  v-if="indexRecovery.startingKind.value === notice.kind"
                  data-icon="inline-start"
                  class="animate-spin"
                />
                <DatabaseZap v-else data-icon="inline-start" />
                {{ notice.action === "retry_build" ? "Retry build" : "Build index" }}
              </Button>
            </div>
          </div>

          <template v-if="response">
            <div v-if="results.length" class="related-grid" data-testid="related-results">
              <article v-for="item in results" :key="item.asset_id" class="related-card">
                <div class="related-card-media">
                  <PhotoCard :src="item.path" :name="item.name" @click="openResult(item)" />

                  <!-- Tier badge: bottom-left, semantic dot -->
                  <span class="tier-label" :data-tier="tierColorTier(item)">
                    <span class="tier-dot" aria-hidden="true" />
                    {{ tierLabel(item) }}
                  </span>

                  <!-- Detail chips: hover-reveal overlay at top of image -->
                  <div class="chip-overlay" aria-hidden="true">
                    <RelationReasonList :reasons="item.relation_reasons" />
                  </div>
                </div>

                <!-- Compact 1-line filename -->
                <Tooltip>
                  <TooltipTrigger as-child>
                    <button type="button" class="result-title" @click="openResult(item)">{{ item.name }}</button>
                  </TooltipTrigger>
                  <TooltipContent side="top" class="max-w-[360px] break-all text-pretty">
                    {{ item.name }}
                  </TooltipContent>
                </Tooltip>
              </article>
            </div>

            <div v-else class="state-card state-card-empty" role="status">
              <ImageOff class="size-5" />
              <div>
                <strong>No related assets found</strong>
                <span>Try a wider scope to include more assets.</span>
              </div>
            </div>
          </template>
        </template>
      </div>
    </SheetContent>
  </Sheet>
</template>

<style scoped>
.related-sheet {
  background: var(--background);
}

.related-content {
  min-height: 0;
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 16px 16px max(24px, calc(env(safe-area-inset-bottom) + 16px));
  scrollbar-gutter: stable;
  -webkit-overflow-scrolling: touch;
}

.coverage-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.coverage-row span {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--gallery-radius-full);
  color: var(--muted-foreground);
  font-size: 12px;
  font-weight: 650;
  text-transform: capitalize;
}

.coverage-row span[data-state="ready"] {
  border-color: color-mix(in srgb, var(--gallery-success) 42%, var(--border));
  color: var(--gallery-success-fg);
}

.coverage-row span[data-state="degraded"],
.coverage-row span[data-state="building"] {
  border-color: color-mix(in srgb, var(--gallery-warning) 42%, var(--border));
  color: var(--gallery-warning-fg);
}

.state-card,
.state-banner,
.readiness-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: var(--gallery-radius-lg);
  background: var(--card);
}

.state-card {
  min-height: 132px;
  justify-content: center;
  padding: 22px;
  text-align: left;
}

.state-card > div,
.readiness-copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.state-card span,
.state-banner span,
.readiness-copy span {
  color: var(--muted-foreground);
  font-size: 12px;
}

.state-card .button,
.state-banner .button {
  margin-left: auto;
}

.state-banner {
  margin-bottom: 12px;
  padding: 9px 11px;
}

.state-banner-warning,
.readiness-notice[data-kind="metadata"]:has(.animate-spin),
.readiness-notice[data-kind="visual"]:has(.animate-spin) {
  border-color: color-mix(in srgb, var(--gallery-warning) 45%, var(--border));
}

.readiness-list {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

.readiness-notice {
  align-items: flex-start;
  padding: 12px;
}

.readiness-copy {
  flex: 1;
}

.readiness-action {
  min-height: 44px;
  flex: 0 0 auto;
}

.related-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(156px, 1fr));
  gap: 14px;
}

.related-card {
  display: grid;
  min-width: 0;
  align-content: start;
  /* tight: image + 1-line filename only */
  gap: 4px;
}

.related-card-media {
  position: relative;
  border-radius: var(--gallery-radius-lg);
  overflow: hidden;
}

/* ── Tier badge: bottom-left, dot + label ── */
.tier-label {
  position: absolute;
  bottom: 6px;
  left: 6px;
  z-index: 4;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px 2px 5px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: var(--gallery-radius-full);
  background: rgba(0, 0, 0, 0.56);
  color: rgba(255, 255, 255, 0.92);
  font-size: 10.5px;
  font-weight: 650;
  line-height: 1.2;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  pointer-events: none;
}

/* Semantic dot per tier */
.tier-dot {
  display: inline-block;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.65);
}
.tier-label[data-tier="exact"] .tier-dot {
  background: #818cf8;
}
.tier-label[data-tier="recipe"] .tier-dot {
  background: #fbbf24;
}
.tier-label[data-tier="prompt"] .tier-dot {
  background: #7dd3fc;
}
.tier-label[data-tier="model"] .tier-dot {
  background: #2dd4bf;
}
.tier-label[data-tier="visual"] .tier-dot {
  background: #fb7185;
}

/* ── Chip overlay: top of image, revealed on hover ── */
.chip-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 5;
  padding: 7px 7px 20px;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.5) 0%, transparent 100%);
  opacity: 0;
  transform: translateY(-4px);
  transition:
    opacity 180ms ease,
    transform 180ms ease;
  pointer-events: none;
}

.related-card-media:hover .chip-overlay,
.related-card-media:focus-within .chip-overlay {
  opacity: 1;
  transform: translateY(0);
}

/* Touch (mobile/tablet): chip overlay stays hidden — tier badge is sufficient.
   Detailed reasons are accessible via the lightbox/detail view.
   Follows image-first grid principle (Google Photos, Apple Photos). */

/* ── Compact filename: 1 line, no wasted height ── */
.result-title {
  display: -webkit-box;
  min-width: 0;
  padding: 1px 0 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: var(--muted-foreground);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.3;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  transition: color 120ms ease;
}

.result-title:hover {
  color: var(--foreground);
}

.result-title:focus-visible {
  border-radius: var(--gallery-radius-sm);
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

@media (min-width: 640px) {
  .related-content {
    padding: 20px 20px 28px;
  }
}

@media (max-width: 639px) {
  .readiness-notice {
    flex-wrap: wrap;
  }

  .readiness-action {
    width: 100%;
  }

  .related-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 8px;
  }
}
</style>
