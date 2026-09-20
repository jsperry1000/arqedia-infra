"""
A tenant's palette is four colours, and a colour it has not set falls back on
its own rather than on ours. Run from the repository root:

    python -m unittest discover -s tests

NEEDS REPORTLAB. style.py is the renderer's, and reportlab is where its colour
type comes from; in the Lambda it arrives in the docprocessing layer. Without
it this module fails to import and says so - which is the point. A palette
nobody can exercise is worse than one nobody wrote a test for.

    pip install reportlab
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lambda" / "render"))

import style  # noqa: E402 - the path above is what makes it importable


# A tenant's own three. Nothing like the platform's, so a fallback taking the
# wrong one is visible in the assertion rather than a coincidence.
DEEP = "#3B0A45"
MID = "#278ACA"
HIGHLIGHT = "#E8B10A"
LIGHT = "#F2E3F5"


def hexes(palette):
    """The palette as six-digit hex, which is how a person reads a colour."""
    return {k: v.hexval()[2:].upper() for k, v in palette.items()}


class PaletteTest(unittest.TestCase):

    def test_no_tenant_takes_the_platform_palette(self):
        """No tenant at all, and a tenant row with nothing set, are the same
        page: the platform's four. Base renders through this - _branding
        passes {} for any plan below Business."""
        for tenant in (None, {}, {"brand_deep": None, "brand_mid": None,
                                  "brand_highlight": None,
                                  "brand_light": None}):
            got = hexes(style.palette_for(tenant))
            self.assertEqual(got, {k: v[1:].upper()
                                   for k, v in style.DEFAULT_PALETTE.items()},
                             "tenant=%r" % (tenant,))
            # Named, because the pill is filled with it and a wrong light is
            # not obviously wrong on the page.
            self.assertEqual(got["light"], "C7E4F8")

    def test_three_colours_set_and_the_light_is_mixed_from_the_mid(self):
        """The case BR-01 was written for: a tenant chose three colours before
        there was a fourth to choose. The pill must not fall back to OUR pale
        blue in the middle of THEIR page."""
        got = hexes(style.palette_for({
            "brand_deep": DEEP, "brand_mid": MID, "brand_highlight": HIGHLIGHT,
        }))
        self.assertEqual(got["deep"], DEEP[1:])
        self.assertEqual(got["mid"], MID[1:])
        self.assertEqual(got["highlight"], HIGHLIGHT[1:])
        self.assertNotEqual(got["light"],
                            style.DEFAULT_PALETTE["light"][1:].upper())

    def test_four_colours_set_and_the_light_is_the_tenant_s_own(self):
        got = hexes(style.palette_for({
            "brand_deep": DEEP, "brand_mid": MID, "brand_highlight": HIGHLIGHT,
            "brand_light": LIGHT,
        }))
        self.assertEqual(got, {"deep": DEEP[1:], "mid": MID[1:],
                               "highlight": HIGHLIGHT[1:],
                               "light": LIGHT[1:]})

    def test_the_mix_is_the_mid_seven_tenths_of_the_way_to_white(self):
        """LIGHT_MIX, checked as arithmetic rather than as a hex literal: the
        number is a judgement about how pale a pill should be, and a test that
        restates the output tells nobody when it is changed."""
        self.assertEqual(style.LIGHT_MIX, 0.7)

        light = style.palette_for({"brand_mid": MID})["light"]
        mid = style.colors.HexColor(MID)
        for channel in ("red", "green", "blue"):
            start = getattr(mid, channel)
            self.assertAlmostEqual(getattr(light, channel),
                                   start + (1 - start) * 0.7, places=6)

        # 0x27/255 -> 0.7459, and so on. Written out so the expected page is
        # legible without running the arithmetic in your head.
        self.assertAlmostEqual(light.red, 0.745882, places=5)
        self.assertAlmostEqual(light.green, 0.862353, places=5)
        self.assertAlmostEqual(light.blue, 0.937647, places=5)

        # Paler than the mid it came from, on every channel. This is the whole
        # point of the fourth level.
        self.assertGreater(light.red, mid.red)
        self.assertGreater(light.green, mid.green)
        self.assertGreater(light.blue, mid.blue)

    def test_a_tenant_with_no_mid_takes_the_platform_light(self):
        """The mix needs a mid to mix. A tenant who set only its deep colour
        gets our pale blue rather than a light mixed from a colour it never
        chose."""
        got = hexes(style.palette_for({"brand_deep": DEEP}))
        self.assertEqual(got["deep"], DEEP[1:])
        self.assertEqual(got["light"], "C7E4F8")

    def test_an_unreadable_colour_never_stops_a_render(self):
        """A memorandum that will not render because somebody typed 'navy' in
        a colour field is a worse failure than a page in the wrong blue."""
        got = hexes(style.palette_for({
            "brand_deep": "navy", "brand_mid": MID, "brand_light": "",
        }))
        self.assertEqual(got["deep"],
                         style.DEFAULT_PALETTE["deep"][1:].upper())
        self.assertEqual(got["mid"], MID[1:])
        # An empty light is not a light: it mixes from the mid, as unset does.
        self.assertNotEqual(got["light"], "C7E4F8")


class PillStyleTest(unittest.TestCase):
    """The fourth-level heading reads its colours from the palette (BR-01)."""

    def test_the_pill_is_set_in_the_deep_not_reversed_out(self):
        palette = style.palette_for({"brand_deep": DEEP, "brand_mid": MID})
        styles = style.build_styles(palette)
        self.assertEqual(styles["pill"].textColor, palette["deep"])


if __name__ == "__main__":
    unittest.main()
