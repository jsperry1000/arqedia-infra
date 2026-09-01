"""Group the documents on Configure by their group, alphabetical within it.

The table lists document types in whatever order the draft returns them, which
for a forked pack is insertion order. Twenty-seven rows with a Group column
that repeats, and no way to find a document by name.

Categories keep the order the configuration gives them - a tenant who has
ordered their groups deliberately keeps that order - and only the documents
inside each are sorted. To alphabetise the groups as well, sort
draft.categories by label in the memo below.

Run from c:\\terraform\\arqedia.
"""

import io
import re
import sys


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def once(text, pattern, replacement, label, flags=0):
    found = re.findall(pattern, text, flags)
    if len(found) != 1:
        sys.exit("ANCHOR %s matched %d times, expected 1" % (label, len(found)))
    return re.sub(pattern, lambda _m: replacement, text, count=1, flags=flags)


# --- ui/src/Configure.tsx ---------------------------------------------------

P = "ui/src/Configure.tsx"
s = read(P)

if "documentGroups" in s:
    sys.exit("already patched")

s = once(
    s,
    r'import \{ useEffect, useMemo, useState \} from "react";',
    'import { Fragment, useEffect, useMemo, useState } from "react";',
    "react import",
)

GROUPS = '''  // Documents as they are grouped for the person who has to say what one is,
  // and alphabetical within each group. Categories keep the order the
  // configuration gives them, because a tenant who has ordered their groups
  // deliberately meant it; only the documents are sorted.
  //
  // The count of fields sought is computed here rather than in the table, so
  // the rendering does not have to reach back into the draft.
  const documentGroups = useMemo(() => {
    if (!draft) return [];

    const sought = (key: string) =>
      draft.fields.filter((f) => f.found_in.includes(key)).length;

    const withCounts = (list: ConfigDocumentType[]) =>
      list.map((t) => ({ ...t, sought: sought(t.key) }))
          .sort((a, b) => a.label.localeCompare(b.label));

    const groups = draft.categories
      .map((c) => ({
        key: c.key,
        label: c.label,
        types: withCounts(
          draft.document_types.filter((t) => t.category === c.key)),
      }))
      .filter((g) => g.types.length > 0);

    // A document whose group has been deleted still exists and is still
    // extracted against. Dropping it because its heading is gone would hide a
    // live document behind a configuration mistake.
    const known = new Set(draft.categories.map((c) => c.key));
    const orphans = withCounts(
      draft.document_types.filter((t) => !known.has(t.category)));
    if (orphans.length > 0) {
      groups.push({ key: "ungrouped", label: "Ungrouped", types: orphans });
    }

    return groups;
  }, [draft]);

'''

s = once(
    s,
    r"  const bound = useMemo\(\(\) => \{",
    GROUPS + "  const bound = useMemo(() => {",
    "documentGroups insertion point",
)

s = once(
    s,
    r'''        <tbody>
          \{draft\?\.document_types\.map\(\(t\) => \{.*?
        </tbody>''',
    '''        <tbody>
          {documentGroups.map((group) => (
            <Fragment key={group.key}>
              <tr className="group-head">
                <td colSpan={4}>
                  {group.label}
                  <span className="muted small">
                    {" \\u00b7 "}{group.types.length}
                  </span>
                </td>
              </tr>
              {group.types.map((t) => (
                <tr key={t.key} className={t.sought ? "" : "aside"}>
                  <td>
                    <a onClick={() => setEditType(t.key)}>
                      <strong>{t.label}</strong>
                    </a>
                    <div className="muted small">{t.description}</div>
                  </td>
                  <td className="muted small">
                    {t.read_mode}{t.always_ocr ? " \\u00b7 always OCR" : ""}
                  </td>
                  <td className="muted small">
                    <a onClick={() => {
                      setOpenType(t.key);
                      setTypeFields((draft?.fields ?? [])
                        .filter((f) => f.found_in.includes(t.key))
                        .map((f) => f.key));
                    }}>
                      {t.sought || <span className="warn">none</span>}
                    </a>
                  </td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>''',
    "documents table body",
    re.S,
)

# The Group column is now the heading above each block, so the column goes.
s = once(
    s,
    r'''          <tr>
            <th>Document</th>
            <th>Group</th>
            <th>Read as</th>
            <th>Fields sought</th>
          </tr>''',
    '''          <tr>
            <th>Document</th>
            <th>Read as</th>
            <th>Fields sought</th>
          </tr>''',
    "documents table header",
)

write(P, s)
print("patched " + P)


# --- ui/src/index.css -------------------------------------------------------

CSS = "ui/src/index.css"
s = read(CSS)

s = s + '''
/* A group heading inside the documents table. Reads as a divider rather than
   a row, so the eye runs down the document names and not across it. */
.docs tr.group-head td {
  padding-top: 1.1rem;
  padding-bottom: 0.35rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  font-size: 0.75rem;
  border-bottom: 1px solid #dde3ec;
}

.docs tr.group-head:first-child td {
  padding-top: 0.35rem;
}
'''

write(CSS, s)
print("patched " + CSS)
print("both files patched")
