import { describe, expect, it, beforeEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import CopyButton from "../CopyButton.vue";

let copyTextMock = vi.fn();
let copyStatusMock: Record<string, boolean> = {};

vi.mock("@/composables/useClipboard", () => ({
  useClipboard: () => ({ copyStatus: { value: copyStatusMock }, copyText: copyTextMock }),
}));

function mountSubject(props: Record<string, unknown> = {}) {
  return mount(CopyButton, {
    props: {
      text: "/photos",
      copyId: "path",
      label: "Copy folder path",
      copiedLabel: "Folder path copied",
      ...props,
    },
    global: {
      stubs: {
        Tooltip: { template: "<span><slot /></span>" },
        TooltipTrigger: { template: "<span><slot /></span>" },
        TooltipContent: { template: "<span><slot /></span>" },
      },
    },
  });
}

describe("CopyButton", () => {
  beforeEach(() => {
    copyTextMock = vi.fn();
    copyStatusMock = {};
  });

  it("copies the provided text with the provided copy id", async () => {
    const wrapper = mountSubject();
    await wrapper.get("button").trigger("click");
    expect(copyTextMock).toHaveBeenCalledWith("/photos", "path");
  });

  it("uses the copied label while copy status is active", () => {
    copyStatusMock = { path: true };
    const wrapper = mountSubject();
    expect(wrapper.get("button").attributes("aria-label")).toBe("Folder path copied");
  });
});
