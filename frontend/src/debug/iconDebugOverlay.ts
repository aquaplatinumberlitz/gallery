/**
 * Purpose:
 * Provides a gated overlay for inspecting mobile and tablet SVG icon sizing.
 *
 * Guarantees:
 * * overlay UI is off unless DEV mode and ?iconDebug=1 are both active
 * * collected metrics are local DOM measurements and do not call backend APIs
 *
 * Run when:
 * * debugging tablet or mobile header icon sizing regressions
 * * changing responsive icon components, toolbar layout, or debug overlay boot
 */

interface SvgMetrics {
  index: number;
  tagName: string;
  className: string;
  attrWidth: string | null;
  attrHeight: string | null;
  attrStrokeWidth: string | null;
  computedWidth: number;
  computedHeight: number;
  computedStrokeWidth: number;
  rectWidth: number;
  rectHeight: number;
  buttonOpacity: number | null;
  buttonClass: string | null;
}

interface DebugData {
  viewport: {
    width: number;
    height: number;
    dpr: number;
    ua: string;
  };
  layout: {
    tabletHeader: boolean;
    tabletToolbar: boolean;
    mobileHeader: boolean;
    mobileBottomBar: boolean;
  };
  tabletHeaderIcons: SvgMetrics[];
  tabletToolbarIcons: SvgMetrics[];
}

function collectSvgMetrics(el: SVGElement, index: number): SvgMetrics {
  const s = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const button = el.closest("button");

  return {
    index,
    tagName: el.tagName,
    className: el.className?.toString?.() || "",
    attrWidth: el.getAttribute("width"),
    attrHeight: el.getAttribute("height"),
    attrStrokeWidth: el.getAttribute("stroke-width"),
    computedWidth: parseFloat(s.width) || 0,
    computedHeight: parseFloat(s.height) || 0,
    computedStrokeWidth: parseFloat(s.strokeWidth) || 0,
    rectWidth: Math.round(r.width * 100) / 100,
    rectHeight: Math.round(r.height * 100) / 100,
    buttonOpacity: button instanceof HTMLElement ? parseFloat(getComputedStyle(button).opacity) : null,
    buttonClass: button instanceof HTMLElement ? button.className : null,
  };
}

function collectData(): DebugData {
  return {
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      dpr: window.devicePixelRatio,
      ua: navigator.userAgent,
    },
    layout: {
      tabletHeader: !!document.querySelector(".tablet-header"),
      tabletToolbar: !!document.querySelector(".tablet-gallery-toolbar"),
      mobileHeader: !!document.querySelector(".mobile-header"),
      mobileBottomBar: !!document.querySelector(".mobile-floating-bottom-bar"),
    },
    tabletHeaderIcons: Array.from(document.querySelectorAll<SVGElement>(".tablet-header svg")).map(collectSvgMetrics),
    tabletToolbarIcons: Array.from(document.querySelectorAll<SVGElement>(".tablet-gallery-toolbar svg")).map(
      collectSvgMetrics,
    ),
  };
}

function buildOverlay(): { overlay: HTMLDivElement; textarea: HTMLTextAreaElement } {
  const overlay = document.createElement("div");

  const style = overlay.style;
  style.position = "fixed";
  style.top = "8px";
  style.right = "8px";
  style.zIndex = "99999";
  style.maxWidth = "90vw";
  style.maxHeight = "70vh";
  style.overflowY = "auto";
  style.background = "#1a1a2e";
  style.color = "#e0e0e0";
  style.fontFamily = "monospace";
  style.fontSize = "12px";
  style.padding = "10px";
  style.borderRadius = "6px";
  style.boxShadow = "0 4px 20px rgba(0,0,0,0.6)";
  style.display = "flex";
  style.flexDirection = "column";
  style.gap = "6px";

  const textarea = document.createElement("textarea");
  textarea.readOnly = true;
  textarea.rows = 15;
  textarea.style.fontFamily = "monospace";
  textarea.style.fontSize = "11px";
  textarea.style.background = "#0d0d1a";
  textarea.style.color = "#e0e0e0";
  textarea.style.border = "1px solid #444";
  textarea.style.borderRadius = "4px";
  textarea.style.padding = "6px";
  textarea.style.resize = "vertical";
  textarea.style.width = "100%";
  textarea.style.boxSizing = "border-box";

  const buttonRow = document.createElement("div");
  buttonRow.style.display = "flex";
  buttonRow.style.flexWrap = "wrap";
  buttonRow.style.gap = "2px";

  const makeButton = (text: string, onClick: () => void): HTMLButtonElement => {
    const btn = document.createElement("button");
    btn.textContent = text;
    btn.style.padding = "4px 8px";
    btn.style.margin = "2px";
    btn.style.cursor = "pointer";
    btn.style.fontSize = "12px";
    btn.style.background = "#333";
    btn.style.color = "#e0e0e0";
    btn.style.border = "1px solid #555";
    btn.style.borderRadius = "3px";
    btn.addEventListener("click", onClick);
    return btn;
  };

  const refresh = () => {
    textarea.value = JSON.stringify(collectData(), null, 2);
  };

  buttonRow.appendChild(makeButton("Refresh", refresh));

  buttonRow.appendChild(
    makeButton("Copy", () => {
      const json = textarea.value;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(json).catch(() => {
          textarea.select();
        });
      } else {
        textarea.select();
      }
    }),
  );

  buttonRow.appendChild(
    makeButton("Select", () => {
      textarea.select();
    }),
  );

  buttonRow.appendChild(
    makeButton("Force Header SVG 40px", () => {
      document.querySelectorAll<SVGElement>(".tablet-header svg").forEach((el) => {
        el.style.width = "40px";
        el.style.height = "40px";
        el.style.outline = "2px solid red";
      });
      refresh();
    }),
  );

  buttonRow.appendChild(
    makeButton("Force Toolbar SVG 40px", () => {
      document.querySelectorAll<SVGElement>(".tablet-gallery-toolbar svg").forEach((el) => {
        el.style.width = "40px";
        el.style.height = "40px";
        el.style.outline = "2px solid blue";
      });
      refresh();
    }),
  );

  buttonRow.appendChild(
    makeButton("Reset Inline Styles", () => {
      const reset = (sel: string) => {
        document.querySelectorAll<SVGElement>(sel).forEach((el) => {
          el.style.width = "";
          el.style.height = "";
          el.style.outline = "";
        });
      };
      reset(".tablet-header svg");
      reset(".tablet-gallery-toolbar svg");
      refresh();
    }),
  );

  buttonRow.appendChild(
    makeButton("Close", () => {
      overlay.remove();
    }),
  );

  overlay.appendChild(textarea);
  overlay.appendChild(buttonRow);

  refresh();

  return { overlay, textarea };
}

export function initIconDebugOverlay(): void {
  if (!import.meta.env.DEV) return;
  if (new URLSearchParams(window.location.search).get("iconDebug") !== "1") return;

  const { overlay } = buildOverlay();
  document.body.appendChild(overlay);
}
