#!/usr/bin/env python3
"""
tenant0_text_mode.py - tenant 0's base stops claiming FORMS (5 October 2026).

The API already reads every scan as plain text and OCRs only a thin layer,
whatever a type is configured with (OCR_READ_MODE and OCR_ONLY_WHEN_THIN in
lambda/api/app.py). This makes the CONFIGURATION say the same thing, in the
one place new tenants copy it from, so the next tenant forks text mode and
nobody reads "forms" in their own base and believes it.

WHAT IT DOES, IN ORDER, AND ONLY WITH --apply:

  1  refuses if tenant 0 already has a draft open - publishing would ship
     whatever unfinished work is in it, and that is not this script's to ship
  2  opens a draft from tenant 0's active revision
  3  sets read_mode = 'text' and always_ocr = 0 on the draft's document types,
     and touches no other column - save_document_type would rewrite label,
     category and description with defaults for anything not sent
  4  publishes the draft as a new revision, which becomes tenant 0's active one
  5  moves the offer to that revision with the same memoranda, because new
     tenants fork the OFFERED revision, not the active one
  6  discards the draft, so tenant 0 is left as it was found: no draft open

NOTHING PUBLISHED IS EDITED. Existing tenants keep their own configuration,
which still says FORMS; the API override is what changes their reads.

Without --apply it reads and prints what it would do, and writes nothing.

    AWS_PROFILE=arqedia AWS_DEFAULT_REGION=us-east-2 \\
    CLUSTER_ARN=... SECRET_ARN=... DATABASE=arqedia \\
    python db/tenant0_text_mode.py [--apply] --by you@firm.com
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lambda", "shared"))

import registry  # noqa: E402 - needs the path above, and CLUSTER_ARN et al.

TENANT = registry.PACK_TENANT
NOTE = ("Read mode: text for every document type, OCR only when the text "
        "layer is thin (5 October 2026). FORMS output was paid for and read "
        "by nothing.")


def col(record, i):
    cell = record[i]
    return None if "isNull" in cell else next(iter(cell.values()))


def changing(revision):
    """The types whose read mode or always-OCR would change, at a revision."""
    return [(col(r, 0), col(r, 1), bool(col(r, 2))) for r in registry._sql(
        "SELECT type_key, read_mode, always_ocr FROM config_document_type "
        "WHERE tenant_id = :t AND revision = :r "
        "AND (read_mode <> 'text' OR always_ocr = 1) ORDER BY type_key",
        [registry._p("t", TENANT), registry._p("r", revision)],
    ).get("records", [])]


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--apply", action="store_true")
    args.add_argument("--by", required=True, help="who is doing this")
    opts = args.parse_args()

    active = registry._active_revision(TENANT)
    offered = registry.offer()
    draft_open = bool(registry._sql(
        "SELECT revision FROM config_revision "
        "WHERE tenant_id = :t AND revision = :d",
        [registry._p("t", TENANT), registry._p("d", registry.DRAFT)],
    ).get("records"))

    print("tenant 0 active revision:", active)
    print("offer: revision", offered["revision"], "templates",
          offered["templates"])
    print("draft open:", draft_open)
    rows = changing(active)
    print("types to change at revision %s: %d" % (active, len(rows)))
    for key, mode, ocr in rows:
        print("  %-28s %-6s always_ocr=%s  ->  text  always_ocr=False"
              % (key, mode, ocr))

    if draft_open:
        print("REFUSED: tenant 0 has a draft open. Publish or discard it "
              "first; this will not ship somebody's unfinished work.")
        return 2
    if not rows:
        print("Nothing to change.")
        return 0
    if not opts.apply:
        print("Dry run. Nothing written. Run again with --apply.")
        return 0

    registry.open_draft(TENANT, opts.by)
    registry._sql(
        "UPDATE config_document_type SET read_mode = 'text', always_ocr = 0 "
        "WHERE tenant_id = :t AND revision = :d "
        "AND (read_mode <> 'text' OR always_ocr = 1)",
        [registry._p("t", TENANT), registry._p("d", registry.DRAFT)])
    left = changing(registry.DRAFT)
    if left:
        print("STOPPED: the draft still has", left, "- discarding it.")
        registry.discard_draft(TENANT)
        return 1

    published = registry.publish(TENANT, opts.by, NOTE)
    if not published.get("published"):
        print("STOPPED: publish refused:", published.get("validation"))
        registry.discard_draft(TENANT)
        return 1
    revision = published["revision"]
    print("published revision", revision)

    moved = registry.set_offer(revision, offered["templates"], opts.by)
    print("offer moved:", moved)

    registry.discard_draft(TENANT)
    print("draft discarded. Types still claiming FORMS or always-OCR at "
          "revision %d: %d" % (revision, len(changing(revision))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
