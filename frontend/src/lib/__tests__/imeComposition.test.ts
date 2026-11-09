import { describe, expect, it } from "vitest";
import { isEnterCommit, isImeComposingEvent } from "@/lib/imeComposition";

// Regression for CJ-02: the Enter that confirms an IME candidate is not a submit.
const key = (init: KeyboardEventInit & { keyCode?: number }) => {
  const event = new KeyboardEvent("keydown", init);
  if (init.keyCode !== undefined) Object.defineProperty(event, "keyCode", { value: init.keyCode });
  return event;
};

describe("imeComposition", () => {
  it("treats keydown with isComposing as IME composition", () => {
    expect(isImeComposingEvent(key({ key: "Enter", isComposing: true }))).toBe(true);
  });

  it("treats keyCode 229 (Process) as IME composition", () => {
    expect(isImeComposingEvent(key({ key: "Process", keyCode: 229 }))).toBe(true);
  });

  it("does not treat a plain keydown as composition", () => {
    expect(isImeComposingEvent(key({ key: "Enter", keyCode: 13 }))).toBe(false);
  });

  it("commits only a plain Enter outside composition", () => {
    expect(isEnterCommit(key({ key: "Enter", keyCode: 13 }))).toBe(true);
    expect(isEnterCommit(key({ key: "Enter", isComposing: true }))).toBe(false);
    expect(isEnterCommit(key({ key: "Enter", keyCode: 229 }))).toBe(false);
    expect(isEnterCommit(key({ key: "a", keyCode: 65 }))).toBe(false);
  });
});
