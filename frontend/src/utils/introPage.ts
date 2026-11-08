/**
 * Landing-page ("intro") selection for automatic mode.
 *
 * `/api/landing-pages` lists every theme folder under `frontend/public/landpage/`. Four of them are
 * seasonal and belong to their dates only; the rest are ordinary and are picked at random on any other day.
 */

/** Theme folders that are only shown on their own dates (slug -> date rule below). */
export const SEASONAL_SLUGS = ["birthday", "noel", "lunar_newyear", "newyear"] as const;
export type SeasonalSlug = (typeof SEASONAL_SLUGS)[number];

/** Folders that must never be offered, even if a build accidentally ships them. */
export const HIDDEN_SLUGS: readonly string[] = ["sample_test"];

/** `/landpage/<slug>/index.html` -> `<slug>` (null for anything that is not a theme page). */
export const landingPageSlug = (url: string): string | null => {
  const match = /\/landpage\/([^/]+)\//i.exec(url);
  return match ? match[1].toLowerCase() : null;
};

/** False only for hidden developer pages (any other URL is kept as is): shown in the Settings list, usable as the manual choice. */
export const isSelectableLandingPage = (url: string): boolean => {
  const slug = landingPageSlug(url);
  return slug === null || !HIDDEN_SLUGS.includes(slug);
};

const isLunarNewYear = (now: Date): boolean => {
  try {
    const formatter = new Intl.DateTimeFormat("en-u-ca-chinese", { month: "numeric", day: "numeric" });
    const parts = formatter.formatToParts(now);
    const month = Number(parts.find((p) => p.type === "month")?.value);
    const day = Number(parts.find((p) => p.type === "day")?.value);
    const isYearEnd = month === 12 && day >= 30;
    const isNewYear = month === 1 && day <= 3;
    return isYearEnd || isNewYear;
  } catch {
    return false;
  }
};

/** Birthday 3 Sep, Noel 24-25 Dec, Lunar New Year (Chinese calendar 30 Dec - 3 Jan), New Year 1 Jan. */
export const SEASONAL_DATE_RULES: Record<SeasonalSlug, (now: Date) => boolean> = {
  birthday: (now) => now.getMonth() === 8 && now.getDate() === 3,
  noel: (now) => now.getMonth() === 11 && (now.getDate() === 24 || now.getDate() === 25),
  lunar_newyear: isLunarNewYear,
  newyear: (now) => now.getMonth() === 0 && now.getDate() === 1,
};

const isSeasonalSlug = (slug: string | null): boolean => (SEASONAL_SLUGS as readonly (string | null)[]).includes(slug);

/**
 * Pick the intro page for automatic mode.
 *
 * On a seasonal date the matching page wins (when the build ships it). On every other day only ordinary
 * themes are candidates: seasonal pages and hidden developer pages are never picked at random.
 * Returns undefined when nothing qualifies, so the caller can skip the intro.
 */
export const pickIntroPage = (
  pages: readonly string[],
  now: Date = new Date(),
  random: () => number = Math.random,
): string | undefined => {
  const selectable = pages.filter(isSelectableLandingPage);

  for (const slug of SEASONAL_SLUGS) {
    if (!SEASONAL_DATE_RULES[slug](now)) continue;
    const seasonal = selectable.find((url) => landingPageSlug(url) === slug);
    if (seasonal) return seasonal;
  }

  const ordinary = selectable.filter((url) => !isSeasonalSlug(landingPageSlug(url)));
  if (ordinary.length === 0) return undefined;
  return ordinary[Math.min(ordinary.length - 1, Math.floor(random() * ordinary.length))];
};
