import type { FieldFilter } from '@/types'

function needsQuoting(value: string): boolean {
  return /\s/.test(value) || /["()]/.test(value)
}

function quoteValue(value: string): string {
  if (needsQuoting(value)) {
    const escaped = value.replace(/"/g, '\\"')
    return `"${escaped}"`
  }
  return value
}

export function serializeAdvancedSearchToQuery(filters: FieldFilter[]): string {
  return filters
    .map((f) => {
      const op = f.operator || ''
      const val = quoteValue(f.value)
      return `${f.field}:${op}${val}`
    })
    .join(' ')
}

export function filterToDisplayString(filter: FieldFilter): string {
  const op = filter.operator || ''
  let displayValue = filter.value
  if (needsQuoting(filter.value)) {
    displayValue = `"${filter.value}"`
  }
  return `${filter.field}:${op}${displayValue}`
}

const FIELDED_TOKEN_RE =
  /([a-z_]+)(:)(>=?|<=?|=)?(?:"((?:[^"\\]|\\.)*)"|(\S+))/gi

export function parseFieldedQuery(q: string): FieldFilter[] {
  const filters: FieldFilter[] = []
  const matches = q.matchAll(FIELDED_TOKEN_RE)
  for (const m of matches) {
    const field = m[1]!.toLowerCase()
    const operator = m[3] || undefined
    const value = m[4] !== undefined ? m[4]!.replace(/\\"/g, '"') : m[5]!
    filters.push({ field, operator, value })
  }
  return filters
}
