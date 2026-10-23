"""
config.py - the tenant's configuration, loaded from the registry.

Replaces the hard-coded pack.py and template.py. Presents the SAME interface
they did, deliberately: every caller swaps an import and changes nothing else,
which is what makes "does revision 1 reproduce what pack.py produced" a
question that can actually be answered.

A revision is IMMUTABLE, so it is cached for the life of the container. Lambda
reuses containers, so a busy function loads a revision once and answers from
memory thereafter. The draft - revision 0 - is never loaded here: editors write
it, and nothing in the pipeline reads it.

WHICH REVISION:
    extraction    the one the document was filed under, from document.config_revision
    composition   the one the memo is being written under
    classify      the tenant's active revision, since nothing is filed yet

A document filed under revision 11 keeps resolving against revision 11 for
ever. That is the whole point of a snapshot, and it is why a memo written in
March still reproduces in September.

SEVERAL TEMPLATES, ONE REVISION. A tenant may hold a credit memorandum, a KYC
memorandum and a lender memorandum side by side. They share the field
vocabulary and the document types - a document is extracted once and read three
ways, and extracting it three times would be paid for three times - and each
has its own sections, bindings and prompts.

One revision covers all of them. Versioning a template separately would mean a
memo pinning a template revision AND a field revision, with cross-object
references to resolve at each; extracted_value carries one config_revision, and
a snapshot is one integer.

A WORKSPACE OWNS THE SERIES (PACK-01, migration 040). A tenant holds one or
more workspaces - Trade Finance, Real Estate - each with its own draft, its own
publishes and its own revision in use. A revision is (tenant_id, workspace_id,
revision). The NUMBER still comes from one counter per tenant, so two
workspaces are never issued the same one; the workspace is in the key so a
draft - revision 0 in every workspace - is one per workspace.

Workspace 0 is "in no workspace": the pack tenant, which curates rather than
works, and any row written before the code that names a workspace was
deployed. workspace_of() reads the second kind as the tenant's only workspace,
which is what it was written in.
"""

import os
import time

import boto3
from botocore.exceptions import ClientError

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# (tenant_id, workspace_id, revision) -> Registry. Immutable, so this never
# goes stale.
_CACHE = {}

# A tenant with no workspace row. The pack tenant, and nothing else today.
NO_WORKSPACE = 0

# Asked when a tenant holds several workspaces and the request named none.
# Never guessed: work landing in the wrong workspace is filed, extracted and
# charged under a configuration nobody chose (decision of 22 October 2026).
CHOOSE_A_WORKSPACE = ("This account has more than one workspace. Choose the "
                      "workspace to work in.")


class WorkspaceRequired(ValueError):
    """Several workspaces, and nothing said which. A ValueError, so every
    route already answers it as 400 with the sentence."""


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
                time.sleep(5)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _col(record, i):
    cell = record[i]
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in cell:
            return cell[kind]
    return None


class Registry(object):
    """One tenant's configuration at one revision.

    Attribute names match pack.py and template.py exactly. That is not
    laziness: it means the switch from hard-coded to configured changes an
    import and nothing else, so any difference in output is a real difference
    rather than a rewrite artefact.
    """

    def __init__(self, tenant_id, workspace_id, revision):
        self.tenant_id = tenant_id
        self.workspace_id = workspace_id
        self.CONFIG_REVISION = revision

        self.CATEGORIES = {}
        self.DOCUMENT_TYPES = {}
        self.SCHEMAS = {}

        # template_key -> {"key", "label", "sections": [...]}
        self.TEMPLATES = {}

        self._labels = {}       # field_key -> label
        self._groups = {}       # group_key -> [(col_key, label, type, desc)]

        self._load()

    # --- loading -----------------------------------------------------------

    def _rows(self, table, columns, extra=""):
        result = _sql(
            "SELECT %s FROM %s WHERE tenant_id = :t AND workspace_id = :w "
            "AND revision = :r %s" % (", ".join(columns), table, extra),
            [_p("t", self.tenant_id), _p("w", self.workspace_id),
             _p("r", self.CONFIG_REVISION)])
        return result.get("records", [])

    def _load(self):
        for r in self._rows("config_category",
                            ["category_key", "label"], "ORDER BY sort_order"):
            self.CATEGORIES[_col(r, 0)] = _col(r, 1)

        # The mapping first: a type carries its schemas, as the pack did.
        mapping = {}
        for r in self._rows("config_type_schema", ["type_key", "schema_key"]):
            mapping.setdefault(_col(r, 0), []).append(_col(r, 1))

        for r in self._rows(
            "config_document_type",
            ["type_key", "label", "category_key", "description",
             "read_mode", "always_ocr"],
            "ORDER BY sort_order",
        ):
            key = _col(r, 0)
            self.DOCUMENT_TYPES[key] = {
                "label": _col(r, 1),
                "category": _col(r, 2),
                "description": _col(r, 3),
                "read_mode": _col(r, 4),
                "always_ocr": bool(_col(r, 5)),
                "schemas": mapping.get(key, []),
            }

        # Fields, rebuilt into the pack's tuple shape. A group's columns share
        # its key; the group's own row carries the label a table is titled
        # with, and is not a column.
        columns = {}
        singles = {}
        group_meta = {}

        for r in self._rows(
            "config_field",
            ["schema_key", "field_key", "label", "field_type", "cardinality",
             "description", "group_key"],
            "ORDER BY sort_order",
        ):
            schema_key = _col(r, 0)
            field_key = _col(r, 1)
            label = _col(r, 2)
            ftype = _col(r, 3)
            card = _col(r, 4)
            desc = _col(r, 5)
            group_key = _col(r, 6)

            # A group COLUMN is deliberately absent from the label map, so
            # label_for falls back to the key exactly as the pack did. Every
            # caller resolves a column through group_columns first, so this is
            # unreachable in practice - but revision 1 must BE the pack, and a
            # difference that has to be argued harmless is still a difference.
            if not group_key or field_key == group_key:
                self._labels[field_key] = label

            if group_key and field_key == group_key:
                group_meta[field_key] = (schema_key, label, desc)
                continue

            if group_key:
                columns.setdefault(group_key, []).append(
                    (field_key, label, ftype, desc))
                continue

            singles.setdefault(schema_key, []).append(
                (field_key, label, ftype, card, desc))

        self._groups = columns

        for r in self._rows("config_schema",
                            ["schema_key", "label", "instruction"],
                            "ORDER BY sort_order"):
            key = _col(r, 0)
            fields = list(singles.get(key, []))
            for group_key, (schema_key, label, desc) in group_meta.items():
                if schema_key == key:
                    fields.append((group_key, label, "group", "group", desc,
                                   columns.get(group_key, [])))
            self.SCHEMAS[key] = {
                "label": _col(r, 1),
                "handler": _col(r, 2),
                "fields": fields,
            }

        # --- the templates -------------------------------------------------
        #
        # Keyed on (template_key, section_key), not section_key alone. Two
        # templates may both carry a section called "summary", and merging
        # their bindings would put a credit memorandum's fields into a KYC one
        # silently - which shows up as a memo saying something nobody
        # configured it to say.
        bindings = {}
        for r in self._rows("config_section_field",
                            ["template_key", "section_key", "field_key"],
                            "ORDER BY sort_order"):
            bindings.setdefault((_col(r, 0), _col(r, 1)), []).append(_col(r, 2))

        for r in self._rows("config_template", ["template_key", "label"],
                            "ORDER BY template_key"):
            key = _col(r, 0)
            self.TEMPLATES[key] = {
                "key": key,
                "label": _col(r, 1),
                "sections": [],
            }

        for r in self._rows(
            "config_section",
            ["template_key", "section_key", "numeral", "title", "kind",
             "shape_key", "prompt", "context_sections"],
            "ORDER BY template_key, sort_order",
        ):
            template_key = _col(r, 0)
            key = _col(r, 1)
            context = _col(r, 7)

            # A section whose template row is missing would otherwise vanish
            # without trace. Broken either way, but a template that appears
            # with its sections is diagnosable and one that silently does not
            # is a memo missing a section nobody can explain.
            template = self.TEMPLATES.setdefault(
                template_key,
                {"key": template_key, "label": template_key, "sections": []})

            template["sections"].append({
                "key": key,
                "num": _col(r, 2),
                "title": _col(r, 3),
                "kind": _col(r, 4),
                "shape": _col(r, 5),
                "prompt": _col(r, 6),
                "context_sections": context.split(",") if context else [],
                "fields": bindings.get((template_key, key), []),
            })

    # --- the pack's interface ---------------------------------------------

    def get_schema(self, schema_key):
        return self.SCHEMAS.get(schema_key)

    def schemas_for(self, document_type):
        spec = self.DOCUMENT_TYPES.get(document_type)
        return spec["schemas"] if spec else []

    def label_for(self, field_key):
        return self._labels.get(field_key, field_key)

    def group_columns(self, field_key):
        return self._groups.get(field_key)

    def document_type_list(self):
        return [
            {"key": key,
             "label": spec["label"],
             "category": self.CATEGORIES.get(spec["category"],
                                             spec["category"]),
             "description": spec["description"],
             "read_mode": spec["read_mode"],
             "always_ocr": spec["always_ocr"]}
            for key, spec in self.DOCUMENT_TYPES.items()
        ]

    def read_mode_for(self, document_type):
        spec = self.DOCUMENT_TYPES.get(document_type)
        return spec["read_mode"] if spec else "text"

    def always_ocr(self, document_type):
        spec = self.DOCUMENT_TYPES.get(document_type)
        return bool(spec and spec["always_ocr"])

    # --- the template's interface ------------------------------------------

    @property
    def TEMPLATE_KEY(self):
        """The default template.

        A tenant with one template has always had one, and every caller that
        predates this asks without naming it. Ordered by key, so the answer
        does not depend on the order rows came back."""
        keys = sorted(self.TEMPLATES)
        return keys[0] if keys else None

    @property
    def MEMO_SECTIONS(self):
        """The default template's sections."""
        return self.sections_for(self.TEMPLATE_KEY)

    def template_list(self):
        """Every template, for a person choosing which memo to write."""
        return [{"key": t["key"],
                 "label": t["label"] or t["key"],
                 "sections": len(t["sections"])}
                for t in sorted(self.TEMPLATES.values(),
                                key=lambda t: t["key"])]

    def has_template(self, template_key):
        return template_key in self.TEMPLATES

    def sections_for(self, template_key):
        """One template's sections, in order. An unknown template yields none -
        the caller validates; this does not invent one."""
        template = self.TEMPLATES.get(template_key)
        return template["sections"] if template else []

    def label_for_template(self, template_key):
        template = self.TEMPLATES.get(template_key)
        return (template["label"] or template_key) if template else template_key

    def sections_of_kind(self, kind, template_key=None):
        """Sections of one kind, from one template. Defaults to the tenant's
        only template, which is what every caller meant before there could be
        more than one."""
        sections = self.sections_for(template_key or self.TEMPLATE_KEY)
        return [s for s in sections if s["kind"] == kind]


def load(tenant_id, workspace_id, revision):
    """A revision, cached. Immutable, so the cache cannot go stale."""
    key = (int(tenant_id), int(workspace_id), int(revision))
    if key not in _CACHE:
        _CACHE[key] = Registry(*key)
    return _CACHE[key]


def workspaces(tenant_id):
    """The tenant's workspaces, oldest first.

    NOT A DELETED ONE (PACK-02 D). A deleted workspace is hidden for six
    months before it is removed, and this is where it is hidden: every list,
    every lookup by number and the one-workspace default read through here.
    Restoring it clears deleted_at, and it is back."""
    result = _sql(
        "SELECT workspace_id, name, active_revision FROM workspace "
        "WHERE tenant_id = :t AND deleted_at IS NULL ORDER BY workspace_id",
        [_p("t", int(tenant_id))])
    return [{"workspace_id": _col(r, 0), "name": _col(r, 1),
             "active_revision": _col(r, 2)}
            for r in result.get("records", [])]


def workspace(tenant_id, workspace_id=None):
    """Which workspace a request works in.

    NAMED, it must be one of this tenant's: the tenant comes from the token
    and a workspace number from the request, so this is the check that keeps
    one tenant out of another's configuration.

    NOT NAMED, the tenant's only workspace, and a refusal where it holds
    several (decision of 22 October 2026). A tenant with none - the pack
    tenant - is workspace 0."""
    held = workspaces(tenant_id)
    if workspace_id not in (None, ""):
        try:
            asked = int(workspace_id)
        except (TypeError, ValueError):
            raise ValueError("a workspace is named by its number")
        if asked == NO_WORKSPACE and not held:
            return NO_WORKSPACE
        if not any(w["workspace_id"] == asked for w in held):
            raise ValueError("this account has no workspace %d" % asked)
        return asked
    if not held:
        return NO_WORKSPACE
    if len(held) > 1:
        raise WorkspaceRequired(CHOOSE_A_WORKSPACE)
    return held[0]["workspace_id"]


def workspace_of(tenant_id, workspace_id):
    """The workspace a stored row belongs to.

    A row carries its own, and that is the answer - except 0 on a tenant that
    has workspaces, which is a row written by code that predates them. It was
    written in the tenant's only workspace, so it is read as that one; with
    several, nothing can say which, and the request is refused rather than
    answered from the wrong configuration."""
    if workspace_id:
        return int(workspace_id)
    return workspace(tenant_id)


def active_revision(tenant_id, workspace_id):
    """The revision a workspace's NEW work files against.

    Absent one, revision 1 - which is the pack every tenant was forked from
    and has in fact been extracting against all along. Workspace 0 reads the
    tenant's own column, which is where the pack tenant keeps it."""
    if int(workspace_id) == NO_WORKSPACE:
        result = _sql(
            "SELECT active_revision FROM tenant WHERE tenant_id = :t",
            [_p("t", int(tenant_id))])
    else:
        result = _sql(
            "SELECT active_revision FROM workspace "
            "WHERE tenant_id = :t AND workspace_id = :w",
            [_p("t", int(tenant_id)), _p("w", int(workspace_id))])
    records = result.get("records", [])
    if not records:
        return 1
    return int(_col(records[0], 0) or 1)


def for_workspace(tenant_id, workspace_id):
    """The workspace's active configuration."""
    return load(tenant_id, workspace_id,
                active_revision(tenant_id, workspace_id))
