<script setup lang="ts">
import { computed } from "vue";
import { Check, FolderOpen, Plus } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import Badge from "@/components/ui/Badge.vue";
import { useActiveLibrarySelection } from "@/composables/useActiveLibrarySelection";
import { useGalleryStore } from "@/stores/gallery";
import type { LibraryImportPath, RegisteredLibrary } from "@/types";

const emit = defineEmits<{
  (e: "close"): void;
}>();

const galleryStore = useGalleryStore();
const { librariesQuery, libraries } = useActiveLibrarySelection();
const selectableLibraries = computed(() => libraries.value.filter((library) => library.import_paths.length > 0));

function select(library: RegisteredLibrary, importPath: LibraryImportPath) {
  if (galleryStore.setActiveLibrary(library, importPath)) emit("close");
}
</script>

<template>
  <div v-if="librariesQuery.isPending.value" class="py-8 text-center text-sm text-muted-foreground">
    Loading libraries...
  </div>

  <div v-else-if="librariesQuery.isError.value" class="flex flex-col items-center gap-3 py-6 text-center">
    <p class="text-sm text-destructive">Could not load registered libraries.</p>
    <Button variant="outline" @click="librariesQuery.refetch()">Retry</Button>
  </div>

  <div v-else-if="!selectableLibraries.length" class="py-6">
    <RouterLink
      to="/admin/libraries"
      class="group flex w-full flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border px-6 py-8 text-center outline-none transition-all duration-200 hover:border-[#ff6b35]/50 hover:bg-[#ff6b35]/[0.03] focus-visible:ring-[3px] focus-visible:ring-ring/50"
      @click="emit('close')"
    >
      <div
        class="flex size-11 items-center justify-center rounded-full border-2 border-dashed border-border transition-all duration-200 group-hover:border-[#ff6b35]/60 group-hover:bg-[#ff6b35]/10"
      >
        <Plus class="size-4 text-muted-foreground transition-colors duration-200 group-hover:text-[#ff6b35]" />
      </div>
      <div>
        <p class="text-sm font-medium text-foreground">Add your first library</p>
        <p class="mt-0.5 text-xs text-muted-foreground">Set up an import path to start browsing</p>
      </div>
    </RouterLink>
  </div>

  <div v-else class="flex flex-col gap-4">
    <section v-for="library in selectableLibraries" :key="library.id" class="flex flex-col gap-2">
      <div class="flex items-center justify-between gap-3">
        <p class="min-w-0 truncate font-medium">{{ library.name }}</p>
        <Badge variant="secondary" class="shrink-0 capitalize">{{ library.state }}</Badge>
      </div>

      <button
        v-for="importPath in library.import_paths"
        :key="importPath.id"
        type="button"
        class="flex w-full items-center gap-3 rounded-md border border-border p-3 text-left transition-colors hover:bg-accent focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
        @click="select(library, importPath)"
      >
        <FolderOpen class="size-4 shrink-0 text-primary" />
        <OverflowTooltip :text="importPath.path" class="min-w-0 flex-1 font-mono text-xs" align="start">
          {{ importPath.path }}
        </OverflowTooltip>
        <Check
          v-if="galleryStore.activeLibraryId === library.id && galleryStore.activeImportPathId === importPath.id"
          class="size-4 shrink-0"
        />
      </button>
    </section>

    <ButtonLink to="/admin/libraries" variant="outline" class="w-full" @click="emit('close')">
      Manage Libraries
    </ButtonLink>
  </div>
</template>
