/**
 * Purpose: Detect IME (input method) composition for search inputs.
 * Guarantees: `isImeComposingEvent` is true for a keydown during composition (`isComposing`, or the legacy
 * `keyCode 229`). `isEnterCommit` is true only for a plain Enter outside composition, so the Enter that confirms an
 * IME candidate neither submits nor blurs the field (CJ-02).
 * Run when: Changing search-box keyboard or input handling. Covered by lib/__tests__/imeComposition.test.ts.
 */
export const isImeComposingEvent = (event: KeyboardEvent): boolean => event.isComposing || event.keyCode === 229;

export const isEnterCommit = (event: KeyboardEvent): boolean => event.key === "Enter" && !isImeComposingEvent(event);
