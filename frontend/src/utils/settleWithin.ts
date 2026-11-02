/**
 * Resolves when `promise` settles (fulfilled or rejected) or after `ms`, whichever comes first. Never rejects.
 *
 * `main.ts` uses it to hold the first mount until the library list has arrived, but only briefly: the sidebar,
 * breadcrumb and toolbar render differently before the active library is hydrated, and painting that state
 * first moved them (up to 81 px) when the list arrived a few dozen milliseconds later (CLS 0.04 on desktop).
 */
export function settleWithin(promise: PromiseLike<unknown>, ms: number): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    const done = () => {
      clearTimeout(timer);
      resolve();
    };
    promise.then(done, done);
  });
}
