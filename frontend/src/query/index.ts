import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import type { App } from "vue";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function installVueQuery(app: App) {
  app.use(VueQueryPlugin, { queryClient });
}
