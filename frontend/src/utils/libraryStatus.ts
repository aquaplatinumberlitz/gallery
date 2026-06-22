export function formatLibraryTimestamp(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Never";
  const date = new Date(typeof value === "number" ? value * 1_000 : value);
  return Number.isNaN(date.getTime())
    ? "Unknown"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatAssetCount(value: number | null | undefined): string {
  return new Intl.NumberFormat().format(Math.max(0, value ?? 0));
}
