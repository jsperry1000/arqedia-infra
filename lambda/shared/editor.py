"""
editor.py - writing the draft.

Every function here writes revision 0 and nothing else. A published revision is
immutable: it is what memos were composed against, and editing one would change
what a memo already issued would say if reproduced.

THE SCHEMA IS INVISIBLE.

In the data model a field belongs to a schema, and a schema is fed by document
types. Nobody outside this file needs to know that. A person answers a simpler
question - "where is this field found?" - and the schema is DERIVED: fields
sharing the same set of document types form one schema.

That is lossless on the pack we started from. No two of its eight schemas are
fed by an identical set of document types, so deriving reproduces all eight
exactly. Checked before this was built rather than assumed.

The derivation also keeps extraction sensible: one model call per schema per
document, so fields that come from the same documents are asked for together.
"""

import hashlib
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

# 128 characters, matching extracted_value.field_id and config_field.field_key.
# It was 64, which no column enforced and which a group's columns exceeded
# anyway - a column key is the group's key plus a suffix.
_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_MAX_KEY = 128


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


def _rows(tenant_id, sql, extra_params=None):
    return _sql(sql, [_p("t", tenant_id), _p("r", DRAFT)]
                + (extra_params or [])).get("records", [])


def _slug(label, prefix=""):
    """A key from a label, for something new. Minted once and never changed -
    renaming the label afterwards is free precisely because the key does not
    follow it."""
    body = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return (prefix + (body or "item"))[:_MAX_KEY]


def _require_draft(tenant_id):
    if not _sql("SELECT revision FROM config_revision "
                "WHERE tenant_id = :t AND revision = :r",
                [_p("t", tenant_id), _p("r", DRAFT)]).get("records"):
        raise ValueError("no draft is open")


# --- reading ---------------------------------------------------------------

def draft(tenant_id):
    """The whole draft, in the order a person thinks about it: what the report
    says, what each part of it needs, and where those facts are found.

    The schema is not in this shape at all. It is an implementation detail of
    extraction, derived on save."""
    _require_draft(tenant_id)

    sections = []
    for r in _rows(tenant_id, """
        SELECT section_key, numeral, title, kind, prompt, template_key,
               sort_order
        FROM config_section WHERE tenant_id = :t AND revision = :r
        ORDER BY sort_order"""):
        sections.append({
            "key": _col(r, 0), "numeral": _col(r, 1), "title": _col(r, 2),
            "kind": _col(r, 3), "prompt": _col(r, 4),
            "template_key": _col(r, 5), "fields": [],
        })
    by_key = {s["key"]: s for s in sections}

    for r in _rows(tenant_id, """
        SELECT section_key, field_key, sort_order
        FROM config_section_field WHERE tenant_id = :t AND revision = :r
        ORDER BY sort_order"""):
        if _col(r, 0) in by_key:
            by_key[_col(r, 0)]["fields"].append(_col(r, 1))

    # Where each field is found, from the schema it sits in. The schema itself
    # is not reported.
    found_in = {}
    for r in _rows(tenant_id, """
        SELECT f.field_key, m.type_key
        FROM config_field f
        JOIN config_type_schema m
          ON m.tenant_id = f.tenant_id AND m.revision = f.revision
         AND m.schema_key = f.schema_key
        WHERE f.tenant_id = :t AND f.revision = :r"""):
        found_in.setdefault(_col(r, 0), []).append(_col(r, 1))

    # A group's columns are part of the group rather than fields in their own
    # right, so they are carried INSIDE it. A person creating a Shippers table
    # names its columns; they do not add four loose fields and hope.
    rows = list(_rows(tenant_id, """
        SELECT field_key, label, field_type, cardinality, description,
               group_key, sort_order
        FROM config_field WHERE tenant_id = :t AND revision = :r
        ORDER BY sort_order"""))

    columns = {}
    for r in rows:
        key, group = _col(r, 0), _col(r, 5)
        if group and group != key:
            columns.setdefault(group, []).append({
                "key": key, "label": _col(r, 1), "type": _col(r, 2),
                "description": _col(r, 4),
            })

    fields = []
    for r in rows:
        key = _col(r, 0)
        group = _col(r, 5)
        if group and group != key:
            continue
        fields.append({
            "key": key, "label": _col(r, 1), "type": _col(r, 2),
            "cardinality": _col(r, 3), "description": _col(r, 4),
            "is_group": bool(group), "columns": columns.get(key, []),
            "found_in": sorted(found_in.get(key, [])),
        })

    types = []
    for r in _rows(tenant_id, """
        SELECT type_key, label, category_key, description, read_mode,
               always_ocr, sort_order
        FROM config_document_type WHERE tenant_id = :t AND revision = :r
        ORDER BY sort_order"""):
        types.append({
            "key": _col(r, 0), "label": _col(r, 1), "category": _col(r, 2),
            "description": _col(r, 3), "read_mode": _col(r, 4),
            "always_ocr": bool(_col(r, 5)),
        })

    categories = [{"key": _col(r, 0), "label": _col(r, 1)}
                  for r in _rows(tenant_id, """
        SELECT category_key, label FROM config_category
        WHERE tenant_id = :t AND revision = :r ORDER BY sort_order""")]

    return {"sections": sections, "fields": fields,
            "document_types": types, "categories": categories}


# --- sections --------------------------------------------------------------

def save_section(tenant_id, body):
    """Add or amend a section of the report."""
    _require_draft(tenant_id)

    key = body.get("key") or _slug(body.get("title"))
    if not _KEY.match(key):
        raise ValueError("a section key must be lower case letters, digits, "
                         "dots, dashes or underscores")

    template_key = body.get("template_key")
    if not template_key:
        rows = _rows(tenant_id, "SELECT template_key FROM config_template "
                                "WHERE tenant_id = :t AND revision = :r")
        template_key = _col(rows[0], 0) if rows else "memo"

    _sql("""
        INSERT INTO config_section
          (tenant_id, revision, template_key, section_key, numeral, title,
           kind, shape_key, prompt, context_sections, sort_order)
        VALUES (:t, :r, :tpl, :k, :num, :title, :kind, :shape, :prompt,
                :context, :sort)
        ON DUPLICATE KEY UPDATE
          numeral = :num, title = :title, kind = :kind, prompt = :prompt,
          context_sections = :context, sort_order = :sort
        """, [
        _p("t", tenant_id), _p("r", DRAFT), _p("tpl", template_key),
        _p("k", key), _p("num", body.get("numeral") or ""),
        _p("title", body.get("title") or key),
        _p("kind", body.get("kind") or "extract"),
        _p("shape", body.get("shape") or key),
        _p("prompt", body.get("prompt")),
        _p("context", ",".join(body.get("context_sections") or []) or None),
        _p("sort", int(body.get("sort_order") or 0)),
    ])
    return {"key": key}


def delete_section(tenant_id, section_key):
    """Remove a section. Its field bindings go with it - the fields
    themselves remain, and will show as unbound at publish."""
    _require_draft(tenant_id)
    for table in ("config_section_field", "config_section"):
        _sql("DELETE FROM %s WHERE tenant_id = :t AND revision = :r "
             "AND section_key = :k" % table,
             [_p("t", tenant_id), _p("r", DRAFT), _p("k", section_key)])
    return {"deleted": section_key}


def set_section_fields(tenant_id, section_key, field_keys):
    """Which fields this section renders, in order.

    THE STAGE 1 FAULT LIVES HERE. A section naming a field that does not exist
    writes a memo reporting facts as absent when they were extracted and
    stored, so this is refused at SAVE rather than at publish - the one
    exception to validating late."""
    _require_draft(tenant_id)

    known = {_col(r, 0) for r in _rows(tenant_id,
             "SELECT field_key FROM config_field "
             "WHERE tenant_id = :t AND revision = :r")}
    unknown = [k for k in field_keys if k not in known]
    if unknown:
        raise ValueError("no such field: " + ", ".join(unknown[:5]))

    rows = _rows(tenant_id, "SELECT template_key FROM config_section "
                            "WHERE tenant_id = :t AND revision = :r "
                            "AND section_key = :k",
                 [_p("k", section_key)])
    if not rows:
        raise ValueError("no such section: " + section_key)
    template_key = _col(rows[0], 0)

    _sql("DELETE FROM config_section_field WHERE tenant_id = :t "
         "AND revision = :r AND section_key = :k",
         [_p("t", tenant_id), _p("r", DRAFT), _p("k", section_key)])

    for i, field_key in enumerate(field_keys):
        _sql("""
            INSERT INTO config_section_field
              (tenant_id, revision, template_key, section_key, field_key,
               sort_order)
            VALUES (:t, :r, :tpl, :sec, :f, :sort)
            """, [_p("t", tenant_id), _p("r", DRAFT), _p("tpl", template_key),
                  _p("sec", section_key), _p("f", field_key), _p("sort", i)])

    return {"section": section_key, "fields": field_keys}


# --- fields ----------------------------------------------------------------

def set_field_documents(tenant_id, field_key, type_keys):
    """Where a field is expected to be found.

    The schema is derived: this field joins the schema fed by exactly these
    document types, and one is created if none exists. A field found nowhere
    is left in place and reported as extracting nothing at publish - it is a
    legitimate mid-configuration state."""
    _require_draft(tenant_id)

    wanted = sorted(set(type_keys or []))

    # Which schema, if any, is fed by exactly this set of types?
    fed = {}
    for r in _rows(tenant_id, "SELECT schema_key, type_key "
                              "FROM config_type_schema "
                              "WHERE tenant_id = :t AND revision = :r"):
        fed.setdefault(_col(r, 0), set()).add(_col(r, 1))

    target = next((s for s, types in fed.items()
                   if sorted(types) == wanted), None)

    if target is None:
        # A stable key from the SET of types, not from their names: two
        # fields found in the same documents must land in the same schema
        # whatever order they were listed in.
        target = "set-" + hashlib.sha1(
            "|".join(wanted).encode("utf-8")).hexdigest()[:16]

        # The label is never shown - the schema is invisible by design - so it
        # says how many documents rather than listing them. Listing them
        # overflowed the column the moment a field was found in eight.
        label = "Fields found in %d document%s" % (
            len(wanted), "" if len(wanted) == 1 else "s")

        _sql("""
            INSERT INTO config_schema
              (tenant_id, revision, schema_key, label, sort_order)
            VALUES (:t, :r, :k, :label, 0)
            ON DUPLICATE KEY UPDATE label = :label
            """, [_p("t", tenant_id), _p("r", DRAFT), _p("k", target),
                  _p("label", label)])

        for type_key in wanted:
            _sql("""
                INSERT IGNORE INTO config_type_schema
                  (tenant_id, revision, type_key, schema_key)
                VALUES (:t, :r, :ty, :s)
                """, [_p("t", tenant_id), _p("r", DRAFT),
                      _p("ty", type_key), _p("s", target)])

    # The group's columns follow the group.
    _sql("""
        UPDATE config_field SET schema_key = :s
        WHERE tenant_id = :t AND revision = :r
          AND (field_key = :f OR group_key = :f)
        """, [_p("s", target), _p("t", tenant_id), _p("r", DRAFT),
              _p("f", field_key)])

    _prune_schemas(tenant_id)
    return {"field": field_key, "found_in": wanted}


def set_document_fields(tenant_id, type_key, field_keys):
    """Which fields are sought in one document.

    The same relationship as set_field_documents, read from the other end: a
    field naming a document and a document naming a field are one fact, stored
    once. Editing from either side writes the same rows, so the two screens
    cannot disagree - there is no second copy to drift.

    Done in ONE operation rather than a call per field. Twelve separate calls
    would each rebuild the grouping, and a half-finished sweep would leave an
    intermediate state that is nobody's intent."""
    _require_draft(tenant_id)

    wanted = set(field_keys or [])

    # Every field, and the documents it is currently found in.
    current = {}
    for r in _rows(tenant_id, """
        SELECT f.field_key, m.type_key
        FROM config_field f
        LEFT JOIN config_type_schema m
          ON m.tenant_id = f.tenant_id AND m.revision = f.revision
         AND m.schema_key = f.schema_key
        WHERE f.tenant_id = :t AND f.revision = :r
          AND (f.group_key IS NULL OR f.group_key = f.field_key)"""):
        current.setdefault(_col(r, 0), set())
        if _col(r, 1):
            current[_col(r, 0)].add(_col(r, 1))

    changed = 0
    for field_key, documents in current.items():
        has = type_key in documents
        should = field_key in wanted
        if has == should:
            continue
        documents = set(documents)
        documents.add(type_key) if should else documents.discard(type_key)
        set_field_documents(tenant_id, field_key, sorted(documents))
        changed += 1

    return {"document": type_key, "fields": sorted(wanted), "changed": changed}


def _prune_schemas(tenant_id):
    """Remove a schema no field sits in.

    Left alone these accumulate as a person moves fields about, and each one
    would be reported at publish as a schema that never runs - noise from the
    editor rather than a fault in the configuration."""
    _sql("""
        DELETE s FROM config_schema s
        LEFT JOIN config_field f
          ON f.tenant_id = s.tenant_id AND f.revision = s.revision
         AND f.schema_key = s.schema_key
        WHERE s.tenant_id = :t AND s.revision = :r AND f.field_key IS NULL
        """, [_p("t", tenant_id), _p("r", DRAFT)])

    _sql("""
        DELETE m FROM config_type_schema m
        LEFT JOIN config_schema s
          ON s.tenant_id = m.tenant_id AND s.revision = m.revision
         AND s.schema_key = m.schema_key
        WHERE m.tenant_id = :t AND m.revision = :r AND s.schema_key IS NULL
        """, [_p("t", tenant_id), _p("r", DRAFT)])


def save_field(tenant_id, body):
    """Add or amend a field.

    The key is minted once from the label and never follows it afterwards.
    That is what makes renaming free: two years of extracted values reference
    the key, not the words on the screen."""
    _require_draft(tenant_id)

    key = body.get("key") or _slug(body.get("label"), "f_").replace("-", "_")
    if not _KEY.match(key):
        raise ValueError(
            "a field identity must be lower case letters, digits, dots, "
            "dashes or underscores, and under %d characters" % _MAX_KEY)

    # A table's columns take this key as their prefix, so the group itself
    # must leave room for the longest of them.
    if body.get("cardinality") == "group":
        for col in (body.get("columns") or []):
            suffix = "." + _slug(col.get("label") or "", "").replace("-", "_")
            if len(key) + len(suffix) > _MAX_KEY:
                raise ValueError(
                    "the name '%s' leaves no room for its column '%s'. "
                    "Shorten the table's name." % (body.get("label"),
                                                   col.get("label")))

    rows = _rows(tenant_id, "SELECT schema_key FROM config_field "
                            "WHERE tenant_id = :t AND revision = :r "
                            "AND field_key = :k", [_p("k", key)])
    schema_key = _col(rows[0], 0) if rows else "unrouted"

    if not rows:
        _sql("""
            INSERT IGNORE INTO config_schema
              (tenant_id, revision, schema_key, label, sort_order)
            VALUES (:t, :r, 'unrouted', 'Not yet routed to a document', 999)
            """, [_p("t", tenant_id), _p("r", DRAFT)])

    _sql("""
        INSERT INTO config_field
          (tenant_id, revision, schema_key, field_key, label, field_type,
           cardinality, description, group_key, sort_order)
        VALUES (:t, :r, :s, :k, :label, :type, :card, :desc, :grp, :sort)
        ON DUPLICATE KEY UPDATE
          label = :label, field_type = :type, cardinality = :card,
          description = :desc, sort_order = :sort
        """, [
        _p("t", tenant_id), _p("r", DRAFT), _p("s", schema_key), _p("k", key),
        _p("label", body.get("label") or key),
        _p("type", body.get("type") or "text"),
        _p("card", body.get("cardinality") or "one"),
        _p("desc", body.get("description")),
        _p("grp", key if body.get("cardinality") == "group" else None),
        _p("sort", int(body.get("sort_order") or 0)),
    ])

    if body.get("cardinality") == "group":
        _save_columns(tenant_id, schema_key, key, body.get("columns") or [])

    return {"key": key}


def _save_columns(tenant_id, schema_key, group_key, columns):
    """A table's columns.

    Rewritten whole rather than merged: a column removed from the form has
    been removed, and reconciling additions against deletions is how a column
    nobody asked for survives three edits."""
    _sql("DELETE FROM config_field WHERE tenant_id = :t AND revision = :r "
         "AND group_key = :g AND field_key <> :g",
         [_p("t", tenant_id), _p("r", DRAFT), _p("g", group_key)])

    for i, col in enumerate(columns):
        label = (col.get("label") or "").strip()
        if not label:
            continue
        key = col.get("key") or (
            group_key + "." + _slug(label).replace("-", "_"))

        # A column's identity is the group's key plus a suffix, so it can
        # exceed what the group alone would. Refused here rather than
        # accepted, published, and failed hours later during extraction on
        # somebody's document.
        if len(key) > _MAX_KEY:
            raise ValueError(
                "'%s' makes an identity too long for a column named '%s'. "
                "Shorten one of them." % (label, group_key))
        _sql("""
            INSERT INTO config_field
              (tenant_id, revision, schema_key, field_key, label, field_type,
               cardinality, description, group_key, sort_order)
            VALUES (:t, :r, :s, :k, :label, :type, 'group', :desc, :g, :sort)
            ON DUPLICATE KEY UPDATE
              label = :label, field_type = :type, description = :desc,
              sort_order = :sort
            """, [
            _p("t", tenant_id), _p("r", DRAFT), _p("s", schema_key),
            _p("k", key), _p("label", label),
            _p("type", col.get("type") or "text"),
            _p("desc", col.get("description")),
            _p("g", group_key), _p("sort", i),
        ])


def delete_field(tenant_id, field_key):
    """Remove a field.

    A REAL BREAK, and treated as one. Values already extracted under this key
    keep resolving against the revision they were filed under - a published
    revision is immutable - but nothing new will carry it. Its bindings are
    removed with it, so no section is left naming a field that does not
    exist."""
    _require_draft(tenant_id)
    _sql("DELETE FROM config_section_field WHERE tenant_id = :t "
         "AND revision = :r AND field_key = :k",
         [_p("t", tenant_id), _p("r", DRAFT), _p("k", field_key)])
    _sql("DELETE FROM config_field WHERE tenant_id = :t AND revision = :r "
         "AND (field_key = :k OR group_key = :k)",
         [_p("t", tenant_id), _p("r", DRAFT), _p("k", field_key)])
    _prune_schemas(tenant_id)
    return {"deleted": field_key}


# --- document types and categories ----------------------------------------

def save_document_type(tenant_id, body):
    """Add or amend a document type.

    The description is not decoration: it is what the classifier reads to tell
    one type from another. Stage 1 showed the same document classified
    differently as a PDF and as a Word file until every type carried a
    sentence describing itself."""
    _require_draft(tenant_id)

    key = body.get("key") or _slug(body.get("label"))
    if not _KEY.match(key):
        raise ValueError("a document type key must be lower case letters, "
                         "digits, dots, dashes or underscores")

    _sql("""
        INSERT INTO config_document_type
          (tenant_id, revision, type_key, label, category_key, description,
           read_mode, always_ocr, sort_order)
        VALUES (:t, :r, :k, :label, :cat, :desc, :mode, :ocr, :sort)
        ON DUPLICATE KEY UPDATE
          label = :label, category_key = :cat, description = :desc,
          read_mode = :mode, always_ocr = :ocr, sort_order = :sort
        """, [
        _p("t", tenant_id), _p("r", DRAFT), _p("k", key),
        _p("label", body.get("label") or key),
        _p("cat", body.get("category") or "other"),
        _p("desc", body.get("description") or ""),
        _p("mode", body.get("read_mode") or "text"),
        _p("ocr", bool(body.get("always_ocr"))),
        _p("sort", int(body.get("sort_order") or 0)),
    ])
    return {"key": key}


def delete_document_type(tenant_id, type_key):
    """Remove a document type. Documents already filed under it keep
    resolving against the revision they were filed under."""
    _require_draft(tenant_id)
    _sql("DELETE FROM config_type_schema WHERE tenant_id = :t "
         "AND revision = :r AND type_key = :k",
         [_p("t", tenant_id), _p("r", DRAFT), _p("k", type_key)])
    _sql("DELETE FROM config_document_type WHERE tenant_id = :t "
         "AND revision = :r AND type_key = :k",
         [_p("t", tenant_id), _p("r", DRAFT), _p("k", type_key)])
    _prune_schemas(tenant_id)
    return {"deleted": type_key}


def save_category(tenant_id, body):
    _require_draft(tenant_id)
    key = body.get("key") or _slug(body.get("label"))
    if not _KEY.match(key):
        raise ValueError("a category key must be lower case letters, digits, "
                         "dots, dashes or underscores")
    _sql("""
        INSERT INTO config_category
          (tenant_id, revision, category_key, label, sort_order)
        VALUES (:t, :r, :k, :label, :sort)
        ON DUPLICATE KEY UPDATE label = :label, sort_order = :sort
        """, [_p("t", tenant_id), _p("r", DRAFT), _p("k", key),
              _p("label", body.get("label") or key),
              _p("sort", int(body.get("sort_order") or 0))])
    return {"key": key}


def delete_category(tenant_id, category_key):
    """Remove a category. A document type left pointing at it is not deleted
    - losing a type because its grouping went would be a surprise, and the
    type simply needs regrouping."""
    _require_draft(tenant_id)
    _sql("DELETE FROM config_category WHERE tenant_id = :t AND revision = :r "
         "AND category_key = :k",
         [_p("t", tenant_id), _p("r", DRAFT), _p("k", category_key)])
    return {"deleted": category_key}
