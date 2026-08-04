import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { validateThemeUsage } from "./validate_theme_usage.mjs";

const contract = JSON.parse(await readFile(new URL("../references/theme-color-contract.json", import.meta.url), "utf8"));

function color(bindingRef, resolvedHex) {
  return { bindingRef, visible: true, resolutionStatus: "resolved", resolvedHex };
}

function validInventory() {
  return {
    schemaVersion: "ksib-pptx-color-inventory/1.0",
    pptx: { fileName: "final.pptx", sha256: "pptx-sha" },
    extractorSha256: "extractor-sha",
    slideCount: 2,
    slides: [
      { slide: 1, objects: [{ objectRef: "slide-1/name:title", stable: true, colors: [color("color:title", "#1F2329")] }] },
      { slide: 2, objects: [{ objectRef: "slide-2/name:chart", stable: true, colors: [
        color("color:main", "#FF4906"),
        color("color:peer", "#006B8F"),
        color("color:other", "#D9DCE1"),
      ] }] },
    ],
  };
}

function validUsage() {
  return {
    schemaVersion: "ksib-theme-usage/1.1",
    themeContractVersion: "ksib-theme-color-contract/1.0",
    pptxArtifactSha256: "pptx-sha",
    slideCount: 2,
    slides: [
      {
        slide: 1,
        pattern: "no-data",
        elements: [{ id: "title", role: "text", token: "neutral.textStrong", backgroundToken: "neutral.white", purpose: "text" }],
        bindings: [{ bindingRef: "color:title", elementId: "title", token: "neutral.textStrong" }],
      },
      {
        slide: 2,
        pattern: "two-way-comparison",
        dominantEvidenceObject: "main",
        dominantEvidenceToken: "primary.base",
        elements: [
          { id: "main", role: "data", token: "primary.base", purpose: "focus" },
          { id: "peer", role: "data", token: "contrast.base", purpose: "comparison" },
          { id: "other", role: "data", token: "neutral.series", purpose: "other" },
        ],
        bindings: [
          { bindingRef: "color:main", elementId: "main", token: "primary.base" },
          { bindingRef: "color:peer", elementId: "peer", token: "contrast.base" },
          { bindingRef: "color:other", elementId: "other", token: "neutral.series" },
        ],
      },
    ],
    exceptions: [],
  };
}

function validate(usage = validUsage(), inventory = validInventory()) {
  return validateThemeUsage(contract, usage, inventory, { expectedExtractorSha256: "extractor-sha" });
}

test("accepts an exact declaration of every final PPTX color binding", () => {
  const report = validate();
  assert.equal(report.passed, true, JSON.stringify(report.errors));
  assert.equal(report.checkedVisibleBindings, 4);
  assert.equal(report.artifactSha256, "pptx-sha");
});

test("blocks renderer declarations that disagree with actual PPTX color", () => {
  const inventory = validInventory();
  inventory.slides[1].objects[0].colors[0].resolvedHex = "#D83D00";
  assert.ok(validate(validUsage(), inventory).errors.some((item) => item.rule === "actual_color_mismatch"));
});

test("blocks undeclared actual colors and phantom renderer bindings", () => {
  const usage = validUsage();
  usage.slides[1].bindings.pop();
  usage.slides[1].bindings.push({ bindingRef: "color:phantom", elementId: "other", token: "neutral.series" });
  const rules = validate(usage).errors.map((item) => item.rule);
  assert.ok(rules.includes("undeclared_actual_color"));
  assert.ok(rules.includes("phantom_binding"));
});

test("blocks duplicate bindings and wrong-page declarations", () => {
  const usage = validUsage();
  usage.slides[0].bindings.push({ bindingRef: "color:main", elementId: "title", token: "neutral.textStrong" });
  const rules = validate(usage).errors.map((item) => item.rule);
  assert.ok(rules.includes("duplicate_binding"));
  assert.ok(rules.includes("binding_slide_mismatch"));
});

test("blocks unresolved colors, unstable colored objects and stale extractor", () => {
  const inventory = validInventory();
  inventory.extractorSha256 = "old-extractor";
  inventory.slides[1].objects[0].stable = false;
  inventory.slides[1].objects[0].colors[0].resolutionStatus = "unresolved";
  inventory.slides[1].objects[0].colors[0].resolvedHex = null;
  const rules = validate(validUsage(), inventory).errors.map((item) => item.rule);
  assert.ok(rules.includes("stale_extractor"));
  assert.ok(rules.includes("unstable_colored_object"));
  assert.ok(rules.includes("unresolved_actual_color"));
});

test("blocks usage bound to a different final PPTX", () => {
  const usage = validUsage();
  usage.pptxArtifactSha256 = "other-pptx";
  assert.ok(validate(usage).errors.some((item) => item.rule === "pptx_hash_mismatch"));
});

test("blocks a saved inventory that differs from live re-extraction", () => {
  const report = validateThemeUsage(contract, validUsage(), validInventory(), {
    expectedExtractorSha256: "extractor-sha",
    inventorySemanticSha256: "saved-inventory",
    reExtractedInventorySemanticSha256: "live-final-pptx",
  });
  assert.ok(report.errors.some((item) => item.rule === "inventory_reextract_mismatch"));
});

test("blocks arbitrary colors, dark gray data fills and gray as focal evidence", () => {
  const usage = validUsage();
  usage.slides[1].dominantEvidenceToken = "neutral.series";
  usage.slides[1].elements.push({ id: "bad", role: "data", token: "neutral.textStrong", purpose: "text", rawHex: "#333333" });
  const rules = validate(usage).errors.map((item) => item.rule);
  assert.ok(rules.includes("raw_hex"));
  assert.ok(rules.includes("dark_neutral_data_fill"));
  assert.ok(rules.includes("neutral_dominant"));
});

test("allows only explicitly approved exact-color exceptions", () => {
  const usage = validUsage();
  const inventory = validInventory();
  inventory.slides[1].objects[0].colors[1].resolvedHex = "#123456";
  usage.slides[1].bindings[1] = { bindingRef: "color:peer", elementId: "peer", exceptionRef: "approved-brand" };
  usage.exceptions = [{ id: "approved-brand", slide: 2, elementId: "peer", rawColor: "#123456", reason: "用户提供的已批准品牌色", approvalRef: "user-approval-2026-08-04", status: "user-approved" }];
  assert.equal(validate(usage, inventory).passed, true);
  usage.exceptions[0].reason = "更好看";
  assert.ok(validate(usage, inventory).errors.some((item) => item.rule === "decorative_exception"));
});

test("blocks insufficient text contrast", () => {
  const usage = validUsage();
  usage.slides[0].elements[0] = { id: "title", role: "text", token: "neutral.textMuted", backgroundToken: "neutral.series", purpose: "text" };
  assert.ok(validate(usage).errors.some((item) => item.rule === "text_contrast"));
});
