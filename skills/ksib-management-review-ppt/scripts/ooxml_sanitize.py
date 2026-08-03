#!/usr/bin/env python3
"""Sanitize PowerPoint compatibility and native editability issues.

The artifact-tool exporter currently gives both the root shape tree and the
first user-visible slide object ``cNvPr id="1"``.  This utility changes only
the root ``p:nvGrpSpPr/p:cNvPr`` ID when it is invalid or duplicates another
object on the same slide. It also removes generated ``noGrp``, ``noMove``,
``noResize``, ``noSelect`` and ``noTextEdit`` locks so native objects remain
directly editable, collapses redundant run-level text colors, and moves
effective paragraph-default bold onto text runs before removing the default
override so selected text can be restyled predictably. It then
synchronizes the extended-properties
``Slides`` and ``Notes`` counts with the package members.  Existing theme parts
are rewritten to the approved KSIB/Kwai color scheme by default. Format-only
work may use ``--preserve-theme``; in that mode theme bytes are preserved while
redundant text-format overrides are still normalized. The semantic fingerprint
compares effective visible colors and bold state, not redundant storage. ZIP
entry order, compression method,
timestamps, attributes, extras, comments, and the archive comment are preserved.
"""

from __future__ import annotations

import argparse
import copy
import io
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Sequence
import xml.etree.ElementTree as ET
import zipfile

from lxml import etree


PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
EXTENDED_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
P = f"{{{PRESENTATION_NS}}}"
AP = f"{{{EXTENDED_PROPERTIES_NS}}}"
MAX_DRAWING_ID = (1 << 32) - 1
SLIDE_MEMBER_RE = re.compile(r"ppt/slides/slide\d+\.xml\Z")
NOTES_MEMBER_RE = re.compile(r"ppt/notesSlides/notesSlide\d+\.xml\Z")
EDITABLE_TEXT_MEMBER_RE = re.compile(
    r"ppt/(?:"
    r"slides/slide\d+|"
    r"notesSlides/notesSlide\d+|"
    r"(?:charts|slides/charts)/chart\d+|"
    r"diagrams/(?:data|drawing)\d+"
    r")\.xml\Z"
)
APP_PROPERTIES_MEMBER = "docProps/app.xml"
THEME_MEMBER_RE = re.compile(r"ppt/theme/theme\d+\.xml\Z")
NS = {"a": DRAWING_NS, "p": PRESENTATION_NS}
TEXT_FILL_NAMES = {
    "solidFill",
    "gradFill",
    "noFill",
    "pattFill",
    "blipFill",
    "grpFill",
}
EDITABILITY_LOCK_ATTRIBUTES = {
    "noGrp",
    "noMove",
    "noResize",
    "noSelect",
    "noTextEdit",
}
KSIB_THEME_NAME = "KSIB Management Review Orange"
KSIB_THEME_FONT_NAME = "KSIB Management Review Chinese"
KSIB_PRIMARY_TYPEFACE = "PingFang SC"
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


class SanitizeError(RuntimeError):
    """Raised when a package cannot be rewritten without broad changes."""


def _parse_drawing_id(value: str | None) -> int | None:
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    parsed = int(value, 10)
    if not 1 <= parsed <= MAX_DRAWING_ID:
        return None
    return parsed


def _namespace_prefix(
    xml_bytes: bytes, namespace_uri: str, member_name: str, preferred: str
) -> str:
    prefixes: list[str] = []
    try:
        for _event, namespace in ET.iterparse(
            io.BytesIO(xml_bytes), events=("start-ns",)
        ):
            prefix, uri = namespace
            if uri == namespace_uri and prefix not in prefixes:
                prefixes.append(prefix)
    except ET.ParseError as exc:
        raise SanitizeError(f"{member_name}: invalid XML: {exc}") from exc
    if not prefixes:
        raise SanitizeError(
            f"{member_name}: namespace declaration not found: {namespace_uri}"
        )
    return preferred if preferred in prefixes else prefixes[0]


def _root_id_span(
    xml_bytes: bytes, prefix: str, member_name: str
) -> tuple[int, int, str | None]:
    qualified = f"{prefix}:".encode("ascii") if prefix else b""
    group_tag = re.escape(qualified + b"nvGrpSpPr")
    properties_tag = re.escape(qualified + b"cNvPr")
    between = rb"(?:\s|<!--.*?-->)*"
    pattern = re.compile(
        rb"<"
        + group_tag
        + rb"\b[^>]*>"
        + between
        + rb"(?P<properties><"
        + properties_tag
        + rb"\b[^>]*>)",
        re.DOTALL,
    )
    matches = list(pattern.finditer(xml_bytes))
    if len(matches) != 1:
        raise SanitizeError(
            f"{member_name}: expected one root shape-tree ID in source bytes; "
            f"found {len(matches)}"
        )
    match = matches[0]
    properties = match.group("properties")
    id_pattern = re.compile(
        rb"(?<![:\w.-])id\s*=\s*(?P<quote>[\"'])(?P<id>[^\"']*)(?P=quote)"
    )
    id_matches = list(id_pattern.finditer(properties))
    if len(id_matches) > 1:
        raise SanitizeError(f"{member_name}: root cNvPr has multiple id attributes")
    if not id_matches:
        insertion = match.start("properties") + 1 + len(qualified + b"cNvPr")
        return insertion, insertion, None
    id_match = id_matches[0]
    try:
        raw_id = id_match.group("id").decode("ascii")
    except UnicodeDecodeError as exc:
        raise SanitizeError(f"{member_name}: root shape-tree ID is not ASCII") from exc
    relative_start, relative_end = id_match.span("id")
    start = match.start("properties") + relative_start
    end = match.start("properties") + relative_end
    return start, end, raw_id


def _slide_id_state(
    xml_bytes: bytes, member_name: str
) -> tuple[ET.Element, list[ET.Element]]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise SanitizeError(f"{member_name}: invalid XML: {exc}") from exc

    shape_tree = root.find(f"./{P}cSld/{P}spTree")
    if shape_tree is None:
        raise SanitizeError(f"{member_name}: p:cSld/p:spTree not found")
    root_properties = shape_tree.find(f"./{P}nvGrpSpPr/{P}cNvPr")
    if root_properties is None:
        raise SanitizeError(
            f"{member_name}: p:nvGrpSpPr/p:cNvPr not found"
        )
    all_properties = list(root.iter(f"{P}cNvPr"))
    if root_properties not in all_properties:
        raise SanitizeError(f"{member_name}: root cNvPr is not part of the slide")
    return root_properties, all_properties


def _audit_non_root_ids(
    root_properties: ET.Element,
    all_properties: list[ET.Element],
    member_name: str,
) -> list[int]:
    values: list[int] = []
    for properties in all_properties:
        if properties is root_properties:
            continue
        raw_value = properties.get("id")
        parsed = _parse_drawing_id(raw_value)
        if parsed is None:
            raise SanitizeError(
                f"{member_name}: non-root cNvPr has invalid id={raw_value!r}; "
                "refusing to change a user object"
            )
        values.append(parsed)
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        joined = ", ".join(str(value) for value in duplicates)
        raise SanitizeError(
            f"{member_name}: duplicate non-root cNvPr IDs ({joined}); "
            "refusing to remap user objects or references"
        )
    return values


def sanitize_slide(xml_bytes: bytes, member_name: str) -> tuple[bytes, bool]:
    """Return slide XML with only the root shape-tree ID changed if needed."""

    root_properties, all_properties = _slide_id_state(xml_bytes, member_name)
    other_ids = _audit_non_root_ids(root_properties, all_properties, member_name)
    root_raw = root_properties.get("id")
    root_id = _parse_drawing_id(root_raw)
    needs_change = root_id is None or root_id in set(other_ids)
    if not needs_change:
        return xml_bytes, False

    numeric_ids = list(other_ids)
    if root_id is not None:
        numeric_ids.append(root_id)
    replacement_id = max(numeric_ids, default=0) + 1
    if replacement_id > MAX_DRAWING_ID:
        raise SanitizeError(
            f"{member_name}: max cNvPr ID leaves no valid max(existing)+1 value"
        )

    prefix = _namespace_prefix(xml_bytes, PRESENTATION_NS, member_name, "p")
    start, end, raw_source_id = _root_id_span(xml_bytes, prefix, member_name)
    if raw_source_id != root_raw:
        raise SanitizeError(
            f"{member_name}: parsed root id={root_raw!r} does not match "
            f"source id={raw_source_id!r}"
        )

    replacement = str(replacement_id).encode("ascii")
    if raw_source_id is None:
        replacement = b' id="' + replacement + b'"'
    rewritten = xml_bytes[:start] + replacement + xml_bytes[end:]

    check_root, check_all = _slide_id_state(rewritten, member_name)
    check_values: list[int] = []
    for properties in check_all:
        parsed = _parse_drawing_id(properties.get("id"))
        if parsed is None:
            raise SanitizeError(f"{member_name}: invalid cNvPr ID after rewrite")
        check_values.append(parsed)
    if check_root.get("id") != str(replacement_id):
        raise SanitizeError(f"{member_name}: root ID verification failed")
    if len(check_values) != len(set(check_values)):
        raise SanitizeError(f"{member_name}: duplicate cNvPr IDs remain after rewrite")
    return rewritten, True


def _fill_child(properties: etree._Element) -> etree._Element | None:
    fills = [
        child
        for child in properties
        if etree.QName(child).localname in TEXT_FILL_NAMES
    ]
    return fills[0] if len(fills) == 1 else None


def _canonical_xml(element: etree._Element) -> bytes:
    return etree.tostring(
        element, method="c14n", exclusive=True, with_comments=False
    )


def normalize_slide_editability(
    xml_bytes: bytes,
    member_name: str,
    preserve_text_color_structure: bool = False,
) -> tuple[bytes, int, int, int]:
    """Remove grouping locks and normalise directly editable text formatting."""

    parser = etree.XMLParser(remove_blank_text=False)
    try:
        root = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as exc:
        raise SanitizeError(f"{member_name}: invalid XML: {exc}") from exc

    group_locks_removed = 0
    redundant_colors_removed = 0
    bold_runs_materialized = 0

    for lock in root.iter():
        for attribute in EDITABILITY_LOCK_ATTRIBUTES:
            if str(lock.get(attribute, "")).lower() in {"1", "true"}:
                del lock.attrib[attribute]
                group_locks_removed += 1

    for paragraph in root.xpath(".//a:p", namespaces=NS):
        default_nodes = paragraph.xpath("./a:pPr/a:defRPr", namespaces=NS)
        if len(default_nodes) != 1:
            continue
        default_fill = _fill_child(default_nodes[0])
        default_signature = (
            _canonical_xml(default_fill) if default_fill is not None else None
        )
        default_bold = default_nodes[0].get("b")
        run_nodes = paragraph.xpath("./a:r | ./a:br | ./a:fld", namespaces=NS)
        run_properties: list[etree._Element] = []
        for run in run_nodes:
            properties = run.find("./a:rPr", namespaces=NS)
            if properties is None:
                properties = etree.Element(etree.QName(DRAWING_NS, "rPr"))
                run.insert(0, properties)
            run_properties.append(properties)
        end_properties = paragraph.find("./a:endParaRPr", namespaces=NS)
        color_properties = list(run_properties)
        if end_properties is not None:
            color_properties.append(end_properties)
        if not preserve_text_color_structure:
            for properties in color_properties:
                run_fill = _fill_child(properties)
                if (
                    run_fill is not None
                    and default_signature is not None
                    and _canonical_xml(run_fill) == default_signature
                ):
                    properties.remove(run_fill)
                    redundant_colors_removed += 1
        if default_bold is not None and run_properties:
            effective_bold = (
                "1" if str(default_bold).lower() in {"1", "true"} else "0"
            )
            for properties in run_properties:
                if properties.get("b") is None:
                    properties.set("b", effective_bold)
                    bold_runs_materialized += 1
            if end_properties is not None and end_properties.get("b") is None:
                end_properties.set("b", effective_bold)
            # Keeping the weight only at paragraph-default level can prevent
            # PowerPoint from truly cancelling bold on imported text. Once the
            # effective weight has been materialized on runs, remove that
            # default so the Bold toggle directly controls the selected text.
            del default_nodes[0].attrib["b"]

    if (
        not group_locks_removed
        and not redundant_colors_removed
        and not bold_runs_materialized
    ):
        return xml_bytes, 0, 0, 0
    payload = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    return (
        payload,
        group_locks_removed,
        redundant_colors_removed,
        bold_runs_materialized,
    )


def normalize_ksib_theme(xml_bytes: bytes, member_name: str) -> tuple[bytes, bool]:
    """Rewrite one theme part to the approved KSIB color and font schemes."""

    parser = etree.XMLParser(remove_blank_text=False)
    try:
        root = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as exc:
        raise SanitizeError(f"{member_name}: invalid XML: {exc}") from exc

    schemes = root.xpath(".//a:themeElements/a:clrScheme", namespaces=NS)
    if len(schemes) != 1:
        raise SanitizeError(
            f"{member_name}: expected one a:clrScheme; found {len(schemes)}"
        )
    scheme = schemes[0]
    changed = scheme.get("name") != KSIB_THEME_NAME
    scheme.set("name", KSIB_THEME_NAME)

    for slot_name, color in KSIB_THEME_COLORS.items():
        slots = scheme.xpath(f"./a:{slot_name}", namespaces=NS)
        if len(slots) != 1:
            raise SanitizeError(
                f"{member_name}: expected one a:{slot_name}; found {len(slots)}"
            )
        slot = slots[0]
        current = slot.xpath("./a:srgbClr/@val", namespaces=NS)
        if current != [color] or len(slot) != 1:
            changed = True
            for child in list(slot):
                slot.remove(child)
            color_node = etree.SubElement(
                slot, etree.QName(DRAWING_NS, "srgbClr")
            )
            color_node.set("val", color)

    font_schemes = root.xpath(
        ".//a:themeElements/a:fontScheme",
        namespaces=NS,
    )
    if len(font_schemes) > 1:
        raise SanitizeError(
            f"{member_name}: expected at most one a:fontScheme; "
            f"found {len(font_schemes)}"
        )
    if font_schemes:
        font_scheme = font_schemes[0]
    else:
        theme_elements = root.xpath(
            ".//a:themeElements",
            namespaces=NS,
        )
        if len(theme_elements) != 1:
            raise SanitizeError(
                f"{member_name}: expected one a:themeElements; "
                f"found {len(theme_elements)}"
            )
        font_scheme = etree.Element(
            etree.QName(DRAWING_NS, "fontScheme")
        )
        color_index = theme_elements[0].index(scheme)
        theme_elements[0].insert(color_index + 1, font_scheme)
        changed = True
    if font_scheme.get("name") != KSIB_THEME_FONT_NAME:
        font_scheme.set("name", KSIB_THEME_FONT_NAME)
        changed = True
    for family_name in ("majorFont", "minorFont"):
        families = font_scheme.xpath(
            f"./a:{family_name}",
            namespaces=NS,
        )
        if len(families) > 1:
            raise SanitizeError(
                f"{member_name}: expected at most one a:{family_name}; "
                f"found {len(families)}"
            )
        if families:
            family = families[0]
        else:
            family = etree.Element(
                etree.QName(DRAWING_NS, family_name)
            )
            if family_name == "majorFont":
                font_scheme.insert(0, family)
            else:
                major_families = font_scheme.xpath(
                    "./a:majorFont",
                    namespaces=NS,
                )
                insertion_index = (
                    font_scheme.index(major_families[0]) + 1
                    if major_families
                    else len(font_scheme)
                )
                font_scheme.insert(insertion_index, family)
            changed = True
        for slot_name in ("latin", "ea", "cs"):
            slots = family.xpath(
                f"./a:{slot_name}",
                namespaces=NS,
            )
            if len(slots) > 1:
                raise SanitizeError(
                    f"{member_name}: expected at most one "
                    f"a:{family_name}/a:{slot_name}; found {len(slots)}"
                )
            if slots:
                slot = slots[0]
            else:
                slot = etree.SubElement(
                    family,
                    etree.QName(DRAWING_NS, slot_name),
                )
                changed = True
            if slot.get("typeface") != KSIB_PRIMARY_TYPEFACE:
                slot.set("typeface", KSIB_PRIMARY_TYPEFACE)
                changed = True

    if not changed:
        return xml_bytes, False
    return (
        etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        ),
        True,
    )


def _element_text_span(
    xml_bytes: bytes, prefix: str, local_name: str, member_name: str
) -> tuple[int, int, bytes]:
    qualified = f"{prefix}:".encode("ascii") if prefix else b""
    tag = re.escape(qualified + local_name.encode("ascii"))
    pattern = re.compile(
        rb"<" + tag + rb"\b[^>]*>(?P<text>[^<]*)</" + tag + rb"\s*>",
        re.DOTALL,
    )
    matches = list(pattern.finditer(xml_bytes))
    if len(matches) != 1:
        raise SanitizeError(
            f"{member_name}: expected one {local_name} text node in source "
            f"bytes; found {len(matches)}"
        )
    match = matches[0]
    start, end = match.span("text")
    return start, end, match.group("text")


def sanitize_app_properties(
    xml_bytes: bytes, slide_count: int, notes_count: int, member_name: str
) -> tuple[bytes, bool]:
    """Synchronize app.xml Slides and Notes while preserving all other bytes."""

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise SanitizeError(f"{member_name}: invalid XML: {exc}") from exc
    expected = {"Slides": slide_count, "Notes": notes_count}
    for local_name in expected:
        elements = list(root.iter(f"{AP}{local_name}"))
        if len(elements) != 1:
            raise SanitizeError(
                f"{member_name}: expected one {local_name} element; "
                f"found {len(elements)}"
            )

    prefix = _namespace_prefix(
        xml_bytes, EXTENDED_PROPERTIES_NS, member_name, "ap"
    )
    replacements: list[tuple[int, int, bytes]] = []
    for local_name, count in expected.items():
        start, end, raw_text = _element_text_span(
            xml_bytes, prefix, local_name, member_name
        )
        try:
            decoded = raw_text.decode("ascii")
        except UnicodeDecodeError as exc:
            raise SanitizeError(
                f"{member_name}: {local_name} count is not ASCII"
            ) from exc
        leading = decoded[: len(decoded) - len(decoded.lstrip())]
        trailing = decoded[len(decoded.rstrip()) :]
        replacement = f"{leading}{count}{trailing}".encode("ascii")
        if replacement != raw_text:
            replacements.append((start, end, replacement))

    if not replacements:
        return xml_bytes, False
    rewritten = xml_bytes
    for start, end, replacement in sorted(replacements, reverse=True):
        rewritten = rewritten[:start] + replacement + rewritten[end:]

    try:
        check_root = ET.fromstring(rewritten)
    except ET.ParseError as exc:
        raise SanitizeError(
            f"{member_name}: invalid XML after count rewrite: {exc}"
        ) from exc
    for local_name, count in expected.items():
        elements = list(check_root.iter(f"{AP}{local_name}"))
        if len(elements) != 1 or (elements[0].text or "").strip() != str(count):
            raise SanitizeError(
                f"{member_name}: {local_name} count verification failed"
            )
    return rewritten, True


def _rewrite_package(
    source_path: Path,
    temporary_path: Path,
    normalize_theme: bool = True,
    preserve_text_color_structure: bool = False,
) -> tuple[int, int, int, bool | None, int, int, int, int]:
    root_ids_changed = 0
    app_properties_changed: bool | None = None
    group_locks_removed = 0
    redundant_colors_removed = 0
    bold_runs_materialized = 0
    themes_rewritten = 0
    try:
        with zipfile.ZipFile(source_path, "r") as source:
            infos = source.infolist()
            names = [info.filename for info in infos]
            duplicate_names = sorted({name for name in names if names.count(name) > 1})
            if duplicate_names:
                raise SanitizeError(
                    "archive contains duplicate member names: "
                    + ", ".join(duplicate_names)
                )
            slide_count = sum(
                1 for info in infos if SLIDE_MEMBER_RE.fullmatch(info.filename)
            )
            notes_count = sum(
                1 for info in infos if NOTES_MEMBER_RE.fullmatch(info.filename)
            )
            if slide_count == 0:
                raise SanitizeError(
                    "archive contains no ppt/slides/slide*.xml members"
                )
            with zipfile.ZipFile(
                temporary_path, "w", allowZip64=True, strict_timestamps=False
            ) as destination:
                destination.comment = source.comment
                for info in infos:
                    content = source.read(info)
                    if SLIDE_MEMBER_RE.fullmatch(info.filename):
                        content, changed = sanitize_slide(content, info.filename)
                        root_ids_changed += int(changed)
                    if EDITABLE_TEXT_MEMBER_RE.fullmatch(info.filename):
                        content, locks_removed, colors_removed, bold_materialized = (
                            normalize_slide_editability(
                                content,
                                info.filename,
                                preserve_text_color_structure=preserve_text_color_structure,
                            )
                        )
                        group_locks_removed += locks_removed
                        redundant_colors_removed += colors_removed
                        bold_runs_materialized += bold_materialized
                    if info.filename == APP_PROPERTIES_MEMBER:
                        content, app_properties_changed = sanitize_app_properties(
                            content, slide_count, notes_count, info.filename
                        )
                    elif normalize_theme and THEME_MEMBER_RE.fullmatch(info.filename):
                        content, changed = normalize_ksib_theme(
                            content, info.filename
                        )
                        themes_rewritten += int(changed)
                    destination.writestr(copy.copy(info), content)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, SanitizeError):
            raise
        raise SanitizeError(str(exc)) from exc
    return (
        slide_count,
        root_ids_changed,
        notes_count,
        app_properties_changed,
        group_locks_removed,
        redundant_colors_removed,
        bold_runs_materialized,
        themes_rewritten,
    )


def sanitize_pptx(
    source_path: Path,
    destination_path: Path,
    normalize_theme: bool = True,
    preserve_text_color_structure: bool = False,
) -> tuple[int, int, int, bool | None, int, int, int, int]:
    source_path = source_path.expanduser().resolve()
    destination_path = destination_path.expanduser().resolve()
    if not source_path.is_file():
        raise SanitizeError(f"input file does not exist: {source_path}")
    if not zipfile.is_zipfile(source_path):
        raise SanitizeError(f"input is not a ZIP/OOXML package: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
        dir=destination_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        result = _rewrite_package(
            source_path,
            temporary_path,
            normalize_theme,
            preserve_text_color_structure,
        )
        source_mode = stat.S_IMODE(source_path.stat().st_mode)
        os.chmod(temporary_path, source_mode)
        os.replace(temporary_path, destination_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize PowerPoint package IDs, grouping permissions, text-color "
            "inheritance, KSIB theme colors, and extended-property counts."
        )
    )
    parser.add_argument("input", type=Path, help="source .pptx path")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="destination .pptx path; may be the same as input",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="atomically replace INPUT via a temporary file and os.replace",
    )
    parser.add_argument(
        "--preserve-theme",
        action="store_true",
        help="do not rewrite theme color schemes; required when format-only color semantics are frozen",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.in_place and args.output is not None:
        parser.error("OUTPUT and --in-place are mutually exclusive")
    if not args.in_place and args.output is None:
        parser.error("provide OUTPUT or use --in-place")

    source_path: Path = args.input
    destination_path: Path = source_path if args.in_place else args.output
    assert destination_path is not None
    try:
        (
            slide_count,
            root_ids_changed,
            notes_count,
            app_changed,
            group_locks_removed,
            redundant_colors_removed,
            bold_runs_materialized,
            themes_rewritten,
        ) = sanitize_pptx(
            source_path,
            destination_path,
            normalize_theme=not args.preserve_theme,
            # Theme preservation freezes the palette, not redundant character
            # overrides. Removing a run-level color that exactly equals the
            # paragraph default keeps the effective color unchanged and makes
            # PowerPoint's color control act on the selected text directly.
            preserve_text_color_structure=False,
        )
    except SanitizeError as exc:
        print(f"ooxml_sanitize: error: {exc}", file=sys.stderr)
        return 2

    app_status = "absent" if app_changed is None else (
        "changed" if app_changed else "unchanged"
    )
    print(
        "ooxml_sanitize: "
        f"slides={slide_count} root_ids_changed={root_ids_changed} "
        f"root_ids_unchanged={slide_count - root_ids_changed} "
        f"notes={notes_count} app_properties={app_status} "
        f"editability_locks_removed={group_locks_removed} "
        f"redundant_run_colors_removed={redundant_colors_removed} "
        f"run_bold_materialized={bold_runs_materialized} "
        f"theme_policy={'preserve' if args.preserve_theme else 'ksib'} "
        f"themes_rewritten={themes_rewritten} "
        f"output={destination_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
