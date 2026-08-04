#!/usr/bin/env python3
"""Regression tests for the executable PowerPoint master contract."""

from __future__ import annotations

import importlib.util
import json
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / "references" / "powerpoint-master-contract.json").read_text(encoding="utf-8"))
TOKENS = json.loads((ROOT / "references" / "design-tokens.json").read_text(encoding="utf-8"))

SPEC = importlib.util.spec_from_file_location("validate_powerpoint_master", ROOT / "scripts" / "validate_powerpoint_master.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


class PowerPointMasterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = ROOT / CONTRACT["templateFile"]
        self.library = ROOT / CONTRACT["layoutLibraryFile"]

    def test_contract_has_eight_foundational_profiles(self) -> None:
        self.assertEqual(8, len(CONTRACT["profiles"]))
        self.assertEqual(
            [
                "cover", "navigator", "section-divider", "content-title-only",
                "content-title-subtitle", "appendix-divider", "appendix-title-only", "appendix-title-subtitle",
            ],
            [profile["profileId"] for profile in CONTRACT["profiles"]],
        )

    def test_master_and_renderer_responsibilities_do_not_overlap(self) -> None:
        master = set(CONTRACT["policy"]["masterOwns"])
        renderer = set(CONTRACT["policy"]["certifiedRendererOwns"])
        self.assertFalse(master & renderer)
        self.assertFalse(CONTRACT["policy"]["freeformBodyGeometryAllowed"])

    def test_contract_uses_only_schema_valid_ooxml_layout_types(self) -> None:
        actual = {profile["layoutType"] for profile in CONTRACT["profiles"]}
        self.assertTrue(actual <= VALIDATOR.VALID_SLIDE_LAYOUT_TYPES)
        self.assertNotIn("titleAndContent", actual)
        self.assertNotIn("sectionHeader", actual)

    def test_body_bearing_profiles_use_custom_layout_type(self) -> None:
        body_profiles = [profile for profile in CONTRACT["profiles"] if "content-body" in profile["placeholders"]]
        self.assertTrue(body_profiles)
        self.assertTrue(all(profile["layoutType"] == "cust" for profile in body_profiles))

    def test_header_chrome_is_fixed_not_a_promoted_placeholder(self) -> None:
        self.assertTrue(all("header-text" not in profile["placeholders"] for profile in CONTRACT["profiles"]))
        for package in (self.template, self.library):
            with zipfile.ZipFile(package) as archive:
                layout_xml = b"\n".join(
                    archive.read(name)
                    for name in archive.namelist()
                    if name.startswith("ppt/slideLayouts/slideLayout") and name.endswith(".xml")
                )
            self.assertNotIn(b'<p:ph type="hdr"', layout_xml)

    def test_template_exists_and_is_a_template_package(self) -> None:
        self.assertTrue(self.template.is_file())
        with zipfile.ZipFile(self.template) as archive:
            content_types = archive.read("[Content_Types].xml")
            self.assertIn(b"presentationml.template.main+xml", content_types)

    def test_template_contains_no_sample_slides(self) -> None:
        with zipfile.ZipFile(self.template) as archive:
            slides = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        self.assertEqual([], slides)

    def test_template_keeps_all_presentation_level_relationships_referenced_by_xml(self) -> None:
        result = VALIDATOR.validate_package(self.template, is_template=True, contract=CONTRACT, tokens=TOKENS)
        self.assertFalse(
            any("references missing relationships" in error for error in result["errors"]),
            result["errors"],
        )

    def test_library_contains_one_sample_per_profile(self) -> None:
        with zipfile.ZipFile(self.library) as archive:
            slides = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        self.assertEqual(len(CONTRACT["profiles"]), len(slides))

    def test_both_packages_pass_structural_gate(self) -> None:
        template_result = VALIDATOR.validate_package(self.template, is_template=True, contract=CONTRACT, tokens=TOKENS)
        library_result = VALIDATOR.validate_package(self.library, is_template=False, contract=CONTRACT, tokens=TOKENS)
        self.assertTrue(template_result["passed"], template_result["errors"])
        self.assertTrue(library_result["passed"], library_result["errors"])

    def test_master_binding_uses_certified_registry(self) -> None:
        binding = CONTRACT["certifiedLayoutBinding"]
        self.assertEqual("references/certified-layout-registry.json", binding["registry"])
        self.assertEqual("scripts/render_certified_layout.mjs", binding["renderer"])
        self.assertTrue(binding["requireTemplateVersionInRenderResult"])

    def test_template_files_do_not_use_personal_names(self) -> None:
        self.assertNotIn("linzhe", self.template.name.lower())
        self.assertNotIn("linzhe", self.library.name.lower())


if __name__ == "__main__":
    unittest.main()
