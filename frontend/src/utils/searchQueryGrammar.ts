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
  checkpoint: "model",
  location: "folder",
  resource: "lora",
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
  start: number;
  end: number;
}

export interface ParsedSearchQuery {
  residualText: string;
  managedFilters: FieldFilter[];
  passThroughTokens: string[];
}

function isWordCharacter(value: string): boolean {
  return /[\p{L}\p{N}_]/u.test(value);
}

function previousCodePoint(raw: string, start: number): string {
  if (start <= 0) return "";
  const previousUnit = raw.charCodeAt(start - 1);
  if (previousUnit >= 0xdc00 && previousUnit <= 0xdfff && start >= 2) {
    const leadingUnit = raw.charCodeAt(start - 2);
    if (leadingUnit >= 0xd800 && leadingUnit <= 0xdbff) return raw.slice(start - 2, start);
  }
  return raw[start - 1] ?? "";
}

function startsSupportedField(raw: string, start: number): boolean {
  let cursor = start;
  if (!/[A-Za-z_]/.test(raw[cursor] ?? "")) return false;
  cursor += 1;
  while (isWordCharacter(raw[cursor] ?? "")) cursor += 1;
  const field = raw.slice(start, cursor).toLowerCase();
  while (/\s/.test(raw[cursor] ?? "")) cursor += 1;
  return SUPPORTED_FIELDS.has(field) && raw[cursor] === ":";
}

function readToken(raw: string, start: number, allowAdjacentField = false): { token: QueryToken; end: number } | null {
  if (!allowAdjacentField && isWordCharacter(previousCodePoint(raw, start))) return null;

  let cursor = start;
  if (!/[A-Za-z_]/.test(raw[cursor] ?? "")) return null;
  cursor += 1;
  while (isWordCharacter(raw[cursor] ?? "")) cursor += 1;

  const fieldStart = start;
  const field = raw.slice(fieldStart, cursor).toLowerCase();
  const supportedField = SUPPORTED_FIELDS.has(field);
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
    const valueParts: string[] = [];
    while (cursor < raw.length) {
      const character = raw[cursor] ?? "";
      if (character === quote) break;
      if (character === "\\" && cursor + 1 < raw.length) {
        const nextCharacter = raw[cursor + 1] ?? "";
        if (nextCharacter === quote || nextCharacter === "\\") {
          valueParts.push(nextCharacter);
          cursor += 2;
          continue;
        }
      }
      valueParts.push(character);
      cursor += 1;
    }
    value = valueParts.join("");
    if (raw[cursor] === quote) cursor += 1;
  } else {
    const valueStart = cursor;
    while (cursor < raw.length && !/[\s"']/.test(raw[cursor] ?? "")) {
      if (supportedField && startsSupportedField(raw, cursor)) break;
      cursor += 1;
    }
    value = raw.slice(valueStart, cursor);
  }

  if (!supportedField) {
    return {
      token: { raw: raw.slice(start, cursor), filter: null, managed: false, start, end: cursor },
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
      start,
      end: cursor,
    },
    end: cursor,
  };
}

function tokenize(raw: string): { tokens: QueryToken[]; residualParts: string[] } {
  const tokens: QueryToken[] = [];
  const residualParts: string[] = [];
  let residualStart = 0;
  let cursor = 0;
  let allowAdjacentField = false;

  while (cursor < raw.length) {
    const parsed = readToken(raw, cursor, allowAdjacentField);
    if (!parsed) {
      allowAdjacentField = false;
      cursor += 1;
      continue;
    }
    const prefix = raw.slice(residualStart, cursor).trim();
    if (prefix) residualParts.push(prefix);
    tokens.push(parsed.token);
    cursor = parsed.end;
    residualStart = cursor;
    allowAdjacentField = parsed.token.filter !== null;
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
  const { tokens } = tokenize(raw);
  const managedTokens = tokens.filter((token) => token.managed);
  const replacement = serializeManagedFilters(filters);
  if (!managedTokens.length) return [raw.trim(), replacement].filter(Boolean).join(" ");

  const parts: string[] = [];
  let previousEnd = 0;
  managedTokens.forEach((token, index) => {
    const prefix = raw.slice(previousEnd, token.start).trim();
    if (prefix) parts.push(prefix);
    if (index === 0 && replacement) parts.push(replacement);
    previousEnd = token.end;
  });
  const tail = raw.slice(previousEnd).trim();
  if (tail) parts.push(tail);
  return parts.join(" ");
}

export function filterToDisplayString(filter: FieldFilter): string {
  return `${filter.field}:${serializedOperator(filter)}${quoteValue(filter.value)}`;
}
