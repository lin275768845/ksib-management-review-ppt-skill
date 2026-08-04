#!/usr/bin/env python3
"""Regression tests for the certified-layout fidelity gate."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from validate_layout_fidelity import A_NS, P_NS, R_NS, REL_NS, resolve_zip_target, validate


EMU = 914400


def emu(value: float) -> int:
    return round(value * EMU)


def shape(object_id: int, name: str, geometry: tuple[float, float, float, float], paragraphs: list[str], font_pt: int | None = None) -> str:
    x, y, width, height = geometry
    font_attribute = f' sz="{font_pt * 100}"' if font_pt else ""
    paragraphs_xml = "".join(
        f'<a:p><a:r><a:rPr{font_attribute}/><a:t>{text}</a:t></a:r></a:p>'
        for text in paragraphs
    )
    return f'''<p:sp><p:nvSpPr><p:cNvPr id="{object_id}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(width)}" cy="{emu(height)}"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>{paragraphs_xml}</p:txBody></p:sp>'''


def graphic(object_id: int, name: str, geometry: tuple[float, float, float, float]) -> str:
    x, y, width, height = geometry
    return f'''<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{object_id}" name="{name}"/><p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="{emu(x)}" y="{emu(y)}"/><a:ext cx="{emu(width)}" cy="{emu(height)}"/></p:xfrm><a:graphic><a:graphicData uri="chart"/></a:graphic></p:graphicFrame>'''


def write_pptx(target: Path, objects: list[str]) -> None:
    presentation = f'''<p:presentation xmlns:p="{P_NS}" xmlns:r="{R_NS}"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'''
    relationships = f'''<Relationships xmlns="{REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>'''
    slide = f'''<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name="root"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>{''.join(objects)}</p:spTree></p:cSld></p:sld>'''
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
        archive.writestr("ppt/slides/slide1.xml", slide)


def sources(base: Path) -> tuple[Path, Path, Path, Path, Path]:
    references = Path(__file__).resolve().parent.parent / "references"
    return (
        references / "certified-layout-registry.json",
        references / "component-registry.json",
        references / "typography-roles.json",
        references / "powerpoint-master-contract.json",
        references / "design-tokens.json",
    )


def render_plan(registry: Path, components: Path, typography: Path, master: Path, design_tokens: Path) -> dict:
    from validate_layout_fidelity import sha256_file

    def geometry(x: float, y: float, w: float, h: float) -> dict:
        return {"x": x, "y": y, "w": w, "h": h, "xEmu": emu(x), "yEmu": emu(y), "wEmu": emu(w), "hEmu": emu(h)}

    specs = [
        ("mainExhibit", "S01-main-exhibit", "native-chart", ["graphicFrame"], (0.8, 1.52, 7.7, 5.13), None, None),
        ("insightPanel", "S01-insight-panel", "insight-panel", ["shape"], (8.85, 1.52, 3.683, 5.13), None, None),
        ("insightTitle", "S01-insight-title", "insight-title", ["shape"], (9.05, 1.72, 3.283, 0.28), "module-title-14", 14),
        ("insightLead", "S01-insight-lead", "insight-lead", ["shape"], (9.05, 2.18, 3.283, 0.72), "insight-lead-14", 14),
        ("insightItems", "S01-insight-items", "insight-list", ["shape"], (9.05, 3.1, 3.283, 3.35), "body-secondary-12", 12),
    ]
    return {
        "schemaVersion": "ksib-render-plan/1.0",
        "masterTemplateVersion": json.loads(master.read_text(encoding="utf-8"))["templateVersion"],
        "designTokensVersion": json.loads(design_tokens.read_text(encoding="utf-8"))["schemaVersion"],
        "sourceHashes": {
            "registrySha256": sha256_file(registry),
            "componentsSha256": sha256_file(components),
            "typographySha256": sha256_file(typography),
            "masterSha256": sha256_file(master),
            "designTokensSha256": sha256_file(design_tokens),
        },
        "rules": {"llmMayGenerateGeometry": False, "freeformBodyObjectsAllowed": False},
        "slides": [{
            "slide": 1,
            "storylineId": "S01",
            "layoutId": "evidenceInsight",
            "variantId": "right-panel-standard",
            "bodyRegion": geometry(0.8, 1.52, 11.733, 5.13),
            "expectedObjects": [
                {
                    "slotId": slot,
                    "componentId": component,
                    "objectName": name,
                    "allowedObjectTypes": types,
                    "geometry": geometry(*coords),
                    "geometryToleranceEmu": 0,
                    "typographyRole": role,
                    "expectedFontSizePt": size,
                    "itemCount": 3 if slot == "insightItems" else None,
                }
                for slot, name, component, types, coords, role, size in specs
            ],
        }],
    }


class LayoutFidelityTests(unittest.TestCase):
    def test_resolves_relative_and_absolute_package_targets(self) -> None:
        self.assertEqual(resolve_zip_target("ppt/presentation.xml", "slides/slide1.xml"), "ppt/slides/slide1.xml")
        self.assertEqual(resolve_zip_target("ppt/presentation.xml", "/ppt/slides/slide1.xml"), "ppt/slides/slide1.xml")

    def test_accepts_exact_certified_geometry_and_typography(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, components, typography, master, design_tokens = sources(root)
            plan_path = root / "render-plan.json"
            plan_path.write_text(json.dumps(render_plan(registry, components, typography, master, design_tokens)), encoding="utf-8")
            pptx = root / "valid.pptx"
            write_pptx(pptx, [
                graphic(2, "S01-main-exhibit", (0.8, 1.52, 7.7, 5.13)),
                shape(3, "S01-insight-panel", (8.85, 1.52, 3.683, 5.13), []),
                shape(4, "S01-insight-title", (9.05, 1.72, 3.283, 0.28), ["管理含义"], 14),
                shape(5, "S01-insight-lead", (9.05, 2.18, 3.283, 0.72), ["证据指向一个明确决策"], 14),
                shape(6, "S01-insight-items", (9.05, 3.1, 3.283, 3.35), ["第一条", "第二条", "第三条"], 12),
            ])
            report = validate(pptx, plan_path, registry, components, typography, master, design_tokens)
            self.assertTrue(report["passed"], report["errors"])

    def test_blocks_geometry_typography_and_freeform_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, components, typography, master, design_tokens = sources(root)
            plan_path = root / "render-plan.json"
            plan_path.write_text(json.dumps(render_plan(registry, components, typography, master, design_tokens)), encoding="utf-8")
            pptx = root / "invalid.pptx"
            write_pptx(pptx, [
                graphic(2, "S01-main-exhibit", (0.81, 1.52, 7.7, 5.13)),
                shape(3, "S01-insight-panel", (8.85, 1.52, 3.683, 5.13), []),
                shape(4, "S01-insight-title", (9.05, 1.72, 3.283, 0.28), ["管理含义"], 12),
                shape(5, "S01-insight-lead", (9.05, 2.18, 3.283, 0.72), ["证据指向一个明确决策"], 14),
                shape(6, "S01-insight-items", (9.05, 3.1, 3.283, 3.35), ["第一条", "第二条"], 12),
                shape(7, "freeform-extra", (1.0, 2.0, 1.0, 0.5), ["临时自由文本"], 10),
            ])
            report = validate(pptx, plan_path, registry, components, typography, master, design_tokens)
            rules = {item["rule"] for item in report["errors"]}
            self.assertFalse(report["passed"])
            self.assertTrue({
                "certified_geometry_mismatch",
                "certified_typography_role_mismatch",
                "certified_item_count_mismatch",
                "uncertified_body_object",
            }.issubset(rules), rules)


def run_embedded_self_test() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LayoutFidelityTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("layout fidelity self-test failed")


if __name__ == "__main__":
    unittest.main()
