/**
 * Share a memo, the parts that decide rather than draw
 * (feature/share-multi-memo). Plain functions, so they are tested without a
 * browser (shareBatch.test.ts).
 *
 * NOTHING HERE SENDS OR CHARGES. It decides which memoranda may be ticked,
 * which of a batch fall inside the allowance and which would be charged, and
 * how the two lists are sorted and filtered. The server still decides every
 * share for itself: it counts each one, and refuses any past the allowance
 * that was not sent with its price accepted.
 */

/** At most this many memoranda are shared at once. The server's own limits
 *  stand behind it: 20 shares a day, and POST /shares/notify takes 5. */
export const MAX_BATCH = 5;

export type BatchMemo = {
  memo_id: number;
  label: string;
  number: string;
  generated_at: string | null;
  engagement: string | null;
  subject_name: string | null;
  unsaved: boolean;
};

// --- ticking ---------------------------------------------------------------

/** The selection after ticking or unticking one memorandum, in the order
 *  they were ticked - which is the order the batch is planned and sent in.
 *  `refused` says why a tick did not take, so the screen can say so rather
 *  than quietly ignore the click. */
export function toggle(selected: number[], memo: BatchMemo):
    { selected: number[]; refused: string | null } {
  if (selected.includes(memo.memo_id)) {
    return { selected: selected.filter((id) => id !== memo.memo_id),
             refused: null };
  }
  if (memo.unsaved) {
    return { selected,
             refused: "That memo has unsaved changes. Save or discard them "
                      + "on the memo first: what is shared is the memo as "
                      + "saved." };
  }
  if (selected.length >= MAX_BATCH) {
    return { selected,
             refused: `At most ${MAX_BATCH} memoranda are shared at once. `
                      + "Untick one to choose another." };
  }
  return { selected: [...selected, memo.memo_id], refused: null };
}

// --- the shortfall plan ----------------------------------------------------

export type Allowance = {
  /** Null is unlimited, never zero. */
  allowance: number | null;
  remaining: number | null;
  overage_cents: number | null;
};

export type PlanKind = "included" | "paid" | "resend";

export type Plan = {
  rows: { memo_id: number; kind: PlanKind }[];
  included: number;
  paid: number;
  resend: number;
  /** What one share past the allowance costs; null where it is not priced -
   *  and then a paid row cannot be sent at all. */
  unitCents: number | null;
  totalCents: number;
};

/** Which of a batch fall inside the allowance, which would be charged, and
 *  which are re-sends - in the order they were ticked.
 *
 *  A RE-SEND IS FREE. A memorandum already shared with this recipient is the
 *  same grant sent again (reinstated if revoked): no allowance, no charge -
 *  so it takes none of the remaining shares.
 *
 *  THE INCLUDED SHARES GO TO THE FIRST ROWS, so unticking a row re-plans the
 *  rest. Nothing here is a promise: the server counts each share as it
 *  arrives, and one that has become paid since this was planned is refused
 *  with its price rather than charged. */
export function planBatch(selected: number[], allowance: Allowance,
                          resendIds: Set<number>): Plan {
  let left = allowance.allowance === null ? Infinity
                                          : Math.max(0, allowance.remaining ?? 0);
  const rows = selected.map((memo_id) => {
    let kind: PlanKind;
    if (resendIds.has(memo_id)) kind = "resend";
    else if (left > 0) { kind = "included"; left -= 1; }
    else kind = "paid";
    return { memo_id, kind };
  });
  const count = (k: PlanKind) => rows.filter((r) => r.kind === k).length;
  const paid = count("paid");
  const unitCents = allowance.overage_cents;
  return { rows, included: count("included"), paid, resend: count("resend"),
           unitCents, totalCents: unitCents === null ? 0 : paid * unitCents };
}

/** Memoranda already shared with this address - the re-sends of a batch. */
export function resendsFor(recipient: string,
                           grants: { memo_id: number; recipient_email: string }[]):
    Set<number> {
  const to = recipient.trim().toLowerCase();
  return new Set(grants.filter((g) => g.recipient_email.toLowerCase() === to)
                       .map((g) => g.memo_id));
}

// --- sorting and filtering ---------------------------------------------------

export type SortDir = "asc" | "desc";

/** Sorted by one column. Missing values sort last whichever way, so an
 *  unopened share never heads a list sorted by when it was opened. */
export function sortRows<T>(rows: T[], key: keyof T, dir: SortDir): T[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = a[key] as unknown;
    const y = b[key] as unknown;
    const xMissing = x === null || x === undefined || x === "";
    const yMissing = y === null || y === undefined || y === "";
    if (xMissing || yMissing) return xMissing === yMissing ? 0 : xMissing ? 1 : -1;
    if (typeof x === "number" && typeof y === "number") return sign * (x - y);
    return sign * String(x).localeCompare(String(y), undefined,
                                           { numeric: true, sensitivity: "base" });
  });
}

export type Filter = {
  /** Matched, ignoring case, against the row's text columns. */
  text: string;
  /** YYYY-MM-DD, inclusive at both ends; empty is open. */
  from: string;
  to: string;
};

export const NO_FILTER: Filter = { text: "", from: "", to: "" };

function inRange(when: string | null | undefined, f: Filter): boolean {
  if (!f.from && !f.to) return true;
  const day = (when ?? "").slice(0, 10);
  if (!day) return false;
  return (!f.from || day >= f.from) && (!f.to || day <= f.to);
}

function matches(fields: (string | null | undefined)[], text: string): boolean {
  const t = text.trim().toLowerCase();
  return !t || fields.some((v) => (v ?? "").toLowerCase().includes(t));
}

/** Share a memo's list: text over name, engagement and number; the date
 *  range over the date generated. */
export function filterMemos(memos: BatchMemo[], f: Filter): BatchMemo[] {
  return memos.filter((m) =>
    matches([m.label, m.engagement, m.subject_name, m.number], f.text)
    && inRange(m.generated_at, f));
}

export type HistoryRow = {
  recipient_email: string;
  memo_label: string;
  subject: string | null;
  sent_at: string;
};

/** History: text over recipient and memorandum; the date range over when it
 *  was sent. */
export function filterHistory<T extends HistoryRow>(grants: T[], f: Filter): T[] {
  return grants.filter((g) =>
    matches([g.recipient_email, g.memo_label, g.subject], f.text)
    && inRange(g.sent_at, f));
}
