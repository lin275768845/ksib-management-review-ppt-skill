#!/usr/bin/env python3
"""Create and compare deterministic semantic fingerprints for PPTX files.

The implementation intentionally uses only the Python standard library.  It
reads the OOXML package directly and does not render or rewrite the deck.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import posixpath
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


SCHEMA_VERSION = "ksib-pptx-semantic-fingerprint/3.0"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SEMANTIC_RELATIONSHIP_SUFFIXES = {
    "/chart",
    "/diagramData",
    "/diagramDrawing",
}
SEMANTIC_OBJECT_TAGS = {"sp", "pic", "graphicFrame", "cxnSp"}

COLOR_TAGS = {"srgbClr", "sysClr", "scrgbClr", "hslClr", "prstClr", "schemeClr"}
DIRECT_COLOR_TAGS = COLOR_TAGS - {"schemeClr"}
TYPEFACE_TAGS = {"latin", "ea", "cs", "font"}
FONT_PROPERTY_TAGS = {"rPr", "defRPr", "endParaRPr"}
TEXT_CONTEXT = {"rPr", "defRPr", "endParaRPr", "fontRef"}
LINE_CONTEXT = {"ln", "lnRef"}
BACKGROUND_CONTEXT = {"bgPr", "bgRef"}
EFFECT_CONTEXT = {"effectLst", "effectDag", "effectRef", "outerShdw", "innerShdw", "glow"}

NUMBER_RE = re.compile(
    r"(?:R\$|BRL|US\$|USD|CNY|[¥￥€$])?\s*"
    r"[+\-−]?(?:\d{1,3}(?:[.,\s]\d{3})+|\d+)(?:[.,]\d+)?"
    r"(?:\s*(?:%|pp|p\.p\.|bps?|[xX×]|倍|万|亿|元|雷亚尔|万元|亿元|万人|百万|十亿))?"
)


class FingerprintError(RuntimeError):
    """Raised for invalid or unsupported fingerprint inputs."""


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_hash(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_number(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("−", "-")
    return re.sub(r"\s+", "", normalized)


def resolve_part(source_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def read_xml(package: zipfile.ZipFile, part_name: str) -> ET.Element:
    try:
        payload = package.read(part_name)
    except KeyError as error:
        raise FingerprintError(f"OOXML part missing: {part_name}") from error
    try:
        return ET.fromstring(payload)
    except ET.ParseError as error:
        raise FingerprintError(f"Malformed XML in {part_name}: {error}") from error


def relationship_records(package: zipfile.ZipFile, source_part: str) -> list[dict[str, str]]:
    rels_name = posixpath.join(
        posixpath.dirname(source_part),
        "_rels",
        f"{posixpath.basename(source_part)}.rels",
    )
    if rels_name not in package.namelist():
        return []
    root = read_xml(package, rels_name)
    relationships: list[dict[str, str]] = []
    for relationship in root.findall(f"{{{REL_NS}}}Relationship"):
        if relationship.get("TargetMode") == "External":
            continue
        rel_id = relationship.get("Id")
        target = relationship.get("Target")
        if rel_id and target:
            relationships.append(
                {
                    "id": rel_id,
                    "target": resolve_part(source_part, target),
                    "type": relationship.get("Type", ""),
                }
            )
    return relationships


def relationship_map(package: zipfile.ZipFile, source_part: str) -> dict[str, str]:
    return {
        relationship["id"]: relationship["target"]
        for relationship in relationship_records(package, source_part)
    }


def relationship_record_map(
    package: zipfile.ZipFile,
    source_part: str,
) -> dict[str, dict[str, str]]:
    return {
        relationship["id"]: relationship
        for relationship in relationship_records(package, source_part)
    }


def slide_parts_in_order(package: zipfile.ZipFile) -> list[str]:
    presentation_part = "ppt/presentation.xml"
    presentation = read_xml(package, presentation_part)
    relationships = relationship_map(package, presentation_part)
    slide_parts: list[str] = []
    slide_ids = presentation.find(f"{{{P_NS}}}sldIdLst")
    if slide_ids is None:
        return slide_parts
    for slide_id in slide_ids.findall(f"{{{P_NS}}}sldId"):
        rel_id = slide_id.get(f"{{{R_NS}}}id")
        if not rel_id or rel_id not in relationships:
            raise FingerprintError(f"Unresolved slide relationship: {rel_id}")
        slide_parts.append(relationships[rel_id])
    return slide_parts


def extract_paragraphs(root: ET.Element) -> list[str]:
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{{{A_NS}}}p"):
        value = "".join(node.text or "" for node in paragraph.iter(f"{{{A_NS}}}t"))
        normalized = normalize_text(value)
        if normalized:
            paragraphs.append(normalized)
    return paragraphs


def extract_numbers(paragraphs: Iterable[str]) -> list[str]:
    numbers: list[str] = []
    for paragraph in paragraphs:
        numbers.extend(normalize_number(match.group(0)) for match in NUMBER_RE.finditer(paragraph))
    return sorted(numbers)


def extract_related_data_values(root: ET.Element) -> list[str]:
    values: list[str] = []
    for node in root.iter():
        if local_name(node.tag) != "v":
            continue
        normalized = normalize_text(node.text or "")
        if normalized:
            values.append(normalized)
    return sorted(values)


def direct_child_attribute(
    node: ET.Element,
    child_name: str,
    attribute_name: str,
) -> str | None:
    for child in list(node):
        if local_name(child.tag) == child_name:
            return child.get(attribute_name)
    return None


def related_data_path_segment(node: ET.Element, ordinal: int) -> str:
    """Return a stable path segment for chart/diagram semantic data."""
    tag = local_name(node.tag)
    if tag == "ser":
        series_index = direct_child_attribute(node, "idx", "val")
        series_order = direct_child_attribute(node, "order", "val")
        identifiers = [
            value
            for value in (
                f"idx={series_index}" if series_index is not None else None,
                f"order={series_order}" if series_order is not None else None,
            )
            if value is not None
        ]
        if identifiers:
            return f"{tag}[{','.join(identifiers)}]"
    if tag == "pt" and node.get("idx") is not None:
        return f"{tag}[idx={node.get('idx')}]"
    if tag in {"dLbl", "dPt"}:
        point_index = direct_child_attribute(node, "idx", "val")
        if point_index is not None:
            return f"{tag}[idx={point_index}]"
    return f"{tag}[{ordinal}]"


def extract_related_data_bindings(
    root: ET.Element,
    part_name: str,
) -> list[dict[str, str]]:
    """Bind cached values, formulas and rich labels to series/point paths."""
    bindings: list[dict[str, str]] = []

    def visit(node: ET.Element, path: tuple[str, ...]) -> None:
        tag = local_name(node.tag)
        if tag in {"v", "f", "t"}:
            value = normalize_text(node.text or "")
            if value:
                bindings.append({
                    "part": part_name,
                    "path": "/".join(path),
                    "kind": tag,
                    "value": value,
                })
        child_ordinals: collections.Counter[str] = collections.Counter()
        for child in list(node):
            child_tag = local_name(child.tag)
            ordinal = child_ordinals[child_tag]
            child_ordinals[child_tag] += 1
            visit(
                child,
                (*path, related_data_path_segment(child, ordinal)),
            )

    visit(root, (related_data_path_segment(root, 0),))
    return sorted(bindings, key=canonical_json)


def color_role(ancestors: list[str]) -> str:
    context = set(ancestors)
    if context & TEXT_CONTEXT:
        return "text"
    if context & LINE_CONTEXT:
        return "line"
    if context & BACKGROUND_CONTEXT:
        return "background"
    if context & EFFECT_CONTEXT:
        return "effect"
    if "fillRef" in context:
        return "fill_style"
    if {"solidFill", "gradFill", "pattFill"} & context:
        return "fill"
    return "other"


def color_value(node: ET.Element) -> str:
    tag = local_name(node.tag)
    if tag == "sysClr":
        return node.get("lastClr") or node.get("val") or ""
    if tag == "scrgbClr":
        return ",".join(node.get(key, "") for key in ("r", "g", "b"))
    if tag == "hslClr":
        return ",".join(node.get(key, "") for key in ("hue", "sat", "lum"))
    return node.get("val", "")


def color_transforms(node: ET.Element) -> list[dict[str, Any]]:
    transforms: list[dict[str, Any]] = []
    for child in list(node):
        transforms.append(
            {
                "name": local_name(child.tag),
                "attributes": dict(sorted(child.attrib.items())),
            }
        )
    return transforms


def collect_colors(root: ET.Element) -> dict[str, list[dict[str, Any]]]:
    counter: collections.Counter[str] = collections.Counter()

    def visit(node: ET.Element, ancestors: list[str]) -> None:
        tag = local_name(node.tag)
        if tag in COLOR_TAGS:
            item = {
                "role": color_role(ancestors),
                "kind": "theme" if tag == "schemeClr" else "direct",
                "type": tag,
                "value": color_value(node),
                "transforms": color_transforms(node),
            }
            counter[canonical_json(item)] += 1
        for child in list(node):
            visit(child, [*ancestors, tag])

    visit(root, [])
    direct: list[dict[str, Any]] = []
    theme: list[dict[str, Any]] = []
    for encoded, count in sorted(counter.items()):
        item = json.loads(encoded)
        item["count"] = count
        (theme if item["kind"] == "theme" else direct).append(item)
    return {"direct": direct, "themeReferences": theme}


def collect_fonts(root: ET.Element) -> list[dict[str, Any]]:
    counter: collections.Counter[str] = collections.Counter()

    def visit(node: ET.Element, ancestors: list[str]) -> None:
        tag = local_name(node.tag)
        if tag in TYPEFACE_TAGS and node.get("typeface"):
            item = {
                "kind": "typeface",
                "role": color_role(ancestors),
                "tag": tag,
                "typeface": node.get("typeface"),
                "script": node.get("script"),
            }
            counter[canonical_json(item)] += 1
        if tag in FONT_PROPERTY_TAGS and node.get("sz"):
            item = {
                "kind": "size",
                "role": color_role([*ancestors, tag]),
                "tag": tag,
                "value": node.get("sz"),
            }
            counter[canonical_json(item)] += 1
        if tag == "fontRef" and node.get("idx"):
            item = {
                "kind": "themeFontReference",
                "role": color_role([*ancestors, tag]),
                "value": node.get("idx"),
            }
            counter[canonical_json(item)] += 1
        for child in list(node):
            visit(child, [*ancestors, tag])

    visit(root, [])
    output: list[dict[str, Any]] = []
    for encoded, count in sorted(counter.items()):
        item = json.loads(encoded)
        item["count"] = count
        output.append(item)
    return output


def merge_font_semantics(items: Iterable[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    counter: collections.Counter[str] = collections.Counter()
    for fonts in items:
        for font in fonts:
            item = dict(font)
            count = int(item.pop("count"))
            counter[canonical_json(item)] += count
    output: list[dict[str, Any]] = []
    for encoded, count in sorted(counter.items()):
        item = json.loads(encoded)
        item["count"] = count
        output.append(item)
    return output


def merge_color_semantics(items: Iterable[dict[str, list[dict[str, Any]]]]) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, collections.Counter[str]] = {
        "direct": collections.Counter(),
        "themeReferences": collections.Counter(),
    }
    for item in items:
        for category in merged:
            for color in item[category]:
                value = dict(color)
                count = int(value.pop("count"))
                merged[category][canonical_json(value)] += count
    output: dict[str, list[dict[str, Any]]] = {"direct": [], "themeReferences": []}
    for category, counter in merged.items():
        for encoded, count in sorted(counter.items()):
            value = json.loads(encoded)
            value["count"] = count
            output[category].append(value)
    return output


def visible_color_semantics(
    colors: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Ignore redundant text-format storage; visible text bindings are tracked separately."""
    return {
        category: [
            item
            for item in colors.get(category, [])
            if item.get("role") != "text"
        ]
        for category in ("direct", "themeReferences")
    }


def object_identity(node: ET.Element, fallback_index: int) -> dict[str, str]:
    for candidate in node.iter():
        if local_name(candidate.tag) == "cNvPr":
            object_id = candidate.get("id")
            if object_id:
                return {
                    "objectId": object_id,
                    "objectType": local_name(node.tag),
                }
    return {
        "objectId": f"anonymous-{fallback_index}",
        "objectType": local_name(node.tag),
    }


def object_relationship_ids(node: ET.Element) -> list[str]:
    values: set[str] = set()
    for candidate in node.iter():
        for attribute, relationship_id in candidate.attrib.items():
            if attribute.startswith(f"{{{R_NS}}}") and relationship_id:
                values.add(relationship_id)
    return sorted(values)


def first_direct_child(node: ET.Element, tag_name: str) -> ET.Element | None:
    return next(
        (child for child in list(node) if local_name(child.tag) == tag_name),
        None,
    )


def object_default_text_color(node: ET.Element) -> dict[str, Any] | None:
    for candidate in node.iter():
        if local_name(candidate.tag) == "fontRef":
            color = first_color_spec(candidate)
            if color is not None:
                return color
    return None


def extract_text_color_bindings(node: ET.Element) -> list[dict[str, Any]]:
    """Preserve ordered visible-text to effective-color bindings in one object."""
    object_default = object_default_text_color(node)
    bindings: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(
        node.iter(f"{{{A_NS}}}p"),
        start=1,
    ):
        paragraph_properties = first_direct_child(paragraph, "pPr")
        default_run_properties = (
            next(
                (
                    candidate
                    for candidate in paragraph_properties.iter()
                    if local_name(candidate.tag) == "defRPr"
                ),
                None,
            )
            if paragraph_properties is not None
            else None
        )
        paragraph_default = (
            first_color_spec(default_run_properties)
            if default_run_properties is not None
            else None
        )
        raw_segments: list[dict[str, Any]] = []
        for child in list(paragraph):
            if local_name(child.tag) not in {"r", "fld"}:
                continue
            text = "".join(
                candidate.text or ""
                for candidate in child.iter(f"{{{A_NS}}}t")
            )
            if not text:
                continue
            run_properties = first_direct_child(child, "rPr")
            run_color = (
                first_color_spec(run_properties)
                if run_properties is not None
                else None
            )
            effective_color = run_color or paragraph_default or object_default
            if (
                raw_segments
                and raw_segments[-1]["color"] == effective_color
            ):
                raw_segments[-1]["text"] += text
            else:
                raw_segments.append({
                    "text": text,
                    "color": effective_color,
                })
        segment_index = 0
        for segment in raw_segments:
            text = normalize_text(segment["text"])
            if not text:
                continue
            segment_index += 1
            bindings.append({
                "paragraph": paragraph_index,
                "segment": segment_index,
                "text": text,
                "color": segment["color"],
            })
    return bindings


def normalized_boolean_property(value: str | None) -> str | None:
    if value is None:
        return None
    return "1" if value.strip().lower() in {"1", "true", "on", "yes"} else "0"


def extract_text_bold_bindings(node: ET.Element) -> list[dict[str, Any]]:
    """Preserve ordered visible-text to effective bold bindings in one object."""
    bindings: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(
        node.iter(f"{{{A_NS}}}p"),
        start=1,
    ):
        paragraph_properties = first_direct_child(paragraph, "pPr")
        default_run_properties = (
            next(
                (
                    candidate
                    for candidate in paragraph_properties.iter()
                    if local_name(candidate.tag) == "defRPr"
                ),
                None,
            )
            if paragraph_properties is not None
            else None
        )
        paragraph_default = normalized_boolean_property(
            default_run_properties.get("b")
            if default_run_properties is not None
            else None
        )
        raw_segments: list[dict[str, Any]] = []
        for child in list(paragraph):
            if local_name(child.tag) not in {"r", "fld"}:
                continue
            text = "".join(
                candidate.text or ""
                for candidate in child.iter(f"{{{A_NS}}}t")
            )
            if not text:
                continue
            run_properties = first_direct_child(child, "rPr")
            run_bold = normalized_boolean_property(
                run_properties.get("b")
                if run_properties is not None
                else None
            )
            effective_bold = (
                run_bold if run_bold is not None else paragraph_default
            )
            if raw_segments and raw_segments[-1]["bold"] == effective_bold:
                raw_segments[-1]["text"] += text
            else:
                raw_segments.append({
                    "text": text,
                    "bold": effective_bold,
                })
        segment_index = 0
        for segment in raw_segments:
            text = normalize_text(segment["text"])
            if not text:
                continue
            segment_index += 1
            bindings.append({
                "paragraph": paragraph_index,
                "segment": segment_index,
                "text": text,
                "bold": segment["bold"],
            })
    return bindings


def semantic_object_inventories(
    package: zipfile.ZipFile,
    root: ET.Element,
    slide_part: str,
) -> dict[str, list[dict[str, Any]]]:
    relationships = relationship_record_map(package, slide_part)
    content_items: list[dict[str, Any]] = []
    color_items: list[dict[str, Any]] = []
    font_items: list[dict[str, Any]] = []
    text_style_items: list[dict[str, Any]] = []
    objects = [
        node
        for node in root.iter()
        if local_name(node.tag) in SEMANTIC_OBJECT_TAGS
    ]
    for index, node in enumerate(objects, start=1):
        identity = object_identity(node, index)
        related_parts: list[str] = []
        related_roots: list[ET.Element] = []
        for relationship_id in object_relationship_ids(node):
            relationship = relationships.get(relationship_id)
            if (
                not relationship
                or not any(
                    relationship["type"].endswith(suffix)
                    for suffix in SEMANTIC_RELATIONSHIP_SUFFIXES
                )
                or not relationship["target"].endswith(".xml")
            ):
                continue
            related_parts.append(relationship["target"])
            related_roots.append(read_xml(package, relationship["target"]))
        paragraphs = extract_paragraphs(node)
        related_data_values = sorted(
            value
            for related_root in related_roots
            for value in extract_related_data_values(related_root)
        )
        related_data_bindings = sorted(
            (
                binding
                for related_part, related_root in zip(
                    related_parts,
                    related_roots,
                )
                for binding in extract_related_data_bindings(
                    related_root,
                    related_part,
                )
            ),
            key=canonical_json,
        )
        if paragraphs or related_data_values or related_parts:
            content_items.append({
                **identity,
                "paragraphs": paragraphs,
                "numbers": extract_numbers([*paragraphs, *related_data_values]),
                "relatedParts": sorted(related_parts),
                "relatedDataValues": related_data_values,
                "relatedDataBindings": related_data_bindings,
            })
        colors = visible_color_semantics(
            merge_color_semantics([
                collect_colors(node),
                *(collect_colors(related_root) for related_root in related_roots),
            ])
        )
        text_color_bindings = extract_text_color_bindings(node)
        related_text_color_bindings = [
            {
                "part": related_part,
                "bindings": extract_text_color_bindings(related_root),
            }
            for related_part, related_root in zip(
                related_parts,
                related_roots,
            )
            if extract_text_color_bindings(related_root)
        ]
        if (
            colors["direct"]
            or colors["themeReferences"]
            or text_color_bindings
            or related_text_color_bindings
        ):
            color_items.append({
                **identity,
                "colorSemantics": colors,
                "textColorBindings": text_color_bindings,
                "relatedTextColorBindings": related_text_color_bindings,
            })
        fonts = merge_font_semantics([
            collect_fonts(node),
            *(collect_fonts(related_root) for related_root in related_roots),
        ])
        if fonts:
            font_items.append({
                **identity,
                "fontSemantics": fonts,
            })
        text_bold_bindings = extract_text_bold_bindings(node)
        related_text_bold_bindings = [
            {
                "part": related_part,
                "bindings": extract_text_bold_bindings(related_root),
            }
            for related_part, related_root in zip(
                related_parts,
                related_roots,
            )
            if extract_text_bold_bindings(related_root)
        ]
        if text_bold_bindings or related_text_bold_bindings:
            text_style_items.append({
                **identity,
                "textBoldBindings": text_bold_bindings,
                "relatedTextBoldBindings": related_text_bold_bindings,
            })
    sort_key = lambda item: (item["objectId"], item["objectType"])
    return {
        "content": sorted(content_items, key=sort_key),
        "colors": sorted(color_items, key=sort_key),
        "fonts": sorted(font_items, key=sort_key),
        "textStyles": sorted(text_style_items, key=sort_key),
    }


def first_color_spec(node: ET.Element) -> dict[str, Any] | None:
    for candidate in node.iter():
        tag = local_name(candidate.tag)
        if tag in COLOR_TAGS:
            return {
                "type": tag,
                "value": color_value(candidate),
                "transforms": color_transforms(candidate),
            }
    return None


def theme_scheme_from_root(root: ET.Element) -> dict[str, Any]:
    scheme = root.find(f".//{{{A_NS}}}clrScheme")
    colors: dict[str, Any] = {}
    if scheme is not None:
        for slot in list(scheme):
            colors[local_name(slot.tag)] = first_color_spec(slot)
    return {
        "schemeName": scheme.get("name", "") if scheme is not None else "",
        "colors": colors,
    }


def theme_font_scheme_from_root(root: ET.Element) -> dict[str, Any]:
    scheme = root.find(f".//{{{A_NS}}}fontScheme")
    if scheme is None:
        return {"schemeName": "", "entries": []}
    entries: list[dict[str, Any]] = []
    for node in scheme.iter():
        tag = local_name(node.tag)
        if tag not in TYPEFACE_TAGS:
            continue
        entries.append({
            "tag": tag,
            "attributes": dict(sorted(node.attrib.items())),
        })
    entries.sort(key=canonical_json)
    return {
        "schemeName": scheme.get("name", ""),
        "entries": entries,
    }


def first_related_part(
    package: zipfile.ZipFile,
    source_part: str,
    relationship_suffix: str,
) -> str | None:
    for relationship in relationship_records(package, source_part):
        if relationship["type"].endswith(relationship_suffix):
            return relationship["target"]
    return None


def inherited_slide_color_semantics(
    package: zipfile.ZipFile,
    slide_part: str,
) -> dict[str, Any]:
    layout_part = first_related_part(package, slide_part, "/slideLayout")
    master_part = first_related_part(package, layout_part, "/slideMaster") if layout_part else None
    theme_part = first_related_part(package, master_part, "/theme") if master_part else None
    theme = theme_scheme_from_root(read_xml(package, theme_part)) if theme_part else None

    master_color_map = None
    if master_part:
        master_root = read_xml(package, master_part)
        color_map = master_root.find(f".//{{{P_NS}}}clrMap")
        if color_map is not None:
            master_color_map = dict(sorted(color_map.attrib.items()))

    layout_override = None
    if layout_part:
        layout_root = read_xml(package, layout_part)
        override = layout_root.find(f".//{{{P_NS}}}clrMapOvr")
        if override is not None and list(override):
            mapping = list(override)[0]
            layout_override = {
                "type": local_name(mapping.tag),
                "attributes": dict(sorted(mapping.attrib.items())),
            }
    return {
        "theme": theme,
        "masterColorMap": master_color_map,
        "layoutColorMapOverride": layout_override,
    }


def extract_theme_semantics(
    package: zipfile.ZipFile,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    theme_parts: list[dict[str, Any]] = []
    semantic_schemes: list[dict[str, Any]] = []
    font_schemes: list[dict[str, Any]] = []
    for part_name in sorted(
        name for name in package.namelist() if name.startswith("ppt/theme/theme") and name.endswith(".xml")
    ):
        root = read_xml(package, part_name)
        semantics = theme_scheme_from_root(root)
        font_semantics = theme_font_scheme_from_root(root)
        theme_parts.append({
            "part": part_name,
            "colorScheme": semantics,
            "fontScheme": font_semantics,
        })
        semantic_schemes.append(semantics)
        font_schemes.append(font_semantics)
    semantic_schemes.sort(key=canonical_json)
    font_schemes.sort(key=canonical_json)
    return theme_parts, semantic_schemes, font_schemes


def build_slide(
    package: zipfile.ZipFile,
    root: ET.Element,
    position: int,
    part_name: str,
) -> dict[str, Any]:
    related_parts = sorted(
        relationship["target"]
        for relationship in relationship_records(package, part_name)
        if any(relationship["type"].endswith(suffix) for suffix in SEMANTIC_RELATIONSHIP_SUFFIXES)
        and relationship["target"].endswith(".xml")
    )
    related_roots = [read_xml(package, related_part) for related_part in related_parts]
    paragraphs = extract_paragraphs(root)
    for related_root in related_roots:
        paragraphs.extend(extract_paragraphs(related_root))
    text_inventory = sorted(paragraphs)
    related_data_values = sorted(
        value
        for related_root in related_roots
        for value in extract_related_data_values(related_root)
    )
    numbers = extract_numbers([*paragraphs, *related_data_values])
    colors = visible_color_semantics(
        merge_color_semantics(
            [collect_colors(root), *(collect_colors(related_root) for related_root in related_roots)]
        )
    )
    colors["inherited"] = inherited_slide_color_semantics(package, part_name)
    fonts = merge_font_semantics(
        [collect_fonts(root), *(collect_fonts(related_root) for related_root in related_roots)]
    )
    object_inventories = semantic_object_inventories(
        package,
        root,
        part_name,
    )
    content_payload = {
        "textInventory": text_inventory,
        "relatedDataValues": related_data_values,
        "numbers": numbers,
        "objectContentSemantics": object_inventories["content"],
    }
    semantic_payload = {
        **content_payload,
        "colorSemantics": colors,
        "fontSemantics": fonts,
        "objectColorSemantics": object_inventories["colors"],
        "objectFontSemantics": object_inventories["fonts"],
        "objectTextStyleSemantics": object_inventories["textStyles"],
    }
    return {
        "position": position,
        "part": part_name,
        "paragraphs": paragraphs,
        "textInventory": text_inventory,
        "relatedParts": related_parts,
        "relatedDataValues": related_data_values,
        "numbers": numbers,
        "colorSemantics": colors,
        "fontSemantics": fonts,
        "objectContentSemantics": object_inventories["content"],
        "objectColorSemantics": object_inventories["colors"],
        "objectFontSemantics": object_inventories["fonts"],
        "objectTextStyleSemantics": object_inventories["textStyles"],
        "contentKey": semantic_hash(content_payload),
        "semanticHash": semantic_hash(semantic_payload),
    }


def create_fingerprint(pptx_path: Path) -> dict[str, Any]:
    if not pptx_path.is_file():
        raise FingerprintError(f"PPTX not found: {pptx_path}")
    try:
        with zipfile.ZipFile(pptx_path) as package:
            bad_part = package.testzip()
            if bad_part:
                raise FingerprintError(f"Corrupt ZIP member: {bad_part}")
            slide_parts = slide_parts_in_order(package)
            slides = [
                build_slide(package, read_xml(package, part_name), index, part_name)
                for index, part_name in enumerate(slide_parts, start=1)
            ]
            theme_parts, theme_semantics, theme_font_semantics = extract_theme_semantics(package)
    except zipfile.BadZipFile as error:
        raise FingerprintError(f"Not a valid PPTX ZIP package: {pptx_path}") from error

    semantic_payload = {
        "slideOrder": [slide["contentKey"] for slide in slides],
        "slides": [
            {
                "textInventory": slide["textInventory"],
                "relatedDataValues": slide["relatedDataValues"],
                "numbers": slide["numbers"],
                "colorSemantics": slide["colorSemantics"],
                "fontSemantics": slide["fontSemantics"],
                "objectContentSemantics": slide["objectContentSemantics"],
                "objectColorSemantics": slide["objectColorSemantics"],
                "objectFontSemantics": slide["objectFontSemantics"],
            }
            for slide in slides
        ],
        "themeColorSemantics": theme_semantics,
        "themeFontSemantics": theme_font_semantics,
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "validatorSha256": sha256_file(Path(__file__).resolve()),
        "archiveSha256": sha256_file(pptx_path),
        "overallHash": semantic_hash(semantic_payload),
        "slideCount": len(slides),
        "slideOrder": [slide["contentKey"] for slide in slides],
        "slides": slides,
        "themeParts": theme_parts,
        "themeColorSemantics": theme_semantics,
        "themeFontSemantics": theme_font_semantics,
    }


def add_error(errors: list[dict[str, Any]], rule: str, detail: str, **context: Any) -> None:
    errors.append({"rule": rule, "detail": detail, **context})


def occurrence_keys(slides: list[dict[str, Any]]) -> list[tuple[str, int]]:
    seen: collections.Counter[str] = collections.Counter()
    result: list[tuple[str, int]] = []
    for slide in slides:
        key = slide["contentKey"]
        seen[key] += 1
        result.append((key, seen[key]))
    return result


def compare_fingerprints(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    font_policy: str = "allow",
) -> dict[str, Any]:
    if baseline.get("schemaVersion") != SCHEMA_VERSION:
        raise FingerprintError(f"Unsupported baseline schema: {baseline.get('schemaVersion')}")
    if candidate.get("schemaVersion") != SCHEMA_VERSION:
        raise FingerprintError(f"Unsupported candidate schema: {candidate.get('schemaVersion')}")

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    baseline_slides = baseline["slides"]
    candidate_slides = candidate["slides"]

    if baseline["slideCount"] != candidate["slideCount"]:
        add_error(
            errors,
            "slide_count_drift",
            f"{baseline['slideCount']} -> {candidate['slideCount']}",
        )

    baseline_order = baseline["slideOrder"]
    candidate_order = candidate["slideOrder"]
    same_content_inventory = collections.Counter(baseline_order) == collections.Counter(candidate_order)
    reordered = same_content_inventory and baseline_order != candidate_order
    if reordered:
        add_error(errors, "slide_order_drift", "逐页内容相同，但页面顺序发生变化")

    pairs: list[tuple[dict[str, Any], dict[str, Any], int, int]] = []
    if same_content_inventory:
        candidate_by_occurrence = {
            occurrence: (slide, index)
            for index, (occurrence, slide) in enumerate(
                zip(occurrence_keys(candidate_slides), candidate_slides), start=1
            )
        }
        for baseline_index, (occurrence, baseline_slide) in enumerate(
            zip(occurrence_keys(baseline_slides), baseline_slides), start=1
        ):
            candidate_slide, candidate_index = candidate_by_occurrence[occurrence]
            pairs.append((baseline_slide, candidate_slide, baseline_index, candidate_index))
    else:
        pairs.extend(
            (baseline_slide, candidate_slide, index, index)
            for index, (baseline_slide, candidate_slide) in enumerate(
                zip(baseline_slides, candidate_slides), start=1
            )
        )

    for baseline_slide, candidate_slide, baseline_index, candidate_index in pairs:
        location = {"baselineSlide": baseline_index, "candidateSlide": candidate_index}
        if baseline_slide["textInventory"] != candidate_slide["textInventory"]:
            add_error(errors, "slide_text_drift", "逐页可见文本发生变化", **location)
        if baseline_slide.get("relatedDataValues", []) != candidate_slide.get("relatedDataValues", []):
            add_error(errors, "slide_embedded_data_drift", "逐页图表／SmartArt缓存数据发生变化", **location)
        if baseline_slide["numbers"] != candidate_slide["numbers"]:
            add_error(errors, "slide_number_drift", "逐页数字／金额／比例发生变化", **location)
        if (
            baseline_slide.get("objectContentSemantics", [])
            != candidate_slide.get("objectContentSemantics", [])
        ):
            add_error(
                errors,
                "slide_object_content_binding_drift",
                "文字、数字、图表缓存数据或系列／点级关系在原生对象内外发生交换或重绑定",
                **location,
            )
        if baseline_slide["colorSemantics"] != candidate_slide["colorSemantics"]:
            add_error(
                errors,
                "slide_color_semantics_drift",
                "直接色、主题色引用、色彩角色或变换发生变化",
                **location,
            )
        if (
            baseline_slide.get("objectColorSemantics", [])
            != candidate_slide.get("objectColorSemantics", [])
        ):
            add_error(
                errors,
                "slide_object_color_binding_drift",
                "颜色语义或同一原生对象内的文字—颜色配对／顺序发生交换或重绑定",
                **location,
            )
        if (
            font_policy == "preserve"
            and baseline_slide.get("fontSemantics", []) != candidate_slide.get("fontSemantics", [])
        ):
            add_error(
                errors,
                "slide_font_semantics_drift",
                "字体族、字号或主题字体引用发生变化",
                **location,
            )
        if (
            font_policy == "preserve"
            and baseline_slide.get("objectFontSemantics", [])
            != candidate_slide.get("objectFontSemantics", [])
        ):
            add_error(
                errors,
                "slide_object_font_binding_drift",
                "字体语义在原生对象之间发生交换或重绑定",
                **location,
            )
        if (
            baseline_slide.get("objectTextStyleSemantics", [])
            != candidate_slide.get("objectTextStyleSemantics", [])
        ):
            add_error(
                errors,
                "slide_object_text_style_binding_drift",
                "加粗状态与可见文字在原生对象内外发生交换或重绑定",
                **location,
            )

    if baseline.get("themeColorSemantics") != candidate.get("themeColorSemantics"):
        add_error(errors, "theme_color_semantics_drift", "主题色槽位或主题色值发生变化")
    if (
        font_policy == "preserve"
        and baseline.get("themeFontSemantics", []) != candidate.get("themeFontSemantics", [])
    ):
        add_error(errors, "theme_font_semantics_drift", "主题字体槽位或字体值发生变化")

    if not same_content_inventory and baseline["slideCount"] == candidate["slideCount"]:
        warnings.append(
            {
                "rule": "slide_order_not_comparable",
                "detail": "存在内容漂移，无法单独证明是否还伴随页序漂移",
            }
        )

    return {
        "schemaVersion": "ksib-pptx-semantic-compare/3.0",
        "validatorSha256": sha256_file(Path(__file__).resolve()),
        "mode": "format-only",
        "fontPolicy": font_policy,
        "passed": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "baseline": {
            "archiveSha256": baseline["archiveSha256"],
            "overallHash": baseline["overallHash"],
            "slideCount": baseline["slideCount"],
        },
        "candidate": {
            "archiveSha256": candidate["archiveSha256"],
            "overallHash": candidate["overallHash"],
            "slideCount": candidate["slideCount"],
        },
        "errors": errors,
        "warnings": warnings,
    }


def write_json(path: Path | None, value: Any) -> None:
    output = f"{json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)}\n"
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        summary = {
            "passed": value.get("passed", True) if isinstance(value, dict) else True,
            "output": str(path),
        }
        for key in ("overallHash", "slideCount", "errorCount", "warningCount"):
            if isinstance(value, dict) and key in value:
                summary[key] = value[key]
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    else:
        print(output, end="")


def load_baseline(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".pptx":
        return create_fingerprint(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FingerprintError(f"Cannot read baseline fingerprint: {path}") from error


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a semantic fingerprint")
    create_parser.add_argument("--pptx", required=True, type=Path)
    create_parser.add_argument("--output", type=Path)

    compare_parser = subparsers.add_parser("compare", help="Compare a PPTX with a locked fingerprint")
    compare_parser.add_argument("--baseline", required=True, type=Path)
    compare_parser.add_argument("--pptx", required=True, type=Path)
    compare_parser.add_argument("--mode", default="format-only", choices=["format-only"])
    compare_parser.add_argument(
        "--font-policy",
        default="allow",
        choices=["allow", "preserve"],
        help="preserve blocks font-family, size, and theme-font drift; allow permits font normalization",
    )
    compare_parser.add_argument("--report", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "create":
            write_json(args.output, create_fingerprint(args.pptx.resolve()))
            return 0
        baseline = load_baseline(args.baseline.resolve())
        candidate = create_fingerprint(args.pptx.resolve())
        report = compare_fingerprints(baseline, candidate, font_policy=args.font_policy)
        write_json(args.report, report)
        return 0 if report["passed"] else 1
    except FingerprintError as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
