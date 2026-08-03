#!/usr/bin/env python3
"""Audit or normalize repeated PowerPoint chrome without changing visible text.

The tool operates directly on PresentationML with only the Python standard
library.  It is intentionally conservative:

* the source PPTX is never overwritten;
* audit/dry-run is the default;
* every requested role must resolve to exactly one named shape on every
  selected slide;
* ambiguous or missing role matches block apply;
* target text nodes are never replaced.

For mixed-layout decks, invoke the tool once per page profile and use
``--slides`` to select the slides that share the canonical chrome.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import posixpath
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


PRESENTATION_NS = (
    "http://schemas.openxmlformats.org/presentationml/2006/main"
)
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
OFFICE_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PACKAGE_REL_NS = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
P = f"{{{PRESENTATION_NS}}}"
A = f"{{{DRAWING_NS}}}"
R = f"{{{OFFICE_REL_NS}}}"
PR = f"{{{PACKAGE_REL_NS}}}"

FILL_NAMES = {
    "noFill",
    "solidFill",
    "gradFill",
    "blipFill",
    "pattFill",
    "grpFill",
}
SHAPE_NAMES = {"sp", "cxnSp", "pic", "graphicFrame", "grpSp"}
TEXT_RUN_NAMES = {"r", "fld", "br"}
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


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def canonical_xml(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    return ET.tostring(element, encoding="unicode")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_part(base_part: str, target: str) -> str:
    # OPC relationship targets may be package-absolute PartNames such as
    # ``/ppt/slides/slide1.xml``.  zipfile member names never carry that
    # leading slash.
    if target.startswith("/"):
        return posixpath.normpath(target).lstrip("/")
    return posixpath.normpath(
        posixpath.join(posixpath.dirname(base_part), target)
    )


def presentation_slide_parts(members: dict[str, bytes]) -> list[str]:
    presentation_name = "ppt/presentation.xml"
    rels_name = "ppt/_rels/presentation.xml.rels"
    if presentation_name not in members or rels_name not in members:
        raise ValueError("PPTX缺少presentation.xml或其关系文件")
    presentation = ET.fromstring(members[presentation_name])
    rels = ET.fromstring(members[rels_name])
    targets = {
        rel.get("Id"): rel.get("Target")
        for rel in rels.findall(f"./{PR}Relationship")
        if rel.get("Id") and rel.get("Target")
    }
    slide_parts: list[str] = []
    slide_id_list = presentation.find(f"./{P}sldIdLst")
    if slide_id_list is None:
        raise ValueError("PPTX没有sldIdLst")
    for slide_id in slide_id_list.findall(f"./{P}sldId"):
        relationship_id = slide_id.get(f"{R}id")
        target = targets.get(relationship_id)
        if target is None:
            raise ValueError(f"无法解析slide关系: {relationship_id}")
        part = resolve_part(presentation_name, target)
        if part not in members:
            raise ValueError(f"slide part不存在: {part}")
        slide_parts.append(part)
    return slide_parts


def shape_name(shape: ET.Element) -> str:
    for candidate in shape.iter():
        if local_name(candidate.tag) == "cNvPr":
            return candidate.get("name", "")
    return ""


def iter_named_shapes(root: ET.Element) -> Iterable[ET.Element]:
    for element in root.iter():
        if local_name(element.tag) not in SHAPE_NAMES:
            continue
        if shape_name(element):
            yield element


def parse_roles(role_args: list[str], roles_csv: str | None) -> list[str]:
    values: list[str] = []
    for raw in role_args:
        values.extend(raw.split(","))
    if roles_csv:
        values.extend(roles_csv.split(","))
    roles: list[str] = []
    for value in values:
        role = value.strip()
        if role and role not in roles:
            roles.append(role)
    if not roles:
        raise ValueError("至少需要一个--role或--roles")
    return roles


def load_aliases(
    roles: list[str],
    alias_args: list[str],
    alias_map_path: str | None,
) -> dict[str, list[str]]:
    aliases = {role: [rf"^{re.escape(role)}$"] for role in roles}
    raw_map: dict[str, object] = {}
    if alias_map_path:
        with Path(alias_map_path).open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("--alias-map必须是JSON对象")
        raw_map.update(loaded)

    # Accept either {"role": ["regex", ...]} or {"legacy-name": "role"}.
    for key, value in raw_map.items():
        if key in aliases:
            patterns = value if isinstance(value, list) else [value]
            for pattern in patterns:
                if not isinstance(pattern, str):
                    raise ValueError(f"别名规则必须是字符串: {key}")
                aliases[key].append(pattern)
        elif isinstance(value, str) and value in aliases:
            aliases[value].append(rf"^{re.escape(key)}$")
        else:
            raise ValueError(f"无法解析别名映射: {key}")

    for raw in alias_args:
        if "=" not in raw:
            raise ValueError("--alias格式必须为ROLE=REGEX")
        role, pattern = raw.split("=", 1)
        role = role.strip()
        if role not in aliases:
            raise ValueError(f"--alias引用了未声明role: {role}")
        aliases[role].append(pattern)

    for role, patterns in aliases.items():
        for pattern in patterns:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"{role}的别名正则无效: {exc}") from exc
    return aliases


def role_matches(name: str, role: str, aliases: dict[str, list[str]]) -> bool:
    return any(
        re.fullmatch(pattern, name, flags=re.IGNORECASE)
        for pattern in aliases[role]
    )


def parse_slide_selection(raw: str | None, slide_count: int) -> list[int]:
    if not raw:
        return list(range(1, slide_count + 1))
    result: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"slide范围倒置: {token}")
            candidates = range(start, end + 1)
        else:
            candidates = [int(token)]
        for slide in candidates:
            if slide < 1 or slide > slide_count:
                raise ValueError(
                    f"slide超出范围: {slide}（共{slide_count}页）"
                )
            if slide not in result:
                result.append(slide)
    if not result:
        raise ValueError("--slides没有选中任何页面")
    return result


def direct_child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    return next(
        (child for child in element if local_name(child.tag) == name),
        None,
    )


def replace_direct_child(
    target_parent: ET.Element,
    child_name: str,
    source_child: ET.Element | None,
    *,
    insert_index: int | None = None,
) -> None:
    for child in list(target_parent):
        if local_name(child.tag) == child_name:
            target_parent.remove(child)
    if source_child is not None:
        clone = copy.deepcopy(source_child)
        if insert_index is None:
            target_parent.append(clone)
        else:
            target_parent.insert(insert_index, clone)


def replace_fill(
    target_properties: ET.Element,
    source_properties: ET.Element,
) -> None:
    source_fill = next(
        (
            child
            for child in source_properties
            if local_name(child.tag) in FILL_NAMES
        ),
        None,
    )
    old_children = list(target_properties)
    fill_positions = [
        index
        for index, child in enumerate(old_children)
        if local_name(child.tag) in FILL_NAMES
    ]
    for child in old_children:
        if local_name(child.tag) in FILL_NAMES:
            target_properties.remove(child)
    if source_fill is not None:
        position = fill_positions[0] if fill_positions else min(
            2, len(target_properties)
        )
        target_properties.insert(position, copy.deepcopy(source_fill))


def style_pool(paragraph: ET.Element) -> list[ET.Element | None]:
    result: list[ET.Element | None] = []
    for child in paragraph:
        if local_name(child.tag) not in TEXT_RUN_NAMES:
            continue
        result.append(direct_child(child, "rPr"))
    return result


def apply_text_style(
    canonical_tx_body: ET.Element,
    target_tx_body: ET.Element,
) -> None:
    replace_direct_child(
        target_tx_body,
        "bodyPr",
        direct_child(canonical_tx_body, "bodyPr"),
        insert_index=0,
    )
    replace_direct_child(
        target_tx_body,
        "lstStyle",
        direct_child(canonical_tx_body, "lstStyle"),
        insert_index=1,
    )
    source_paragraphs = [
        child for child in canonical_tx_body if local_name(child.tag) == "p"
    ]
    target_paragraphs = [
        child for child in target_tx_body if local_name(child.tag) == "p"
    ]
    if not source_paragraphs:
        return
    fallback_run_style = next(
        (
            style
            for paragraph in source_paragraphs
            for style in style_pool(paragraph)
            if style is not None
        ),
        None,
    )
    for paragraph_index, target_paragraph in enumerate(target_paragraphs):
        source_paragraph = source_paragraphs[
            min(paragraph_index, len(source_paragraphs) - 1)
        ]
        replace_direct_child(
            target_paragraph,
            "pPr",
            direct_child(source_paragraph, "pPr"),
            insert_index=0,
        )
        source_run_styles = style_pool(source_paragraph)
        target_runs = [
            child
            for child in target_paragraph
            if local_name(child.tag) in TEXT_RUN_NAMES
        ]
        for run_index, target_run in enumerate(target_runs):
            source_style = (
                source_run_styles[
                    min(run_index, len(source_run_styles) - 1)
                ]
                if source_run_styles
                else fallback_run_style
            )
            replace_direct_child(
                target_run,
                "rPr",
                source_style,
                insert_index=0,
            )
        replace_direct_child(
            target_paragraph,
            "endParaRPr",
            direct_child(source_paragraph, "endParaRPr"),
        )


def visible_text(shape: ET.Element) -> tuple[str, ...]:
    return tuple(
        element.text or ""
        for element in shape.iter()
        if local_name(element.tag) == "t"
    )


def semantic_text_snapshot(shape: ET.Element) -> dict[str, object]:
    """Capture visible text and field content, ignoring empty style carriers."""
    fields = []
    for element in shape.iter():
        if local_name(element.tag) != "fld":
            continue
        fields.append(
            {
                "attributes": dict(sorted(element.attrib.items())),
                "text": "".join(
                    candidate.text or ""
                    for candidate in element.iter()
                    if local_name(candidate.tag) == "t"
                ),
            }
        )
    return {
        "visibleText": "".join(visible_text(shape)),
        "fields": fields,
    }


def copy_chrome_format(
    canonical_shape: ET.Element,
    target_shape: ET.Element,
    scope: str = "all",
) -> None:
    canonical_sp_pr = direct_child(canonical_shape, "spPr")
    target_sp_pr = direct_child(target_shape, "spPr")
    if canonical_sp_pr is not None and target_sp_pr is not None:
        if scope in {"all", "geometry"}:
            replace_direct_child(
                target_sp_pr,
                "xfrm",
                direct_child(canonical_sp_pr, "xfrm"),
                insert_index=0,
            )
        if scope in {"all", "style"}:
            replace_fill(target_sp_pr, canonical_sp_pr)
            replace_direct_child(
                target_sp_pr,
                "ln",
                direct_child(canonical_sp_pr, "ln"),
            )
    if scope in {"all", "style"}:
        replace_direct_child(
            target_shape,
            "style",
            direct_child(canonical_shape, "style"),
        )
        canonical_tx_body = direct_child(canonical_shape, "txBody")
        target_tx_body = direct_child(target_shape, "txBody")
        if canonical_tx_body is not None and target_tx_body is not None:
            apply_text_style(canonical_tx_body, target_tx_body)
            ensure_canonical_font_style_set(canonical_shape, target_shape)


def format_signature(
    shape: ET.Element,
    scope: str = "all",
) -> dict[str, object]:
    sp_pr = direct_child(shape, "spPr")
    tx_body = direct_child(shape, "txBody")
    signature: dict[str, object] = {
        "xfrm": canonical_xml(direct_child(sp_pr, "xfrm")),
        "fill": None,
        "line": canonical_xml(direct_child(sp_pr, "ln")),
        "style": canonical_xml(direct_child(shape, "style")),
        "bodyPr": canonical_xml(direct_child(tx_body, "bodyPr")),
        "listStyle": canonical_xml(direct_child(tx_body, "lstStyle")),
        "paragraphStyles": [],
        "runStyles": [],
        "effectiveFontSet": effective_font_style_set(shape),
    }
    if sp_pr is not None:
        fill = next(
            (
                child
                for child in sp_pr
                if local_name(child.tag) in FILL_NAMES
            ),
            None,
        )
        signature["fill"] = canonical_xml(fill)
    if tx_body is not None:
        paragraphs = [
            child for child in tx_body if local_name(child.tag) == "p"
        ]
        signature["paragraphStyles"] = [
            canonical_xml(direct_child(paragraph, "pPr"))
            for paragraph in paragraphs
        ]
        signature["runStyles"] = [
            [
                canonical_xml(direct_child(run, "rPr"))
                for run in paragraph
                if local_name(run.tag) in TEXT_RUN_NAMES
            ]
            for paragraph in paragraphs
        ]
    geometry_fields = {"xfrm"}
    style_fields = {
        "fill",
        "line",
        "style",
        "bodyPr",
        "listStyle",
        "paragraphStyles",
        "runStyles",
        "effectiveFontSet",
    }
    requested_fields = {
        "geometry": geometry_fields,
        "style": style_fields,
        "all": geometry_fields | style_fields,
    }[scope]
    return {
        key: value
        for key, value in signature.items()
        if key in requested_fields
    }


def selected_font_style_signature(
    element: ET.Element | None,
) -> dict[str, object] | None:
    if element is None:
        return None
    return {
        "attributes": {
            local_name(key): value
            for key, value in sorted(element.attrib.items())
            if local_name(key) in FONT_STYLE_ATTRIBUTES
        },
        "children": [
            canonical_xml(child)
            for child in element
            if local_name(child.tag) in FONT_STYLE_CHILDREN
        ],
    }


def effective_font_style_set(
    shape: ET.Element,
) -> list[dict[str, object] | None]:
    """Mirror OOXML QA's text-independent unique font-style inventory."""
    signatures: list[dict[str, object] | None] = []
    tx_body = direct_child(shape, "txBody")
    if tx_body is None:
        return signatures
    for paragraph in (
        child for child in tx_body if local_name(child.tag) == "p"
    ):
        paragraph_properties = direct_child(paragraph, "pPr")
        signatures.append(
            selected_font_style_signature(
                direct_child(paragraph_properties, "defRPr")
            )
        )
        for run_tag in ("r", "fld"):
            for run in (
                child
                for child in paragraph
                if local_name(child.tag) == run_tag
            ):
                signatures.append(
                    selected_font_style_signature(
                        direct_child(run, "rPr")
                    )
                )
        signatures.append(
            selected_font_style_signature(
                direct_child(paragraph, "endParaRPr")
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


def font_style_sources(
    shape: ET.Element,
) -> dict[str, ET.Element | None]:
    """Map each unique QA font signature to a source style element."""
    sources: dict[str, ET.Element | None] = {}
    tx_body = direct_child(shape, "txBody")
    if tx_body is None:
        return sources
    for paragraph in (
        child for child in tx_body if local_name(child.tag) == "p"
    ):
        paragraph_properties = direct_child(paragraph, "pPr")
        candidates: list[ET.Element | None] = [
            direct_child(paragraph_properties, "defRPr")
        ]
        for run_tag in ("r", "fld"):
            candidates.extend(
                direct_child(run, "rPr")
                for run in paragraph
                if local_name(run.tag) == run_tag
            )
        candidates.append(direct_child(paragraph, "endParaRPr"))
        for candidate in candidates:
            signature = selected_font_style_signature(candidate)
            key = json.dumps(
                signature,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            sources.setdefault(key, candidate)
    return sources


def ensure_canonical_font_style_set(
    canonical_shape: ET.Element,
    target_shape: ET.Element,
) -> int:
    """Add zero-length style-carrier runs for canonical styles not represented.

    Empty text boxes have no visible run, so copying paragraph defaults alone
    can leave their unique font-style inventory smaller than the canonical
    shape's.  A zero-length run preserves all existing text and fields while
    carrying the otherwise-missing canonical run style for exact OOXML QA.
    """
    canonical_sources = font_style_sources(canonical_shape)
    target_sources = font_style_sources(target_shape)
    missing_keys = [
        key for key in canonical_sources if key not in target_sources
    ]
    if not missing_keys:
        return 0
    tx_body = direct_child(target_shape, "txBody")
    if tx_body is None:
        return 0
    paragraph = next(
        (
            child
            for child in tx_body
            if local_name(child.tag) == "p"
        ),
        None,
    )
    if paragraph is None:
        return 0
    insert_index = next(
        (
            index
            for index, child in enumerate(paragraph)
            if local_name(child.tag) == "endParaRPr"
        ),
        len(paragraph),
    )
    added = 0
    for key in missing_keys:
        source_style = canonical_sources[key]
        run = ET.Element(f"{A}r")
        if source_style is not None:
            run_properties = copy.deepcopy(source_style)
            run_properties.tag = f"{A}rPr"
            run.append(run_properties)
        text = ET.Element(f"{A}t")
        text.text = ""
        run.append(text)
        paragraph.insert(insert_index, run)
        insert_index += 1
        added += 1
    return added


def expected_signature(
    canonical_shape: ET.Element,
    target_shape: ET.Element,
    scope: str = "all",
) -> dict[str, object]:
    expected = copy.deepcopy(target_shape)
    copy_chrome_format(canonical_shape, expected, scope=scope)
    return format_signature(expected, scope=scope)


def signature_differences(
    actual: dict[str, object],
    expected: dict[str, object],
) -> list[str]:
    return [
        key
        for key in expected
        if actual.get(key) != expected.get(key)
    ]


def copy_pptx(
    source: Path,
    output: Path,
    infos: list[zipfile.ZipInfo],
    members: dict[str, bytes],
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
        )[1]
    )
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            for info in infos:
                archive.writestr(info, members[info.filename])
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()


def normalize(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    input_path = Path(args.input).expanduser().resolve()
    output_path = (
        Path(args.output).expanduser().resolve() if args.output else None
    )
    report_path = (
        Path(args.report).expanduser().resolve() if args.report else None
    )
    errors: list[str] = []
    if not input_path.is_file():
        errors.append(f"输入文件不存在: {input_path}")
    if input_path.suffix.lower() != ".pptx":
        errors.append("输入必须是.pptx")
    if args.apply and output_path is None:
        errors.append("--apply必须同时提供--output")
    if output_path is not None and output_path == input_path:
        errors.append("禁止覆盖源文件")
    if (
        args.apply
        and output_path is not None
        and output_path.exists()
        and not args.force
    ):
        errors.append("输出文件已存在；如确认覆盖输出副本，请使用--force")
    if errors:
        report = {
            "schema": "ksib-pptx-chrome-normalizer/1.0",
            "passed": False,
            "blocked": True,
            "mode": "apply" if args.apply else "audit",
            "scope": args.scope,
            "errors": errors,
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return report, 2

    roles = parse_roles(args.role, args.roles)
    aliases = load_aliases(roles, args.alias, args.alias_map)
    with zipfile.ZipFile(input_path) as archive:
        infos = archive.infolist()
        members = {info.filename: archive.read(info.filename) for info in infos}
    slide_parts = presentation_slide_parts(members)
    selected_slides = parse_slide_selection(args.slides, len(slide_parts))
    if args.canonical_slide not in selected_slides:
        selected_slides.insert(0, args.canonical_slide)
    if not 1 <= args.canonical_slide <= len(slide_parts):
        raise ValueError(
            f"canonical slide超出范围: {args.canonical_slide}"
        )

    roots = {
        slide_number: ET.fromstring(members[slide_parts[slide_number - 1]])
        for slide_number in selected_slides
    }
    matches: dict[tuple[int, str], list[ET.Element]] = {}
    findings: list[dict[str, object]] = []
    ambiguous_count = 0
    missing_count = 0
    for slide_number in selected_slides:
        named_shapes = list(iter_named_shapes(roots[slide_number]))
        for role in roles:
            role_shapes = [
                shape
                for shape in named_shapes
                if role_matches(shape_name(shape), role, aliases)
            ]
            matches[(slide_number, role)] = role_shapes
            if len(role_shapes) == 0:
                status = "missing"
                missing_count += 1
            elif len(role_shapes) > 1:
                status = "ambiguous"
                ambiguous_count += 1
            else:
                status = "resolved"
            findings.append(
                {
                    "slide": slide_number,
                    "role": role,
                    "status": status,
                    "matchCount": len(role_shapes),
                    "shapeNames": [shape_name(shape) for shape in role_shapes],
                    "objectType": (
                        local_name(role_shapes[0].tag)
                        if len(role_shapes) == 1
                        else None
                    ),
                }
            )

    type_mismatch_count = 0
    if not ambiguous_count and not missing_count:
        canonical_types = {
            role: local_name(
                matches[(args.canonical_slide, role)][0].tag
            )
            for role in roles
        }
        for finding in findings:
            slide_number = int(finding["slide"])
            role = str(finding["role"])
            actual_type = str(finding["objectType"])
            canonical_type = canonical_types[role]
            finding["canonicalObjectType"] = canonical_type
            finding["typeMatched"] = actual_type == canonical_type
            if actual_type != canonical_type:
                type_mismatch_count += 1
                finding["status"] = "type-mismatch"
                errors.append(
                    "对象类型不一致: "
                    f"slide {slide_number} role {role} "
                    f"expected {canonical_type}, actual {actual_type}"
                )

    blocked = bool(
        ambiguous_count or missing_count or type_mismatch_count
    )
    changed_shapes = 0
    changed_slides: set[int] = set()
    text_before_count = 0
    text_after_count = 0
    text_changed_count = 0
    style_carrier_run_count = 0
    target_shape_count = 0

    if not blocked:
        canonical_shapes = {
            role: matches[(args.canonical_slide, role)][0]
            for role in roles
        }
        for finding in findings:
            slide_number = int(finding["slide"])
            role = str(finding["role"])
            if slide_number == args.canonical_slide:
                finding["differences"] = []
                finding["formatAligned"] = True
                finding["postApplyDifferences"] = []
                finding["postApplyAligned"] = True
                continue
            target = matches[(slide_number, role)][0]
            canonical = canonical_shapes[role]
            differences = signature_differences(
                format_signature(target, scope=args.scope),
                expected_signature(
                    canonical, target, scope=args.scope
                ),
            )
            finding["differences"] = differences
            finding["formatAligned"] = not differences
            target_shape_count += 1
            before_text = visible_text(target)
            before_semantic_text = semantic_text_snapshot(target)
            text_before_count += len(before_text)
            if args.apply and differences:
                copy_chrome_format(
                    canonical, target, scope=args.scope
                )
                changed_shapes += 1
                changed_slides.add(slide_number)
            post_apply_differences = signature_differences(
                format_signature(target, scope=args.scope),
                expected_signature(
                    canonical, target, scope=args.scope
                ),
            )
            finding["postApplyDifferences"] = post_apply_differences
            finding["postApplyAligned"] = not post_apply_differences
            after_text = visible_text(target)
            after_semantic_text = semantic_text_snapshot(target)
            text_after_count += len(after_text)
            style_carrier_run_count += max(
                0, len(after_text) - len(before_text)
            )
            if before_semantic_text != after_semantic_text:
                text_changed_count += 1

    if args.apply and not blocked and text_changed_count == 0:
        # Rewrite only changed slide parts.  This avoids namespace-prefix and
        # serialization churn on canonical or already-aligned slides.
        for slide_number in changed_slides:
            members[slide_parts[slide_number - 1]] = ET.tostring(
                roots[slide_number],
                encoding="utf-8",
                xml_declaration=True,
            )
        assert output_path is not None
        copy_pptx(input_path, output_path, infos, members)

    if text_changed_count:
        blocked = True
        errors.append("可见文本发生变化，已阻断输出")

    report: dict[str, object] = {
        "schema": "ksib-pptx-chrome-normalizer/1.0",
        "passed": not blocked,
        "blocked": blocked,
        "mode": "apply" if args.apply else "audit",
        "scope": args.scope,
        "profile": args.profile,
        "input": str(input_path),
        "inputSha256": sha256_file(input_path),
        "output": str(output_path) if output_path else None,
        "outputSha256": (
            sha256_file(output_path)
            if args.apply
            and not blocked
            and output_path is not None
            and output_path.exists()
            else None
        ),
        "canonicalSlide": args.canonical_slide,
        "selectedSlides": selected_slides,
        "roles": roles,
        "aliases": aliases,
        "findings": findings,
        "semanticSafety": {
            "targetShapeCount": target_shape_count,
            "textBeforeNodeCount": text_before_count,
            "textAfterNodeCount": text_after_count,
            "textChangedShapeCount": text_changed_count,
            "visibleTextPreserved": text_changed_count == 0,
            "styleCarrierRunCount": style_carrier_run_count,
            "missingRoleCount": missing_count,
            "ambiguousRoleCount": ambiguous_count,
            "typeMismatchCount": type_mismatch_count,
            "changedShapeCount": changed_shapes,
            "changedSlideCount": len(changed_slides),
        },
        "errors": errors,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report, 2 if blocked else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "按稳定shape name角色审计或归一既有PPTX的跨页页眉/页脚Chrome"
        )
    )
    parser.add_argument("--input", required=True, help="源PPTX（永不覆盖）")
    parser.add_argument("--output", help="--apply时写入的新PPTX")
    parser.add_argument(
        "--canonical-slide",
        type=int,
        required=True,
        help="1-based基准页码",
    )
    parser.add_argument(
        "--role",
        action="append",
        default=[],
        help="稳定角色名；可重复或逗号分隔",
    )
    parser.add_argument("--roles", help="逗号分隔的稳定角色名")
    parser.add_argument(
        "--alias",
        action="append",
        default=[],
        help="legacy别名规则，格式ROLE=REGEX；可重复",
    )
    parser.add_argument(
        "--alias-map",
        help='JSON映射：{"role":["regex"]}或{"legacy-name":"role"}',
    )
    parser.add_argument(
        "--slides",
        help="同一page profile的页码，如2-10,12；默认全Deck",
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="写入报告的page profile名称",
    )
    parser.add_argument(
        "--scope",
        choices=("all", "geometry", "style"),
        default="all",
        help=(
            "归一范围：all=几何+样式，geometry=仅x/y/w/h/rotation，"
            "style=仅填充/线条/文本与段落样式"
        ),
    )
    parser.add_argument("--report", help="JSON报告路径")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入新副本；未提供时仅audit/dry-run",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="允许覆盖已存在的输出副本；永不允许覆盖源文件",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report, exit_code = normalize(args)
    except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        report = {
            "schema": "ksib-pptx-chrome-normalizer/1.0",
            "passed": False,
            "blocked": True,
            "mode": "apply" if args.apply else "audit",
            "scope": args.scope,
            "errors": [str(exc)],
        }
        if args.report:
            report_path = Path(args.report).expanduser().resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
