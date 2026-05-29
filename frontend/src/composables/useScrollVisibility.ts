import { ref, onMounted, onBeforeUnmount, watch, type Ref, type WatchStopHandle } from 'vue'

const SCROLL_SELECTOR = '.vue-recycle-scroller, .scroller, .folders-only-container'

export function useScrollVisibility(containerRef?: Ref<HTMLElement | null>) {
  const barsVisible = ref(true)
  const isScrollingDown = ref(false)
  let lastScrollY = 0
  let observer: MutationObserver | null = null
  let rafId = 0
  let intervalId: ReturnType<typeof setInterval> | null = null
  let cleanupScroll: (() => void) | null = null
  let stopContainerWatch: WatchStopHandle | null = null
  let attachedElement: HTMLElement | null = null

  function attachToElement(el: HTMLElement) {
    const handler = () => {
      if (rafId) return
      rafId = requestAnimationFrame(() => {
        rafId = 0
        const st = el.scrollTop

        // ★ BOTTOM GUARD: prevent toggle when near bottom
        // to avoid layout-shift / rubber-band feedback loop on iOS
        const nearBottom = el.scrollHeight - el.clientHeight - st < 150
        if (nearBottom && st > 0) {
          lastScrollY = st
          return
        }

        if (st <= 0) {
          barsVisible.value = true
          isScrollingDown.value = false
        } else if (st > lastScrollY) {
          barsVisible.value = false
          isScrollingDown.value = true
        } else if (st < lastScrollY) {
          barsVisible.value = true
          isScrollingDown.value = false
        }
        lastScrollY = st
      })
    }
    el.addEventListener('scroll', handler, { passive: true })
    return () => el.removeEventListener('scroll', handler)
  }

  function cleanupAttachedElement() {
    cleanupScroll?.()
    cleanupScroll = null
    attachedElement = null
  }

  function attach(el: HTMLElement) {
    if (attachedElement === el) return
    cleanupAttachedElement()
    attachedElement = el
    lastScrollY = el.scrollTop
    cleanupScroll = attachToElement(el)
  }

  onMounted(() => {
    if (containerRef) {
      stopContainerWatch = watch(
        containerRef,
        (el) => {
          if (el) {
            attach(el)
          } else {
            cleanupAttachedElement()
          }
        },
        { immediate: true }
      )
      return
    }

    // Poll for .vue-recycle-scroller (may not render immediately)
    intervalId = setInterval(() => {
      const el = document.querySelector<HTMLElement>(SCROLL_SELECTOR)
      if (el && el.scrollHeight > el.clientHeight) {
        clearInterval(intervalId!)
        intervalId = null
        attach(el)
        // Watch for DOM re-creation within the scroller's parent container
        const scrollerParent = el.parentElement
        if (scrollerParent) {
          observer = new MutationObserver(() => {
            const newEl = document.querySelector<HTMLElement>(SCROLL_SELECTOR)
            if (newEl) {
              attach(newEl)
            }
          })
          observer.observe(scrollerParent, { childList: true, subtree: true })
        }
      }
    }, 200)
  })

  onBeforeUnmount(() => {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
    observer?.disconnect()
    observer = null
    stopContainerWatch?.()
    stopContainerWatch = null
    cleanupAttachedElement()
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = 0
    }
  })

  return { barsVisible, isScrollingDown }
}
