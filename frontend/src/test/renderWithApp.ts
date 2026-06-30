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
import { TooltipProvider } from "@/components/ui/tooltip";
import { createIsolatedQueryClient } from "./queryClient";

/** Common options shared between sync and async render helpers. */
export interface RenderWithAppBaseOptions {
  slots?: MountingOptions<Component>["slots"];
  props?: Record<string, unknown>;
}

/** Options for the sync renderWithApp helper — does NOT support initialRoute. */
export interface RenderWithAppOptions extends RenderWithAppBaseOptions {
  /** {@inheritDoc} — renderWithApp does not support initialRoute. Use renderWithAppAsync. */
  initialRoute?: never;
}

/** Options for the async renderWithAppAsync helper — supports initialRoute. */
export interface RenderWithAppAsyncOptions extends RenderWithAppBaseOptions {
  initialRoute?: string;
}

let routeCounter = 0;

function createTestRouter() {
  routeCounter += 1;
  return createRouter({
    history: createMemoryHistory(`/test-base-${routeCounter}/`),
    routes: [{ path: "/:pathMatch(.*)*", component: { template: "<div />" } }],
  });
}

/**
 * Mount a component with the full app plugin stack (Pinia + Router + Vue Query).
 *
 * Does NOT accept `initialRoute`. For route-aware components use
 * `renderWithAppAsync`.
 *
 * Example:
 * ```ts
 * const { wrapper } = renderWithApp(MyComponent, { props: { id: 1 } })
 * expect(wrapper.text()).toContain("Hello")
 * ```
 */
export function renderWithApp(
  component: DefineComponent<Record<string, unknown>> | Component,
  options: RenderWithAppOptions = {},
) {
  if ("initialRoute" in options) {
    throw new Error("renderWithApp does not support initialRoute. Use renderWithAppAsync for route-aware components.");
  }
  setActivePinia(createPinia());

  const router = createTestRouter();
  const queryClient = createIsolatedQueryClient();

  const App = defineComponent({
    setup() {
      return () => h(TooltipProvider, null, { default: () => h(component, options.props ?? {}, options.slots ?? {}) });
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

/**
 * Async variant of renderWithApp that pushes the initial route and waits for
 * the router to be ready before mounting the component.
 *
 * Example:
 * ```ts
 * const { wrapper } = await renderWithAppAsync(MyComponent, { initialRoute: "/admin" })
 * ```
 */
export async function renderWithAppAsync(
  component: DefineComponent<Record<string, unknown>> | Component,
  options: RenderWithAppAsyncOptions = {},
) {
  setActivePinia(createPinia());

  const router = createTestRouter();
  const queryClient = createIsolatedQueryClient();

  if (options.initialRoute) {
    await router.push(options.initialRoute);
    await router.isReady();
  }

  const App = defineComponent({
    setup() {
      return () => h(TooltipProvider, null, { default: () => h(component, options.props ?? {}, options.slots ?? {}) });
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
