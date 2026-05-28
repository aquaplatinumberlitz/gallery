import { ref, onMounted, onBeforeUnmount } from 'vue'

const SCROLL_CONTAINER_SELECTOR = '.vue-recycle-scroller, .scroller, .folders-only-container'

export function useScrollVisibility() {
  const barsVisible = ref(true)
  const isScrollingDown = ref(false)
  let lastScrollY = 0
  let observer: MutationObserver | null = null
  let rafId = 0
  let intervalId: ReturnType<typeof setInterval> | null = null
  let cleanupScroll: (() => void) | null = null

  function attachToElement(el: HTMLElement) {
    const handler = () => {
      if (rafId) return
      rafId = requestAnimationFrame(() => {
        rafId = 0
        const st = el.scrollTop
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

  onMounted(() => {
    // Poll for the active scroll container (may not render immediately)
    intervalId = setInterval(() => {
      const el = document.querySelector<HTMLElement>(SCROLL_CONTAINER_SELECTOR)
      if (el && el.scrollHeight > el.clientHeight) {
        clearInterval(intervalId!)
        intervalId = null
        cleanupScroll = attachToElement(el)
        // Watch for DOM re-creation within the scroller's parent container
        const scrollerParent = el.parentElement
        if (scrollerParent) {
          observer = new MutationObserver(() => {
            const newEl = document.querySelector<HTMLElement>(SCROLL_CONTAINER_SELECTOR)
            if (newEl && newEl !== el) {
              cleanupScroll?.()
              cleanupScroll = attachToElement(newEl)
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
    cleanupScroll?.()
    cleanupScroll = null
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = 0
    }
  })

  return { barsVisible, isScrollingDown }
}
