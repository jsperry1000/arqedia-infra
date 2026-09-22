"""
config/plans.json against the Paddle catalogue (18.5 / 11.3).

    python -m unittest discover -s tests

THE CHECK THIS FILE EXISTS FOR is one line: a plan's monthly_price_cents must
equal the amount on the Paddle price it names. Those two numbers are what a
customer is shown and what a customer is billed, they live in two files, and
nothing until now compared them. Everything else here is a guard on the file's
shape, so that the comparison cannot pass by accident - a plan with the key
misspelled would otherwise be silently skipped rather than caught.

ENTERPRISE IS SKIPPED BY NAME, which is to say by having no paddle_price_name.
Not by its plan_key: a plan is exempt because it is not sold through Paddle,
and testing the key would make "enterprise" a magic word in the checker as
well as in the catalogue.

IT IS NOT A CI GATE, and saying so is the point. .github/workflows holds
deploy-admin, deploy-frontend and deploy-site, and none of them runs a test:

    $ grep -ln "unittest\\|pytest" .github/workflows/*
    (no output)

So this fails for a person running the suite and blocks nothing on a merge.
That is the same gap CLAUDE.md records as "Does CI build the app", and this
check inherits it. Until CI runs tests, the discipline is a person running
them - which is what the worklist asks for on every branch.

Nothing reaches AWS: this reads two committed files and nothing else.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "config" / "plans.json"
PADDLE = ROOT / "config" / "paddle" / "sandbox.json"

# Every key a plan carries. Listed rather than inferred from the first row: a
# field dropped from every plan at once would otherwise pass.
FIELDS = (
    "plan_key", "name", "seat_count", "monthly_price_cents",
    "monthly_credit_cents", "share_allowance", "field_sets_per_type",
    "sections_per_template", "daily_classification_cents",
    "paddle_price_name", "how_it_starts", "active",
)

# A Paddle product that is not a plan. The top-up is a one-off purchase of
# metered credit, not a subscription, and it has no plan row to agree with.
NOT_A_PLAN = "ARQEDIA Top-up"


def plans():
    return json.loads(PLANS.read_text(encoding="utf-8"))["plans"]


def paddle_products():
    return json.loads(PADDLE.read_text(encoding="utf-8"))["products"]


class PriceAgreementTest(unittest.TestCase):
    """What a customer is shown, against what Paddle would bill."""

    def setUp(self):
        self.plans = plans()
        self.products = {p["name"]: p for p in paddle_products()}

    def test_every_priced_plan_agrees_with_its_paddle_price(self):
        checked = 0
        for plan in self.plans:
            name = plan["paddle_price_name"]
            if name is None:
                continue
            with self.subTest(plan=plan["plan_key"]):
                self.assertIn(
                    name, self.products,
                    "%s names a Paddle product that is not in the catalogue"
                    % plan["plan_key"])
                # Paddle records the amount as a string of cents.
                self.assertEqual(
                    plan["monthly_price_cents"],
                    int(self.products[name]["amount"]),
                    "%s is sold at %s and billed at %s"
                    % (plan["plan_key"], plan["monthly_price_cents"],
                       self.products[name]["amount"]))
                checked += 1
        self.assertEqual(checked, 2,
                         "expected Base and Small Business to be checked")

    def test_a_priced_plan_bills_monthly(self):
        """A plan billed one_time would take one payment and renew nothing."""
        for plan in self.plans:
            name = plan["paddle_price_name"]
            if name is None:
                continue
            with self.subTest(plan=plan["plan_key"]):
                self.assertEqual(self.products[name]["billing"], "month")

    def test_every_plan_product_in_the_catalogue_is_claimed(self):
        """The check the other way round. A price added to Paddle and not to
        plans.json is a thing a customer can be billed for that no plan
        describes."""
        named = {p["paddle_price_name"] for p in self.plans
                 if p["paddle_price_name"]}
        for product in paddle_products():
            if product["name"] == NOT_A_PLAN:
                continue
            with self.subTest(product=product["name"]):
                self.assertIn(product["name"], named)

    def test_enterprise_is_skipped_by_having_no_paddle_price(self):
        """Exempt because it is not sold through Paddle, not because of what
        it is called."""
        enterprise = [p for p in self.plans if p["plan_key"] == "enterprise"]
        self.assertEqual(len(enterprise), 1)
        self.assertIsNone(enterprise[0]["paddle_price_name"])
        self.assertIsNone(enterprise[0]["monthly_price_cents"])

    def test_the_prices_are_the_sandbox_ones(self):
        """Stated so the day this file gains a live catalogue is the day this
        test says so, rather than quietly comparing a sandbox price with a
        live one."""
        catalogue = json.loads(PADDLE.read_text(encoding="utf-8"))
        self.assertEqual(catalogue["environment"], "sandbox")


class TrialLengthTest(unittest.TestCase):
    """The published figure against the one that enforces it.

    THE TWO ARE DIFFERENT THINGS, deliberately. config/plans.json is what the
    marketing site and the application render at build; signup.TRIAL_DAYS is
    what computes tenant.trial_ends_at, and the signup Lambda bundles
    lambda/signup only, so it cannot read the file. This is what stops them
    parting - the same arrangement the plan prices have with Paddle.

    IT HAS PARTED BEFORE. Every customer-facing surface said 30 while the code
    said 14, from 17 to 22 September, including the summary shown immediately
    before somebody committed to a signup."""

    def setUp(self):
        self.doc = json.loads(PLANS.read_text(encoding="utf-8"))

    def enforced(self):
        """TRIAL_DAYS as the signup Lambda holds it, read from the source
        rather than imported: signup/app.py opens boto3 clients and reads six
        environment variables at import, and none of that is needed to read
        one integer."""
        text = (ROOT / "lambda" / "signup" / "app.py").read_text(
            encoding="utf-8")
        found = re.search(r"^TRIAL_DAYS\s*=\s*(\d+)\s*$", text, re.M)
        self.assertIsNotNone(found, "signup/app.py has no TRIAL_DAYS")
        return int(found.group(1))

    def test_the_file_states_a_trial_length(self):
        self.assertIsInstance(self.doc["trial_days"], int)
        self.assertGreater(self.doc["trial_days"], 0)

    def test_it_agrees_with_what_signup_enforces(self):
        self.assertEqual(
            self.doc["trial_days"], self.enforced(),
            "config/plans.json publishes a trial length the signup Lambda "
            "does not write")

    def test_it_is_outside_the_plans(self):
        """Every plan has the same trial. A per-plan field would be three
        copies of one number."""
        for plan in self.doc["plans"]:
            with self.subTest(plan=plan["plan_key"]):
                self.assertNotIn("trial_days", plan)

    def test_no_customer_facing_file_states_a_length_of_its_own(self):
        """The six places that said 30 now carry a token or an import. A
        number typed back into any of them is what this catches."""
        surfaces = [
            ROOT / "site" / "index.html",
            ROOT / "site" / "pricing" / "index.html",
            ROOT / "ui" / "src" / "App.tsx",
            ROOT / "ui" / "src" / "SignUp.tsx",
        ]
        for path in surfaces:
            text = path.read_text(encoding="utf-8")
            for phrase in ("30 days, full use", "30-day trial",
                           "30 days free"):
                with self.subTest(file=path.name, phrase=phrase):
                    self.assertNotIn(phrase, text)


class ShapeTest(unittest.TestCase):
    """Guards on the file, so the comparison above cannot pass by accident."""

    def setUp(self):
        self.plans = plans()

    def test_every_plan_carries_every_field(self):
        for plan in self.plans:
            with self.subTest(plan=plan.get("plan_key")):
                self.assertEqual(sorted(plan), sorted(FIELDS))

    def test_plan_keys_are_unique(self):
        keys = [p["plan_key"] for p in self.plans]
        self.assertEqual(len(keys), len(set(keys)))

    def test_a_priced_plan_carries_numbers(self):
        """Base and Small Business go into the plan table, whose seat_count,
        monthly_price_cents and monthly_credit_cents are NOT NULL. A string
        in any of them is a migration that fails on apply."""
        for plan in self.plans:
            if plan["paddle_price_name"] is None:
                continue
            with self.subTest(plan=plan["plan_key"]):
                for field in ("seat_count", "monthly_price_cents",
                              "monthly_credit_cents", "field_sets_per_type",
                              "sections_per_template",
                              "daily_classification_cents"):
                    self.assertIsInstance(plan[field], int, field)
                # share_allowance alone may be null: null is unlimited, as
                # migration 018 says, and it is the one nullable column.
                self.assertTrue(plan["share_allowance"] is None
                                or isinstance(plan["share_allowance"], int))

    def test_enterprise_carries_a_string_where_the_site_prints_one(self):
        """Null where a number would be a price; the page's own words
        everywhere else."""
        e = [p for p in self.plans if p["plan_key"] == "enterprise"][0]
        for field in ("seat_count", "monthly_credit_cents", "share_allowance",
                      "field_sets_per_type", "sections_per_template",
                      "daily_classification_cents"):
            with self.subTest(field=field):
                self.assertIsInstance(e[field], str, field)

    def test_how_it_starts_is_a_way_in(self):
        for plan in self.plans:
            with self.subTest(plan=plan["plan_key"]):
                self.assertRegex(plan["how_it_starts"], r"^(https://|mailto:)")

    def test_the_file_records_where_each_field_came_from(self):
        """Three of these numbers exist in no table and no constant - only in
        site/pricing/index.html. Somebody reading this file a year from now has
        to be able to find that out without being told."""
        doc = json.loads(PLANS.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(doc["sources"]),
            # topup_increment_cents is not one of a plan's fields - it sits
            # beside them, for the reason the file's own note gives - so it
            # is in "sources" without being in FIELDS.
            sorted(FIELDS + ("enterprise", "topup_increment_cents",
                             "trial_days")))
        for field in ("field_sets_per_type", "sections_per_template",
                      "daily_classification_cents"):
            self.assertIn("site/pricing/index.html", doc["sources"][field])


class TopUpIncrementTest(unittest.TestCase):
    """The one number on the pricing table that is not a plan attribute.

    It reads $5 in all three columns and has since 16 September 2026; before
    that it was $10, $25 and $5 x seats, which is why the row looks per-plan.
    One value, outside "plans", rendered into every column by
    site/plans-table.ts."""

    def setUp(self):
        self.doc = json.loads(PLANS.read_text(encoding="utf-8"))

    def test_it_is_a_number_outside_the_plans(self):
        self.assertIsInstance(self.doc["topup_increment_cents"], int)
        for plan in self.doc["plans"]:
            with self.subTest(plan=plan["plan_key"]):
                self.assertNotIn("topup_increment_cents", plan)

    def test_it_agrees_with_the_paddle_top_up_price(self):
        """The row says what a customer pays, and Paddle is what charges
        it."""
        product = next(p for p in paddle_products() if p["name"] == NOT_A_PLAN)
        self.assertEqual(self.doc["topup_increment_cents"],
                         int(product["amount"]))


if __name__ == "__main__":
    unittest.main()
