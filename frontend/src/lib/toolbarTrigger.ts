/**
 * Shared toolbar trigger class for dropdown/button triggers across
 * the main gallery and /metadata toolbars.
 *
 * Matches the shadcn SelectTrigger visual standard used by
 * "All prompts" / "All models" on the /metadata page.
 */
export const toolbarTriggerClass =
  "flex h-9 items-center justify-between gap-2 rounded-md border border-input bg-background px-3 text-sm font-normal text-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";
