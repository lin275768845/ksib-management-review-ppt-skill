#!/usr/bin/env python3
"""Create a non-overwriting PowerPoint revision workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = "ksib-pptx-revision/1.0"
REQUIRED_PPTX_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "ppt/presentation.xml",
}


class RevisionError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pptx(path: Path) -> None:
    if path.suffix.casefold() != ".pptx":
        raise RevisionError("input必须是.pptx文件")
    if not path.is_file():
        raise RevisionError(f"input不存在: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = sorted(REQUIRED_PPTX_PARTS - names)
            if missing:
                raise RevisionError(
                    f"input不是完整PPTX，缺少: {', '.join(missing)}"
                )
            bad_part = archive.testzip()
            if bad_part:
                raise RevisionError(f"input ZIP校验失败: {bad_part}")
    except zipfile.BadZipFile as error:
        raise RevisionError("input不是合法PPTX ZIP包") from error


def safe_label(value: str | None) -> str:
    if not value:
        return "revision"
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    return cleaned[:40] or "revision"


def prepare_revision(
    input_path: Path,
    workspace: Path,
    *,
    label: str | None = None,
    now: datetime | None = None,
) -> dict:
    input_path = input_path.expanduser().resolve()
    workspace = workspace.expanduser().resolve()
    validate_pptx(input_path)
    input_sha256 = sha256_file(input_path)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    revision_id = (
        f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}-"
        f"{input_sha256[:8]}-{safe_label(label)}"
    )
    revision_root = workspace / revision_id
    if revision_root.exists():
        raise RevisionError(f"revision已存在，拒绝覆盖: {revision_root}")
    source_dir = revision_root / "source"
    work_dir = revision_root / "work"
    qa_dir = revision_root / "qa"
    source_dir.mkdir(parents=True)
    work_dir.mkdir()
    qa_dir.mkdir()

    source_copy = source_dir / input_path.name
    working_copy = work_dir / f"{input_path.stem}.working.pptx"
    shutil.copy2(input_path, source_copy)
    shutil.copy2(input_path, working_copy)
    source_sha256 = sha256_file(source_copy)
    working_sha256 = sha256_file(working_copy)
    if source_sha256 != input_sha256 or working_sha256 != input_sha256:
        raise RevisionError("工作副本哈希与输入不一致")

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "revisionId": revision_id,
        "createdAt": timestamp.isoformat().replace("+00:00", "Z"),
        "input": {
            "fileName": input_path.name,
            "sha256": input_sha256,
            "bytes": input_path.stat().st_size,
        },
        "copies": {
            "source": {
                "relativePath": str(source_copy.relative_to(revision_root)),
                "sha256": source_sha256,
            },
            "working": {
                "relativePath": str(working_copy.relative_to(revision_root)),
                "sha256": working_sha256,
            },
        },
        "policy": {
            "inputMustRemainUnchanged": True,
            "workingCopyMayBeModified": True,
            "finalOutputMustUseNewPath": True,
        },
    }
    manifest_path = revision_root / "revision-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **manifest,
        "revisionRoot": str(revision_root),
        "sourceCopy": str(source_copy),
        "workingCopy": str(working_copy),
        "manifest": str(manifest_path),
    }


def make_fixture(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr(
            "ppt/presentation.xml",
            "<p:presentation xmlns:p="
            '"http://schemas.openxmlformats.org/presentationml/2006/main"/>',
        )


def self_test() -> dict:
    tests: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        input_path = root / "client.pptx"
        make_fixture(input_path)
        original_sha256 = sha256_file(input_path)
        first = prepare_revision(
            input_path,
            root / "revisions",
            label="format-only",
            now=datetime(2026, 7, 30, 12, 0, 0, 1, tzinfo=timezone.utc),
        )
        tests["working_copy_matches_input"] = (
            sha256_file(Path(first["workingCopy"])) == original_sha256
        )
        tests["source_copy_matches_input"] = (
            sha256_file(Path(first["sourceCopy"])) == original_sha256
        )
        tests["original_remains_unchanged"] = (
            sha256_file(input_path) == original_sha256
        )
        second = prepare_revision(
            input_path,
            root / "revisions",
            label="format-only",
            now=datetime(2026, 7, 30, 12, 0, 0, 2, tzinfo=timezone.utc),
        )
        tests["revisions_never_share_output_path"] = (
            first["revisionRoot"] != second["revisionRoot"]
        )
    return {
        "passed": all(tests.values()),
        "tests": tests,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--workspace")
    parser.add_argument("--label")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        report = self_test()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["passed"] else 1)
    if not args.input or not args.workspace:
        parser.error("--input和--workspace为必填项")
    try:
        report = prepare_revision(
            Path(args.input),
            Path(args.workspace),
            label=args.label,
        )
    except RevisionError as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
