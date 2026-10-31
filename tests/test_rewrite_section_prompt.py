"""
Rewrite's "Use this section's prompt" (31 October 2026): each saved section's
prompt as configured now, sent with the memo. Run from the repository root:

    python -m unittest discover -s tests

A saved heading is looked up in the revision the memo was written under, as
Update looks it up, and the prompt is the one in the revision in use - so a
section renamed since still finds it, and the prompt is today's.

Nothing reaches AWS: config is stubbed.
"""

import unittest
from unittest import mock

from api_modules import load_api
from test_memo_update import FakeRegistry, section


def prompted(key, num, title, prompt, kind="extract"):
    return dict(section(key, num, title, kind), prompt=prompt)


# The memo was written under 3; 9 is in use. Business is renamed Operations
# and given a new prompt, People has none, Summary was dropped.
REVISION_3 = [
    prompted("summary", "I", "Summary", "Two lines."),
    prompted("business", "II", "Business", "Old prompt."),
    prompted("people", "III", "People", None),
]
REVISION_9 = [
    prompted("business", "II", "Operations", "Present the lines as a table."),
    prompted("people", "III", "People", None),
]


class SectionPrompts(unittest.TestCase):
    def setUp(self):
        self.app = load_api()
        registries = {3: FakeRegistry(REVISION_3), 9: FakeRegistry(REVISION_9)}
        for name, kw in (("load", dict(side_effect=lambda t, w, r:
                                       registries[r])),
                         ("active_revision", dict(return_value=9))):
            p = mock.patch.object(self.app.config, name, **kw)
            p.start()
            self.addCleanup(p.stop)

    def prompts(self):
        return self.app._section_prompts(7, 3, "credit", 3)

    def test_a_renamed_section_gets_the_prompt_in_use(self):
        self.assertEqual(self.prompts()["ii. business"],
                         "Present the lines as a table.")

    def test_a_section_with_no_prompt_is_there_and_empty(self):
        self.assertEqual(self.prompts()["iii. people"], "")

    def test_a_section_the_configuration_dropped_is_absent(self):
        self.assertNotIn("i. summary", self.prompts())

    def test_a_saved_heading_is_matched_as_update_matches_it(self):
        norm = self.app._heading_norm
        self.assertEqual(norm("##  II.   Business"), "ii. business")
        self.assertEqual(norm("## . Business"), "business")

    def test_a_template_not_in_use_gives_nothing(self):
        self.assertEqual(self.app._section_prompts(7, 3, "kyc", 3), {})


if __name__ == "__main__":
    unittest.main()
