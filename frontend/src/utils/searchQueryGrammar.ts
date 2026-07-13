import type { FieldFilter } from "@/types";

const SUPPORTED_FIELDS = new Set([
  "prompt",
  "positive",
  "negative",
  "date",
  "generation_time",
  "gen_time",
  "source",
  "tool",
  "seed",
  "steps",
  "cfg",
  "cfg_scale",
  "sampler",
  "scheduler",
  "size",
  "width",
  "height",
  "aspect_ratio",
  "ratio",
  "model",
  "checkpoint",
  "model_hash",
  "model_or_hash",
  "lora",
  "resource",
  "resource_hash",
  "clip_skip",
  "hires_upscale",
  "hires_steps",
  "denoising_strength",
  "vae",
  "ensd",
  "aesthetic_score",
  "path",
  "folder",
  "location",
  "name",
  "param",
  "advanced",
  "raw",
]);

const MANAGED_FIELD_ALIASES: Record<string, string> = {
  positive: "prompt",
  cfg_scale: "cfg",
  aspect_ratio: "ratio",
  denoising: "denoising_strength",
  path: "folder",
};

const MANAGED_FIELDS = new Set([
  "prompt",
  "negative",
  "model",
  "folder",
  "name",
  "date",
  "sampler",
  "scheduler",
  "lora",
  "vae",
  "seed",
  "steps",
  "cfg",
  "clip_skip",
  "denoising_strength",
  "hires_upscale",
  "hires_steps",
  "width",
  "height",
  "size",
  "ratio",
  "param",
  "advanced",
  "raw",
]);

const LITERAL_FIELDS = new Set(["ratio", "size", "date"]);

interface QueryToken {
  raw: string;
  filter: FieldFilter | null;
  managed: boolean;
}

export interface ParsedSearchQuery {
  residualText: string;
  managedFilters: FieldFilter[];
  passThroughTokens: string[];
}

function isWordCharacter(value: string): boolean {
  return /[A-Za-z0-9_]/.test(value);
}

function unescapeValue(value: string): string {
  let result = "";
  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === "\\" && index + 1 < value.length) {
      result += value[index + 1];
      index += 1;
    } else {
      result += value[index];
    }
  }
  return result;
}

function readToken(raw: string, start: number): { token: QueryToken; end: number } | null {
  if (start > 0 && isWordCharacter(raw[start - 1] ?? "")) return null;

  let cursor = start;
  if (!/[A-Za-z_]/.test(raw[cursor] ?? "")) return null;
  cursor += 1;
  while (isWordCharacter(raw[cursor] ?? "")) cursor += 1;

  const fieldStart = start;
  const field = raw.slice(fieldStart, cursor).toLowerCase();
  while (/\s/.test(raw[cursor] ?? "")) cursor += 1;
  if (raw[cursor] !== ":") return null;
  cursor += 1;
  while (/\s/.test(raw[cursor] ?? "")) cursor += 1;

  let operator = "";
  const twoCharacterOperator = raw.slice(cursor, cursor + 2);
  if (twoCharacterOperator === ">=" || twoCharacterOperator === "<=") {
    operator = twoCharacterOperator;
    cursor += 2;
  } else if (raw[cursor] === ">" || raw[cursor] === "<" || raw[cursor] === "=") {
    operator = raw[cursor] ?? "";
    cursor += 1;
  }

  const quote = raw[cursor] === '"' || raw[cursor] === "'" ? raw[cursor] : "";
  let value: string;
  if (quote) {
    cursor += 1;
    const valueStart = cursor;
    let escaped = false;
    while (cursor < raw.length) {
      const character = raw[cursor] ?? "";
      if (!escaped && character === quote) break;
      escaped = !escaped && character === "\\";
      if (character !== "\\") escaped = false;
      cursor += 1;
    }
    value = unescapeValue(raw.slice(valueStart, cursor));
    if (raw[cursor] === quote) cursor += 1;
  } else {
    const valueStart = cursor;
    while (cursor < raw.length && !/\s/.test(raw[cursor] ?? "")) cursor += 1;
    value = unescapeValue(raw.slice(valueStart, cursor));
  }

  if (!SUPPORTED_FIELDS.has(field)) {
    return {
      token: { raw: raw.slice(start, cursor), filter: null, managed: false },
      end: cursor,
    };
  }

  const managedField = MANAGED_FIELD_ALIASES[field] ?? field;
  const managed = MANAGED_FIELDS.has(managedField);
  return {
    token: {
      raw: raw.slice(start, cursor),
      filter: { field: managedField, operator: operator || undefined, value },
      managed,
    },
    end: cursor,
  };
}

function tokenize(raw: string): { tokens: QueryToken[]; residualParts: string[] } {
  const tokens: QueryToken[] = [];
  const residualParts: string[] = [];
  let residualStart = 0;
  let cursor = 0;

  while (cursor < raw.length) {
    const parsed = readToken(raw, cursor);
    if (!parsed) {
      cursor += 1;
      continue;
    }
    const prefix = raw.slice(residualStart, cursor).trim();
    if (prefix) residualParts.push(prefix);
    tokens.push(parsed.token);
    cursor = parsed.end;
    residualStart = cursor;
  }

  const tail = raw.slice(residualStart).trim();
  if (tail) residualParts.push(tail);
  return { tokens, residualParts };
}

export function parseSearchQuery(raw: string): ParsedSearchQuery {
  const { tokens, residualParts } = tokenize(raw);
  const managedFilters: FieldFilter[] = [];
  const passThroughTokens: string[] = [];

  for (const token of tokens) {
    if (token.managed && token.filter) managedFilters.push(token.filter);
    else passThroughTokens.push(token.raw);
  }

  return {
    residualText: residualParts.join(" ").replace(/\s+/g, " ").trim(),
    managedFilters,
    passThroughTokens,
  };
}

function needsQuoting(value: string): boolean {
  return value.length === 0 || /\s|["'()\\]/u.test(value);
}

function quoteValue(value: string): string {
  if (!needsQuoting(value)) return value;
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function serializedOperator(filter: FieldFilter): string {
  return LITERAL_FIELDS.has(filter.field.toLowerCase()) ? "" : (filter.operator ?? "");
}

export function serializeManagedFilters(filters: FieldFilter[]): string {
  return filters.map((filter) => `${filter.field}:${serializedOperator(filter)}${quoteValue(filter.value)}`).join(" ");
}

export function replaceManagedFilters(raw: string, filters: FieldFilter[]): string {
  const parsed = parseSearchQuery(raw);
  return [parsed.residualText, ...parsed.passThroughTokens, serializeManagedFilters(filters)]
    .filter(Boolean)
    .join(" ")
    .trim();
}

export function filterToDisplayString(filter: FieldFilter): string {
  return `${filter.field}:${serializedOperator(filter)}${quoteValue(filter.value)}`;
}
