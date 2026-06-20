import { useQueryClient } from "@tanstack/vue-query";
import { computed, onMounted, onUnmounted, ref, shallowRef } from "vue";
import { getLibraryEventsUrl } from "@/services/api";
import { queryKeys } from "@/query/keys";
import type { LibraryJobState, LibraryState } from "@/types";

type LibraryEventType = "job.updated" | "library.progress" | "job.completed" | "job.failed";

interface LibraryEventPayload {
  type: LibraryEventType;
  job_id: number | null;
  library_id: number | null;
  state: LibraryJobState | LibraryState | string;
  progress_current: number;
  progress_total: number | null;
  message: string | null;
  error: string | null;
  updated_at: number;
}

const EVENT_TYPES: LibraryEventType[] = ["job.updated", "library.progress", "job.completed", "job.failed"];

export function useLibraryEvents() {
  const queryClient = useQueryClient();
  const source = shallowRef<EventSource | null>(null);
  const connectionState = ref<"idle" | "connecting" | "connected" | "reconnecting" | "stopped" | "unavailable">("idle");
  const lastEvent = shallowRef<LibraryEventPayload | null>(null);
  const lastError = shallowRef<Event | Error | null>(null);
  const isAvailable = computed(() => typeof EventSource !== "undefined");
  const isConnected = computed(() => connectionState.value === "connected");

  async function invalidateForEvent(payload: LibraryEventPayload) {
    const invalidations = [
      queryClient.invalidateQueries({ queryKey: queryKeys.jobsRoot() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.libraries() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.galleryStats() }),
    ];

    if (payload.job_id) {
      invalidations.push(queryClient.invalidateQueries({ queryKey: queryKeys.job(payload.job_id) }));
    }
    if (payload.library_id) {
      invalidations.push(
        queryClient.invalidateQueries({ queryKey: queryKeys.library(payload.library_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryProgress(payload.library_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryStats(payload.library_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.libraryJobs(payload.library_id) }),
      );
    }
    await Promise.all(invalidations);
  }

  function handleMessage(event: MessageEvent<string>) {
    try {
      const payload = JSON.parse(event.data) as LibraryEventPayload;
      lastEvent.value = payload;
      lastError.value = null;
      void invalidateForEvent(payload);
    } catch (error) {
      lastError.value = error instanceof Error ? error : new Error("Invalid library event payload");
    }
  }

  function start() {
    if (source.value || typeof EventSource === "undefined") {
      if (typeof EventSource === "undefined") connectionState.value = "unavailable";
      return;
    }

    connectionState.value = "connecting";
    const eventSource = new EventSource(getLibraryEventsUrl());
    source.value = eventSource;
    eventSource.onopen = () => {
      connectionState.value = "connected";
      lastError.value = null;
    };
    eventSource.onerror = (event) => {
      connectionState.value = "reconnecting";
      lastError.value = event;
    };
    for (const eventType of EVENT_TYPES) eventSource.addEventListener(eventType, handleMessage as EventListener);
  }

  function stop() {
    source.value?.close();
    source.value = null;
    connectionState.value = "stopped";
  }

  onMounted(start);
  onUnmounted(stop);

  return { connectionState, isAvailable, isConnected, lastEvent, lastError, start, stop };
}
