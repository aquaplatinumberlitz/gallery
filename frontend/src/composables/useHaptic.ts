/**
 * Lightweight haptic feedback composable.
 * Wraps navigator.vibrate() with a guard — only fires when available.
 */
export function useHaptic() {
  const canVibrate = typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function';

  function light() {
    if (canVibrate) navigator.vibrate(10);
  }

  function medium() {
    if (canVibrate) navigator.vibrate(20);
  }

  return { light, medium, canVibrate };
}
