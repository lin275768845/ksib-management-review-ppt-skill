#!/usr/bin/env python3
"""Validate OPC and PresentationML semantics that PowerPoint enforces."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET


OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
CHART_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DIAGRAM_NS = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
A = f"{{{DRAWING_NS}}}"
P = f"{{{PRESENTATION_NS}}}"
C = f"{{{CHART_NS}}}"
DGM = f"{{{DIAGRAM_NS}}}"
EMU_PER_INCH = 914400
TEXT_FILL_NAMES = {
    "solidFill",
    "gradFill",
    "noFill",
    "pattFill",
    "blipFill",
    "grpFill",
}
KSIB_THEME_NAME = "KSIB Management Review Orange"
KSIB_THEME_FONT_NAME = "KSIB Management Review Chinese"
KSIB_THEME_COLORS = {
    "dk1": "1F2329",
    "lt1": "FFFFFF",
    "dk2": "646A73",
    "lt2": "FAFAFA",
    "accent1": "FF4906",
    "accent2": "D83D00",
    "accent3": "FFF7F3",
    "accent4": "FFDBCD",
    "accent5": "3B4048",
    "accent6": "E5E6EB",
    "hlink": "3370FF",
    "folHlink": "7C3AED",
}
APPROVED_TYPEFACES = {"PingFang SC", "Microsoft YaHei", "苹方-简"}
APPROVED_POINT_SIZES = {9, 10, 12, 14, 16, 18, 22, 24, 28, 44}
UNRESOLVED_MARKERS = ("[占位]", "[替换]", "[TBD]", "[待验证]")
NINE_POINT_ROLE_TOKENS = {
    "source",
    "footnote",
    "footer",
    "pagenumber",
    "来源",
    "脚注",
    "页脚",
    "页码",
}
TEN_POINT_ROLE_TOKENS = {
    *NINE_POINT_ROLE_TOKENS,
    "header",
    "header-text",
    "页眉",
    "appendix",
    "appendix-table",
    "dense",
    "附录",
    "密集表",
}
EDITABILITY_LOCK_ATTRIBUTES = {
    "noGrp",
    "noMove",
    "noResize",
    "noSelect",
    "noTextEdit",
}
EDITABLE_TEXT_MEMBER_RE = re.compile(
    r"ppt/(?:"
    r"slides/slide\d+|"
    r"notesSlides/notesSlide\d+|"
    r"(?:charts|slides/charts)/chart\d+|"
    r"diagrams/(?:data|drawing)\d+"
    r")\.xml"
)
PRESENTATION_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "presentationml.presentation.main+xml"
)
SLIDE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "presentationml.slide+xml"
)
FORMAT_CONTRACT_SCHEMA = "ksib-format-contract/1.0"
CROSS_SLIDE_COMPARE_FIELDS = {
    "geometry",
    "rotation",
    "objectType",
    "fill",
    "line",
    "textMargins",
    "verticalAlignment",
    "font",
    "paragraph",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fill_signature(properties: ET.Element | None) -> bytes | None:
    if properties is None:
        return None
    fills = [
        child for child in properties if local_name(child.tag) in TEXT_FILL_NAMES
    ]
    if len(fills) != 1:
        return None
    return ET.tostring(fills[0], encoding="utf-8")


def shape_name(shape: ET.Element) -> str:
    properties = shape.find(f"./{P}nvSpPr/{P}cNvPr")
    return properties.get("name", "") if properties is not None else ""


def nearest_named_object(
    element: ET.Element,
    parent_by_child: dict[ET.Element, ET.Element],
) -> ET.Element | None:
    current = element
    while current in parent_by_child:
        current = parent_by_child[current]
        if local_name(current.tag) in {
            "sp",
            "graphicFrame",
            "cxnSp",
            "pic",
            "grpSp",
        }:
            return current
    return None


def object_name(element: ET.Element | None) -> str:
    if element is None:
        return ""
    properties = next(
        (
            candidate
            for candidate in element.iter()
            if local_name(candidate.tag) == "cNvPr"
        ),
        None,
    )
    return properties.get("name", "") if properties is not None else ""


def object_vertical_offset(element: ET.Element | None) -> int | None:
    if element is None:
        return None
    for candidate in element.iter():
        if local_name(candidate.tag) != "off":
            continue
        value = candidate.get("y")
        if value is None:
            continue
        try:
            return int(value)
        except ValueError:
            return None
    return None


def object_name_matches_text_role(name: str, tokens: set[str]) -> bool:
    folded = name.casefold().strip()
    if not folded:
        return False
    normalized_tokens = {token.casefold() for token in tokens}
    for token in tokens:
        escaped = re.escape(token.casefold())
        if re.fullmatch(rf"{escaped}(?:[-_ ]?\d+)?", folded):
            return True
    parts = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", folded)
    return bool(parts) and all(
        part.isdigit() or part in normalized_tokens
        for part in parts
    )


def is_notes_placeholder(
    part_name: str,
    element: ET.Element | None,
) -> bool:
    """Return true for standard notes-page placeholders, not user objects."""
    if not part_name.startswith("ppt/notesSlides/") or element is None:
        return False
    return any(
        local_name(candidate.tag) == "ph"
        for candidate in element.iter()
    )


def format_role_matches(name: str, role: str) -> bool:
    folded_name = name.casefold().strip()
    folded_role = role.casefold().strip()
    return bool(
        re.fullmatch(
            rf"{re.escape(folded_role)}(?:[-_ ]?\d+)?",
            folded_name,
        )
    )


def object_geometry(element: ET.Element) -> dict[str, float] | None:
    """Read the first DrawingML transform from a top-level slide object."""
    transform = next(
        (
            candidate
            for candidate in element.iter()
            if local_name(candidate.tag) == "xfrm"
        ),
        None,
    )
    if transform is None:
        return None
    offset = next(
        (
            child
            for child in transform
            if local_name(child.tag) == "off"
        ),
        None,
    )
    extent = next(
        (
            child
            for child in transform
            if local_name(child.tag) == "ext"
        ),
        None,
    )
    if offset is None or extent is None:
        return None
    try:
        return {
            "x": int(offset.get("x", "")) / EMU_PER_INCH,
            "y": int(offset.get("y", "")) / EMU_PER_INCH,
            "w": int(extent.get("cx", "")) / EMU_PER_INCH,
            "h": int(extent.get("cy", "")) / EMU_PER_INCH,
        }
    except ValueError:
        return None


def object_geometry_emu(element: ET.Element) -> dict[str, int] | None:
    """Read exact top-level geometry without lossy inch conversion."""
    transform = next(
        (
            candidate
            for candidate in element.iter()
            if local_name(candidate.tag) == "xfrm"
        ),
        None,
    )
    if transform is None:
        return None
    offset = next(
        (
            child
            for child in transform
            if local_name(child.tag) == "off"
        ),
        None,
    )
    extent = next(
        (
            child
            for child in transform
            if local_name(child.tag) == "ext"
        ),
        None,
    )
    if offset is None or extent is None:
        return None
    try:
        return {
            "x": int(offset.get("x", "")),
            "y": int(offset.get("y", "")),
            "w": int(extent.get("cx", "")),
            "h": int(extent.get("cy", "")),
        }
    except ValueError:
        return None


def canonical_xml_style(element: ET.Element | None) -> dict | None:
    """Return a namespace-stable, JSON-safe representation of style XML."""
    if element is None:
        return None
    return {
        "tag": local_name(element.tag),
        "attributes": {
            local_name(key): value
            for key, value in sorted(
                element.attrib.items(),
                key=lambda item: local_name(item[0]),
            )
        },
        "text": (element.text or "").strip() or None,
        "children": [
            canonical_xml_style(child)
            for child in element
        ],
    }


def style_hash(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def object_transform(element: ET.Element) -> ET.Element | None:
    return next(
        (
            candidate
            for candidate in element.iter()
            if local_name(candidate.tag) == "xfrm"
        ),
        None,
    )


def object_shape_properties(element: ET.Element) -> ET.Element | None:
    expected_name = (
        "grpSpPr"
        if local_name(element.tag) == "grpSp"
        else "spPr"
    )
    return next(
        (
            child
            for child in element
            if local_name(child.tag) == expected_name
        ),
        None,
    )


def direct_child_by_local_name(
    element: ET.Element | None,
    names: set[str],
) -> ET.Element | None:
    if element is None:
        return None
    return next(
        (
            child
            for child in element
            if local_name(child.tag) in names
        ),
        None,
    )


def object_fill_style(element: ET.Element) -> dict:
    properties = object_shape_properties(element)
    explicit = direct_child_by_local_name(properties, TEXT_FILL_NAMES)
    style = direct_child_by_local_name(element, {"style"})
    reference = direct_child_by_local_name(style, {"fillRef"})
    return {
        "explicit": canonical_xml_style(explicit),
        "reference": canonical_xml_style(reference),
    }


def object_line_style(element: ET.Element) -> dict:
    properties = object_shape_properties(element)
    explicit = direct_child_by_local_name(properties, {"ln"})
    style = direct_child_by_local_name(element, {"style"})
    reference = direct_child_by_local_name(style, {"lnRef"})
    return {
        "explicit": canonical_xml_style(explicit),
        "reference": canonical_xml_style(reference),
    }


def text_body_margins_emu(element: ET.Element) -> dict[str, int] | None:
    text_body = element.find(f"./{P}txBody")
    if text_body is None:
        return None
    body_properties = text_body.find(f"./{A}bodyPr")
    if body_properties is None:
        return None
    defaults = {
        "lIns": 91440,
        "rIns": 91440,
        "tIns": 45720,
        "bIns": 45720,
    }
    try:
        return {
            attribute: int(body_properties.get(attribute, str(default)))
            for attribute, default in defaults.items()
        }
    except ValueError:
        return None


def effective_boolean_attribute(
    element: ET.Element,
    attribute: str,
    default: bool = False,
) -> bool | str:
    raw = element.get(attribute)
    if raw is None:
        return default
    folded = raw.casefold()
    if folded in {"1", "true", "on"}:
        return True
    if folded in {"0", "false", "off"}:
        return False
    return raw


def text_body_vertical_alignment(element: ET.Element) -> dict | None:
    """Return effective bodyPr vertical alignment and orientation values."""
    text_body = element.find(f"./{P}txBody")
    if text_body is None:
        return None
    body_properties = text_body.find(f"./{A}bodyPr")
    if body_properties is None:
        return None
    try:
        body_rotation: int | str = int(body_properties.get("rot", "0"))
    except ValueError:
        body_rotation = body_properties.get("rot", "")
    return {
        # ECMA-376 defaults are materialized so an omitted default and an
        # explicitly written equivalent do not create a false drift.
        "anchor": body_properties.get("anchor", "t"),
        "anchorCtr": effective_boolean_attribute(
            body_properties,
            "anchorCtr",
        ),
        "vert": body_properties.get("vert", "horz"),
        "vertOverflow": body_properties.get(
            "vertOverflow",
            "overflow",
        ),
        "upright": effective_boolean_attribute(
            body_properties,
            "upright",
        ),
        "rot": body_rotation,
    }


FONT_STYLE_ATTRIBUTES = {
    "sz",
    "b",
    "i",
    "u",
    "strike",
    "kern",
    "cap",
    "baseline",
    "normalizeH",
    "lang",
    "altLang",
    "dirty",
    "smtClean",
}
FONT_STYLE_CHILDREN = {
    "latin",
    "ea",
    "cs",
    "sym",
    "solidFill",
    "gradFill",
    "noFill",
    "pattFill",
}
PARAGRAPH_STYLE_ATTRIBUTES = {
    "marL",
    "marR",
    "lvl",
    "indent",
    "algn",
    "defTabSz",
    "rtl",
    "eaLnBrk",
    "latinLnBrk",
    "hangingPunct",
    "fontAlgn",
}
PARAGRAPH_STYLE_CHILDREN = {
    "lnSpc",
    "spcBef",
    "spcAft",
    "buClrTx",
    "buClr",
    "buSzTx",
    "buSzPct",
    "buSzPts",
    "buFontTx",
    "buFont",
    "buNone",
    "buAutoNum",
    "buChar",
    "tabLst",
}


def selected_style_signature(
    element: ET.Element | None,
    *,
    attributes: set[str],
    children: set[str],
) -> dict | None:
    if element is None:
        return None
    return {
        "attributes": {
            key: value
            for key, value in sorted(element.attrib.items())
            if local_name(key) in attributes
        },
        "children": [
            canonical_xml_style(child)
            for child in element
            if local_name(child.tag) in children
        ],
    }


def object_font_style(element: ET.Element) -> list[dict | None]:
    """Inventory stable direct/default font styling, independent of text."""
    signatures: list[dict | None] = []
    for paragraph in element.iter(f"{A}p"):
        paragraph_properties = paragraph.find(f"./{A}pPr")
        default_properties = (
            paragraph_properties.find(f"./{A}defRPr")
            if paragraph_properties is not None
            else None
        )
        signatures.append(
            selected_style_signature(
                default_properties,
                attributes=FONT_STYLE_ATTRIBUTES,
                children=FONT_STYLE_CHILDREN,
            )
        )
        for run_tag in ("r", "fld"):
            for run in paragraph.findall(f"./{A}{run_tag}"):
                signatures.append(
                    selected_style_signature(
                        run.find(f"./{A}rPr"),
                        attributes=FONT_STYLE_ATTRIBUTES,
                        children=FONT_STYLE_CHILDREN,
                    )
                )
        signatures.append(
            selected_style_signature(
                paragraph.find(f"./{A}endParaRPr"),
                attributes=FONT_STYLE_ATTRIBUTES,
                children=FONT_STYLE_CHILDREN,
            )
        )
    unique = {
        json.dumps(
            signature,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ): signature
        for signature in signatures
    }
    return [unique[key] for key in sorted(unique)]


def object_paragraph_style(element: ET.Element) -> list[dict | None]:
    signatures = [
        selected_style_signature(
            paragraph.find(f"./{A}pPr"),
            attributes=PARAGRAPH_STYLE_ATTRIBUTES,
            children=PARAGRAPH_STYLE_CHILDREN,
        )
        for paragraph in element.iter(f"{A}p")
    ]
    unique = {
        json.dumps(
            signature,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ): signature
        for signature in signatures
    }
    return [unique[key] for key in sorted(unique)]


def object_cross_slide_signature(record: dict) -> dict:
    element = record["element"]
    transform = object_transform(element)
    try:
        rotation = int(transform.get("rot", "0")) if transform is not None else 0
    except ValueError:
        rotation = None
    return {
        "objectType": record["type"],
        "geometryEmu": object_geometry_emu(element),
        "rotation": rotation,
        "fill": object_fill_style(element),
        "line": object_line_style(element),
        "textMarginsEmu": text_body_margins_emu(element),
        "verticalAlignment": text_body_vertical_alignment(element),
        "font": object_font_style(element),
        "paragraph": object_paragraph_style(element),
    }


def object_text(element: ET.Element) -> str:
    return "".join(
        candidate.text or ""
        for candidate in element.iter(f"{A}t")
    ).strip()


def weighted_title_length(value: str) -> float:
    total = 0.0
    for character in value:
        if character.isspace():
            total += 0.3
        elif ord(character) <= 0x7F:
            total += 0.55 if character.isalnum() else 0.45
        else:
            total += 1.0
    return total


def action_title_text_structure(element: ET.Element) -> dict:
    paragraphs = []
    explicit_break_count = 0
    newline_character_count = 0
    for paragraph in element.iter(f"{A}p"):
        paragraph_text = "".join(
            candidate.text or ""
            for candidate in paragraph.iter(f"{A}t")
        )
        if paragraph_text.strip():
            paragraphs.append(paragraph_text)
        explicit_break_count += len(paragraph.findall(f".//{A}br"))
        newline_character_count += sum(
            paragraph_text.count(character)
            for character in ("\r", "\n", "\u2028", "\u2029")
        )
    text = "".join(paragraphs)
    return {
        "nonEmptyParagraphCount": len(paragraphs),
        "explicitBreakCount": explicit_break_count,
        "newlineCharacterCount": newline_character_count,
        "weightedCharacters": round(weighted_title_length(text), 3),
    }


def object_type(element: ET.Element) -> str:
    name = local_name(element.tag)
    if name == "pic":
        return "pictures"
    if name == "cxnSp":
        return "connectors"
    if name == "grpSp":
        return "groups"
    if name == "graphicFrame":
        if any(candidate.tag == f"{A}tbl" for candidate in element.iter()):
            return "tables"
        if any(candidate.tag == f"{C}chart" for candidate in element.iter()):
            return "charts"
        if any(candidate.tag == f"{DGM}relIds" for candidate in element.iter()):
            return "smartArt"
        return "graphicFrames"
    if name == "sp":
        if object_text(element):
            return "textBoxes"
        return "shapes"
    return "other"


def connector_semantics(element: ET.Element) -> dict[str, bool]:
    """Inventory whether a native connector is truly attached and arrowed."""
    if local_name(element.tag) != "cxnSp":
        return {
            "startConnected": False,
            "endConnected": False,
            "hasArrowhead": False,
        }
    connection_properties = next(
        (
            candidate
            for candidate in element.iter()
            if local_name(candidate.tag) == "cNvCxnSpPr"
        ),
        None,
    )
    start_connected = bool(
        connection_properties is not None
        and any(
            local_name(candidate.tag) == "stCxn"
            and candidate.get("id")
            for candidate in connection_properties
        )
    )
    end_connected = bool(
        connection_properties is not None
        and any(
            local_name(candidate.tag) == "endCxn"
            and candidate.get("id")
            for candidate in connection_properties
        )
    )
    has_arrowhead = any(
        local_name(candidate.tag) in {"headEnd", "tailEnd"}
        and candidate.get("type", "none") != "none"
        for candidate in element.iter()
    )
    return {
        "startConnected": start_connected,
        "endConnected": end_connected,
        "hasArrowhead": has_arrowhead,
    }


def object_field_types(element: ET.Element) -> list[str]:
    return sorted({
        candidate.get("type", "").strip()
        for candidate in element.iter(f"{A}fld")
        if candidate.get("type", "").strip()
    })


def chart_data_mode(
    *,
    chart_part: str,
    chart_root: ET.Element,
    relationships_by_source: dict[str | None, dict[str, ET.Element]],
) -> dict:
    relationships = relationships_by_source.get(chart_part, {})
    embedded_targets = sorted({
        resolve_target(chart_part, relationship.get("Target", ""))
        for relationship in relationships.values()
        if (
            relationship.get("TargetMode") != "External"
            and (
                relationship.get("Type", "").endswith("/package")
                or "embeddings/" in relationship.get("Target", "")
                or relationship.get("Target", "").lower().endswith(
                    (".xlsx", ".xlsm", ".xlsb")
                )
            )
        )
    })
    has_external_data = any(
        local_name(candidate.tag) == "externalData"
        for candidate in chart_root.iter()
    )
    has_literal_data = any(
        local_name(candidate.tag) in {"strLit", "numLit"}
        for candidate in chart_root.iter()
    )
    has_reference_data = any(
        local_name(candidate.tag) in {"strRef", "numRef", "multiLvlStrRef"}
        for candidate in chart_root.iter()
    )
    if embedded_targets:
        mode = "embeddedWorkbook"
    elif has_literal_data:
        mode = "nativeLiteral"
    elif has_reference_data:
        mode = "cachedReference"
    else:
        mode = "unknown"
    return {
        "part": chart_part,
        "mode": mode,
        "embeddedTargets": embedded_targets,
        "hasExternalData": has_external_data,
        "hasLiteralData": has_literal_data,
        "hasReferenceData": has_reference_data,
    }


def text_body_margins(element: ET.Element) -> dict[str, float] | None:
    text_body = element.find(f"./{P}txBody")
    if text_body is None:
        return None
    body_properties = text_body.find(f"./{A}bodyPr")
    if body_properties is None:
        return None
    # OOXML defaults are intentionally non-zero. Missing attributes therefore
    # do not satisfy a zero-margin role contract.
    defaults = {
        "lIns": 91440,
        "rIns": 91440,
        "tIns": 45720,
        "bIns": 45720,
    }
    margins: dict[str, float] = {}
    for attribute, default in defaults.items():
        raw = body_properties.get(attribute)
        try:
            margins[attribute] = int(raw) / EMU_PER_INCH if raw is not None else default / EMU_PER_INCH
        except ValueError:
            return None
    return margins


def normalize_hierarchy_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)


def bigram_similarity(left: str, right: str) -> float:
    left_normalized = normalize_hierarchy_text(left)
    right_normalized = normalize_hierarchy_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    if len(left_normalized) == 1 or len(right_normalized) == 1:
        return 0.0
    left_bigrams = {
        left_normalized[index:index + 2]
        for index in range(len(left_normalized) - 1)
    }
    right_bigrams = {
        right_normalized[index:index + 2]
        for index in range(len(right_normalized) - 1)
    }
    union = left_bigrams | right_bigrams
    return len(left_bigrams & right_bigrams) / len(union) if union else 0.0


def load_format_contract(path: str | None) -> tuple[dict | None, list[dict]]:
    if path is None:
        return None, []
    findings: list[dict] = []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [{
            "kind": "format_contract_unreadable",
            "detail": str(exc),
        }]
    if payload.get("schemaVersion") != FORMAT_CONTRACT_SCHEMA:
        findings.append({
            "kind": "format_contract_schema_invalid",
            "actual": payload.get("schemaVersion"),
            "expected": FORMAT_CONTRACT_SCHEMA,
        })
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        findings.append({
            "kind": "format_contract_slides_missing",
        })
    elif any(
        not isinstance(item, dict)
        or not isinstance(item.get("slide"), int)
        or item.get("slide", 0) <= 0
        for item in slides
    ):
        findings.append({
            "kind": "format_contract_slide_entry_invalid",
        })
    elif len({item["slide"] for item in slides}) != len(slides):
        findings.append({
            "kind": "format_contract_duplicate_slide",
        })
    equality_groups = payload.get("crossSlideEqualityGroups")
    if equality_groups is not None:
        if not isinstance(equality_groups, list):
            findings.append({
                "kind": "format_cross_slide_groups_invalid",
                "detail": "crossSlideEqualityGroups must be a list",
            })
        else:
            seen_group_ids: set[str] = set()
            for index, group in enumerate(equality_groups):
                group_id = (
                    group.get("id", "").strip()
                    if isinstance(group, dict)
                    and isinstance(group.get("id"), str)
                    else ""
                )
                roles = group.get("roles") if isinstance(group, dict) else None
                if (
                    not isinstance(group, dict)
                    or not group_id
                    or not isinstance(roles, list)
                    or not roles
                    or any(
                        not isinstance(role, str) or not role.strip()
                        for role in roles
                    )
                ):
                    findings.append({
                        "kind": "format_cross_slide_group_invalid",
                        "groupIndex": index,
                        "detail": "each group requires a non-empty id and roles[]",
                    })
                    continue
                if group_id in seen_group_ids:
                    findings.append({
                        "kind": "format_cross_slide_group_duplicate",
                        "group": group_id,
                    })
                seen_group_ids.add(group_id)
                explicit_slides = group.get("slides")
                if explicit_slides is not None and (
                    not isinstance(explicit_slides, list)
                    or not explicit_slides
                    or any(
                        not isinstance(slide, int) or slide <= 0
                        for slide in explicit_slides
                    )
                    or len(set(explicit_slides)) != len(explicit_slides)
                ):
                    findings.append({
                        "kind": "format_cross_slide_group_slides_invalid",
                        "group": group_id,
                    })
                selector = group.get("slideSelector")
                if selector is not None and not isinstance(selector, dict):
                    findings.append({
                        "kind": "format_cross_slide_group_selector_invalid",
                        "group": group_id,
                    })
                tolerance = group.get(
                    "geometryToleranceEmu",
                    group.get("toleranceEmu", 0),
                )
                if (
                    not isinstance(tolerance, int)
                    or isinstance(tolerance, bool)
                    or tolerance < 0
                ):
                    findings.append({
                        "kind": "format_cross_slide_group_tolerance_invalid",
                        "group": group_id,
                        "actual": tolerance,
                    })
                aliases = group.get("roleAliases")
                if aliases is not None and (
                    not isinstance(aliases, dict)
                    or any(
                        not isinstance(canonical, str)
                        or not isinstance(values, list)
                        or any(
                            not isinstance(value, str) or not value.strip()
                            for value in values
                        )
                        for canonical, values in aliases.items()
                    )
                ):
                    findings.append({
                        "kind": "format_cross_slide_group_aliases_invalid",
                        "group": group_id,
                    })
                compare_fields = group.get("compareFields")
                if compare_fields is not None and (
                    not isinstance(compare_fields, list)
                    or not compare_fields
                    or any(
                        not isinstance(field, str)
                        or field not in CROSS_SLIDE_COMPARE_FIELDS
                        for field in compare_fields
                    )
                    or len(set(compare_fields)) != len(compare_fields)
                ):
                    findings.append({
                        "kind": "format_cross_slide_group_compare_fields_invalid",
                        "group": group_id,
                        "actual": compare_fields,
                        "allowed": sorted(CROSS_SLIDE_COMPARE_FIELDS),
                    })
                reference_slide = group.get("referenceSlide")
                if reference_slide is not None and (
                    not isinstance(reference_slide, int)
                    or isinstance(reference_slide, bool)
                    or reference_slide <= 0
                ):
                    findings.append({
                        "kind": "format_cross_slide_group_reference_invalid",
                        "group": group_id,
                        "actual": reference_slide,
                    })
    return payload, findings


def slide_object_records(slide_root: ET.Element) -> list[dict]:
    shape_tree = slide_root.find(f"./{P}cSld/{P}spTree")
    if shape_tree is None:
        return []
    records = []
    for child in shape_tree:
        if local_name(child.tag) not in {
            "sp",
            "graphicFrame",
            "cxnSp",
            "pic",
            "grpSp",
        }:
            continue
        records.append({
            "name": object_name(child),
            "type": object_type(child),
            "geometry": object_geometry(child),
            "text": object_text(child),
            "margins": text_body_margins(child),
            "connector": connector_semantics(child),
            "fieldTypes": object_field_types(child),
            "element": child,
        })
    return records


def contract_role_aliases(contract: dict, role: str) -> list[str]:
    aliases: list[str] = []
    top_level_aliases = contract.get("roleAliases", {})
    if isinstance(top_level_aliases, dict):
        aliases.extend(
            alias
            for alias in top_level_aliases.get(role, [])
            if isinstance(alias, str) and alias.strip()
        )
    for group in contract.get("crossSlideEqualityGroups", []):
        if not isinstance(group, dict):
            continue
        group_aliases = group.get("roleAliases", {})
        if not isinstance(group_aliases, dict):
            continue
        aliases.extend(
            alias
            for alias in group_aliases.get(role, [])
            if isinstance(alias, str) and alias.strip()
        )
    return list(dict.fromkeys(aliases))


def records_for_contract_role(
    records: list[dict],
    contract: dict,
    role: str,
) -> list[dict]:
    accepted_names = [role, *contract_role_aliases(contract, role)]
    return [
        record
        for record in records
        if any(
            format_role_matches(record["name"], accepted_name)
            for accepted_name in accepted_names
        )
    ]


def validate_header_role_geometry(
    *,
    slide_number: int,
    slide_part: str,
    records: list[dict],
    contract: dict,
) -> tuple[list[dict], dict]:
    """Block title/subtitle overlap and dividers above subtitle bottom."""
    errors: list[dict] = []
    matched: dict[str, dict] = {}
    for role in ("action-title", "subtitle", "title-divider"):
        role_records = records_for_contract_role(records, contract, role)
        if len(role_records) == 1:
            matched[role] = role_records[0]

    title_geometry = (
        object_geometry_emu(matched["action-title"]["element"])
        if "action-title" in matched
        else None
    )
    subtitle_geometry = (
        object_geometry_emu(matched["subtitle"]["element"])
        if "subtitle" in matched
        else None
    )
    divider_geometry = (
        object_geometry_emu(matched["title-divider"]["element"])
        if "title-divider" in matched
        else None
    )
    if title_geometry is not None and subtitle_geometry is not None:
        overlap_width = max(
            0,
            min(
                title_geometry["x"] + title_geometry["w"],
                subtitle_geometry["x"] + subtitle_geometry["w"],
            )
            - max(title_geometry["x"], subtitle_geometry["x"]),
        )
        overlap_height = max(
            0,
            min(
                title_geometry["y"] + title_geometry["h"],
                subtitle_geometry["y"] + subtitle_geometry["h"],
            )
            - max(title_geometry["y"], subtitle_geometry["y"]),
        )
        if overlap_width > 0 and overlap_height > 0:
            errors.append({
                "kind": "format_header_role_overlap",
                "part": slide_part,
                "slide": slide_number,
                "roles": ["action-title", "subtitle"],
                "objects": [
                    matched["action-title"]["name"],
                    matched["subtitle"]["name"],
                ],
                "rule": "positive-area-overlap",
                "overlapEmu": {
                    "w": overlap_width,
                    "h": overlap_height,
                    "area": overlap_width * overlap_height,
                },
            })
    if subtitle_geometry is not None and divider_geometry is not None:
        subtitle_bottom = (
            subtitle_geometry["y"] + subtitle_geometry["h"]
        )
        if divider_geometry["y"] < subtitle_bottom:
            errors.append({
                "kind": "format_header_role_overlap",
                "part": slide_part,
                "slide": slide_number,
                "roles": ["subtitle", "title-divider"],
                "objects": [
                    matched["subtitle"]["name"],
                    matched["title-divider"]["name"],
                ],
                "rule": "divider-above-subtitle-bottom",
                "subtitleBottomEmu": subtitle_bottom,
                "dividerTopEmu": divider_geometry["y"],
                "deltaEmu": divider_geometry["y"] - subtitle_bottom,
            })
    return errors, {
        "roles": {
            role: {
                "object": record["name"],
                "geometryEmu": object_geometry_emu(record["element"]),
            }
            for role, record in matched.items()
        },
    }


def validate_action_title_policy(
    *,
    slide_number: int,
    slide_part: str,
    records: list[dict],
    contract: dict,
) -> tuple[list[dict], dict | None]:
    policy = contract.get("titlePolicy")
    if not isinstance(policy, dict):
        return [], None
    errors: list[dict] = []
    divider_matches = records_for_contract_role(
        records,
        contract,
        "title-divider",
    )
    if (
        policy.get("defaultTitleDividerPolicy") == "forbid"
        and divider_matches
    ):
        errors.append({
            "kind": "format_default_title_divider_forbidden",
            "part": slide_part,
            "slide": slide_number,
            "objects": [record["name"] for record in divider_matches],
        })
    matches = records_for_contract_role(records, contract, "action-title")
    if len(matches) != 1:
        return errors, {
            "objectCount": len(matches),
            "evaluated": False,
            "defaultTitleDividerPolicy": policy.get(
                "defaultTitleDividerPolicy"
            ),
        }
    record = matches[0]
    structure = action_title_text_structure(record["element"])
    if (
        policy.get("forbidMultipleParagraphs") is True
        and structure["nonEmptyParagraphCount"] > 1
    ):
        errors.append({
            "kind": "format_action_title_multiline",
            "part": slide_part,
            "slide": slide_number,
            "object": record["name"],
            "rule": "multiple-paragraphs",
            "actual": structure["nonEmptyParagraphCount"],
            "maximum": 1,
        })
    if (
        policy.get("forbidExplicitLineBreaks") is True
        and (
            structure["explicitBreakCount"] > 0
            or structure["newlineCharacterCount"] > 0
        )
    ):
        errors.append({
            "kind": "format_action_title_multiline",
            "part": slide_part,
            "slide": slide_number,
            "object": record["name"],
            "rule": "explicit-line-break",
            "explicitBreakCount": structure["explicitBreakCount"],
            "newlineCharacterCount": structure["newlineCharacterCount"],
        })
    maximum_weighted = policy.get("maxWeightedCharacters")
    if (
        isinstance(maximum_weighted, (int, float))
        and structure["weightedCharacters"] > float(maximum_weighted)
    ):
        errors.append({
            "kind": "format_action_title_width_budget_exceeded",
            "part": slide_part,
            "slide": slide_number,
            "object": record["name"],
            "actualWeightedCharacters": structure["weightedCharacters"],
            "maximumWeightedCharacters": float(maximum_weighted),
        })
    return errors, {
        "object": record["name"],
        "evaluated": True,
        **structure,
        "maximumWeightedCharacters": maximum_weighted,
        "defaultTitleDividerPolicy": policy.get(
            "defaultTitleDividerPolicy"
        ),
        "softWrapRequiresVisualGate": policy.get(
            "softWrapRequiresVisualGate",
            True,
        ),
    }


def validate_body_start_policy(
    *,
    slide_number: int,
    slide_part: str,
    records: list[dict],
    contract: dict,
    slide_contract: dict,
    header_contract: dict,
) -> tuple[list[dict], dict | None]:
    policy = contract.get("bodyStartPolicy")
    if not isinstance(policy, dict):
        return [], None
    body_start = header_contract.get("bodyStartY")
    if not isinstance(body_start, (int, float)):
        return [], None
    roles = slide_contract.get("bodyStartRoles")
    errors: list[dict] = []
    if policy.get("requireNamedAnchors") is True and not roles:
        errors.append({
            "kind": "format_body_start_roles_missing",
            "part": slide_part,
            "slide": slide_number,
            "headerMode": slide_contract.get("headerMode"),
        })
        return errors, {
            "bodyStartYIn": float(body_start),
            "roles": [],
        }
    if not isinstance(roles, list):
        return errors, None
    inventory = []
    for role in roles:
        matches = records_for_contract_role(records, contract, role)
        if len(matches) != 1:
            errors.append({
                "kind": "format_body_start_role_count_invalid",
                "part": slide_part,
                "slide": slide_number,
                "role": role,
                "actual": len(matches),
                "expected": 1,
            })
            continue
        record = matches[0]
        geometry = record.get("geometry")
        inventory.append({
            "role": role,
            "object": record["name"],
            "geometry": geometry,
        })
        if geometry is not None and geometry["y"] + 1e-9 < float(body_start):
            errors.append({
                "kind": "format_body_starts_above_header_clearance",
                "part": slide_part,
                "slide": slide_number,
                "role": role,
                "object": record["name"],
                "actualYIn": round(geometry["y"], 4),
                "minimumYIn": float(body_start),
                "deltaIn": round(geometry["y"] - float(body_start), 4),
            })
    return errors, {
        "bodyStartYIn": float(body_start),
        "roles": inventory,
    }


def validate_cross_slide_equality_groups(
    *,
    contract: dict,
    slide_contexts: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Enforce exact repeated chrome geometry and style across slide groups."""
    groups = contract.get("crossSlideEqualityGroups")
    if groups is None:
        return [], []
    if not isinstance(groups, list):
        # The loader reports this for file-backed contracts. Keep the direct
        # function safe for callers that use it independently in tests/tools.
        return [{
            "kind": "format_cross_slide_groups_invalid",
            "detail": "crossSlideEqualityGroups must be a list",
        }], []

    errors: list[dict] = []
    inventory: list[dict] = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        group_id = group.get("id") or f"group-{group_index + 1}"
        roles = [
            role
            for role in group.get("roles", [])
            if isinstance(role, str) and role.strip()
        ]
        if not roles:
            errors.append({
                "kind": "format_cross_slide_group_roles_invalid",
                "group": group_id,
                "detail": "roles[] must contain at least one role",
            })
            continue
        compare_fields_value = group.get("compareFields")
        compare_fields = (
            list(CROSS_SLIDE_COMPARE_FIELDS)
            if compare_fields_value is None
            else compare_fields_value
        )
        if (
            not isinstance(compare_fields, list)
            or not compare_fields
            or any(
                not isinstance(field, str)
                or field not in CROSS_SLIDE_COMPARE_FIELDS
                for field in compare_fields
            )
        ):
            errors.append({
                "kind": "format_cross_slide_group_compare_fields_invalid",
                "group": group_id,
                "actual": compare_fields_value,
                "allowed": sorted(CROSS_SLIDE_COMPARE_FIELDS),
            })
            compare_fields = list(CROSS_SLIDE_COMPARE_FIELDS)
        compare_fields_set = set(compare_fields)
        explicit_slides = group.get("slides")
        selector = group.get("slideSelector", {})
        if not isinstance(selector, dict):
            selector = {}
        selected = list(slide_contexts)
        if isinstance(explicit_slides, list):
            selected_slide_numbers = {
                slide
                for slide in explicit_slides
                if isinstance(slide, int)
            }
            missing_explicit_slides = sorted(
                selected_slide_numbers
                - {
                    context["slide"]
                    for context in slide_contexts
                }
            )
            if missing_explicit_slides:
                errors.append({
                    "kind": "format_cross_slide_group_slide_missing",
                    "group": group_id,
                    "slides": missing_explicit_slides,
                })
            selected = [
                context
                for context in selected
                if context["slide"] in selected_slide_numbers
            ]
        selected_header_modes = selector.get("headerModes")
        if isinstance(selected_header_modes, list):
            selected_header_modes = {
                value
                for value in selected_header_modes
                if isinstance(value, str)
            }
            selected = [
                context
                for context in selected
                if context.get("headerMode") in selected_header_modes
            ]
        selected_slide_roles = selector.get("slideRoles")
        if isinstance(selected_slide_roles, list):
            selected_slide_roles = {
                value
                for value in selected_slide_roles
                if isinstance(value, str)
            }
            selected = [
                context
                for context in selected
                if context.get("slideRole") in selected_slide_roles
            ]
        selected.sort(key=lambda context: context["slide"])
        if len(selected) < 2:
            errors.append({
                "kind": "format_cross_slide_group_insufficient_coverage",
                "group": group_id,
                "minimum": 2,
                "actual": len(selected),
                "slides": [
                    context["slide"]
                    for context in selected
                ],
                "explicitSlides": (
                    explicit_slides
                    if isinstance(explicit_slides, list)
                    else None
                ),
            })

        # Header modes are separate geometry systems. They remain isolated by
        # default even when a broad selector names several modes.
        partitions: dict[str, list[dict]] = {}
        if group.get("groupByHeaderMode", True):
            for context in selected:
                key = context.get("headerMode") or "<none>"
                partitions.setdefault(key, []).append(context)
        else:
            partitions["<mixed>"] = selected

        aliases_by_role = (
            group.get("roleAliases", {})
            if isinstance(group.get("roleAliases"), dict)
            else {}
        )
        tolerance_emu = group.get(
            "geometryToleranceEmu",
            group.get("toleranceEmu", 0),
        )
        if (
            not isinstance(tolerance_emu, int)
            or isinstance(tolerance_emu, bool)
            or tolerance_emu < 0
        ):
            tolerance_emu = 0
        requested_reference = group.get("referenceSlide")
        if (
            requested_reference is not None
            and requested_reference not in {
                context["slide"]
                for context in selected
            }
        ):
            errors.append({
                "kind": "format_cross_slide_reference_slide_missing",
                "group": group_id,
                "referenceSlide": requested_reference,
                "selectedSlides": [
                    context["slide"]
                    for context in selected
                ],
            })

        for partition_key, partition_contexts in sorted(partitions.items()):
            partition_inventory = {
                "group": group_id,
                "headerMode": partition_key,
                "slides": [
                    context["slide"]
                    for context in partition_contexts
                ],
                "referenceSlide": None,
                "geometryToleranceEmu": tolerance_emu,
                "compareFields": sorted(compare_fields_set),
                "roles": {},
            }
            if not partition_contexts:
                inventory.append(partition_inventory)
                continue
            reference_context = next(
                (
                    context
                    for context in partition_contexts
                    if context["slide"] == requested_reference
                ),
                partition_contexts[0],
            )
            partition_inventory["referenceSlide"] = (
                reference_context["slide"]
            )

            for role in roles:
                aliases = [
                    alias
                    for alias in aliases_by_role.get(role, [])
                    if isinstance(alias, str)
                ]
                accepted_names = [role, *aliases]
                role_items: list[dict] = []
                usable_records: dict[int, dict] = {}
                for context in partition_contexts:
                    matches = [
                        record
                        for record in context["records"]
                        if any(
                            format_role_matches(
                                record["name"],
                                accepted_name,
                            )
                            for accepted_name in accepted_names
                        )
                    ]
                    if len(matches) != 1:
                        errors.append({
                            "kind": "format_cross_slide_role_count_invalid",
                            "group": group_id,
                            "headerMode": partition_key,
                            "slide": context["slide"],
                            "part": context["part"],
                            "role": role,
                            "aliases": aliases,
                            "actual": len(matches),
                            "expected": 1,
                        })
                        role_items.append({
                            "slide": context["slide"],
                            "part": context["part"],
                            "object": None,
                            "status": "role-count-invalid",
                        })
                        continue
                    record = matches[0]
                    signature = object_cross_slide_signature(record)
                    usable_records[context["slide"]] = {
                        "record": record,
                        "signature": signature,
                    }
                    role_items.append({
                        "slide": context["slide"],
                        "part": context["part"],
                        "object": record["name"],
                        "geometryEmu": signature["geometryEmu"],
                        "objectType": signature["objectType"],
                        "rotation": signature["rotation"],
                        "styleHashes": {
                            field: style_hash(signature[signature_field])
                            for field, signature_field in (
                                ("fill", "fill"),
                                ("line", "line"),
                                ("textMargins", "textMarginsEmu"),
                                (
                                    "verticalAlignment",
                                    "verticalAlignment",
                                ),
                                ("font", "font"),
                                ("paragraph", "paragraph"),
                            )
                            if field in compare_fields_set
                        },
                        "status": "inventoried",
                    })
                partition_inventory["roles"][role] = role_items

                reference_item = usable_records.get(
                    reference_context["slide"]
                )
                if reference_item is None:
                    continue
                baseline = reference_item["signature"]
                for context in partition_contexts:
                    if context["slide"] == reference_context["slide"]:
                        continue
                    current_item = usable_records.get(context["slide"])
                    if current_item is None:
                        continue
                    actual = current_item["signature"]
                    expected_geometry = baseline["geometryEmu"]
                    actual_geometry = actual["geometryEmu"]
                    if (
                        "geometry" in compare_fields_set
                        and (
                            expected_geometry is None
                            or actual_geometry is None
                        )
                    ):
                        if expected_geometry != actual_geometry:
                            errors.append({
                                "kind": "format_cross_slide_geometry_missing",
                                "group": group_id,
                                "headerMode": partition_key,
                                "role": role,
                                "referenceSlide": reference_context["slide"],
                                "slide": context["slide"],
                                "part": context["part"],
                                "expected": expected_geometry,
                                "actual": actual_geometry,
                            })
                    elif "geometry" in compare_fields_set:
                        drift = {
                            key: {
                                "expected": expected_geometry[key],
                                "actual": actual_geometry[key],
                                "deltaEmu": (
                                    actual_geometry[key]
                                    - expected_geometry[key]
                                ),
                            }
                            for key in ("x", "y", "w", "h")
                            if abs(
                                actual_geometry[key]
                                - expected_geometry[key]
                            ) > tolerance_emu
                        }
                        if drift:
                            errors.append({
                                "kind": "format_cross_slide_geometry_drift",
                                "group": group_id,
                                "headerMode": partition_key,
                                "role": role,
                                "referenceSlide": reference_context["slide"],
                                "slide": context["slide"],
                                "part": context["part"],
                                "geometryToleranceEmu": tolerance_emu,
                                "drift": drift,
                            })

                    if (
                        "objectType" in compare_fields_set
                        and baseline["objectType"] != actual["objectType"]
                    ):
                        errors.append({
                            "kind": "format_cross_slide_object_type_drift",
                            "group": group_id,
                            "headerMode": partition_key,
                            "role": role,
                            "referenceSlide": reference_context["slide"],
                            "slide": context["slide"],
                            "part": context["part"],
                            "expected": baseline["objectType"],
                            "actual": actual["objectType"],
                        })

                    style_drift = {
                        field: {
                            "expectedHash": style_hash(
                                baseline[signature_field]
                            ),
                            "actualHash": style_hash(
                                actual[signature_field]
                            ),
                        }
                        for field, signature_field in (
                            ("rotation", "rotation"),
                            ("fill", "fill"),
                            ("line", "line"),
                            ("textMargins", "textMarginsEmu"),
                            (
                                "verticalAlignment",
                                "verticalAlignment",
                            ),
                            ("font", "font"),
                            ("paragraph", "paragraph"),
                        )
                        if (
                            field in compare_fields_set
                            and baseline[signature_field]
                            != actual[signature_field]
                        )
                    }
                    if style_drift:
                        errors.append({
                            "kind": "format_cross_slide_style_drift",
                            "group": group_id,
                            "headerMode": partition_key,
                            "role": role,
                            "referenceSlide": reference_context["slide"],
                            "slide": context["slide"],
                            "part": context["part"],
                            "fields": sorted(style_drift),
                            "drift": style_drift,
                        })
            inventory.append(partition_inventory)
    return errors, inventory


def validate_slide_format_contract(
    *,
    slide_number: int,
    slide_part: str,
    slide_root: ET.Element,
    slide_width_emu: int | None,
    slide_height_emu: int | None,
    contract: dict,
    slide_contract: dict,
) -> tuple[list[dict], dict]:
    errors: list[dict] = []
    tolerance = float(contract.get("deck", {}).get("toleranceIn", 0.03))
    records = slide_object_records(slide_root)
    names = [record["name"] for record in records if record["name"]]
    duplicate_names = sorted(
        name
        for name, count in Counter(names).items()
        if count > 1
    )
    if duplicate_names:
        errors.append({
            "kind": "format_role_object_name_duplicate",
            "part": slide_part,
            "slide": slide_number,
            "names": duplicate_names,
        })

    header_mode = slide_contract.get("headerMode", "none")
    header_modes = contract.get("headerModes", {})
    if (
        contract.get("titlePolicy", {}).get("maxActionTitleLines") == 1
        and "two-line" in str(header_mode).casefold()
    ):
        errors.append({
            "kind": "format_two_line_header_mode_forbidden",
            "part": slide_part,
            "slide": slide_number,
            "headerMode": header_mode,
        })
    header_contract = header_modes.get(header_mode)
    if header_contract is None:
        errors.append({
            "kind": "format_header_mode_unknown",
            "part": slide_part,
            "slide": slide_number,
            "headerMode": header_mode,
        })
        header_contract = {}

    required_roles = [
        *header_contract.get("requiredRoles", []),
        *slide_contract.get("requiredRoles", []),
    ]
    forbidden_roles = [
        *header_contract.get("forbiddenRoles", []),
        *slide_contract.get("forbiddenRoles", []),
    ]
    common_geometry = contract.get("roleGeometry", {})
    role_geometry = {
        **common_geometry,
        **header_contract.get("roleGeometry", {}),
        **slide_contract.get("roleGeometry", {}),
    }
    role_records: dict[str, list[dict]] = {}
    for role in set(required_roles + forbidden_roles + list(role_geometry)):
        role_records[role] = [
            record
            for record in records
            if format_role_matches(record["name"], role)
        ]
    for role in required_roles:
        matches = role_records.get(role, [])
        if len(matches) != 1:
            errors.append({
                "kind": "format_required_role_count_invalid",
                "part": slide_part,
                "slide": slide_number,
                "role": role,
                "actual": len(matches),
                "expected": 1,
            })
    for role in forbidden_roles:
        matches = role_records.get(role, [])
        if matches:
            errors.append({
                "kind": "format_forbidden_role_present",
                "part": slide_part,
                "slide": slide_number,
                "role": role,
                "actual": len(matches),
            })

    for role, expected_contract in role_geometry.items():
        matches = role_records.get(role, [])
        if len(matches) != 1:
            continue
        record = matches[0]
        allowed_types = expected_contract.get("objectTypes")
        if allowed_types and record["type"] not in allowed_types:
            errors.append({
                "kind": "format_role_object_type_invalid",
                "part": slide_part,
                "slide": slide_number,
                "role": role,
                "actual": record["type"],
                "expected": allowed_types,
            })
        expected_geometry = expected_contract.get("geometry", {})
        actual_geometry = record["geometry"]
        if expected_geometry and actual_geometry is None:
            errors.append({
                "kind": "format_role_geometry_missing",
                "part": slide_part,
                "slide": slide_number,
                "role": role,
            })
        elif expected_geometry:
            drift = {
                key: {
                    "actual": round(actual_geometry[key], 4),
                    "expected": float(expected_value),
                    "delta": round(actual_geometry[key] - float(expected_value), 4),
                }
                for key, expected_value in expected_geometry.items()
                if key in actual_geometry
                and abs(actual_geometry[key] - float(expected_value)) > tolerance
            }
            if drift:
                errors.append({
                    "kind": "format_role_geometry_drift",
                    "part": slide_part,
                    "slide": slide_number,
                    "role": role,
                    "toleranceIn": tolerance,
                    "drift": drift,
                })
        if expected_contract.get("zeroTextMargins") is True:
            margins = record["margins"]
            if margins is None or any(
                abs(value) > (1 / EMU_PER_INCH)
                for value in (margins or {}).values()
            ):
                errors.append({
                    "kind": "format_role_text_margin_not_zero",
                    "part": slide_part,
                    "slide": slide_number,
                    "role": role,
                    "actual": margins,
                })

    header_geometry_errors, header_geometry_inventory = (
        validate_header_role_geometry(
            slide_number=slide_number,
            slide_part=slide_part,
            records=records,
            contract=contract,
        )
    )
    errors.extend(header_geometry_errors)
    title_policy_errors, title_policy_inventory = (
        validate_action_title_policy(
            slide_number=slide_number,
            slide_part=slide_part,
            records=records,
            contract=contract,
        )
    )
    errors.extend(title_policy_errors)
    body_start_errors, body_start_inventory = (
        validate_body_start_policy(
            slide_number=slide_number,
            slide_part=slide_part,
            records=records,
            contract=contract,
            slide_contract=slide_contract,
            header_contract=header_contract,
        )
    )
    errors.extend(body_start_errors)

    counts = Counter(record["type"] for record in records)
    for object_kind, minimum in slide_contract.get(
        "nativeObjectMinimums",
        {},
    ).items():
        if counts.get(object_kind, 0) < int(minimum):
            errors.append({
                "kind": "native_object_minimum_not_met",
                "part": slide_part,
                "slide": slide_number,
                "objectType": object_kind,
                "actual": counts.get(object_kind, 0),
                "minimum": int(minimum),
            })
    for object_kind, maximum in slide_contract.get(
        "nativeObjectMaximums",
        {},
    ).items():
        if counts.get(object_kind, 0) > int(maximum):
            errors.append({
                "kind": "native_object_maximum_exceeded",
                "part": slide_part,
                "slide": slide_number,
                "objectType": object_kind,
                "actual": counts.get(object_kind, 0),
                "maximum": int(maximum),
            })

    connector_policy = slide_contract.get("connectorPolicy", {})
    connectors = [
        record
        for record in records
        if record["type"] == "connectors"
    ]
    if connector_policy.get("requireAttachedBothEnds") is True:
        unattached = [
            record["name"]
            for record in connectors
            if not (
                record["connector"]["startConnected"]
                and record["connector"]["endConnected"]
            )
        ]
        if unattached:
            errors.append({
                "kind": "native_connector_not_attached_both_ends",
                "part": slide_part,
                "slide": slide_number,
                "objects": unattached,
            })
    if connector_policy.get("requireArrowhead") is True:
        without_arrowhead = [
            record["name"]
            for record in connectors
            if not record["connector"]["hasArrowhead"]
        ]
        if without_arrowhead:
            errors.append({
                "kind": "native_connector_arrowhead_missing",
                "part": slide_part,
                "slide": slide_number,
                "objects": without_arrowhead,
            })

    slide_number_policy = contract.get(
        "nativeEditability",
        {},
    ).get("slideNumberPolicy", "inventory-only")
    page_number_records = [
        record
        for record in records
        if format_role_matches(record["name"], "page-number")
    ]
    slide_number_field_count = sum(
        1
        for record in page_number_records
        if any(
            field_type.casefold() in {"slidenum", "slide number"}
            for field_type in record["fieldTypes"]
        )
    )
    if (
        slide_number_policy == "field-required"
        and page_number_records
        and slide_number_field_count != len(page_number_records)
    ):
        errors.append({
            "kind": "slide_number_field_missing",
            "part": slide_part,
            "slide": slide_number,
            "actualFieldCount": slide_number_field_count,
            "pageNumberObjectCount": len(page_number_records),
        })

    full_slide_picture_count = 0
    slide_area = (
        slide_width_emu * slide_height_emu
        if slide_width_emu and slide_height_emu
        else None
    )
    coverage_threshold = float(
        contract.get("nativeEditability", {}).get(
            "fullSlideRasterCoverageThreshold",
            0.90,
        )
    )
    for record in records:
        if record["type"] != "pictures" or record["geometry"] is None or not slide_area:
            continue
        picture_area = (
            record["geometry"]["w"]
            * EMU_PER_INCH
            * record["geometry"]["h"]
            * EMU_PER_INCH
        )
        if picture_area / slide_area >= coverage_threshold:
            full_slide_picture_count += 1
    if (
        contract.get("nativeEditability", {}).get("allowFullSlideRaster") is False
        and full_slide_picture_count
    ):
        errors.append({
            "kind": "full_slide_raster_detected",
            "part": slide_part,
            "slide": slide_number,
            "count": full_slide_picture_count,
            "coverageThreshold": coverage_threshold,
        })

    hierarchy_roles = contract.get("hierarchy", {}).get(
        "roles",
        ["action-title", "subtitle", "takeaway"],
    )
    hierarchy_text = {}
    for role in hierarchy_roles:
        matches = [
            record
            for record in records
            if format_role_matches(record["name"], role)
            and record["text"]
        ]
        if len(matches) == 1:
            hierarchy_text[role] = matches[0]["text"]
    similarity_threshold = float(
        contract.get("hierarchy", {}).get("similarityThreshold", 0.72)
    )
    for left_index, left_role in enumerate(hierarchy_roles):
        for right_role in hierarchy_roles[left_index + 1:]:
            left_text = hierarchy_text.get(left_role)
            right_text = hierarchy_text.get(right_role)
            if not left_text or not right_text:
                continue
            left_normalized = normalize_hierarchy_text(left_text)
            right_normalized = normalize_hierarchy_text(right_text)
            contains = (
                min(len(left_normalized), len(right_normalized)) >= 6
                and (
                    left_normalized in right_normalized
                    or right_normalized in left_normalized
                )
            )
            similarity = bigram_similarity(left_text, right_text)
            if contains or similarity >= similarity_threshold:
                errors.append({
                    "kind": "format_hierarchy_text_redundant",
                    "part": slide_part,
                    "slide": slide_number,
                    "roles": [left_role, right_role],
                    "contains": contains,
                    "similarity": round(similarity, 4),
                    "threshold": similarity_threshold,
                })

    takeaway_policy = contract.get("takeawayPolicy", {})
    if (
        takeaway_policy.get("requireNamedBottomTextBlocks") is True
        and slide_contract.get("slideRole") not in {"cover", "navigator"}
    ):
        bottom_band_y = float(
            takeaway_policy.get("bottomBandYIn", 6.20)
        )
        allowed_bottom_roles = {
            *takeaway_policy.get(
                "allowedBottomRoles",
                ["takeaway", "source-footnote", "page-number"],
            ),
        }
        unclassified_bottom_text = []
        for record in records:
            geometry = record["geometry"]
            if (
                record["type"] != "textBoxes"
                or not record["text"]
                or geometry is None
                or geometry["y"] < bottom_band_y
            ):
                continue
            if any(
                format_role_matches(record["name"], role)
                for role in allowed_bottom_roles
            ):
                continue
            unclassified_bottom_text.append({
                "object": record["name"],
                "y": round(geometry["y"], 4),
            })
        if unclassified_bottom_text:
            errors.append({
                "kind": "format_bottom_text_role_unclassified",
                "part": slide_part,
                "slide": slide_number,
                "bottomBandYIn": bottom_band_y,
                "objects": unclassified_bottom_text,
            })

    return errors, {
        "slide": slide_number,
        "part": slide_part,
        "slideRole": slide_contract.get("slideRole"),
        "headerMode": header_mode,
        "nativeObjectCounts": dict(sorted(counts.items())),
        "connectorEditability": {
            "count": len(connectors),
            "attachedBothEnds": sum(
                1
                for record in connectors
                if (
                    record["connector"]["startConnected"]
                    and record["connector"]["endConnected"]
                )
            ),
            "withArrowhead": sum(
                1
                for record in connectors
                if record["connector"]["hasArrowhead"]
            ),
        },
        "slideNumberFieldCount": slide_number_field_count,
        "fullSlidePictureCount": full_slide_picture_count,
        "hierarchyRolesPresent": sorted(hierarchy_text),
        "headerRoleGeometry": header_geometry_inventory,
        "actionTitleSingleLine": title_policy_inventory,
        "bodyStart": body_start_inventory,
    }


def source_for_rels(path: str) -> str | None:
    if path == "_rels/.rels":
        return None
    parent, filename = posixpath.split(path)
    if not parent.endswith("/_rels"):
        return ""
    source_dir = parent[: -len("/_rels")]
    return posixpath.join(source_dir, filename[: -len(".rels")])


def resolve_target(source: str | None, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    base = "" if source is None else posixpath.dirname(source)
    return posixpath.normpath(posixpath.join(base, target))


def redacted_external_target(target: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}/<redacted>"
    if parsed.scheme:
        return f"{parsed.scheme}:<redacted>"
    return "<external-target-redacted>"


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(
    path: str,
    theme_policy: str = "ksib",
    font_policy: str = "ksib",
    format_contract_path: str | None = None,
) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    format_contract, contract_findings = load_format_contract(
        format_contract_path
    )
    errors.extend(contract_findings)
    format_contract_sha256 = (
        sha256_file(format_contract_path)
        if format_contract is not None and format_contract_path is not None
        else None
    )
    format_contract_inventory: list[dict] = []
    cross_slide_equality_inventory: list[dict] = []
    external_relationships: list[dict] = []
    media_parts: list[str] = []
    embedded_parts: list[str] = []
    direct_typeface_inventory: dict[str, list[str]] = {}
    theme_typeface_inventory: dict[str, dict[str, str | None]] = {}
    direct_point_size_inventory: dict[str, list[float]] = {}
    chart_data_inventory: list[dict] = []
    with zipfile.ZipFile(path) as archive:
        bad_crc_part = archive.testzip()
        if bad_crc_part:
            errors.append({"kind": "zip_crc_failure", "part": bad_crc_part})
        names = archive.namelist()
        name_set = set(names)
        media_parts = sorted(
            name for name in names
            if name.startswith("ppt/media/") and not name.endswith("/")
        )
        embedded_parts = sorted(
            name for name in names
            if (
                name.startswith("ppt/embeddings/")
                or "oleObject" in name
                or name.lower().endswith("vbaproject.bin")
            )
            and not name.endswith("/")
        )
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            errors.append({"kind": "macro_payload_present"})
        if embedded_parts:
            warnings.append({
                "kind": "embedded_payload_present",
                "count": len(embedded_parts),
                "parts": embedded_parts[:20],
            })
        duplicates = [name for name, count in Counter(names).items() if count > 1]
        if duplicates:
            errors.append({"kind": "duplicate_zip_entry", "parts": duplicates})

        xml_parts: dict[str, ET.Element] = {}
        for name in names:
            if not (name.endswith(".xml") or name.endswith(".rels")):
                continue
            try:
                xml_parts[name] = ET.fromstring(archive.read(name))
            except ET.ParseError as exc:
                errors.append({"kind": "malformed_xml", "part": name, "detail": str(exc)})

        content_root = xml_parts.get("[Content_Types].xml")
        defaults: dict[str, str] = {}
        overrides: dict[str, str] = {}
        if content_root is None:
            errors.append({"kind": "missing_content_types"})
        else:
            default_entries = []
            override_entries = []
            for child in content_root:
                if local_name(child.tag) == "Default":
                    default_entries.append(child.get("Extension"))
                    defaults[child.get("Extension", "").lower()] = child.get("ContentType", "")
                elif local_name(child.tag) == "Override":
                    key = child.get("PartName", "").lstrip("/")
                    override_entries.append(key)
                    overrides[key] = child.get("ContentType", "")
            for key, count in Counter(default_entries).items():
                if count > 1:
                    errors.append({"kind": "duplicate_content_default", "extension": key})
            for key, count in Counter(override_entries).items():
                if count > 1:
                    errors.append({"kind": "duplicate_content_override", "part": key})
            for name in names:
                if name.endswith("/") or name == "[Content_Types].xml":
                    continue
                if name in overrides:
                    continue
                basename = PurePosixPath(name).name
                extension = basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
                if extension not in defaults:
                    errors.append({"kind": "missing_content_type", "part": name})

        rel_ids_by_source: dict[str | None, set[str]] = {}
        relationships_by_source: dict[
            str | None,
            dict[str, ET.Element],
        ] = {}
        presentation_for_geometry = xml_parts.get("ppt/presentation.xml")
        slide_width_emu: int | None = None
        slide_height_emu: int | None = None
        if presentation_for_geometry is not None:
            slide_size = presentation_for_geometry.find(f"./{P}sldSz")
            if slide_size is not None:
                try:
                    slide_width_emu = int(slide_size.get("cx", ""))
                    slide_height_emu = int(slide_size.get("cy", ""))
                except ValueError:
                    slide_width_emu = None
                    slide_height_emu = None

        for name, root in xml_parts.items():
            if not name.endswith(".rels"):
                continue
            source = source_for_rels(name)
            if source not in (None, "") and source not in name_set:
                errors.append({"kind": "relationship_source_missing", "part": name, "source": source})
            ids = [rel.get("Id", "") for rel in root]
            rel_ids_by_source[source] = set(ids)
            relationships_by_source[source] = {
                rel.get("Id", ""): rel
                for rel in root
                if rel.get("Id")
            }
            for rel_id, count in Counter(ids).items():
                if count > 1:
                    errors.append({"kind": "duplicate_relationship_id", "part": name, "id": rel_id})
            for rel in root:
                if rel.get("TargetMode") == "External":
                    finding = {
                        "kind": "external_relationship",
                        "part": name,
                        "id": rel.get("Id"),
                        "type": (rel.get("Type", "").rsplit("/", 1)[-1]),
                        "target": redacted_external_target(rel.get("Target", "")),
                    }
                    external_relationships.append(finding)
                    warnings.append(finding)
                    continue
                target = resolve_target(source, rel.get("Target", ""))
                if target not in name_set:
                    errors.append({
                        "kind": "missing_relationship_target",
                        "part": name,
                        "id": rel.get("Id"),
                        "target": target,
                    })

        presentation_part = "ppt/presentation.xml"
        presentation_root = xml_parts.get(presentation_part)
        root_relationships = relationships_by_source.get(None, {})
        office_document_relationships = [
            relationship
            for relationship in root_relationships.values()
            if relationship.get("Type", "").endswith("/officeDocument")
            and relationship.get("TargetMode") != "External"
        ]
        if len(office_document_relationships) != 1:
            errors.append({
                "kind": "office_document_relationship_invalid",
                "count": len(office_document_relationships),
            })
        elif resolve_target(
            None,
            office_document_relationships[0].get("Target", ""),
        ) != presentation_part:
            errors.append({
                "kind": "office_document_relationship_target_invalid",
                "target": redacted_external_target(
                    office_document_relationships[0].get("Target", "")
                ),
            })
        if presentation_root is None:
            errors.append({"kind": "missing_presentation_part"})
        if overrides.get(presentation_part) != PRESENTATION_CONTENT_TYPE:
            errors.append({
                "kind": "presentation_content_type_invalid",
                "actual": overrides.get(presentation_part),
                "expected": PRESENTATION_CONTENT_TYPE,
            })

        actual_slide_parts = sorted(
            name
            for name in name_set
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        )
        referenced_slide_parts: list[str] = []
        if presentation_root is not None:
            slide_ids = list(presentation_root.iter(f"{P}sldId"))
            if not slide_ids:
                errors.append({"kind": "presentation_has_no_slides"})
            presentation_relationships = relationships_by_source.get(
                presentation_part,
                {},
            )
            slide_relationship_ids: list[str] = []
            for slide_index, slide_id in enumerate(slide_ids, start=1):
                relationship_id = slide_id.get(f"{{{OFFICE_REL_NS}}}id")
                if not relationship_id:
                    errors.append({
                        "kind": "slide_relationship_id_missing",
                        "slide": slide_index,
                    })
                    continue
                slide_relationship_ids.append(relationship_id)
                relationship = presentation_relationships.get(
                    relationship_id
                )
                if relationship is None:
                    errors.append({
                        "kind": "slide_relationship_missing",
                        "slide": slide_index,
                        "id": relationship_id,
                    })
                    continue
                if (
                    not relationship.get("Type", "").endswith("/slide")
                    or relationship.get("TargetMode") == "External"
                ):
                    errors.append({
                        "kind": "slide_relationship_type_invalid",
                        "slide": slide_index,
                        "id": relationship_id,
                    })
                    continue
                target = resolve_target(
                    presentation_part,
                    relationship.get("Target", ""),
                )
                referenced_slide_parts.append(target)
                if not re.fullmatch(r"ppt/slides/slide\d+\.xml", target):
                    errors.append({
                        "kind": "slide_relationship_target_invalid",
                        "slide": slide_index,
                        "target": target,
                    })
            duplicate_slide_relationship_ids = [
                relationship_id
                for relationship_id, count in Counter(
                    slide_relationship_ids
                ).items()
                if count > 1
            ]
            if duplicate_slide_relationship_ids:
                errors.append({
                    "kind": "duplicate_slide_relationship_reference",
                    "ids": duplicate_slide_relationship_ids,
                })
        if sorted(referenced_slide_parts) != actual_slide_parts:
            errors.append({
                "kind": "presentation_slide_part_set_mismatch",
                "referenced": sorted(referenced_slide_parts),
                "actual": actual_slide_parts,
            })
        for slide_part in actual_slide_parts:
            if overrides.get(slide_part) != SLIDE_CONTENT_TYPE:
                errors.append({
                    "kind": "slide_content_type_invalid",
                    "part": slide_part,
                    "actual": overrides.get(slide_part),
                    "expected": SLIDE_CONTENT_TYPE,
                })

        for name, root in xml_parts.items():
            if name.endswith(".rels") or name == "[Content_Types].xml":
                continue
            referenced_ids = set()
            for element in root.iter():
                for key, value in element.attrib.items():
                    if key.startswith("{" + OFFICE_REL_NS + "}"):
                        referenced_ids.add(value)
            missing = referenced_ids - rel_ids_by_source.get(name, set())
            for rel_id in sorted(missing):
                errors.append({"kind": "missing_relationship_id", "part": name, "id": rel_id})

            parent_by_child = {child: parent for parent in root.iter() for child in parent}
            cnvpr = [element for element in root.iter() if local_name(element.tag) == "cNvPr"]
            ids = [element.get("id") for element in cnvpr]
            for object_id, count in Counter(ids).items():
                if object_id is None or count <= 1:
                    continue
                elements_for_id = [element for element in cnvpr if element.get("id") == object_id]
                root_group_reuse = any(
                    local_name(parent_by_child[element].tag) == "nvGrpSpPr"
                    for element in elements_for_id
                )
                finding = {
                    "kind": "root_group_object_id_reuse" if root_group_reuse else "duplicate_nonvisual_object_id",
                    "part": name,
                    "id": object_id,
                    "names": [element.get("name") for element in elements_for_id],
                }
                (warnings if root_group_reuse else errors).append(finding)

            if EDITABLE_TEXT_MEMBER_RE.fullmatch(name):
                editability_locks: list[dict[str, str]] = []
                for element in root.iter():
                    active_attributes = sorted(
                        attribute
                        for attribute in EDITABILITY_LOCK_ATTRIBUTES
                        if str(element.get(attribute, "")).lower() in {"1", "true"}
                    )
                    if not active_attributes:
                        continue
                    owning_object = nearest_named_object(
                        element,
                        parent_by_child,
                    )
                    if is_notes_placeholder(name, owning_object):
                        continue
                    owning_name = object_name(owning_object) or "<part-text>"
                    editability_locks.extend(
                        {
                            "object": owning_name,
                            "attribute": attribute,
                        }
                        for attribute in active_attributes
                    )
                if editability_locks:
                    errors.append({
                        "kind": "native_editability_locks",
                        "part": name,
                        "count": len(editability_locks),
                        "locks": editability_locks[:20],
                    })

                redundant_colors_by_object: Counter[str] = Counter()
                paragraph_bold_by_object: Counter[str] = Counter()
                for paragraph in root.iter(f"{A}p"):
                    owning_object = nearest_named_object(
                        paragraph,
                        parent_by_child,
                    )
                    owning_name = object_name(owning_object) or "<part-text>"
                    paragraph_properties = paragraph.find(f"./{A}pPr")
                    default_properties = (
                        paragraph_properties.find(f"./{A}defRPr")
                        if paragraph_properties is not None
                        else None
                    )
                    has_visible_run_text = any(
                        "".join(
                            text_node.text or ""
                            for text_node in run.iter(f"{A}t")
                        ).strip()
                        for run_tag in ("r", "fld")
                        for run in paragraph.findall(f"./{A}{run_tag}")
                    )
                    if (
                        default_properties is not None
                        and default_properties.get("b") is not None
                        and has_visible_run_text
                    ):
                        paragraph_bold_by_object[owning_name] += 1
                    default_fill = fill_signature(default_properties)
                    if default_fill is None:
                        continue
                    run_properties = []
                    for run_tag in ("r", "br", "fld"):
                        for run in paragraph.findall(f"./{A}{run_tag}"):
                            properties = run.find(f"./{A}rPr")
                            if properties is not None:
                                run_properties.append(properties)
                    end_properties = paragraph.find(f"./{A}endParaRPr")
                    if end_properties is not None:
                        run_properties.append(end_properties)
                    redundant_colors_by_object[owning_name] += sum(
                        1
                        for properties in run_properties
                        if fill_signature(properties) == default_fill
                    )
                for owning_name, count in sorted(
                    redundant_colors_by_object.items()
                ):
                    if count:
                        errors.append({
                            "kind": "redundant_run_text_color",
                            "part": name,
                            "object": owning_name,
                            "count": count,
                        })
                for owning_name, count in sorted(
                    paragraph_bold_by_object.items()
                ):
                    if count:
                        errors.append({
                            "kind": "paragraph_default_bold_blocks_toggle",
                            "part": name,
                            "object": owning_name,
                            "count": count,
                        })

            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                slide_text = "".join(
                    element.text or "" for element in root.iter(f"{A}t")
                )
                unresolved = [
                    marker for marker in UNRESOLVED_MARKERS if marker in slide_text
                ]
                if unresolved:
                    errors.append({
                        "kind": "unresolved_placeholder",
                        "part": name,
                        "markers": unresolved,
                    })

                direct_typefaces = sorted({
                    element.get("typeface", "").strip()
                    for element in root.iter()
                    if local_name(element.tag) in {"latin", "ea", "cs"}
                    and element.get("typeface", "").strip()
                })
                if direct_typefaces:
                    direct_typeface_inventory[name] = direct_typefaces
                unapproved_typefaces = [
                    typeface for typeface in direct_typefaces
                    if typeface not in APPROVED_TYPEFACES
                    and not typeface.startswith("+")
                ]
                if unapproved_typefaces:
                    finding = {
                        "kind": "unapproved_direct_typeface",
                        "part": name,
                        "typefaces": unapproved_typefaces,
                    }
                    (errors if font_policy == "ksib" else warnings).append(finding)

                direct_point_sizes: set[float] = set()
                direct_point_size_records: list[
                    tuple[ET.Element, float]
                ] = []
                invalid_font_size_values: list[str] = []
                for element in root.iter():
                    if local_name(element.tag) not in {
                        "rPr",
                        "defRPr",
                        "endParaRPr",
                    }:
                        continue
                    raw_size = element.get("sz")
                    if raw_size is None:
                        continue
                    try:
                        numeric_size = int(raw_size)
                    except ValueError:
                        invalid_font_size_values.append(raw_size)
                        continue
                    if numeric_size <= 0:
                        invalid_font_size_values.append(raw_size)
                        continue
                    point_size = numeric_size / 100
                    direct_point_sizes.add(point_size)
                    direct_point_size_records.append((element, point_size))
                if direct_point_sizes:
                    direct_point_size_inventory[name] = sorted(direct_point_sizes)
                if invalid_font_size_values:
                    errors.append({
                        "kind": "invalid_direct_font_size",
                        "part": name,
                        "values": sorted(set(invalid_font_size_values)),
                    })
                unapproved_point_sizes = sorted(
                    size
                    for size in direct_point_sizes
                    if size not in APPROVED_POINT_SIZES
                )
                if unapproved_point_sizes:
                    finding = {
                        "kind": "unapproved_direct_font_size",
                        "part": name,
                        "pointSizes": unapproved_point_sizes,
                        "approvedPointSizes": sorted(APPROVED_POINT_SIZES),
                    }
                    (errors if font_policy == "ksib" else warnings).append(finding)

                undersized_body_findings: list[dict] = []
                for properties, point_size in direct_point_size_records:
                    if point_size not in {9, 10}:
                        continue
                    owning_object = nearest_named_object(
                        properties,
                        parent_by_child,
                    )
                    owning_name = object_name(owning_object)
                    allowed_tokens = (
                        NINE_POINT_ROLE_TOKENS
                        if point_size == 9
                        else TEN_POINT_ROLE_TOKENS
                    )
                    semantic_role_allowed = object_name_matches_text_role(
                        owning_name,
                        allowed_tokens,
                    )
                    vertical_offset = object_vertical_offset(owning_object)
                    bottom_zone_allowed = (
                        slide_height_emu is not None
                        and vertical_offset is not None
                        and vertical_offset
                        >= slide_height_emu * (0.86 if point_size == 9 else 0.84)
                    )
                    if not semantic_role_allowed and not bottom_zone_allowed:
                        undersized_body_findings.append({
                            "object": owning_name,
                            "pointSize": point_size,
                            "verticalOffset": vertical_offset,
                        })
                if undersized_body_findings:
                    finding = {
                        "kind": "body_text_font_size_below_minimum",
                        "part": name,
                        "count": len(undersized_body_findings),
                        "items": undersized_body_findings[:20],
                        "rule": (
                            "9pt仅允许来源/脚注/页脚/页码；"
                            "10pt仅允许上述角色或明确命名的附录密集表"
                        ),
                    }
                    (errors if font_policy == "ksib" else warnings).append(finding)

            for element in root.iter():
                if local_name(element.tag) != "ext":
                    continue
                for attribute in ("cx", "cy"):
                    value = element.get(attribute)
                    if value is None:
                        continue
                    try:
                        numeric_value = int(value)
                    except ValueError:
                        errors.append({
                            "kind": "invalid_positive_size",
                            "part": name,
                            "attribute": attribute,
                            "value": value,
                        })
                        continue
                    if numeric_value < 0:
                        errors.append({
                            "kind": "negative_positive_size",
                            "part": name,
                            "attribute": attribute,
                            "value": numeric_value,
                        })

        chart_parts = sorted(
            name
            for name, root in xml_parts.items()
            if (
                not name.endswith(".rels")
                and local_name(root.tag) == "chartSpace"
            )
        )
        chart_data_inventory = [
            chart_data_mode(
                chart_part=chart_part,
                chart_root=xml_parts[chart_part],
                relationships_by_source=relationships_by_source,
            )
            for chart_part in chart_parts
        ]

        if format_contract is not None:
            slide_number_policy = format_contract.get(
                "nativeEditability",
                {},
            ).get("slideNumberPolicy", "inventory-only")
            if slide_number_policy not in {
                "inventory-only",
                "static-allowed",
                "field-required",
            }:
                errors.append({
                    "kind": "format_slide_number_policy_invalid",
                    "actual": slide_number_policy,
                })
            chart_data_policy = format_contract.get(
                "nativeEditability",
                {},
            ).get("chartDataPolicy", "inventory-only")
            if chart_data_policy not in {
                "inventory-only",
                "native-data-required",
                "embedded-workbook-required",
            }:
                errors.append({
                    "kind": "format_chart_data_policy_invalid",
                    "actual": chart_data_policy,
                })
            elif chart_data_policy == "native-data-required":
                invalid_charts = [
                    item["part"]
                    for item in chart_data_inventory
                    if item["mode"] == "unknown"
                ]
                if invalid_charts:
                    errors.append({
                        "kind": "native_chart_data_missing",
                        "parts": invalid_charts,
                    })
            elif chart_data_policy == "embedded-workbook-required":
                invalid_charts = [
                    {
                        "part": item["part"],
                        "mode": item["mode"],
                    }
                    for item in chart_data_inventory
                    if item["mode"] != "embeddedWorkbook"
                ]
                if invalid_charts:
                    errors.append({
                        "kind": "embedded_chart_workbook_missing",
                        "charts": invalid_charts,
                    })

            contract_slides = {
                item["slide"]: item
                for item in format_contract.get("slides", [])
                if isinstance(item, dict)
                and isinstance(item.get("slide"), int)
            }
            actual_slide_numbers = set(
                range(1, len(referenced_slide_parts) + 1)
            )
            contract_slide_numbers = set(contract_slides)
            if (
                format_contract.get("deck", {}).get(
                    "requireAllSlides",
                    True,
                )
                and contract_slide_numbers != actual_slide_numbers
            ):
                errors.append({
                    "kind": "format_contract_slide_set_mismatch",
                    "actual": sorted(actual_slide_numbers),
                    "contract": sorted(contract_slide_numbers),
                })

            expected_width = format_contract.get("deck", {}).get("widthIn")
            expected_height = format_contract.get("deck", {}).get("heightIn")
            tolerance = float(
                format_contract.get("deck", {}).get(
                    "toleranceIn",
                    0.03,
                )
            )
            actual_dimensions = {
                "widthIn": (
                    slide_width_emu / EMU_PER_INCH
                    if slide_width_emu is not None
                    else None
                ),
                "heightIn": (
                    slide_height_emu / EMU_PER_INCH
                    if slide_height_emu is not None
                    else None
                ),
            }
            dimension_drift = {}
            for key, expected in (
                ("widthIn", expected_width),
                ("heightIn", expected_height),
            ):
                actual = actual_dimensions[key]
                if (
                    expected is not None
                    and (
                        actual is None
                        or abs(actual - float(expected)) > tolerance
                    )
                ):
                    dimension_drift[key] = {
                        "actual": (
                            round(actual, 4)
                            if actual is not None
                            else None
                        ),
                        "expected": float(expected),
                    }
            if dimension_drift:
                errors.append({
                    "kind": "format_contract_slide_size_drift",
                    "toleranceIn": tolerance,
                    "drift": dimension_drift,
                })

            takeaway_slide_numbers: list[int] = []
            content_slide_numbers: list[int] = []
            cross_slide_contexts: list[dict] = []
            for slide_number, slide_part in enumerate(
                referenced_slide_parts,
                start=1,
            ):
                slide_contract = contract_slides.get(slide_number)
                slide_root = xml_parts.get(slide_part)
                if slide_contract is None or slide_root is None:
                    continue
                slide_errors, slide_inventory = (
                    validate_slide_format_contract(
                        slide_number=slide_number,
                        slide_part=slide_part,
                        slide_root=slide_root,
                        slide_width_emu=slide_width_emu,
                        slide_height_emu=slide_height_emu,
                        contract=format_contract,
                        slide_contract=slide_contract,
                    )
                )
                errors.extend(slide_errors)
                format_contract_inventory.append(slide_inventory)
                cross_slide_contexts.append({
                    "slide": slide_number,
                    "part": slide_part,
                    "slideRole": slide_contract.get("slideRole"),
                    "headerMode": slide_contract.get(
                        "headerMode",
                        "none",
                    ),
                    "records": slide_object_records(slide_root),
                })
                slide_role = slide_contract.get("slideRole")
                if slide_role not in {
                    "cover",
                    "navigator",
                    "appendix",
                }:
                    content_slide_numbers.append(slide_number)
                records = slide_object_records(slide_root)
                has_takeaway = any(
                    format_role_matches(record["name"], "takeaway")
                    and record["text"]
                    for record in records
                )
                if has_takeaway:
                    takeaway_slide_numbers.append(slide_number)

            cross_slide_errors, cross_slide_equality_inventory = (
                validate_cross_slide_equality_groups(
                    contract=format_contract,
                    slide_contexts=cross_slide_contexts,
                )
            )
            errors.extend(cross_slide_errors)

            takeaway_policy = format_contract.get(
                "takeawayPolicy",
                {},
            )
            max_ratio = float(
                takeaway_policy.get("maxContentSlideRatio", 0.25)
            )
            max_count = (
                max(1, int(len(content_slide_numbers) * max_ratio))
                if content_slide_numbers
                else 0
            )
            if len(takeaway_slide_numbers) > max_count:
                errors.append({
                    "kind": "format_takeaway_overuse",
                    "actual": len(takeaway_slide_numbers),
                    "maximum": max_count,
                    "contentSlideCount": len(content_slide_numbers),
                    "slides": takeaway_slide_numbers,
                })
            max_consecutive = int(
                takeaway_policy.get("maxConsecutive", 1)
            )
            streak: list[int] = []
            for slide_number in takeaway_slide_numbers:
                if streak and slide_number == streak[-1] + 1:
                    streak.append(slide_number)
                else:
                    streak = [slide_number]
                if len(streak) > max_consecutive:
                    errors.append({
                        "kind": "format_takeaway_consecutive_overuse",
                        "maximum": max_consecutive,
                        "slides": streak.copy(),
                    })
                    break

        theme_parts = sorted(
            name
            for name in xml_parts
            if name.startswith("ppt/theme/theme") and name.endswith(".xml")
        )
        if not theme_parts:
            errors.append({"kind": "missing_theme_part"})
        for name in theme_parts:
            root = xml_parts[name]
            schemes = list(root.iter(f"{A}clrScheme"))
            if len(schemes) != 1:
                errors.append({
                    "kind": "invalid_theme_color_scheme",
                    "part": name,
                    "count": len(schemes),
                })
                continue
            scheme = schemes[0]
            if theme_policy == "ksib" and scheme.get("name") != KSIB_THEME_NAME:
                errors.append({
                    "kind": "unapproved_theme_color_scheme_name",
                    "part": name,
                    "actual": scheme.get("name"),
                    "expected": KSIB_THEME_NAME,
                })
            for slot_name, expected in KSIB_THEME_COLORS.items():
                slots = scheme.findall(f"./{A}{slot_name}")
                actual = None
                if len(slots) == 1 and len(slots[0]) == 1:
                    child = slots[0][0]
                    if child.tag == f"{A}srgbClr":
                        actual = child.get("val")
                if theme_policy == "ksib" and actual != expected:
                    errors.append({
                        "kind": "unapproved_theme_color",
                        "part": name,
                        "slot": slot_name,
                        "actual": actual,
                        "expected": expected,
                    })

            font_schemes = list(root.iter(f"{A}fontScheme"))
            if len(font_schemes) != 1:
                finding = {
                    "kind": "invalid_theme_font_scheme",
                    "part": name,
                    "count": len(font_schemes),
                }
                (errors if font_policy == "ksib" else warnings).append(
                    finding
                )
                continue
            font_scheme = font_schemes[0]
            if (
                font_policy == "ksib"
                and font_scheme.get("name") != KSIB_THEME_FONT_NAME
            ):
                errors.append({
                    "kind": "unapproved_theme_font_scheme_name",
                    "part": name,
                    "actual": font_scheme.get("name"),
                    "expected": KSIB_THEME_FONT_NAME,
                })
            typefaces: dict[str, str | None] = {}
            for family_name in ("majorFont", "minorFont"):
                families = font_scheme.findall(f"./{A}{family_name}")
                if len(families) != 1:
                    finding = {
                        "kind": "invalid_theme_font_family",
                        "part": name,
                        "family": family_name,
                        "count": len(families),
                    }
                    (
                        errors
                        if font_policy == "ksib"
                        else warnings
                    ).append(finding)
                    continue
                for slot_name in ("latin", "ea", "cs"):
                    slots = families[0].findall(f"./{A}{slot_name}")
                    key = f"{family_name}.{slot_name}"
                    value = (
                        slots[0].get("typeface")
                        if len(slots) == 1
                        else None
                    )
                    typefaces[key] = value
                    if len(slots) != 1 or value not in APPROVED_TYPEFACES:
                        finding = {
                            "kind": "unapproved_theme_typeface",
                            "part": name,
                            "slot": key,
                            "actual": value,
                            "approvedTypefaces": sorted(
                                APPROVED_TYPEFACES
                            ),
                        }
                        (
                            errors
                            if font_policy == "ksib"
                            else warnings
                        ).append(finding)
            theme_typeface_inventory[name] = typefaces

        app_root = xml_parts.get("docProps/app.xml")
        presentation_root = xml_parts.get("ppt/presentation.xml")
        if app_root is not None and presentation_root is not None:
            slide_count = sum(1 for element in presentation_root.iter() if local_name(element.tag) == "sldId")
            note_count = sum(
                1 for name in names
                if name.startswith("ppt/notesSlides/notesSlide") and name.endswith(".xml")
            )
            app_values = {local_name(element.tag): (element.text or "") for element in app_root}
            for key, actual in (("Slides", slide_count), ("Notes", note_count)):
                stated = app_values.get(key)
                if stated != str(actual):
                    warnings.append({
                        "kind": "extended_property_count_mismatch",
                        "property": key,
                        "stated": stated,
                        "actual": actual,
                    })

    return {
        "file": Path(path).name,
        "sha256": sha256_file(path),
        "errors": errors,
        "warnings": warnings,
        "inventory": {
            "mediaCount": len(media_parts),
            "mediaParts": media_parts,
            "embeddedCount": len(embedded_parts),
            "externalRelationshipCount": len(external_relationships),
            "externalRelationships": external_relationships,
            "directTypefacesByPart": direct_typeface_inventory,
            "directPointSizesByPart": direct_point_size_inventory,
            "themeTypefacesByPart": theme_typeface_inventory,
            "chartDataByPart": chart_data_inventory,
            "formatContractSha256": format_contract_sha256,
            "formatContractSlides": format_contract_inventory,
            "crossSlideEqualityGroups": cross_slide_equality_inventory,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx", nargs="+")
    parser.add_argument(
        "--theme-policy",
        choices=["ksib", "preserve"],
        default="ksib",
        help="ksib enforces the approved palette; preserve only audits package integrity",
    )
    parser.add_argument(
        "--font-policy",
        choices=["ksib", "preserve"],
        default="ksib",
        help="ksib enforces approved direct typefaces; preserve inventories existing fonts without blocking",
    )
    parser.add_argument(
        "--format-contract",
        help=(
            "optional ksib-format-contract/1.0 JSON that enforces "
            "role geometry, hierarchy, native object types, and raster limits"
        ),
    )
    parser.add_argument(
        "--output",
        help="optional JSON report path",
    )
    args = parser.parse_args()
    reports = [
        audit(
            path,
            theme_policy=args.theme_policy,
            font_policy=args.font_policy,
            format_contract_path=args.format_contract,
        )
        for path in args.pptx
    ]
    errors = [
        {"file": report["file"], **error}
        for report in reports
        for error in report["errors"]
    ]
    warnings = [
        {"file": report["file"], **warning}
        for report in reports
        for warning in report["warnings"]
    ]
    output = {
        "schemaVersion": "ksib-ooxml-qa/2.0",
        "validatorSha256": sha256_file(__file__),
        "themePolicy": args.theme_policy,
        "fontPolicy": args.font_policy,
        "formatContract": (
            {
                "file": Path(args.format_contract).name,
                "sha256": sha256_file(args.format_contract),
            }
            if args.format_contract and Path(args.format_contract).is_file()
            else None
        ),
        "passed": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "reports": reports,
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    raise SystemExit(0 if output["passed"] else 1)


if __name__ == "__main__":
    main()
