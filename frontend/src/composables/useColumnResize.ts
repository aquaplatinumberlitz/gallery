import { onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from 'vue'
import { BREAKPOINTS } from './useDevice'

const GAP = 20
const MIN_COLS = 1
const MAX_COLS = 8
const GRID_SIZE_KEY = 'gallery-grid-size'

function getDefaultCols(): number {
  if (typeof window === 'undefined') return 4
  const w = window.innerWidth
  if (w >= BREAKPOINTS.tablet) return 4
  if (w >= BREAKPOINTS.phone) return 3    // tablet: 768-1023px
  // Grid density threshold — not a device breakpoint.
  // At this width the grid can fit 3 columns without overflow.
  const GRID_THREE_COL_MIN_WIDTH = 460
  if (w >= GRID_THREE_COL_MIN_WIDTH) return 3  // large phone: 460-767px (e.g. iPhone Plus/Pro Max)
  if (w >= BREAKPOINTS.compact) return 2   // medium phone: 375-459px (iPhone standard)
  return 2                                  // small phone: <375px — still at least 2 columns
}

export function useColumnResize() {
  const columnCount = ref(getDefaultCols())
  const rowHeight = ref(0)
  let resizeObserver: ResizeObserver | null = null
  const lastGridWidth = ref(0)

  const loadGridSize = () => {
    if (typeof window === 'undefined') return
    try {
      const stored = Number(localStorage.getItem(GRID_SIZE_KEY))
      if (!Number.isNaN(stored) && stored >= MIN_COLS && stored <= MAX_COLS) {
        columnCount.value = stored
      }
    } catch (e) {
      // Safari Private Browsing — localStorage throws; use default
    }
  }

  const saveGridSize = (val: number) => {
    if (typeof window === 'undefined') return
    try {
      localStorage.setItem(GRID_SIZE_KEY, String(val))
    } catch (e) {
      // Safari Private Browsing — localStorage throws; silently ignore
    }
  }

  const recomputeRowHeight = (width: number) => {
    if (!width) return
    lastGridWidth.value = width
    const totalGap = GAP * (columnCount.value - 1)
    const itemWidth = (width - totalGap) / columnCount.value
    rowHeight.value = itemWidth + GAP // include vertical gap
  }

  const setGridRef = (el: Element | ComponentPublicInstance | null) => {
    if (el && el instanceof HTMLElement) {
      // Disconnect existing if any (though usually null here)
      if (resizeObserver) resizeObserver.disconnect()

      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0]
        if (entry) {
          recomputeRowHeight(entry.contentRect.width)
        }
      })

      resizeObserver.observe(el)
      // Initial compute
      const initialWidth = el.getBoundingClientRect().width
      if (initialWidth) {
        recomputeRowHeight(initialWidth)
      }
    } else {
      if (resizeObserver) {
        resizeObserver.disconnect()
        resizeObserver = null
      }
    }
  }

  onBeforeUnmount(() => {
    if (resizeObserver) resizeObserver.disconnect()
  })

  onMounted(() => {
    loadGridSize()
  })

  watch(columnCount, (val: number) => {
    saveGridSize(val)
    if (lastGridWidth.value) {
      recomputeRowHeight(lastGridWidth.value)
    }
  })

  return { columnCount, rowHeight, setGridRef, MIN_COLS, MAX_COLS, GAP }
}
