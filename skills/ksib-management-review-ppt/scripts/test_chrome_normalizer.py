#!/usr/bin/env python3
"""Tests for pptx_chrome_normalizer.py using a minimal OOXML fixture."""

from __future__ import annotations

import importlib.util
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SCRIPT_PATH = Path(__file__).with_name("pptx_chrome_normalizer.py")
SPEC = importlib.util.spec_from_file_location("chrome_normalizer", SCRIPT_PATH)
assert SPEC and SPEC.loader
NORMALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZER)

P = NORMALIZER.P
A = NORMALIZER.A
R = NORMALIZER.R
PR = NORMALIZER.PR


def shape_xml(
    shape_id: int,
    name: str,
    text: str,
    *,
    x: int,
    y: int,
    cx: int,
    cy: int,
    color: str,
    font_size: int,
    margin_left: int,
) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="{name}"/>
        <p:cNvSpPr/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm rot="0">
          <a:off x="{x}" y="{y}"/>
          <a:ext cx="{cx}" cy="{cy}"/>
        </a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
        <a:ln w="12700"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln>
      </p:spPr>
      <p:txBody>
        <a:bodyPr lIns="{margin_left}" rIns="0" tIns="0" bIns="0" anchor="ctr"/>
        <a:lstStyle/>
        <a:p>
          <a:pPr algn="l"/>
          <a:r>
            <a:rPr lang="zh-CN" sz="{font_size}" b="1">
              <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
              <a:latin typeface="PingFang SC"/>
              <a:ea typeface="PingFang SC"/>
            </a:rPr>
            <a:t>{text}</a:t>
          </a:r>
          <a:endParaRPr lang="zh-CN" sz="{font_size}"/>
        </a:p>
      </p:txBody>
    </p:sp>
    """


def inherited_subtitle_shape_xml(
    shape_id: int,
    name: str,
    text: str | None,
    *,
    x: int,
    color: str,
) -> str:
    run = (
        f"""<a:r>
          <a:rPr sz="1400" b="0">
            <a:latin typeface="PingFang SC"/>
            <a:ea typeface="PingFang SC"/>
            <a:cs typeface="PingFang SC"/>
          </a:rPr>
          <a:t>{text}</a:t>
        </a:r>"""
        if text is not None
        else ""
    )
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="{name}"/>
        <p:cNvSpPr/><p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm><a:off x="{x}" y="923544"/><a:ext cx="10728900" cy="238125"/></a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:noFill/><a:ln><a:noFill/></a:ln>
      </p:spPr>
      <p:txBody>
        <a:bodyPr lIns="0" rIns="0" tIns="0" bIns="0"/>
        <a:lstStyle/>
        <a:p>
          <a:pPr algn="l">
            <a:defRPr sz="1400">
              <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
              <a:latin typeface="PingFang SC"/>
              <a:ea typeface="PingFang SC"/>
              <a:cs typeface="PingFang SC"/>
            </a:defRPr>
          </a:pPr>
          {run}
        </a:p>
      </p:txBody>
    </p:sp>
    """


def slide_xml(shapes: str) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:a="{NORMALIZER.DRAWING_NS}"
           xmlns:r="{NORMALIZER.OFFICE_REL_NS}"
           xmlns:p="{NORMALIZER.PRESENTATION_NS}">
      <p:cSld><p:spTree>
        <p:nvGrpSpPr>
          <p:cNvPr id="1" name=""/>
          <p:cNvGrpSpPr/><p:nvPr/>
        </p:nvGrpSpPr>
        <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
        {shapes}
      </p:spTree></p:cSld>
      <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
    </p:sld>""".encode("utf-8")


def make_fixture(
    path: Path,
    *,
    duplicate_alias: bool = False,
    absolute_targets: bool = False,
    empty_target_subtitle: bool = False,
    target_type_mismatch: bool = False,
) -> None:
    canonical_shapes = shape_xml(
        2,
        "header-accent",
        "",
        x=731520,
        y=137160,
        cx=27432,
        cy=182880,
        color="FF4906",
        font_size=1200,
        margin_left=0,
    ) + (
        inherited_subtitle_shape_xml(
            3,
            "header-text",
            "Canonical Header",
            x=838200,
            color="646A73",
        )
        if empty_target_subtitle
        else shape_xml(
            3,
            "header-text",
            "Canonical Header",
            x=838200,
            y=137160,
            cx=10619280,
            cy=182880,
            color="1F2329",
            font_size=1200,
            margin_left=0,
        )
    )
    target_accent = shape_xml(
        2,
        "v284-header-accent",
        "",
        x=733000,
        y=140000,
        cx=38000,
        cy=210000,
        color="FF4B0B",
        font_size=1000,
        margin_left=9144,
    )
    target_header = (
        inherited_subtitle_shape_xml(
            3,
            "v284-header-text",
            None,
            x=857250,
            color="FF4906",
        )
        if empty_target_subtitle
        else shape_xml(
            3,
            "v284-header-text",
            "Target Header Must Stay",
            x=857250,
            y=114300,
            cx=6667500,
            cy=247650,
            color="646A73",
            font_size=1000,
            margin_left=9144,
        )
    )
    if target_type_mismatch:
        target_header = target_header.replace(
            "<p:sp>", "<p:cxnSp>", 1
        ).replace("</p:sp>", "</p:cxnSp>", 1)
    target_shapes = target_accent + target_header
    if duplicate_alias:
        target_shapes += shape_xml(
            4,
            "legacy-header-text",
            "Ambiguous",
            x=1,
            y=1,
            cx=1,
            cy=1,
            color="000000",
            font_size=900,
            margin_left=0,
        )

    content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
      <Default Extension="xml" ContentType="application/xml"/>
      <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
      <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
      <Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
    </Types>"""
    root_rels = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
    </Relationships>"""
    presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
    <p:presentation xmlns:p="{NORMALIZER.PRESENTATION_NS}"
                    xmlns:r="{NORMALIZER.OFFICE_REL_NS}">
      <p:sldIdLst>
        <p:sldId id="256" r:id="rId1"/>
        <p:sldId id="257" r:id="rId2"/>
      </p:sldIdLst>
      <p:sldSz cx="12192000" cy="6858000"/>
    </p:presentation>""".encode("utf-8")
    slide1_target = (
        "/ppt/slides/slide1.xml"
        if absolute_targets
        else "slides/slide1.xml"
    )
    slide2_target = (
        "/ppt/slides/slide2.xml"
        if absolute_targets
        else "slides/slide2.xml"
    )
    presentation_rels = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="{NORMALIZER.PACKAGE_REL_NS}">
      <Relationship Id="rId1" Type="{NORMALIZER.OFFICE_REL_NS}/slide" Target="{slide1_target}"/>
      <Relationship Id="rId2" Type="{NORMALIZER.OFFICE_REL_NS}/slide" Target="{slide2_target}"/>
    </Relationships>""".encode("utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr(
            "ppt/_rels/presentation.xml.rels", presentation_rels
        )
        archive.writestr("ppt/slides/slide1.xml", slide_xml(canonical_shapes))
        archive.writestr("ppt/slides/slide2.xml", slide_xml(target_shapes))


def load_shapes(path: Path, slide: int) -> dict[str, ET.Element]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read(f"ppt/slides/slide{slide}.xml"))
    return {
        NORMALIZER.shape_name(shape): shape
        for shape in NORMALIZER.iter_named_shapes(root)
    }


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        text=True,
        capture_output=True,
        check=False,
    )


class ChromeNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.pptx"
        make_fixture(self.source)
        self.common_args = [
            "--input",
            str(self.source),
            "--canonical-slide",
            "1",
            "--roles",
            "header-accent,header-text",
            "--alias",
            r"header-accent=^v\d+-header-accent$",
            "--alias",
            r"header-text=^(?:v\d+-header-text|legacy-header-text)$",
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_audit_detects_two_header_systems_without_output(self) -> None:
        report_path = self.root / "audit.json"
        result = run_tool(*self.common_args, "--report", str(report_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        target_findings = [
            finding
            for finding in report["findings"]
            if finding["slide"] == 2
        ]
        self.assertTrue(all(f["differences"] for f in target_findings))
        self.assertEqual(report["mode"], "audit")
        self.assertEqual(report["semanticSafety"]["changedShapeCount"], 0)
        self.assertFalse((self.root / "output.pptx").exists())

    def test_apply_exactly_aligns_format_and_preserves_text(self) -> None:
        output = self.root / "output.pptx"
        report_path = self.root / "apply.json"
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        result = run_tool(
            *self.common_args,
            "--output",
            str(output),
            "--report",
            str(report_path),
            "--apply",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["semanticSafety"]["visibleTextPreserved"])
        self.assertEqual(report["semanticSafety"]["changedShapeCount"], 2)
        self.assertEqual(
            hashlib.sha256(self.source.read_bytes()).hexdigest(), source_hash
        )
        target_findings = [
            finding
            for finding in report["findings"]
            if finding["slide"] == 2
        ]
        self.assertTrue(all(f["postApplyAligned"] for f in target_findings))

        canonical = load_shapes(output, 1)
        target = load_shapes(output, 2)
        self.assertEqual(
            NORMALIZER.visible_text(target["v284-header-text"]),
            ("Target Header Must Stay",),
        )
        for canonical_name, target_name in [
            ("header-accent", "v284-header-accent"),
            ("header-text", "v284-header-text"),
        ]:
            self.assertEqual(
                NORMALIZER.format_signature(target[target_name]),
                NORMALIZER.expected_signature(
                    canonical[canonical_name], target[target_name]
                ),
            )

    def test_second_run_is_idempotent(self) -> None:
        first = self.root / "first.pptx"
        second = self.root / "second.pptx"
        first_result = run_tool(
            *self.common_args, "--output", str(first), "--apply"
        )
        self.assertEqual(first_result.returncode, 0, first_result.stderr)
        second_args = [
            "--input",
            str(first),
            "--canonical-slide",
            "1",
            "--roles",
            "header-accent,header-text",
            "--alias",
            r"header-accent=^v\d+-header-accent$",
            "--alias",
            r"header-text=^v\d+-header-text$",
            "--output",
            str(second),
            "--apply",
        ]
        second_result = run_tool(*second_args)
        self.assertEqual(second_result.returncode, 0, second_result.stderr)
        report = json.loads(second_result.stdout)
        self.assertEqual(report["semanticSafety"]["changedShapeCount"], 0)
        self.assertEqual(load_shapes(first, 2).keys(), load_shapes(second, 2).keys())
        self.assertEqual(
            NORMALIZER.format_signature(
                load_shapes(first, 2)["v284-header-text"]
            ),
            NORMALIZER.format_signature(
                load_shapes(second, 2)["v284-header-text"]
            ),
        )

    def test_ambiguous_role_blocks_apply_and_writes_no_output(self) -> None:
        ambiguous = self.root / "ambiguous.pptx"
        make_fixture(ambiguous, duplicate_alias=True)
        output = self.root / "blocked.pptx"
        args = self.common_args.copy()
        args[1] = str(ambiguous)
        result = run_tool(*args, "--output", str(output), "--apply")
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertTrue(report["blocked"])
        self.assertEqual(report["semanticSafety"]["ambiguousRoleCount"], 1)
        self.assertFalse(output.exists())

    def test_package_absolute_slide_targets_are_supported(self) -> None:
        absolute_source = self.root / "absolute-targets.pptx"
        make_fixture(absolute_source, absolute_targets=True)
        args = self.common_args.copy()
        args[1] = str(absolute_source)
        result = run_tool(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["passed"])
        self.assertEqual(report["selectedSlides"], [1, 2])

    def test_empty_target_paragraph_matches_canonical_effective_font_set(
        self,
    ) -> None:
        source = self.root / "empty-subtitle.pptx"
        output = self.root / "empty-subtitle-output.pptx"
        make_fixture(source, empty_target_subtitle=True)
        args = self.common_args.copy()
        args[1] = str(source)
        result = run_tool(*args, "--output", str(output), "--apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        subtitle_findings = [
            finding
            for finding in report["findings"]
            if finding["role"] == "header-text"
        ]
        self.assertTrue(
            all(finding["postApplyAligned"] for finding in subtitle_findings)
        )
        canonical = load_shapes(output, 1)["header-text"]
        target = load_shapes(output, 2)["v284-header-text"]
        self.assertEqual("".join(NORMALIZER.visible_text(target)), "")
        self.assertGreaterEqual(
            report["semanticSafety"]["styleCarrierRunCount"], 1
        )
        self.assertEqual(
            NORMALIZER.effective_font_style_set(canonical),
            NORMALIZER.effective_font_style_set(target),
        )

    def test_geometry_scope_does_not_change_color_or_font(self) -> None:
        output = self.root / "geometry-only.pptx"
        before_shapes = load_shapes(self.source, 2)
        result = run_tool(
            *self.common_args,
            "--scope",
            "geometry",
            "--output",
            str(output),
            "--apply",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "geometry")
        canonical_shapes = load_shapes(output, 1)
        after_shapes = load_shapes(output, 2)
        for canonical_name, target_name in [
            ("header-accent", "v284-header-accent"),
            ("header-text", "v284-header-text"),
        ]:
            self.assertEqual(
                NORMALIZER.format_signature(
                    after_shapes[target_name], scope="geometry"
                ),
                NORMALIZER.format_signature(
                    canonical_shapes[canonical_name], scope="geometry"
                ),
            )
            self.assertEqual(
                NORMALIZER.format_signature(
                    after_shapes[target_name], scope="style"
                ),
                NORMALIZER.format_signature(
                    before_shapes[target_name], scope="style"
                ),
            )

    def test_style_scope_does_not_change_geometry(self) -> None:
        output = self.root / "style-only.pptx"
        before_shapes = load_shapes(self.source, 2)
        result = run_tool(
            *self.common_args,
            "--scope",
            "style",
            "--output",
            str(output),
            "--apply",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "style")
        canonical_shapes = load_shapes(output, 1)
        after_shapes = load_shapes(output, 2)
        for canonical_name, target_name in [
            ("header-accent", "v284-header-accent"),
            ("header-text", "v284-header-text"),
        ]:
            self.assertEqual(
                NORMALIZER.format_signature(
                    after_shapes[target_name], scope="geometry"
                ),
                NORMALIZER.format_signature(
                    before_shapes[target_name], scope="geometry"
                ),
            )
            self.assertEqual(
                NORMALIZER.format_signature(
                    after_shapes[target_name], scope="style"
                ),
                NORMALIZER.expected_signature(
                    canonical_shapes[canonical_name],
                    after_shapes[target_name],
                    scope="style",
                ),
            )

    def test_object_type_mismatch_blocks_apply(self) -> None:
        mismatched = self.root / "type-mismatch.pptx"
        output = self.root / "type-mismatch-output.pptx"
        make_fixture(mismatched, target_type_mismatch=True)
        args = self.common_args.copy()
        args[1] = str(mismatched)
        result = run_tool(*args, "--output", str(output), "--apply")
        self.assertEqual(result.returncode, 2)
        report = json.loads(result.stdout)
        self.assertTrue(report["blocked"])
        self.assertEqual(
            report["semanticSafety"]["typeMismatchCount"], 1
        )
        mismatch_findings = [
            finding
            for finding in report["findings"]
            if finding["status"] == "type-mismatch"
        ]
        self.assertEqual(len(mismatch_findings), 1)
        self.assertFalse(mismatch_findings[0]["typeMatched"])
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
