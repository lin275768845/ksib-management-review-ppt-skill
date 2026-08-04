#!/usr/bin/env node
import crypto from "node:crypto";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const validatorPath = fileURLToPath(import.meta.url);
const extractorPath = path.join(here, "extract_pptx_theme_colors.py");
const defaultContractPath = path.join(here, "..", "references", "theme-color-contract.json");
const execFileAsync = promisify(execFile);

function issue(rule, message, slide = null, elementId = null, bindingRef = null) {
  return {
    rule,
    message,
    ...(slide === null ? {} : { slide }),
    ...(elementId ? { elementId } : {}),
    ...(bindingRef ? { bindingRef } : {}),
  };
}

function tokenGroup(contract, token) {
  return Object.entries(contract.tokenGroups).find(([, tokens]) => tokens.includes(token))?.[0] ?? null;
}

function normalizedHex(value) {
  return typeof value === "string" && /^#[0-9A-Fa-f]{6}$/.test(value) ? value.toUpperCase() : null;
}

function contrastRatio(foreground, background) {
  const luminance = (hex) => {
    const channels = [1, 3, 5].map((index) => Number.parseInt(hex.slice(index, index + 2), 16) / 255).map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  const values = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

function exactSlideCoverage(slides, count) {
  const expected = Number.isInteger(count) ? Array.from({ length: count }, (_, index) => index + 1) : [];
  const actual = slides.map((slide) => slide?.slide).filter(Number.isInteger).sort((a, b) => a - b);
  return expected.length > 0 && JSON.stringify(actual) === JSON.stringify(expected);
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

function semanticSha256(value) {
  return crypto.createHash("sha256").update(canonicalJson(value)).digest("hex");
}

function inventoryBindings(inventory) {
  const bindings = [];
  for (const slide of Array.isArray(inventory?.slides) ? inventory.slides : []) {
    for (const object of Array.isArray(slide?.objects) ? slide.objects : []) {
      for (const color of Array.isArray(object?.colors) ? object.colors : []) {
        bindings.push({ slide: slide.slide, object, color });
      }
    }
  }
  return bindings;
}

export function validateThemeUsage(contract, usage, inventory, metadata = {}) {
  const errors = [];
  if (usage?.schemaVersion !== contract.usageSchemaVersion) errors.push(issue("usage_schema_version", `usage schema必须为${contract.usageSchemaVersion}`));
  if (usage?.themeContractVersion !== contract.schemaVersion) errors.push(issue("theme_contract_version", `theme contract必须为${contract.schemaVersion}`));
  if (inventory?.schemaVersion !== contract.inventorySchemaVersion) errors.push(issue("inventory_schema_version", `inventory schema必须为${contract.inventorySchemaVersion}`));
  if (!Number.isInteger(usage?.slideCount) || usage.slideCount < 1) errors.push(issue("slide_count", "slideCount必须是正整数"));
  if (!Array.isArray(usage?.slides)) errors.push(issue("slides", "slides必须是数组"));
  if (!Array.isArray(inventory?.slides)) errors.push(issue("inventory_slides", "inventory.slides必须是数组"));
  if (inventory?.slideCount !== usage?.slideCount) errors.push(issue("inventory_slide_count", "Theme Usage与最终PPTX页数不一致"));
  if (inventory?.pptx?.sha256 !== usage?.pptxArtifactSha256) errors.push(issue("pptx_hash_mismatch", "Theme Usage未绑定当前最终PPTX的SHA256"));
  if (metadata.expectedExtractorSha256 && inventory?.extractorSha256 !== metadata.expectedExtractorSha256) errors.push(issue("stale_extractor", "颜色清单不是由当前标准提取器生成"));
  if (metadata.reExtractedInventorySemanticSha256 && metadata.inventorySemanticSha256 !== metadata.reExtractedInventorySemanticSha256) errors.push(issue("inventory_reextract_mismatch", "保存的颜色清单与从当前最终PPTX现场重提取的结果不一致"));

  const slides = Array.isArray(usage?.slides) ? usage.slides : [];
  const inventorySlides = Array.isArray(inventory?.slides) ? inventory.slides : [];
  if (Number.isInteger(usage?.slideCount) && !exactSlideCoverage(slides, usage.slideCount)) errors.push(issue("slide_coverage", "slides[]必须逐页且仅一次覆盖1..slideCount"));
  if (Number.isInteger(inventory?.slideCount) && !exactSlideCoverage(inventorySlides, inventory.slideCount)) errors.push(issue("inventory_slide_coverage", "最终PPTX颜色清单必须逐页且仅一次覆盖1..slideCount"));

  const knownTokens = new Set(Object.keys(contract.palette));
  const patterns = new Set(contract.chartPatterns);
  const declaredBindings = new Map();
  const declaredBindingCounts = new Map();
  const elementBySlide = new Map();
  for (const slide of slides) {
    const number = slide?.slide ?? null;
    if (!patterns.has(slide?.pattern)) errors.push(issue("chart_pattern", "页面必须声明受支持的chart pattern", number));
    if (!Array.isArray(slide?.elements)) errors.push(issue("elements", "elements必须是数组", number));
    if (!Array.isArray(slide?.bindings)) errors.push(issue("bindings", "bindings必须逐项绑定最终PPTX颜色清单", number));
    const elements = Array.isArray(slide?.elements) ? slide.elements : [];
    const ids = new Set();
    const elementsMap = new Map();
    const dataGroups = new Set();
    for (const element of elements) {
      const id = typeof element?.id === "string" ? element.id.trim() : "";
      if (!id || ids.has(id)) errors.push(issue("element_id", "有色元素必须有页内唯一稳定ID", number, id || null));
      ids.add(id);
      if (id) elementsMap.set(id, element);
      if (element?.rawHex) errors.push(issue("raw_hex", "元素不得直接使用rawHex；请改用合同Token或登记例外", number, id));
      const token = element?.token;
      if (!knownTokens.has(token)) {
        errors.push(issue("unknown_token", `未知颜色Token：${String(token)}`, number, id));
        continue;
      }
      const purposes = contract.allowedPurposes[token] ?? [];
      if (!purposes.includes(element?.purpose)) errors.push(issue("purpose", `${token}不能用于${String(element?.purpose)}`, number, id));
      if (element?.purpose === "decoration") errors.push(issue("decoration", "有彩色Token不得用于纯装饰", number, id));
      const group = tokenGroup(contract, token);
      if (element?.role === "data") {
        if (group && group !== "neutral") dataGroups.add(group);
        if (["neutral.textStrong", "neutral.textMuted", "neutral.chartLabel"].includes(token)) errors.push(issue("dark_neutral_data_fill", "文字灰Token不得用作数据填充", number, id));
      }
      if (element?.role === "text") {
        if (!knownTokens.has(element?.backgroundToken)) errors.push(issue("text_background", "文字元素必须登记有效backgroundToken", number, id));
        else {
          const minimum = element?.largeText === true ? contract.rules.minimumLargeTextContrast : contract.rules.minimumNormalTextContrast;
          if (contrastRatio(contract.palette[token], contract.palette[element.backgroundToken]) < minimum) errors.push(issue("text_contrast", `文字对比度低于${minimum}:1`, number, id));
        }
      }
    }
    elementBySlide.set(number, elementsMap);
    for (const binding of Array.isArray(slide?.bindings) ? slide.bindings : []) {
      const bindingRef = typeof binding?.bindingRef === "string" ? binding.bindingRef.trim() : "";
      if (!bindingRef) {
        errors.push(issue("binding_ref", "颜色绑定必须提供bindingRef", number, binding?.elementId));
        continue;
      }
      declaredBindingCounts.set(bindingRef, (declaredBindingCounts.get(bindingRef) ?? 0) + 1);
      if (!declaredBindings.has(bindingRef)) declaredBindings.set(bindingRef, { ...binding, slide: number });
      const element = elementsMap.get(binding?.elementId);
      if (!element) errors.push(issue("binding_element", "颜色绑定必须引用本页已登记元素", number, binding?.elementId, bindingRef));
      if (binding?.token && element?.token !== binding.token) errors.push(issue("binding_token_semantics", "binding token必须与元素语义Token一致", number, binding?.elementId, bindingRef));
      if (!binding?.token && !binding?.exceptionRef) errors.push(issue("binding_assignment", "颜色绑定必须声明token或approved exception", number, binding?.elementId, bindingRef));
    }
    if (dataGroups.size > contract.rules.maxChromaticDataGroupsPerSlide) errors.push(issue("too_many_chromatic_groups", "同页有彩色数据语义组超过合同上限", number));
    if (slide?.pattern !== "no-data") {
      if (!slide?.dominantEvidenceObject || !ids.has(slide.dominantEvidenceObject)) errors.push(issue("dominant_evidence_object", "数据页面必须登记存在于elements中的主证据对象", number));
      if (!knownTokens.has(slide?.dominantEvidenceToken)) errors.push(issue("dominant_evidence_token", "数据页面必须登记有效的主证据Token", number));
      if (tokenGroup(contract, slide?.dominantEvidenceToken) === "neutral") errors.push(issue("neutral_dominant", "中性色不能承担页面主证据", number));
    }
    if (slide?.pattern === "two-way-comparison") {
      const comparisonTokens = new Set(elements.filter((item) => item?.role === "data").map((item) => item.token));
      if (!comparisonTokens.has("primary.base") || (!comparisonTokens.has("contrast.base") && !comparisonTokens.has("neutral.series"))) errors.push(issue("two_way_palette", "两方对比必须使用主色＋对比辅色，或主色＋浅灰基线", number));
    }
    if (slide?.pattern === "sequential") {
      const invalid = elements.some((item) => item?.role === "data" && tokenGroup(contract, item.token) !== "primary");
      if (invalid) errors.push(issue("sequential_palette", "有序图表的数据色必须来自同一主色阶", number));
    }
  }

  const exceptions = Array.isArray(usage?.exceptions) ? usage.exceptions : [];
  const exceptionById = new Map();
  for (const exception of exceptions) {
    if (typeof exception?.id === "string" && exception.id.trim()) exceptionById.set(exception.id, exception);
    if (!/^#[0-9A-Fa-f]{6}$/.test(exception?.rawColor ?? "") || !String(exception?.reason ?? "").trim() || !String(exception?.approvalRef ?? "").trim() || exception?.status !== "user-approved") errors.push(issue("invalid_exception", "颜色例外必须含ID、Hex、业务原因、approvalRef和user-approved状态", exception?.slide ?? null, exception?.elementId ?? null));
    if (/装饰|好看|丰富/i.test(String(exception?.reason ?? ""))) errors.push(issue("decorative_exception", "装饰性理由不能成为颜色合同例外", exception?.slide ?? null, exception?.elementId ?? null));
  }

  const actualBindings = inventoryBindings(inventory);
  const actualRefs = new Set();
  for (const { slide, object, color } of actualBindings) {
    const ref = color?.bindingRef;
    if (!ref || actualRefs.has(ref)) errors.push(issue("inventory_binding_ref", "最终PPTX颜色bindingRef缺失或重复", slide, null, ref));
    if (ref) actualRefs.add(ref);
    if (!color?.visible) continue;
    if (!object?.stable) errors.push(issue("unstable_colored_object", "有色原生对象必须使用页内唯一对象名，不能依赖易变ID", slide, null, ref));
    if (color?.resolutionStatus !== "resolved" || !normalizedHex(color?.resolvedHex)) errors.push(issue("unresolved_actual_color", "最终PPTX存在无法解析的可见颜色", slide, null, ref));
    const declaration = declaredBindings.get(ref);
    if (!declaration) {
      errors.push(issue("undeclared_actual_color", "最终PPTX可见颜色未在Theme Usage中登记", slide, null, ref));
      continue;
    }
    if (declaration.slide !== slide) errors.push(issue("binding_slide_mismatch", "颜色绑定登记在错误页码", slide, declaration.elementId, ref));
    if ((declaredBindingCounts.get(ref) ?? 0) !== 1) errors.push(issue("duplicate_binding", "同一最终颜色必须且只能登记一次", slide, declaration.elementId, ref));
    if (declaration.token) {
      if (!knownTokens.has(declaration.token)) errors.push(issue("unknown_binding_token", `未知binding token：${String(declaration.token)}`, slide, declaration.elementId, ref));
      else if (normalizedHex(contract.palette[declaration.token]) !== normalizedHex(color.resolvedHex)) errors.push(issue("actual_color_mismatch", `${declaration.token}=${contract.palette[declaration.token]}，但最终PPTX实际为${color.resolvedHex}`, slide, declaration.elementId, ref));
    } else if (declaration.exceptionRef) {
      const exception = exceptionById.get(declaration.exceptionRef);
      if (!exception) errors.push(issue("unknown_exception", "binding引用的颜色例外不存在", slide, declaration.elementId, ref));
      else if (normalizedHex(exception.rawColor) !== normalizedHex(color.resolvedHex)) errors.push(issue("exception_color_mismatch", "颜色例外Hex与最终PPTX实际颜色不一致", slide, declaration.elementId, ref));
    }
  }
  for (const [ref, declaration] of declaredBindings) {
    if (!actualRefs.has(ref)) errors.push(issue("phantom_binding", "Theme Usage声明了最终PPTX中不存在的颜色绑定", declaration.slide, declaration.elementId, ref));
  }

  return {
    schemaVersion: "ksib-theme-color-gate/1.1",
    passed: errors.length === 0,
    errorCount: errors.length,
    checkedSlides: slides.length,
    checkedVisibleBindings: actualBindings.filter((item) => item.color?.visible).length,
    artifactSha256: inventory?.pptx?.sha256 ?? null,
    inventorySha256: metadata.inventorySha256 ?? null,
    inventorySemanticSha256: metadata.inventorySemanticSha256 ?? null,
    reExtractedInventorySemanticSha256: metadata.reExtractedInventorySemanticSha256 ?? null,
    usageSha256: metadata.usageSha256 ?? null,
    validatorSha256: metadata.validatorSha256 ?? null,
    extractorSha256: inventory?.extractorSha256 ?? null,
    errors,
  };
}

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) result[argv[index]?.replace(/^--/, "")] = argv[index + 1];
  return result;
}

async function sha256(pathname) {
  return crypto.createHash("sha256").update(await readFile(pathname)).digest("hex");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = parseArgs(process.argv.slice(2));
  if (!args.usage || !args.inventory || !args.pptx) throw new Error("用法：validate_theme_usage.mjs --pptx <final.pptx> --usage <json> --inventory <json> [--python <python>] [--contract <json>] [--report <json>]");
  const contract = JSON.parse(await readFile(args.contract || defaultContractPath, "utf8"));
  const usage = JSON.parse(await readFile(args.usage, "utf8"));
  const inventory = JSON.parse(await readFile(args.inventory, "utf8"));
  const tempDirectory = await mkdtemp(path.join(os.tmpdir(), "ksib-pptx-color-"));
  let report;
  try {
    const reExtractedPath = path.join(tempDirectory, "inventory.json");
    await execFileAsync(args.python || process.env.PYTHON || "python3", [extractorPath, "--pptx", args.pptx, "--output", reExtractedPath], { maxBuffer: 10 * 1024 * 1024 });
    const reExtracted = JSON.parse(await readFile(reExtractedPath, "utf8"));
    report = validateThemeUsage(contract, usage, inventory, {
      usageSha256: await sha256(args.usage),
      inventorySha256: await sha256(args.inventory),
      inventorySemanticSha256: semanticSha256(inventory),
      reExtractedInventorySemanticSha256: semanticSha256(reExtracted),
      validatorSha256: await sha256(validatorPath),
      expectedExtractorSha256: await sha256(extractorPath),
    });
  } finally {
    await rm(tempDirectory, { recursive: true, force: true });
  }
  if (args.report) await writeFile(args.report, `${JSON.stringify(report, null, 2)}\n`);
  else process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.passed) process.exitCode = 1;
}
