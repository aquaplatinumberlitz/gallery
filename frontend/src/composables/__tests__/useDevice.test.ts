import { describe, it, expect, beforeEach } from "vitest";
import { withSetup } from "@/test/withSetup";
import { useDevice } from "../useDevice";

describe("useDevice", () => {
  beforeEach(() => {
    window.innerWidth = 1200;
  });

  it("isCompact when width 479", () => {
    window.innerWidth = 479;
    const { result } = withSetup(() => useDevice());
    expect(result.isCompact.value).toBe(true);
    expect(result.isMobileOnly.value).toBe(false);
    expect(result.isTablet.value).toBe(false);
    expect(result.isDesktop.value).toBe(false);
    expect(result.isWide.value).toBe(false);
  });

  it("isMobileOnly when width 480", () => {
    window.innerWidth = 480;
    const { result } = withSetup(() => useDevice());
    expect(result.isMobileOnly.value).toBe(true);
    expect(result.isCompact.value).toBe(false);
    expect(result.isTablet.value).toBe(false);
  });

  it("isMobileOnly when width 767", () => {
    window.innerWidth = 767;
    const { result } = withSetup(() => useDevice());
    expect(result.isMobileOnly.value).toBe(true);
    expect(result.isCompact.value).toBe(false);
    expect(result.isTablet.value).toBe(false);
  });

  it("isTablet when width 768", () => {
    window.innerWidth = 768;
    const { result } = withSetup(() => useDevice());
    expect(result.isTablet.value).toBe(true);
    expect(result.isMobileOnly.value).toBe(false);
    expect(result.isDesktop.value).toBe(false);
  });

  it("isTablet when width 1199", () => {
    window.innerWidth = 1199;
    const { result } = withSetup(() => useDevice());
    expect(result.isTablet.value).toBe(true);
    expect(result.isMobileOnly.value).toBe(false);
    expect(result.isDesktop.value).toBe(false);
  });

  it("isDesktop when width 1200", () => {
    window.innerWidth = 1200;
    const { result } = withSetup(() => useDevice());
    expect(result.isDesktop.value).toBe(true);
    expect(result.isTablet.value).toBe(false);
    expect(result.isWide.value).toBe(false);
  });

  it("isDesktop when width 1439", () => {
    window.innerWidth = 1439;
    const { result } = withSetup(() => useDevice());
    expect(result.isDesktop.value).toBe(true);
    expect(result.isTablet.value).toBe(false);
    expect(result.isWide.value).toBe(false);
  });

  it("isWide when width 1440", () => {
    window.innerWidth = 1440;
    const { result } = withSetup(() => useDevice());
    expect(result.isWide.value).toBe(true);
    expect(result.isDesktop.value).toBe(false);
  });

  it("isMobile is true for compact and mobile widths", () => {
    window.innerWidth = 479;
    const { result } = withSetup(() => useDevice());
    expect(result.isMobile.value).toBe(true);

    window.innerWidth = 700;
    window.dispatchEvent(new Event("resize"));
    expect(result.isMobile.value).toBe(true);

    window.innerWidth = 768;
    window.dispatchEvent(new Event("resize"));
    expect(result.isMobile.value).toBe(false);
  });

  it("isLargeScreen is true for tablet, desktop, and wide", () => {
    window.innerWidth = 767;
    const { result } = withSetup(() => useDevice());
    expect(result.isLargeScreen.value).toBe(false);

    window.innerWidth = 768;
    window.dispatchEvent(new Event("resize"));
    expect(result.isLargeScreen.value).toBe(true);

    window.innerWidth = 1200;
    window.dispatchEvent(new Event("resize"));
    expect(result.isLargeScreen.value).toBe(true);

    window.innerWidth = 1440;
    window.dispatchEvent(new Event("resize"));
    expect(result.isLargeScreen.value).toBe(true);
  });

  it("breakpoint returns the correct string per breakpoint", () => {
    window.innerWidth = 200;
    const { result } = withSetup(() => useDevice());
    expect(result.breakpoint.value).toBe("compact");

    window.innerWidth = 500;
    window.dispatchEvent(new Event("resize"));
    expect(result.breakpoint.value).toBe("mobile");

    window.innerWidth = 1000;
    window.dispatchEvent(new Event("resize"));
    expect(result.breakpoint.value).toBe("tablet");

    window.innerWidth = 1300;
    window.dispatchEvent(new Event("resize"));
    expect(result.breakpoint.value).toBe("desktop");

    window.innerWidth = 2000;
    window.dispatchEvent(new Event("resize"));
    expect(result.breakpoint.value).toBe("wide");
  });
});
