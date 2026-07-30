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
A = f"{{{DRAWING_NS}}}"
P = f"{{{PRESENTATION_NS}}}"
TEXT_FILL_NAMES = {
    "solidFill",
    "gradFill",
    "noFill",
    "pattFill",
    "blipFill",
    "grpFill",
}
KSIB_THEME_NAME = "KSIB Management Review Orange"
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
    "appendix",
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
    r"charts/chart\d+|"
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
) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    external_relationships: list[dict] = []
    media_parts: list[str] = []
    embedded_parts: list[str] = []
    direct_typeface_inventory: dict[str, list[str]] = {}
    direct_point_size_inventory: dict[str, list[float]] = {}
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
        slide_height_emu: int | None = None
        if presentation_for_geometry is not None:
            slide_size = presentation_for_geometry.find(f"./{P}sldSz")
            if slide_size is not None and slide_size.get("cy"):
                try:
                    slide_height_emu = int(slide_size.get("cy", ""))
                except ValueError:
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
    args = parser.parse_args()
    reports = [
        audit(
            path,
            theme_policy=args.theme_policy,
            font_policy=args.font_policy,
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
        "passed": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "reports": reports,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if output["passed"] else 1)


if __name__ == "__main__":
    main()
