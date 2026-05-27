import { ref, onMounted, onBeforeUnmount } from 'vue'

export function useScrollVisibility() {
  const barsVisible = ref(true)
  const isScrollingDown = ref(false)
  let lastScrollY = 0
  let observer: MutationObserver | null = null
  let rafId = 0

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
    // Poll for .vue-recycle-scroller (may not render immediately)
    const tryAttach = setInterval(() => {
      const el = document.querySelector<HTMLElement>('.vue-recycle-scroller')
      if (el && el.scrollHeight > el.clientHeight) {
        clearInterval(tryAttach)
        let cleanup = attachToElement(el)
        // Watch for DOM re-creation (key change on RecycleScroller)
        observer = new MutationObserver(() => {
          const newEl = document.querySelector<HTMLElement>('.vue-recycle-scroller')
          if (newEl && newEl !== el) {
            cleanup()
            cleanup = attachToElement(newEl)
          }
        })
        observer.observe(document.body, { childList: true, subtree: true })
      }
    }, 200)
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
  })

  return { barsVisible, isScrollingDown }
}
