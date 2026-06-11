/**
 * Eruda mobile debug console.
 * Enable via ?eruda=1 query param (persists to localStorage as 'gallery-debug-eruda').
 * Disable via ?eruda=0 (clears localStorage).
 * If no query param, falls back to localStorage value.
 * Guarded by import.meta.env.DEV — no-ops in production builds.
 */

const STORAGE_KEY = 'gallery-debug-eruda';

function shouldEnableEruda(): boolean {
  const params = new URLSearchParams(window.location.search);
  const erudaParam = params.get('eruda');

  if (erudaParam === '1') {
    localStorage.setItem(STORAGE_KEY, '1');
    return true;
  }
  if (erudaParam === '0') {
    localStorage.removeItem(STORAGE_KEY);
    return false;
  }

  // Fall back to localStorage
  return localStorage.getItem(STORAGE_KEY) === '1';
}

export async function initErudaDebug(): Promise<void> {
  if (!shouldEnableEruda()) {
    return;
  }

  // Avoid double init
  if ((window as any).eruda) {
    return;
  }

  try {
    const eruda = await import('eruda');
    eruda.default.init();
    console.log('[Eruda] Debug console initialized');
  } catch (err) {
    console.warn('[Eruda] Failed to load eruda:', err);
  }
}
