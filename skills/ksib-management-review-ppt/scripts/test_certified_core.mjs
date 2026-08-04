import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { buildPayloads } from "../benchmarks/certified-layouts/core-library/fixtures.mjs";
import { validateCertifiedRenderInput } from "./render_certified_layout.mjs";
import { resolveRenderPlan } from "./resolve_render_plan.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REFERENCES = path.resolve(HERE, "../references");

async function sources() {
  const [registry, components, typography, master, tokens] = await Promise.all([
    fs.readFile(path.join(REFERENCES, "certified-layout-registry.json"), "utf8").then(JSON.parse),
    fs.readFile(path.join(REFERENCES, "component-registry.json"), "utf8").then(JSON.parse),
    fs.readFile(path.join(REFERENCES, "typography-roles.json"), "utf8").then(JSON.parse),
    fs.readFile(path.join(REFERENCES, "powerpoint-master-contract.json"), "utf8").then(JSON.parse),
    fs.readFile(path.join(REFERENCES, "design-tokens.json"), "utf8").then(JSON.parse),
  ]);
  return {
    registry,
    components,
    typography,
    master,
    tokens,
    hashes: {
      registrySha256: "test",
      componentsSha256: "test",
      typographySha256: "test",
      masterSha256: "test",
      tokensSha256: "test",
    },
  };
}

async function validFixture() {
  const loaded = await sources();
  const payloads = buildPayloads(loaded.registry);
  const plan = resolveRenderPlan(payloads.renderPlanInput, loaded);
  return { ...payloads, plan };
}

test("36-page Golden fixture covers all 12 Certified Core layouts and 18 variants", async () => {
  const { content, plan } = await validFixture();
  assert.equal(plan.slides.length, 36);
  assert.equal(new Set(plan.slides.map((slide) => slide.layoutId)).size, 12);
  assert.equal(new Set(plan.slides.map((slide) => `${slide.layoutId}/${slide.variantId}`)).size, 18);
  assert.doesNotThrow(() => validateCertifiedRenderInput(plan, content));
});

test("renderer blocks layout drift", async () => {
  const { content, plan } = await validFixture();
  const invalid = structuredClone(content);
  invalid.slides[0].layoutId = "singleExhibit";
  assert.throws(() => validateCertifiedRenderInput(plan, invalid), /layoutId/);
});

test("phasePlaybook blocks a missing action field", async () => {
  const { content, plan } = await validFixture();
  const invalid = structuredClone(content);
  const slide = invalid.slides.find((item) => item.layoutId === "phasePlaybook");
  delete slide.slotContent.phases[0].action;
  assert.throws(() => validateCertifiedRenderInput(plan, invalid), /action is required/);
});

test("native table blocks row/header width mismatch", async () => {
  const { content, plan } = await validFixture();
  const invalid = structuredClone(content);
  const slide = invalid.slides.find((item) => item.layoutId === "tableInsight");
  slide.slotContent.mainExhibit.rows[0].pop();
  assert.throws(() => validateCertifiedRenderInput(plan, invalid), /match header count/);
});

test("processValueChain blocks a missing stage", async () => {
  const { content, plan } = await validFixture();
  const invalid = structuredClone(content);
  const slide = invalid.slides.find((item) => item.layoutId === "processValueChain");
  slide.slotContent.stages.pop();
  assert.throws(() => validateCertifiedRenderInput(plan, invalid), /stages must contain/);
});

test("executiveSummary blocks pillar overflow", async () => {
  const { content, plan } = await validFixture();
  const invalid = structuredClone(content);
  const slide = invalid.slides.find((item) => item.layoutId === "executiveSummary");
  slide.slotContent.pillars[0].items = ["[占位] 1", "[占位] 2", "[占位] 3", "[占位] 4"];
  assert.throws(() => validateCertifiedRenderInput(plan, invalid), /pillars\[0\]\.items must contain/);
});
