import { useMutation, useQueryClient } from "@tanstack/vue-query";
import { useToast } from "@/composables/useToast";
import { queryKeys } from "@/query/keys";
import {
  createLibrary,
  deleteLibrary,
  GalleryAPIError,
  repairLibrary,
  scanAllLibraries,
  scanLibrary,
  updateLibrary,
  validateLibraryCreate,
  validateLibraryUpdate,
} from "@/services/api";
import type { LibraryCreateRequest, LibraryUpdateRequest } from "@/types";
import type { RegisteredLibrary } from "@/types";
import { useGalleryStore } from "@/stores/gallery";

interface UpdateVariables {
  id: number;
  payload: LibraryUpdateRequest;
}

interface ValidateVariables {
  id?: number;
  payload: LibraryCreateRequest | LibraryUpdateRequest;
}

function errorMessage(error: unknown): string {
  return error instanceof GalleryAPIError ? error.userMessage : "An unexpected error occurred.";
}

export function useLibraryMutations() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const galleryStore = useGalleryStore();

  const createMutation = useMutation({
    mutationFn: createLibrary,
    onSuccess: async () => {
      toast.success("Library created");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.librariesRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
      ]);
    },
    onError: (error) => toast.error("Could not create library", errorMessage(error)),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: UpdateVariables) => updateLibrary(id, payload),
    onSuccess: async (library, { id }) => {
      if (galleryStore.activeLibraryId === id) {
        const selectedPath = library.import_paths.find((path) => path.id === galleryStore.activeImportPathId);
        galleryStore.setActiveLibrary(library, selectedPath);
      }
      toast.success("Library updated");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.library(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryStats(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryProgress(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
      ]);
    },
    onError: (error) => toast.error("Could not update library", errorMessage(error)),
  });

  const validateMutation = useMutation({
    mutationFn: ({ id, payload }: ValidateVariables) =>
      id ? validateLibraryUpdate(id, payload as LibraryUpdateRequest) : validateLibraryCreate(payload),
    onSuccess: (result) => {
      if (result.is_valid) toast.success("Library settings are valid");
      else toast.warning("Library settings need attention");
    },
    onError: (error) => toast.error("Could not validate library", errorMessage(error)),
  });

  const scanMutation = useMutation({
    mutationFn: scanLibrary,
    onSuccess: async (_response, id) => {
      toast.success("Library scan queued");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.library(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryProgress(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryStats(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryJobs(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
      ]);
    },
    onError: (error) => toast.error("Could not scan library", errorMessage(error)),
  });

  const scanAllMutation = useMutation({
    mutationFn: scanAllLibraries,
    onSuccess: async () => {
      toast.success("Library scans queued");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.librariesRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      ]);
    },
    onError: (error) => toast.error("Could not scan libraries", errorMessage(error)),
  });

  const repairMutation = useMutation({
    mutationFn: repairLibrary,
    onSuccess: async (response, id) => {
      toast.success(
        "Library repaired",
        `${response.added} added, ${response.removed} removed, ${response.modified} modified`,
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.library(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryProgress(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryStats(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryJobs(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
      ]);
    },
    onError: (error) => toast.error("Could not repair library", errorMessage(error)),
  });

  const unregisterMutation = useMutation({
    mutationFn: deleteLibrary,
    onSuccess: async (_response, id) => {
      toast.success("Library unregistered");
      if (galleryStore.activeLibraryId === id) {
        const remaining = (queryClient.getQueryData<RegisteredLibrary[]>(queryKeys.libraries()) ?? [])
          .filter((library) => library.id !== id && library.import_paths.length > 0)
          .sort((a, b) => a.id - b.id);
        if (remaining[0]) galleryStore.setActiveLibrary(remaining[0]);
        else galleryStore.clearActiveLibrary();
      }
      queryClient.removeQueries({ queryKey: queryKeys.library(id) });
      queryClient.removeQueries({ queryKey: queryKeys.libraryProgress(id) });
      queryClient.removeQueries({ queryKey: queryKeys.libraryStats(id) });
      queryClient.removeQueries({ queryKey: queryKeys.libraryJobs(id) });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.librariesRoot() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      ]);
    },
    onError: (error) => toast.error("Could not unregister library", errorMessage(error)),
  });

  return {
    createMutation,
    updateMutation,
    validateMutation,
    scanMutation,
    scanAllMutation,
    repairMutation,
    unregisterMutation,
  };
}
