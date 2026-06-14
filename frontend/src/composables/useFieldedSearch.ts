import { ref, computed } from 'vue'
import type { FieldFilter } from '@/types'
import { serializeAdvancedSearchToQuery } from '@/utils/serializeAdvancedSearchToQuery'

const fieldedFilters = ref<FieldFilter[]>([])

const cachedQueryString = ref<string>('')
let lastAppliedFilters = ''

function updateCache() {
  const serialized = JSON.stringify(fieldedFilters.value)
  if (serialized !== lastAppliedFilters) {
    lastAppliedFilters = serialized
    cachedQueryString.value = serializeAdvancedSearchToQuery(fieldedFilters.value)
  }
}

export function useFieldedSearch() {
  const isActive = computed(() => fieldedFilters.value.length > 0)

  const queryString = computed(() => {
    updateCache()
    return cachedQueryString.value
  })

  function applyFilters(filters: FieldFilter[]) {
    fieldedFilters.value = [...filters]
    updateCache()
  }

  function removeFilter(index: number) {
    const next = [...fieldedFilters.value]
    next.splice(index, 1)
    fieldedFilters.value = next
    updateCache()
  }

  function clearAll() {
    fieldedFilters.value = []
    cachedQueryString.value = ''
    lastAppliedFilters = ''
  }

  return {
    fieldedFilters,
    isActive,
    queryString,
    applyFilters,
    removeFilter,
    clearAll,
  }
}
