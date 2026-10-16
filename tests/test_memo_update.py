"""
Update: a saved memo written again from the configuration in use and the
documents filed now, with what is new set beside the saved text (decision of
16 October 2026).

    python -m unittest discover -s tests

WHAT THESE ARE ABOUT, in the order the decision put them:

  * The saved text is the base and comes back character for character. It is
    asserted on the row's output, not trusted to the model: the model only
    says what to add and where.
  * Sections match by section_key, worked out from each revision's headings.
    A section renamed in the configuration still matches; a heading retyped
    in the memo does not, and that section is left alone.
  * A contradiction is an Open Item - in the Open Items section where the memo
    has one, inline otherwise - and never a change to the saved sentence.
  * A section new in the template is offered whole; one the template dropped
    is kept.
  * revise takes the revision and the documents filed since from the Update
    rows it accepts, and from nowhere else. Every other save is as it was.
  * Update is charged as a generation, and every refusal is above the charge.

WHAT THESE CANNOT SHOW. Whether the model judges "already covered" correctly.
The model is a stub here; that judgement is the accepted weak point and is
observed on dev, not asserted.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows
from test_section_prompt import load_composition

TENANT = 7
MEMO = 120
RUN = "a" * 32
EMAIL = "susan@vantage.test"


def section(key, num, title, kind="extract"):
    return {"key": key, "num": num, "title": title, "kind": kind,
            "prompt": None, "fields": []}


class FakeRegistry:
    """One revision of one template: its sections, in order."""

    def __init__(self, sections, template="credit"):
        self.template = template
        self.sections = sections

    def has_template(self, key):
        return key == self.template

    def sections_for(self, key):
        return list(self.sections)

    def label_for_template(self, key):
        return "Credit Memorandum"


# The memo as a person saved it, under revision 3. Section II's second
# paragraph is theirs; III's heading was retyped by hand.
SAVED = "\n".join([
    "# Credit Memorandum",
    "",
    "| | |",
    "|---|---|",
    "| **Subject** | Meridian |",
    "",
    "---",
    "",
    "## I. Summary",
    "",
    "Meridian trades pecans. *a.pdf, page 1*",
    "",
    "## II. Business",
    "",
    "Meridian buys from three growers. *a.pdf, page 2*",
    "",
    "We have met all three growers ourselves.",
    "",
    "## III. Our view of the people",
    "",
    "Two directors. *a.pdf, page 3*",
    "",
    "## VIII. Open Items",
    "",
    "> **Gap.** No audited accounts.",
    "",
])

REVISION_3 = [
    section("summary", "I", "Summary"),
    section("business", "II", "Business"),
    section("people", "III", "People"),
    section("open_items", "VIII", "Open Items", kind="composed"),
]

# Revision 9: Business renamed Operations, a Sanctions section added.
REVISION_9 = [
    section("summary", "I", "Summary"),
    section("business", "II", "Operations"),
    section("people", "III", "People"),
    section("sanctions", "IV", "Sanctions"),
    section("open_items", "VIII", "Open Items", kind="composed"),
]

FRESH = {
    "summary": "## I. Summary\n\nMeridian trades pecans. *a.pdf, page 1*\n",
    "business": ("## II. Operations\n\nMeridian buys from four growers. "
                 "*b.pdf, page 1* A new grower in Texas. *b.pdf, page 2*\n"),
    "people": "## III. People\n\nTwo directors. *a.pdf, page 3*\n",
    "sanctions": "## IV. Sanctions\n\nNo match. *c.pdf, page 1*\n",
    "open_items": "## VIII. Open Items\n\n> **Gap.** No audited accounts.\n",
}


def value(param):
    """A Data API parameter back as Python. isNull is None, not True."""
    cell = param["value"]
    return None if cell.get("isNull") else list(cell.values())[0]


class UpdateRun(unittest.TestCase):
    """composition's _update, over the saved memo above."""

    def setUp(self):
        self.app = load_composition()
        self.rows = []
        self.puts = []
        self.answers = {}
        self.calls = []
        self.registries = {3: FakeRegistry(REVISION_3),
                           9: FakeRegistry(REVISION_9)}

        def sql(statement, params=None):
            if "FROM memo WHERE" in statement:
                return rows(("curated", "memos/120.md", 3, "credit", 42))
            if "INSERT INTO memo_rewrite" in statement:
                self.rows.append({p["name"]: value(p) for p in params})
                return {"generatedFields": [{"longValue": 500 + len(self.rows)}]}
            raise AssertionError("unexpected SQL: " + statement)

        def get_object(Bucket, Key):
            if Key == "memos/120.md":
                body = mock.MagicMock()
                body.read.return_value = SAVED.encode("utf-8")
                return {"Body": body}
            raise self.app.ClientError("NoSuchKey")

        def write_sections(registry, template_key, values, subject):
            sections = registry.sections_for(template_key)
            assembled = {s["key"]: {"num": s["num"], "title": s["title"],
                                    "markdown": FRESH[s["key"]],
                                    "values": []}
                         for s in sections}
            return sections, assembled, [], 0, 0

        def invoke(prompt, system=None, stage="?", section="?", chars_in=0):
            self.calls.append(section)
            return (json.dumps(self.answers.get(section, {})),
                    {"input_tokens": 10, "output_tokens": 5})

        patches = [
            mock.patch.object(self.app, "_sql", side_effect=sql),
            mock.patch.object(self.app._s3, "get_object",
                              side_effect=get_object),
            mock.patch.object(self.app._s3, "put_object",
                              side_effect=lambda **k: self.puts.append(k)),
            mock.patch.object(self.app.config, "load",
                              side_effect=lambda t, r: self.registries[r]),
            mock.patch.object(self.app, "_load_values",
                              return_value=[{"document_id": 1}]),
            mock.patch.object(self.app, "_subject_of", return_value=None),
            mock.patch.object(self.app, "_write_sections",
                              side_effect=write_sections),
            mock.patch.object(self.app, "_invoke", side_effect=invoke),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_update(self):
        result = self.app._update({
            "action": "update", "tenant_id": TENANT, "memo_id": MEMO,
            "engagement_id": 42, "template_key": "credit",
            "config_revision": 9, "run": RUN, "requested_by": EMAIL})
        state = json.loads(self.puts[-1]["Body"].decode("utf-8"))
        return result, state

    def row_for(self, heading):
        found = [r for r in self.rows if r["heading"] == heading]
        self.assertEqual(len(found), 1, heading)
        return found[0]

    def saved_section(self, heading):
        for s in self.app._split_saved(SAVED):
            if s["heading"] == heading:
                return s["text"]
        raise KeyError(heading)

    # --- nothing has changed --------------------------------------------

    def test_nothing_new_writes_no_row_and_says_so(self):
        result, state = self.run_update()
        self.assertEqual(result["status"], "done")
        self.assertEqual(state["status"], "done")
        # Only the section new in the template is offered.
        self.assertEqual([r["heading"] for r in self.rows],
                         ["## IV. Sanctions"])
        # Summary, Business and Open Items compared and found unchanged.
        self.assertEqual(state["unchanged"], 3)
        self.assertEqual(state["changed"], 0)

    # --- a rename -------------------------------------------------------

    def test_a_renamed_section_still_matches_by_key(self):
        _, state = self.run_update()
        # "## II. Business" under 3 is "business"; so is "II. Operations"
        # under 9. Compared, not offered as new, not kept aside.
        self.assertIn("business", self.calls)
        self.assertNotIn("## II. Business", state["kept"])
        self.assertNotIn("## II. Operations", [r["heading"] for r in self.rows])

    # --- a changed value ------------------------------------------------

    def test_an_addition_is_put_in_and_the_saved_text_is_untouched(self):
        self.answers["business"] = {"additions": [
            {"after": 1, "text": "A new grower in Texas. [[C3]]"}]}
        self.run_update()
        row = self.row_for("## II. Business")
        saved = self.saved_section("## II. Business")
        self.assertEqual(row["input"], saved)
        # Every saved line, in order, unchanged.
        out = row["output"].split("\n")
        it = iter(out)
        for line in saved.rstrip().split("\n"):
            self.assertIn(line, it)
        # The addition sits after the first block, with its citation back.
        self.assertIn("A new grower in Texas. *b.pdf, page 2*", row["output"])
        self.assertLess(
            row["output"].index("three growers"),
            row["output"].index("A new grower in Texas"))
        self.assertLess(
            row["output"].index("A new grower in Texas"),
            row["output"].index("We have met all three growers"))
        self.assertEqual(row["revision"], 9)
        self.assertEqual(row["status"], "done")

    def test_an_addition_with_no_citation_is_discarded(self):
        self.answers["business"] = {"additions": [
            {"after": 1, "text": "Meridian is a fine business."}]}
        _, state = self.run_update()
        self.assertNotIn("## II. Business", [r["heading"] for r in self.rows])
        self.assertEqual(state["uncited_discarded"], 1)

    # --- a contradiction -----------------------------------------------

    def test_a_contradiction_goes_to_the_open_items_section(self):
        self.answers["business"] = {"open_items": [
            {"after": 1, "text": "The memorandum states three growers; the "
                                 "documents now on file state four. [[C2]]"}]}
        self.run_update()
        # Business itself is untouched: no row for it.
        self.assertNotIn("## II. Business", [r["heading"] for r in self.rows])
        row = self.row_for("## VIII. Open Items")
        self.assertTrue(row["output"].startswith(
            self.saved_section("## VIII. Open Items").rstrip()))
        self.assertIn("> **Open item.** The memorandum states three growers",
                      row["output"])
        self.assertIn("*b.pdf, page 1*", row["output"])

    def test_without_an_open_items_section_it_is_inline(self):
        global SAVED
        original = SAVED
        SAVED = original.split("## VIII. Open Items")[0]
        self.addCleanup(lambda: globals().__setitem__("SAVED", original))
        self.answers["business"] = {"open_items": [
            {"after": 1, "text": "Three growers here; four on file. [[C2]]"}]}
        self.run_update()
        row = self.row_for("## II. Business")
        self.assertIn("> **Open item.** Three growers here; four on file. "
                      "*b.pdf, page 1*", row["output"])
        self.assertIn("We have met all three growers ourselves.",
                      row["output"])

    # --- what is left alone ---------------------------------------------

    def test_a_retyped_heading_is_kept_and_not_offered_again(self):
        _, state = self.run_update()
        self.assertIn("## III. Our view of the people", state["kept"])
        self.assertNotIn("people", self.calls)
        # Not offered as new either: the template had it when this memo was
        # written, so a person changed it, and putting it back would undo
        # them.
        self.assertNotIn("## III. People", [r["heading"] for r in self.rows])

    def test_a_section_new_in_the_template_is_offered_whole(self):
        self.run_update()
        row = self.row_for("## IV. Sanctions")
        self.assertEqual(row["input"], "")
        self.assertEqual(row["output"], FRESH["sanctions"].rstrip() + "\n")

    def test_every_row_is_marked_as_update(self):
        self.answers["business"] = {"additions": [
            {"after": 1, "text": "A new grower. [[C3]]"}]}
        self.run_update()
        for row in self.rows:
            self.assertEqual(row["prompt"], self.app.cleanup.UPDATE_ROW_PROMPT)
            self.assertEqual(row["revision"], 9)

    # --- failure --------------------------------------------------------

    def test_a_reply_that_is_not_json_fails_that_section_only(self):
        original = self.app._invoke.side_effect

        def invoke(prompt, system=None, stage="?", section="?", chars_in=0):
            if section == "business":
                return "I could not do that.", {"output_tokens": 3}
            return original(prompt, system, stage, section, chars_in)

        self.app._invoke.side_effect = invoke
        result, state = self.run_update()
        self.assertEqual(result["status"], "done")
        row = self.row_for("## II. Business")
        self.assertEqual(row["status"], "failed")
        self.assertIsNone(row["output"])
        self.assertEqual(state["failed_sections"], 1)

    def test_a_finished_run_is_not_run_again(self):
        done = {"status": "done", "run": RUN}
        with mock.patch.object(self.app, "_get_update", return_value=done):
            result = self.app._update({
                "tenant_id": TENANT, "memo_id": MEMO, "run": RUN,
                "config_revision": 9})
        self.assertEqual(result["status"], "already-done")
        self.assertEqual(self.calls, [])


class Insertion(unittest.TestCase):
    """_insert, on its own: the saved lines are never touched."""

    def setUp(self):
        self.app = load_composition()

    def test_after_zero_is_before_the_first_block(self):
        text = "## I. A\n\nfirst\n\nsecond"
        self.assertEqual(self.app._insert(text, [(0, "new")]),
                         "## I. A\n\nnew\n\nfirst\n\nsecond")

    def test_past_the_last_block_is_after_it(self):
        text = "## I. A\n\nfirst\n"
        self.assertEqual(self.app._insert(text, [(9, "new")]),
                         "## I. A\n\nfirst\n\nnew\n")

    def test_a_table_is_one_block(self):
        text = "## I. A\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nafter"
        out = self.app._insert(text, [(1, "new")])
        self.assertEqual(out, "## I. A\n\n| a | b |\n|---|---|\n| 1 | 2 |"
                              "\n\nnew\n\nafter")


class UpdateRoute(unittest.TestCase):
    """The API's half: what is refused, what is charged, what is sent."""

    def setUp(self):
        self.app = load_api()
        self.charges, self.invocations, self.puts = [], [], []
        self.memo = (("credit", 42, 100, 2),)
        self.registry = FakeRegistry(REVISION_9)

        patches = [
            mock.patch.object(self.app, "_sql",
                              side_effect=lambda s, p=None: rows(*self.memo)),
            mock.patch.object(self.app.config, "active_revision",
                              return_value=9),
            mock.patch.object(self.app.config, "load",
                              side_effect=lambda t, r: self.registry),
            mock.patch.object(self.app.wallet, "charge",
                              side_effect=lambda *a, **k:
                                  self.charges.append((a, k))),
            mock.patch.object(self.app._lambda, "invoke",
                              side_effect=lambda **k:
                                  self.invocations.append(k)),
            mock.patch.object(self.app._s3, "put_object",
                              side_effect=lambda **k: self.puts.append(k)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_it_charges_as_a_generation_and_runs_under_the_revision_in_use(self):
        started = self.app.update_memo(TENANT, EMAIL, MEMO, "idem-1")
        self.assertEqual(started["config_revision"], 9)
        [(args, kwargs)] = self.charges
        self.assertEqual(args[2], "memo_generated")
        self.assertEqual(args[3], 1)
        self.assertEqual(kwargs["idempotency_key"], "idem-1")
        self.assertIn("update of memo 100.2", kwargs["reference"])
        payload = json.loads(self.invocations[0]["Payload"])
        self.assertEqual(payload["action"], "update")
        self.assertEqual(payload["config_revision"], 9)
        self.assertEqual(payload["memo_id"], MEMO)
        self.assertEqual(payload["engagement_id"], 42)
        # The run exists before composition is asked to finish it.
        state = json.loads(self.puts[0]["Body"].decode("utf-8"))
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["run"], payload["run"])

    def test_a_repeated_click_gets_its_run_and_starts_nothing(self):
        first = self.app.update_memo(TENANT, EMAIL, MEMO, "idem-1")
        self.app.wallet.charge.side_effect = lambda *a, **k: {"repeated": True}
        again = self.app.update_memo(TENANT, EMAIL, MEMO, "idem-1")
        self.assertEqual(again["status"], "repeated")
        self.assertEqual(again["run"], first["run"])
        self.assertEqual(len(self.invocations), 1)
        self.assertEqual(len(self.puts), 1)

    def test_no_engagement_is_refused_before_the_charge(self):
        self.memo = (("credit", None, 100, 2),)
        with self.assertRaises(ValueError):
            self.app.update_memo(TENANT, EMAIL, MEMO, "idem-1")
        self.assertEqual(self.charges, [])
        self.assertEqual(self.invocations, [])

    def test_a_template_not_in_use_is_refused_before_the_charge(self):
        self.memo = (("kyc", 42, 100, 2),)
        with self.assertRaises(ValueError):
            self.app.update_memo(TENANT, EMAIL, MEMO, "idem-1")
        self.assertEqual(self.charges, [])

    def test_a_memo_that_is_not_there_is_none(self):
        self.memo = ()
        self.assertIsNone(self.app.update_memo(TENANT, EMAIL, MEMO, "k"))
        self.assertEqual(self.charges, [])

    def test_a_run_id_that_is_not_one_is_refused(self):
        with self.assertRaises(ValueError):
            self.app.update_progress(TENANT, MEMO, "../../other")


class ReviseFromUpdate(unittest.TestCase):
    """revise_memo's two changes, and that every other save is unchanged."""

    def setUp(self):
        self.app = load_api()
        self.statements = []
        self.update_revisions = ()

        def sql(statement, params=None):
            values = {p["name"]: value(p) for p in (params or [])}
            self.statements.append((statement, values))
            if "SELECT s3_key, template_key, config_revision" in statement:
                return rows(("memos/100.md", "credit", 3, None, 1, 42,
                             "live"))
            if "FROM memo_source ms" in statement:
                return rows(("a.pdf",))
            if "state = 'filed' AND active = 1" in statement:
                return rows((8, "b.pdf"), (9, "b.pdf"), (5, "a.pdf"))
            if "SELECT rewrite_id FROM memo_rewrite" in statement:
                return rows(*[(r,) for r in (501,)])
            if "DISTINCT config_revision" in statement:
                return rows(*self.update_revisions)
            if "MAX(revision)" in statement:
                return rows((1,))
            if "INSERT INTO memo" in statement and "memo_source" not in \
                    statement:
                return {"generatedFields": [{"longValue": 777}]}
            return rows()

        patches = [
            mock.patch.object(self.app, "_sql", side_effect=sql),
            mock.patch.object(self.app._s3, "put_object",
                              return_value={"VersionId": "v1"}),
            mock.patch.object(self.app._lambda, "invoke"),
            mock.patch.object(self.app, "_put_working"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def inserted_memo(self):
        [values] = [v for s, v in self.statements
                    if "INSERT INTO memo" in s and "s3_version_id" in s]
        return values

    def added_sources(self):
        return sorted(v["d"] for s, v in self.statements
                      if "VALUES (:new_id, :d, :t)" in s)

    def test_an_ordinary_save_inherits_the_parents_revision(self):
        self.app.revise_memo(TENANT, EMAIL, MEMO, "Text. *a.pdf, page 1*")
        self.assertEqual(self.inserted_memo()["config_revision"], 3)

    def test_an_ordinary_save_still_refuses_a_document_filed_since(self):
        with self.assertRaises(ValueError) as caught:
            self.app.revise_memo(TENANT, EMAIL, MEMO,
                                 "New. *b.pdf, page 1*")
        self.assertIn("b.pdf", str(caught.exception))

    def test_an_update_save_records_the_new_revision(self):
        out = self.app.revise_memo(TENANT, EMAIL, MEMO,
                                   "Text. *a.pdf, page 1*", [501],
                                   config_revision=9, add_sources=True)
        self.assertEqual(self.inserted_memo()["config_revision"], 9)
        self.assertEqual(out["config_revision"], 9)

    def test_an_update_save_takes_in_a_document_filed_since(self):
        self.app.revise_memo(TENANT, EMAIL, MEMO,
                             "New grower. *b.pdf, page 1*", [501],
                             config_revision=9, add_sources=True)
        # Both documents in the file called b.pdf; a.pdf was already one.
        self.assertEqual(self.added_sources(), [8, 9])

    def test_an_update_save_adds_only_what_the_text_cites(self):
        self.app.revise_memo(TENANT, EMAIL, MEMO, "Text. *a.pdf, page 1*",
                             [501], config_revision=9, add_sources=True)
        self.assertEqual(self.added_sources(), [])

    def test_an_update_save_still_refuses_a_document_nobody_filed(self):
        with self.assertRaises(ValueError):
            self.app.revise_memo(TENANT, EMAIL, MEMO, "X. *made-up.pdf*",
                                 [501], config_revision=9, add_sources=True)

    def test_the_revision_comes_from_the_rows(self):
        self.update_revisions = ((9,),)
        self.assertEqual(self.app._update_revision(TENANT, MEMO, [501]), 9)

    def test_no_update_rows_means_no_update(self):
        self.assertIsNone(self.app._update_revision(TENANT, MEMO, [501]))
        self.assertIsNone(self.app._update_revision(TENANT, MEMO, []))

    def test_rows_from_two_revisions_are_refused(self):
        self.update_revisions = ((9,), (10,))
        with self.assertRaises(ValueError):
            self.app._update_revision(TENANT, MEMO, [501, 502])


if __name__ == "__main__":
    unittest.main()
