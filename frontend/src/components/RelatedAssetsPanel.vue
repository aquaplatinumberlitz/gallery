<script setup lang="ts">
import { computed } from "vue";
import { storeToRefs } from "pinia";
import { ImageOff, Loader, RefreshCw, ScanSearch, TriangleAlert } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import GenerationFamilySummary from "@/components/GenerationFamilySummary.vue";
import PhotoCard from "@/components/PhotoCard.vue";
import RelationReasonList from "@/components/RelationReasonList.vue";
import { usePhotoMetadataQuery } from "@/composables/usePhotoMetadataQuery";
import { useRelatedAssetsQuery } from "@/composables/useRelatedAssetsQuery";
import { GalleryAPIError } from "@/services/api";
import { useLightboxStore } from "@/stores/lightbox";
import { useRelatedAssetsStore } from "@/stores/relatedAssets";
import type {
  FileNode,
  RelatedProfileV1,
  RelatedSearchRequestV1,
  RelatedSearchResultV1,
  RelatedSearchStatusV1,
} from "@/types";

const relatedStore = useRelatedAssetsStore();
const lightboxStore = useLightboxStore();
const { isOpen, reference, scope, profile } = storeToRefs(relatedStore);

const request = computed<RelatedSearchRequestV1 | null>(() => {
  if (!isOpen.value || !reference.value || !scope.value) return null;
  return {
    schema_version: 1,
    reference_asset_id: reference.value.assetId,
    profile: profile.value,
    scope: scope.value,
    limit: 60,
  };
});
const relatedQuery = useRelatedAssetsQuery(request);
const response = computed(() => relatedQuery.data.value ?? null);
const results = computed(() => response.value?.items ?? []);
const selectedAssetId = computed(() => results.value[0]?.asset_id ?? null);
const selectedResult = computed(() => results.value.find((item) => item.asset_id === selectedAssetId.value) ?? null);
const referencePath = computed(() => reference.value?.path ?? "");
const candidatePath = computed(() => selectedResult.value?.path ?? "");
const referenceMetadataQuery = usePhotoMetadataQuery(isOpen, referencePath);
const candidateMetadataQuery = usePhotoMetadataQuery(isOpen, candidatePath);

const error = computed(() => (relatedQuery.error.value instanceof GalleryAPIError ? relatedQuery.error.value : null));
const hasStaleError = computed(() => Boolean(error.value && response.value));
const displayStatus = computed<RelatedSearchStatusV1 | null>(
  () => response.value?.status ?? error.value?.relatedStatus ?? null,
);
const tierLabel = (item: RelatedSearchResultV1) => {
  if (item.relation_reasons.includes("same_exact_signature")) return "Exact settings";
  if (item.relation_reasons.includes("same_recipe")) return "Same recipe";
  if (item.relation_reasons.includes("same_generation_family")) return "Same family";
  if (item.relation_reasons.includes("visual_variant")) return "Visual variant";
  return {
    100: "Exact settings",
    90: "Same recipe",
    80: "Same family",
    70: "Same prompt",
    60: "Strong relation",
    40: "Related",
  }[item.relation_tier];
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
    relation_scope: response.value?.scope,
  })),
);

function setProfile(value: string | number) {
  relatedStore.setProfile(value as RelatedProfileV1);
}

function openResult(item: RelatedSearchResultV1) {
  const index = resultNodes.value.findIndex((node) => node.asset_id === item.asset_id);
  const node = resultNodes.value[index];
  if (!node) return;
  relatedStore.close();
  lightboxStore.open(node, resultNodes.value, index);
}

function useAsReference(item: RelatedSearchResultV1) {
  if (!response.value) return;
  relatedStore.open(
    { assetId: item.asset_id, path: item.path, name: item.name, libraryId: item.library_id },
    response.value.scope,
  );
}
</script>

<template>
  <Sheet :open="isOpen" @update:open="!$event && relatedStore.close()">
    <SheetContent
      side="right"
      class="related-sheet w-full gap-0 p-0 sm:max-w-[760px]"
      data-testid="related-assets-panel"
    >
      <SheetHeader class="border-b border-border px-5 py-4 pr-14 text-left">
        <div class="flex items-start gap-3">
          <div class="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <ScanSearch class="size-5" />
          </div>
          <div class="min-w-0">
            <SheetTitle class="truncate">Related Assets</SheetTitle>
            <SheetDescription class="truncate">
              {{ reference?.name || "Selected image" }} · recorded evidence and visual variants
            </SheetDescription>
          </div>
        </div>
      </SheetHeader>

      <Tabs :model-value="profile" class="flex min-h-0 flex-1 flex-col" @update:model-value="setProfile">
        <div class="border-b border-border px-4 py-3 sm:px-5">
          <TabsList class="grid h-auto w-full grid-cols-3">
            <TabsTrigger value="related" class="min-h-11 px-2">Related</TabsTrigger>
            <TabsTrigger value="recipe" class="min-h-11 px-2">Same recipe</TabsTrigger>
            <TabsTrigger value="visual" class="min-h-11 px-2">Visual variants</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent :value="profile" class="mt-0 min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
          <div v-if="displayStatus" class="coverage-row" aria-label="Related Assets index coverage">
            <span :data-state="displayStatus.metadata.state">
              Metadata: {{ stateLabel(displayStatus.metadata.state) }}
            </span>
            <span :data-state="displayStatus.visual.state"> Visual: {{ stateLabel(displayStatus.visual.state) }} </span>
          </div>

          <div v-if="hasStaleError" class="state-banner state-banner-warning" role="alert">
            <TriangleAlert class="size-4" />
            <span>Refresh failed. Showing the last successful related results.</span>
            <Button variant="outline" size="sm" @click="relatedQuery.refetch()"> <RefreshCw /> Retry </Button>
          </div>

          <div v-if="relatedQuery.isPending.value && !response" class="state-card" role="status">
            <Loader class="size-5 animate-spin" />
            <div><strong>Finding related assets…</strong><span>Reading persisted relation indexes.</span></div>
          </div>

          <div v-else-if="error && !response" class="state-card" role="alert">
            <TriangleAlert class="size-5" />
            <div>
              <strong>{{ error.userMessage }}</strong>
              <span>{{ error.suggestion }}</span>
            </div>
            <Button v-if="error.canRetry" variant="outline" size="sm" @click="relatedQuery.refetch()">
              <RefreshCw /> Retry
            </Button>
          </div>

          <template v-else-if="response">
            <div v-if="profile === 'related' && !response.status.visual.usable" class="state-banner" role="status">
              <ImageOff class="size-4" />
              <span
                >Showing metadata relations. Visual coverage is {{ stateLabel(response.status.visual.state) }}.</span
              >
            </div>

            <GenerationFamilySummary
              v-if="profile !== 'visual' && results.length"
              class="mb-4"
              :results="results"
              :reference-metadata="referenceMetadataQuery.data.value ?? null"
              :candidate-metadata="candidateMetadataQuery.data.value ?? null"
              :candidate-name="selectedResult?.name"
            />

            <div v-if="results.length" class="related-grid" aria-live="polite">
              <article v-for="item in results" :key="`${item.library_id}:${item.asset_id}`" class="related-card">
                <div class="related-card-media">
                  <PhotoCard
                    :src="item.path"
                    :name="item.name"
                    :can-find-related="true"
                    @click="openResult(item)"
                    @find-related="useAsReference(item)"
                  />
                  <span class="tier-label">{{ tierLabel(item) }}</span>
                </div>
                <button type="button" class="result-title" @click="openResult(item)">{{ item.name }}</button>
                <RelationReasonList :reasons="item.relation_reasons" />
              </article>
            </div>

            <div v-else class="state-card state-card-empty" role="status">
              <ImageOff class="size-5" />
              <div>
                <strong>No matching assets in this scope</strong>
                <span v-if="profile === 'visual'">Visual matching is intentionally limited to near-duplicates.</span>
                <span v-else>Try a wider scope or another relation filter.</span>
              </div>
            </div>
          </template>
        </TabsContent>
      </Tabs>
    </SheetContent>
  </Sheet>
</template>

<style scoped>
.related-sheet {
  display: flex;
  height: 100dvh;
  flex-direction: column;
  background: var(--background);
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
  border-radius: 999px;
  color: var(--muted-foreground);
  font-size: 10px;
  font-weight: 650;
  text-transform: capitalize;
}

.coverage-row span[data-state="ready"] {
  border-color: color-mix(in srgb, var(--success, #3a9d62) 42%, var(--border));
  color: color-mix(in srgb, var(--success, #3a9d62) 80%, var(--foreground));
}

.coverage-row span[data-state="degraded"],
.coverage-row span[data-state="building"] {
  border-color: color-mix(in srgb, var(--warning, #d98b1d) 42%, var(--border));
}

.state-card,
.state-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--card);
}

.state-card {
  min-height: 132px;
  justify-content: center;
  padding: 22px;
  text-align: left;
}

.state-card > div {
  display: grid;
  gap: 3px;
}

.state-card span,
.state-banner span {
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

.state-banner-warning {
  border-color: color-mix(in srgb, var(--warning, #d98b1d) 45%, var(--border));
}

.related-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(156px, 1fr));
  gap: 16px;
}

.related-card {
  display: grid;
  min-width: 0;
  align-content: start;
  gap: 7px;
}

.related-card-media {
  position: relative;
}

.tier-label {
  position: absolute;
  bottom: 7px;
  left: 7px;
  z-index: 4;
  padding: 4px 7px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.62);
  color: white;
  font-size: 9px;
  font-weight: 750;
  letter-spacing: 0.02em;
  backdrop-filter: blur(8px);
}

.result-title {
  min-width: 0;
  padding: 0;
  overflow: hidden;
  border: 0;
  background: transparent;
  color: var(--foreground);
  font-size: 12px;
  font-weight: 700;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.result-title:focus-visible {
  border-radius: 4px;
  outline: none;
  box-shadow: var(--focus-ring-shadow);
}

@media (max-width: 639px) {
  .related-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px 8px;
  }
}
</style>
