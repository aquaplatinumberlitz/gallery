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

  const createMutation = useMutation({
    mutationFn: createLibrary,
    onSuccess: async () => {
      toast.success("Library created");
      await queryClient.invalidateQueries({ queryKey: queryKeys.librariesRoot() });
    },
    onError: (error) => toast.error("Could not create library", errorMessage(error)),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: UpdateVariables) => updateLibrary(id, payload),
    onSuccess: async (_library, { id }) => {
      toast.success("Library updated");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.library(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
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
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryProgress(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryJobs(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      ]);
    },
    onError: (error) => toast.error("Could not scan library", errorMessage(error)),
  });

  const scanAllMutation = useMutation({
    mutationFn: scanAllLibraries,
    onSuccess: async () => {
      toast.success("Library scans queued");
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() });
    },
    onError: (error) => toast.error("Could not scan libraries", errorMessage(error)),
  });

  const repairMutation = useMutation({
    mutationFn: repairLibrary,
    onSuccess: async (_response, id) => {
      toast.success("Library repaired");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryStats(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryJobs(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      ]);
    },
    onError: (error) => toast.error("Could not repair library", errorMessage(error)),
  });

  const unregisterMutation = useMutation({
    mutationFn: deleteLibrary,
    onSuccess: async () => {
      toast.success("Library unregistered");
      await queryClient.invalidateQueries({ queryKey: queryKeys.librariesRoot() });
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
