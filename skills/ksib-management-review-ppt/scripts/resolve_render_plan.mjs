import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REFERENCES = path.resolve(HERE, "../references");
const DEFAULT_REGISTRY = path.join(REFERENCES, "certified-layout-registry.json");
const DEFAULT_COMPONENTS = path.join(REFERENCES, "component-registry.json");
const DEFAULT_TYPOGRAPHY = path.join(REFERENCES, "typography-roles.json");
const DEFAULT_MASTER = path.join(REFERENCES, "powerpoint-master-contract.json");
const DEFAULT_TOKENS = path.join(REFERENCES, "design-tokens.json");
const INPUT_SCHEMA = "ksib-render-plan-input/1.0";
const OUTPUT_SCHEMA = "ksib-render-plan/1.0";
const EMU_PER_INCH = 914400;

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) throw new Error(`Unexpected argument: ${token}`);
    const key = token.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) args[key] = true;
    else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

function fail(message) {
  throw new Error(message);
}

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function positiveInteger(value, label) {
  if (!Number.isInteger(value) || value < 1) fail(`${label} must be a positive integer`);
  return value;
}

function stableObjectName(value, label) {
  const name = text(value);
  if (!/^[A-Za-z][A-Za-z0-9._-]{2,79}$/.test(name)) {
    fail(`${label} must be a stable ASCII object name (3-80 characters)`);
  }
  return name;
}

function geometryWithEmu(geometry) {
  const result = {};
  for (const key of ["x", "y", "w", "h"]) {
    const value = geometry?.[key];
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0) fail(`Invalid geometry.${key}`);
    result[key] = value;
    result[`${key}Emu`] = Math.round(value * EMU_PER_INCH);
  }
  return result;
}

function executionMode(value) {
  const mode = text(value);
  if (!["story-change", "locked-content", "format-only"].includes(mode)) {
    fail(`Unsupported executionMode: ${mode || "(missing)"}`);
  }
  return mode;
}

function resolveSlide(slide, index, registry, components, typography, master, names) {
  const slideNumber = positiveInteger(slide?.slide ?? index + 1, `slides[${index}].slide`);
  const storylineId = text(slide?.storylineId);
  if (!storylineId) fail(`slides[${index}].storylineId is required`);
  const layoutId = text(slide?.layoutId);
  const layout = registry.layouts?.[layoutId];
  if (!layout) fail(`slides[${index}] references uncertified layoutId: ${layoutId || "(missing)"}`);
  const variantId = text(slide?.variantId);
  const variant = layout.variants?.[variantId];
  if (!variant) fail(`slides[${index}] references unknown variantId ${variantId || "(missing)"} for ${layoutId}`);
  if (text(slide?.headerProfile) !== variant.headerProfile) {
    fail(`slides[${index}].headerProfile must equal ${variant.headerProfile}`);
  }
  if (slide?.customLayoutAllowed === true || layout.customLayoutAllowed === true) {
    fail(`Certified layout ${layoutId}/${variantId} cannot enable custom layout geometry`);
  }
  const bindings = slide?.slotBindings;
  if (!bindings || typeof bindings !== "object" || Array.isArray(bindings)) fail(`slides[${index}].slotBindings is required`);
  const expectedObjects = [];
  const requiredSlots = layout.requiredSlots || Object.keys(variant.slots || {});
  for (const slotId of requiredSlots) {
    const slot = variant.slots?.[slotId];
    if (!slot) fail(`${layoutId}/${variantId} is missing required slot ${slotId}`);
    const binding = bindings[slotId];
    if (!binding || typeof binding !== "object" || Array.isArray(binding)) fail(`slides[${index}].slotBindings.${slotId} is required`);
    const componentId = text(binding.componentId);
    if (!slot.allowedComponents?.includes(componentId)) {
      fail(`slides[${index}].slotBindings.${slotId} component ${componentId || "(missing)"} is not allowed`);
    }
    const component = components.components?.[componentId];
    if (!component) fail(`Unknown componentId: ${componentId}`);
    const objectName = stableObjectName(binding.objectName, `slides[${index}].slotBindings.${slotId}.objectName`);
    if (names.has(objectName)) fail(`Object name must be unique across the render plan: ${objectName}`);
    names.add(objectName);
    const itemCount = binding.itemCount == null ? null : positiveInteger(binding.itemCount, `${slotId}.itemCount`);
    const minimum = slot.minItems ?? component.minItems ?? null;
    const maximum = slot.maxItems ?? component.maxItems ?? null;
    if (minimum != null && (itemCount == null || itemCount < minimum)) fail(`${slotId}.itemCount must be at least ${minimum}`);
    if (maximum != null && (itemCount == null || itemCount > maximum)) fail(`${slotId}.itemCount must be at most ${maximum}`);
    const typographyRole = slot.typographyRole ?? component.typographyRole ?? null;
    if (typographyRole && !typography.roles?.[typographyRole]) fail(`Unknown typography role: ${typographyRole}`);
    expectedObjects.push({
      slotId,
      regionId: slot.region,
      componentId,
      objectName,
      allowedObjectTypes: component.objectTypes,
      nativeEditable: component.nativeEditable === true,
      typographyInspection: component.typographyInspection ?? (typographyRole ? "slot-role" : "none"),
      geometry: geometryWithEmu(slot.geometry),
      geometryToleranceEmu: slot.geometryToleranceEmu ?? variant.geometryToleranceEmu ?? 0,
      typographyRole,
      expectedFontSizePt: typographyRole ? typography.roles[typographyRole].fontSizePt : null,
      itemCount,
    });
  }
  const extraSlots = Object.keys(bindings).filter((slotId) => !variant.slots?.[slotId]);
  if (extraSlots.length) fail(`slides[${index}] contains undeclared slots: ${extraSlots.join(", ")}`);
  return {
    slide: slideNumber,
    storylineId,
    layoutId,
    variantId,
    layoutRegistryVersion: registry.registryVersion,
    masterProfile: variant.headerProfile,
    masterTemplateVersion: master.templateVersion,
    headerProfile: variant.headerProfile,
    customLayoutAllowed: false,
    bodyRegion: geometryWithEmu(variant.bodyRegion),
    regions: Object.fromEntries(Object.entries(variant.regions || {}).map(([key, value]) => [key, geometryWithEmu(value)])),
    expectedObjects,
  };
}

export function resolveRenderPlan(input, sources) {
  if (input?.schemaVersion !== INPUT_SCHEMA) fail(`schemaVersion must be ${INPUT_SCHEMA}`);
  if (!Array.isArray(input.slides) || !input.slides.length) fail("slides[] must be non-empty");
  if (sources.registry.schemaVersion !== "ksib-certified-layout-registry/1.0") fail("Unsupported certified layout registry");
  if (sources.components.schemaVersion !== "ksib-component-registry/1.0") fail("Unsupported component registry");
  if (sources.typography.schemaVersion !== "ksib-typography-roles/1.0") fail("Unsupported typography registry");
  if (sources.master.schemaVersion !== "ksib-powerpoint-master/1.0") fail("Unsupported PowerPoint master contract");
  if (sources.tokens.schemaVersion !== "ksib-design-tokens/1.3") fail("Unsupported design tokens");
  const mode = executionMode(input.executionMode);
  const names = new Set();
  const slides = input.slides.map((slide, index) => resolveSlide(slide, index, sources.registry, sources.components, sources.typography, sources.master, names));
  const slideNumbers = slides.map((slide) => slide.slide);
  if (new Set(slideNumbers).size !== slideNumbers.length) fail("slides[].slide must be unique");
  return {
    schemaVersion: OUTPUT_SCHEMA,
    generatedAt: new Date().toISOString(),
    executionMode: mode,
    sourceHashes: sources.hashes,
    registryVersion: sources.registry.registryVersion,
    masterTemplateVersion: sources.master.templateVersion,
    designTokensVersion: sources.tokens.schemaVersion,
    overflowPolicy: sources.registry.overflowPolicies[mode],
    rules: {
      llmMayGenerateGeometry: false,
      rawFontSizeAllowed: false,
      freeformBodyObjectsAllowed: false,
      overflowMustFollowPolicy: true,
    },
    slides,
  };
}

async function loadSources(args) {
  const paths = {
    registry: path.resolve(args.registry || DEFAULT_REGISTRY),
    components: path.resolve(args.components || DEFAULT_COMPONENTS),
    typography: path.resolve(args.typography || DEFAULT_TYPOGRAPHY),
    master: path.resolve(args.master || DEFAULT_MASTER),
    tokens: path.resolve(args.tokens || DEFAULT_TOKENS),
  };
  const payloads = Object.fromEntries(await Promise.all(Object.entries(paths).map(async ([key, target]) => [key, await fs.readFile(target)])));
  return {
    registry: JSON.parse(payloads.registry),
    components: JSON.parse(payloads.components),
    typography: JSON.parse(payloads.typography),
    master: JSON.parse(payloads.master),
    tokens: JSON.parse(payloads.tokens),
    hashes: {
      registrySha256: sha256(payloads.registry),
      componentsSha256: sha256(payloads.components),
      typographySha256: sha256(payloads.typography),
      masterSha256: sha256(payloads.master),
      designTokensSha256: sha256(payloads.tokens),
    },
  };
}

async function selfTest() {
  const sources = await loadSources({});
  const input = {
    schemaVersion: INPUT_SCHEMA,
    executionMode: "story-change",
    slides: [{
      slide: 1,
      storylineId: "S01",
      layoutId: "evidenceInsight",
      variantId: "right-panel-standard",
      headerProfile: "content-title-only",
      slotBindings: {
        mainExhibit: { componentId: "native-chart", objectName: "S01-main-exhibit" },
        insightPanel: { componentId: "insight-panel", objectName: "S01-insight-panel" },
        insightTitle: { componentId: "insight-title", objectName: "S01-insight-title" },
        insightLead: { componentId: "insight-lead", objectName: "S01-insight-lead" },
        insightItems: { componentId: "insight-list", objectName: "S01-insight-items", itemCount: 3 },
      },
    }],
  };
  const plan = resolveRenderPlan(input, sources);
  if (plan.slides[0].expectedObjects.length !== 5) fail("self-test expected five objects");
  if (plan.slides[0].expectedObjects[0].geometry.xEmu !== Math.round(0.8 * EMU_PER_INCH)) fail("self-test geometry mismatch");
  if (plan.slides[0].expectedObjects[0].typographyRole !== null) fail("self-test aggregate chart must use component-specific typography inspection");
  if (plan.overflowPolicy.at(-1) !== "block") fail("self-test overflow policy mismatch");
  if (plan.masterTemplateVersion !== sources.master.templateVersion) fail("self-test master version mismatch");
  if (plan.designTokensVersion !== sources.tokens.schemaVersion) fail("self-test design tokens mismatch");
  const coverageSlides = [];
  let coverageIndex = 1;
  for (const [layoutId, layout] of Object.entries(sources.registry.layouts)) {
    for (const [variantId, variant] of Object.entries(layout.variants)) {
      const storylineId = `C${String(coverageIndex).padStart(2, "0")}`;
      const slotBindings = Object.fromEntries(Object.entries(variant.slots).map(([slotId, slot]) => {
        const componentId = slot.allowedComponents[0];
        const component = sources.components.components[componentId] || {};
        const itemCount = slot.minItems ?? component.minItems;
        return [slotId, {
          componentId,
          objectName: `${storylineId}-${slotId}`,
          ...(Number.isInteger(itemCount) ? { itemCount } : {}),
        }];
      }));
      coverageSlides.push({
        slide: coverageIndex,
        storylineId,
        layoutId,
        variantId,
        headerProfile: variant.headerProfile,
        slotBindings,
      });
      coverageIndex += 1;
    }
  }
  const coverage = resolveRenderPlan({ schemaVersion: INPUT_SCHEMA, executionMode: "story-change", slides: coverageSlides }, sources);
  if (coverage.slides.length !== 18) fail(`self-test expected 18 certified variants, got ${coverage.slides.length}`);
  if (new Set(coverage.slides.map((slide) => slide.layoutId)).size !== 12) fail("self-test expected 12 certified layouts");
  let rejected = 0;
  for (const mutate of [
    (value) => { value.slides[0].variantId = "freeform"; },
    (value) => { value.slides[0].slotBindings.insightItems.itemCount = 4; },
    (value) => { value.slides[0].slotBindings.insightLead.objectName = "S01-main-exhibit"; },
    (value) => { value.slides[0].headerProfile = "content-title-subtitle"; },
  ]) {
    const candidate = structuredClone(input);
    mutate(candidate);
    try { resolveRenderPlan(candidate, sources); }
    catch { rejected += 1; }
  }
  if (rejected !== 4) fail(`self-test rejected ${rejected}/4 invalid plans`);
  console.log(JSON.stringify({ passed: true, tests: 12, layouts: 12, variants: 18, schemaVersion: OUTPUT_SCHEMA, masterTemplateVersion: plan.masterTemplateVersion, designTokensVersion: plan.designTokensVersion }, null, 2));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["self-test"]) return selfTest();
  if (!args.input) fail("Missing --input");
  if (!args.output) fail("Missing --output");
  const sources = await loadSources(args);
  const inputPayload = await fs.readFile(path.resolve(args.input), "utf8");
  const plan = resolveRenderPlan(JSON.parse(inputPayload), sources);
  const outputPath = path.resolve(args.output);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(outputPath, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ passed: true, output: outputPath, slideCount: plan.slides.length }, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
