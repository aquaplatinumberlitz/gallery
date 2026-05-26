import { onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from 'vue'

const GAP = 20
const MIN_COLS = 1
const MAX_COLS = 8
const GRID_SIZE_KEY = 'gallery-grid-size'

function getDefaultCols(): number {
  if (typeof window === 'undefined') return 4
  const w = window.innerWidth
  if (w >= 1024) return 5
  if (w > 640) return 3
  return 2
}

export function useColumnResize() {
  const columnCount = ref(getDefaultCols())
  const rowHeight = ref(0)
  let resizeObserver: ResizeObserver | null = null
  const lastGridWidth = ref(0)

  const loadGridSize = () => {
    if (typeof window === 'undefined') return
    const stored = Number(localStorage.getItem(GRID_SIZE_KEY))
    if (!Number.isNaN(stored) && stored >= MIN_COLS && stored <= MAX_COLS) {
      columnCount.value = stored
    }
  }

  const saveGridSize = (val: number) => {
    if (typeof window === 'undefined') return
    localStorage.setItem(GRID_SIZE_KEY, String(val))
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
