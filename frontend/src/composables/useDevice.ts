import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

// Source-of-truth breakpoints — also exists as SCSS vars in _breakpoints.scss
export const BREAKPOINTS = {
  compact: 480,
  mobile: 768,
  desktop: 1200,
  wide: 1440,
} as const

export type Breakpoint = 'compact' | 'mobile' | 'tablet' | 'desktop' | 'wide'

// Singleton state
let refCount = 0
const currentWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1200)
let resizeHandler: (() => void) | null = null

export function useDevice() {
  const breakpoint = computed<Breakpoint>(() => {
    const w = currentWidth.value
    if (w < BREAKPOINTS.compact) return 'compact'
    if (w < BREAKPOINTS.mobile) return 'mobile'
    if (w < BREAKPOINTS.desktop) return 'tablet'
    if (w < BREAKPOINTS.wide) return 'desktop'
    return 'wide'
  })

  const isCompact = computed(() => breakpoint.value === 'compact')
  const isMobileOnly = computed(() => breakpoint.value === 'mobile')
  const isTablet = computed(() => breakpoint.value === 'tablet')
  const isDesktop = computed(() => breakpoint.value === 'desktop')
  const isWide = computed(() => breakpoint.value === 'wide')
  const isMobile = computed(() => isCompact.value || isMobileOnly.value)
  const isLargeScreen = computed(() => isTablet.value || isDesktop.value || isWide.value)

  onMounted(() => {
    refCount++
    if (refCount === 1) {
      // First subscriber — start listening
      resizeHandler = () => { currentWidth.value = window.innerWidth }
      window.addEventListener('resize', resizeHandler, { passive: true })
    }
  })

  onBeforeUnmount(() => {
    refCount--
    if (refCount === 0 && resizeHandler) {
      window.removeEventListener('resize', resizeHandler)
      resizeHandler = null
    }
  })

  return { breakpoint, isCompact, isMobileOnly, isTablet, isDesktop, isWide, isMobile, isLargeScreen }
}
