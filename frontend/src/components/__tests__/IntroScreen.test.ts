/**
 * Purpose:
 * Verify which landing page the intro screen shows in automatic, manual and forced mode.
 *
 * Guarantees:
 * * On an ordinary day automatic mode picks only ordinary themes (never a seasonal page or `sample_test`),
 *   whatever the random draw is.
 * * Seasonal pages appear only on their dates: birthday 3 Sep, Noel 24-25 Dec, New Year 1 Jan and Lunar New
 *   Year (Chinese calendar 30 Dec - 3 Jan); a missing seasonal page falls back to an ordinary theme.
 * * `sample_test` is never picked or used as a stale manual choice.
 * * With no ordinary theme the intro closes instead of showing a seasonal page out of season.
 *
 * Run when:
 * * changing IntroScreen.vue, utils/introPage.ts or the landing-page folder layout
 */
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import IntroScreen from "../IntroScreen.vue";
import { fetchLandingPages } from "../../services/api";

vi.mock("../../services/api", () => ({
  fetchLandingPages: vi.fn(),
}));

const PAGES = [
  "/landpage/newyear/index.html",
  "/landpage/birthday/index.html",
  "/landpage/sample_test/index.html",
  "/landpage/eiga/index.html",
  "/landpage/lunar_newyear/index.html",
  "/landpage/normal_mouse/index.html",
  "/landpage/normal_angel/index.html",
  "/landpage/noel/index.html",
];
const ORDINARY = [
  "/landpage/eiga/index.html",
  "/landpage/normal_mouse/index.html",
  "/landpage/normal_angel/index.html",
];

const RANDOM_DRAWS = [0, 0.1, 0.25, 0.34, 0.5, 0.67, 0.75, 0.9, 0.999999];

const setDay = (year: number, month: number, day: number) => {
  // Local noon, so the calendar date is the same in every time zone.
  vi.setSystemTime(new Date(year, month - 1, day, 12, 0, 0));
};

const shownPages = async (draws: number[] = RANDOM_DRAWS, pages: string[] = PAGES): Promise<(string | null)[]> => {
  const shown: (string | null)[] = [];
  for (const draw of draws) {
    vi.mocked(fetchLandingPages).mockResolvedValue(pages);
    vi.spyOn(Math, "random").mockReturnValue(draw);
    const wrapper = mount(IntroScreen, { props: { visible: true } });
    await flushPromises();
    shown.push(wrapper.find("iframe").exists() ? (wrapper.find("iframe").attributes("src") ?? null) : null);
    wrapper.unmount();
  }
  return shown;
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  localStorage.clear();
  vi.mocked(fetchLandingPages).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("IntroScreen automatic mode", () => {
  it.each([
    ["an ordinary Sunday in November", 2026, 11, 8],
    ["the day before the birthday", 2026, 9, 2],
    ["the day after the birthday", 2026, 9, 4],
    ["the day before Noel", 2026, 12, 23],
    ["the day after Noel", 2026, 12, 26],
    ["2 January", 2027, 1, 2],
    ["a day in the middle of the lunar year", 2027, 5, 20],
  ])("picks only ordinary themes on %s", async (_label, y, m, d) => {
    setDay(y, m, d);
    const shown = await shownPages();
    expect(new Set(shown)).toEqual(new Set(ORDINARY));
  });

  it("can reach every ordinary theme and nothing else across the random range", async () => {
    setDay(2026, 11, 8);
    const shown = await shownPages();
    for (const url of ORDINARY) expect(shown).toContain(url);
    expect(shown.filter((u) => u && !ORDINARY.includes(u))).toEqual([]);
  });

  it.each([
    ["the birthday (3 September)", 2026, 9, 3, "/landpage/birthday/index.html"],
    ["Christmas Eve", 2026, 12, 24, "/landpage/noel/index.html"],
    ["Christmas Day", 2026, 12, 25, "/landpage/noel/index.html"],
    ["New Year's Day", 2027, 1, 1, "/landpage/newyear/index.html"],
    ["Lunar New Year's Day 2027 (6 Feb)", 2027, 2, 6, "/landpage/lunar_newyear/index.html"],
    ["the third day of Lunar New Year 2027", 2027, 2, 8, "/landpage/lunar_newyear/index.html"],
  ])("shows the seasonal page on %s", async (_label, y, m, d, expected) => {
    setDay(y, m, d);
    const shown = await shownPages([0, 0.5, 0.999999]);
    expect(shown).toEqual([expected, expected, expected]);
  });

  it("falls back to an ordinary theme when the seasonal page is not shipped", async () => {
    setDay(2026, 9, 3);
    const withoutBirthday = PAGES.filter((p) => !p.includes("/birthday/"));
    const shown = await shownPages([0, 0.5, 0.999999], withoutBirthday);
    expect(shown.every((u) => u && ORDINARY.includes(u))).toBe(true);
  });

  it("never picks sample_test, even when it is the only page", async () => {
    setDay(2026, 11, 8);
    vi.mocked(fetchLandingPages).mockResolvedValue(["/landpage/sample_test/index.html"]);
    const wrapper = mount(IntroScreen, { props: { visible: true } });
    await flushPromises();
    expect(wrapper.find("iframe").exists()).toBe(false);
    expect(wrapper.emitted("update:visible")?.at(-1)).toEqual([false]);
  });

  it("does not show a seasonal page out of season when it is the only page", async () => {
    setDay(2026, 11, 8);
    vi.mocked(fetchLandingPages).mockResolvedValue(["/landpage/noel/index.html"]);
    const wrapper = mount(IntroScreen, { props: { visible: true } });
    await flushPromises();
    expect(wrapper.find("iframe").exists()).toBe(false);
    expect(wrapper.emitted("update:visible")?.at(-1)).toEqual([false]);
  });
});

describe("IntroScreen manual and forced mode", () => {
  it("shows a seasonal theme the user chose manually, on any day", async () => {
    setDay(2026, 11, 8);
    localStorage.setItem("intro_mode", "manual");
    localStorage.setItem("intro_theme", "/landpage/noel/index.html");
    const wrapper = mount(IntroScreen, { props: { visible: true } });
    await flushPromises();
    expect(wrapper.find("iframe").attributes("src")).toBe("/landpage/noel/index.html");
    expect(fetchLandingPages).not.toHaveBeenCalled();
  });

  it("ignores a stale manual choice of sample_test and falls back to automatic mode", async () => {
    setDay(2026, 11, 8);
    localStorage.setItem("intro_mode", "manual");
    localStorage.setItem("intro_theme", "/landpage/sample_test/index.html");
    vi.mocked(fetchLandingPages).mockResolvedValue(PAGES);
    vi.spyOn(Math, "random").mockReturnValue(0);
    const wrapper = mount(IntroScreen, { props: { visible: true } });
    await flushPromises();
    const src = wrapper.find("iframe").attributes("src");
    expect(src).not.toContain("sample_test");
    expect(ORDINARY).toContain(src);
  });

  it("closes when the intro is disabled", async () => {
    localStorage.setItem("intro_mode", "disabled");
    const wrapper = mount(IntroScreen, { props: { visible: true } });
    await flushPromises();
    expect(wrapper.emitted("update:visible")?.at(-1)).toEqual([false]);
    expect(fetchLandingPages).not.toHaveBeenCalled();
  });

  it("shows the forced preview URL without asking the API", async () => {
    const wrapper = mount(IntroScreen, { props: { visible: true, forceUrl: "/landpage/eiga/index.html" } });
    await flushPromises();
    expect(wrapper.find("iframe").attributes("src")).toBe("/landpage/eiga/index.html");
    expect(fetchLandingPages).not.toHaveBeenCalled();
  });
});
