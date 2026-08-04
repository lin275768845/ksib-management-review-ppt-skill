#!/usr/bin/env python3
"""Extract final OOXML object colors from a PPTX into a deterministic inventory.

The inventory is deliberately derived from the final archive.  It gives the
Theme Usage validator a stable binding surface that cannot be satisfied by a
renderer declaration alone.
"""

from __future__ import annotations

import argparse
import collections
import colorsys
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from pptx_semantic_fingerprint import (
    A_NS,
    COLOR_TAGS,
    P_NS,
    R_NS,
    SEMANTIC_OBJECT_TAGS,
    SEMANTIC_RELATIONSHIP_SUFFIXES,
    FingerprintError,
    color_role,
    color_transforms,
    color_value,
    extract_text_color_bindings,
    first_related_part,
    iter_semantic,
    local_name,
    normalize_text,
    object_identity,
    object_relationship_ids,
    read_xml,
    relationship_record_map,
    relationship_semantic_type,
    sha256_file,
    slide_parts_in_order,
)


SCHEMA_VERSION = "ksib-pptx-color-inventory/1.0"
EXTRACTOR_PATH = Path(__file__).resolve()
SCHEME_ALIASES = {"tx1", "bg1", "tx2", "bg2"}
PRESET_COLORS = {
    "black": "000000", "white": "FFFFFF", "red": "FF0000",
    "green": "008000", "blue": "0000FF", "yellow": "FFFF00",
    "orange": "FFA500", "purple": "800080", "gray": "808080",
    "grey": "808080", "ltGray": "D3D3D3", "dkGray": "A9A9A9",
    "cyan": "00FFFF", "magenta": "FF00FF", "navy": "000080",
    "teal": "008080", "maroon": "800000", "olive": "808000",
    "silver": "C0C0C0", "lime": "00FF00", "aqua": "00FFFF",
    "fuchsia": "FF00FF",
}
SUPPORTED_TRANSFORMS = {
    "alpha", "alphaMod", "alphaOff", "tint", "shade", "lumMod",
    "lumOff", "satMod", "satOff", "hueMod", "hueOff", "comp",
    "inv", "gray", "gamma", "invGamma",
}


class ExtractionError(RuntimeError):
    """Raised when the final PPTX cannot be inspected safely."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, value))


def as_unit(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value or 0) / 100000.0
    except ValueError:
        return default


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(clamp(channel) * 255):02X}" for channel in rgb)


def hex_to_rgb(value: str) -> tuple[float, float, float] | None:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6:
        return None
    try:
        return tuple(int(normalized[index:index + 2], 16) / 255 for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def gamma_channel(value: float) -> float:
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def inverse_gamma_channel(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def apply_transforms(
    rgb: tuple[float, float, float],
    transforms: list[dict[str, Any]],
) -> tuple[tuple[float, float, float] | None, float, list[str]]:
    current = rgb
    alpha = 1.0
    unsupported: list[str] = []
    for transform in transforms:
        name = transform.get("name", "")
        attrs = transform.get("attributes", {})
        if name not in SUPPORTED_TRANSFORMS:
            unsupported.append(name or "unknown")
            continue
        amount = as_unit(attrs.get("val"))
        if name == "alpha":
            alpha = amount
        elif name == "alphaMod":
            alpha *= amount
        elif name == "alphaOff":
            alpha += amount
        elif name == "tint":
            current = tuple(channel + (1 - channel) * amount for channel in current)  # type: ignore[assignment]
        elif name == "shade":
            current = tuple(channel * amount for channel in current)  # type: ignore[assignment]
        elif name in {"lumMod", "lumOff", "satMod", "satOff", "hueMod", "hueOff", "comp"}:
            hue, lum, sat = colorsys.rgb_to_hls(*current)
            if name == "lumMod":
                lum *= amount
            elif name == "lumOff":
                lum += amount
            elif name == "satMod":
                sat *= amount
            elif name == "satOff":
                sat += amount
            elif name == "hueMod":
                hue *= amount
            elif name == "hueOff":
                try:
                    hue += float(attrs.get("val", 0)) / 21600000.0
                except ValueError:
                    unsupported.append(name)
            elif name == "comp":
                hue += 0.5
            current = colorsys.hls_to_rgb(hue % 1.0, clamp(lum), clamp(sat))
        elif name == "inv":
            current = tuple(1 - channel for channel in current)  # type: ignore[assignment]
        elif name == "gray":
            gray = 0.2126 * current[0] + 0.7152 * current[1] + 0.0722 * current[2]
            current = (gray, gray, gray)
        elif name == "gamma":
            current = tuple(gamma_channel(channel) for channel in current)  # type: ignore[assignment]
        elif name == "invGamma":
            current = tuple(inverse_gamma_channel(channel) for channel in current)  # type: ignore[assignment]
    if unsupported:
        return None, clamp(alpha), sorted(set(unsupported))
    return tuple(clamp(channel) for channel in current), clamp(alpha), []


def first_color_node(node: ET.Element) -> ET.Element | None:
    return next((item for item in iter_semantic(node) if local_name(item.tag) in COLOR_TAGS), None)


def theme_context(package: zipfile.ZipFile, slide_part: str) -> dict[str, Any]:
    layout_part = first_related_part(package, slide_part, "/slideLayout")
    master_part = first_related_part(package, layout_part, "/slideMaster") if layout_part else None
    theme_part = first_related_part(package, master_part, "/theme") if master_part else None
    scheme: dict[str, ET.Element] = {}
    if theme_part:
        theme_root = read_xml(package, theme_part)
        clr_scheme = theme_root.find(f".//{{{A_NS}}}clrScheme")
        if clr_scheme is not None:
            for slot in list(clr_scheme):
                color = first_color_node(slot)
                if color is not None:
                    scheme[local_name(slot.tag)] = color
    mapping: dict[str, str] = {}
    if master_part:
        master_root = read_xml(package, master_part)
        clr_map = master_root.find(f".//{{{P_NS}}}clrMap")
        if clr_map is not None:
            mapping.update(clr_map.attrib)
    if layout_part:
        layout_root = read_xml(package, layout_part)
        override = layout_root.find(f".//{{{P_NS}}}clrMapOvr")
        if override is not None:
            override_mapping = next((child for child in list(override) if local_name(child.tag) == "overrideClrMapping"), None)
            if override_mapping is not None:
                mapping.update(override_mapping.attrib)
    return {
        "layoutPart": layout_part,
        "masterPart": master_part,
        "themePart": theme_part,
        "scheme": scheme,
        "mapping": mapping,
    }


def resolve_color_node(
    node: ET.Element,
    context: dict[str, Any],
    stack: tuple[str, ...] = (),
) -> dict[str, Any]:
    tag = local_name(node.tag)
    source = color_value(node)
    base: tuple[float, float, float] | None = None
    resolution_notes: list[str] = []
    if tag == "srgbClr":
        base = hex_to_rgb(source)
    elif tag == "sysClr":
        base = hex_to_rgb(node.get("lastClr") or "")
        if base is None:
            resolution_notes.append("sysClr缺少lastClr")
    elif tag == "scrgbClr":
        try:
            base = tuple(clamp(float(node.get(key, "0")) / 100000) for key in ("r", "g", "b"))  # type: ignore[assignment]
        except ValueError:
            base = None
    elif tag == "hslClr":
        try:
            hue = (float(node.get("hue", "0")) / 21600000) % 1.0
            sat = clamp(float(node.get("sat", "0")) / 100000)
            lum = clamp(float(node.get("lum", "0")) / 100000)
            base = colorsys.hls_to_rgb(hue, lum, sat)
        except ValueError:
            base = None
    elif tag == "prstClr":
        base = hex_to_rgb(PRESET_COLORS.get(source, ""))
        if base is None:
            resolution_notes.append(f"不支持的prstClr:{source}")
    elif tag == "schemeClr":
        slot = context["mapping"].get(source, source) if source in SCHEME_ALIASES else source
        if slot == "phClr":
            resolution_notes.append("phClr依赖格式样式占位色")
        elif slot in stack:
            resolution_notes.append(f"主题色循环引用:{slot}")
        else:
            theme_node = context["scheme"].get(slot)
            if theme_node is None:
                resolution_notes.append(f"主题色槽不存在:{slot}")
            else:
                resolved_theme = resolve_color_node(theme_node, context, (*stack, slot))
                base = hex_to_rgb(resolved_theme.get("resolvedHex") or "")
                resolution_notes.extend(resolved_theme.get("resolutionNotes", []))
    else:
        resolution_notes.append(f"不支持的颜色类型:{tag}")

    transforms = color_transforms(node)
    transformed: tuple[float, float, float] | None = None
    alpha = 1.0
    unsupported: list[str] = []
    if base is not None:
        transformed, alpha, unsupported = apply_transforms(base, transforms)
    if unsupported:
        resolution_notes.append("不支持的颜色变换:" + ",".join(unsupported))
    if base is None and not resolution_notes:
        resolution_notes.append("颜色值无法解析")
    return {
        "colorType": tag,
        "sourceValue": source,
        "transforms": transforms,
        "resolvedHex": rgb_to_hex(transformed) if transformed is not None else None,
        "alpha": round(alpha, 6),
        "visible": alpha > 0,
        "resolutionStatus": "resolved" if transformed is not None else "unresolved",
        "resolutionNotes": resolution_notes,
    }


def semantic_paths(root: ET.Element) -> Iterable[tuple[ET.Element, tuple[str, ...], tuple[str, ...]]]:
    def visit(node: ET.Element, path: tuple[str, ...], ancestors: tuple[str, ...]):
        yield node, path, ancestors
        ordinals: collections.Counter[str] = collections.Counter()
        for child in list(node):
            tag = local_name(child.tag)
            if tag == "extLst":
                continue
            ordinal = ordinals[tag]
            ordinals[tag] += 1
            yield from visit(child, (*path, f"{tag}[{ordinal}]"), (*ancestors, local_name(node.tag)))
    yield from visit(root, (f"{local_name(root.tag)}[0]",), ())


def extract_bindings(
    root: ET.Element,
    object_ref: str,
    source_part: str,
    source_role: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    ordinal = 0
    for node, xml_path, ancestors in semantic_paths(root):
        if local_name(node.tag) not in COLOR_TAGS:
            continue
        ordinal += 1
        resolved = resolve_color_node(node, context)
        property_name = color_role(list(ancestors))
        binding_seed = f"{object_ref}|{source_role}|{'/'.join(xml_path)}|{ordinal}"
        bindings.append({
            "bindingRef": f"color:{sha256_text(binding_seed)[:20]}",
            "sourcePart": source_part,
            "sourceRole": source_role,
            "xmlPath": "/".join(xml_path),
            "property": property_name,
            **resolved,
        })
    for text_binding in extract_text_color_bindings(root):
        if text_binding.get("color") is not None:
            continue
        implicit_path = f"effectiveText/paragraph[{text_binding['paragraph']}]/segment[{text_binding['segment']}]"
        binding_seed = f"{object_ref}|{source_role}|{implicit_path}|implicit-text"
        bindings.append({
            "bindingRef": f"color:{sha256_text(binding_seed)[:20]}",
            "sourcePart": source_part,
            "sourceRole": source_role,
            "xmlPath": implicit_path,
            "property": "text",
            "colorType": "implicit",
            "sourceValue": "inherited-text-color",
            "transforms": [],
            "resolvedHex": None,
            "alpha": 1.0,
            "visible": True,
            "resolutionStatus": "unresolved",
            "resolutionNotes": ["可见文字依赖对象外的继承颜色；正式交付前必须物化为明确颜色"],
        })
    if source_role.startswith("chart"):
        for series_index, series in enumerate(
            (node for node in iter_semantic(root) if local_name(node.tag) == "ser"),
            start=1,
        ):
            if any(local_name(node.tag) in COLOR_TAGS for node in iter_semantic(series)):
                continue
            implicit_path = f"chartSeries[{series_index}]/automatic-theme-color"
            binding_seed = f"{object_ref}|{source_role}|{implicit_path}|implicit-chart-series"
            bindings.append({
                "bindingRef": f"color:{sha256_text(binding_seed)[:20]}",
                "sourcePart": source_part,
                "sourceRole": source_role,
                "xmlPath": implicit_path,
                "property": "data-fill",
                "colorType": "implicit",
                "sourceValue": "automatic-chart-theme-color",
                "transforms": [],
                "resolvedHex": None,
                "alpha": 1.0,
                "visible": True,
                "resolutionStatus": "unresolved",
                "resolutionNotes": ["图表系列依赖自动主题轮换；正式交付前必须写入明确系列颜色"],
            })
    return bindings


def object_name(node: ET.Element) -> str:
    for candidate in iter_semantic(node):
        if local_name(candidate.tag) == "cNvPr":
            return normalize_text(candidate.get("name") or "")
    return ""


def extract_slide(
    package: zipfile.ZipFile,
    slide_part: str,
    slide_number: int,
) -> dict[str, Any]:
    root = read_xml(package, slide_part)
    context = theme_context(package, slide_part)
    relationships = relationship_record_map(package, slide_part)
    objects = [node for node in iter_semantic(root) if local_name(node.tag) in SEMANTIC_OBJECT_TAGS]
    names = [object_name(node) for node in objects]
    name_counts: collections.Counter[str] = collections.Counter(name for name in names if name)
    records: list[dict[str, Any]] = []
    for index, node in enumerate(objects, start=1):
        identity = object_identity(node, index, name_counts)
        stable = identity["objectKey"].startswith("name:")
        object_ref = f"slide-{slide_number}/{identity['objectKey']}"
        bindings = extract_bindings(node, object_ref, slide_part, "slide-object", context)
        related_counts: collections.Counter[str] = collections.Counter()
        for relationship_id in object_relationship_ids(node):
            relationship = relationships.get(relationship_id)
            if not relationship or not relationship["target"].endswith(".xml"):
                continue
            if not any(relationship["type"].endswith(suffix) for suffix in SEMANTIC_RELATIONSHIP_SUFFIXES):
                continue
            relation_type = relationship_semantic_type(relationship["type"])
            related_counts[relation_type] += 1
            role = f"{relation_type}[{related_counts[relation_type]}]"
            related_root = read_xml(package, relationship["target"])
            bindings.extend(extract_bindings(related_root, object_ref, relationship["target"], role, context))
        records.append({
            "objectRef": object_ref,
            "objectKey": identity["objectKey"],
            "objectName": names[index - 1] or None,
            "objectType": identity["objectType"],
            "stable": stable,
            "colors": sorted(bindings, key=lambda item: item["bindingRef"]),
        })

    # Slide backgrounds sit outside spTree, so expose them as a stable pseudo-object.
    background = root.find(f".//{{{P_NS}}}bg")
    if background is not None:
        object_ref = f"slide-{slide_number}/name:slide-background"
        records.append({
            "objectRef": object_ref,
            "objectKey": "name:slide-background",
            "objectName": "slide-background",
            "objectType": "background",
            "stable": True,
            "colors": extract_bindings(background, object_ref, slide_part, "slide-background", context),
        })
    return {
        "slide": slide_number,
        "part": slide_part,
        "themePart": context["themePart"],
        "objects": sorted(records, key=lambda item: item["objectRef"]),
    }


def extract_inventory(pptx_path: Path) -> dict[str, Any]:
    if not pptx_path.is_file():
        raise ExtractionError(f"PPTX不存在: {pptx_path}")
    try:
        with zipfile.ZipFile(pptx_path) as package:
            slide_parts = slide_parts_in_order(package)
            if not slide_parts:
                raise ExtractionError("PPTX没有可解析的幻灯片")
            slides = [extract_slide(package, part, index) for index, part in enumerate(slide_parts, start=1)]
    except (zipfile.BadZipFile, FingerprintError, ET.ParseError) as error:
        raise ExtractionError(str(error)) from error

    all_objects = [obj for slide in slides for obj in slide["objects"]]
    all_colors = [color for obj in all_objects for color in obj["colors"]]
    visible = [color for color in all_colors if color["visible"]]
    unresolved = [color for color in visible if color["resolutionStatus"] != "resolved"]
    unstable = [obj for obj in all_objects if obj["colors"] and not obj["stable"]]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "pptx": {
            "fileName": pptx_path.name,
            "sha256": sha256_file(pptx_path),
        },
        "extractorSha256": sha256_file(EXTRACTOR_PATH),
        "slideCount": len(slides),
        "summary": {
            "objectCount": len(all_objects),
            "colorBindingCount": len(all_colors),
            "visibleColorBindingCount": len(visible),
            "unresolvedVisibleBindingCount": len(unresolved),
            "unstableColoredObjectCount": len(unstable),
        },
        "slides": slides,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        inventory = extract_inventory(args.pptx.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": True, "output": str(args.output), **inventory["summary"]}, ensure_ascii=False))
        return 0
    except ExtractionError as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
