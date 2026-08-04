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
            "ksib-design-tokens/1.3",
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
        self.assertEqual(
            self.tokens["theme"]["themeColorContractVersion"],
            "ksib-theme-color-contract/1.0",
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
        self.assertEqual(chart_style["neutralSeries"], ["D9DCE1", "E5E6EB"])
        self.assertEqual(chart_style["baselineStroke"], "B9BDC5")
        self.assertEqual(chart_style["comparisonSpotlight"], "006B8F")
        semantic = self.tokens["theme"]["semanticPalette"]
        self.assertEqual(
            semantic["primaryRamp"],
            ["D83D00", "FF4906", "FFDBCD", "FFF7F3"],
        )
        self.assertEqual(semantic["contrastBase"], "006B8F")
        self.assertEqual(semantic["neutralSeries"], "D9DCE1")

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

    def test_action_title_is_single_line_and_has_no_default_divider(self) -> None:
        title_policy = self.tokens["titlePolicy"]
        self.assertEqual(title_policy["scope"], "content-action-title")
        self.assertEqual(title_policy["maxActionTitleLines"], 1)
        self.assertTrue(title_policy["forbidExplicitLineBreaks"])
        self.assertTrue(title_policy["forbidMultipleParagraphs"])
        self.assertEqual(title_policy["maxWeightedCharacters"], 38)
        self.assertEqual(
            title_policy["defaultTitleDividerPolicy"],
            "forbid",
        )
        self.assertEqual(
            set(self.tokens["headerModes"]),
            {"title-only", "title-subtitle"},
        )
        self.assertNotIn(
            "title-divider",
            self.tokens["crossSlideChrome"]["fixedRoles"],
        )
        for mode in self.tokens["headerModes"].values():
            self.assertEqual(mode["dividerPolicy"], "none")
            self.assertEqual(mode["maxActionTitleLines"], 1)

    def test_modern_open_body_spacing_matches_golden_contract(self) -> None:
        title_only = self.tokens["headerModes"]["title-only"]
        title_subtitle = self.tokens["headerModes"]["title-subtitle"]
        self.assertEqual(title_only["bodyStartY"], 1.52)
        self.assertEqual(title_subtitle["bodyStartY"], 1.66)
        self.assertGreaterEqual(
            title_only["bodyStartY"]
            - title_only["actionTitle"]["y"]
            - title_only["actionTitle"]["h"],
            title_only["titleBodyGapMinIn"],
        )
        self.assertGreaterEqual(
            title_subtitle["bodyStartY"]
            - title_subtitle["subtitle"]["y"]
            - title_subtitle["subtitle"]["h"],
            title_subtitle["subtitleBodyGapMinIn"],
        )
        self.assertEqual(
            set(self.golden["headerModes"]),
            {"none", "title-only", "title-subtitle"},
        )
        for mode_name in ("title-only", "title-subtitle"):
            golden_mode = self.golden["headerModes"][mode_name]
            self.assertEqual(
                golden_mode["bodyStartY"],
                self.tokens["headerModes"][mode_name]["bodyStartY"],
            )
            self.assertIn("title-divider", golden_mode["forbiddenRoles"])

    def test_bottom_band_spacing_has_safe_minimum_and_point_three_default(self) -> None:
        spacing = self.tokens["spacing"]
        self.assertEqual(spacing["bodyToBottomBandGapMinimumIn"], 0.15)
        self.assertEqual(spacing["bodyToBottomBandGapIn"], 0.3)
        self.assertGreater(
            spacing["bodyToBottomBandGapIn"],
            spacing["bodyToBottomBandGapMinimumIn"],
        )

if __name__ == "__main__":
    unittest.main()
