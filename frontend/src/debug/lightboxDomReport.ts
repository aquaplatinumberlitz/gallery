/**
 * Purpose:
 * Provides a manual PhotoSwipe DOM report for diagnosing lightbox visual layering.
 *
 * Guarantees:
 * * report is read-only and only prints current PhotoSwipe DOM state to the console
 * * the global hook can be registered without changing lightbox behavior
 *
 * Run when:
 * * debugging duplicate PhotoSwipe roots, visible images, or placeholders
 * * changing PhotoSwipe lifecycle, visual layers, or lightbox DOM diagnostics
 */

export function galleryLightboxDOMReport(): void {
  const pswpRoots = document.querySelectorAll(".pswp");
  console.group("%c Gallery Lightbox DOM Report", "font-weight:bold;font-size:1.1em;");

  console.log("---- .pswp roots ----");
  console.log("Count:", pswpRoots.length);
  if (pswpRoots.length !== 1) {
    console.warn("EXPECTED exactly 1 .pswp root, found", pswpRoots.length);
  }
  pswpRoots.forEach((el, i) => {
    console.log(`  [${i}]`, el, `(parent: ${(el.parentElement?.className ?? "none").slice(0, 60)})`);
  });

  console.log("---- .pswp__item ----");
  const items = document.querySelectorAll(".pswp__item");
  console.log("Count:", items.length);
  items.forEach((el, i) => {
    console.log(`  [${i}]`, el);
  });

  console.log("---- .pswp__img ----");
  const images = document.querySelectorAll<HTMLImageElement>(".pswp__img");
  console.log("Total count:", images.length);
  const visibleImages: HTMLImageElement[] = [];
  images.forEach((img, i) => {
    const rect = img.getBoundingClientRect();
    const style = getComputedStyle(img);
    const isVisible =
      style.display !== "none" &&
      parseFloat(style.opacity) > 0 &&
      style.visibility !== "hidden" &&
      rect.width > 0 &&
      rect.height > 0;
    if (isVisible) visibleImages.push(img);

    console.group(`  .pswp__img [${i}]`);
    console.log("  src:", img.src.slice(0, 120));
    console.log("  currentSrc:", img.currentSrc.slice(0, 120));
    console.log(
      "  boundingClientRect:",
      JSON.stringify({
        x: rect.x.toFixed(1),
        y: rect.y.toFixed(1),
        w: rect.width.toFixed(1),
        h: rect.height.toFixed(1),
      }),
    );
    console.log(
      "  computed:",
      JSON.stringify({
        display: style.display,
        opacity: style.opacity,
        visibility: style.visibility,
        transform: style.transform.slice(0, 60),
      }),
    );
    console.log("  parent classes:", img.parentElement?.className.slice(0, 120) ?? "none");
    console.log("  visible (heuristic):", isVisible);
    console.groupEnd();
  });

  console.log("---- .pswp__img--placeholder ----");
  const placeholders = document.querySelectorAll(".pswp__img--placeholder");
  console.log("Count:", placeholders.length);
  placeholders.forEach((el, i) => {
    console.log(`  [${i}]`, el, "boundingClientRect:", JSON.stringify(el.getBoundingClientRect()));
  });

  console.log("---- .pswp active-slide ----");
  const activeSlide = document.querySelector('.pswp__item--active, [aria-selected="true"]');
  console.log("Found:", !!activeSlide, activeSlide);

  console.log("---- Summary ----");
  console.log("pswp roots:", pswpRoots.length, "(expected 1)");
  console.log("total .pswp__img:", images.length);
  console.log("visible .pswp__img:", visibleImages.length);

  console.groupEnd();
}

export function registerLightboxDOMReport(): void {
  if (typeof window !== "undefined") {
    (window as any).__galleryLightboxDOMReport = galleryLightboxDOMReport;
  }
}
