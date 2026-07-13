import type { FieldFilter } from "@/types";
import { filterToDisplayString, parseSearchQuery, serializeManagedFilters } from "./searchQueryGrammar";

export { filterToDisplayString };

export function serializeAdvancedSearchToQuery(filters: FieldFilter[]): string {
  return serializeManagedFilters(filters);
}

export function parseFieldedQuery(query: string): FieldFilter[] {
  return parseSearchQuery(query).managedFilters;
}
