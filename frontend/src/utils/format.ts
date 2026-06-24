/**
 * Shared formatting utilities.
 */

/**
 * Format a byte count into a human-readable string (e.g. "1.5 GB").
 * Returns "0 B" for falsy/zero values.
 */
export function formatBytes(bytes?: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}
