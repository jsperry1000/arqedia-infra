"""
The reviewer (REV-01). Run from the repository root:

    python -m unittest discover -s tests

What is tested is what decides money and what reaches the draft: a
suggestion keeps only what can be acted on and takes its current value from
the draft; an accept writes whole objects, refuses what has gone stale, and
runs quote, write, charge in that order, once per session.
"""

import datetime
import importlib
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

ENV = {"REVIEW_BUCKET": "review", "CLUSTER_ARN": "arn:cluster",
       "SECRET_ARN": "arn:secret", "DATABASE": "arqedia",
       "MODEL_ID": "sonnet", "AWS_LAMBDA_FUNCTION_NAME": "reviewer"}


def load_reviewer():
    """The reviewer, with boto3 and botocore replaced so nothing reaches
    AWS, and with editor, registry and wallet as it imported them."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    config = types.ModuleType("botocore.config")
    config.Config = mock.MagicMock()
    botocore.config = config
    fakes = {"boto3": boto3, "botocore": botocore,
             "botocore.exceptions": exceptions, "botocore.config": config}
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fakes), mock.patch.dict(os.environ, ENV):
        for name in ("app", "editor", "registry", "wallet"):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(ROOT / "lambda" / "reviewer"))
        sys.path.insert(1, str(ROOT / "lambda" / "shared"))
        try:
            return importlib.import_module("app")
        finally:
            sys.path[:] = saved
            sys.modules.pop("app", None)


def a_draft():
    return {
        "templates": [{"key": "credit", "label": "Credit Memorandum"}],
        "sections": [{
            "key": "summary", "numeral": "1", "title": "Summary",
            "kind": "extract", "prompt": "Summarise.", "template_key": "credit",
            "sort_order": 0, "context_sections": [], "fields": ["f_name"],
        }],
        "fields": [
            {"key": "f_name", "label": "Name", "type": "text",
             "cardinality": "one", "description": "The name.",
             "is_group": False, "columns": [], "found_in": ["coi"]},
            {"key": "f_holders", "label": "Holders", "type": "text",
             "cardinality": "group", "description": "Who holds shares.",
             "is_group": True, "found_in": ["register"],
             "columns": [{"key": "f_holders.name", "label": "Name",
                          "type": "text", "description": "Holder."}]},
        ],
        "document_types": [
            {"key": "coi", "label": "Certificate", "category": "corporate",
             "description": "A certificate.", "read_mode": "text",
             "always_ocr": False},
            {"key": "register", "label": "Register", "category": "corporate",
             "description": "A register.", "read_mode": "text",
             "always_ocr": True},
        ],
        "categories": [{"key": "corporate", "label": "Corporate"}],
    }


class CleanTest(unittest.TestCase):
    def setUp(self):
        self.r = load_reviewer()
        self.draft = a_draft()

    def clean(self, *suggestions, allowed=None, template_key=None):
        return self.r.clean(self.draft, {"suggestions": list(suggestions)},
                            allowed or self.r.KINDS, template_key)

    def test_current_comes_from_the_draft_not_the_model(self):
        kept, _ = self.clean({"kind": "field_description",
                              "target": {"field_key": "f_name"},
                              "current": "something the model made up",
                              "proposed": "The registered legal name."})
        self.assertEqual(kept[0]["current"], "The name.")

    def test_an_unknown_target_is_dropped(self):
        kept, dropped = self.clean({"kind": "field_description",
                                    "target": {"field_key": "f_nobody"},
                                    "proposed": "x"})
        self.assertEqual((kept, dropped), ([], 1))

    def test_a_kind_this_part_was_not_asked_for_is_dropped(self):
        kept, dropped = self.clean(
            {"kind": "section_prompt",
             "target": {"section_key": "summary"}, "proposed": "x"},
            allowed=("field_description",))
        self.assertEqual((kept, dropped), ([], 1))

    def test_a_proposal_the_same_as_now_is_dropped(self):
        kept, dropped = self.clean({"kind": "field_description",
                                    "target": {"field_key": "f_name"},
                                    "proposed": "The name."})
        self.assertEqual((kept, dropped), ([], 1))

    def test_found_in_must_name_types_the_draft_holds(self):
        kept, dropped = self.clean({"kind": "field_found_in",
                                    "target": {"field_key": "f_name"},
                                    "proposed": ["coi", "invented"]})
        self.assertEqual((kept, dropped), ([], 1))

    def test_found_in_is_the_whole_set_sorted(self):
        kept, _ = self.clean({"kind": "field_found_in",
                              "target": {"field_key": "f_name"},
                              "proposed": ["register", "coi"]})
        self.assertEqual(kept[0]["proposed"], ["coi", "register"])
        self.assertEqual(kept[0]["current"], ["coi"])

    def test_a_section_takes_its_memorandum_from_the_call(self):
        kept, _ = self.clean({"kind": "section_prompt",
                              "target": {"section_key": "summary"},
                              "proposed": "Lead with the name."},
                             template_key="credit")
        self.assertEqual(kept[0]["target"],
                         {"section_key": "summary", "template_key": "credit"})

    def test_a_new_field_with_a_label_already_held_is_dropped(self):
        kept, dropped = self.clean({
            "kind": "new_field",
            "target": {"template_key": "credit", "section_key": "summary"},
            "proposed": {"label": "name", "description": "d",
                         "is_table": False, "found_in": ["coi"]}})
        self.assertEqual((kept, dropped), ([], 1))

    def test_a_new_table_needs_a_column(self):
        kept, dropped = self.clean({
            "kind": "new_field",
            "target": {"template_key": "credit", "section_key": "summary"},
            "proposed": {"label": "Directors", "description": "d",
                         "is_table": True, "columns": [],
                         "found_in": ["register"]}})
        self.assertEqual((kept, dropped), ([], 1))

    def test_a_question_needs_a_question(self):
        kept, dropped = self.clean(
            {"kind": "question", "target": {"field_key": "f_name"},
             "question": ""},
            {"kind": "question", "target": {"field_key": "f_name"},
             "question": "Registered or trading name?"})
        self.assertEqual(dropped, 1)
        self.assertEqual(kept[0]["question"], "Registered or trading name?")


class BedrockClientTest(unittest.TestCase):
    """The first live review timed out on botocore's 60-second default."""

    def test_the_model_client_waits_as_long_as_compositions(self):
        r = load_reviewer()
        r.Config.assert_any_call(
            read_timeout=300, retries={"mode": "standard", "max_attempts": 2})


class AcceptTest(unittest.TestCase):
    """accept, with S3, the database, editor and wallet replaced."""

    SESSION = "a" * 32

    def setUp(self):
        self.r = load_reviewer()
        self.draft = a_draft()
        self.objects = {}
        self.calls = []

        opened = self.r._stamp()
        self.review = {"status": "ready", "opened_at": opened,
                       "suggestions": []}
        self.objects[self.r._review_key(7, self.SESSION)] = self.review

        self.r._get = lambda key: self.objects.get(key)
        self.r._put = lambda key, body: self.objects.__setitem__(key, body)
        self.r._plan_key = lambda tenant_id: "business"
        self.paid = None
        self.r._charged = lambda tenant_id, session_id: self.paid

        editor = mock.MagicMock()
        editor.draft.return_value = self.draft
        editor.save_field.side_effect = \
            lambda t, body: self.calls.append(("save_field", body)) \
            or {"key": body.get("key") or "f_new"}
        editor.save_section.side_effect = \
            lambda t, body: self.calls.append(("save_section", body))
        editor.save_document_type.side_effect = \
            lambda t, body: self.calls.append(("save_document_type", body))
        editor.set_field_documents.side_effect = \
            lambda t, k, types_: self.calls.append(("found_in", k, types_))
        editor.set_section_fields.side_effect = \
            lambda t, tpl, sec, keys: self.calls.append(("bind", sec, keys))
        self.r.editor = editor

        wallet = self.r.wallet
        self.quote = {"affordable": True, "total_cents": 100,
                      "available_cents": 500, "purchased_only": False,
                      "unit_cents": 100}
        wallet.quote = lambda t, e: self.calls.append(("quote", e)) \
            or self.quote
        wallet.charge = mock.MagicMock(
            side_effect=lambda *a, **k: self.calls.append(("charge", k))
            or {"entry_id": 91, "amount_cents": 100, "repeated": False})

    def suggest(self, **s):
        s.setdefault("id", "s-0001")
        s.setdefault("reason", "")
        s.setdefault("question", None)
        self.review["suggestions"].append(s)
        return s["id"]

    def accept(self, sid, role="admin", **kw):
        return self.r.accept(7, "a@firm.com", role, self.SESSION, sid, **kw)

    # --- whole objects -----------------------------------------------------

    def test_a_description_is_written_with_the_rest_of_the_field(self):
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_holders"},
                           current="Who holds shares.",
                           proposed="Each registered holder and stake.")
        self.accept(sid)
        [(_, body)] = [c for c in self.calls if c[0] == "save_field"]
        self.assertEqual(body["key"], "f_holders")
        self.assertEqual(body["cardinality"], "group")
        self.assertEqual(body["columns"][0]["key"], "f_holders.name")
        self.assertEqual(body["description"],
                         "Each registered holder and stake.")

    def test_a_prompt_keeps_the_section_and_leaves_its_order_alone(self):
        sid = self.suggest(kind="section_prompt",
                           target={"template_key": "credit",
                                   "section_key": "summary"},
                           current="Summarise.", proposed="Lead with it.")
        self.accept(sid)
        [(_, body)] = [c for c in self.calls if c[0] == "save_section"]
        self.assertEqual(body["title"], "Summary")
        self.assertEqual(body["kind"], "extract")
        self.assertNotIn("sort_order", body)
        self.assertNotIn("context_sections", body)

    def test_a_type_description_keeps_how_it_is_read(self):
        sid = self.suggest(kind="document_type_description",
                           target={"type_key": "register"},
                           current="A register.",
                           proposed="The register of members.")
        self.accept(sid)
        [(_, body)] = [c for c in self.calls
                       if c[0] == "save_document_type"]
        self.assertTrue(body["always_ocr"])
        self.assertEqual(body["category"], "corporate")

    def test_a_new_field_is_created_routed_and_bound(self):
        sid = self.suggest(kind="new_field",
                           target={"template_key": "credit",
                                   "section_key": "summary"},
                           current=None,
                           proposed={"label": "Incorporation date",
                                     "description": "d", "is_table": False,
                                     "columns": [], "found_in": ["coi"]})
        self.accept(sid, bind_to={"template_key": "credit",
                                  "section_key": "summary"})
        [(_, body)] = [c for c in self.calls if c[0] == "save_field"]
        self.assertNotIn("key", body)    # a create, never an overwrite
        self.assertIn(("found_in", "f_new", ["coi"]), self.calls)
        self.assertIn(("bind", "summary", ["f_name", "f_new"]), self.calls)

    # --- refusals ----------------------------------------------------------

    def test_stale_is_refused_and_nothing_is_written_or_charged(self):
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="What it said before.",
                           proposed="New.")
        with self.assertRaises(self.r.Stale):
            self.accept(sid)
        self.assertEqual([c for c in self.calls if c[0] != "quote"], [])
        self.r.wallet.charge.assert_not_called()

    def test_a_member_is_refused(self):
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        with self.assertRaises(PermissionError):
            self.accept(sid, role="member")

    def test_an_old_session_is_refused(self):
        self.review["opened_at"] = self.r._stamp(
            self.r._now() - datetime.timedelta(hours=25))
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        with self.assertRaises(ValueError):
            self.accept(sid)

    def test_a_closed_session_is_refused(self):
        self.objects[self.r._closed_key(7, self.SESSION)] = {"closed_at": "x"}
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        with self.assertRaises(ValueError):
            self.accept(sid)

    # --- money -------------------------------------------------------------

    def test_quote_then_write_then_charge(self):
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        self.accept(sid)
        order = [c[0] for c in self.calls]
        self.assertEqual(order, ["quote", "save_field", "charge"])
        _, kwargs = self.r.wallet.charge.call_args
        self.assertEqual(kwargs["idempotency_key"], "review:" + self.SESSION)

    def test_unaffordable_writes_nothing(self):
        self.quote = dict(self.quote, affordable=False, available_cents=10)
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        with self.assertRaises(self.r.wallet.InsufficientFunds):
            self.accept(sid)
        self.assertEqual([c[0] for c in self.calls], ["quote"])

    def test_a_paid_session_is_not_quoted_or_charged_again(self):
        self.paid = 91
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        out = self.accept(sid)
        self.assertEqual([c[0] for c in self.calls], ["save_field"])
        self.assertEqual(out["charged_cents"], 0)
        self.assertEqual(out["entry_id"], 91)

    def test_a_refused_write_is_not_charged(self):
        self.r.editor.save_field.side_effect = ValueError("refused")
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        with self.assertRaises(ValueError):
            self.accept(sid)
        self.r.wallet.charge.assert_not_called()

    # --- the person's own edit (inline edit before accept) -----------------

    def test_an_edited_description_is_written_whole_with_the_edit(self):
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_holders"},
                           current="Who holds shares.",
                           proposed="Each registered holder and stake.")
        out = self.accept(sid, value="  Each holder, stake and class.  ")
        [(_, body)] = [c for c in self.calls if c[0] == "save_field"]
        self.assertEqual(body["description"], "Each holder, stake and class.")
        # The rest of the field is written back as it was.
        self.assertEqual(body["cardinality"], "group")
        self.assertEqual(body["columns"][0]["key"], "f_holders.name")
        self.assertEqual(out["value"], "Each holder, stake and class.")

    def test_an_edited_prompt_is_written_and_the_section_kept(self):
        sid = self.suggest(kind="section_prompt",
                           target={"template_key": "credit",
                                   "section_key": "summary"},
                           current="Summarise.", proposed="Lead with it.")
        self.accept(sid, value="Lead with the name, then the number.")
        [(_, body)] = [c for c in self.calls if c[0] == "save_section"]
        self.assertEqual(body["prompt"], "Lead with the name, then the number.")
        self.assertEqual(body["title"], "Summary")
        self.assertNotIn("sort_order", body)

    def test_an_empty_edit_is_refused_and_nothing_is_written_or_charged(self):
        sid = self.suggest(kind="section_prompt",
                           target={"template_key": "credit",
                                   "section_key": "summary"},
                           current="Summarise.", proposed="Lead with it.")
        with self.assertRaises(ValueError):
            self.accept(sid, value="   ")
        self.assertEqual([c for c in self.calls if c[0] != "quote"], [])
        self.r.wallet.charge.assert_not_called()

    def test_no_edit_writes_the_suggestion_as_it_came(self):
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="The legal name.")
        self.accept(sid)
        [(_, body)] = [c for c in self.calls if c[0] == "save_field"]
        self.assertEqual(body["description"], "The legal name.")

    def test_an_edit_is_still_refused_when_the_draft_moved(self):
        # Stale is checked against what the review read, edit or no edit.
        sid = self.suggest(kind="field_description",
                           target={"field_key": "f_name"},
                           current="Something older.", proposed="New.")
        with self.assertRaises(self.r.Stale):
            self.accept(sid, value="My own wording.")
        self.assertEqual([c for c in self.calls if c[0] != "quote"], [])

    def test_a_question_cannot_be_accepted(self):
        sid = self.suggest(kind="question", target={"field_key": "f_name"},
                           current=None, proposed=None, question="Which?")
        with self.assertRaises(ValueError):
            self.accept(sid)
        self.assertEqual(self.calls, [])


class AnswerTest(unittest.TestCase):
    """A question answered (REV-01 S2): recorded, turned into one suggestion
    in the background, accepted like any other - and never charged by
    itself. AcceptTest's stubs, borrowed rather than inherited, so its tests
    do not run twice."""

    SESSION = AcceptTest.SESSION

    def setUp(self):
        AcceptTest.setUp(self)
        self.r._lambda = mock.MagicMock()
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.r._records = lambda t, s, kind: {
            v["suggestion_id"]: v for k, v in self.objects.items()
            if "/%s/" % kind in k}
        self.model = {"suggestions": [{
            "kind": "field_found_in", "target": {"field_key": "f_name"},
            "proposed": ["coi", "register"],
            "reason": "You said the register names it too."}]}
        self.r._invoke = lambda prompt, system: (
            json.dumps(self.model), {"input_tokens": 9, "output_tokens": 3},
            "end_turn")
        self.qid = AcceptTest.suggest(
            self, id="s-0024", kind="question",
            target={"field_key": "f_name"}, current=None, proposed=None,
            question="Is the name also on the register?")

    def answer(self, text="Yes, the register has it.", role="admin",
               qid=None):
        return self.r.answer(7, "a@firm.com", role, self.SESSION,
                             qid or self.qid, text)

    def read(self):
        return self.r._answer_read_safely(7, self.SESSION, self.qid)

    def record(self):
        return self.objects[self.r._answer_key(7, self.SESSION, self.qid)]

    def test_answering_records_it_and_starts_the_read(self):
        out = self.answer()
        self.assertEqual(out, {"suggestion_id": "s-0024",
                               "status": "answering"})
        self.assertEqual(self.record()["answer"], "Yes, the register has it.")
        call = self.r._lambda.invoke.call_args.kwargs
        self.assertEqual(call["InvocationType"], "Event")
        self.assertEqual(json.loads(call["Payload"])["action"], "answer_read")

    def test_the_read_makes_one_suggestion_with_the_drafts_current(self):
        self.answer()
        self.read()
        made = self.record()["suggestion"]
        self.assertEqual(made["id"], "s-0024-a")
        self.assertEqual(made["from_question"], "s-0024")
        self.assertEqual(made["current"], ["coi"])   # from the draft
        self.assertEqual(made["proposed"], ["coi", "register"])

    def test_an_answer_that_changes_nothing_says_so(self):
        self.model = {"suggestions": [{
            "kind": "question", "target": {"field_key": "f_name"},
            "question": "Which register?"}]}
        self.answer()
        self.read()
        self.assertEqual(self.record()["status"], "no_change")
        self.assertNotIn("suggestion", self.record())

    def test_a_model_failure_is_written_where_the_screen_polls(self):
        def broken(prompt, system):
            raise RuntimeError("model down")
        self.r._invoke = broken
        self.answer()
        self.assertEqual(self.read(), {"status": "failed"})
        self.assertEqual(self.record()["status"], "failed")

    def test_answering_and_reading_charge_nothing_and_write_nothing(self):
        self.answer()
        self.read()
        self.r.wallet.charge.assert_not_called()
        self.assertEqual([c for c in self.calls if c[0] != "quote"], [])

    def test_poll_shows_the_answer_and_the_suggestion_after_its_question(self):
        self.answer()
        self.read()
        listed = self.r.poll(7, self.SESSION)["suggestions"]
        ids = [s["id"] for s in listed]
        self.assertEqual(ids[ids.index("s-0024") + 1], "s-0024-a")
        question = listed[ids.index("s-0024")]
        self.assertEqual(question["answer"]["status"], "ready")
        self.assertEqual(listed[ids.index("s-0024-a")]["status"], "open")

    def test_poll_shows_what_was_written_including_an_edit(self):
        AcceptTest.suggest(self, id="s-0001", kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="The legal name.")
        self.r.accept(7, "a@firm.com", "admin", self.SESSION, "s-0001",
                      value="The registered legal name.")
        listed = {s["id"]: s for s in self.r.poll(7, self.SESSION)
                  ["suggestions"]}
        self.assertEqual(listed["s-0001"]["status"], "accepted")
        self.assertEqual(listed["s-0001"]["written"],
                         "The registered legal name.")
        self.assertEqual(listed["s-0001"]["proposed"], "The legal name.")
        self.assertNotIn("written", listed["s-0024"])   # never accepted

    def test_the_suggestion_is_accepted_and_charged_like_any_other(self):
        self.answer()
        self.read()
        out = self.r.accept(7, "a@firm.com", "admin", self.SESSION,
                            "s-0024-a")
        self.assertEqual(out["status"], "accepted")
        self.assertEqual([c[0] for c in self.calls],
                         ["quote", "found_in", "charge"])
        self.assertIn(("found_in", "f_name", ["coi", "register"]), self.calls)

    def test_a_paid_session_answers_and_accepts_with_no_second_charge(self):
        self.paid = 91
        self.answer()
        self.read()
        out = self.r.accept(7, "a@firm.com", "admin", self.SESSION,
                            "s-0024-a")
        self.r.wallet.charge.assert_not_called()
        self.assertEqual(out["charged_cents"], 0)

    def test_only_a_question_can_be_answered(self):
        AcceptTest.suggest(self, id="s-0001", kind="field_description",
                           target={"field_key": "f_name"},
                           current="The name.", proposed="New.")
        with self.assertRaises(ValueError):
            self.answer(qid="s-0001")
        with self.assertRaises(ValueError):
            self.answer(qid="s-9999")

    def test_an_empty_or_long_answer_is_refused(self):
        with self.assertRaises(ValueError):
            self.answer("   ")
        with self.assertRaises(ValueError):
            self.answer("x" * 2001)
        self.r._lambda.invoke.assert_not_called()

    def test_a_question_is_answered_once_unless_it_came_to_nothing(self):
        self.answer()
        with self.assertRaises(ValueError):
            self.answer("Again.")
        self.record()["status"] = "no_change"
        self.assertEqual(self.answer("Try this.")["status"], "answering")

    def test_a_member_a_closed_or_an_old_session_cannot_answer(self):
        with self.assertRaises(PermissionError):
            self.answer(role="member")
        self.objects[self.r._closed_key(7, self.SESSION)] = {"closed_at": "x"}
        with self.assertRaises(ValueError):
            self.answer()

    def test_an_unknown_answered_id_finds_nothing(self):
        # A made-up "-a" id must not reach storage through its question.
        with self.assertRaises(ValueError):
            self.r.accept(7, "a@firm.com", "admin", self.SESSION, "../x-a")


if __name__ == "__main__":
    unittest.main()
