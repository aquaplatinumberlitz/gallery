<script setup lang="ts">
import { computed } from "vue";
import { Check, FolderOpen, Library } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import ButtonLink from "@/components/ui/ButtonLink.vue";
import OverflowTooltip from "@/components/ui/OverflowTooltip.vue";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useActiveLibrarySelection } from "@/composables/useActiveLibrarySelection";
import { useGalleryStore } from "@/stores/gallery";
import type { LibraryImportPath, RegisteredLibrary } from "@/types";

const open = defineModel<boolean>({ required: true });
const galleryStore = useGalleryStore();
const { librariesQuery, libraries } = useActiveLibrarySelection();
const selectableLibraries = computed(() => libraries.value.filter((library) => library.import_paths.length > 0));

function select(library: RegisteredLibrary, importPath: LibraryImportPath) {
  if (galleryStore.setActiveLibrary(library, importPath)) open.value = false;
}
</script>

<template>
  <Sheet v-model:open="open">
    <SheetContent side="bottom" class="max-h-[85vh] overflow-y-auto rounded-t-xl">
      <SheetHeader>
        <SheetTitle>Select library</SheetTitle>
        <SheetDescription>Choose a registered import path to browse.</SheetDescription>
      </SheetHeader>

      <div v-if="librariesQuery.isPending.value" class="py-8 text-center text-sm text-muted-foreground">
        Loading libraries…
      </div>
      <div v-else-if="librariesQuery.isError.value" class="space-y-3 py-6 text-center">
        <p class="text-sm text-destructive">Could not load registered libraries.</p>
        <Button variant="outline" @click="librariesQuery.refetch()">Retry</Button>
      </div>
      <div v-else-if="!selectableLibraries.length" class="space-y-4 py-8 text-center">
        <Library class="mx-auto size-8 text-muted-foreground" />
        <div>
          <p class="font-medium">No libraries registered</p>
          <p class="mt-1 text-sm text-muted-foreground">Add a library before browsing the gallery.</p>
        </div>
        <ButtonLink to="/admin/libraries" @click="open = false">Add Library</ButtonLink>
      </div>
      <div v-else class="mt-5 space-y-4">
        <section v-for="library in selectableLibraries" :key="library.id" class="space-y-2">
          <div class="flex items-center justify-between gap-3">
            <p class="font-medium">{{ library.name }}</p>
            <span class="text-xs capitalize text-muted-foreground">{{ library.state }}</span>
          </div>
          <button
            v-for="importPath in library.import_paths"
            :key="importPath.id"
            type="button"
            class="flex w-full items-center gap-3 rounded-md border border-border p-3 text-left hover:bg-accent"
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
        <ButtonLink to="/admin/libraries" variant="outline" class="w-full" @click="open = false">
          Manage Libraries
        </ButtonLink>
      </div>
    </SheetContent>
  </Sheet>
</template>
