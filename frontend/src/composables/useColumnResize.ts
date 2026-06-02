import { computed, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from 'vue'
import { BREAKPOINTS } from './useDevice'

const GAP = 20
const GRID_SIZE_KEY = 'gallery-grid-size'

/**
 * Apple HIG-inspired 5-level thumbnail size / grid density mapping.
 * Level 1 (Compact) = 8 columns (smallest thumbnails)
 * Level 5 (Largest) = 4 columns (largest thumbnails)
 * Default: Level 3 (Medium) = 6 columns
 */
export const PHOTO_GRID_LEVELS = [
  { level: 1, label: 'Compact', columns: 8 },
  { level: 2, label: 'Small', columns: 7 },
  { level: 3, label: 'Medium', columns: 6 },
  { level: 4, label: 'Large', columns: 5 },
  { level: 5, label: 'Largest', columns: 4 },
] as const

export type PhotoGridLevel = (typeof PHOTO_GRID_LEVELS)[number]['level']
export const DEFAULT_PHOTO_GRID_LEVEL: PhotoGridLevel = 3

function levelToColumns(level: number): number {
  const entry = PHOTO_GRID_LEVELS.find(l => l.level === level)
  return entry?.columns ?? PHOTO_GRID_LEVELS[DEFAULT_PHOTO_GRID_LEVEL - 1].columns
}

/**
 * Migrate old localStorage value (1–8 raw column count) to new level-based value.
 * Old values 1,2,3 → default level 3 (6 cols, Medium).
 * Old values > 8 → clamp to 8 → level 1 (Compact).
 * Valid old values 4–8 map to the appropriate level.
 */
function migrateColumnsToLevel(stored: number): number {
  if (stored >= 1 && stored <= 3) return DEFAULT_PHOTO_GRID_LEVEL
  const clamped = Math.min(stored, 8)
  const entry = PHOTO_GRID_LEVELS.find(l => l.columns === clamped)
  return entry?.level ?? DEFAULT_PHOTO_GRID_LEVEL
}

function getDefaultLevel(): number {
  if (typeof window === 'undefined') return DEFAULT_PHOTO_GRID_LEVEL
  const w = window.innerWidth
  if (w >= BREAKPOINTS.desktop) return DEFAULT_PHOTO_GRID_LEVEL
  if (w >= BREAKPOINTS.mobile) return DEFAULT_PHOTO_GRID_LEVEL
  return DEFAULT_PHOTO_GRID_LEVEL
}

export function useColumnResize() {
  const sliderLevel = ref(getDefaultLevel())
  const rowHeight = ref(0)
  let resizeObserver: ResizeObserver | null = null
  const lastGridWidth = ref(0)

  /** Effective photo grid column count derived from slider level */
  const effectiveColumnCount = computed(() => levelToColumns(sliderLevel.value))

  /** Alias for backward compatibility with template bindings */
  const columnCount = effectiveColumnCount

  const loadGridSize = () => {
    if (typeof window === 'undefined') return
    try {
      const stored = Number(localStorage.getItem(GRID_SIZE_KEY))
      if (!Number.isNaN(stored)) {
        if (stored >= 1 && stored <= PHOTO_GRID_LEVELS.length) {
          // New level-based value (1-5)
          sliderLevel.value = stored as PhotoGridLevel
        } else {
          // Legacy raw column count — migrate
          sliderLevel.value = migrateColumnsToLevel(stored) as PhotoGridLevel
        }
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
    const totalGap = GAP * (effectiveColumnCount.value - 1)
    const itemWidth = (width - totalGap) / effectiveColumnCount.value
    rowHeight.value = itemWidth + GAP // include vertical gap
  }

  const setGridRef = (el: Element | ComponentPublicInstance | null) => {
    if (el && el instanceof HTMLElement) {
      if (resizeObserver) resizeObserver.disconnect()

      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0]
        if (entry) {
          recomputeRowHeight(entry.contentRect.width)
        }
      })

      resizeObserver.observe(el)
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

  watch(sliderLevel, (val: number) => {
    saveGridSize(val)
    if (lastGridWidth.value) {
      recomputeRowHeight(lastGridWidth.value)
    }
  })

  return {
    /** Slider level (1-5) for UI binding */
    sliderLevel,
    /** Effective column count derived from slider level */
    effectiveColumnCount,
    /** Alias for backward compatibility */
    columnCount,
    rowHeight,
    setGridRef,
    GAP,
  }
}
