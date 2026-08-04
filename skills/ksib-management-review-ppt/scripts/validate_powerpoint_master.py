#!/usr/bin/env python3
"""Validate the KSIB PowerPoint master and editable layout library."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

EMU_PER_INCH = 914400
VALID_SLIDE_LAYOUT_TYPES = {
    "title", "tx", "twoColTx", "tbl", "txAndChart", "chartAndTx", "dgm", "chart",
    "txAndClipArt", "clipArtAndTx", "titleOnly", "blank", "txAndObj", "objAndTx",
    "objOnly", "obj", "txAndMedia", "mediaAndTx", "objOverTx", "txOverObj",
    "txAndTwoObj", "twoObjAndTx", "twoObjOverTx", "fourObj", "vertTx",
    "clipArtAndVertTx", "vertTitleAndTx", "vertTitleAndTxOverChart", "twoObj",
    "objAndTwoObj", "twoObjAndObj", "cust", "secHead", "twoTxTwoObj", "objTx", "picTx",
}
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}


def parse_args() -> argparse.Namespace:
    skill_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=skill_root / "references" / "powerpoint-master-contract.json")
    parser.add_argument("--tokens", type=Path, default=skill_root / "references" / "design-tokens.json")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def read_xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(archive.read(name))


def shape_map(layout: ET.Element) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for shape in layout.findall(".//p:sp", NS):
        props = shape.find("./p:nvSpPr/p:cNvPr", NS)
        if props is not None and props.get("name"):
            result[props.get("name", "")] = shape
    return result


def geometry(shape: ET.Element) -> dict[str, int] | None:
    transform = shape.find("./p:spPr/a:xfrm", NS)
    if transform is None:
        return None
    offset = transform.find("a:off", NS)
    extent = transform.find("a:ext", NS)
    if offset is None or extent is None:
        return None
    return {
        "x": int(offset.get("x", "0")),
        "y": int(offset.get("y", "0")),
        "w": int(extent.get("cx", "0")),
        "h": int(extent.get("cy", "0")),
    }


def expected_emu(spec: dict[str, float]) -> dict[str, int]:
    return {key: round(float(spec[key]) * EMU_PER_INCH) for key in ("x", "y", "w", "h")}


def validate_package(path: Path, *, is_template: bool, contract: dict, tokens: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        content_types = read_xml(archive, "[Content_Types].xml")
        main_types = [node.get("ContentType", "") for node in content_types.findall("ct:Override", NS) if node.get("PartName") == "/ppt/presentation.xml"]
        expected_main = "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml" if is_template else "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
        if main_types != [expected_main]:
            errors.append(f"presentation content type is {main_types!r}; expected {expected_main}")

        slide_names = sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        expected_slides = 0 if is_template else len(contract["profiles"])
        if len(slide_names) != expected_slides:
            errors.append(f"slide count is {len(slide_names)}; expected {expected_slides}")

        presentation = read_xml(archive, "ppt/presentation.xml")
        presentation_rels = read_xml(archive, "ppt/_rels/presentation.xml.rels")
        referenced_relationship_ids = {
            value
            for node in presentation.iter()
            for attribute, value in node.attrib.items()
            if attribute == f"{{{NS['r']}}}id"
        }
        available_relationship_ids = {
            node.get("Id", "") for node in presentation_rels.findall("rel:Relationship", NS)
        }
        missing_relationship_ids = sorted(referenced_relationship_ids - available_relationship_ids)
        if missing_relationship_ids:
            errors.append(f"presentation references missing relationships {missing_relationship_ids}")

        layout_names = sorted(name for name in names if name.startswith("ppt/slideLayouts/slideLayout") and name.endswith(".xml"))
        expected_layouts = len(contract["profiles"]) + 1
        if len(layout_names) != expected_layouts:
            errors.append(f"layout part count is {len(layout_names)}; expected {expected_layouts}")

        master = read_xml(archive, "ppt/slideMasters/slideMaster1.xml")
        master_layouts = master.findall("./p:sldLayoutIdLst/p:sldLayoutId", NS)
        if len(master_layouts) != expected_layouts:
            errors.append(f"master layout relationship count is {len(master_layouts)}; expected {expected_layouts}")

        for profile_index, profile in enumerate(contract["profiles"]):
            part = f"ppt/slideLayouts/slideLayout{profile_index + 2}.xml"
            if part not in names:
                errors.append(f"missing {part}")
                continue
            layout = read_xml(archive, part)
            layout_type = layout.get("type")
            if layout_type not in VALID_SLIDE_LAYOUT_TYPES:
                errors.append(f"{part} uses invalid OOXML slide layout type {layout_type!r}")
            if layout_type != profile["layoutType"]:
                errors.append(f"{part} type is {layout_type!r}; expected {profile['layoutType']!r}")
            if "content-body" in profile["placeholders"] and layout_type != "cust":
                errors.append(
                    f"{part} exposes a content-body placeholder but uses {layout_type!r}; "
                    "PowerPoint-safe body-bearing KSIB layouts must use the custom layout type 'cust'"
                )
            common = layout.find("./p:cSld", NS)
            if common is None or common.get("name") != profile["layoutName"]:
                errors.append(f"{part} name does not match {profile['layoutName']}")
            shapes = shape_map(layout)
            header_placeholders = layout.findall(".//p:ph[@type='hdr']", NS)
            if header_placeholders:
                errors.append(
                    f"{part} contains a header placeholder; KSIB header chrome must remain a fixed "
                    "layout shape because promoted hdr placeholders trigger PowerPoint repair"
                )
            for placeholder_name in profile["placeholders"]:
                shape = shapes.get(placeholder_name)
                placeholder = shape.find("./p:nvSpPr/p:nvPr/p:ph", NS) if shape is not None else None
                if placeholder is None:
                    errors.append(f"{profile['profileId']} missing placeholder {placeholder_name}")
            if profile["profileId"] in {"navigator", "content-title-only", "content-title-subtitle", "appendix-title-only", "appendix-title-subtitle"}:
                page = shapes.get("page-number")
                if page is None or page.find(".//a:fld[@type='slidenum']", NS) is None:
                    errors.append(f"{profile['profileId']} page number is not a dynamic slidenum field")

        content_profile_index = next(index for index, item in enumerate(contract["profiles"]) if item["profileId"] == "content-title-only")
        content_layout = read_xml(archive, f"ppt/slideLayouts/slideLayout{content_profile_index + 2}.xml")
        content_shapes = shape_map(content_layout)
        for role, spec in tokens["roleGeometry"].items():
            shape = content_shapes.get(role)
            if shape is None:
                errors.append(f"content-title-only is missing fixed role {role}")
                continue
            actual = geometry(shape)
            expected = expected_emu(spec)
            if actual != expected:
                errors.append(f"{role} geometry is {actual}; expected {expected}")

        theme_candidates = sorted(name for name in names if name.startswith("ppt/slideMasters/theme/") and name.endswith(".xml"))
        if not theme_candidates:
            errors.append("missing master theme")
        else:
            theme = read_xml(archive, theme_candidates[0])
            scheme = theme.find(".//a:fontScheme", NS)
            if scheme is None or scheme.get("name") != tokens["theme"]["fontSchemeName"]:
                errors.append("theme font scheme name does not match design tokens")
            font_faces = {node.get("typeface") for node in theme.findall(".//a:fontScheme//a:latin", NS) + theme.findall(".//a:fontScheme//a:ea", NS) + theme.findall(".//a:fontScheme//a:cs", NS)}
            if font_faces != {tokens["type"]["primaryTypeface"]}:
                errors.append(f"theme font faces are {sorted(font_faces)}")

        if any("linzhe" in name.lower() for name in names):
            warnings.append("package contains a path with personal naming")

    return {
        "path": str(path),
        "kind": "potx" if is_template else "pptx",
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "slideCount": expected_slides,
        "customProfileCount": len(contract["profiles"]),
        "layoutPartCount": expected_layouts,
    }


def main() -> int:
    args = parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    tokens = json.loads(args.tokens.read_text(encoding="utf-8"))
    skill_root = args.contract.parent.parent
    template = args.template or skill_root / contract["templateFile"]
    library = args.library or skill_root / contract["layoutLibraryFile"]
    results = [
        validate_package(template, is_template=True, contract=contract, tokens=tokens),
        validate_package(library, is_template=False, contract=contract, tokens=tokens),
    ]
    report = {
        "schemaVersion": "ksib-powerpoint-master-gate/1.0",
        "templateVersion": contract["templateVersion"],
        "passed": all(item["passed"] for item in results),
        "results": results,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
