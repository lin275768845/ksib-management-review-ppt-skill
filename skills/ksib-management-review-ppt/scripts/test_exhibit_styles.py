#!/usr/bin/env python3
"""Regression tests for the Golden Deck's MBB table and chart styling."""

from __future__ import annotations

import json
import os
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
PUBLISHED_GOLDEN_PPTX = (
    SKILL_DIR
    / "benchmarks"
    / "format-golden-deck"
    / "output"
    / "KSIB_MBB_FORMAT_GOLDEN_DECK_V1.pptx"
)
GOLDEN_PPTX = Path(
    os.environ.get("KSIB_GOLDEN_PPTX", PUBLISHED_GOLDEN_PPTX)
)
GOLDEN_BUILD = (
    SKILL_DIR
    / "benchmarks"
    / "format-golden-deck"
    / "build.mjs"
)
GOLDEN_FORMAT_CONTRACT = (
    SKILL_DIR
    / "references"
    / "golden-deck-format-contract.json"
)

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A_NS, "c": C_NS, "p": P_NS}


def read_xml(package: zipfile.ZipFile, part: str) -> ET.Element:
    return ET.fromstring(package.read(part))


def direct_fill(cell: ET.Element) -> str | None:
    node = cell.find("./a:tcPr/a:solidFill/a:srgbClr", NS)
    return node.get("val") if node is not None else None


def border_fill(cell: ET.Element, side: str) -> str | None:
    node = cell.find(
        f"./a:tcPr/a:ln{side}/a:solidFill/a:srgbClr",
        NS,
    )
    return node.get("val") if node is not None else None


def border_is_none(cell: ET.Element, side: str) -> bool:
    return cell.find(f"./a:tcPr/a:ln{side}/a:noFill", NS) is not None


def function_body(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.index(marker)
    open_paren = source.index("(", start)
    paren_depth = 0
    close_paren = None
    for index in range(open_paren, len(source)):
        if source[index] == "(":
            paren_depth += 1
        elif source[index] == ")":
            paren_depth -= 1
            if paren_depth == 0:
                close_paren = index
                break
    if close_paren is None:
        raise AssertionError(f"Unclosed function parameters: {name}")
    brace = source.index("{", close_paren)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:index]
    raise AssertionError(f"Unclosed function body: {name}")


class GoldenExhibitStyleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not GOLDEN_PPTX.is_file():
            raise AssertionError(f"Golden Deck not found: {GOLDEN_PPTX}")
        cls.package = zipfile.ZipFile(GOLDEN_PPTX)
        cls.build_source = GOLDEN_BUILD.read_text(encoding="utf-8")
        cls.format_contract = json.loads(
            GOLDEN_FORMAT_CONTRACT.read_text(encoding="utf-8")
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.package.close()

    def test_analysis_table_uses_white_header_and_no_vertical_grid(self) -> None:
        root = read_xml(self.package, "ppt/slides/slide3.xml")
        rows = root.findall(".//a:tbl/a:tr", NS)
        self.assertEqual(len(rows), 6)
        for row in rows:
            for cell in row.findall("./a:tc", NS):
                self.assertTrue(border_is_none(cell, "L"))
                self.assertTrue(border_is_none(cell, "R"))
        for cell in rows[0].findall("./a:tc", NS):
            self.assertEqual(direct_fill(cell), "FFFFFF")
            self.assertEqual(border_fill(cell, "T"), "FF4906")
            self.assertEqual(border_fill(cell, "B"), "AEB2BA")
        for row in rows[1:-1]:
            for cell in row.findall("./a:tc", NS):
                self.assertTrue(border_is_none(cell, "T"))
                self.assertTrue(border_is_none(cell, "B"))
        for cell in rows[-1].findall("./a:tc", NS):
            self.assertEqual(direct_fill(cell), "FFFFFF")
            self.assertTrue(border_is_none(cell, "B"))

    def test_analysis_table_total_rule_is_an_independent_native_shape(self) -> None:
        build_table_slide = function_body(
            self.build_source,
            "buildTableSlide",
        )
        self.assertIn('name: "table-total-rule"', build_table_slide)
        self.assertIn("color: C.orange", build_table_slide)
        self.assertIn("width: 1.5", build_table_slide)
        self.assertNotIn("setCellRules(table.getCell(5", build_table_slide)

        add_line = function_body(self.build_source, "addLine")
        self.assertIn('geometry: "line"', add_line)
        self.assertIn('fill: "none"', add_line)

        slide_contract = next(
            item
            for item in self.format_contract["slides"]
            if item["slide"] == 3
        )
        self.assertIn("table-total-rule", slide_contract["requiredRoles"])
        total_rule = slide_contract["roleGeometry"]["table-total-rule"]
        self.assertEqual(total_rule["objectTypes"], ["shapes"])
        self.assertEqual(
            total_rule["geometry"],
            {"x": 0.8, "y": 5.592, "w": 8.55, "h": 0.0},
        )
        if "KSIB_GOLDEN_PPTX" in os.environ:
            root = read_xml(self.package, "ppt/slides/slide3.xml")
            rule_shape = next(
                shape
                for shape in root.findall(".//p:sp", NS)
                if shape.find("./p:nvSpPr/p:cNvPr", NS).get("name")
                == "table-total-rule"
            )
            self.assertEqual(
                rule_shape.find("./p:spPr/a:prstGeom", NS).get("prst"),
                "line",
            )
            self.assertEqual(
                rule_shape.find(
                    "./p:spPr/a:ln/a:solidFill/a:srgbClr",
                    NS,
                ).get("val"),
                "FF4906",
            )
            rows = root.findall(".//a:tbl/a:tr", NS)
            for cell in rows[-1].findall("./a:tc", NS):
                self.assertTrue(border_is_none(cell, "T"))

    def test_appendix_table_uses_light_header_and_horizontal_rules(self) -> None:
        root = read_xml(self.package, "ppt/slides/slide6.xml")
        rows = root.findall(".//a:tbl/a:tr", NS)
        self.assertEqual(len(rows), 8)
        for cell in rows[0].findall("./a:tc", NS):
            self.assertEqual(direct_fill(cell), "F5F6F7")
            self.assertTrue(border_is_none(cell, "L"))
            self.assertTrue(border_is_none(cell, "R"))
            self.assertEqual(border_fill(cell, "T"), "FF4906")
        for cell in rows[2].findall("./a:tc", NS):
            self.assertEqual(direct_fill(cell), "FFFFFF")
            self.assertTrue(border_is_none(cell, "L"))
            self.assertTrue(border_is_none(cell, "R"))
            self.assertEqual(border_fill(cell, "B"), "E5E6EB")

    def test_chart_uses_horizontal_direct_label_spotlight(self) -> None:
        chart_part = "ppt/slides/charts/chart1.xml"
        self.assertIn(chart_part, self.package.namelist())
        root = read_xml(self.package, chart_part)
        self.assertEqual(root.find(".//c:barDir", NS).get("val"), "bar")
        self.assertIsNone(root.find(".//c:legend", NS))
        self.assertIsNone(root.find(".//c:majorGridlines", NS))
        labels = root.findall(".//c:ser/c:dLbls/c:dLbl", NS)
        self.assertEqual(len(labels), 4)
        spotlight = next(
            label
            for label in labels
            if label.find("./c:idx", NS).get("val") == "3"
        )
        spotlight_color = spotlight.find(".//a:srgbClr", NS)
        self.assertIsNotNone(spotlight_color)
        self.assertEqual(spotlight_color.get("val"), "FF4906")


if __name__ == "__main__":
    unittest.main()
