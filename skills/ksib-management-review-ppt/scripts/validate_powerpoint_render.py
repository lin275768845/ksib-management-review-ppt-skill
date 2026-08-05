#!/usr/bin/env python3
"""Validate PowerPoint-native screenshots and rendered layout semantics.

This is the final visual-truth gate. PDF, LibreOffice and auxiliary PNG renders
may help review, but they cannot satisfy this gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from build_visual_review_gate import parse_png, sha256_file


SCHEMA_VERSION = "ksib-powerpoint-render-gate/1.0"
REVIEW_SCHEMA_VERSION = "ksib-powerpoint-review/1.0"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
REQUIRED_SLIDE_CHECKS = (
    "fullSize100",
    "reducedScale",
    "noOverlap",
    "noClipping",
    "noUnexpectedWrap",
    "labelOwnership",
    "numberDisplay",
    "layoutContract",
)
PHASE_FIELDS = (
    ("title", ("title",)),
    ("logic", ("logic",)),
    ("successCriterion", ("successCriterion", "criterion")),
    ("action", ("action",)),
)
NON_LABEL_OBJECT_PREFIXES = (
    "action-title",
    "subtitle",
    "header-",
    "footer-",
    "source-",
    "page-number",
    "takeaway",
)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_text(value: Any) -> str:
    return re.sub(r"[\s\u00a0，。,:：;；!?！？、/／\\|｜()（）\[\]【】{}<>《》\-—–]+", "", str(value or "")).lower()


def is_external_label_object(name: str) -> bool:
    normalized = name.strip().lower()
    return not any(normalized.startswith(prefix) for prefix in NON_LABEL_OBJECT_PREFIXES)


def numeric_value(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "").replace("％", "%")
    text = re.sub(r"(?:个百分点|百分点|pp|%)$", "", text, flags=re.IGNORECASE).strip()
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return None
    return float(text)


def add_error(errors: list[dict[str, Any]], rule: str, detail: str, **extra: Any) -> None:
    errors.append({"rule": rule, "detail": detail, **extra})


def resolve_zip_target(source: str, target: str) -> str:
    # OOXML relationship targets may be package-absolute (leading slash) or
    # relative to the source part. Zip members never carry that leading slash.
    if target.startswith("/"):
        return posixpath.normpath(target).lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source), target))


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


def slide_count(archive: zipfile.ZipFile) -> int:
    presentation = xml_root(archive, "ppt/presentation.xml")
    return sum(1 for _ in presentation.iter(f"{{{P_NS}}}sldId"))


def element_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{{{A_NS}}}t")).strip()


def slide_objects(archive: zipfile.ZipFile, slide_number: int) -> tuple[dict[str, str], ET.Element]:
    root = xml_root(archive, f"ppt/slides/slide{slide_number}.xml")
    objects: dict[str, str] = {}
    for candidate in list(root.iter(f"{{{P_NS}}}sp")) + list(root.iter(f"{{{P_NS}}}graphicFrame")):
        metadata = candidate.find(f".//{{{P_NS}}}cNvPr")
        if metadata is None:
            continue
        name = metadata.get("name") or ""
        if name:
            objects[name] = element_text(candidate)
    return objects, root


def slide_chart_parts(archive: zipfile.ZipFile, slide_number: int, slide_root: ET.Element) -> list[tuple[str, ET.Element]]:
    rel_path = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
    try:
        rel_root = xml_root(archive, rel_path)
    except RuntimeError:
        return []
    relationships = {
        item.get("Id"): resolve_zip_target(f"ppt/slides/slide{slide_number}.xml", item.get("Target") or "")
        for item in rel_root.iter(f"{{{REL_NS}}}Relationship")
        if item.get("Id") and (item.get("Type") or "").endswith("/chart")
    }
    parts: list[tuple[str, ET.Element]] = []
    for chart_ref in slide_root.iter(f"{{{C_NS}}}chart"):
        rel_id = chart_ref.get(f"{{{R_NS}}}id")
        target = relationships.get(rel_id)
        if target:
            parts.append((target, xml_root(archive, target)))
    return parts


def cache_values(root: ET.Element, axis: str) -> list[str]:
    values: list[str] = []
    for parent in root.iter(f"{{{C_NS}}}{axis}"):
        # PowerPoint may persist chart data as cached references or native
        # literals. The ownership rule cares about the final visible values,
        # so read every c:v below c:cat/c:val instead of assuming one cache.
        for value in parent.iter(f"{{{C_NS}}}v"):
            if value.text is not None:
                values.append(value.text.strip())
    return values


def native_category_labels_visible(root: ET.Element) -> bool:
    category_axes = list(root.iter(f"{{{C_NS}}}catAx")) + list(root.iter(f"{{{C_NS}}}dateAx"))
    if not category_axes:
        return False
    for axis in category_axes:
        tick = axis.find(f"{{{C_NS}}}tickLblPos")
        if tick is None or tick.get("val") != "none":
            return True
    return False


def native_data_labels_visible(root: ET.Element) -> bool:
    for labels in root.iter(f"{{{C_NS}}}dLbls"):
        show_value = labels.find(f"{{{C_NS}}}showVal")
        show_category = labels.find(f"{{{C_NS}}}showCatName")
        if (show_value is not None and show_value.get("val", "1") != "0") or (
            show_category is not None and show_category.get("val", "1") != "0"
        ):
            return True
    return False


def native_legend_visible(root: ET.Element) -> bool:
    for legend in root.iter(f"{{{C_NS}}}legend"):
        deleted = legend.find(f"{{{C_NS}}}delete")
        if deleted is None or deleted.get("val", "0") != "1":
            return True
    return False


def chart_title_values(root: ET.Element) -> list[str]:
    return [element_text(title) for title in root.iter(f"{{{C_NS}}}title") if element_text(title)]


def series_name_values(root: ET.Element) -> list[str]:
    values: list[str] = []
    for series in root.iter(f"{{{C_NS}}}ser"):
        text_node = series.find(f"{{{C_NS}}}tx")
        if text_node is None:
            continue
        values.extend(value.text.strip() for value in text_node.iter(f"{{{C_NS}}}v") if value.text)
    return values


def chart_is_line(root: ET.Element) -> bool:
    return any(True for _ in root.iter(f"{{{C_NS}}}lineChart"))


def chart_has_smoothing(root: ET.Element) -> bool:
    return any(item.get("val", "1") != "0" for item in root.iter(f"{{{C_NS}}}smooth"))


def looks_like_dates(values: list[str]) -> bool:
    if len(values) < 3:
        return False
    pattern = re.compile(r"^(?:\d{4}[-/.年])?\d{1,2}[-/.月]\d{1,2}(?:日)?$")
    return sum(bool(pattern.match(value)) for value in values) >= max(3, len(values) // 2)


def decimal_places(format_code: str) -> int | None:
    if "%" not in format_code:
        return None
    clean = format_code.replace('"%"', "%")
    match = re.search(r"0(?:\.(0+))?%", clean)
    return len(match.group(1) or "") if match else None


def chart_percent_precisions(root: ET.Element) -> list[int]:
    result: list[int] = []
    for item in root.iter(f"{{{C_NS}}}numFmt"):
        precision = decimal_places(item.get("formatCode") or "")
        if precision is not None:
            result.append(precision)
    return result


def semantic_by_chart(format_contract: dict[str, Any], slide: int, chart_path: str) -> dict[str, Any] | None:
    candidates = format_contract.get("chartSemantics", [])
    if not isinstance(candidates, list):
        return None
    chart_name = PurePosixPath(chart_path).name
    for candidate in candidates:
        if candidate.get("slide") == slide and candidate.get("chart") in {chart_name, chart_path}:
            return candidate
    return None


def audit_charts(
    archive: zipfile.ZipFile,
    format_contract: dict[str, Any],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for slide in range(1, slide_count(archive) + 1):
        objects, slide_root = slide_objects(archive, slide)
        external_texts = {
            name: normalize_text(text)
            for name, text in objects.items()
            if normalize_text(text) and is_external_label_object(name)
        }
        for chart_path, chart_root in slide_chart_parts(archive, slide, slide_root):
            categories = cache_values(chart_root, "cat")
            values = cache_values(chart_root, "val")
            duplicate_names: set[str] = set()
            if native_category_labels_visible(chart_root):
                category_tokens = {normalize_text(value) for value in categories if normalize_text(value)}
                duplicate_names.update(name for name, text in external_texts.items() if text in category_tokens)
            if duplicate_names:
                add_error(
                    errors,
                    "duplicate_label_ownership",
                    "原生分类轴与外部文本框同时负责同一分类标签",
                    slide=slide,
                    chart=PurePosixPath(chart_path).name,
                    objects=sorted(duplicate_names),
                )
            if native_data_labels_visible(chart_root):
                numeric_values = [number for number in (numeric_value(value) for value in values) if number is not None]
                duplicated_values = []
                for name, text in objects.items():
                    if not is_external_label_object(name):
                        continue
                    number = numeric_value(text)
                    if number is None:
                        continue
                    if any(abs(number - value) <= 1e-9 or abs(number / 100 - value) <= 1e-9 for value in numeric_values):
                        duplicated_values.append(name)
                if duplicated_values:
                    add_error(
                        errors,
                        "duplicate_label_ownership",
                        "原生数据标签与外部文本框同时负责同一数值标签",
                        slide=slide,
                        chart=PurePosixPath(chart_path).name,
                        objects=duplicated_values,
                    )
            title_tokens = {normalize_text(value) for value in chart_title_values(chart_root)}
            duplicated_titles = sorted(name for name, text in external_texts.items() if text in title_tokens)
            if duplicated_titles:
                add_error(errors, "duplicate_label_ownership", "原生图表标题与外部文本框同时负责同一标题", slide=slide, chart=PurePosixPath(chart_path).name, objects=duplicated_titles)
            if native_legend_visible(chart_root):
                series_tokens = {normalize_text(value) for value in series_name_values(chart_root)}
                duplicated_series = sorted(name for name, text in external_texts.items() if text in series_tokens)
                if duplicated_series:
                    add_error(errors, "duplicate_label_ownership", "原生图例与外部文本框同时负责同一系列标签", slide=slide, chart=PurePosixPath(chart_path).name, objects=duplicated_series)

            semantic = semantic_by_chart(format_contract, slide, chart_path)
            precisions = chart_percent_precisions(chart_root)
            if precisions:
                if semantic is None or semantic.get("measureKind") not in {"percent", "percentage-point"}:
                    add_error(
                        errors,
                        "percentage_semantics_missing",
                        "百分比图表必须声明measureKind为percent或percentage-point",
                        slide=slide,
                        chart=PurePosixPath(chart_path).name,
                    )
                expected = semantic.get("precision") if semantic else 0
                if expected not in {0, 1}:
                    add_error(errors, "percentage_precision_invalid", "precision只能为0或1", slide=slide, chart=PurePosixPath(chart_path).name)
                precision_reason = str((semantic or {}).get("precisionReason") or "").strip()
                if expected == 1 and not re.search(r"关键|差异|小于\s*1|监管|regulat|material", precision_reason, re.IGNORECASE):
                    add_error(errors, "percentage_precision_reason_missing", "保留1位小数必须说明关键差异、小于1%或监管口径", slide=slide, chart=PurePosixPath(chart_path).name)
                if len(set(precisions)) > 1:
                    add_error(errors, "percentage_precision_inconsistent", "同一图表的百分比轴和标签精度不一致", slide=slide, chart=PurePosixPath(chart_path).name, precisions=precisions)
                if any(precision != expected for precision in precisions):
                    add_error(errors, "percentage_precision_mismatch", f"声明precision={expected}，实际为{sorted(set(precisions))}", slide=slide, chart=PurePosixPath(chart_path).name)

            line = chart_is_line(chart_root)
            time_series = line and (looks_like_dates(categories) or (semantic or {}).get("semanticType") == "financial-time-series")
            # Serious management decks default to unsmoothed line charts.
            # Even when a missing semantic declaration prevents date inference,
            # smoothing remains blocked rather than silently accepted.
            if line and chart_has_smoothing(chart_root):
                add_error(errors, "financial_line_smoothing_forbidden", "金融时间序列禁止平滑曲线", slide=slide, chart=PurePosixPath(chart_path).name)
            records.append({
                "slide": slide,
                "chart": PurePosixPath(chart_path).name,
                "nativeCategoryLabels": native_category_labels_visible(chart_root),
                "nativeDataLabels": native_data_labels_visible(chart_root),
                "percentPrecisions": precisions,
                "financialTimeSeries": time_series,
                "smoothed": chart_has_smoothing(chart_root),
            })
    return records


def content_slides(content: Any) -> list[dict[str, Any]]:
    return content if isinstance(content, list) else content.get("slides", [])


def render_validation_record(format_contract: dict[str, Any], slide: int) -> dict[str, Any] | None:
    records = (format_contract.get("renderValidation") or {}).get("slides", [])
    for record in records if isinstance(records, list) else []:
        if record.get("slide") == slide:
            return record
    return None


def audit_phase_playbooks(
    archive: zipfile.ZipFile,
    content: Any,
    format_contract: dict[str, Any],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for slide, payload in enumerate(content_slides(content), start=1):
        layout = payload.get("layoutContract") or payload.get("slideType") or payload.get("layoutId")
        if layout != "phasePlaybook":
            continue
        slot_content = payload.get("slotContent") if isinstance(payload.get("slotContent"), dict) else {}
        phases = payload.get("phases") or slot_content.get("phases") or []
        if not 3 <= len(phases) <= 4:
            add_error(errors, "phase_playbook_phase_count", "phasePlaybook必须包含3至4个阶段", slide=slide)
        objects, _ = slide_objects(archive, slide)
        contract = render_validation_record(format_contract, slide)
        rows = contract.get("rows", []) if isinstance(contract, dict) else []
        if not isinstance(contract, dict) or contract.get("layout") != "phasePlaybook":
            add_error(errors, "phase_playbook_render_contract_missing", "format-contract必须声明phasePlaybook逐字段渲染合同", slide=slide)
            rows = []
        by_field = {row.get("field"): row.get("objectNames") for row in rows if isinstance(row, dict)}
        for canonical_field, aliases in PHASE_FIELDS:
            row_field = next((alias for alias in aliases if f"phases[].{alias}" in by_field), None)
            names = by_field.get(f"phases[].{row_field}") if row_field else None
            if not isinstance(names, list) or len(names) != len(phases):
                alias_text = "或".join(f"phases[].{alias}" for alias in aliases)
                add_error(errors, "phase_playbook_role_mapping_missing", f"{alias_text}必须逐阶段绑定对象名", slide=slide)
                continue
            for index, (phase, name) in enumerate(zip(phases, names), start=1):
                expected = normalize_text(next((phase.get(alias) for alias in aliases if phase.get(alias)), ""))
                actual = normalize_text(objects.get(str(name), ""))
                if not expected or not actual or expected not in actual:
                    add_error(errors, "phase_playbook_field_not_rendered", f"第{index}阶段{canonical_field}未在对象{name}中按合同渲染", slide=slide, objectName=name)
        records.append({"slide": slide, "phaseCount": len(phases), "contractDeclared": isinstance(contract, dict)})
    return records


def validate_screenshots(
    pptx: Path,
    screenshot_dir: Path,
    review: dict[str, Any],
    expected_slides: int,
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    if review.get("schemaVersion") != REVIEW_SCHEMA_VERSION:
        add_error(errors, "powerpoint_review_schema_invalid", f"必须使用{REVIEW_SCHEMA_VERSION}")
    if review.get("source") != "Microsoft PowerPoint":
        add_error(errors, "powerpoint_source_unverified", "截图来源必须明确为Microsoft PowerPoint")
    pptx_hash = sha256_file(pptx)
    if review.get("pptxSha256") != pptx_hash:
        add_error(errors, "powerpoint_review_hash_mismatch", "审阅记录未绑定当前PPTX")
    reviewer = str(review.get("reviewedBy") or "").strip()
    reviewed_at = str(review.get("reviewedAt") or "").strip()
    reviewer_role = review.get("reviewerRole")
    if not reviewer or not reviewed_at or reviewer_role not in {"independent", "builder"}:
        add_error(errors, "powerpoint_review_attribution_missing", "必须记录审阅者、时间与reviewerRole")
    raw_slides = review.get("slides") if isinstance(review.get("slides"), list) else []
    by_slide = {item.get("slide"): item for item in raw_slides if isinstance(item, dict)}
    records: list[dict[str, Any]] = []
    for slide in range(1, expected_slides + 1):
        item = by_slide.get(slide)
        if item is None:
            add_error(errors, "powerpoint_screenshot_missing", "缺少PowerPoint逐页截图与审阅记录", slide=slide)
            continue
        filename = item.get("screenshot")
        screenshot = screenshot_dir / str(filename or "")
        metadata: dict[str, Any] | None = None
        payload = b""
        if not filename or not screenshot.is_file():
            add_error(errors, "powerpoint_screenshot_missing", f"截图文件不存在：{filename}", slide=slide)
        else:
            try:
                payload = screenshot.read_bytes()
                metadata = parse_png(payload)
            except Exception as error:  # parse_png raises a dedicated runtime error
                add_error(errors, "powerpoint_screenshot_invalid", str(error), slide=slide)
        checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
        for check in REQUIRED_SLIDE_CHECKS:
            if checks.get(check) is not True:
                add_error(errors, "powerpoint_slide_check_failed", check, slide=slide)
        issues = item.get("issues")
        if not isinstance(issues, list):
            add_error(errors, "powerpoint_issue_log_missing", "issues必须为数组", slide=slide)
            issues = ["invalid"]
        if issues:
            add_error(errors, "powerpoint_unresolved_issues", "仍有未解决的PowerPoint视觉问题", slide=slide, issues=issues)
        if not str(item.get("reviewedAt") or "").strip():
            add_error(errors, "powerpoint_slide_review_time_missing", "每页必须记录reviewedAt", slide=slide)
        if reviewer_role == "builder" and len(str(item.get("notes") or "").strip()) < 12:
            add_error(errors, "builder_review_evidence_weak", "构建者自审时每页必须留下具体复核说明", slide=slide)
        records.append({
            "slide": slide,
            "screenshot": filename,
            "sha256": hashlib.sha256(payload).hexdigest() if payload else None,
            "pixelSha256": metadata.get("pixelSha256") if metadata else None,
            "width": metadata.get("width") if metadata else None,
            "height": metadata.get("height") if metadata else None,
            "reviewedAt": item.get("reviewedAt"),
            "reviewedBy": item.get("reviewedBy") or reviewer,
            "passed": not issues and all(checks.get(check) is True for check in REQUIRED_SLIDE_CHECKS) and metadata is not None,
        })
    unexpected = sorted(key for key in by_slide if not isinstance(key, int) or key < 1 or key > expected_slides)
    if unexpected:
        add_error(errors, "powerpoint_review_slide_out_of_range", str(unexpected))
    screenshot_set_hash = hashlib.sha256(stable_json([
        {"slide": item["slide"], "sha256": item["sha256"], "pixelSha256": item["pixelSha256"]}
        for item in records
    ]).encode("utf-8")).hexdigest()
    return records, screenshot_set_hash


def build_report(pptx: Path, content_path: Path, format_contract_path: Path, review_path: Path, screenshot_dir: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    content = read_json(content_path, "content")
    format_contract = read_json(format_contract_path, "format contract")
    review = read_json(review_path, "PowerPoint review")
    with zipfile.ZipFile(pptx) as archive:
        count = slide_count(archive)
        chart_records = audit_charts(archive, format_contract, errors)
        playbook_records = audit_phase_playbooks(archive, content, format_contract, errors)
    screenshot_records, screenshot_set_hash = validate_screenshots(pptx, screenshot_dir, review, count, errors)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "validatorSha256": sha256_file(Path(__file__).resolve()),
        "passed": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "pptx": {"fileName": pptx.name, "sha256": sha256_file(pptx), "slideCount": count},
        "inputHashes": {
            "contentSha256": sha256_file(content_path),
            "formatContractSha256": sha256_file(format_contract_path),
        },
        "review": {
            "schemaVersion": review.get("schemaVersion"),
            "reviewedBy": review.get("reviewedBy"),
            "reviewedAt": review.get("reviewedAt"),
            "reviewerRole": review.get("reviewerRole"),
            "source": review.get("source"),
        },
        "powerpointScreenshotSetHash": screenshot_set_hash,
        "reviewedSlideCount": sum(1 for item in screenshot_records if item["passed"]),
        "slides": screenshot_records,
        "charts": chart_records,
        "phasePlaybooks": playbook_records,
        "checks": {
            "powerpointScreenshots": not any(item["rule"].startswith("powerpoint_") or item["rule"] == "builder_review_evidence_weak" for item in errors),
            "labelOwnership": not any(item["rule"] == "duplicate_label_ownership" for item in errors),
            "numberDisplay": not any(item["rule"].startswith("percentage_") for item in errors),
            "financialChartSemantics": not any(item["rule"] == "financial_line_smoothing_forbidden" for item in errors),
            "rendererImplementation": not any(item["rule"].startswith("phase_playbook_") for item in errors),
        },
        "errors": errors,
        "warnings": warnings,
    }


def write_report(path: Path | None, report: dict[str, Any]) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(payload, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


def self_test() -> None:
    # Synthetic Golden Deck: one intentionally bad chart plus one correctly
    # rendered phasePlaybook. It is deterministic and needs no Office runtime.
    absolute_target = resolve_zip_target("ppt/slides/slide1.xml", "/ppt/slides/charts/chart1.xml")
    if absolute_target != "ppt/slides/charts/chart1.xml":
        raise RuntimeError(f"Absolute OOXML relationship target failed: {absolute_target}")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        pptx = root / "bad.pptx"
        phases = [
            {"title": f"阶段{index}", "logic": f"逻辑{index}", "successCriterion": f"标准{index}", "action": f"行动{index}"}
            for index in (1, 2, 3)
        ]
        phase_shapes = []
        object_id = 2
        for index, phase in enumerate(phases, start=1):
            for field, suffix in (("title", "title"), ("logic", "logic"), ("successCriterion", "criterion"), ("action", "action")):
                phase_shapes.append(
                    f'<p:sp><p:nvSpPr><p:cNvPr id="{object_id}" name="phase-{index}-{suffix}"/></p:nvSpPr>'
                    f'<p:txBody><a:p><a:r><a:t>{phase[field]}</a:t></a:r></a:p></p:txBody></p:sp>'
                )
                object_id += 1
        with zipfile.ZipFile(pptx, "w") as archive:
            archive.writestr("ppt/presentation.xml", f'<p:presentation xmlns:p="{P_NS}"><p:sldIdLst><p:sldId id="256"/><p:sldId id="257"/></p:sldIdLst></p:presentation>')
            archive.writestr("ppt/slides/slide1.xml", f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:c="{C_NS}" xmlns:r="{R_NS}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="external-category"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>7月1日</a:t></a:r></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id="4" name="external-value-label"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>12.34%</a:t></a:r></a:p></p:txBody></p:sp><p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="3" name="chart-main"/></p:nvGraphicFramePr><a:graphic><a:graphicData><c:chart r:id="rId1"/></a:graphicData></a:graphic></p:graphicFrame></p:spTree></p:cSld></p:sld>')
            archive.writestr("ppt/slides/slide2.xml", f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree>{"".join(phase_shapes)}</p:spTree></p:cSld></p:sld>')
            archive.writestr("ppt/slides/_rels/slide1.xml.rels", f'<Relationships xmlns="{REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/></Relationships>')
            archive.writestr("ppt/charts/chart1.xml", f'<c:chartSpace xmlns:c="{C_NS}"><c:chart><c:plotArea><c:lineChart><c:dLbls><c:showVal val="1"/><c:numFmt formatCode="0.00%"/></c:dLbls><c:ser><c:cat><c:strRef><c:strCache><c:pt><c:v>7月1日</c:v></c:pt><c:pt><c:v>7月2日</c:v></c:pt><c:pt><c:v>7月3日</c:v></c:pt></c:strCache></c:strRef></c:cat><c:val><c:numLit><c:pt><c:v>12.34</c:v></c:pt></c:numLit></c:val><c:smooth val="1"/></c:ser></c:lineChart><c:catAx><c:tickLblPos val="nextTo"/></c:catAx><c:valAx><c:numFmt formatCode="0.00%"/></c:valAx></c:plotArea></c:chart></c:chartSpace>')
        errors: list[dict[str, Any]] = []
        with zipfile.ZipFile(pptx) as archive:
            charts = audit_charts(archive, {}, errors)
            phase_missing_contract_errors: list[dict[str, Any]] = []
            audit_phase_playbooks(
                archive,
                {"slides": [{"slideType": "cover", "title": "封面"}, {"slideType": "phasePlaybook", "title": "打法", "phases": phases}]},
                {},
                phase_missing_contract_errors,
            )
            phase_valid_errors: list[dict[str, Any]] = []
            audit_phase_playbooks(
                archive,
                {"slides": [{"slideType": "cover", "title": "封面"}, {"slideType": "phasePlaybook", "title": "打法", "phases": phases}]},
                {
                    "renderValidation": {
                        "slides": [{
                            "slide": 2,
                            "layout": "phasePlaybook",
                            "rows": [
                                {"field": "phases[].title", "objectNames": [f"phase-{index}-title" for index in (1, 2, 3)]},
                                {"field": "phases[].logic", "objectNames": [f"phase-{index}-logic" for index in (1, 2, 3)]},
                                {"field": "phases[].successCriterion", "objectNames": [f"phase-{index}-criterion" for index in (1, 2, 3)]},
                                {"field": "phases[].action", "objectNames": [f"phase-{index}-action" for index in (1, 2, 3)]},
                            ],
                        }]
                    }
                },
                phase_valid_errors,
            )
            certified_phases = [
                {
                    "title": phase["title"],
                    "logic": phase["logic"],
                    "criterion": phase["successCriterion"],
                    "action": phase["action"],
                }
                for phase in phases
            ]
            certified_phase_errors: list[dict[str, Any]] = []
            audit_phase_playbooks(
                archive,
                {"slides": [
                    {"layoutId": "cover", "title": "封面"},
                    {"layoutId": "phasePlaybook", "slotContent": {"phases": certified_phases}},
                ]},
                {
                    "renderValidation": {
                        "slides": [{
                            "slide": 2,
                            "layout": "phasePlaybook",
                            "rows": [
                                {"field": "phases[].title", "objectNames": [f"phase-{index}-title" for index in (1, 2, 3)]},
                                {"field": "phases[].logic", "objectNames": [f"phase-{index}-logic" for index in (1, 2, 3)]},
                                {"field": "phases[].criterion", "objectNames": [f"phase-{index}-criterion" for index in (1, 2, 3)]},
                                {"field": "phases[].action", "objectNames": [f"phase-{index}-action" for index in (1, 2, 3)]},
                            ],
                        }]
                    }
                },
                certified_phase_errors,
            )
        rules = {item["rule"] for item in errors}
        phase_missing_rules = {item["rule"] for item in phase_missing_contract_errors}
        checks = {
            "duplicate_native_and_external_category_labels_block": "duplicate_label_ownership" in rules,
            "duplicate_native_and_external_value_labels_block": any(
                item["rule"] == "duplicate_label_ownership" and "数据标签" in item["detail"]
                for item in errors
            ),
            "integer_percent_display_is_enforced": "percentage_precision_mismatch" in rules,
            "percentage_and_percentage_point_semantics_are_required": "percentage_semantics_missing" in rules,
            "smoothed_financial_time_series_blocks": "financial_line_smoothing_forbidden" in rules,
            "phase_playbook_contract_is_required": "phase_playbook_render_contract_missing" in phase_missing_rules,
            "complete_phase_playbook_golden_fixture_passes": not phase_valid_errors,
            "certified_renderer_phase_playbook_shape_passes": not certified_phase_errors,
            "chart_audit_records_native_state": bool(charts and charts[0]["smoothed"]),
        }
        if not all(checks.values()):
            raise RuntimeError(f"Self-test failed: {checks}; errors={errors}")
        print(json.dumps({"passed": True, "tests": list(checks)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", type=Path)
    parser.add_argument("--content", type=Path)
    parser.add_argument("--format-contract", type=Path)
    parser.add_argument("--review-json", type=Path)
    parser.add_argument("--screenshot-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (args.pptx, args.content, args.format_contract, args.review_json, args.screenshot_dir)
    if any(value is None for value in required):
        parser.error("--pptx, --content, --format-contract, --review-json and --screenshot-dir are required")
    try:
        report = build_report(
            args.pptx.expanduser().resolve(),
            args.content.expanduser().resolve(),
            args.format_contract.expanduser().resolve(),
            args.review_json.expanduser().resolve(),
            args.screenshot_dir.expanduser().resolve(),
        )
        write_report(args.output.expanduser().resolve() if args.output else None, report)
        return 0 if report["passed"] else 1
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
