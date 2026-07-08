<script setup lang="ts">
import { computed } from "vue";
import { Check, FolderOpen, Library } from "lucide-vue-next";
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

  <div v-else-if="!selectableLibraries.length" class="flex flex-col items-center gap-4 py-8 text-center">
    <Library class="size-8 text-muted-foreground" />
    <div>
      <p class="font-medium">No libraries registered</p>
      <p class="mt-1 text-sm text-muted-foreground">Add a library before browsing the gallery.</p>
    </div>
    <ButtonLink to="/admin/libraries" @click="emit('close')">Add Library</ButtonLink>
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
