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
  /** What the engagement is shown as (migration 051). */
  engagement_shown?: string | null;
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

export type PlanRow = { memo_id: number; recipient: string; kind: PlanKind };

export type Plan = {
  rows: PlanRow[];
  included: number;
  paid: number;
  resend: number;
  /** What one share past the allowance costs; null where it is not priced -
   *  and then a paid row cannot be sent at all. */
  unitCents: number | null;
  totalCents: number;
};

/** Which of a batch fall inside the allowance, which would be charged, and
 *  which are re-sends - in the order given.
 *
 *  A RE-SEND IS FREE. A memorandum already shared with this recipient is the
 *  same grant sent again (reinstated if revoked): no allowance, no charge -
 *  so it takes none of the remaining shares.
 *
 *  THE INCLUDED SHARES GO TO THE FIRST ROWS, so unticking a row re-plans the
 *  rest. Nothing here is a promise: the server counts each share as it
 *  arrives, and one that has become paid since this was planned is refused
 *  with its price rather than charged. */
function planPairs(pairs: { memo_id: number; recipient: string }[],
                   allowance: Allowance,
                   isResend: (memoId: number, recipient: string) => boolean): Plan {
  let left = allowance.allowance === null ? Infinity
                                          : Math.max(0, allowance.remaining ?? 0);
  const rows = pairs.map(({ memo_id, recipient }) => {
    let kind: PlanKind;
    if (isResend(memo_id, recipient)) kind = "resend";
    else if (left > 0) { kind = "included"; left -= 1; }
    else kind = "paid";
    return { memo_id, recipient, kind };
  });
  const count = (k: PlanKind) => rows.filter((r) => r.kind === k).length;
  const paid = count("paid");
  const unitCents = allowance.overage_cents;
  return { rows, included: count("included"), paid, resend: count("resend"),
           unitCents, totalCents: unitCents === null ? 0 : paid * unitCents };
}

/** One recipient: the memoranda in the order they were ticked. */
export function planBatch(selected: number[], allowance: Allowance,
                          resendIds: Set<number>, recipient = ""): Plan {
  return planPairs(selected.map((memo_id) => ({ memo_id, recipient })),
                   allowance, (id) => resendIds.has(id));
}

/** Several recipients (9 November 2026): every ticked memorandum to every
 *  recipient, each pair its own share. Recipient by recipient, so where the
 *  included shares run out, the first recipients have the whole batch. */
export function planShares(selected: number[], recipients: string[],
                           allowance: Allowance,
                           grants: { memo_id: number; recipient_email: string }[]):
    Plan {
  const sent = new Map(recipients.map((r) => [r, resendsFor(r, grants)]));
  return planPairs(
    recipients.flatMap((recipient) =>
      selected.map((memo_id) => ({ memo_id, recipient }))),
    allowance, (id, r) => sent.get(r)?.has(id) ?? false);
}

// --- recipients --------------------------------------------------------------

/** At most this many recipients for one batch. */
export const MAX_RECIPIENTS = 5;

const EMAIL = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/;

/** The recipient field read as a list: split on commas (or semicolons, as a
 *  mail client pastes them), trimmed, a repeat taken once ignoring case.
 *  `problem` says what keeps it from being sent, or is null. */
export function parseRecipients(text: string):
    { recipients: string[]; problem: string | null } {
  const seen = new Set<string>();
  const recipients: string[] = [];
  for (const part of text.split(/[,;]/)) {
    const address = part.trim();
    if (!address || seen.has(address.toLowerCase())) continue;
    seen.add(address.toLowerCase());
    recipients.push(address);
  }
  const bad = recipients.filter((a) => !EMAIL.test(a));
  if (bad.length > 0) {
    return { recipients, problem: `Not an email address: ${bad.join(", ")}.` };
  }
  if (recipients.length > MAX_RECIPIENTS) {
    return { recipients,
             problem: `At most ${MAX_RECIPIENTS} recipients at once; `
                      + `${recipients.length} are listed.` };
  }
  return { recipients, problem: null };
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

/** Share a memo's list: text over name, engagement and number, and over who
 *  each memo has been shared with and by (`sharedWith`, 31 October 2026);
 *  the date range over the date generated. */
export function filterMemos(memos: BatchMemo[], f: Filter,
                            sharedWith: (memoId: number) => string[] = () => []):
    BatchMemo[] {
  return memos.filter((m) =>
    matches([m.label, m.engagement_shown ?? m.engagement, m.subject_name,
             m.number, ...sharedWith(m.memo_id)], f.text)
    && inRange(m.generated_at, f));
}

/** Each memorandum's shares, newest first: who got it, when, and from whom. */
export function sharesByMemo<T extends { memo_id: number; sent_at: string }>(
    grants: T[]): Map<number, T[]> {
  const out = new Map<number, T[]>();
  for (const g of grants) out.set(g.memo_id, [...(out.get(g.memo_id) ?? []), g]);
  for (const list of out.values()) list.sort((a, b) => b.sent_at.localeCompare(a.sent_at));
  return out;
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
