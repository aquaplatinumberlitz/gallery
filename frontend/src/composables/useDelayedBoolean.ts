import { ref, watch, onBeforeUnmount, type Ref } from "vue";

export function useDelayedBoolean(source: Ref<boolean>, delayMs = 250) {
  const delayed = ref(false)
  let timer: number | undefined

  watch(source, (value) => {
    if (timer) window.clearTimeout(timer)
    if (!value) {
      delayed.value = false
      return
    }
    timer = window.setTimeout(() => { delayed.value = true }, delayMs)
  }, { immediate: true })

  onBeforeUnmount(() => { if (timer) window.clearTimeout(timer) })

  return delayed
}
