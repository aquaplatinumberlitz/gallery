/**
 * Shared formatting utilities.
 */

/**
 * Format a byte count into a human-readable string (e.g. "1.5 GB").
 * Returns "0 B" for zero, "—" for invalid/negative/NaN/Infinity.
 */
export function formatPercent(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return "\u2014";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatFraction(numerator: number | undefined | null, denominator: number | undefined | null): string {
  const n = numerator ?? 0;
  const d = denominator ?? 0;
  if (d === 0) return `${n} / ${d}`;
  const pct = ((n / d) * 100).toFixed(1);
  return `${n} / ${d} (${pct}%)`;
}

export function formatBytes(bytes?: number): string {
  if (bytes === 0) return "0 B";
  if (!bytes || !Number.isFinite(bytes) || bytes < 0) return "\u2014";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}
