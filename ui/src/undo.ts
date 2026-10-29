import { parseBlocks } from "./memodoc";

/**
 * Undo in the memo (UNDO-01, docs/specs/undo_01_design_2026-10-14.md).
 *
 * A step holds the changed blocks only, as they were and as they became, and
 * the place they start. The last ten are kept with the working copy, so undo
 * survives a reload. Saving ends the history with the working copy.
 *
 * Plain functions, no React: Memo.tsx records and undoes through these.
 */

export type Act = "edit" | "add" | "split" | "delete" | "drop-empty" | "row"
  | "accept" | "put-back" | "discard" | "image" | "page-break";

export type Step = {
  act: Act;
  at: number;          // index of the first changed block
  before: string[];    // block sources as they were
  after: string[];     // block sources as they became
  // Only the acts that change more than the text carry these: each key as it
  // was before the act, null where the key was absent.
  accepted_by?: Record<string, number[] | null>;
  pending?: Record<string, number | null>;
  prompts?: Record<string, string | null>;
  // Proposed in the build, not in the design: Discard also ends an Update
  // that is out, and undoing it has to bring the run back.
  update_run?: string | null;
};

export const HISTORY_MAX = 10;

/** What the Undo control says it will undo. */
export const ACT_SAID: Record<Act, string> = {
  "edit": "an edit",
  "add": "add a paragraph",
  "split": "break a paragraph",
  "delete": "delete a block",
  "drop-empty": "remove an emptied block",
  "row": "a table row",
  "accept": "accept a rewrite",
  "put-back": "put back the original",
  "discard": "discard changes",
  "image": "put in an image",
  "page-break": "put in a page break",
};

/** The block sources of a text. Joined with "\n" they are the text again
 *  (serializeBlocks), so a step can name blocks by position. */
export function sourcesOf(markdown: string): string[] {
  return parseBlocks(markdown).map((b) => b.source);
}

/** The step from one text to the next: the blocks between their longest
 *  common head and tail. Null when the texts are the same. */
export function diffStep(act: Act, before: string, after: string): Step | null {
  if (before === after) return null;
  const a = sourcesOf(before);
  const b = sourcesOf(after);
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head++;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head
         && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail++;
  return { act, at: head, before: a.slice(head, a.length - tail),
           after: b.slice(head, b.length - tail) };
}

/** The text with a step taken back, or null when the blocks at the step's
 *  place are no longer what it left there - then nothing is changed. */
export function undoStep(markdown: string, step: Step): string | null {
  const now = sourcesOf(markdown);
  const end = step.at + step.after.length;
  if (end > now.length) return null;
  for (let i = 0; i < step.after.length; i++) {
    if (now[step.at + i] !== step.after[i]) return null;
  }
  return [...now.slice(0, step.at), ...step.before, ...now.slice(end)].join("\n");
}

/** The history with one more step, the oldest dropped past the limit. */
export function pushStep(history: Step[], step: Step): Step[] {
  return [...history, step].slice(-HISTORY_MAX);
}

/** A map with the keys a step carries put back as they were. */
export function restoreKeys<T>(current: Record<string, T>,
                               was: Record<string, T | null>): Record<string, T> {
  const next = { ...current };
  for (const [key, value] of Object.entries(was)) {
    if (value === null) delete next[key];
    else next[key] = value;
  }
  return next;
}

/**
 * The bytes the server writes for a value: Python's json.dumps with
 * ensure_ascii=False, whose separators are ", " and ": " - one byte more
 * per separator than JSON.stringify writes.
 */
export function storedSize(value: unknown): number {
  const text = JSON.stringify(value) ?? "";
  return new TextEncoder().encode(text).length + separators(value);
}

function separators(value: unknown): number {
  if (Array.isArray(value)) {
    return Math.max(value.length - 1, 0)
      + value.reduce((n: number, v) => n + separators(v), 0);
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value).filter(([, v]) => v !== undefined);
    // A comma between entries and a colon in each.
    return Math.max(entries.length - 1, 0) + entries.length
      + entries.reduce((n, [, v]) => n + separators(v), 0);
  }
  return 0;
}

/**
 * The working copy with the oldest steps dropped until it fits under the
 * server's cap, so the text is always written even when history cannot be.
 * `margin` is for what the server wraps it in: the address and the time.
 */
export function fitHistory<C extends { history: Step[] }>(
    copy: C, cap: number, margin: number): C {
  // Three bytes a character is the most UTF-8 takes for one UTF-16 unit, and
  // separators are fewer than characters: under this, nothing to measure.
  if (JSON.stringify(copy).length * 4 + margin <= cap) return copy;
  let fitted = copy;
  while (fitted.history.length > 0 && storedSize(fitted) + margin > cap) {
    fitted = { ...fitted, history: fitted.history.slice(1) };
  }
  return fitted;
}
