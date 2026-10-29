import type { DocumentDetail } from "./api";

/**
 * What the footnote picker offers, found by fact, by document type or by name
 * (29 October 2026).
 *
 * A PERSON CITES A FACT, NOT A FILE. Writing "the facility is USD 2,000,000"
 * they know the figure and not which of eleven documents it came out of, so
 * searching by filename asked them to know the one thing they did not. Every
 * value read at filing already carries its document and, for a page-based
 * one, its page - so a fact found here brings the page with it and nobody
 * types one.
 *
 * ONE SEARCH, NO MODES. Every word typed must appear, in any order, in a
 * fact's label or value, or in a document's name or type. What answers is
 * grouped under its document type.
 *
 * THE MEMO'S OWN SOURCES, AND NOTHING ELSE, as before: the save refuses a
 * citation to any other document. Built from the values each source already
 * returns (GET /documents/{id}/values); nothing new is asked of the server.
 */

export type Source = { name: string; documentId: number };

/** One place a fact was read: the document, its page where it has one, and
 *  what was read there. */
export type Place = { name: string; page: number | null; values: string[] };

export type Fact = { label: string; places: Place[] };

export type TypeGroup = { type: string; documents: string[]; facts: Fact[] };

/** A document whose values could not be had, or are still on their way. */
export const TYPE_UNKNOWN = "Type not known";
/** Read, and given no type at filing. */
export const UNCLASSIFIED = "Not classified";

export function searchWords(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter(Boolean);
}

function matches(words: string[], text: string): boolean {
  const hay = text.toLowerCase();
  return words.every((w) => hay.includes(w));
}

/** The page a value was read from. A sheet or a section is not a page, and
 *  the citation it would need is not what a footnote here writes, so such a
 *  fact cites its file alone. */
export function pageOf(kind: string | null, index: number | null): number | null {
  return kind === "page" && index !== null && index > 0 ? index : null;
}

/**
 * The sources, and what matches the search in them, by document type.
 *
 * With nothing typed it is every source under its type, and no facts: a memo's
 * sources hold hundreds of values and a list of all of them is not a choice.
 * A document is listed when its name or type matches; a fact when its label or
 * value does, with every place it was read.
 */
export function groupByType(sources: Source[],
                            details: Record<number, DocumentDetail | undefined>,
                            query: string): TypeGroup[] {
  const words = searchWords(query);
  const groups = new Map<string, { documents: string[];
                                   facts: Map<string, Map<string, Place>> }>();
  const groupOf = (type: string) => {
    let g = groups.get(type);
    if (!g) groups.set(type, g = { documents: [], facts: new Map() });
    return g;
  };

  for (const source of sources) {
    const detail = details[source.documentId];
    const type = !detail ? TYPE_UNKNOWN : detail.document_type || UNCLASSIFIED;

    if (matches(words, source.name + " " + type)) {
      groupOf(type).documents.push(source.name);
    }
    if (!detail || words.length === 0) continue;

    for (const v of detail.values) {
      const value = (v.value ?? "").trim();
      if (!value || !matches(words, v.label + " " + value)) continue;
      const facts = groupOf(type).facts;
      let places = facts.get(v.label);
      if (!places) facts.set(v.label, places = new Map());
      const page = pageOf(v.locator_kind, v.locator_index);
      const key = source.name + "#" + (page ?? "");
      const place = places.get(key)
        ?? { name: source.name, page, values: [] };
      if (!place.values.includes(value)) place.values.push(value);
      places.set(key, place);
    }
  }

  const byName = (a: string, b: string) => a.localeCompare(b);
  return [...groups.entries()]
    .map(([type, g]) => ({
      type,
      documents: g.documents.sort(byName),
      facts: [...g.facts.entries()]
        .map(([label, places]) => ({
          label,
          places: [...places.values()].sort((a, b) =>
            byName(a.name, b.name) || (a.page ?? 0) - (b.page ?? 0)),
        }))
        .sort((a, b) => byName(a.label, b.label)),
    }))
    .filter((g) => g.documents.length > 0 || g.facts.length > 0)
    // Types by name; the ones not known yet at the foot.
    .sort((a, b) => (a.type === TYPE_UNKNOWN ? 1 : 0)
                    - (b.type === TYPE_UNKNOWN ? 1 : 0)
                    || byName(a.type, b.type));
}
