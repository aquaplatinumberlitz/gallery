/**
 * Shared formatting utilities.
 */

/**
 * Format a byte count into a human-readable string (e.g. "1.5 GB").
 * Returns "0 B" for zero, "—" for invalid/negative/NaN/Infinity.
 */
export function formatBytes(bytes?: number): string {
  if (bytes === 0) return "0 B";
  if (!bytes || !Number.isFinite(bytes) || bytes < 0) return "\u2014";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}
