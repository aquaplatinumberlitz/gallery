import { fireEvent, render } from "@testing-library/vue";
import { describe, expect, it, vi } from "vitest";
import { FocusScope } from "reka-ui";

describe("FocusScope", () => {
  it("traps focus inside scope when trapped=true (Tab wraps last→first)", async () => {
    const { container } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="true" :loop="true" data-testid="scope">
          <button id="btn-1">First</button>
          <button id="btn-2">Second</button>
          <button id="btn-3">Third</button>
        </FocusScope>
      `,
    });

    const btn1 = container.querySelector("#btn-1") as HTMLElement;
    const btn3 = container.querySelector("#btn-3") as HTMLElement;

    vi.useFakeTimers();
    btn1.focus();
    vi.runAllTimers();

    expect(document.activeElement).toBe(btn1);
    vi.useRealTimers();

    fireEvent.keyDown(btn3, { key: "Tab", shiftKey: false, bubbles: true });
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(btn1);
    });
  });

  it("traps focus inside scope when trapped=true (Shift+Tab wraps first→last)", async () => {
    const { container } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="true" :loop="true" data-testid="scope">
          <button id="btn-1">First</button>
          <button id="btn-2">Second</button>
          <button id="btn-3">Third</button>
        </FocusScope>
      `,
    });

    const btn1 = container.querySelector("#btn-1") as HTMLElement;
    const btn3 = container.querySelector("#btn-3") as HTMLElement;

    btn1.focus();

    fireEvent.keyDown(btn1, { key: "Tab", shiftKey: true, bubbles: true });
    expect(document.activeElement).toBe(btn3);
  });

  it("does not trap focus when trapped=false", async () => {
    const { container } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="false" :loop="false" data-testid="scope">
          <button id="btn-1">First</button>
          <button id="btn-2">Second</button>
        </FocusScope>
      `,
    });

    const outside = document.createElement("button");
    outside.id = "outside";
    document.body.appendChild(outside);

    const btn2 = container.querySelector("#btn-2") as HTMLElement;
    btn2.focus();

    fireEvent.keyDown(btn2, { key: "Tab", shiftKey: false, bubbles: true });
    expect(document.activeElement?.id).not.toBe("btn-1");
  });

  it("returns focus to trigger element on unmount", async () => {
    const trigger = document.createElement("button");
    trigger.id = "trigger";
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { unmount } = render({
      components: { FocusScope },
      template: `
        <FocusScope :trapped="true" :loop="true">
          <button id="inner">Inner</button>
        </FocusScope>
      `,
    });

    // FocusScope auto-focuses first tabbable on mount
    vi.useFakeTimers();
    await vi.runAllTimersAsync();
    expect(document.activeElement?.id).toBe("inner");

    unmount();
    // After unmount, FocusScope should restore focus to trigger
    await vi.waitFor(() => {
      expect(document.activeElement?.id).toBe("trigger");
    });
    vi.useRealTimers();
  });
});
