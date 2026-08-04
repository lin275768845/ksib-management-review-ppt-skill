#!/usr/bin/env python3
"""Regression tests for final-PPTX color extraction."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from extract_pptx_theme_colors import extract_inventory


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def rels(*relationships: tuple[str, str, str]) -> str:
    body = "".join(f'<Relationship Id="{rid}" Type="{kind}" Target="{target}"/>' for rid, kind, target in relationships)
    return f'<Relationships xmlns="{PR}">{body}</Relationships>'


def write_fixture(path: Path) -> None:
    presentation = f'''<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'''
    shape_named = f'''
      <p:sp><p:nvSpPr><p:cNvPr id="2" name="focus-box"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:solidFill><a:schemeClr val="accent1"><a:tint val="50000"/></a:schemeClr></a:solidFill></p:spPr>
      </p:sp>'''
    shape_unnamed = f'''
      <p:sp><p:nvSpPr><p:cNvPr id="3" name=""/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:ln><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:ln></p:spPr>
      </p:sp>'''
    shape_implicit_text = f'''
      <p:sp><p:nvSpPr><p:cNvPr id="5" name="implicit-text"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Inherited color</a:t></a:r></a:p></p:txBody>
      </p:sp>'''
    chart_frame = f'''
      <p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="4" name="chart-main"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
        <a:graphic><a:graphicData><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" r:id="rIdChart"/></a:graphicData></a:graphic>
      </p:graphicFrame>'''
    slide = f'''<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>{shape_named}{shape_unnamed}{shape_implicit_text}{chart_frame}</p:spTree></p:cSld></p:sld>'''
    chart = f'''<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="{A}"><c:chart><c:plotArea><c:ser><c:spPr><a:solidFill><a:srgbClr val="006B8F"/></a:solidFill></c:spPr></c:ser><c:ser/></c:plotArea></c:chart></c:chartSpace>'''
    layout = f'''<p:sldLayout xmlns:p="{P}"><p:cSld><p:spTree/></p:cSld><p:clrMapOvr><p:masterClrMapping/></p:clrMapOvr></p:sldLayout>'''
    master = f'''<p:sldMaster xmlns:p="{P}" xmlns:a="{A}" preserve="1"><p:cSld><p:spTree/></p:cSld><p:clrMap accent1="accent1" bg1="lt1" bg2="lt2" tx1="dk1" tx2="dk2"/></p:sldMaster>'''
    theme = f'''<a:theme xmlns:a="{A}" name="Test"><a:themeElements><a:clrScheme name="Test"><a:dk1><a:srgbClr val="000000"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F2329"/></a:dk2><a:lt2><a:srgbClr val="FAFAFA"/></a:lt2><a:accent1><a:srgbClr val="FF4906"/></a:accent1></a:clrScheme></a:themeElements></a:theme>'''
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("ppt/presentation.xml", presentation)
        package.writestr("ppt/_rels/presentation.xml.rels", rels(("rId1", f"{R}/slide", "slides/slide1.xml")))
        package.writestr("ppt/slides/slide1.xml", slide)
        package.writestr("ppt/slides/_rels/slide1.xml.rels", rels(
            ("rIdLayout", f"{R}/slideLayout", "../slideLayouts/slideLayout1.xml"),
            ("rIdChart", f"{R}/chart", "../charts/chart1.xml"),
        ))
        package.writestr("ppt/charts/chart1.xml", chart)
        package.writestr("ppt/slideLayouts/slideLayout1.xml", layout)
        package.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels(("rIdMaster", f"{R}/slideMaster", "../slideMasters/slideMaster1.xml")))
        package.writestr("ppt/slideMasters/slideMaster1.xml", master)
        package.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels(("rIdTheme", f"{R}/theme", "../theme/theme1.xml")))
        package.writestr("ppt/theme/theme1.xml", theme)


class FinalPptxColorExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pptx = Path(self.temp_dir.name) / "fixture.pptx"
        write_fixture(self.pptx)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolves_theme_transform_and_related_chart_color(self) -> None:
        inventory = extract_inventory(self.pptx)
        objects = {item["objectName"]: item for item in inventory["slides"][0]["objects"]}
        focus = objects["focus-box"]
        self.assertTrue(focus["stable"])
        self.assertEqual(focus["colors"][0]["resolvedHex"], "#FFA482")
        chart_colors = objects["chart-main"]["colors"]
        self.assertTrue(any(color["resolvedHex"] == "#006B8F" and color["sourceRole"] == "chart[1]" for color in chart_colors))
        self.assertEqual(inventory["summary"]["unresolvedVisibleBindingCount"], 2)

    def test_blocks_implicit_text_and_automatic_chart_series_colors(self) -> None:
        inventory = extract_inventory(self.pptx)
        unresolved = [
            color
            for obj in inventory["slides"][0]["objects"]
            for color in obj["colors"]
            if color["resolutionStatus"] == "unresolved"
        ]
        self.assertEqual({item["sourceValue"] for item in unresolved}, {"inherited-text-color", "automatic-chart-theme-color"})

    def test_marks_colored_objects_without_unique_names_unstable(self) -> None:
        inventory = extract_inventory(self.pptx)
        unnamed = next(item for item in inventory["slides"][0]["objects"] if item["objectName"] is None)
        self.assertFalse(unnamed["stable"])
        self.assertEqual(unnamed["colors"][0]["resolvedHex"], "#1F2329")
        self.assertEqual(inventory["summary"]["unstableColoredObjectCount"], 1)

    def test_inventory_is_deterministic_and_bound_to_archive(self) -> None:
        first = extract_inventory(self.pptx)
        second = extract_inventory(self.pptx)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(len(first["pptx"]["sha256"]), 64)
        refs = [color["bindingRef"] for obj in first["slides"][0]["objects"] for color in obj["colors"]]
        self.assertEqual(len(refs), len(set(refs)))

    def test_golden_deck_has_only_resolved_stable_contract_colors(self) -> None:
        skill_root = Path(__file__).resolve().parent.parent
        golden = skill_root / "benchmarks/format-golden-deck/output/KSIB_MBB_FORMAT_GOLDEN_DECK_V1.pptx"
        contract = json.loads((skill_root / "references/theme-color-contract.json").read_text(encoding="utf-8"))
        inventory = extract_inventory(golden)
        actual = {
            color["resolvedHex"]
            for slide in inventory["slides"]
            for obj in slide["objects"]
            for color in obj["colors"]
            if color["visible"]
        }
        self.assertEqual(inventory["summary"]["unresolvedVisibleBindingCount"], 0)
        self.assertEqual(inventory["summary"]["unstableColoredObjectCount"], 0)
        self.assertTrue(actual.issubset(set(contract["palette"].values())), sorted(actual - set(contract["palette"].values())))


if __name__ == "__main__":
    unittest.main()
