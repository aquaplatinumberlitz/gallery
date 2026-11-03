/**
 * Purpose: Protect the metric-matched fallback of the header brand title (layout-shift guard, see fonts.css).
 * Guarantees: fonts.css declares "Cinzel Fallback" from local() sources only (nothing to download) with a
 * size-adjust, and AppHeader's `.brand-title` lists it right after Cinzel, so the title wraps the same before and
 * after the web font swaps in. The browser-level proof is tests/e2e/home-layout-shift.spec.ts.
 * Run when: Changing fonts.css, the brand title font stack, its text, weight or letter-spacing.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (relative: string) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

describe("brand title fallback font", () => {
  const fontsCss = read("../fonts.css");
  const face = fontsCss.slice(fontsCss.indexOf('font-family: "Cinzel Fallback"') - 20);
  const faceBlock = face.slice(0, face.indexOf("}") + 1);

  it("is a local()-only face with a size adjustment", () => {
    expect(faceBlock).toContain('font-family: "Cinzel Fallback"');
    expect(faceBlock).toMatch(/size-adjust:\s*\d+(\.\d+)?%/);
    expect(faceBlock).toContain('local("Times New Roman Bold")');
    expect(faceBlock).not.toContain("url(");
  });

  it("is used by the brand title right after Cinzel", () => {
    const header = read("../../components/AppHeader.vue");
    const rule = header.slice(header.indexOf(".brand-title {"));
    expect(rule.slice(0, rule.indexOf("}"))).toContain('font-family: "Cinzel", "Cinzel Fallback", serif;');
  });
});
