#!/usr/bin/env python3
"""Regression tests for the final-PPTX format engineering contract."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ooxml_qa import (  # noqa: E402
    A,
    C,
    P,
    EMU_PER_INCH,
    FORMAT_CONTRACT_SCHEMA,
    audit,
    chart_data_mode,
    is_notes_placeholder,
    load_format_contract,
    object_type,
    slide_object_records,
    validate_cross_slide_equality_groups,
    validate_slide_format_contract,
)

P_NS = P[1:-1]
A_NS = A[1:-1]
C_NS = C[1:-1]
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def emu(value: float) -> int:
    return round(value * EMU_PER_INCH)


def text_shape(
    object_id: int,
    name: str,
    text: str,
    geometry: tuple[float, float, float, float],
    *,
    zero_margins: bool = True,
    geometry_delta_emu: tuple[int, int, int, int] = (0, 0, 0, 0),
    fill_color: str | None = None,
    font_size: int = 2200,
    anchor: str | None = None,
    anchor_centered: bool | None = None,
) -> str:
    x, y, width, height = geometry
    delta_x, delta_y, delta_width, delta_height = geometry_delta_emu
    margins = (
        ' lIns="0" rIns="0" tIns="0" bIns="0"'
        if zero_margins
        else ""
    )
    fill = (
        f'<a:solidFill><a:srgbClr val="{fill_color}"/></a:solidFill>'
        if fill_color
        else ""
    )
    vertical_attributes = ""
    if anchor is not None:
        vertical_attributes += f' anchor="{anchor}"'
    if anchor_centered is not None:
        vertical_attributes += (
            f' anchorCtr="{1 if anchor_centered else 0}"'
        )
    return f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="{object_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{emu(x) + delta_x}" y="{emu(y) + delta_y}"/><a:ext cx="{emu(width) + delta_width}" cy="{emu(height) + delta_height}"/></a:xfrm>{fill}</p:spPr>
  <p:txBody><a:bodyPr{margins}{vertical_attributes}/><a:lstStyle/><a:p><a:r><a:rPr sz="{font_size}"/><a:t>{text}</a:t></a:r></a:p></p:txBody>
</p:sp>"""


def structured_text_shape(
    object_id: int,
    name: str,
    geometry: tuple[float, float, float, float],
    paragraphs: list[str],
    *,
    explicit_break: bool = False,
) -> str:
    x, y, width, height = geometry
    if explicit_break:
        paragraph_xml = (
            '<a:p><a:r><a:rPr sz="2200"/><a:t>第一部分</a:t></a:r>'
            '<a:br/><a:r><a:rPr sz="2200"/><a:t>第二部分</a:t></a:r></a:p>'
        )
    else:
        paragraph_xml = "".join(
            f'<a:p><a:r><a:rPr sz="2200"/><a:t>{text}</a:t></a:r></a:p>'
            for text in paragraphs
        )
    return f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="{object_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(width)}" cy="{emu(height)}"/></a:xfrm></p:spPr>
  <p:txBody><a:bodyPr lIns="0" rIns="0" tIns="0" bIns="0"/><a:lstStyle/>{paragraph_xml}</p:txBody>
</p:sp>"""


def chart_frame(
    object_id: int,
    name: str,
    geometry: tuple[float, float, float, float],
) -> str:
    x, y, width, height = geometry
    return f"""<p:graphicFrame>
  <p:nvGraphicFramePr><p:cNvPr id="{object_id}" name="{name}"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr>
  <p:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(width)}" cy="{emu(height)}"/></p:xfrm>
  <a:graphic><a:graphicData uri="{C_NS}"><c:chart xmlns:c="{C_NS}"/></a:graphicData></a:graphic>
</p:graphicFrame>"""


def picture(
    object_id: int,
    name: str,
    geometry: tuple[float, float, float, float],
) -> str:
    x, y, width, height = geometry
    return f"""<p:pic>
  <p:nvPicPr><p:cNvPr id="{object_id}" name="{name}"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
  <p:blipFill/>
  <p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(width)}" cy="{emu(height)}"/></a:xfrm></p:spPr>
</p:pic>"""


def connector(
    object_id: int,
    name: str,
    *,
    start_connected: bool,
    end_connected: bool,
    arrowhead: bool,
) -> str:
    start = (
        '<a:stCxn id="10" idx="3"/>'
        if start_connected
        else ""
    )
    end = (
        '<a:endCxn id="11" idx="1"/>'
        if end_connected
        else ""
    )
    arrow = '<a:tailEnd type="arrow"/>' if arrowhead else ""
    return f"""<p:cxnSp>
  <p:nvCxnSpPr><p:cNvPr id="{object_id}" name="{name}"/><p:cNvCxnSpPr>{start}{end}</p:cNvCxnSpPr><p:nvPr/></p:nvCxnSpPr>
  <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/></a:xfrm><a:ln>{arrow}</a:ln></p:spPr>
</p:cxnSp>"""


def slide(*objects: str) -> ET.Element:
    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:c="{C_NS}">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name="root"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
    <p:grpSpPr/>
    {''.join(objects)}
  </p:spTree></p:cSld>
</p:sld>"""
    return ET.fromstring(payload)


def contract() -> dict:
    return {
        "schemaVersion": FORMAT_CONTRACT_SCHEMA,
        "deck": {
            "widthIn": 13.333,
            "heightIn": 7.5,
            "toleranceIn": 0.03,
        },
        "nativeEditability": {
            "allowFullSlideRaster": False,
            "fullSlideRasterCoverageThreshold": 0.9,
        },
        "hierarchy": {
            "roles": ["action-title", "subtitle", "takeaway"],
            "similarityThreshold": 0.72,
        },
        "takeawayPolicy": {
            "requireNamedBottomTextBlocks": True,
            "bottomBandYIn": 6.2,
            "allowedBottomRoles": [
                "takeaway",
                "source-footnote",
                "page-number",
            ],
        },
        "roleGeometry": {},
        "headerModes": {
            "title-only": {
                "requiredRoles": ["action-title"],
                "forbiddenRoles": ["subtitle"],
                "roleGeometry": {
                    "action-title": {
                        "objectTypes": ["textBoxes"],
                        "geometry": {
                            "x": 0.8,
                            "y": 0.55,
                            "w": 11.733,
                            "h": 0.4,
                        },
                        "zeroTextMargins": True,
                    }
                },
            }
        },
    }


def equality_context(
    slide_number: int,
    root: ET.Element,
    *,
    header_mode: str = "title-only",
) -> dict:
    return {
        "slide": slide_number,
        "part": f"ppt/slides/slide{slide_number}.xml",
        "slideRole": "content",
        "headerMode": header_mode,
        "records": slide_object_records(root),
    }


class FormatContractTest(unittest.TestCase):
    def test_legacy_contract_without_cross_slide_groups_is_unchanged(self) -> None:
        errors, inventory = validate_cross_slide_equality_groups(
            contract=contract(),
            slide_contexts=[],
        )
        self.assertEqual(errors, [])
        self.assertEqual(inventory, [])

    def test_cross_slide_exact_equality_accepts_aliases(self) -> None:
        first = slide(
            text_shape(
                2,
                "header-accent",
                "A",
                (0.8, 0.15, 0.03, 0.2),
                fill_color="FF4906",
            )
        )
        second = slide(
            text_shape(
                2,
                "v284-header-accent",
                "B",
                (0.8, 0.15, 0.03, 0.2),
                fill_color="FF4906",
                anchor="t",
                anchor_centered=False,
            )
        )
        payload = contract()
        payload["crossSlideEqualityGroups"] = [{
            "id": "title-only-chrome",
            "referenceSlide": 2,
            "slides": [2, 3],
            "roles": ["header-accent"],
            "geometryToleranceEmu": 0,
            "roleAliases": {
                "header-accent": [
                    "v283-header-accent",
                    "v284-header-accent",
                    "v285-header-accent",
                ],
            },
        }]
        errors, inventory = validate_cross_slide_equality_groups(
            contract=payload,
            slide_contexts=[
                equality_context(2, first),
                equality_context(3, second),
            ],
        )
        self.assertEqual(errors, [])
        self.assertEqual(inventory[0]["referenceSlide"], 2)
        self.assertEqual(
            inventory[0]["roles"]["header-accent"][1]["object"],
            "v284-header-accent",
        )

    def test_cross_slide_one_emu_geometry_drift_fails(self) -> None:
        first = slide(
            text_shape(
                2,
                "header-accent",
                "A",
                (0.8, 0.15, 0.03, 0.2),
                fill_color="FF4906",
            )
        )
        second = slide(
            text_shape(
                2,
                "header-accent",
                "B",
                (0.8, 0.15, 0.03, 0.2),
                geometry_delta_emu=(1, 0, 0, 0),
                fill_color="FF4906",
            )
        )
        payload = contract()
        payload["crossSlideEqualityGroups"] = [{
            "id": "title-only-chrome",
            "slides": [2, 3],
            "roles": ["header-accent"],
        }]
        errors, _ = validate_cross_slide_equality_groups(
            contract=payload,
            slide_contexts=[
                equality_context(2, first),
                equality_context(3, second),
            ],
        )
        drift = next(
            item
            for item in errors
            if item["kind"] == "format_cross_slide_geometry_drift"
        )
        self.assertEqual(drift["geometryToleranceEmu"], 0)
        self.assertEqual(drift["drift"]["x"]["deltaEmu"], 1)

    def test_cross_slide_color_and_font_size_drift_fail(self) -> None:
        first = slide(
            text_shape(
                2,
                "header-text",
                "第一章",
                (0.92, 0.15, 4.0, 0.2),
                fill_color="FF4906",
                font_size=1200,
            )
        )
        second = slide(
            text_shape(
                2,
                "header-text",
                "第二章",
                (0.92, 0.15, 4.0, 0.2),
                fill_color="FF4B0B",
                font_size=1400,
            )
        )
        payload = contract()
        payload["crossSlideEqualityGroups"] = [{
            "id": "title-only-chrome",
            "slides": [2, 3],
            "roles": ["header-text"],
        }]
        errors, _ = validate_cross_slide_equality_groups(
            contract=payload,
            slide_contexts=[
                equality_context(2, first),
                equality_context(3, second),
            ],
        )
        style_drift = next(
            item
            for item in errors
            if item["kind"] == "format_cross_slide_style_drift"
        )
        self.assertIn("fill", style_drift["fields"])
        self.assertIn("font", style_drift["fields"])

    def test_cross_slide_different_header_modes_are_isolated(self) -> None:
        title_only = slide(
            text_shape(
                2,
                "header-accent",
                "A",
                (0.8, 0.15, 0.03, 0.2),
                fill_color="FF4906",
            )
        )
        title_subtitle = slide(
            text_shape(
                2,
                "header-accent",
                "B",
                (0.9, 0.25, 0.08, 0.3),
                fill_color="000000",
                font_size=1400,
            )
        )
        payload = contract()
        payload["crossSlideEqualityGroups"] = [{
            "id": "content-chrome",
            "slideSelector": {
                "headerModes": ["title-only", "title-subtitle"],
            },
            "roles": ["header-accent"],
        }]
        errors, inventory = validate_cross_slide_equality_groups(
            contract=payload,
            slide_contexts=[
                equality_context(
                    2,
                    title_only,
                    header_mode="title-only",
                ),
                equality_context(
                    3,
                    title_subtitle,
                    header_mode="title-subtitle",
                ),
            ],
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            {item["headerMode"] for item in inventory},
            {"title-only", "title-subtitle"},
        )

    def test_cross_slide_object_type_and_vertical_alignment_drift_fail(
        self,
    ) -> None:
        first = slide(
            text_shape(
                2,
                "header-accent",
                "A",
                (0.8, 0.15, 0.03, 0.2),
                fill_color="FF4906",
            ),
            text_shape(
                3,
                "header-text",
                "第一章",
                (0.92, 0.15, 4.0, 0.2),
                anchor="t",
                anchor_centered=False,
            ),
        )
        second = slide(
            picture(
                2,
                "header-accent",
                (0.8, 0.15, 0.03, 0.2),
            ),
            text_shape(
                3,
                "header-text",
                "第二章",
                (0.92, 0.15, 4.0, 0.2),
                anchor="ctr",
                anchor_centered=True,
            ),
        )
        payload = contract()
        payload["crossSlideEqualityGroups"] = [{
            "id": "content-chrome",
            "slides": [2, 3],
            "roles": ["header-accent", "header-text"],
        }]
        errors, _ = validate_cross_slide_equality_groups(
            contract=payload,
            slide_contexts=[
                equality_context(2, first),
                equality_context(3, second),
            ],
        )
        type_drift = next(
            item
            for item in errors
            if item["kind"] == "format_cross_slide_object_type_drift"
        )
        self.assertEqual(type_drift["expected"], "textBoxes")
        self.assertEqual(type_drift["actual"], "pictures")
        vertical_drift = next(
            item
            for item in errors
            if (
                item["kind"] == "format_cross_slide_style_drift"
                and item["role"] == "header-text"
            )
        )
        self.assertIn("verticalAlignment", vertical_drift["fields"])

    def test_cross_slide_empty_roles_fail_instead_of_vacuous_pass(
        self,
    ) -> None:
        payload = contract()
        payload["crossSlideEqualityGroups"] = [{
            "id": "empty-role-group",
            "slides": [2, 3],
            "roles": [],
        }]
        errors, _ = validate_cross_slide_equality_groups(
            contract=payload,
            slide_contexts=[],
        )
        self.assertIn(
            "format_cross_slide_group_roles_invalid",
            {item["kind"] for item in errors},
        )

    def test_cross_slide_missing_and_filtered_slides_fail_coverage(
        self,
    ) -> None:
        root = slide(
            text_shape(
                2,
                "header-accent",
                "A",
                (0.8, 0.15, 0.03, 0.2),
            )
        )
        missing_payload = contract()
        missing_payload["crossSlideEqualityGroups"] = [{
            "id": "missing-slide",
            "slides": [2, 99],
            "roles": ["header-accent"],
        }]
        missing_errors, _ = validate_cross_slide_equality_groups(
            contract=missing_payload,
            slide_contexts=[equality_context(2, root)],
        )
        missing_kinds = {item["kind"] for item in missing_errors}
        self.assertIn(
            "format_cross_slide_group_slide_missing",
            missing_kinds,
        )
        self.assertIn(
            "format_cross_slide_group_insufficient_coverage",
            missing_kinds,
        )

        filtered_payload = contract()
        filtered_payload["crossSlideEqualityGroups"] = [{
            "id": "filtered-slide",
            "slides": [2, 3],
            "slideSelector": {"headerModes": ["title-only"]},
            "roles": ["header-accent"],
        }]
        filtered_errors, _ = validate_cross_slide_equality_groups(
            contract=filtered_payload,
            slide_contexts=[
                equality_context(2, root, header_mode="title-only"),
                equality_context(
                    3,
                    root,
                    header_mode="title-subtitle",
                ),
            ],
        )
        self.assertIn(
            "format_cross_slide_group_insufficient_coverage",
            {item["kind"] for item in filtered_errors},
        )

    def test_cross_slide_compare_fields_can_authorize_geometry_only(
        self,
    ) -> None:
        first = slide(
            text_shape(
                2,
                "header-text",
                "第一章",
                (0.92, 0.15, 4.0, 0.2),
                fill_color="FF4906",
                font_size=1200,
                anchor="t",
            )
        )
        second = slide(
            text_shape(
                2,
                "header-text",
                "第二章",
                (0.92, 0.15, 4.0, 0.2),
                fill_color="000000",
                font_size=1800,
                anchor="ctr",
            )
        )
        payload = contract()
        payload["crossSlideEqualityGroups"] = [{
            "id": "geometry-only",
            "slides": [2, 3],
            "roles": ["header-text"],
            "compareFields": ["geometry"],
        }]
        errors, inventory = validate_cross_slide_equality_groups(
            contract=payload,
            slide_contexts=[
                equality_context(2, first),
                equality_context(3, second),
            ],
        )
        self.assertEqual(errors, [])
        self.assertEqual(inventory[0]["compareFields"], ["geometry"])

    def test_contract_loader_rejects_unknown_compare_fields(self) -> None:
        payload = contract()
        payload["slides"] = [{"slide": 1}]
        payload["crossSlideEqualityGroups"] = [{
            "id": "bad-fields",
            "slides": [1, 2],
            "roles": ["header-accent"],
            "compareFields": ["geometry", "shadow"],
        }]
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "format-contract.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            _, findings = load_format_contract(str(path))
        self.assertIn(
            "format_cross_slide_group_compare_fields_invalid",
            {item["kind"] for item in findings},
        )

    def test_header_overlap_and_divider_position_fail_with_aliases(
        self,
    ) -> None:
        root = slide(
            text_shape(
                2,
                "v284-action-title",
                "本页标题结论",
                (0.8, 0.55, 11.733, 0.62),
            ),
            text_shape(
                3,
                "v284-subtitle",
                "统计范围与时间口径",
                (0.8, 0.99, 11.733, 0.24),
                font_size=1400,
            ),
            text_shape(
                4,
                "v284-title-divider",
                "",
                (0.8, 1.10, 11.733, 0.01),
            ),
        )
        payload = contract()
        payload["headerModes"]["title-subtitle"] = {
            "requiredRoles": [],
            "forbiddenRoles": [],
            "roleGeometry": {},
        }
        payload["crossSlideEqualityGroups"] = [{
            "id": "legacy-header-aliases",
            "slides": [15, 16],
            "roles": ["action-title", "subtitle", "title-divider"],
            "roleAliases": {
                "action-title": ["v284-action-title"],
                "subtitle": ["v284-subtitle"],
                "title-divider": ["v284-title-divider"],
            },
        }]
        errors, inventory = validate_slide_format_contract(
            slide_number=15,
            slide_part="ppt/slides/slide15.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=payload,
            slide_contract={
                "slide": 15,
                "slideRole": "content",
                "headerMode": "title-subtitle",
            },
        )
        overlaps = [
            item
            for item in errors
            if item["kind"] == "format_header_role_overlap"
        ]
        self.assertEqual(len(overlaps), 2)
        self.assertEqual(
            {item["rule"] for item in overlaps},
            {
                "positive-area-overlap",
                "divider-above-subtitle-bottom",
            },
        )
        self.assertEqual(
            inventory["headerRoleGeometry"]["roles"][
                "action-title"
            ]["object"],
            "v284-action-title",
        )

    def test_header_roles_may_touch_boundaries_without_overlap(self) -> None:
        root = slide(
            text_shape(
                2,
                "action-title",
                "本页标题结论",
                (0.8, 0.55, 11.733, 0.44),
            ),
            text_shape(
                3,
                "subtitle",
                "统计范围与时间口径",
                (0.8, 0.99, 11.733, 0.24),
                font_size=1400,
            ),
            text_shape(
                4,
                "title-divider",
                "",
                (0.8, 1.23, 11.733, 0.01),
            ),
        )
        payload = contract()
        payload["headerModes"]["title-subtitle"] = {
            "requiredRoles": [],
            "forbiddenRoles": [],
            "roleGeometry": {},
        }
        errors, _ = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=payload,
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-subtitle",
            },
        )
        self.assertNotIn(
            "format_header_role_overlap",
            {item["kind"] for item in errors},
        )

    def test_action_title_policy_rejects_multiple_paragraphs(self) -> None:
        root = slide(
            structured_text_shape(
                2,
                "action-title",
                (0.8, 0.55, 11.733, 0.4),
                ["第一段结论", "第二段解释"],
            ),
        )
        payload = contract()
        payload["titlePolicy"] = {
            "forbidMultipleParagraphs": True,
            "forbidExplicitLineBreaks": True,
            "maxWeightedCharacters": 38,
        }
        errors, inventory = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=payload,
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-only",
            },
        )
        self.assertIn(
            "format_action_title_multiline",
            {item["kind"] for item in errors},
        )
        self.assertEqual(
            inventory["actionTitleSingleLine"]["nonEmptyParagraphCount"],
            2,
        )

    def test_action_title_policy_rejects_explicit_break_and_width(self) -> None:
        payload = contract()
        payload["titlePolicy"] = {
            "forbidMultipleParagraphs": True,
            "forbidExplicitLineBreaks": True,
            "maxWeightedCharacters": 7,
        }
        root = slide(
            structured_text_shape(
                2,
                "action-title",
                (0.8, 0.55, 11.733, 0.4),
                ["ignored"],
                explicit_break=True,
            ),
        )
        errors, _ = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=payload,
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-only",
            },
        )
        kinds = {item["kind"] for item in errors}
        self.assertIn("format_action_title_multiline", kinds)
        self.assertIn("format_action_title_width_budget_exceeded", kinds)

    def test_body_start_policy_blocks_content_above_open_header(self) -> None:
        payload = contract()
        payload["headerModes"]["title-only"]["bodyStartY"] = 1.52
        payload["bodyStartPolicy"] = {"requireNamedAnchors": True}
        root = slide(
            text_shape(
                2,
                "action-title",
                "本页标题结论",
                (0.8, 0.55, 11.733, 0.4),
            ),
            text_shape(
                3,
                "body-main",
                "主体证据",
                (0.8, 1.40, 5.0, 1.0),
            ),
        )
        errors, inventory = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=payload,
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-only",
                "bodyStartRoles": ["body-main"],
            },
        )
        self.assertIn(
            "format_body_starts_above_header_clearance",
            {item["kind"] for item in errors},
        )
        self.assertEqual(inventory["bodyStart"]["bodyStartYIn"], 1.52)

    def test_body_start_policy_accepts_exact_boundary(self) -> None:
        payload = contract()
        payload["headerModes"]["title-only"]["bodyStartY"] = 1.52
        payload["bodyStartPolicy"] = {"requireNamedAnchors": True}
        root = slide(
            text_shape(
                2,
                "action-title",
                "本页标题结论",
                (0.8, 0.55, 11.733, 0.4),
            ),
            text_shape(
                3,
                "body-main",
                "主体证据",
                (0.8, 1.52, 5.0, 1.0),
            ),
        )
        errors, _ = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=payload,
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-only",
                "bodyStartRoles": ["body-main"],
            },
        )
        self.assertNotIn(
            "format_body_starts_above_header_clearance",
            {item["kind"] for item in errors},
        )

    def test_single_line_policy_rejects_two_line_mode_and_title_divider(self) -> None:
        payload = contract()
        payload["titlePolicy"] = {
            "maxActionTitleLines": 1,
            "forbidMultipleParagraphs": True,
            "forbidExplicitLineBreaks": True,
            "maxWeightedCharacters": 38,
            "defaultTitleDividerPolicy": "forbid",
        }
        payload["headerModes"]["title-two-line"] = payload["headerModes"]["title-only"]
        root = slide(
            text_shape(
                2,
                "action-title",
                "本页标题结论",
                (0.8, 0.55, 11.733, 0.4),
            ),
            text_shape(
                3,
                "title-divider",
                "",
                (0.8, 1.10, 11.733, 0.01),
            ),
        )
        errors, _ = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=payload,
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-two-line",
            },
        )
        kinds = {item["kind"] for item in errors}
        self.assertIn("format_two_line_header_mode_forbidden", kinds)
        self.assertIn("format_default_title_divider_forbidden", kinds)

    def test_shape_classification_requires_non_empty_text(self) -> None:
        empty_text_body = ET.fromstring(
            f"""<p:sp xmlns:p="{P_NS}" xmlns:a="{A_NS}">
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
</p:sp>"""
        )
        whitespace_only_text = ET.fromstring(
            f"""<p:sp xmlns:p="{P_NS}" xmlns:a="{A_NS}">
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>   </a:t></a:r></a:p></p:txBody>
</p:sp>"""
        )
        real_text_box = ET.fromstring(
            f"""<p:sp xmlns:p="{P_NS}" xmlns:a="{A_NS}">
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>真实文本</a:t></a:r></a:p></p:txBody>
</p:sp>"""
        )
        native_connector = ET.fromstring(f'<p:cxnSp xmlns:p="{P_NS}"/>')
        native_table = ET.fromstring(
            f"""<p:graphicFrame xmlns:p="{P_NS}" xmlns:a="{A_NS}">
  <a:graphic><a:graphicData><a:tbl/></a:graphicData></a:graphic>
</p:graphicFrame>"""
        )
        native_chart = ET.fromstring(
            f"""<p:graphicFrame xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:c="{C_NS}">
  <a:graphic><a:graphicData><c:chart/></a:graphicData></a:graphic>
</p:graphicFrame>"""
        )

        self.assertEqual(object_type(empty_text_body), "shapes")
        self.assertEqual(object_type(whitespace_only_text), "shapes")
        self.assertEqual(object_type(real_text_box), "textBoxes")
        self.assertEqual(object_type(native_connector), "connectors")
        self.assertEqual(object_type(native_table), "tables")
        self.assertEqual(object_type(native_chart), "charts")

    def test_chart_data_inventory_distinguishes_literal_and_workbook(self) -> None:
        literal_root = ET.fromstring(
            f"""<c:chartSpace xmlns:c="{C_NS}">
  <c:chart><c:plotArea><c:barChart><c:ser>
    <c:val><c:numLit><c:pt idx="0"><c:v>57</c:v></c:pt></c:numLit></c:val>
  </c:ser></c:barChart></c:plotArea></c:chart>
</c:chartSpace>"""
        )
        literal = chart_data_mode(
            chart_part="ppt/charts/chart1.xml",
            chart_root=literal_root,
            relationships_by_source={},
        )
        self.assertEqual(literal["mode"], "nativeLiteral")

        workbook_root = ET.fromstring(
            f"""<c:chartSpace xmlns:c="{C_NS}" xmlns:r="{R_NS}">
  <c:externalData r:id="rIdWorkbook"/>
  <c:chart><c:plotArea><c:barChart><c:ser>
    <c:val><c:numRef><c:f>Sheet1!$B$2:$B$3</c:f></c:numRef></c:val>
  </c:ser></c:barChart></c:plotArea></c:chart>
</c:chartSpace>"""
        )
        relationship = ET.fromstring(
            f"""<Relationship
  xmlns="http://schemas.openxmlformats.org/package/2006/relationships"
  Id="rIdWorkbook"
  Type="{R_NS}/package"
  Target="../embeddings/Microsoft_Excel_Worksheet1.xlsx"/>"""
        )
        workbook = chart_data_mode(
            chart_part="ppt/charts/chart1.xml",
            chart_root=workbook_root,
            relationships_by_source={
                "ppt/charts/chart1.xml": {
                    "rIdWorkbook": relationship,
                }
            },
        )
        self.assertEqual(workbook["mode"], "embeddedWorkbook")
        self.assertEqual(
            workbook["embeddedTargets"],
            ["ppt/embeddings/Microsoft_Excel_Worksheet1.xlsx"],
        )

    def test_valid_role_geometry_and_native_chart_pass(self) -> None:
        root = slide(
            text_shape(
                2,
                "action-title",
                "类别D形成唯一视觉焦点",
                (0.8, 0.55, 11.733, 0.4),
            ),
            chart_frame(3, "chart-main", (0.8, 1.52, 8.6, 5.2)),
        )
        errors, inventory = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=contract(),
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-only",
                "requiredRoles": ["chart-main"],
                "nativeObjectMinimums": {"charts": 1},
            },
        )
        self.assertEqual(errors, [])
        self.assertEqual(inventory["nativeObjectCounts"]["charts"], 1)
        self.assertEqual(inventory["hierarchyRolesPresent"], ["action-title"])

    def test_detects_geometry_margin_hierarchy_native_and_raster_failures(self) -> None:
        root = slide(
            text_shape(
                2,
                "action-title",
                "类别D形成唯一视觉焦点",
                (0.8, 0.72, 11.733, 0.4),
                zero_margins=False,
            ),
            text_shape(
                3,
                "subtitle",
                "类别D形成唯一视觉焦点，明显高于其他类别",
                (0.8, 0.99, 11.733, 0.24),
            ),
            picture(4, "flattened-slide", (0, 0, 13.333, 7.5)),
        )
        errors, _ = validate_slide_format_contract(
            slide_number=2,
            slide_part="ppt/slides/slide2.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=contract(),
            slide_contract={
                "slide": 2,
                "slideRole": "content",
                "headerMode": "title-only",
                "nativeObjectMinimums": {"charts": 1},
            },
        )
        kinds = {item["kind"] for item in errors}
        self.assertIn("format_forbidden_role_present", kinds)
        self.assertIn("format_role_geometry_drift", kinds)
        self.assertIn("format_role_text_margin_not_zero", kinds)
        self.assertIn("native_object_minimum_not_met", kinds)
        self.assertIn("full_slide_raster_detected", kinds)
        self.assertIn("format_hierarchy_text_redundant", kinds)

    def test_connector_policy_distinguishes_native_from_attached(self) -> None:
        root = slide(
            text_shape(
                2,
                "action-title",
                "流程通过原生连接器形成闭环",
                (0.8, 0.55, 11.733, 0.4),
            ),
            connector(
                3,
                "connector-1",
                start_connected=True,
                end_connected=False,
                arrowhead=False,
            ),
        )
        errors, inventory = validate_slide_format_contract(
            slide_number=5,
            slide_part="ppt/slides/slide5.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=contract(),
            slide_contract={
                "slide": 5,
                "slideRole": "content",
                "headerMode": "title-only",
                "nativeObjectMinimums": {"connectors": 1},
                "connectorPolicy": {
                    "requireAttachedBothEnds": True,
                    "requireArrowhead": True,
                },
            },
        )
        kinds = {item["kind"] for item in errors}
        self.assertIn("native_connector_not_attached_both_ends", kinds)
        self.assertIn("native_connector_arrowhead_missing", kinds)
        self.assertEqual(
            inventory["connectorEditability"]["attachedBothEnds"],
            0,
        )

    def test_unclassified_bottom_text_cannot_hide_takeaway_box(self) -> None:
        root = slide(
            text_shape(
                2,
                "action-title",
                "标题已经完整表达本页结论",
                (0.8, 0.55, 11.733, 0.4),
            ),
            text_shape(
                3,
                "TextBox 17",
                "所以我们应立即行动",
                (0.8, 6.35, 11.0, 0.45),
            ),
        )
        errors, _ = validate_slide_format_contract(
            slide_number=4,
            slide_part="ppt/slides/slide4.xml",
            slide_root=root,
            slide_width_emu=emu(13.333),
            slide_height_emu=emu(7.5),
            contract=contract(),
            slide_contract={
                "slide": 4,
                "slideRole": "content",
                "headerMode": "title-only",
            },
        )
        self.assertIn(
            "format_bottom_text_role_unclassified",
            {item["kind"] for item in errors},
        )

    def test_standard_notes_placeholder_is_not_treated_as_user_object(self) -> None:
        placeholder = ET.fromstring(
            f"""<p:sp xmlns:p="{P_NS}">
  <p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder 2"/><p:cNvSpPr/><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>
</p:sp>"""
        )
        user_object = ET.fromstring(
            f"""<p:sp xmlns:p="{P_NS}">
  <p:nvSpPr><p:cNvPr id="3" name="Reviewer note"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
</p:sp>"""
        )
        self.assertTrue(
            is_notes_placeholder(
                "ppt/notesSlides/notesSlide1.xml",
                placeholder,
            )
        )
        self.assertFalse(
            is_notes_placeholder(
                "ppt/notesSlides/notesSlide1.xml",
                user_object,
            )
        )
        self.assertFalse(
            is_notes_placeholder(
                "ppt/slides/slide1.xml",
                placeholder,
            )
        )

    def test_audit_ignores_system_notes_lock_but_not_user_notes_lock(self) -> None:
        def notes_payload(include_user_object: bool) -> bytes:
            user_object = (
                f"""<p:sp>
  <p:nvSpPr><p:cNvPr id="3" name="Reviewer note"/><p:cNvSpPr><a:spLocks noMove="1"/></p:cNvSpPr><p:nvPr/></p:nvSpPr>
  <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Review</a:t></a:r></a:p></p:txBody>
</p:sp>"""
                if include_user_object
                else ""
            )
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:notes xmlns:p="{P_NS}" xmlns:a="{A_NS}">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr>
      <p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>Notes</a:t></a:r></a:p></p:txBody>
    </p:sp>
    {user_object}
  </p:spTree></p:cSld>
</p:notes>""".encode()

        with tempfile.TemporaryDirectory() as temporary_directory:
            system_only = Path(temporary_directory) / "system-only.pptx"
            with zipfile.ZipFile(system_only, "w") as archive:
                archive.writestr(
                    "ppt/notesSlides/notesSlide1.xml",
                    notes_payload(False),
                )
            with_user = Path(temporary_directory) / "with-user.pptx"
            with zipfile.ZipFile(with_user, "w") as archive:
                archive.writestr(
                    "ppt/notesSlides/notesSlide1.xml",
                    notes_payload(True),
                )
            system_report = audit(
                str(system_only),
                theme_policy="preserve",
                font_policy="preserve",
            )
            user_report = audit(
                str(with_user),
                theme_policy="preserve",
                font_policy="preserve",
            )

        system_lock_parts = [
            item["part"]
            for item in system_report["errors"]
            if item["kind"] == "native_editability_locks"
        ]
        user_lock_findings = [
            item
            for item in user_report["errors"]
            if item["kind"] == "native_editability_locks"
        ]
        self.assertNotIn(
            "ppt/notesSlides/notesSlide1.xml",
            system_lock_parts,
        )
        self.assertEqual(len(user_lock_findings), 1)
        self.assertEqual(
            user_lock_findings[0]["locks"][0]["object"],
            "Reviewer note",
        )

    def test_contract_loader_blocks_invalid_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "invalid.json"
            path.write_text(
                '{"schemaVersion":"wrong","slides":[]}',
                encoding="utf-8",
            )
            payload, findings = load_format_contract(str(path))
        self.assertEqual(payload["schemaVersion"], "wrong")
        kinds = {item["kind"] for item in findings}
        self.assertIn("format_contract_schema_invalid", kinds)
        self.assertIn("format_contract_slides_missing", kinds)


if __name__ == "__main__":
    unittest.main()
