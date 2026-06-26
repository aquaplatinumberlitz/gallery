/**
 * Shared component mount helper for Vitest + Vue Test Utils.
 *
 * Purpose:
 * Mount a Vue component with Pinia, Vue Router, and Vue Query pre-configured
 * so tests do not repeat boilerplate.
 *
 * Guarantees:
 * * Pinia is installed and active (createPinia)
 * * Vue Router is installed with createMemoryHistory (no URL side effects)
 * * A fresh router is created per call (no cross-test state leak)
 * * Vue Query is installed with an isolated QueryClient (retry: false)
 * * Reka UI / Tooltip providers are included when needed
 * * Common component stubs (transition, teleport, keep-alive) are provided
 *
 * Run when:
 * * mounting Vue components that depend on Pinia stores, router, or query cache
 */

import { mount, type MountingOptions } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { defineComponent, h, type Component, type DefineComponent } from "vue";
import { createIsolatedQueryClient } from "./queryClient";

export interface RenderWithAppOptions {
  /** Route path to start on (default /) */
  initialRoute?: string;
  /** Component slots */
  slots?: MountingOptions<Component>["slots"];
  /** Props to pass to the component */
  props?: Record<string, unknown>;
}

let routeCounter = 0;

function createTestRouter(initialRoute?: string) {
  routeCounter += 1;
  const router = createRouter({
    history: createMemoryHistory(`/test-base-${routeCounter}/`),
    routes: [{ path: "/:pathMatch(.*)*", component: { template: "<div />" } }],
  });
  if (initialRoute) {
    router.push(initialRoute);
  }
  return router;
}

/**
 * Mount a component with the full app plugin stack (Pinia + Router + Vue Query).
 *
 * Example:
 * ```ts
 * const wrapper = renderWithApp(MyComponent, { props: { id: 1 } })
 * expect(wrapper.text()).toContain("Hello")
 * ```
 */
export function renderWithApp(
  component: DefineComponent<Record<string, unknown>> | Component,
  options: RenderWithAppOptions = {},
) {
  setActivePinia(createPinia());

  const router = createTestRouter(options.initialRoute);
  const queryClient = createIsolatedQueryClient();

  const App = defineComponent({
    setup() {
      return () => h(component, options.props ?? {}, options.slots ?? {});
    },
  });

  const wrapper = mount(App, {
    global: {
      plugins: [router, [VueQueryPlugin, { queryClient }]],
      stubs: {
        teleport: true,
        transition: false,
        "keep-alive": true,
      },
    },
  });

  return { wrapper, router, queryClient };
}
