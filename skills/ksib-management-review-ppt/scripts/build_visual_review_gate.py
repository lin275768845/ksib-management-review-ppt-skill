#!/usr/bin/env python3
"""Bind a full-slide visual review to one exact PPTX and its rendered PNGs."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import tempfile
import zipfile
import zlib
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


SCHEMA_VERSION = "ksib-visual-review/2.0"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
REQUIRED_CHECKS = (
    "fullSizeReview",
    "noOverlap",
    "noClipping",
    "noUnexpectedWrap",
    "footerAndPageNumber",
    "chartDataAndSources",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_RENDER_WIDTH = 960
MIN_RENDER_HEIGHT = 540
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
PNG_VALID_BIT_DEPTHS = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    3: {1, 2, 4, 8},
    4: {8, 16},
    6: {8, 16},
}


class VisualGateError(RuntimeError):
    """Raised when visual-review inputs are structurally invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def pptx_metadata(path: Path) -> dict[str, int | None]:
    try:
        with zipfile.ZipFile(path) as archive:
            payload = archive.read("ppt/presentation.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise VisualGateError(f"Cannot read PPTX presentation.xml: {error}") from error
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise VisualGateError(f"Malformed presentation.xml: {error}") from error
    slide_size = root.find(f"{{{P_NS}}}sldSz")
    return {
        "slideCount": sum(1 for _ in root.iter(f"{{{P_NS}}}sldId")),
        "widthEmu": int(slide_size.get("cx")) if slide_size is not None and slide_size.get("cx") else None,
        "heightEmu": int(slide_size.get("cy")) if slide_size is not None and slide_size.get("cy") else None,
    }


def paeth_predictor(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def parse_png(payload: bytes) -> dict[str, int | str]:
    """Validate PNG structure, CRCs and image payload; return image metadata."""
    if not payload.startswith(PNG_SIGNATURE):
        raise VisualGateError("PNG signature missing")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    saw_iend = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise VisualGateError("truncated PNG chunk")
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        chunk_type = payload[offset + 4:offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise VisualGateError("PNG chunk length exceeds file size")
        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            raise VisualGateError(f"PNG CRC mismatch in {chunk_type.decode('ascii', errors='replace')}")
        chunks.append((chunk_type, chunk_data))
        offset = crc_end
        if chunk_type == b"IEND":
            if length != 0:
                raise VisualGateError("PNG IEND must be empty")
            saw_iend = True
            break
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        raise VisualGateError("PNG must start with a 13-byte IHDR")
    if not saw_iend or offset != len(payload):
        raise VisualGateError("PNG missing terminal IEND or contains trailing bytes")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    if width <= 0 or height <= 0:
        raise VisualGateError("PNG dimensions must be positive")
    if color_type not in PNG_CHANNELS or bit_depth not in PNG_VALID_BIT_DEPTHS[color_type]:
        raise VisualGateError(f"unsupported PNG color type/bit depth: {color_type}/{bit_depth}")
    if compression != 0 or filter_method != 0 or interlace not in {0, 1}:
        raise VisualGateError("unsupported PNG compression, filter or interlace method")
    if interlace == 1:
        raise VisualGateError(
            "interlaced PNG is not supported; render a non-interlaced full-slide PNG"
        )
    idat = b"".join(data for chunk_type, data in chunks if chunk_type == b"IDAT")
    if not idat:
        raise VisualGateError("PNG has no IDAT payload")
    try:
        decoded = zlib.decompress(idat)
    except zlib.error as error:
        raise VisualGateError(f"PNG IDAT cannot be decompressed: {error}") from error
    row_bytes = (width * PNG_CHANNELS[color_type] * bit_depth + 7) // 8
    expected_length = height * (row_bytes + 1)
    if len(decoded) != expected_length:
        raise VisualGateError(
            f"PNG decoded size mismatch: {len(decoded)} != {expected_length}"
        )
    stride = row_bytes + 1
    if any(decoded[row * stride] > 4 for row in range(height)):
        raise VisualGateError("PNG scanline uses an invalid filter type")
    bytes_per_pixel = max(
        1,
        (PNG_CHANNELS[color_type] * bit_depth + 7) // 8,
    )
    previous = bytearray(row_bytes)
    canonical_pixels = bytearray()
    for row in range(height):
        start = row * stride
        filter_type = decoded[start]
        raw = decoded[start + 1:start + stride]
        reconstructed = bytearray(row_bytes)
        for column, value in enumerate(raw):
            left = (
                reconstructed[column - bytes_per_pixel]
                if column >= bytes_per_pixel
                else 0
            )
            up = previous[column]
            up_left = (
                previous[column - bytes_per_pixel]
                if column >= bytes_per_pixel
                else 0
            )
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            else:
                predictor = paeth_predictor(left, up, up_left)
            reconstructed[column] = (value + predictor) & 0xFF
        canonical_pixels.extend(reconstructed)
        previous = reconstructed
    visual_chunk_types = {
        b"PLTE",
        b"tRNS",
        b"gAMA",
        b"cHRM",
        b"sRGB",
        b"iCCP",
    }
    visual_metadata = b"".join(
        chunk_type + struct.pack(">I", len(chunk_data)) + chunk_data
        for chunk_type, chunk_data in chunks
        if chunk_type in visual_chunk_types
    )
    pixel_hash_payload = (
        struct.pack(">IIBB", width, height, bit_depth, color_type)
        + visual_metadata
        + bytes(canonical_pixels)
    )
    return {
        "width": width,
        "height": height,
        "bitDepth": bit_depth,
        "colorType": color_type,
        "interlace": interlace,
        "pixelSha256": hashlib.sha256(pixel_hash_payload).hexdigest(),
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VisualGateError(f"Cannot read review JSON: {error}") from error
    if not isinstance(value, dict):
        raise VisualGateError("Review JSON must be an object")
    return value


def safe_render_path(render_dir: Path, file_name: str) -> Path:
    if not file_name or Path(file_name).name != file_name:
        raise VisualGateError(f"renderFile must be a file name without directories: {file_name}")
    candidate = (render_dir / file_name).resolve()
    try:
        candidate.relative_to(render_dir.resolve())
    except ValueError as error:
        raise VisualGateError(f"renderFile escapes render directory: {file_name}") from error
    return candidate


def build_visual_gate(
    pptx: Path,
    render_dir: Path,
    review_json: Path,
) -> dict[str, Any]:
    pptx = pptx.expanduser().resolve()
    render_dir = render_dir.expanduser().resolve()
    review_json = review_json.expanduser().resolve()
    if not pptx.is_file():
        raise VisualGateError(f"PPTX not found: {pptx}")
    if not render_dir.is_dir():
        raise VisualGateError(f"Render directory not found: {render_dir}")

    review = read_json(review_json)
    metadata = pptx_metadata(pptx)
    slide_count = int(metadata["slideCount"] or 0)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checks = review.get("checks") if isinstance(review.get("checks"), dict) else {}

    def add_error(rule: str, detail: str, **context: Any) -> None:
        errors.append({"rule": rule, "detail": detail, **context})

    if not review.get("reviewedBy"):
        add_error("reviewer_missing", "reviewedBy不能为空")
    if not review.get("reviewedAt"):
        add_error("reviewed_at_missing", "reviewedAt不能为空")
    for check_name in REQUIRED_CHECKS:
        if checks.get(check_name) is not True:
            add_error("global_visual_check_failed", f"checks.{check_name}必须为true")

    slide_reviews = review.get("slideReviews")
    if not isinstance(slide_reviews, list):
        add_error("slide_reviews_missing", "slideReviews[]必须逐页登记")
        slide_reviews = []
    by_slide: dict[int, dict[str, Any]] = {}
    used_render_files: set[str] = set()
    for index, item in enumerate(slide_reviews):
        if not isinstance(item, dict):
            add_error("slide_review_invalid", f"slideReviews[{index}]必须为对象")
            continue
        slide = item.get("slide")
        if not isinstance(slide, int) or slide < 1:
            add_error("slide_number_invalid", f"slideReviews[{index}].slide必须为正整数")
            continue
        if slide in by_slide:
            add_error("slide_review_duplicate", f"第{slide}页重复登记")
            continue
        by_slide[slide] = item

    slide_records: list[dict[str, Any]] = []
    render_hash_to_slide: dict[str, int] = {}
    pixel_hash_to_slide: dict[str, int] = {}
    for slide in range(1, slide_count + 1):
        item = by_slide.get(slide)
        if item is None:
            add_error("slide_review_missing", f"第{slide}页没有逐页复核记录")
            continue
        render_file = str(item.get("renderFile") or "")
        if render_file in used_render_files:
            add_error("render_file_duplicate", f"{render_file}被多页重复引用", slide=slide)
        used_render_files.add(render_file)
        try:
            render_path = safe_render_path(render_dir, render_file)
        except VisualGateError as error:
            add_error("render_file_invalid", str(error), slide=slide)
            continue
        if not render_path.is_file():
            add_error("render_file_missing", render_file, slide=slide)
            continue
        payload = render_path.read_bytes()
        render_sha256 = hashlib.sha256(payload).hexdigest()
        first_slide = render_hash_to_slide.get(render_sha256)
        if first_slide is not None:
            add_error(
                "render_content_duplicate",
                f"第{slide}页与第{first_slide}页引用了内容完全相同的PNG，逐页渲染不可复用",
                slide=slide,
                firstSlide=first_slide,
                sha256=render_sha256,
            )
        else:
            render_hash_to_slide[render_sha256] = slide
        png_metadata: dict[str, int | str] | None = None
        try:
            png_metadata = parse_png(payload)
        except VisualGateError as error:
            add_error("render_invalid_png", str(error), slide=slide, renderFile=render_file)
        if png_metadata:
            pixel_sha256 = str(png_metadata["pixelSha256"])
            first_pixel_slide = pixel_hash_to_slide.get(pixel_sha256)
            if first_pixel_slide is not None:
                add_error(
                    "render_pixels_duplicate",
                    f"第{slide}页与第{first_pixel_slide}页的规范化像素完全相同，PNG元数据或压缩差异不能视为不同渲染",
                    slide=slide,
                    firstSlide=first_pixel_slide,
                    pixelSha256=pixel_sha256,
                )
            else:
                pixel_hash_to_slide[pixel_sha256] = slide
        if png_metadata and (
            png_metadata["width"] < MIN_RENDER_WIDTH
            or png_metadata["height"] < MIN_RENDER_HEIGHT
        ):
            add_error(
                "render_resolution_too_low",
                f"{png_metadata['width']}×{png_metadata['height']}；最低{MIN_RENDER_WIDTH}×{MIN_RENDER_HEIGHT}",
                slide=slide,
            )
        if (
            png_metadata
            and metadata["widthEmu"]
            and metadata["heightEmu"]
        ):
            pptx_ratio = float(metadata["widthEmu"]) / float(metadata["heightEmu"])
            render_ratio = png_metadata["width"] / png_metadata["height"]
            if abs(render_ratio - pptx_ratio) / pptx_ratio > 0.01:
                add_error(
                    "render_aspect_ratio_mismatch",
                    f"PNG={render_ratio:.4f}, PPTX={pptx_ratio:.4f}",
                    slide=slide,
                )
        issues = item.get("issues", [])
        if not isinstance(issues, list):
            add_error("slide_issues_not_array", f"第{slide}页issues必须为数组")
            issues = ["invalid issues field"]
        if item.get("passed") is not True:
            add_error("slide_review_failed", f"第{slide}页passed必须为true")
        if issues:
            add_error("slide_review_has_issues", f"第{slide}页仍有未解决问题", issues=issues)
        slide_records.append({
            "slide": slide,
            "renderFile": render_file,
            "bytes": len(payload),
            "sha256": render_sha256,
            "pixelSha256": (
                str(png_metadata["pixelSha256"])
                if png_metadata
                else None
            ),
            "width": png_metadata["width"] if png_metadata else None,
            "height": png_metadata["height"] if png_metadata else None,
            "passed": item.get("passed") is True and not issues and png_metadata is not None,
            "notes": item.get("notes"),
        })

    unexpected_slides = sorted(set(by_slide) - set(range(1, slide_count + 1)))
    if unexpected_slides:
        add_error("slide_review_out_of_range", f"超出PPT页数：{unexpected_slides}")

    referenced_pngs = {
        record["renderFile"]
        for record in slide_records
    }
    available_pngs = {
        path.name
        for path in render_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".png"
    }
    unreviewed_pngs = sorted(available_pngs - referenced_pngs)
    if unreviewed_pngs:
        warnings.append({
            "rule": "unreviewed_extra_pngs",
            "detail": "渲染目录存在未绑定到页面的额外PNG",
            "files": unreviewed_pngs,
        })

    render_dimensions = {
        (record["width"], record["height"])
        for record in slide_records
        if record["width"] is not None and record["height"] is not None
    }
    if len(render_dimensions) > 1:
        add_error(
            "render_dimensions_inconsistent",
            f"逐页PNG尺寸不一致：{sorted(render_dimensions)}",
        )

    reviewed_slide_count = sum(1 for record in slide_records if record["passed"])
    render_set_hash = hashlib.sha256(
        stable_json([
            {
                "slide": record["slide"],
                "renderFile": record["renderFile"],
                "sha256": record["sha256"],
                "pixelSha256": record["pixelSha256"],
            }
            for record in slide_records
        ]).encode("utf-8")
    ).hexdigest()
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "validatorSha256": sha256_file(Path(__file__).resolve()),
        "passed": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "slideCount": slide_count,
        "reviewedSlideCount": reviewed_slide_count,
        "reviewedBy": review.get("reviewedBy"),
        "reviewedAt": review.get("reviewedAt"),
        "checks": checks,
        "pptx": {
            "fileName": pptx.name,
            "sha256": sha256_file(pptx),
            "slideCount": slide_count,
            "widthEmu": metadata["widthEmu"],
            "heightEmu": metadata["heightEmu"],
        },
        "renderSetHash": render_set_hash,
        "slides": slide_records,
        "errors": errors,
        "warnings": warnings,
    }
    return report


def write_json(path: Path | None, report: dict[str, Any]) -> None:
    output = f"{json.dumps(report, ensure_ascii=False, indent=2)}\n"
    if path is None:
        print(output, end="")
        return
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "output": str(path),
        "slideCount": report["slideCount"],
        "reviewedSlideCount": report["reviewedSlideCount"],
        "errorCount": report["errorCount"],
        "warningCount": report["warningCount"],
    }, ensure_ascii=False))


def self_test() -> None:
    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    def make_png_from_raw(
        width: int,
        height: int,
        raw: bytes,
        interlace: int = 0,
    ) -> bytes:
        ihdr = struct.pack(
            ">IIBBBBB",
            width,
            height,
            8,
            2,
            0,
            0,
            interlace,
        )
        return (
            PNG_SIGNATURE
            + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"IDAT", zlib.compress(raw))
            + png_chunk(b"IEND", b"")
        )

    def make_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
        scanline = b"\x00" + bytes(rgb) * width
        return make_png_from_raw(width, height, scanline * height)

    def add_text_metadata(payload: bytes, text: bytes) -> bytes:
        iend = png_chunk(b"IEND", b"")
        if not payload.endswith(iend):
            raise VisualGateError("self-test PNG has no terminal IEND")
        return payload[:-len(iend)] + png_chunk(b"tEXt", text) + iend

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        pptx = root / "fixture.pptx"
        render_dir = root / "renders"
        render_dir.mkdir()
        presentation = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P_NS}">
  <p:sldSz cx="12191695" cy="6858000"/>
  <p:sldIdLst><p:sldId id="256"/><p:sldId id="257"/></p:sldIdLst>
</p:presentation>""".encode()
        with zipfile.ZipFile(pptx, "w") as archive:
            archive.writestr("ppt/presentation.xml", presentation)
        for slide in (1, 2):
            (render_dir / f"slide-{slide}.png").write_bytes(
                make_png(1280, 720, (slide, 73, 6))
            )
        valid_review = {
            "reviewedBy": "reviewer",
            "reviewedAt": "2026-07-20T00:00:00Z",
            "checks": {name: True for name in REQUIRED_CHECKS},
            "slideReviews": [
                {
                    "slide": slide,
                    "renderFile": f"slide-{slide}.png",
                    "passed": True,
                    "issues": [],
                }
                for slide in (1, 2)
            ],
        }
        valid_path = root / "valid.json"
        valid_path.write_text(json.dumps(valid_review), encoding="utf-8")
        valid = build_visual_gate(pptx, render_dir, valid_path)
        invalid_path = root / "invalid.json"
        invalid_review = dict(valid_review)
        invalid_review["slideReviews"] = valid_review["slideReviews"][:1]
        invalid_path.write_text(json.dumps(invalid_review), encoding="utf-8")
        invalid = build_visual_gate(pptx, render_dir, invalid_path)
        fake_png_path = render_dir / "slide-1.png"
        fake_png_path.write_bytes(PNG_SIGNATURE + b"not-a-png")
        fake_png_review_path = root / "fake-png.json"
        fake_png_review_path.write_text(json.dumps(valid_review), encoding="utf-8")
        fake_png = build_visual_gate(pptx, render_dir, fake_png_review_path)
        fake_png_path.write_bytes(make_png_from_raw(1280, 720, b"\x00"))
        short_decoded_png = build_visual_gate(
            pptx,
            render_dir,
            fake_png_review_path,
        )
        fake_png_path.write_bytes(
            make_png_from_raw(1280, 720, b"\x00", interlace=1)
        )
        interlaced_png = build_visual_gate(
            pptx,
            render_dir,
            fake_png_review_path,
        )
        fake_png_path.write_bytes(make_png(1280, 720, (1, 73, 6)))
        (render_dir / "slide-2.png").write_bytes(fake_png_path.read_bytes())
        duplicate_content = build_visual_gate(
            pptx,
            render_dir,
            valid_path,
        )
        same_pixels = make_png(1280, 720, (9, 73, 6))
        fake_png_path.write_bytes(same_pixels)
        (render_dir / "slide-2.png").write_bytes(
            add_text_metadata(same_pixels, b"comment\x00metadata-only")
        )
        duplicate_pixels_with_metadata = build_visual_gate(
            pptx,
            render_dir,
            valid_path,
        )
        checks = {
            "valid_full_slide_review": valid["passed"],
            "missing_slide_review_blocks": any(
                item["rule"] == "slide_review_missing"
                for item in invalid["errors"]
            ),
            "pptx_and_png_hashes_recorded": bool(
                valid["pptx"]["sha256"]
                and valid["renderSetHash"]
                and all(item["sha256"] for item in valid["slides"])
            ),
            "validator_hash_recorded": (
                valid["validatorSha256"]
                == sha256_file(Path(__file__).resolve())
            ),
            "formal_error_contract_recorded": (
                valid["errorCount"] == 0 and valid["errors"] == []
            ),
            "fake_png_signature_payload_rejected": any(
                item["rule"] == "render_invalid_png"
                for item in fake_png["errors"]
            ),
            "short_decoded_png_payload_rejected": any(
                item["rule"] == "render_invalid_png"
                and "PNG decoded size mismatch: 1 != 2765520" in item["detail"]
                for item in short_decoded_png["errors"]
            ),
            "interlaced_png_rejected": any(
                item["rule"] == "render_invalid_png"
                and "interlaced PNG is not supported" in item["detail"]
                for item in interlaced_png["errors"]
            ),
            "same_png_content_under_different_names_rejected": any(
                item["rule"] == "render_content_duplicate"
                and item.get("slide") == 2
                and item.get("firstSlide") == 1
                for item in duplicate_content["errors"]
            ),
            "same_pixels_with_different_metadata_rejected": (
                any(
                    item["rule"] == "render_pixels_duplicate"
                    and item.get("slide") == 2
                    and item.get("firstSlide") == 1
                    for item in duplicate_pixels_with_metadata["errors"]
                )
                and not any(
                    item["rule"] == "render_content_duplicate"
                    for item in duplicate_pixels_with_metadata["errors"]
                )
            ),
            "render_dimensions_recorded": all(
                item["width"] == 1280 and item["height"] == 720
                for item in valid["slides"]
            ),
        }
        if not all(checks.values()):
            raise VisualGateError(f"Self-test failed: {checks}")
        print(json.dumps({"passed": True, "tests": list(checks)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", type=Path)
    parser.add_argument("--render-dir", type=Path)
    parser.add_argument("--review-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.pptx or not args.render_dir or not args.review_json:
        parser.error("--pptx, --render-dir and --review-json are required")
    try:
        report = build_visual_gate(args.pptx, args.render_dir, args.review_json)
        write_json(args.output, report)
        return 0 if report["passed"] else 1
    except VisualGateError as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
