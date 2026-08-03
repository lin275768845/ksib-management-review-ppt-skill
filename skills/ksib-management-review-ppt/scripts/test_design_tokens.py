#!/usr/bin/env python3
"""Keep design tokens, OOXML policy, and the Golden Deck contract aligned."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ooxml_qa import (  # noqa: E402
    APPROVED_POINT_SIZES,
    APPROVED_TYPEFACES,
    KSIB_THEME_COLORS,
    KSIB_THEME_FONT_NAME,
    KSIB_THEME_NAME,
)
from ooxml_sanitize import (  # noqa: E402
    KSIB_PRIMARY_TYPEFACE,
    KSIB_THEME_COLORS as SANITIZER_THEME_COLORS,
    KSIB_THEME_FONT_NAME as SANITIZER_THEME_FONT_NAME,
    KSIB_THEME_NAME as SANITIZER_THEME_NAME,
)


class DesignTokenContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tokens = json.loads(
            (SKILL_DIR / "references/design-tokens.json").read_text(
                encoding="utf-8"
            )
        )
        cls.golden = json.loads(
            (
                SKILL_DIR
                / "references/golden-deck-format-contract.json"
            ).read_text(encoding="utf-8")
        )

    def test_theme_and_type_policy_match_runtime_constants(self) -> None:
        self.assertEqual(
            self.tokens["schemaVersion"],
            "ksib-design-tokens/1.0",
        )
        self.assertEqual(self.tokens["theme"]["name"], KSIB_THEME_NAME)
        self.assertEqual(
            self.tokens["theme"]["fontSchemeName"],
            KSIB_THEME_FONT_NAME,
        )
        self.assertEqual(
            self.tokens["theme"]["colors"],
            KSIB_THEME_COLORS,
        )
        self.assertEqual(
            self.tokens["theme"]["colors"],
            SANITIZER_THEME_COLORS,
        )
        self.assertEqual(SANITIZER_THEME_NAME, KSIB_THEME_NAME)
        self.assertEqual(
            SANITIZER_THEME_FONT_NAME,
            KSIB_THEME_FONT_NAME,
        )
        self.assertEqual(
            self.tokens["type"]["primaryTypeface"],
            KSIB_PRIMARY_TYPEFACE,
        )
        self.assertEqual(
            set(self.tokens["type"]["approvedTypefaces"]),
            APPROVED_TYPEFACES,
        )
        self.assertEqual(
            set(self.tokens["type"]["approvedPointSizes"]),
            APPROVED_POINT_SIZES,
        )

    def test_golden_deck_geometry_uses_current_tokens(self) -> None:
        deck_tokens = self.tokens["deck"]
        golden_deck = self.golden["deck"]
        self.assertEqual(golden_deck["widthIn"], deck_tokens["widthIn"])
        self.assertEqual(
            golden_deck["heightIn"],
            deck_tokens["heightIn"],
        )
        self.assertEqual(
            golden_deck["toleranceIn"],
            deck_tokens["geometryToleranceIn"],
        )
        for role, geometry in self.tokens["roleGeometry"].items():
            self.assertEqual(
                self.golden["roleGeometry"][role]["geometry"],
                geometry,
            )

    def test_exhibit_defaults_are_minimal_and_single_spotlight(self) -> None:
        exhibits = self.tokens["exhibits"]
        self.assertEqual(
            exhibits["defaultTableStyle"],
            "minimal-rule",
        )
        table_style = exhibits["tableStyles"]["minimal-rule"]
        self.assertEqual(table_style["headerFill"], "FFFFFF")
        self.assertEqual(table_style["tableTopRule"], "FF4906")
        self.assertEqual(table_style["headerRule"], "AEB2BA")
        self.assertEqual(table_style["totalRowTopRule"], "FF4906")
        self.assertFalse(table_style["outerBorder"])
        self.assertFalse(table_style["verticalBorders"])
        self.assertEqual(table_style["numericAlignment"], "right")
        self.assertEqual(
            exhibits["tableStyles"]["appendix-dense"][
                "zebraStripeMinimumRows"
            ],
            11,
        )
        self.assertEqual(
            exhibits["defaultChartStyle"],
            "direct-label-spotlight",
        )
        chart_style = exhibits["chartStyles"][
            "direct-label-spotlight"
        ]
        self.assertFalse(chart_style["chartBorder"])
        self.assertFalse(chart_style["plotBorder"])
        self.assertEqual(chart_style["maxSpotlightSeriesOrPoints"], 1)

    def test_fixed_chrome_uses_zero_emu_tolerance(self) -> None:
        deck = self.tokens["deck"]
        chrome = self.tokens["crossSlideChrome"]
        self.assertEqual(deck["fixedChromeGeometryToleranceEmu"], 0)
        self.assertEqual(
            chrome["schemaVersion"],
            "ksib-cross-slide-chrome/1.0",
        )
        self.assertEqual(chrome["geometryToleranceEmu"], 0)
        self.assertEqual(
            set(chrome["fixedRoles"]),
            {
                "header-accent",
                "header-text",
                "action-title",
                "subtitle",
                "title-divider",
                "footer-divider",
                "source-footnote",
                "page-number",
            },
        )
        self.assertIn("fill", chrome["styleEquality"])
        self.assertIn("fontSize", chrome["styleEquality"])
        self.assertIn("paragraphSpacing", chrome["styleEquality"])
        self.assertEqual(
            chrome["profileIds"],
            [
                "cover",
                "navigator",
                "section-divider",
                "content-title-only",
                "content-title-subtitle",
                "content-title-two-line",
                "content-title-two-line-subtitle",
                "appendix-divider",
                "appendix-title-only",
                "appendix-title-subtitle",
            ],
        )
        groups = self.golden["crossSlideEqualityGroups"]
        self.assertTrue(groups)
        self.assertTrue(
            all(group["geometryToleranceEmu"] == 0 for group in groups)
        )
        common_group = next(
            group
            for group in groups
            if group["id"] == "golden-common-chrome"
        )
        self.assertFalse(common_group["groupByHeaderMode"])
        self.assertEqual(
            set(common_group["roles"]),
            {
                "header-accent",
                "header-text",
                "footer-divider",
                "source-footnote",
                "page-number",
            },
        )

    def test_two_line_subtitle_profile_has_no_vertical_overlap(self) -> None:
        profile = self.tokens["headerModes"][
            "title-two-line-subtitle"
        ]
        title = profile["actionTitle"]
        subtitle = profile["subtitle"]
        self.assertLessEqual(
            title["y"] + title["h"],
            subtitle["y"],
        )
        self.assertLessEqual(
            subtitle["y"] + subtitle["h"],
            profile["dividerY"],
        )
        self.assertLess(
            profile["dividerY"],
            profile["bodyStartY"],
        )


if __name__ == "__main__":
    unittest.main()
