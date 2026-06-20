import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getLibraryEventsUrl } from "@/services/api";
import { useLibraryEvents } from "../useLibraryEvents";

const EVENT_TYPES = ["job.updated", "library.progress", "job.completed", "job.failed"] as const;

vi.mock("@/services/api", async () => {
  const actual = await vi.importActual<typeof import("@/services/api")>("@/services/api");
  return {
    ...actual,
    getLibraryEventsUrl: vi.fn(),
  };
});

class MockEventSource {
  url: string;
  onopen: ((this: EventSource, ev: Event) => unknown) | null = null;
  onerror: ((this: EventSource, ev: Event) => unknown) | null = null;
  listeners: Record<string, EventListener> = {};
  readyState = 0;
  closed = false;

  constructor(url: string) {
    this.url = url;
    instances.push(this);
  }
  addEventListener(type: string, listener: EventListener) {
    this.listeners[type] = listener;
  }
  removeEventListener(type: string) {
    delete this.listeners[type];
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  emit(type: string, data: unknown) {
    const listener = this.listeners[type];
    if (listener) listener({ data: JSON.stringify(data) } as MessageEvent<string>);
  }
}

const instances: MockEventSource[] = [];

describe("useLibraryEvents", () => {
  let queryClient: QueryClient;
  let originalEventSource: typeof EventSource | undefined;
  const globalWithOptional = globalThis as { EventSource?: typeof EventSource };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getLibraryEventsUrl).mockReturnValue("https://api.example.test/api/events");
    instances.length = 0;
    originalEventSource = globalThis.EventSource;
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  });

  afterEach(() => {
    if (originalEventSource === undefined) delete globalWithOptional.EventSource;
    else globalThis.EventSource = originalEventSource;
  });

  function setup() {
    let events!: ReturnType<typeof useLibraryEvents>;
    const wrapper = mount(
      defineComponent({
        setup() {
          events = useLibraryEvents();
          return () => h("div");
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
    );
    return { events, wrapper };
  }

  it("constructs EventSource with URL from getLibraryEventsUrl (includes API_BASE prefix)", () => {
    const { wrapper } = setup();
    expect(getLibraryEventsUrl).toHaveBeenCalled();
    expect(instances.length).toBe(1);
    expect(instances[0].url).toBe("https://api.example.test/api/events");
    expect(instances[0].url).not.toBe("/api/events");
    wrapper.unmount();
  });

  it("listens to all named event types", () => {
    const { wrapper } = setup();
    const instance = instances[0];
    for (const eventType of EVENT_TYPES) {
      expect(instance.listeners[eventType]).toBeDefined();
    }
    wrapper.unmount();
  });

  it("transitions idle -> connecting -> connected on open", () => {
    const { events, wrapper } = setup();
    expect(events.connectionState.value).toBe("connecting");
    const instance = instances[0];
    instance.onopen?.call(instance as unknown as EventSource, new Event("open"));
    expect(events.connectionState.value).toBe("connected");
    expect(events.isConnected.value).toBe(true);
    expect(events.lastError.value).toBeNull();
    wrapper.unmount();
  });

  it("transitions to reconnecting on error and records the error", () => {
    const { events, wrapper } = setup();
    const instance = instances[0];
    instance.onopen?.call(instance as unknown as EventSource, new Event("open"));
    const errorEvent = new Event("error");
    instance.onerror?.call(instance as unknown as EventSource, errorEvent);
    expect(events.connectionState.value).toBe("reconnecting");
    expect(events.isConnected.value).toBe(false);
    expect(events.lastError.value).toBe(errorEvent);
    wrapper.unmount();
  });

  it("transitions to stopped and closes the source on stop()", () => {
    const { events, wrapper } = setup();
    const instance = instances[0];
    events.stop();
    expect(instance.closed).toBe(true);
    expect(events.connectionState.value).toBe("stopped");
    wrapper.unmount();
  });

  it("closes the source on unmount via onUnmounted", () => {
    const { wrapper } = setup();
    const instance = instances[0];
    wrapper.unmount();
    expect(instance.closed).toBe(true);
  });

  it("does not start a second source if one is already active", () => {
    const { events, wrapper } = setup();
    expect(instances.length).toBe(1);
    events.start();
    expect(instances.length).toBe(1);
    wrapper.unmount();
  });

  it("parses named event payloads and stores lastEvent", () => {
    const { events, wrapper } = setup();
    const instance = instances[0];
    const payload = {
      type: "job.updated",
      job_id: 7,
      library_id: 3,
      state: "running",
      progress_current: 5,
      progress_total: 10,
      message: "scanning",
      error: null,
      updated_at: 123456,
    };
    instance.emit("job.updated", payload);
    expect(events.lastEvent.value).toEqual(payload);
    wrapper.unmount();
  });

  it("records an error when an event payload is invalid JSON", () => {
    const { events, wrapper } = setup();
    const instance = instances[0];
    const listener = instance.listeners["job.updated"];
    expect(listener).toBeDefined();
    listener({ data: "{not valid json" } as MessageEvent<string>);
    expect(events.lastError.value).toBeInstanceOf(Error);
    expect(events.lastEvent.value).toBeNull();
    wrapper.unmount();
  });

  it("marks connection unavailable when EventSource is undefined", () => {
    const original = globalThis.EventSource;
    delete globalWithOptional.EventSource;
    try {
      let events!: ReturnType<typeof useLibraryEvents>;
      const wrapper = mount(
        defineComponent({
          setup() {
            events = useLibraryEvents();
            return () => h("div");
          },
        }),
        { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
      );
      expect(events.isAvailable.value).toBe(false);
      expect(events.connectionState.value).toBe("unavailable");
      wrapper.unmount();
    } finally {
      globalThis.EventSource = original;
    }
  });
});
