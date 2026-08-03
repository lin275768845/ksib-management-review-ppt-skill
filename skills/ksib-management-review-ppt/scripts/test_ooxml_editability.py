#!/usr/bin/env python3
"""Regression tests for native PowerPoint editability normalization."""

from __future__ import annotations

import hashlib
import tempfile
import sys
import unittest
import zipfile
from pathlib import Path

from lxml import etree

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ooxml_qa import audit
from ooxml_sanitize import (
    KSIB_THEME_COLORS,
    KSIB_THEME_FONT_NAME,
    KSIB_THEME_NAME,
    KSIB_PRIMARY_TYPEFACE,
    _rewrite_package,
    normalize_ksib_theme,
    normalize_slide_editability,
)
from pptx_semantic_fingerprint import (
    compare_fingerprints,
    create_fingerprint,
    extract_text_bold_bindings,
)


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def write_semantic_fixture(
    target: Path,
    slide: bytes,
    *,
    slide_relationships: bytes | None = None,
    extra_parts: dict[str, bytes] | None = None,
) -> None:
    presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="{R}">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
    presentation_relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL}">
  <Relationship Id="rId1" Type="{R}/slide" Target="slides/slide1.xml"/>
</Relationships>""".encode()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr(
            "ppt/_rels/presentation.xml.rels",
            presentation_relationships,
        )
        archive.writestr("ppt/slides/slide1.xml", slide)
        if slide_relationships is not None:
            archive.writestr(
                "ppt/slides/_rels/slide1.xml.rels",
                slide_relationships,
            )
        for part_name, payload in (extra_parts or {}).items():
            archive.writestr(part_name, payload)


class EditabilityNormalizationTest(unittest.TestCase):
    def test_semantic_fingerprint_equates_missing_clr_map_override_with_master_mapping(self) -> None:
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}"><p:cSld><p:spTree/></p:cSld></p:sld>""".encode()
        slide_relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL}">
  <Relationship Id="rIdLayout" Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>""".encode()
        layout_relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL}">
  <Relationship Id="rIdMaster" Type="{R}/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>""".encode()
        master_relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL}">
  <Relationship Id="rIdTheme" Type="{R}/theme" Target="../theme/theme1.xml"/>
</Relationships>""".encode()
        master = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sldMaster xmlns:p="{P}">
  <p:cSld/><p:clrMap accent1="accent1" tx1="dk1" bg1="lt1"/>
</p:sldMaster>""".encode()
        theme = f"""<?xml version="1.0" encoding="UTF-8"?>
<a:theme xmlns:a="{A}" name="KSIB">
  <a:themeElements>
    <a:clrScheme name="KSIB"><a:dk1><a:srgbClr val="1F2329"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:accent1><a:srgbClr val="FF4906"/></a:accent1></a:clrScheme>
    <a:fontScheme name="KSIB"><a:majorFont><a:latin typeface="PingFang SC"/></a:majorFont><a:minorFont><a:latin typeface="PingFang SC"/></a:minorFont></a:fontScheme>
  </a:themeElements>
</a:theme>""".encode()

        def layout(include_mapping: bool) -> bytes:
            override = (
                f'<p:clrMapOvr><a:masterClrMapping xmlns:a="{A}"/></p:clrMapOvr>'
                if include_mapping
                else ""
            )
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sldLayout xmlns:p="{P}"><p:cSld/>{override}</p:sldLayout>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline_path = root / "missing-override.pptx"
            candidate_path = root / "master-mapping.pptx"
            common_parts = {
                "ppt/slideLayouts/_rels/slideLayout1.xml.rels": layout_relationships,
                "ppt/slideMasters/slideMaster1.xml": master,
                "ppt/slideMasters/_rels/slideMaster1.xml.rels": master_relationships,
                "ppt/theme/theme1.xml": theme,
            }
            for target, include_mapping in (
                (baseline_path, False),
                (candidate_path, True),
            ):
                write_semantic_fixture(
                    target,
                    slide,
                    slide_relationships=slide_relationships,
                    extra_parts={
                        **common_parts,
                        "ppt/slideLayouts/slideLayout1.xml": layout(
                            include_mapping
                        ),
                    },
                )
            baseline = create_fingerprint(baseline_path)
            candidate = create_fingerprint(candidate_path)
            report = compare_fingerprints(
                baseline,
                candidate,
                font_policy="preserve",
            )

        self.assertTrue(report["passed"])
        self.assertIsNone(
            baseline["slides"][0]["colorSemantics"]["inherited"][
                "layoutColorMapOverride"
            ]
        )
        self.assertIsNone(
            candidate["slides"][0]["colorSemantics"]["inherited"][
                "layoutColorMapOverride"
            ]
        )

    def test_semantic_fingerprint_deduplicates_themes_but_blocks_office_font_drift(self) -> None:
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}"><p:cSld><p:spTree/></p:cSld></p:sld>""".encode()
        slide_relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL}">
  <Relationship Id="rIdLayout" Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
</Relationships>""".encode()
        active_theme_parts = {
            "ppt/slideLayouts/slideLayout1.xml": (
                f'<p:sldLayout xmlns:p="{P}"><p:cSld/></p:sldLayout>'
            ).encode(),
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels": (
                f'<Relationships xmlns="{PKG_REL}"><Relationship Id="rIdMaster" Type="{R}/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>'
            ).encode(),
            "ppt/slideMasters/slideMaster1.xml": (
                f'<p:sldMaster xmlns:p="{P}"><p:cSld/><p:clrMap accent1="accent1" tx1="dk1" bg1="lt1"/></p:sldMaster>'
            ).encode(),
            "ppt/slideMasters/_rels/slideMaster1.xml.rels": (
                f'<Relationships xmlns="{PKG_REL}"><Relationship Id="rIdTheme" Type="{R}/theme" Target="../theme/theme1.xml"/></Relationships>'
            ).encode(),
        }

        def theme(typeface: str, scheme_name: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<a:theme xmlns:a="{A}" name="{scheme_name}">
  <a:themeElements>
    <a:clrScheme name="KSIB Colors">
      <a:dk1><a:srgbClr val="1F2329"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:accent1><a:srgbClr val="FF4906"/></a:accent1>
    </a:clrScheme>
    <a:fontScheme name="{scheme_name}">
      <a:majorFont><a:latin typeface="{typeface}"/><a:ea typeface="{typeface}"/><a:cs typeface="{typeface}"/></a:majorFont>
      <a:minorFont><a:latin typeface="{typeface}"/><a:ea typeface="{typeface}"/><a:cs typeface="{typeface}"/></a:minorFont>
    </a:fontScheme>
  </a:themeElements>
</a:theme>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline_path = root / "pingfang.pptx"
            duplicate_path = root / "pingfang-duplicate.pptx"
            office_path = root / "office-duplicate.pptx"
            pingfang = theme("PingFang SC", "KSIB Chinese")
            office = theme("Calibri", "Office")
            write_semantic_fixture(
                baseline_path,
                slide,
                slide_relationships=slide_relationships,
                extra_parts={
                    **active_theme_parts,
                    "ppt/theme/theme1.xml": pingfang,
                },
            )
            write_semantic_fixture(
                duplicate_path,
                slide,
                slide_relationships=slide_relationships,
                extra_parts={
                    **active_theme_parts,
                    "ppt/theme/theme1.xml": pingfang,
                    "ppt/theme/theme2.xml": pingfang,
                },
            )
            write_semantic_fixture(
                office_path,
                slide,
                slide_relationships=slide_relationships,
                extra_parts={
                    **active_theme_parts,
                    "ppt/theme/theme1.xml": office,
                    "ppt/theme/theme2.xml": office,
                },
            )
            baseline = create_fingerprint(baseline_path)
            duplicate = create_fingerprint(duplicate_path)
            office_candidate = create_fingerprint(office_path)
            duplicate_report = compare_fingerprints(
                baseline,
                duplicate,
                font_policy="preserve",
            )
            office_report = compare_fingerprints(
                baseline,
                office_candidate,
                font_policy="preserve",
            )

        self.assertEqual(len(duplicate["themeColorSemantics"]), 1)
        self.assertEqual(len(duplicate["themeFontSemantics"]), 1)
        self.assertTrue(duplicate_report["passed"])
        self.assertFalse(office_report["passed"])
        office_rules = {item["rule"] for item in office_report["errors"]}
        self.assertIn("theme_font_semantics_drift", office_rules)
        self.assertNotIn("theme_color_semantics_drift", office_rules)

    def test_semantic_fingerprint_matches_chart_by_type_ordinal_and_keeps_formula_strict(self) -> None:
        def slide(relationship_id: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:c="{C}" xmlns:r="{R}">
  <p:cSld><p:spTree><p:graphicFrame>
    <p:nvGraphicFramePr><p:cNvPr id="2" name="chart-main"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
    <a:xfrm/><a:graphic><a:graphicData uri="{C}"><c:chart r:id="{relationship_id}"/></a:graphicData></a:graphic>
  </p:graphicFrame></p:spTree></p:cSld>
</p:sld>""".encode()

        def slide_relationships(
            relationship_id: str,
            target: str,
        ) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL}">
  <Relationship Id="{relationship_id}" Type="{R}/chart" Target="{target}"/>
</Relationships>""".encode()

        def chart(value_formula: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<c:chartSpace xmlns:c="{C}">
  <c:chart><c:plotArea><c:barChart><c:ser>
    <c:idx val="0"/><c:order val="0"/>
    <c:tx><c:strRef><c:f>Sheet1!$B$1</c:f><c:strCache><c:pt idx="0"><c:v>Series A</c:v></c:pt></c:strCache></c:strRef></c:tx>
    <c:cat><c:strRef><c:f>Sheet1!$A$2:$A$3</c:f><c:strCache><c:pt idx="0"><c:v>Alpha</c:v></c:pt><c:pt idx="1"><c:v>Beta</c:v></c:pt></c:strCache></c:strRef></c:cat>
    <c:val><c:numRef><c:f>{value_formula}</c:f><c:numCache><c:pt idx="0"><c:v>10</c:v></c:pt><c:pt idx="1"><c:v>20</c:v></c:pt></c:numCache></c:numRef></c:val>
  </c:ser></c:barChart></c:plotArea></c:chart>
</c:chartSpace>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline_path = root / "chart1.pptx"
            relocated_path = root / "chart-relocated.pptx"
            formula_drift_path = root / "chart-formula-drift.pptx"
            write_semantic_fixture(
                baseline_path,
                slide("rIdChart1"),
                slide_relationships=slide_relationships(
                    "rIdChart1",
                    "../charts/chart1.xml",
                ),
                extra_parts={
                    "ppt/charts/chart1.xml": chart(
                        "Sheet1!$B$2:$B$3"
                    ),
                },
            )
            write_semantic_fixture(
                relocated_path,
                slide("rId99"),
                slide_relationships=slide_relationships(
                    "rId99",
                    "../charts/renamed99.xml",
                ),
                extra_parts={
                    "ppt/charts/renamed99.xml": chart(
                        "Sheet1!$B$2:$B$3"
                    ),
                },
            )
            write_semantic_fixture(
                formula_drift_path,
                slide("rId99"),
                slide_relationships=slide_relationships(
                    "rId99",
                    "../charts/renamed99.xml",
                ),
                extra_parts={
                    "ppt/charts/renamed99.xml": chart(
                        "Sheet1!$C$2:$C$3"
                    ),
                },
            )
            baseline = create_fingerprint(baseline_path)
            relocated = create_fingerprint(relocated_path)
            formula_drift = create_fingerprint(formula_drift_path)
            relocated_report = compare_fingerprints(
                baseline,
                relocated,
                font_policy="preserve",
            )
            formula_report = compare_fingerprints(
                baseline,
                formula_drift,
                font_policy="preserve",
            )

        self.assertEqual(
            baseline["slides"][0]["objectContentSemantics"],
            relocated["slides"][0]["objectContentSemantics"],
        )
        self.assertEqual(
            baseline["slides"][0]["objectContentSemantics"][0][
                "relatedParts"
            ],
            ["chart[1]"],
        )
        self.assertTrue(relocated_report["passed"])
        self.assertFalse(formula_report["passed"])
        formula_rules = {item["rule"] for item in formula_report["errors"]}
        self.assertIn("slide_object_content_binding_drift", formula_rules)

    def test_semantic_fingerprint_ignores_extensions_empty_text_defaults_and_line_defaults(self) -> None:
        def slide(powerpoint_defaults: bool) -> bytes:
            empty_paragraph = (
                f"""<a:p><a:pPr><a:defRPr sz="4000"><a:latin typeface="Calibri"/><a:solidFill><a:srgbClr val="00FF00"/></a:solidFill></a:defRPr></a:pPr><a:endParaRPr sz="4000"/></a:p>"""
                if powerpoint_defaults
                else ""
            )
            line_attributes = (
                ' cap="flat" cmpd="sng" algn="ctr"'
                if powerpoint_defaults
                else ""
            )
            line_defaults = (
                """<a:prstDash val="solid"/><a:round/><a:headEnd type="none" w="med" len="med"/><a:tailEnd type="none" w="med" len="med"/>"""
                if powerpoint_defaults
                else ""
            )
            extension = (
                f"""<a:extLst><a:ext uri="noise"><x:payload xmlns:x="urn:test"><a:solidFill><a:srgbClr val="00FF00"/></a:solidFill><a:p><a:r><a:rPr sz="4000"/><a:t>extension noise</a:t></a:r></a:p></x:payload></a:ext></a:extLst>"""
                if powerpoint_defaults
                else ""
            )
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="2" name="default-noise"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr><a:ln w="12700"{line_attributes}><a:solidFill><a:srgbClr val="AEB2BA"/></a:solidFill>{line_defaults}</a:ln>{extension}</p:spPr>
    <p:txBody><a:bodyPr/><a:lstStyle/>{empty_paragraph}<a:p>
      <a:r><a:rPr sz="1400" b="0"><a:latin typeface="PingFang SC"/><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:rPr><a:t>可见文字</a:t></a:r>
    </a:p></p:txBody>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline_path = root / "minimal.pptx"
            candidate_path = root / "powerpoint-defaults.pptx"
            write_semantic_fixture(baseline_path, slide(False))
            write_semantic_fixture(candidate_path, slide(True))
            report = compare_fingerprints(
                create_fingerprint(baseline_path),
                create_fingerprint(candidate_path),
                font_policy="preserve",
            )

        self.assertTrue(report["passed"])

    def test_semantic_fingerprint_canonicalizes_shared_table_edges_but_detects_missing_orange(self) -> None:
        no_line = "<a:noFill/>"
        orange = (
            '<a:solidFill><a:srgbClr val="FF4906"/></a:solidFill>'
        )

        def line(side: str, payload: str) -> str:
            width = ' w="14288"' if payload == orange else ""
            return f"<a:{side}{width}>{payload}</a:{side}>"

        def table_slide(upper_bottom: str, lower_top: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:graphicFrame>
    <p:nvGraphicFramePr><p:cNvPr id="2" name="table-main"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
    <a:xfrm/><a:graphic><a:graphicData uri="table"><a:tbl>
      <a:tblGrid><a:gridCol w="2000000"/></a:tblGrid>
      <a:tr h="400000"><a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>上行</a:t></a:r></a:p></a:txBody><a:tcPr>{line("lnB", upper_bottom)}</a:tcPr></a:tc></a:tr>
      <a:tr h="400000"><a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>下行</a:t></a:r></a:p></a:txBody><a:tcPr>{line("lnT", lower_top)}</a:tcPr></a:tc></a:tr>
    </a:tbl></a:graphicData></a:graphic>
  </p:graphicFrame></p:spTree></p:cSld>
</p:sld>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline_path = root / "upper-owned.pptx"
            transferred_path = root / "lower-owned.pptx"
            lost_path = root / "lost.pptx"
            write_semantic_fixture(
                baseline_path,
                table_slide(orange, no_line),
            )
            write_semantic_fixture(
                transferred_path,
                table_slide(no_line, orange),
            )
            write_semantic_fixture(
                lost_path,
                table_slide(no_line, no_line),
            )
            baseline = create_fingerprint(baseline_path)
            transferred_report = compare_fingerprints(
                baseline,
                create_fingerprint(transferred_path),
                font_policy="preserve",
            )
            lost_report = compare_fingerprints(
                baseline,
                create_fingerprint(lost_path),
                font_policy="preserve",
            )

        self.assertTrue(transferred_report["passed"])
        self.assertFalse(lost_report["passed"])
        lost_rules = {item["rule"] for item in lost_report["errors"]}
        self.assertIn("slide_object_graphic_style_binding_drift", lost_rules)
        self.assertIn("slide_object_color_binding_drift", lost_rules)

    def test_semantic_fingerprint_merges_only_adjacent_runs_with_same_effective_style(self) -> None:
        def run(
            text: str,
            *,
            typeface: str = "PingFang SC",
            size: str = "1400",
            bold: str = "1",
            color: str = "1F2329",
        ) -> str:
            return f"""<a:r><a:rPr sz="{size}" b="{bold}"><a:latin typeface="{typeface}"/><a:ea typeface="{typeface}"/><a:cs typeface="{typeface}"/><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr><a:t>{text}</a:t></a:r>"""

        def slide(runs: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="2" name="run-body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>{runs}</a:p></p:txBody>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()

        baseline_runs = (
            run("资源需求｜")
            + run("2")
            + run("个角色", bold="0")
        )
        merged_runs = run("资源需求｜2") + run("个角色", bold="0")
        mutations = {
            "font": (
                run("资源需求｜")
                + run("2", typeface="Calibri")
                + run("个角色", bold="0"),
                "slide_font_semantics_drift",
            ),
            "size": (
                run("资源需求｜")
                + run("2", size="1600")
                + run("个角色", bold="0"),
                "slide_font_semantics_drift",
            ),
            "bold": (
                run("资源需求｜")
                + run("2", bold="0")
                + run("个角色", bold="0"),
                "slide_object_text_style_binding_drift",
            ),
            "color": (
                run("资源需求｜")
                + run("2", color="FF4906")
                + run("个角色", bold="0"),
                "slide_object_color_binding_drift",
            ),
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            baseline_path = root / "split.pptx"
            merged_path = root / "merged.pptx"
            write_semantic_fixture(baseline_path, slide(baseline_runs))
            write_semantic_fixture(merged_path, slide(merged_runs))
            baseline = create_fingerprint(baseline_path)
            merged_report = compare_fingerprints(
                baseline,
                create_fingerprint(merged_path),
                font_policy="preserve",
            )
            mutation_reports: dict[str, tuple[dict[str, object], str]] = {}
            for name, (payload, expected_rule) in mutations.items():
                candidate_path = root / f"{name}.pptx"
                write_semantic_fixture(candidate_path, slide(payload))
                mutation_reports[name] = (
                    compare_fingerprints(
                        baseline,
                        create_fingerprint(candidate_path),
                        font_policy="preserve",
                    ),
                    expected_rule,
                )

        self.assertTrue(merged_report["passed"])
        for name, (report, expected_rule) in mutation_reports.items():
            with self.subTest(property=name):
                self.assertFalse(report["passed"])
                rules = {item["rule"] for item in report["errors"]}
                self.assertIn(expected_rule, rules)
                if name in {"bold", "color"}:
                    self.assertNotIn("slide_font_semantics_drift", rules)
                    self.assertNotIn(
                        "slide_object_font_binding_drift",
                        rules,
                    )

    def test_semantic_fingerprint_uses_unique_object_name_before_internal_id(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""

        def slide(object_id: int) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="{object_id}" name="action-title"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
      <a:r><a:rPr b="1"><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:rPr><a:t>结论保持不变</a:t></a:r>
    </a:p></p:txBody>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, object_id in ((baseline_path, 2), (candidate_path, 27)):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
                    archive.writestr("ppt/slides/slide1.xml", slide(object_id))
            baseline = create_fingerprint(baseline_path)
            candidate = create_fingerprint(candidate_path)
            report = compare_fingerprints(
                baseline,
                candidate,
                font_policy="preserve",
            )

        self.assertTrue(report["passed"])
        self.assertEqual(
            baseline["slides"][0]["objectContentSemantics"][0]["objectKey"],
            "name:action-title",
        )

    def test_semantic_fingerprint_binds_text_and_color_to_native_objects(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""

        def shape(object_id: int, text: str, color: str) -> str:
            return f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="{object_id}" name="shape-{object_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
    <a:r><a:rPr sz="1200"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr><a:t>{text}</a:t></a:r>
  </a:p></p:txBody>
</p:sp>"""

        def slide(first: tuple[str, str], second: tuple[str, str]) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree>
    {shape(2, first[0], first[1])}
    {shape(3, second[0], second[1])}
  </p:spTree></p:cSld>
</p:sld>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, slide_payload in (
                (baseline_path, slide(("结论A 42.0%", "FF4906"), ("结论B 28.0%", "1F2329"))),
                (candidate_path, slide(("结论B 28.0%", "1F2329"), ("结论A 42.0%", "FF4906"))),
            ):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
                    archive.writestr("ppt/slides/slide1.xml", slide_payload)
            baseline = create_fingerprint(baseline_path)
            candidate = create_fingerprint(candidate_path)
            report = compare_fingerprints(
                baseline,
                candidate,
                font_policy="preserve",
            )
        rules = {item["rule"] for item in report["errors"]}
        self.assertIn("slide_object_content_binding_drift", rules)
        self.assertIn("slide_object_color_binding_drift", rules)
        validator_hash = hashlib.sha256(
            Path(create_fingerprint.__code__.co_filename).read_bytes()
        ).hexdigest()
        self.assertEqual(baseline["validatorSha256"], validator_hash)
        self.assertEqual(report["validatorSha256"], validator_hash)

    def test_semantic_fingerprint_binds_text_to_color_within_one_object(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""

        def run(text: str, color: str) -> str:
            return f"""<a:r>
  <a:rPr><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:rPr>
  <a:t>{text}</a:t>
</a:r>"""

        def slide(first_color: str, second_color: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="2" name="body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
      {run("结论A", first_color)}
      {run("结论B", second_color)}
    </a:p></p:txBody>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, slide_payload in (
                (baseline_path, slide("FF4906", "1F2329")),
                (candidate_path, slide("1F2329", "FF4906")),
            ):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
                    archive.writestr("ppt/slides/slide1.xml", slide_payload)
            baseline = create_fingerprint(baseline_path)
            candidate = create_fingerprint(candidate_path)
            report = compare_fingerprints(baseline, candidate)
            restyled = compare_fingerprints(
                baseline,
                candidate,
                style_policy="allow",
            )

        self.assertEqual(
            baseline["slides"][0]["textInventory"],
            candidate["slides"][0]["textInventory"],
        )
        self.assertEqual(
            baseline["slides"][0]["colorSemantics"],
            candidate["slides"][0]["colorSemantics"],
        )
        self.assertNotEqual(
            baseline["slides"][0]["objectColorSemantics"],
            candidate["slides"][0]["objectColorSemantics"],
        )
        self.assertFalse(report["passed"])
        rules = {item["rule"] for item in report["errors"]}
        self.assertIn("slide_object_color_binding_drift", rules)
        self.assertTrue(restyled["passed"])
        self.assertEqual(restyled["stylePolicy"], "allow")

    def test_semantic_fingerprint_binds_text_to_effective_bold(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""

        def slide(first_bold: str, second_bold: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="2" name="body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
      <a:r><a:rPr b="{first_bold}"/><a:t>结论A</a:t></a:r>
      <a:r><a:rPr b="{second_bold}"/><a:t>结论B</a:t></a:r>
    </a:p></p:txBody>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, slide_payload in (
                (baseline_path, slide("1", "0")),
                (candidate_path, slide("0", "1")),
            ):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
                    archive.writestr("ppt/slides/slide1.xml", slide_payload)
            baseline = create_fingerprint(baseline_path)
            candidate = create_fingerprint(candidate_path)
            report = compare_fingerprints(baseline, candidate)
            restyled = compare_fingerprints(
                baseline,
                candidate,
                style_policy="allow",
            )

        self.assertFalse(report["passed"])
        rules = {item["rule"] for item in report["errors"]}
        self.assertIn("slide_object_text_style_binding_drift", rules)
        self.assertTrue(restyled["passed"])

    def test_semantic_fingerprint_binds_border_width_and_dash(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""

        def slide(width: str, dash: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="2" name="bordered-shape"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr>
      <a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>
      <a:ln w="{width}">
        <a:solidFill><a:srgbClr val="AEB2BA"/></a:solidFill>
        <a:prstDash val="{dash}"/>
      </a:ln>
    </p:spPr>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, slide_payload in (
                (baseline_path, slide("12700", "solid")),
                (candidate_path, slide("25400", "dash")),
            ):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
                    archive.writestr("ppt/slides/slide1.xml", slide_payload)
            baseline = create_fingerprint(baseline_path)
            candidate = create_fingerprint(candidate_path)
            report = compare_fingerprints(baseline, candidate)
            restyled = compare_fingerprints(
                baseline,
                candidate,
                style_policy="allow",
            )

        self.assertEqual(
            baseline["slides"][0]["colorSemantics"],
            candidate["slides"][0]["colorSemantics"],
        )
        self.assertNotEqual(
            baseline["slides"][0]["objectGraphicStyleSemantics"],
            candidate["slides"][0]["objectGraphicStyleSemantics"],
        )
        self.assertFalse(report["passed"])
        rules = {item["rule"] for item in report["errors"]}
        self.assertIn("slide_object_graphic_style_binding_drift", rules)
        self.assertTrue(restyled["passed"])

    def test_semantic_fingerprint_binds_chart_data_to_series_and_points(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        presentation_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:c="{C}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree><p:graphicFrame>
    <p:nvGraphicFramePr>
      <p:cNvPr id="2" name="chart"/>
      <p:cNvGraphicFramePr/>
      <p:nvPr/>
    </p:nvGraphicFramePr>
    <a:xfrm/>
    <a:graphic><a:graphicData uri="{C}">
      <c:chart r:id="rIdChart"/>
    </a:graphicData></a:graphic>
  </p:graphicFrame></p:spTree></p:cSld>
</p:sld>""".encode()
        slide_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
</Relationships>"""

        def points(values: list[str]) -> str:
            return "".join(
                f'<c:pt idx="{index}"><c:v>{value}</c:v></c:pt>'
                for index, value in enumerate(values)
            )

        def series(
            index: int,
            name: str,
            labels: list[str],
            values: list[str],
        ) -> str:
            return f"""<c:ser>
  <c:idx val="{index}"/><c:order val="{index}"/>
  <c:tx><c:strRef><c:strCache>{points([name])}</c:strCache></c:strRef></c:tx>
  <c:cat><c:strRef><c:strCache>{points(labels)}</c:strCache></c:strRef></c:cat>
  <c:val><c:numRef><c:numCache>{points(values)}</c:numCache></c:numRef></c:val>
</c:ser>"""

        def chart(series_values: list[tuple[str, list[str], list[str]]]) -> bytes:
            payload = "".join(
                series(index, name, labels, values)
                for index, (name, labels, values) in enumerate(series_values)
            )
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<c:chartSpace xmlns:c="{C}">
  <c:chart><c:plotArea><c:barChart>{payload}</c:barChart></c:plotArea></c:chart>
</c:chartSpace>""".encode()

        baseline_series = [
            ("Series A", ["Alpha", "Beta"], ["10", "20"]),
            ("Series B", ["Alpha", "Beta"], ["30", "40"]),
        ]
        candidates = {
            "point_value_swap": [
                ("Series A", ["Alpha", "Beta"], ["20", "10"]),
                ("Series B", ["Alpha", "Beta"], ["30", "40"]),
            ],
            "point_label_swap": [
                ("Series A", ["Beta", "Alpha"], ["10", "20"]),
                ("Series B", ["Alpha", "Beta"], ["30", "40"]),
            ],
            "series_label_swap": [
                ("Series B", ["Alpha", "Beta"], ["10", "20"]),
                ("Series A", ["Alpha", "Beta"], ["30", "40"]),
            ],
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            def write_fixture(target: Path, chart_payload: bytes) -> None:
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr(
                        "ppt/_rels/presentation.xml.rels",
                        presentation_relationships,
                    )
                    archive.writestr("ppt/slides/slide1.xml", slide)
                    archive.writestr(
                        "ppt/slides/_rels/slide1.xml.rels",
                        slide_relationships,
                    )
                    archive.writestr("ppt/charts/chart1.xml", chart_payload)

            baseline_path = root / "baseline.pptx"
            write_fixture(baseline_path, chart(baseline_series))
            baseline = create_fingerprint(baseline_path)
            for case_name, candidate_series in candidates.items():
                with self.subTest(case=case_name):
                    candidate_path = root / f"{case_name}.pptx"
                    write_fixture(candidate_path, chart(candidate_series))
                    candidate = create_fingerprint(candidate_path)
                    self.assertEqual(
                        baseline["slides"][0]["relatedDataValues"],
                        candidate["slides"][0]["relatedDataValues"],
                    )
                    self.assertNotEqual(
                        baseline["slides"][0]["objectContentSemantics"],
                        candidate["slides"][0]["objectContentSemantics"],
                    )
                    report = compare_fingerprints(baseline, candidate)
                    self.assertFalse(report["passed"])
                    rules = {item["rule"] for item in report["errors"]}
                    self.assertIn("slide_object_content_binding_drift", rules)

    def test_semantic_fingerprint_binds_related_chart_text_color_and_bold(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        presentation_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:c="{C}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree><p:graphicFrame>
    <p:nvGraphicFramePr><p:cNvPr id="2" name="chart"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
    <a:xfrm/><a:graphic><a:graphicData uri="{C}"><c:chart r:id="rIdChart"/></a:graphicData></a:graphic>
  </p:graphicFrame></p:spTree></p:cSld>
</p:sld>""".encode()
        slide_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdChart" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
</Relationships>"""

        def chart(
            first_color: str,
            first_bold: str,
            second_color: str,
            second_bold: str,
        ) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<c:chartSpace xmlns:c="{C}" xmlns:a="{A}">
  <c:chart><c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p>
    <a:r><a:rPr b="{first_bold}"><a:solidFill><a:srgbClr val="{first_color}"/></a:solidFill></a:rPr><a:t>结论A</a:t></a:r>
    <a:r><a:rPr b="{second_bold}"><a:solidFill><a:srgbClr val="{second_color}"/></a:solidFill></a:rPr><a:t>结论B</a:t></a:r>
  </a:p></c:rich></c:tx></c:title></c:chart>
</c:chartSpace>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, chart_payload in (
                (baseline_path, chart("FF4906", "1", "1F2329", "0")),
                (candidate_path, chart("1F2329", "0", "FF4906", "1")),
            ):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr(
                        "ppt/_rels/presentation.xml.rels",
                        presentation_relationships,
                    )
                    archive.writestr("ppt/slides/slide1.xml", slide)
                    archive.writestr(
                        "ppt/slides/_rels/slide1.xml.rels",
                        slide_relationships,
                    )
                    archive.writestr("ppt/charts/chart1.xml", chart_payload)
            report = compare_fingerprints(
                create_fingerprint(baseline_path),
                create_fingerprint(candidate_path),
            )

        rules = {item["rule"] for item in report["errors"]}
        self.assertIn("slide_object_color_binding_drift", rules)
        self.assertIn("slide_object_text_style_binding_drift", rules)

    def test_semantic_fingerprint_binds_related_diagram_text_color_and_bold(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        presentation_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:dgm="{DGM}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree><p:graphicFrame>
    <p:nvGraphicFramePr><p:cNvPr id="2" name="smartart"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
    <a:xfrm/><a:graphic><a:graphicData uri="{DGM}">
      <dgm:relIds r:dm="rIdData" r:lo="rIdLayout" r:qs="rIdStyle" r:cs="rIdColors"/>
    </a:graphicData></a:graphic>
  </p:graphicFrame></p:spTree></p:cSld>
</p:sld>""".encode()
        slide_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdData" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData" Target="../diagrams/data1.xml"/>
  <Relationship Id="rIdLayout" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramLayout" Target="../diagrams/layout1.xml"/>
  <Relationship Id="rIdStyle" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramQuickStyle" Target="../diagrams/quickStyle1.xml"/>
  <Relationship Id="rIdColors" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramColors" Target="../diagrams/colors1.xml"/>
</Relationships>"""

        def diagram_data(
            first_color: str,
            first_bold: str,
            second_color: str,
            second_bold: str,
        ) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<dgm:dataModel xmlns:dgm="{DGM}" xmlns:a="{A}">
  <dgm:ptLst><dgm:pt modelId="1"><dgm:t><a:bodyPr/><a:lstStyle/><a:p>
    <a:r><a:rPr b="{first_bold}"><a:solidFill><a:srgbClr val="{first_color}"/></a:solidFill></a:rPr><a:t>结论A</a:t></a:r>
    <a:r><a:rPr b="{second_bold}"><a:solidFill><a:srgbClr val="{second_color}"/></a:solidFill></a:rPr><a:t>结论B</a:t></a:r>
  </a:p></dgm:t></dgm:pt></dgm:ptLst>
</dgm:dataModel>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, data_payload in (
                (baseline_path, diagram_data("FF4906", "1", "1F2329", "0")),
                (candidate_path, diagram_data("1F2329", "0", "FF4906", "1")),
            ):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr(
                        "ppt/_rels/presentation.xml.rels",
                        presentation_relationships,
                    )
                    archive.writestr("ppt/slides/slide1.xml", slide)
                    archive.writestr(
                        "ppt/slides/_rels/slide1.xml.rels",
                        slide_relationships,
                    )
                    archive.writestr("ppt/diagrams/data1.xml", data_payload)
                    archive.writestr("ppt/diagrams/layout1.xml", b"<layout/>")
                    archive.writestr("ppt/diagrams/quickStyle1.xml", b"<style/>")
                    archive.writestr("ppt/diagrams/colors1.xml", b"<colors/>")
            report = compare_fingerprints(
                create_fingerprint(baseline_path),
                create_fingerprint(candidate_path),
            )

        rules = {item["rule"] for item in report["errors"]}
        self.assertIn("slide_object_color_binding_drift", rules)
        self.assertIn("slide_object_text_style_binding_drift", rules)

    def test_rewrite_package_normalizes_related_chart_text(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree>
  <p:nvGrpSpPr><p:cNvPr id="1" name="root"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
  <p:grpSpPr/>
</p:spTree></p:cSld></p:sld>""".encode()
        chart = f"""<?xml version="1.0" encoding="UTF-8"?>
<c:chartSpace xmlns:c="{C}" xmlns:a="{A}">
  <c:chart><c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p>
    <a:pPr><a:defRPr b="1"><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:defRPr></a:pPr>
    <a:r><a:rPr><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:rPr><a:t>chart title</a:t></a:r>
  </a:p></c:rich></c:tx></c:title></c:chart>
</c:chartSpace>""".encode()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.pptx"
            rewritten = Path(temporary_directory) / "rewritten.pptx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("ppt/presentation.xml", presentation)
                archive.writestr(
                    "ppt/_rels/presentation.xml.rels",
                    relationships,
                )
                archive.writestr("ppt/slides/slide1.xml", slide)
                archive.writestr("ppt/charts/chart1.xml", chart)
            result = _rewrite_package(
                source,
                rewritten,
                normalize_theme=False,
                preserve_text_color_structure=False,
            )
            with zipfile.ZipFile(rewritten) as archive:
                chart_root = etree.fromstring(
                    archive.read("ppt/charts/chart1.xml")
                )
            before_report = audit(
                str(source),
                theme_policy="preserve",
                font_policy="preserve",
            )
            after_report = audit(
                str(rewritten),
                theme_policy="preserve",
                font_policy="preserve",
            )
        ns = {"a": A, "c": C}
        self.assertEqual(result[5], 1)
        self.assertEqual(result[6], 1)
        self.assertEqual(
            chart_root.xpath(".//a:pPr/a:defRPr/@b", namespaces=ns),
            [],
        )
        self.assertEqual(
            chart_root.xpath(".//a:r/a:rPr/@b", namespaces=ns),
            ["1"],
        )
        self.assertEqual(
            chart_root.xpath(
                ".//a:r/a:rPr/a:solidFill/a:srgbClr/@val",
                namespaces=ns,
            ),
            [],
        )
        before_kinds = {item["kind"] for item in before_report["errors"]}
        after_kinds = {item["kind"] for item in after_report["errors"]}
        self.assertTrue({
            "redundant_run_text_color",
            "paragraph_default_bold_blocks_toggle",
        }.issubset(before_kinds))
        self.assertFalse({
            "redundant_run_text_color",
            "paragraph_default_bold_blocks_toggle",
        } & after_kinds)

    def test_semantic_fingerprint_font_policy_is_explicit(self) -> None:
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""

        def make_slide(typeface: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="2" name="body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
      <a:r><a:rPr sz="1200"><a:latin typeface="{typeface}"/></a:rPr><a:t>同一段文字 42.0%</a:t></a:r>
    </a:p></p:txBody>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()

        def make_theme(typeface: str) -> bytes:
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<a:theme xmlns:a="{A}" name="Client Theme">
  <a:themeElements>
    <a:clrScheme name="Client Colors"><a:dk1><a:srgbClr val="111111"/></a:dk1></a:clrScheme>
    <a:fontScheme name="Client Fonts">
      <a:majorFont><a:latin typeface="{typeface}"/><a:ea typeface="{typeface}"/><a:cs typeface="{typeface}"/></a:majorFont>
      <a:minorFont><a:latin typeface="{typeface}"/><a:ea typeface="{typeface}"/><a:cs typeface="{typeface}"/></a:minorFont>
    </a:fontScheme>
  </a:themeElements>
</a:theme>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            baseline_path = Path(temporary_directory) / "baseline.pptx"
            candidate_path = Path(temporary_directory) / "candidate.pptx"
            for target, typeface in (
                (baseline_path, "PingFang SC"),
                (candidate_path, "Microsoft YaHei"),
            ):
                with zipfile.ZipFile(target, "w") as archive:
                    archive.writestr("ppt/presentation.xml", presentation)
                    archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
                    archive.writestr("ppt/slides/slide1.xml", make_slide(typeface))
                    archive.writestr("ppt/theme/theme1.xml", make_theme(typeface))
            baseline = create_fingerprint(baseline_path)
            candidate = create_fingerprint(candidate_path)
            allowed = compare_fingerprints(
                baseline,
                candidate,
                font_policy="allow",
            )
            preserved = compare_fingerprints(
                baseline,
                candidate,
                font_policy="preserve",
            )
        self.assertTrue(allowed["passed"])
        preserved_rules = {item["rule"] for item in preserved["errors"]}
        self.assertIn("slide_font_semantics_drift", preserved_rules)
        self.assertIn("theme_font_semantics_drift", preserved_rules)

    def test_removes_editability_locks_and_only_redundant_run_color(self) -> None:
        source = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="body"/><p:cNvSpPr><a:spLocks noGrp="1" noMove="1" noTextEdit="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
      <p:spPr/>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:pPr><a:defRPr><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:defRPr></a:pPr>
        <a:r><a:rPr><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:rPr><a:t>normal</a:t></a:r>
        <a:r><a:rPr><a:solidFill><a:srgbClr val="FF4906"/></a:solidFill></a:rPr><a:t>accent</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>""".encode()

        payload, locks_removed, colors_removed, bold_runs_materialized = normalize_slide_editability(
            source, "ppt/slides/slide1.xml"
        )
        root = etree.fromstring(payload)
        ns = {"p": P, "a": A}

        self.assertEqual(locks_removed, 3)
        self.assertEqual(colors_removed, 1)
        self.assertEqual(bold_runs_materialized, 0)
        self.assertFalse(
            root.xpath(".//*[@noGrp or @noMove or @noTextEdit]")
        )
        run_fills = root.xpath(
            ".//a:r/a:rPr/a:solidFill/a:srgbClr/@val", namespaces=ns
        )
        self.assertEqual(run_fills, ["FF4906"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            before_path = Path(temporary_directory) / "locked.pptx"
            after_path = Path(temporary_directory) / "unlocked.pptx"
            with zipfile.ZipFile(before_path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", source)
            with zipfile.ZipFile(after_path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", payload)
            before_report = audit(
                str(before_path),
                theme_policy="preserve",
                font_policy="preserve",
            )
            after_report = audit(
                str(after_path),
                theme_policy="preserve",
                font_policy="preserve",
            )
        self.assertIn(
            "native_editability_locks",
            {item["kind"] for item in before_report["errors"]},
        )
        self.assertNotIn(
            "native_editability_locks",
            {item["kind"] for item in after_report["errors"]},
        )

    def test_materializes_effective_bold_so_powerpoint_toggle_can_cancel_it(self) -> None:
        source = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="bold-body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:pPr><a:defRPr b="1"/></a:pPr>
        <a:r><a:rPr/><a:t>inherits bold</a:t></a:r>
        <a:r><a:rPr b="0"/><a:t>explicit regular</a:t></a:r>
        <a:endParaRPr/>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>""".encode()

        payload, locks_removed, colors_removed, bold_runs_materialized = (
            normalize_slide_editability(source, "ppt/slides/slide1.xml")
        )
        root = etree.fromstring(payload)
        ns = {"p": P, "a": A}

        self.assertEqual(locks_removed, 0)
        self.assertEqual(colors_removed, 0)
        self.assertEqual(bold_runs_materialized, 1)
        self.assertEqual(
            root.xpath(".//a:pPr/a:defRPr/@b", namespaces=ns),
            [],
        )
        self.assertEqual(
            root.xpath(".//a:r/a:rPr/@b", namespaces=ns),
            ["1", "0"],
        )
        self.assertEqual(
            root.xpath(".//a:endParaRPr/@b", namespaces=ns),
            ["1"],
        )
        self.assertEqual(
            extract_text_bold_bindings(etree.fromstring(source)),
            extract_text_bold_bindings(root),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            before_path = Path(temporary_directory) / "before.pptx"
            after_path = Path(temporary_directory) / "after.pptx"
            with zipfile.ZipFile(before_path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", source)
            with zipfile.ZipFile(after_path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", payload)
            before_report = audit(
                str(before_path),
                theme_policy="preserve",
                font_policy="preserve",
            )
            after_report = audit(
                str(after_path),
                theme_policy="preserve",
                font_policy="preserve",
            )

        before_kinds = {item["kind"] for item in before_report["errors"]}
        after_kinds = {item["kind"] for item in after_report["errors"]}
        self.assertIn("paragraph_default_bold_blocks_toggle", before_kinds)
        self.assertNotIn("paragraph_default_bold_blocks_toggle", after_kinds)

    def test_normalizes_table_cell_color_bold_and_graphic_frame_locks(self) -> None:
        source = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree>
    <p:graphicFrame>
      <p:nvGraphicFramePr>
        <p:cNvPr id="2" name="table"/>
        <p:cNvGraphicFramePr><a:graphicFrameLocks noMove="1" noResize="1"/></p:cNvGraphicFramePr>
        <p:nvPr/>
      </p:nvGraphicFramePr>
      <p:xfrm/>
      <a:graphic><a:graphicData uri="table"><a:tbl><a:tr><a:tc>
        <a:txBody><a:bodyPr/><a:lstStyle/><a:p>
          <a:pPr><a:defRPr b="1"><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:defRPr></a:pPr>
          <a:r><a:rPr><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:rPr><a:t>table text</a:t></a:r>
        </a:p></a:txBody>
      </a:tc></a:tr></a:tbl></a:graphicData></a:graphic>
    </p:graphicFrame>
  </p:spTree></p:cSld>
</p:sld>""".encode()

        payload, locks_removed, colors_removed, bold_runs_materialized = (
            normalize_slide_editability(source, "ppt/slides/slide1.xml")
        )
        root = etree.fromstring(payload)
        ns = {"p": P, "a": A}
        self.assertEqual(locks_removed, 2)
        self.assertEqual(colors_removed, 1)
        self.assertEqual(bold_runs_materialized, 1)
        self.assertFalse(root.xpath(".//*[@noMove or @noResize]"))
        self.assertEqual(
            root.xpath(".//a:pPr/a:defRPr/@b", namespaces=ns),
            [],
        )
        self.assertEqual(
            root.xpath(".//a:r/a:rPr/@b", namespaces=ns),
            ["1"],
        )
        self.assertEqual(
            root.xpath(
                ".//a:r/a:rPr/a:solidFill/a:srgbClr/@val",
                namespaces=ns,
            ),
            [],
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            before_path = Path(temporary_directory) / "before-table.pptx"
            after_path = Path(temporary_directory) / "after-table.pptx"
            with zipfile.ZipFile(before_path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", source)
            with zipfile.ZipFile(after_path, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", payload)
            before_report = audit(
                str(before_path),
                theme_policy="preserve",
                font_policy="preserve",
            )
            after_report = audit(
                str(after_path),
                theme_policy="preserve",
                font_policy="preserve",
            )
        before_kinds = {item["kind"] for item in before_report["errors"]}
        after_kinds = {item["kind"] for item in after_report["errors"]}
        self.assertTrue({
            "native_editability_locks",
            "redundant_run_text_color",
            "paragraph_default_bold_blocks_toggle",
        }.issubset(before_kinds))
        self.assertFalse({
            "native_editability_locks",
            "redundant_run_text_color",
            "paragraph_default_bold_blocks_toggle",
        } & after_kinds)

    def test_rewrites_existing_theme_color_picker_palette(self) -> None:
        slots = "".join(
            f'<a:{slot}><a:srgbClr val="000000"/></a:{slot}>'
            for slot in KSIB_THEME_COLORS
        )
        source = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="{A}" name="Old Theme">
  <a:themeElements><a:clrScheme name="Old Scheme">{slots}</a:clrScheme></a:themeElements>
</a:theme>""".encode()

        payload, changed = normalize_ksib_theme(
            source, "ppt/theme/theme1.xml"
        )
        root = etree.fromstring(payload)
        ns = {"a": A}
        scheme = root.xpath(".//a:clrScheme", namespaces=ns)[0]
        font_scheme = root.xpath(".//a:fontScheme", namespaces=ns)[0]

        self.assertTrue(changed)
        self.assertEqual(scheme.get("name"), KSIB_THEME_NAME)
        self.assertEqual(
            font_scheme.get("name"),
            KSIB_THEME_FONT_NAME,
        )
        self.assertEqual(
            font_scheme.xpath(
                "./a:majorFont/a:latin/@typeface | "
                "./a:majorFont/a:ea/@typeface | "
                "./a:majorFont/a:cs/@typeface | "
                "./a:minorFont/a:latin/@typeface | "
                "./a:minorFont/a:ea/@typeface | "
                "./a:minorFont/a:cs/@typeface",
                namespaces=ns,
            ),
            [KSIB_PRIMARY_TYPEFACE] * 6,
        )
        for slot, expected in KSIB_THEME_COLORS.items():
            actual = scheme.xpath(
                f"./a:{slot}/a:srgbClr/@val", namespaces=ns
            )
            self.assertEqual(actual, [expected])

    def test_qa_surfaces_macro_external_link_placeholder_and_font_drift(self) -> None:
        content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/>
</Types>"""
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree><p:sp>
    <p:nvSpPr><p:cNvPr id="2" name="body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
    <p:spPr/>
    <p:txBody><a:bodyPr/><a:lstStyle/><a:p>
      <a:r><a:rPr sz="1150"><a:latin typeface="Aptos"/></a:rPr><a:t>[TBD]</a:t></a:r>
    </a:p></p:txBody>
  </p:sp></p:spTree></p:cSld>
</p:sld>""".encode()
        rels = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/path?token=redacted" TargetMode="External"/>
</Relationships>"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            pptx = Path(temporary_directory) / "audit-fixture.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr("[Content_Types].xml", content_types)
                archive.writestr("ppt/slides/slide1.xml", slide)
                archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
                archive.writestr("ppt/vbaProject.bin", b"macro")
            report = audit(str(pptx))
            preserve_report = audit(str(pptx), font_policy="preserve")
        error_kinds = {item["kind"] for item in report["errors"]}
        warning_kinds = {item["kind"] for item in report["warnings"]}
        preserve_error_kinds = {
            item["kind"] for item in preserve_report["errors"]
        }
        preserve_warning_kinds = {
            item["kind"] for item in preserve_report["warnings"]
        }
        self.assertIn("macro_payload_present", error_kinds)
        self.assertIn("unresolved_placeholder", error_kinds)
        self.assertIn("unapproved_direct_typeface", error_kinds)
        self.assertIn("unapproved_direct_font_size", error_kinds)
        self.assertNotIn("unapproved_direct_typeface", preserve_error_kinds)
        self.assertIn("unapproved_direct_typeface", preserve_warning_kinds)
        self.assertNotIn("unapproved_direct_font_size", preserve_error_kinds)
        self.assertIn("unapproved_direct_font_size", preserve_warning_kinds)
        self.assertIn("external_relationship", warning_kinds)
        external = report["inventory"]["externalRelationships"][0]["target"]
        self.assertEqual(external, "https://example.com/<redacted>")

    def test_qa_rejects_nine_point_body_but_allows_named_source(self) -> None:
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:r><a:rPr sz="900"/><a:t>正文不应使用九号字</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="3" name="source-footnote"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:r><a:rPr sz="900"/><a:t>数据来源：测试</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="4" name="page-insight"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:r><a:rPr sz="900"/><a:t>对象名含page不能伪装成页码</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>""".encode()
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}">
  <p:sldSz cx="12192000" cy="6858000"/>
</p:presentation>""".encode()
        with tempfile.TemporaryDirectory() as temporary_directory:
            pptx = Path(temporary_directory) / "font-role.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr("ppt/presentation.xml", presentation)
                archive.writestr("ppt/slides/slide1.xml", slide)
            report = audit(
                str(pptx),
                theme_policy="preserve",
                font_policy="ksib",
            )

        findings = [
            item
            for item in report["errors"]
            if item["kind"] == "body_text_font_size_below_minimum"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["count"], 2)
        item_by_name = {
            item["object"]: item
            for item in findings[0]["items"]
        }
        self.assertEqual(item_by_name["body"]["pointSize"], 9)
        self.assertEqual(item_by_name["page-insight"]["pointSize"], 9)
        self.assertNotIn("source-footnote", item_by_name)

    def test_qa_rejects_presentation_that_references_missing_slide_part(self) -> None:
        content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
</Types>"""
        root_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdOffice" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>"""
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode()
        presentation_relationships = b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            pptx = Path(temporary_directory) / "missing-slide.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr("[Content_Types].xml", content_types)
                archive.writestr("_rels/.rels", root_relationships)
                archive.writestr("ppt/presentation.xml", presentation)
                archive.writestr(
                    "ppt/_rels/presentation.xml.rels",
                    presentation_relationships,
                )
            report = audit(
                str(pptx),
                theme_policy="preserve",
                font_policy="preserve",
            )
        error_kinds = {item["kind"] for item in report["errors"]}
        self.assertIn("missing_relationship_target", error_kinds)
        self.assertIn("presentation_slide_part_set_mismatch", error_kinds)

    def test_format_only_rewrite_can_preserve_theme_bytes(self) -> None:
        slide = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P}" xmlns:a="{A}">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name="root"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr/>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="body"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>
        <a:pPr><a:defRPr><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:defRPr></a:pPr>
        <a:r><a:rPr><a:solidFill><a:srgbClr val="1F2329"/></a:solidFill></a:rPr><a:t>text</a:t></a:r>
      </a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>""".encode()
        theme = f"""<?xml version="1.0" encoding="UTF-8"?>
<a:theme xmlns:a="{A}" name="Client Theme">
  <a:themeElements><a:clrScheme name="Client Scheme">
    <a:dk1><a:srgbClr val="111111"/></a:dk1>
  </a:clrScheme></a:themeElements>
</a:theme>""".encode()
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.pptx"
            rewritten = Path(temporary_directory) / "rewritten.pptx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "ppt/presentation.xml",
                    f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>""".encode(),
                )
                archive.writestr(
                    "ppt/_rels/presentation.xml.rels",
                    b"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>""",
                )
                archive.writestr("ppt/slides/slide1.xml", slide)
                archive.writestr("ppt/theme/theme1.xml", theme)
            baseline_fingerprint = create_fingerprint(source)
            result = _rewrite_package(
                source,
                rewritten,
                normalize_theme=False,
                preserve_text_color_structure=False,
            )
            with zipfile.ZipFile(rewritten) as archive:
                preserved = archive.read("ppt/theme/theme1.xml")
                preserved_slide = archive.read("ppt/slides/slide1.xml")
            rewritten_fingerprint = create_fingerprint(rewritten)
            semantic_report = compare_fingerprints(
                baseline_fingerprint,
                rewritten_fingerprint,
                font_policy="preserve",
            )
        self.assertEqual(preserved, theme)
        self.assertEqual(preserved_slide.count(b'<a:srgbClr val="1F2329"/>'), 1)
        self.assertEqual(result[5], 1)
        self.assertEqual(result[-1], 0)
        self.assertTrue(semantic_report["passed"])


if __name__ == "__main__":
    unittest.main()
