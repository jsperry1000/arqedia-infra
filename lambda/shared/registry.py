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


def _copy(from_tenant, from_revision, to_tenant, to_revision):
    """Deep-copy one revision to another. Never a reference.

    A starter pack forked into a tenant must not change under them when we
    edit the pack. And a draft opened from revision 4 must not alter revision
    4 as it is edited."""
    for table, columns in TABLES:
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

    A draft opens as a copy of a published revision - by default the latest -
    so a person edits from where they are rather than from nothing. Opening a
    draft when one exists returns it untouched: an unfinished edit is not
    something to discard because somebody clicked twice."""
    existing = _sql(
        "SELECT revision FROM config_revision "
        "WHERE tenant_id = :t AND revision = :d",
        [_p("t", tenant_id), _p("d", DRAFT)])
    if existing.get("records"):
        return {"revision": DRAFT, "created": False}

    source = from_revision if from_revision is not None \
        else _latest_published(tenant_id)

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


def fork(tenant_id, email, pack_revision=1, pack_tenant=PACK_TENANT):
    """Take a starter pack as this tenant's first revision.

    A deep copy, never a reference: our later edits to a pack must not reach a
    tenant who has already forked it. Refused where the tenant already has a
    published revision - adopting a pack over existing configuration would
    discard work, and that is a decision for a person rather than a call."""
    if _latest_published(tenant_id):
        raise ValueError(
            "this tenant already has a published configuration; open a draft "
            "and edit it instead")

    _sql(
        """
        INSERT INTO config_revision
          (tenant_id, revision, status, forked_from, note, created_by,
           published_at, published_by)
        VALUES (:t, 1, 'published', :src, 'forked from a starter pack', :who,
                UTC_TIMESTAMP(), :who)
        """,
        [_p("t", tenant_id),
         _p("src", "pack:%d:%d" % (pack_tenant, pack_revision)),
         _p("who", email)],
    )

    _copy(pack_tenant, pack_revision, tenant_id, 1)

    _sql("UPDATE tenant SET active_revision = 1 WHERE tenant_id = :t",
         [_p("t", tenant_id)])

    return {"forked": True, "revision": 1,
            "from": "pack:%d:%d" % (pack_tenant, pack_revision)}


def packs():
    """The starter packs on offer. They live in the reserved pack tenant."""
    result = _sql(
        """
        SELECT r.revision, r.note,
               (SELECT COUNT(*) FROM config_document_type t
                 WHERE t.tenant_id = r.tenant_id AND t.revision = r.revision),
               (SELECT COUNT(*) FROM config_field f
                 WHERE f.tenant_id = r.tenant_id AND f.revision = r.revision)
        FROM config_revision r
        WHERE r.tenant_id = :p AND r.status = 'published'
        ORDER BY r.revision DESC
        """,
        [_p("p", PACK_TENANT)],
    )
    return [
        {"revision": _col(r, 0), "note": _col(r, 1),
         "document_types": _col(r, 2), "fields": _col(r, 3)}
        for r in result.get("records", [])
    ]
