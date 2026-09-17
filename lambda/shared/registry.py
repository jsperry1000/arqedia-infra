"""
registry.py - authoring a tenant's configuration.

Editors write the DRAFT, revision 0. Extraction and composition read a
published revision and never the draft. Publishing copies the draft into a new
revision, which is then never touched again - which is why a memo written in
March still reproduces in September.

VALIDATION RUNS AT PUBLISH, NOT AT SAVE. A draft mid-edit is legitimately
inconsistent: a schema exists before anything routes to it, a field exists
before a template binds it. Blocking every save would make the editors
unusable.

Four faults are FATAL and refuse the publish:

    a template binding a field that does not exist
    a table with no group key
    a table with no columns
    a column whose key does not begin with its table

The first is not a matter of taste. It is the Stage 1 defect: a template
naming a field the pack did not define produced a memo that confidently
reported facts as absent when they had been extracted and stored. A memo that
is wrong in that direction is worse than no memo.

The other three are the same defect wearing a different coat, and they cost a
session in September. A field carries TWO answers to "is this a table" -
cardinality and group_key - written by different lines and read by different
rules. A field saying group with no group_key is read as a single value
carrying the word "group", and extraction asking it for its columns stopped on
every document in the tenant. A column key without its table's prefix is
read by composition as a field in its own right and rendered outside the table
it belongs to, silently.

None of the three was caught, so a broken revision published and reached
fifty-six documents. Refused here, none of them can.

Three faults are WARNINGS, shown and not blocking:

    a document type feeding no schema      - extracts nothing
    a schema no document type feeds        - never runs
    a field no template binds              - extracted, never read

Each is a real hole, and each is also a legitimate mid-configuration state.
A tenant part-way through will have all three. They are reported so the
person decides, rather than refused so the product decides for them.
"""

import datetime
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

DRAFT = 0
PACK_TENANT = 0

# Every table a revision spans. Order matters for the copy: nothing here has
# foreign keys, but reading them in chain order keeps a partial failure
# comprehensible.
TABLES = [
    ("config_category",
     ["category_key", "label", "sort_order"]),
    ("config_document_type",
     ["type_key", "label", "category_key", "description", "read_mode",
      "always_ocr", "sort_order"]),
    ("config_schema",
     ["schema_key", "label", "instruction", "sort_order"]),
    ("config_type_schema",
     ["type_key", "schema_key"]),
    ("config_field",
     ["schema_key", "field_key", "label", "field_type", "cardinality",
      "description", "group_key", "sort_order"]),
    ("config_template",
     ["template_key", "label"]),
    ("config_section",
     ["template_key", "section_key", "numeral", "title", "kind", "shape_key",
      "prompt", "context_sections", "sort_order"]),
    ("config_section_field",
     ["template_key", "section_key", "field_key", "sort_order"]),
]

# A whole revision is both. A base is the vocabulary - what can be found and
# where it is looked for; a memorandum is the layout over it. A tenant 0
# revision now holds both at once (migration 023), so a fork takes one part of
# it rather than the whole thing.
BASE_TABLES = TABLES[:5]
TEMPLATE_TABLES = TABLES[5:]

_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _sql(statement, params=None):
    for _ in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                database=DATABASE, sql=statement, parameters=params or [])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(3)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"longValue": 1 if value else 0}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _col(record, i):
    cell = record[i]
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in cell:
            return cell[kind]
    return None


def valid_key(key):
    """A key is an identity that never changes and appears in stored values.
    Constrained so it cannot later become awkward in a URL, a filename or a
    column."""
    return bool(_KEY.match(key or ""))


# --- revisions -------------------------------------------------------------

def revisions(tenant_id):
    """Every revision this tenant has, newest first, draft included."""
    result = _sql(
        """
        SELECT revision, status, note, created_at, created_by,
               published_at, published_by, forked_from
        FROM config_revision
        WHERE tenant_id = :t
        ORDER BY revision DESC
        """,
        [_p("t", tenant_id)],
    )
    return [
        {"revision": _col(r, 0),
         "status": _col(r, 1),
         "note": _col(r, 2),
         "created_at": _col(r, 3),
         "created_by": _col(r, 4),
         "published_at": _col(r, 5),
         "published_by": _col(r, 6),
         "forked_from": _col(r, 7),
         "is_draft": _col(r, 0) == DRAFT}
        for r in result.get("records", [])
    ]


def _latest_published(tenant_id):
    result = _sql(
        """
        SELECT COALESCE(MAX(revision), 0) FROM config_revision
        WHERE tenant_id = :t AND status = 'published'
        """,
        [_p("t", tenant_id)],
    )
    records = result.get("records", [])
    return int(_col(records[0], 0) or 0) if records else 0


def _copy(from_tenant, from_revision, to_tenant, to_revision, tables=None):
    """Deep-copy one revision to another. Never a reference.

    A starter pack forked into a tenant must not change under them when we
    edit the pack. And a draft opened from revision 4 must not alter revision
    4 as it is edited.

    tables narrows what travels. A draft copies everything; a base fork copies
    the vocabulary and leaves our memoranda behind, which matters now that one
    revision holds both."""
    for table, columns in (tables or TABLES):
        names = ", ".join(columns)
        _sql(
            "INSERT INTO {t} (tenant_id, revision, {c}) "
            "SELECT :to_tenant, :to_rev, {c} FROM {t} "
            "WHERE tenant_id = :from_tenant AND revision = :from_rev".format(
                t=table, c=names),
            [_p("to_tenant", to_tenant), _p("to_rev", to_revision),
             _p("from_tenant", from_tenant), _p("from_rev", from_revision)],
        )


def _clear(tenant_id, revision):
    for table, _ in reversed(TABLES):
        _sql("DELETE FROM %s WHERE tenant_id = :t AND revision = :r" % table,
             [_p("t", tenant_id), _p("r", revision)])


def open_draft(tenant_id, email, from_revision=None):
    """Start editing.

    A draft opens as a copy of a published revision - by default the one in
    use - so a person edits from where they are rather than from nothing.
    Opening a draft when one exists returns it untouched: an unfinished edit
    is not something to discard because somebody clicked twice.

    THE ONE IN USE, NOT THE NEWEST (revision selection decision record, item
    9). A tenant who selected an earlier revision is working against that one,
    and opening the newest would silently reopen work they had stepped back
    from. Falls back to the newest where nothing is selected: a tenant that
    has never published has nothing to select."""
    existing = _sql(
        "SELECT revision FROM config_revision "
        "WHERE tenant_id = :t AND revision = :d",
        [_p("t", tenant_id), _p("d", DRAFT)])
    if existing.get("records"):
        return {"revision": DRAFT, "created": False}

    source = from_revision if from_revision is not None \
        else (_active_revision(tenant_id) or _latest_published(tenant_id))

    _sql(
        """
        INSERT INTO config_revision
          (tenant_id, revision, status, note, created_by, forked_from)
        VALUES (:t, :d, 'draft', :note, :who, :from_rev)
        """,
        [_p("t", tenant_id), _p("d", DRAFT),
         _p("note", None), _p("who", email),
         _p("from_rev", "%d:%d" % (tenant_id, source) if source else None)],
    )

    if source:
        _copy(tenant_id, source, tenant_id, DRAFT)

    return {"revision": DRAFT, "created": True, "copied_from": source}


def discard_draft(tenant_id):
    """Throw the draft away. Published revisions are untouched - they are what
    memos were written against and are never editable."""
    _clear(tenant_id, DRAFT)
    _sql("DELETE FROM config_revision WHERE tenant_id = :t AND revision = :d",
         [_p("t", tenant_id), _p("d", DRAFT)])
    return {"discarded": True}


# --- validation ------------------------------------------------------------

def validate(tenant_id, revision=DRAFT):
    """The coverage surface.

    Returns fatal faults and warnings separately, because they mean different
    things: a fatal fault produces a memo that is WRONG, a warning produces a
    memo that is incomplete in a way the person may have intended."""
    fatal, warnings = [], []

    def rows(sql):
        return _sql(sql, [_p("t", tenant_id), _p("r", revision)]
                    ).get("records", [])

    # FATAL. A template naming a field that does not exist writes a memo
    # reporting facts as absent when they were extracted and stored.
    for r in rows(
        """
        SELECT DISTINCT sf.section_key, sf.field_key
        FROM config_section_field sf
        LEFT JOIN config_field f
          ON f.tenant_id = sf.tenant_id AND f.revision = sf.revision
         AND f.field_key = sf.field_key
        WHERE sf.tenant_id = :t AND sf.revision = :r AND f.field_key IS NULL
        ORDER BY sf.section_key, sf.field_key
        """
    ):
        fatal.append({
            "kind": "template-binds-undefined-field",
            "section": _col(r, 0),
            "field": _col(r, 1),
            "detail": "Section '%s' renders '%s', which no schema defines. "
                      "The memo would report it as absent whether or not it "
                      "was extracted." % (_col(r, 0), _col(r, 1)),
        })

    # FATAL. A field whose cardinality says table but which carries no group
    # key. A COLUMN also says group and points at its table, so the test is
    # group_key IS NULL and nothing wider: "group_key <> field_key" would
    # match every column in the tenant and refuse every publish. config.py reads a row with no group_key as a single value, so this
    # arrives downstream as a five-part tuple calling itself a group, and
    # asking it for its columns raises IndexError on every document that
    # reaches it. save_field once set group_key on insert and not on update,
    # so changing a field's shape produced exactly this.
    for r in rows(
        """
        SELECT field_key, label FROM config_field
        WHERE tenant_id = :t AND revision = :r
          AND cardinality = 'group' AND group_key IS NULL
        ORDER BY sort_order
        """
    ):
        fatal.append({
            "kind": "table-without-group-key",
            "field": _col(r, 0),
            "detail": "'%s' is a table but is not recorded as one. Nothing "
                      "would be read from any document carrying it. Change "
                      "its shape to a single value and back, or delete and "
                      "recreate it." % _col(r, 1),
        })

    # FATAL. A table with no columns holds nothing, and the prompt built from
    # it asks the model for an empty row.
    for r in rows(
        """
        SELECT g.field_key, g.label FROM config_field g
        LEFT JOIN config_field c
          ON c.tenant_id = g.tenant_id AND c.revision = g.revision
         AND c.group_key = g.field_key AND c.field_key <> g.field_key
        WHERE g.tenant_id = :t AND g.revision = :r
          AND g.cardinality = 'group' AND g.group_key = g.field_key
          AND c.field_key IS NULL
        ORDER BY g.sort_order
        """
    ):
        fatal.append({
            "kind": "table-without-columns",
            "field": _col(r, 0),
            "detail": "'%s' is a table with no columns, so it holds nothing. "
                      "Name what each row should carry." % _col(r, 1),
        })

    # FATAL. A column's identity is its table's key and a suffix. Four places
    # recover the table by splitting on the dot; a column without one is read
    # as a field in its own right and rendered outside its table.
    for r in rows(
        """
        SELECT field_key, label, group_key FROM config_field
        WHERE tenant_id = :t AND revision = :r
          AND group_key IS NOT NULL AND field_key <> group_key
          AND field_key NOT LIKE CONCAT(group_key, '.%')
        ORDER BY sort_order
        """
    ):
        fatal.append({
            "kind": "column-without-its-table",
            "field": _col(r, 0),
            "detail": "Column '%s' is identified as '%s' rather than "
                      "'%s.%s'. It would be read as a fact of its own and "
                      "rendered outside its table. Delete the column and add "
                      "it again." % (_col(r, 1), _col(r, 0),
                                     _col(r, 2), _col(r, 0)),
        })

    # WARNING. A type routing to nothing files documents that extract nothing.
    for r in rows(
        """
        SELECT t.type_key, t.label
        FROM config_document_type t
        LEFT JOIN config_type_schema m
          ON m.tenant_id = t.tenant_id AND m.revision = t.revision
         AND m.type_key = t.type_key
        WHERE t.tenant_id = :t AND t.revision = :r AND m.type_key IS NULL
        ORDER BY t.sort_order
        """
    ):
        warnings.append({
            "kind": "type-feeds-no-schema",
            "type": _col(r, 0),
            "detail": "'%s' extracts nothing: no schema is mapped to it."
                      % _col(r, 1),
        })

    # WARNING. A schema nothing routes to never runs.
    for r in rows(
        """
        SELECT s.schema_key, s.label
        FROM config_schema s
        LEFT JOIN config_type_schema m
          ON m.tenant_id = s.tenant_id AND m.revision = s.revision
         AND m.schema_key = s.schema_key
        WHERE s.tenant_id = :t AND s.revision = :r AND m.schema_key IS NULL
        ORDER BY s.sort_order
        """
    ):
        warnings.append({
            "kind": "schema-unused",
            "schema": _col(r, 0),
            "detail": "'%s' never runs: no document type is mapped to it."
                      % _col(r, 1),
        })

    # WARNING. A field nothing binds is extracted and never read. Group
    # columns are excluded: a template binds the group, not its columns.
    for r in rows(
        """
        SELECT f.field_key, f.label
        FROM config_field f
        LEFT JOIN config_section_field sf
          ON sf.tenant_id = f.tenant_id AND sf.revision = f.revision
         AND sf.field_key = f.field_key
        WHERE f.tenant_id = :t AND f.revision = :r
          AND sf.field_key IS NULL
          AND (f.group_key IS NULL OR f.group_key = f.field_key)
        ORDER BY f.sort_order
        """
    ):
        warnings.append({
            "kind": "field-unbound",
            "field": _col(r, 0),
            "detail": "'%s' is extracted but no memo section renders it."
                      % _col(r, 1),
        })

    return {
        "revision": revision,
        "may_publish": not fatal,
        "fatal": fatal,
        "warnings": warnings,
    }


# --- publishing ------------------------------------------------------------

def publish(tenant_id, email, note=None):
    """Copy the draft into a new immutable revision.

    The draft survives publication. A person mid-way through a larger change
    who publishes an intermediate state should not lose their place."""
    report = validate(tenant_id, DRAFT)
    if not report["may_publish"]:
        return {"published": False, "validation": report}

    revision = _latest_published(tenant_id) + 1

    _sql(
        """
        INSERT INTO config_revision
          (tenant_id, revision, status, note, created_by,
           published_at, published_by)
        VALUES (:t, :r, 'published', :note, :who, UTC_TIMESTAMP(), :who)
        """,
        [_p("t", tenant_id), _p("r", revision), _p("note", note),
         _p("who", email)],
    )

    _copy(tenant_id, DRAFT, tenant_id, revision)

    # New work files against it. Everything already filed keeps resolving
    # against the revision it was filed under.
    _sql("UPDATE tenant SET active_revision = :r WHERE tenant_id = :t",
         [_p("r", revision), _p("t", tenant_id)])

    return {
        "published": True,
        "revision": revision,
        "note": note,
        "warnings": report["warnings"],
    }


def _active_revision(tenant_id):
    """The revision the tenant's new work files against.

    Read here rather than through config.active_revision because registry is
    the layer below: config loads a revision, this one writes them."""
    result = _sql("SELECT active_revision FROM tenant WHERE tenant_id = :t",
                  [_p("t", tenant_id)])
    records = result.get("records", [])
    if not records:
        return 0
    return int(_col(records[0], 0) or 0)


def select_revision(tenant_id, revision):
    """Choose which published revision new work is written against.

    Publishing makes a revision available; this is what puts one in use, and
    reverting is selecting an earlier one (revision selection decision record,
    items 1, 2 and 4). Nothing is retired and nothing is deleted.

    WHAT IS ALREADY FILED OR GENERATED DOES NOT MOVE. A document pins
    document.config_revision at filing and a memorandum pins
    memo.config_revision; both keep resolving against the revision they name.

    REFUSED WHILE A DRAFT IS OPEN (amendment of 17 September 2026, PROPOSED).
    A draft is a copy of the revision it was opened from, and publishing it
    numbers from the highest revision - so selecting another revision
    underneath it would leave a person editing one configuration and filing
    against a different one, and their publish would ship the first over the
    second.

    The draft is refused as a selection too: it is mutable, and composition
    would be reading a configuration that changes under it. A revision
    belonging to another tenant cannot be reached - the lookup is scoped by
    tenant_id, which comes from the token."""
    if revision is None or isinstance(revision, bool):
        raise ValueError("choose a revision to use")
    try:
        revision = int(revision)
    except (TypeError, ValueError):
        raise ValueError("choose a revision to use")
    if revision == DRAFT:
        raise ValueError(
            "the draft is not a published revision. Publish it first, then "
            "it can be put in use.")

    # forked_from records what the draft was opened from, as "tenant:revision"
    # (open_draft). Named in the refusal so a person knows which work is at
    # stake rather than being told only that something is in the way.
    draft = _sql(
        "SELECT forked_from FROM config_revision "
        "WHERE tenant_id = :t AND revision = :d",
        [_p("t", tenant_id), _p("d", DRAFT)]).get("records", [])
    if draft:
        opened_from = (_col(draft[0], 0) or "").rsplit(":", 1)[-1]
        raise ValueError(
            "a draft is open, taken from revision %s. Publish it or discard "
            "it before putting another revision in use."
            % (opened_from or "an earlier one"))

    rows = _sql(
        "SELECT status FROM config_revision "
        "WHERE tenant_id = :t AND revision = :r",
        [_p("t", tenant_id), _p("r", revision)]).get("records", [])
    if not rows:
        raise ValueError("this workspace has no revision %d" % revision)
    if _col(rows[0], 0) != "published":
        raise ValueError("revision %d is not published" % revision)

    _sql("UPDATE tenant SET active_revision = :r WHERE tenant_id = :t",
         [_p("r", revision), _p("t", tenant_id)])
    return {"active_revision": revision}


def _offer(pack_key, kind):
    """What is on offer under one key: the tenant, the revision, and for a
    memorandum the template_key inside it.

    THE MARK, NOT THE NEWEST (revision selection decision record, items 6 and
    7). This read MAX(revision) for a pack_key, so publishing a revision
    changed what every new tenant got, with nothing said and no way to put it
    back. Now a row in pack_offer says it, and the revision it names must
    still be published - a mark on a revision somebody withdrew offers
    nothing.

    None where no mark exists, which is how a pack taken off offer stops
    being forkable."""
    records = _sql(
        """
        SELECT o.tenant_id, o.revision, o.template_key
        FROM pack_offer o
        JOIN config_revision r ON r.tenant_id = o.tenant_id
         AND r.revision = o.revision AND r.status = 'published'
        WHERE o.pack_key = :key AND o.kind = :k
        """,
        [_p("key", pack_key), _p("k", kind)],
    ).get("records", [])
    if not records:
        return None
    return {"tenant_id": _col(records[0], 0), "revision": _col(records[0], 1),
            "template_key": _col(records[0], 2)}


def _holds_facts(tenant_id, revision):
    """Whether a revision holds a vocabulary. A memorandum-only revision does
    not, and forking one as a base would give a tenant a configuration that
    cannot extract anything."""
    records = _sql(
        "SELECT COUNT(*) FROM config_field WHERE tenant_id = :t AND revision = :r",
        [_p("t", tenant_id), _p("r", revision)]).get("records", [])
    return bool(records and int(_col(records[0], 0) or 0))


def _revision_kind(tenant_id, revision):
    records = _sql(
        "SELECT kind FROM config_revision "
        "WHERE tenant_id = :t AND revision = :r",
        [_p("t", tenant_id), _p("r", revision)]).get("records", [])
    return _col(records[0], 0) if records else None


def _keys(tenant_id, revision, table, column, extra="", params=None):
    """One column of keys from one revision, as a set."""
    records = _sql(
        "SELECT DISTINCT {c} FROM {t} "
        "WHERE tenant_id = :t AND revision = :r {x}".format(
            c=column, t=table, x=extra),
        [_p("t", tenant_id), _p("r", revision)] + (params or []),
    ).get("records", [])
    return {_col(r, 0) for r in records}


def _in(keys, prefix="k"):
    """An IN list and its parameters. Written out rather than interpolated:
    a pack's keys are ours, but a query that interpolates once is a query that
    interpolates twice."""
    names = [":%s%d" % (prefix, i) for i in range(len(keys))]
    params = [_p("%s%d" % (prefix, i), k) for i, k in enumerate(keys)]
    return ", ".join(names), params


def fork_base(tenant_id, email, pack_revision=None, pack_key="base",
              pack_tenant=PACK_TENANT):
    """Take a starter base as this tenant's first revision.

    The base is the facts, the document types, and which facts are sought in
    which type. A memorandum is not part of it - see fork_template.

    A deep copy, never a reference: our later edits to a pack must not reach a
    tenant who has already forked it. Refused where the tenant already has a
    published revision - adopting a base over existing configuration would
    discard work, and that is a decision for a person rather than a call."""
    if _latest_published(tenant_id):
        raise ValueError(
            "this tenant already has a published configuration; open a draft "
            "and edit it instead")

    if pack_revision is not None:
        source_tenant, revision = pack_tenant, pack_revision
    else:
        offer = _offer(pack_key, "base")
        if offer is None:
            raise ValueError("no base is on offer under '%s'" % pack_key)
        source_tenant, revision = offer["tenant_id"], offer["revision"]

    # A memorandum-only revision holds no facts, and the legacy whole-pack
    # revision is not offered any more. The test is what the revision HOLDS
    # rather than what it is called: a marked revision is a whole tenant
    # configuration (kind 'tenant'), and reading kind would refuse it.
    if not _holds_facts(source_tenant, revision):
        raise ValueError(
            "revision %s of tenant %s holds no facts, so it cannot be a base"
            % (revision, source_tenant))

    _sql(
        """
        INSERT INTO config_revision
          (tenant_id, revision, status, kind, forked_from, note, created_by,
           published_at, published_by)
        VALUES (:t, 1, 'published', 'tenant', :src,
                'forked from a starter base', :who, UTC_TIMESTAMP(), :who)
        """,
        [_p("t", tenant_id),
         _p("src", "pack:%d:%d" % (source_tenant, revision)),
         _p("who", email)],
    )

    # The vocabulary only. Our memoranda live in the same revision now, and a
    # base fork must not bring them: which memoranda a tenant holds is their
    # choice, made in Get started.
    _copy(source_tenant, revision, tenant_id, 1, BASE_TABLES)

    _sql("UPDATE tenant SET active_revision = 1 WHERE tenant_id = :t",
         [_p("t", tenant_id)])

    return {"forked": True, "revision": 1, "pack_key": pack_key,
            "from": "pack:%d:%d" % (source_tenant, revision)}


def fork(tenant_id, email, pack_revision=None, pack_tenant=PACK_TENANT):
    """Kept for everything that called it before the split. Forking a pack
    means forking a base, and this is that call under its old name."""
    return fork_base(tenant_id, email, pack_revision=pack_revision,
                     pack_tenant=pack_tenant)


def fork_template(tenant_id, email, pack_key, pack_tenant=PACK_TENANT):
    """Add one of our memoranda to a tenant's configuration.

    INTO THE DRAFT, ALWAYS. A published revision is immutable and cached for
    the life of a container, so nothing may be added to one; the draft is the
    only revision anything writes to. A draft is opened if none is open, over
    the tenant's LIVE configuration rather than the latest published one -
    those are the same today, and a template laid over facts that are not live
    would be a memorandum binding facts nobody is extracting.

    ADDITIVE. A key the tenant already holds is left exactly as it is,
    including wording they have changed. Their section survives a re-fork of
    the same template, and so does their label.

    IT BRINGS BACK WHAT IT NEEDS. A template binds facts, and the tenant may
    not have them: never forked, or deleted since. The facts are added from
    the base, with the schema each belongs to, the document types those
    schemas are fed by, and the categories those types sit in. Nothing else,
    and nothing that is already there.

    IT SAYS WHAT IT ADDED. Somebody who deleted a fact in March and finds it
    back in September is told why, in the moment.

    A SECOND TAKE MAKES A SECOND MEMORANDUM. Taking one already held used to
    merge into it: their label and retitled sections survived, but sections
    they had deleted and facts they had unbound came back, silently. Now it
    arrives beside theirs, keyed <key>-2 and labelled "... (2)", so their own
    work is never reached (decision record, the take rule)."""
    if not _latest_published(tenant_id):
        raise ValueError(
            "fork a base before a template: a memorandum binds facts, and "
            "sections with no facts behind them cannot be published")

    offer = _offer(pack_key, "template")
    if offer is None:
        raise ValueError("no memorandum is on offer under '%s'" % pack_key)
    pack_tenant = offer["tenant_id"]
    source = offer["revision"]
    source_key = offer["template_key"]
    if not source_key:
        raise ValueError(
            "the mark for '%s' names no memorandum" % pack_key)

    base_offer = _offer("base", "base")
    if base_offer is None:
        raise ValueError("no base is on offer; a memorandum's facts come "
                         "from it")
    base_tenant, base = base_offer["tenant_id"], base_offer["revision"]

    # The draft, over what is live. open_draft returns an existing draft
    # untouched, so an unfinished edit is never disturbed.
    live = _active_revision(tenant_id) or _latest_published(tenant_id)
    opened = open_draft(tenant_id, email, live)

    # --- what the template needs, worked out before anything is written ----

    bound = _keys(pack_tenant, source, "config_section_field", "field_key",
                  "AND template_key = :tk", [_p("tk", source_key)])
    held_fields = _keys(tenant_id, DRAFT, "config_field", "field_key")
    wanted = sorted(bound - held_fields)

    # A fact the base does not define either. Nothing in our own content does
    # this, and writing a draft that cannot publish is worse than refusing.
    if wanted:
        names, params = _in(wanted)
        in_base = _keys(base_tenant, base, "config_field", "field_key",
                        "AND field_key IN (%s)" % names, params)
        orphans = [k for k in wanted if k not in in_base]
        if orphans:
            raise ValueError(
                "this template binds facts the base does not define: %s"
                % ", ".join(orphans[:6]))

    # A table's columns come with it: they are rows of their own, and a
    # section binds the table rather than its columns.
    groups = []
    if wanted:
        names, params = _in(wanted)
        groups = sorted(_keys(
            base_tenant, base, "config_field", "field_key",
            "AND group_key = field_key AND field_key IN (%s)" % names,
            params))
    columns = []
    if groups:
        names, params = _in(groups, "g")
        columns = sorted(_keys(
            base_tenant, base, "config_field", "field_key",
            "AND group_key IN (%s) AND field_key <> group_key" % names,
            params))

    fields = sorted(set(wanted) | set(columns))

    schemas, types, categories = [], [], []
    if fields:
        names, params = _in(fields, "f")
        needs_schema = _keys(base_tenant, base, "config_field", "schema_key",
                             "AND field_key IN (%s)" % names, params)
        held_schemas = _keys(tenant_id, DRAFT, "config_schema", "schema_key")
        schemas = sorted(needs_schema - held_schemas)

        if needs_schema:
            names, params = _in(sorted(needs_schema), "s")
            feeds = _keys(base_tenant, base, "config_type_schema", "type_key",
                          "AND schema_key IN (%s)" % names, params)
            held_types = _keys(tenant_id, DRAFT, "config_document_type",
                               "type_key")
            types = sorted(feeds - held_types)

        if types:
            names, params = _in(types, "t")
            wants_category = _keys(base_tenant, base, "config_document_type",
                                   "category_key",
                                   "AND type_key IN (%s)" % names, params)
            held_categories = _keys(tenant_id, DRAFT, "config_category",
                                    "category_key")
            categories = sorted(wants_category - held_categories)

    # --- writing, in the order the references run --------------------------

    def add(table, columns_, keys, column, prefix, extra=""):
        """Rows of one table, by key, skipping what the draft already has.
        The skip is in the statement: a shared key in a bare INSERT ... SELECT
        fails it and leaves the revision half written."""
        if not keys:
            return
        names, params = _in(keys, prefix)
        listed = ", ".join(columns_)
        _sql(
            """
            INSERT IGNORE INTO {t} (tenant_id, revision, {c})
            SELECT :to_t, :to_r, {c} FROM {t}
             WHERE tenant_id = :from_t AND revision = :from_r
               AND {col} IN ({keys}) {x}
            """.format(t=table, c=listed, col=column, keys=names, x=extra),
            [_p("to_t", tenant_id), _p("to_r", DRAFT),
             _p("from_t", base_tenant), _p("from_r", base)] + params,
        )

    add("config_category", ["category_key", "label", "sort_order"],
        categories, "category_key", "c")
    add("config_document_type",
        ["type_key", "label", "category_key", "description", "read_mode",
         "always_ocr", "sort_order"],
        types, "type_key", "t")
    add("config_schema", ["schema_key", "label", "instruction", "sort_order"],
        schemas, "schema_key", "s")
    # The routing for the schemas that were added, and only those: a schema
    # the tenant already had keeps the routing they gave it.
    add("config_type_schema", ["type_key", "schema_key"],
        schemas, "schema_key", "r")
    add("config_field",
        ["schema_key", "field_key", "label", "field_type", "cardinality",
         "description", "group_key", "sort_order"],
        fields, "field_key", "f")

    # --- the memorandum itself ---------------------------------------------
    #
    # IGNORE rather than upsert throughout: a tenant who has renamed the
    # memorandum, retitled a section or unbound a fact keeps every one of
    # those decisions when the same template is forked again.

    before = _counts(tenant_id, DRAFT)

    # A key the draft does not already hold, and a label that says which copy
    # this is. Keys are identity and never change, so the count is minted once
    # and a rename afterwards leaves it alone - the same rule
    # editor.duplicate_template follows.
    held_templates = _keys(tenant_id, DRAFT, "config_template", "template_key")
    new_key, suffix, copy_number = source_key, "", 1
    if source_key in held_templates:
        copy_number = 2
        while ("%s-%d" % (source_key, copy_number))[:64] in held_templates:
            copy_number += 1
        new_key = ("%s-%d" % (source_key, copy_number))[:64]
        suffix = " (%d)" % copy_number

    where = (" WHERE tenant_id = :from_t AND revision = :from_r"
             " AND template_key = :src_key")
    params = [_p("to_t", tenant_id), _p("to_r", DRAFT),
              _p("from_t", pack_tenant), _p("from_r", source),
              _p("src_key", source_key), _p("new_key", new_key)]

    _sql(
        """
        INSERT IGNORE INTO config_template (tenant_id, revision, template_key,
               label)
        SELECT :to_t, :to_r, :new_key, CONCAT(label, :suffix)
          FROM config_template""" + where,
        params + [_p("suffix", suffix)],
    )
    _sql(
        """
        INSERT IGNORE INTO config_section
          (tenant_id, revision, template_key, section_key, numeral, title,
           kind, shape_key, prompt, context_sections, sort_order)
        SELECT :to_t, :to_r, :new_key, section_key, numeral, title,
               kind, shape_key, prompt, context_sections, sort_order
          FROM config_section""" + where,
        params,
    )
    # context_sections names sections by key WITHIN this memorandum, and the
    # section keys are unchanged, so nothing has to be remapped.
    _sql(
        """
        INSERT IGNORE INTO config_section_field
          (tenant_id, revision, template_key, section_key, field_key,
           sort_order)
        SELECT :to_t, :to_r, :new_key, section_key, field_key, sort_order
          FROM config_section_field""" + where,
        params,
    )

    after = _counts(tenant_id, DRAFT)

    return {
        "forked": True,
        "pack_key": pack_key,
        "revision": DRAFT,
        "templates": [new_key],
        "template_key": new_key,
        "copy": copy_number,
        "draft_was_open": not opened.get("created", False),
        "sections": after["sections"] - before["sections"],
        "bindings": after["bindings"] - before["bindings"],
        "added": {
            "categories": categories,
            "document_types": types,
            "schemas": schemas,
            "facts": fields,
        },
    }


def _counts(tenant_id, revision):
    """Enough of a revision to say what a fork added to it."""
    records = _sql(
        """
        SELECT (SELECT COUNT(*) FROM config_section
                 WHERE tenant_id = :t AND revision = :r),
               (SELECT COUNT(*) FROM config_section_field
                 WHERE tenant_id = :t AND revision = :r)
        """,
        [_p("t", tenant_id), _p("r", revision)],
    ).get("records", [])
    if not records:
        return {"sections": 0, "bindings": 0}
    return {"sections": int(_col(records[0], 0) or 0),
            "bindings": int(_col(records[0], 1) or 0)}


def packs(pack_tenant=PACK_TENANT):
    """The bases on offer.

    THE MARKS, not a revision's kind and not the newest of them (decision
    record item 7). pack_tenant is kept for callers that pass it and is no
    longer read: each mark says which tenant's revision it names.

    Ordered by key so the list does not move when a pack is added."""
    result = _sql(
        """
        SELECT o.revision, o.pack_key, r.note,
               (SELECT COUNT(*) FROM config_document_type t
                 WHERE t.tenant_id = o.tenant_id AND t.revision = o.revision),
               (SELECT COUNT(*) FROM config_field f
                 WHERE f.tenant_id = o.tenant_id AND f.revision = o.revision)
        FROM pack_offer o
        JOIN config_revision r ON r.tenant_id = o.tenant_id
         AND r.revision = o.revision AND r.status = 'published'
        WHERE o.kind = 'base'
        ORDER BY o.pack_key
        """,
    )
    return [
        {"revision": _col(r, 0), "pack_key": _col(r, 1), "note": _col(r, 2),
         "document_types": _col(r, 3), "fields": _col(r, 4)}
        for r in result.get("records", [])
    ]


def template_packs(tenant_id, pack_tenant=PACK_TENANT):
    """The memoranda on offer, and whether this tenant already holds each.

    A base is a base and a template is a template. They are different lists
    because they are different acts: one is taken once, the other whenever
    somebody wants another memorandum."""
    result = _sql(
        """
        SELECT o.revision, o.pack_key, r.note, o.tenant_id, o.template_key,
               (SELECT COUNT(*) FROM config_section s
                 WHERE s.tenant_id = o.tenant_id AND s.revision = o.revision
                   AND s.template_key = o.template_key),
               (SELECT COUNT(*) FROM config_section_field f
                 WHERE f.tenant_id = o.tenant_id AND f.revision = o.revision
                   AND f.template_key = o.template_key)
        FROM pack_offer o
        JOIN config_revision r ON r.tenant_id = o.tenant_id
         AND r.revision = o.revision AND r.status = 'published'
        WHERE o.kind = 'template'
        ORDER BY o.pack_key
        """,
    )
    packs_ = [
        {"revision": _col(r, 0), "pack_key": _col(r, 1), "note": _col(r, 2),
         "tenant_id": _col(r, 3), "template_key": _col(r, 4),
         "sections": _col(r, 5), "facts": _col(r, 6)}
        for r in result.get("records", [])
    ]

    # What the tenant holds, live and in the draft, so a template already
    # taken is marked rather than offered again as though it were new.
    live = _active_revision(tenant_id) or _latest_published(tenant_id)
    held = _keys(tenant_id, live, "config_template", "template_key") \
        | _keys(tenant_id, DRAFT, "config_template", "template_key")

    for pack in packs_:
        # The memorandum's own name and the headings it carries. pack_key is
        # an identity and the note records where the pack came from; neither
        # is a name to put in front of a customer choosing between them.
        #
        # One memorandum per mark, so both reads name the template_key the
        # mark carries. The revision holds three others.
        where = [_p("p", pack["tenant_id"]), _p("r", pack["revision"]),
                 _p("k", pack["template_key"])]
        rows = _sql(
            "SELECT template_key, label FROM config_template "
            "WHERE tenant_id = :p AND revision = :r AND template_key = :k",
            where,
        ).get("records", [])
        pack["template_keys"] = [_col(r, 0) for r in rows]
        pack["label"] = (_col(rows[0], 1) or _col(rows[0], 0)) if rows \
            else pack["pack_key"]

        headings = _sql(
            "SELECT numeral, title FROM config_section "
            "WHERE tenant_id = :p AND revision = :r AND template_key = :k "
            "ORDER BY sort_order",
            where,
        ).get("records", [])
        pack["section_titles"] = [
            ("%s. %s" % (_col(r, 0), _col(r, 1))) if _col(r, 0)
            else _col(r, 1)
            for r in headings
        ]

        # Held, including a second copy taken under <key>-2. PROPOSED: a
        # tenant who has taken it can take it again, and the chooser says so
        # rather than hiding it.
        pack["held"] = any(
            k == pack["template_key"]
            or k.startswith(pack["template_key"] + "-") for k in held)

    return packs_
