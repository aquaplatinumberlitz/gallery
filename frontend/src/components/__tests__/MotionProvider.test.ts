/**
 * Purpose: Protect the motion-v feature setup that keeps layout/drag/pan code out of the mount-critical bundle.
 * Guarantees: MotionProvider provides the animation features so `m.*` elements still run `initial` -> `animate`; the
 * same element without the provider never animates (proof the provider matters); and no source file imports the full
 * `motion` component, which bundles the layout-projection, drag and pan features regardless of what the page uses.
 * Run when: Changing MotionProvider.vue, adding an animated element, or using motion `layout`, `drag` or `pan`.
 */
import { mount } from "@vue/test-utils";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { m } from "motion-v";
import { defineComponent, h } from "vue";
import { describe, expect, it } from "vitest";
import MotionProvider from "../MotionProvider.vue";

const Probe = defineComponent({
  setup: () => () =>
    h(m.div, {
      "data-testid": "probe",
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      transition: { duration: 0.01 },
    }),
});

const settle = async (el: HTMLElement) => {
  for (let i = 0; i < 60; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 20));
    if (el.style.opacity === "1") return;
  }
};

describe("MotionProvider", () => {
  it("lets m.* elements run their initial -> animate transition", async () => {
    const wrapper = mount(MotionProvider, { slots: { default: () => h(Probe) }, attachTo: document.body });
    const el = wrapper.get('[data-testid="probe"]').element as HTMLElement;
    expect(el.style.opacity).toBe("0");

    await settle(el);

    expect(el.style.opacity).toBe("1");
    wrapper.unmount();
  });

  it("is what makes the animation run: without the provider an m.* element stays at its initial style", async () => {
    const wrapper = mount(Probe, { attachTo: document.body });
    const el = wrapper.get('[data-testid="probe"]').element as HTMLElement;

    await settle(el);

    expect(el.style.opacity).toBe("0");
    wrapper.unmount();
  });
});

describe("motion-v imports", () => {
  const srcRoot = join(process.cwd(), "src") + "/"; // vitest runs from frontend/
  const sourceFiles = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return name === "__tests__" ? [] : sourceFiles(path);
      return /\.(vue|ts)$/.test(name) ? [path] : [];
    });

  it("never imports the full `motion` component (use `m` under MotionProvider)", () => {
    const offenders = sourceFiles(srcRoot).filter((file) => {
      const importLines = readFileSync(file, "utf8").match(/import\s*\{[^}]*\}\s*from\s*"motion-v";?/g) ?? [];
      return importLines.some((line) => /[{,\s]motion[,\s}]/.test(line));
    });

    expect(offenders.map((file) => file.slice(srcRoot.length))).toEqual([]);
  });

  it("keeps the animation features (LazyMotion, domAnimation) in MotionProvider.vue, loaded through loadMotionProvider", () => {
    const files = sourceFiles(srcRoot);
    const featureImporters = files.filter((file) =>
      /import\s*\{[^}]*\b(LazyMotion|domAnimation|domMax)\b[^}]*\}\s*from\s*"motion-v"/.test(
        readFileSync(file, "utf8"),
      ),
    );
    expect(featureImporters.map((file) => file.slice(srcRoot.length))).toEqual(["components/MotionProvider.vue"]);

    const staticProviderImports = files.filter((file) =>
      /^\s*import\s+\w+\s+from\s+["'][^"']*MotionProvider\.vue["']/m.test(readFileSync(file, "utf8")),
    );
    expect(staticProviderImports).toEqual([]);

    const main = readFileSync(join(srcRoot, "main.ts"), "utf8");
    expect(main).toMatch(/loadMotionProvider\(\)/);
  });
});
