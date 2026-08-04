#!/usr/bin/env python3
"""Validate that certified-layout slots were rendered at their locked geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


SCHEMA_VERSION = "ksib-layout-fidelity-gate/1.0"
PLAN_SCHEMA_VERSION = "ksib-render-plan/1.0"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CHROME_PREFIXES = (
    "header-",
    "action-title",
    "subtitle",
    "title-divider",
    "footer-",
    "source-",
    "page-number",
    "takeaway",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read {label}: {error}") from error


def xml_root(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        return ET.fromstring(archive.read(name))
    except (KeyError, ET.ParseError) as error:
        raise RuntimeError(f"Cannot parse {name}: {error}") from error


def resolve_zip_target(source: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target).lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source), target)).lstrip("/")


def presentation_order(archive: zipfile.ZipFile) -> list[str]:
    presentation = xml_root(archive, "ppt/presentation.xml")
    relationships = xml_root(archive, "ppt/_rels/presentation.xml.rels")
    targets = {
        item.get("Id"): resolve_zip_target("ppt/presentation.xml", item.get("Target") or "")
        for item in relationships.iter(f"{{{REL_NS}}}Relationship")
        if item.get("Id") and (item.get("Type") or "").endswith("/slide")
    }
    order = []
    for item in presentation.iter(f"{{{P_NS}}}sldId"):
        target = targets.get(item.get(f"{{{R_NS}}}id"))
        if target:
            order.append(target)
    return order


def child(element: ET.Element, path: str) -> ET.Element | None:
    return element.find(path)


def object_name(element: ET.Element, kind: str) -> str:
    paths = {
        "shape": f"./{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr",
        "graphicFrame": f"./{{{P_NS}}}nvGraphicFramePr/{{{P_NS}}}cNvPr",
        "group": f"./{{{P_NS}}}nvGrpSpPr/{{{P_NS}}}cNvPr",
        "picture": f"./{{{P_NS}}}nvPicPr/{{{P_NS}}}cNvPr",
        "connector": f"./{{{P_NS}}}nvCxnSpPr/{{{P_NS}}}cNvPr",
    }
    metadata = child(element, paths[kind])
    return metadata.get("name", "") if metadata is not None else ""


def object_geometry(element: ET.Element, kind: str) -> dict[str, int] | None:
    if kind == "graphicFrame":
        transform = child(element, f"./{{{P_NS}}}xfrm")
    elif kind == "group":
        transform = child(element, f"./{{{P_NS}}}grpSpPr/{{{A_NS}}}xfrm")
    else:
        transform = child(element, f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
    if transform is None:
        return None
    offset = child(transform, f"./{{{A_NS}}}off")
    extent = child(transform, f"./{{{A_NS}}}ext")
    if offset is None or extent is None:
        return None
    try:
        return {
            "x": int(offset.get("x", "0")),
            "y": int(offset.get("y", "0")),
            "w": int(extent.get("cx", "0")),
            "h": int(extent.get("cy", "0")),
        }
    except ValueError:
        return None


def text_font_sizes(element: ET.Element) -> list[float]:
    values: list[float] = []
    for tag in ("rPr", "defRPr", "endParaRPr"):
        for node in element.iter(f"{{{A_NS}}}{tag}"):
            raw = node.get("sz")
            if raw and raw.isdigit():
                values.append(int(raw) / 100)
    return values


def visible_paragraph_count(element: ET.Element) -> int:
    return sum(
        1
        for paragraph in element.iter(f"{{{A_NS}}}p")
        if any((node.text or "").strip() for node in paragraph.iter(f"{{{A_NS}}}t"))
    )


def slide_objects(root: ET.Element) -> list[dict[str, Any]]:
    tree = root.find(f".//{{{P_NS}}}spTree")
    if tree is None:
        return []
    tag_kinds = {
        f"{{{P_NS}}}sp": "shape",
        f"{{{P_NS}}}graphicFrame": "graphicFrame",
        f"{{{P_NS}}}grpSp": "group",
        f"{{{P_NS}}}pic": "picture",
        f"{{{P_NS}}}cxnSp": "connector",
    }
    output = []
    for element in list(tree):
        kind = tag_kinds.get(element.tag)
        if not kind:
            continue
        output.append(
            {
                "name": object_name(element, kind),
                "type": kind,
                "geometry": object_geometry(element, kind),
                "fontSizesPt": text_font_sizes(element),
                "paragraphCount": visible_paragraph_count(element),
            }
        )
    return output


def intersects(left: dict[str, int], right: dict[str, int]) -> bool:
    return not (
        left["x"] + left["w"] <= right["x"]
        or right["x"] + right["w"] <= left["x"]
        or left["y"] + left["h"] <= right["y"]
        or right["y"] + right["h"] <= left["y"]
    )


def expected_geometry(payload: dict[str, Any]) -> dict[str, int]:
    return {key: int(payload[f"{key}Emu"]) for key in ("x", "y", "w", "h")}


def add_error(errors: list[dict[str, Any]], rule: str, detail: str, **extra: Any) -> None:
    errors.append({"rule": rule, "detail": detail, **extra})


def compare_geometry(actual: dict[str, int] | None, expected: dict[str, int], tolerance: int) -> list[str]:
    if actual is None:
        return ["missing geometry"]
    return [
        f"{key}: expected {expected[key]}, actual {actual[key]}"
        for key in ("x", "y", "w", "h")
        if abs(actual[key] - expected[key]) > tolerance
    ]


def validate_slide(
    slide_plan: dict[str, Any],
    objects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    slide_number = slide_plan["slide"]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in objects:
        if item["name"]:
            by_name.setdefault(item["name"], []).append(item)
    expected_names = {item["objectName"] for item in slide_plan["expectedObjects"]}
    body = expected_geometry(slide_plan["bodyRegion"])
    for expected in slide_plan["expectedObjects"]:
        name = expected["objectName"]
        candidates = by_name.get(name, [])
        if len(candidates) != 1:
            add_error(
                errors,
                "certified_object_missing_or_duplicate",
                f"{name} must exist exactly once; found {len(candidates)}",
                slide=slide_number,
                objectName=name,
                slotId=expected["slotId"],
            )
            continue
        actual = candidates[0]
        if actual["type"] not in expected["allowedObjectTypes"]:
            add_error(
                errors,
                "certified_object_type_mismatch",
                f"{name} must be one of {expected['allowedObjectTypes']}; found {actual['type']}",
                slide=slide_number,
                objectName=name,
            )
        geometry_issues = compare_geometry(
            actual["geometry"],
            expected_geometry(expected["geometry"]),
            int(expected.get("geometryToleranceEmu", 0)),
        )
        if geometry_issues:
            add_error(
                errors,
                "certified_geometry_mismatch",
                "; ".join(geometry_issues),
                slide=slide_number,
                objectName=name,
                slotId=expected["slotId"],
            )
        font_size = expected.get("expectedFontSizePt")
        if font_size is not None:
            if not actual["fontSizesPt"]:
                add_error(
                    errors,
                    "certified_typography_unresolved",
                    f"{name} has no explicit run/default font size",
                    slide=slide_number,
                    objectName=name,
                )
            elif any(abs(value - float(font_size)) > 0.01 for value in actual["fontSizesPt"]):
                add_error(
                    errors,
                    "certified_typography_role_mismatch",
                    f"{name} must use {font_size} pt; found {actual['fontSizesPt']}",
                    slide=slide_number,
                    objectName=name,
                    typographyRole=expected.get("typographyRole"),
                )
        item_count = expected.get("itemCount")
        if item_count is not None and actual["paragraphCount"] != item_count:
            add_error(
                errors,
                "certified_item_count_mismatch",
                f"{name} must render {item_count} non-empty paragraphs; found {actual['paragraphCount']}",
                slide=slide_number,
                objectName=name,
            )
    for actual in objects:
        geometry = actual["geometry"]
        name = actual["name"]
        if not geometry or not intersects(geometry, body):
            continue
        if name in expected_names or any(name.startswith(prefix) for prefix in CHROME_PREFIXES):
            continue
        add_error(
            errors,
            "uncertified_body_object",
            f"Body object is not declared by the locked render plan: {name or '(unnamed)'}",
            slide=slide_number,
            objectName=name or None,
            objectType=actual["type"],
        )
    return errors, warnings


def validate(
    pptx_path: Path,
    plan_path: Path,
    registry_path: Path,
    components_path: Path,
    typography_path: Path,
    master_path: Path,
    design_tokens_path: Path,
) -> dict[str, Any]:
    plan_payload = plan_path.read_bytes()
    plan = json.loads(plan_payload)
    if plan.get("schemaVersion") != PLAN_SCHEMA_VERSION:
        raise RuntimeError(f"Render plan schema must be {PLAN_SCHEMA_VERSION}")
    source_paths = {
        "registrySha256": registry_path,
        "componentsSha256": components_path,
        "typographySha256": typography_path,
        "masterSha256": master_path,
        "designTokensSha256": design_tokens_path,
    }
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for key, source in source_paths.items():
        expected = plan.get("sourceHashes", {}).get(key)
        actual = sha256_file(source)
        if expected != actual:
            add_error(errors, "render_plan_source_hash_mismatch", f"{key} does not match current source", expected=expected, actual=actual)
    master_contract = read_json(master_path, "PowerPoint master contract")
    design_tokens = read_json(design_tokens_path, "design tokens")
    if plan.get("masterTemplateVersion") != master_contract.get("templateVersion"):
        add_error(errors, "render_plan_master_version_mismatch", "Render plan masterTemplateVersion does not match the current master contract", expected=master_contract.get("templateVersion"), actual=plan.get("masterTemplateVersion"))
    if plan.get("designTokensVersion") != design_tokens.get("schemaVersion"):
        add_error(errors, "render_plan_design_tokens_version_mismatch", "Render plan designTokensVersion does not match current design tokens", expected=design_tokens.get("schemaVersion"), actual=plan.get("designTokensVersion"))
    if plan.get("rules", {}).get("llmMayGenerateGeometry") is not False:
        add_error(errors, "render_plan_allows_free_geometry", "Certified render plan must set llmMayGenerateGeometry=false")
    if plan.get("rules", {}).get("freeformBodyObjectsAllowed") is not False:
        add_error(errors, "render_plan_allows_freeform_body", "Certified render plan must set freeformBodyObjectsAllowed=false")
    results = []
    try:
        with zipfile.ZipFile(pptx_path) as archive:
            order = presentation_order(archive)
            for slide_plan in plan.get("slides", []):
                number = int(slide_plan.get("slide", 0))
                if number < 1 or number > len(order):
                    slide_errors = [{"rule": "render_plan_slide_missing", "detail": f"Slide {number} is outside PPTX range", "slide": number}]
                    slide_warnings: list[dict[str, Any]] = []
                else:
                    root = xml_root(archive, order[number - 1])
                    slide_errors, slide_warnings = validate_slide(slide_plan, slide_objects(root))
                errors.extend(slide_errors)
                warnings.extend(slide_warnings)
                results.append(
                    {
                        "slide": number,
                        "storylineId": slide_plan.get("storylineId"),
                        "layoutId": slide_plan.get("layoutId"),
                        "variantId": slide_plan.get("variantId"),
                        "passed": not slide_errors,
                        "errorCount": len(slide_errors),
                    }
                )
    except (OSError, zipfile.BadZipFile, RuntimeError, ET.ParseError) as error:
        add_error(errors, "pptx_unreadable", str(error))
    validator_path = Path(__file__).resolve()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "validatorSha256": sha256_file(validator_path),
        "passed": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "inputHashes": {
            "pptxSha256": sha256_file(pptx_path),
            "renderPlanSha256": sha256_bytes(plan_payload),
            "registrySha256": sha256_file(registry_path),
            "componentsSha256": sha256_file(components_path),
            "typographySha256": sha256_file(typography_path),
            "masterSha256": sha256_file(master_path),
            "designTokensSha256": sha256_file(design_tokens_path),
        },
        "slideCount": len(results),
        "results": results,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pptx", type=Path)
    parser.add_argument("--render-plan", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--components", type=Path)
    parser.add_argument("--typography", type=Path)
    parser.add_argument("--master", type=Path)
    parser.add_argument("--design-tokens", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.self_test:
        from test_layout_fidelity import run_embedded_self_test

        run_embedded_self_test()
        return 0
    script_dir = Path(__file__).resolve().parent
    references = script_dir.parent / "references"
    if not args.pptx or not args.render_plan:
        raise RuntimeError("--pptx and --render-plan are required")
    report = validate(
        args.pptx.resolve(),
        args.render_plan.resolve(),
        (args.registry or references / "certified-layout-registry.json").resolve(),
        (args.components or references / "component-registry.json").resolve(),
        (args.typography or references / "typography-roles.json").resolve(),
        (args.master or references / "powerpoint-master-contract.json").resolve(),
        (args.design_tokens or references / "design-tokens.json").resolve(),
    )
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (RuntimeError, OSError, json.JSONDecodeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
