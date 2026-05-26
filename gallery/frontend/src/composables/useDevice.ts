import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

export const BREAKPOINTS = {
  compact: 480,
  phone: 768,
  tablet: 1024,
} as const

export type Breakpoint = 'compact' | 'phone' | 'tablet' | 'desktop'

// Singleton state
let refCount = 0
const currentWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1024)
let resizeHandler: (() => void) | null = null

export function useDevice() {
  const breakpoint = computed<Breakpoint>(() => {
    const w = currentWidth.value
    if (w < BREAKPOINTS.compact) return 'compact'
    if (w < BREAKPOINTS.phone) return 'phone'
    if (w < BREAKPOINTS.tablet) return 'tablet'
    return 'desktop'
  })

  const isCompact = computed(() => breakpoint.value === 'compact')
  const isPhone = computed(() => breakpoint.value === 'phone')
  const isTablet = computed(() => breakpoint.value === 'tablet')
  const isDesktop = computed(() => breakpoint.value === 'desktop')
  const isMobile = computed(() => isCompact.value || isPhone.value)
  const isLargeScreen = computed(() => isTablet.value || isDesktop.value)

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

  return { breakpoint, isCompact, isPhone, isTablet, isDesktop, isMobile, isLargeScreen }
}
