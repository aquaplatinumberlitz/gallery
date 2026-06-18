import { mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, h, provide, type Component, type InjectionKey } from "vue";

/**
 * Test helper: mount a host component that runs a composable in its setup()
 * so lifecycle hooks (onMounted/onBeforeUnmount/watch) execute normally.
 *
 * Returns the composable result and the wrapper so tests can inspect the DOM
 * or unmount to trigger cleanup hooks.
 */
export function withSetup<T>(composable: () => T): { wrapper: VueWrapper<Component>; result: T } {
  let result!: T;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = composable();
        return () => h("div");
      },
    }),
  );
  return { wrapper, result };
}

/**
 * Variant of withSetup that lets the test inject provide() values for the
 * composable's inject() calls.
 */
export function withSetupAndProvides<T>(
  composable: () => T,
  provides: Array<[InjectionKey<unknown> | string, unknown]>,
): { wrapper: VueWrapper<Component>; result: T } {
  let result!: T;
  const wrapper = mount(
    defineComponent({
      setup() {
        for (const [key, value] of provides) provide(key, value);
        result = composable();
        return () => h("div");
      },
    }),
  );
  return { wrapper, result };
}
