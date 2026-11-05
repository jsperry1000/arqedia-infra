import type { ShareGrant } from "./api";

/**
 * Addresses this workspace has shared with, for the recipient field
 * (5 November 2026). Decided: the workspace's sends - what the Sharing
 * history already shows anybody who can see it - not only the signed-in
 * person's. Read from the shares the form already loads; nothing new is
 * asked of the server.
 *
 * Most recent first, once each however it was typed, in the case it was last
 * sent to. Typing filters through the browser's own datalist.
 */
export function recipientSuggestions(grants: ShareGrant[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const recent = [...grants].sort((a, b) =>
    (b.sent_at ?? "").localeCompare(a.sent_at ?? ""));
  for (const g of recent) {
    const address = (g.recipient_email ?? "").trim();
    const key = address.toLowerCase();
    if (!address || seen.has(key)) continue;
    seen.add(key);
    out.push(address);
  }
  return out;
}
