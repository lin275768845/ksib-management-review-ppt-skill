#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

const SCHEMA_VERSION = "ksib-release-manifest/3.2";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const MATRIX_PATH = path.resolve(HERE, "../references/layout-matrix.json");
const DESIGN_TOKENS_PATH = path.resolve(HERE, "../references/design-tokens.json");
const CODEX_HOME = process.env.CODEX_HOME
  ? path.resolve(process.env.CODEX_HOME)
  : path.join(os.homedir(), ".codex");
const CANONICAL_VALIDATOR_PATHS = {
  storyline: path.resolve(HERE, "validate_storyline_gate.mjs"),
  "storyline-upstream": path.resolve(
    CODEX_HOME,
    "skills/linzhe-mbb-storyline/scripts/validate_storyline.mjs",
  ),
  evidence: path.resolve(HERE, "validate_evidence.mjs"),
  content: path.resolve(HERE, "validate_content.mjs"),
  handoff: path.resolve(HERE, "validate_storyline_handoff.mjs"),
  fingerprint: path.resolve(HERE, "pptx_semantic_fingerprint.py"),
  ooxml: path.resolve(HERE, "ooxml_qa.py"),
  visual: path.resolve(HERE, "build_visual_review_gate.py"),
  "theme-color": path.resolve(HERE, "validate_theme_usage.mjs"),
  "powerpoint-render": path.resolve(HERE, "validate_powerpoint_render.py"),
};
const REQUIRED_POWERPOINT_CHECKS = [
  "noRepairPrompt",
  "textEditUndo",
  "textColorChangeUndo",
  "boldToggleUndo",
  "fontFamilyChangeUndo",
  "shapeFillChangeUndo",
  "groupUngroup",
  "fontDisplay",
  "finalSlideAndPageNumber",
];
const CONDITIONAL_POWERPOINT_CHECKS = {
  tables: ["tableCellFormatUndo"],
  charts: ["chartTextFormatUndo", "chartDataEditUndo"],
  smartArt: ["smartArtTextFormatUndo"],
};
const DELIVERY_MODES = new Set(["format-only", "locked-content", "story-change"]);
const RENDERER_MODES = new Set(["canonical", "fallback"]);
const MANDATORY_GATES_BY_MODE = {
  "format-only": ["fingerprint", "ooxml", "visual", "theme-color", "powerpoint-render"],
  "locked-content": ["storyline", "evidence", "content", "handoff", "ooxml", "visual", "theme-color", "powerpoint-render"],
  "story-change": ["storyline", "evidence", "content", "handoff", "ooxml", "visual", "theme-color", "powerpoint-render"],
};
const REQUIRED_VISUAL_CHECKS = [
  "fullSizeReview",
  "noOverlap",
  "noClipping",
  "noUnexpectedWrap",
  "footerAndPageNumber",
  "chartDataAndSources",
];

function parseArgs(argv) {
  const args = { gate: [], validator: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) throw new Error(`Unexpected argument: ${token}`);
    const key = token.slice(2);
    if (key === "self-test") {
      args[key] = true;
      continue;
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`Missing value for --${key}`);
    if (key === "gate") args.gate.push(value);
    else if (key === "validator") args.validator.push(value);
    else args[key] = value;
    index += 1;
  }
  return args;
}

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256Buffer(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

async function sha256File(filePath) {
  return sha256Buffer(await fs.readFile(filePath));
}

async function realPathOrResolved(filePath) {
  try {
    return await fs.realpath(filePath);
  } catch {
    return path.resolve(filePath);
  }
}

async function validateCanonicalValidatorArguments(validatorArguments) {
  for (const argument of validatorArguments) {
    const canonical = CANONICAL_VALIDATOR_PATHS[argument.name];
    if (!canonical) throw new Error(`No canonical validator registered for: ${argument.name}`);
    const [actualRealPath, canonicalRealPath] = await Promise.all([
      realPathOrResolved(argument.filePath),
      realPathOrResolved(canonical),
    ]);
    if (actualRealPath !== canonicalRealPath) {
      throw new Error(
        `Noncanonical validator path for ${argument.name}: ${argument.filePath}; expected ${canonical}`,
      );
    }
  }
}

function findEndOfCentralDirectory(buffer) {
  const minimumOffset = Math.max(0, buffer.length - 65_557);
  for (let offset = buffer.length - 22; offset >= minimumOffset; offset -= 1) {
    if (buffer.readUInt32LE(offset) === 0x06054b50) return offset;
  }
  return -1;
}

function readZipEntry(buffer, entry) {
  const offset = entry.localHeaderOffset;
  if (offset < 0 || offset + 30 > buffer.length || buffer.readUInt32LE(offset) !== 0x04034b50) {
    throw new Error(`PPTX ZIP local header invalid: ${entry.name}`);
  }
  const nameLength = buffer.readUInt16LE(offset + 26);
  const extraLength = buffer.readUInt16LE(offset + 28);
  const start = offset + 30 + nameLength + extraLength;
  const end = start + entry.compressedSize;
  if (end > buffer.length) throw new Error(`PPTX ZIP entry truncated: ${entry.name}`);
  const payload = buffer.subarray(start, end);
  if (entry.compressionMethod === 0) return payload;
  if (entry.compressionMethod === 8) return zlib.inflateRawSync(payload);
  throw new Error(
    `PPTX ZIP uses unsupported compression method ${entry.compressionMethod}: ${entry.name}`,
  );
}

function parseXmlAttributes(tag) {
  const attributes = {};
  const pattern = /([A-Za-z_][A-Za-z0-9_.:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
  for (const match of tag.matchAll(pattern)) {
    attributes[match[1]] = match[2] ?? match[3] ?? "";
  }
  return attributes;
}

function relationshipRecords(xml) {
  return [...xml.matchAll(/<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?Relationship\b[^>]*\/?>/g)]
    .map((match) => parseXmlAttributes(match[0]));
}

function contentTypeOverrides(xml) {
  return new Map(
    [...xml.matchAll(/<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?Override\b[^>]*\/?>/g)]
      .map((match) => parseXmlAttributes(match[0]))
      .filter((attributes) => attributes.PartName && attributes.ContentType)
      .map((attributes) => [
        attributes.PartName.replace(/^\/+/, ""),
        attributes.ContentType,
      ]),
  );
}

function resolvePresentationTarget(target) {
  return path.posix.normalize(
    path.posix.join(path.posix.dirname("ppt/presentation.xml"), target),
  ).replace(/^\/+/, "");
}

async function validatePptxPackage(filePath) {
  if (path.extname(filePath).toLowerCase() !== ".pptx") {
    throw new Error(`Final artifact must have .pptx extension: ${filePath}`);
  }
  const buffer = await fs.readFile(filePath);
  if (buffer.length < 22) throw new Error("Final PPTX is not a valid ZIP package");
  const eocdOffset = findEndOfCentralDirectory(buffer);
  if (eocdOffset < 0) throw new Error("Final PPTX ZIP central directory is missing");
  const entryCount = buffer.readUInt16LE(eocdOffset + 10);
  const centralDirectorySize = buffer.readUInt32LE(eocdOffset + 12);
  const centralDirectoryOffset = buffer.readUInt32LE(eocdOffset + 16);
  if (
    entryCount < 3
    || centralDirectoryOffset + centralDirectorySize > eocdOffset
  ) {
    throw new Error("Final PPTX ZIP central directory is malformed");
  }
  const entries = new Map();
  let cursor = centralDirectoryOffset;
  for (let index = 0; index < entryCount; index += 1) {
    if (cursor + 46 > buffer.length || buffer.readUInt32LE(cursor) !== 0x02014b50) {
      throw new Error("Final PPTX ZIP central entry is malformed");
    }
    const flags = buffer.readUInt16LE(cursor + 8);
    const compressionMethod = buffer.readUInt16LE(cursor + 10);
    const compressedSize = buffer.readUInt32LE(cursor + 20);
    const uncompressedSize = buffer.readUInt32LE(cursor + 24);
    const nameLength = buffer.readUInt16LE(cursor + 28);
    const extraLength = buffer.readUInt16LE(cursor + 30);
    const commentLength = buffer.readUInt16LE(cursor + 32);
    const localHeaderOffset = buffer.readUInt32LE(cursor + 42);
    const end = cursor + 46 + nameLength + extraLength + commentLength;
    if (end > buffer.length) throw new Error("Final PPTX ZIP central entry is truncated");
    const name = buffer.subarray(cursor + 46, cursor + 46 + nameLength).toString("utf8");
    if (flags & 0x0001) throw new Error(`Final PPTX contains encrypted ZIP entry: ${name}`);
    if (entries.has(name)) throw new Error(`Final PPTX contains duplicate ZIP entry: ${name}`);
    entries.set(name, {
      name,
      flags,
      compressionMethod,
      compressedSize,
      uncompressedSize,
      localHeaderOffset,
    });
    cursor = end;
  }
  if (cursor !== centralDirectoryOffset + centralDirectorySize) {
    throw new Error("Final PPTX ZIP central directory size does not match entries");
  }
  const requiredParts = [
    "[Content_Types].xml",
    "_rels/.rels",
    "ppt/presentation.xml",
    "ppt/_rels/presentation.xml.rels",
  ];
  for (const requiredPart of requiredParts) {
    if (!entries.has(requiredPart)) {
      throw new Error(`Final PPTX package part missing: ${requiredPart}`);
    }
  }
  const xmlChecks = [
    ["[Content_Types].xml", /<(?:\w+:)?Types\b/],
    ["_rels/.rels", /<(?:\w+:)?Relationships\b/],
    ["ppt/presentation.xml", /<(?:\w+:)?presentation\b/],
  ];
  for (const [partName, rootPattern] of xmlChecks) {
    const entry = entries.get(partName);
    const xml = readZipEntry(buffer, entry).toString("utf8");
    if (!rootPattern.test(xml)) {
      throw new Error(`Final PPTX package part is not expected OOXML: ${partName}`);
    }
  }
  const contentTypesXml = readZipEntry(
    buffer,
    entries.get("[Content_Types].xml"),
  ).toString("utf8");
  const overrides = contentTypeOverrides(contentTypesXml);
  const presentationContentType = (
    "application/vnd.openxmlformats-officedocument."
    + "presentationml.presentation.main+xml"
  );
  const slideContentType = (
    "application/vnd.openxmlformats-officedocument."
    + "presentationml.slide+xml"
  );
  if (overrides.get("ppt/presentation.xml") !== presentationContentType) {
    throw new Error("Final PPTX presentation content type is missing or invalid");
  }
  const rootRelationships = relationshipRecords(
    readZipEntry(buffer, entries.get("_rels/.rels")).toString("utf8"),
  ).filter((relationship) => (
    relationship.Type?.endsWith("/officeDocument")
    && relationship.TargetMode !== "External"
  ));
  if (
    rootRelationships.length !== 1
    || path.posix.normalize(rootRelationships[0].Target ?? "").replace(/^\/+/, "")
      !== "ppt/presentation.xml"
  ) {
    throw new Error(
      "Final PPTX must contain exactly one root officeDocument relationship to ppt/presentation.xml",
    );
  }
  const presentationXml = readZipEntry(
    buffer,
    entries.get("ppt/presentation.xml"),
  ).toString("utf8");
  const slideRelationshipIds = [
    ...presentationXml.matchAll(
      /<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?sldId\b[^>]*\/?>/g,
    ),
  ].map((match) => parseXmlAttributes(match[0])["r:id"]).filter(Boolean);
  if (!slideRelationshipIds.length) {
    throw new Error("Final PPTX presentation contains no slide references");
  }
  if (new Set(slideRelationshipIds).size !== slideRelationshipIds.length) {
    throw new Error("Final PPTX presentation contains duplicate slide relationship references");
  }
  const presentationRelationships = new Map(
    relationshipRecords(
      readZipEntry(
        buffer,
        entries.get("ppt/_rels/presentation.xml.rels"),
      ).toString("utf8"),
    ).map((relationship) => [relationship.Id, relationship]),
  );
  const referencedSlideParts = [];
  for (const relationshipId of slideRelationshipIds) {
    const relationship = presentationRelationships.get(relationshipId);
    if (
      !relationship
      || !relationship.Type?.endsWith("/slide")
      || relationship.TargetMode === "External"
    ) {
      throw new Error(
        `Final PPTX slide relationship is missing or invalid: ${relationshipId}`,
      );
    }
    referencedSlideParts.push(resolvePresentationTarget(relationship.Target ?? ""));
  }
  const actualSlideParts = [...entries.keys()]
    .filter((name) => /^ppt\/slides\/slide\d+\.xml$/.test(name))
    .sort();
  const uniqueReferencedSlideParts = [...new Set(referencedSlideParts)].sort();
  if (
    actualSlideParts.length !== slideRelationshipIds.length
    || JSON.stringify(uniqueReferencedSlideParts) !== JSON.stringify(actualSlideParts)
  ) {
    throw new Error(
      "Final PPTX slide references do not exactly match slide parts",
    );
  }
  for (const slidePart of actualSlideParts) {
    if (overrides.get(slidePart) !== slideContentType) {
      throw new Error(`Final PPTX slide content type is missing or invalid: ${slidePart}`);
    }
  }
  const tableCount = actualSlideParts.reduce((count, slidePart) => {
    const slideXml = readZipEntry(buffer, entries.get(slidePart)).toString("utf8");
    return count + [...slideXml.matchAll(
      /<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?tbl\b/g,
    )].length;
  }, 0);
  const chartCount = [...entries.keys()].filter(
    (name) => /^ppt\/charts\/chart\d+\.xml$/.test(name),
  ).length;
  const smartArtCount = [...entries.keys()].filter(
    (name) => /^ppt\/diagrams\/data\d+\.xml$/.test(name),
  ).length;
  return {
    valid: true,
    entryCount,
    requiredParts,
    slideCount: actualSlideParts.length,
    nativeObjectInventory: {
      tables: tableCount,
      charts: chartCount,
      smartArt: smartArtCount,
    },
  };
}

async function readJson(filePath, label) {
  try {
    return JSON.parse(await fs.readFile(filePath, "utf8"));
  } catch (error) {
    throw new Error(`Cannot read ${label} JSON (${filePath}): ${error.message}`);
  }
}

function parseNamedPathArgument(value, flagName) {
  const separator = value.indexOf("=");
  if (separator < 1 || separator === value.length - 1) {
    throw new Error(`--${flagName} must use name=path: ${value}`);
  }
  return {
    name: value.slice(0, separator).trim(),
    filePath: path.resolve(value.slice(separator + 1).trim()),
  };
}

function nonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function duplicateValues(values) {
  return values.filter((value, index) => values.indexOf(value) !== index);
}

function sameStringSet(left, right) {
  return left.length === right.length
    && new Set(left).size === left.length
    && new Set(right).size === right.length
    && left.every((value) => right.includes(value));
}

function rendererUsageSlides(payload) {
  if (Array.isArray(payload)) return payload;
  return Array.isArray(payload?.slides) ? payload.slides : null;
}

function compactCheckStatus(check) {
  const checks = check.checks && typeof check.checks === "object" ? check.checks : {};
  return {
    passed: check.passed === true,
    checkedBy: check.checkedBy ?? null,
    checkedAt: check.checkedAt ?? null,
    pptxSha256: check.pptxSha256 ?? null,
    checks,
    notes: check.notes ?? null,
  };
}

function validateGateContract(name, report) {
  const issues = [];
  const requireValue = (condition, detail) => {
    if (!condition) issues.push(detail);
  };
  requireValue(
    Number.isInteger(report.errorCount) && report.errorCount === 0,
    `${name}.errorCount必须严格等于0`,
  );
  requireValue(
    Array.isArray(report.errors) && report.errors.length === 0,
    `${name}.errors[]必须存在且为空`,
  );
  requireValue(Boolean(report.validatorSha256), `${name}.validatorSha256缺失`);
  if (name === "storyline") {
    requireValue(report.schemaVersion === "ksib-storyline-gate/1.0", "storyline schemaVersion无效");
    requireValue(report.productionReady === true, "storyline.productionReady必须为true");
    requireValue(Boolean(report.inputHashes?.storylineSha256), "storyline.inputHashes.storylineSha256缺失");
    requireValue(Boolean(report.upstreamValidatorSha256), "storyline.upstreamValidatorSha256缺失");
  } else if (name === "evidence") {
    requireValue(report.schemaVersion === "ksib-evidence-gate/2.0", "evidence schemaVersion无效");
    requireValue(report.mode === "full", "evidence必须是full模式，不能使用registry-only");
    requireValue(report.coverage && typeof report.coverage === "object", "evidence.coverage缺失");
    requireValue(Boolean(report.inputHashes?.evidenceSha256), "evidence.inputHashes.evidenceSha256缺失");
    requireValue(Boolean(report.inputHashes?.contentSha256), "evidence.inputHashes.contentSha256缺失");
    requireValue(Boolean(report.inputHashes?.matrixSha256), "evidence.inputHashes.matrixSha256缺失");
  } else if (name === "content") {
    requireValue(report.schemaVersion === "ksib-content-gate/2.0", "content schemaVersion无效");
    requireValue(Number.isInteger(report.slideCount) && report.slideCount > 0, "content.slideCount必须为正整数");
    requireValue(Boolean(report.inputHashes?.contentSha256), "content.inputHashes.contentSha256缺失");
    requireValue(Boolean(report.inputHashes?.matrixSha256), "content.inputHashes.matrixSha256缺失");
    requireValue(Array.isArray(report.results), "content.results[]缺失");
    requireValue(
      Array.isArray(report.results)
        && report.results.length === report.slideCount
        && report.results.every((result) => (
          Number.isInteger(result.slide)
          && nonEmptyString(result.storylineId)
          && result.rendererContract?.provider
          && result.rendererContract?.canonicalRenderer
          && result.rendererContract?.editableNative === true
        )),
      "content每页必须解析到可编辑canonical renderer合同",
    );
    requireValue(
      Array.isArray(report.results)
        && sameStringSet(
          report.results.map((result) => String(result.slide)),
          Array.from({ length: report.slideCount }, (_, index) => String(index + 1)),
        ),
      "content.results[].slide必须唯一且完整覆盖1..slideCount",
    );
    requireValue(
      Array.isArray(report.results)
        && duplicateValues(report.results.map((result) => result.storylineId)).length === 0,
      "content.results[].storylineId必须唯一",
    );
  } else if (name === "handoff") {
    requireValue(report.schemaVersion === "ksib-storyline-handoff/2.0", "handoff schemaVersion无效");
    requireValue(Array.isArray(report.semanticHashes) && report.semanticHashes.length > 0, "handoff.semanticHashes[]缺失");
    requireValue(
      Array.isArray(report.semanticHashes)
        && report.semanticHashes.every((item) => (
          nonEmptyString(item.storylineId)
          && item.storylineHash === item.contentHash
        )),
      "handoff逐页Storyline与Content语义哈希必须一致",
    );
    requireValue(
      Array.isArray(report.semanticHashes)
        && duplicateValues(report.semanticHashes.map((item) => item.storylineId)).length === 0,
      "handoff.semanticHashes[].storylineId必须唯一",
    );
    requireValue(report.argumentTree?.passed === true, "handoff.argumentTree必须通过");
    requireValue(Boolean(report.inputHashes?.storylineSha256), "handoff.inputHashes.storylineSha256缺失");
    requireValue(Boolean(report.inputHashes?.contentSha256), "handoff.inputHashes.contentSha256缺失");
    requireValue(Boolean(report.inputHashes?.matrixSha256), "handoff.inputHashes.matrixSha256缺失");
  } else if (name === "fingerprint") {
    requireValue(
      report.schemaVersion === "ksib-pptx-semantic-compare/3.2"
        && report.mode === "format-only"
        && ["allow", "preserve"].includes(report.fontPolicy)
        && ["allow", "preserve"].includes(report.stylePolicy),
      "fingerprint必须来自format-only语义比较脚本",
    );
    requireValue(Boolean(report.baseline?.archiveSha256), "fingerprint.baseline.archiveSha256缺失");
    requireValue(Boolean(report.candidate?.archiveSha256), "fingerprint.candidate.archiveSha256缺失");
  } else if (name === "ooxml") {
    requireValue(report.schemaVersion === "ksib-ooxml-qa/2.0", "ooxml schemaVersion无效");
    requireValue(Array.isArray(report.reports) && report.reports.length > 0, "ooxml.reports[]缺失");
    requireValue(["ksib", "preserve"].includes(report.themePolicy), "ooxml.themePolicy缺失或无效");
    requireValue(["ksib", "preserve"].includes(report.fontPolicy), "ooxml.fontPolicy缺失或无效");
    requireValue(
      report.reports?.length === 1 && Boolean(report.reports[0]?.sha256),
      "ooxml必须只审计一个最终PPTX并记录其sha256",
    );
  } else if (name === "visual") {
    requireValue(report.schemaVersion === "ksib-visual-review/2.0", "visual schemaVersion无效");
    requireValue(Number.isInteger(report.slideCount) && report.slideCount > 0, "visual.slideCount必须为正整数");
    requireValue(report.reviewedSlideCount === report.slideCount, "visual必须逐页全尺寸复核");
    requireValue(Boolean(report.reviewedBy), "visual.reviewedBy缺失");
    requireValue(Boolean(report.reviewedAt), "visual.reviewedAt缺失");
    requireValue(Boolean(report.pptx?.sha256), "visual.pptx.sha256缺失");
    requireValue(
      Array.isArray(report.slides)
        && report.slides.length === report.slideCount
        && report.slides.every((slide) => (
          Number.isInteger(slide.slide)
          && slide.passed === true
          && Boolean(slide.sha256)
          && Boolean(slide.pixelSha256)
          && Number.isInteger(slide.width)
          && Number.isInteger(slide.height)
        )),
      "visual.slides[]必须逐页登记通过状态、PNG文件哈希、规范化像素哈希与尺寸",
    );
    requireValue(
      Array.isArray(report.slides)
        && sameStringSet(
          report.slides.map((slide) => String(slide.slide)),
          Array.from({ length: report.slideCount }, (_, index) => String(index + 1)),
        ),
      "visual.slides[].slide必须唯一且完整覆盖1..slideCount",
    );
    requireValue(
      Array.isArray(report.slides)
        && report.slides.length === report.slideCount
        && report.slides.every((slide) => nonEmptyString(slide.sha256))
        && new Set(report.slides.map((slide) => slide.sha256)).size === report.slideCount,
      "visual.slides[].sha256必须逐页唯一，禁止不同页面复用同一PNG内容",
    );
    requireValue(
      Array.isArray(report.slides)
        && report.slides.length === report.slideCount
        && report.slides.every((slide) => nonEmptyString(slide.pixelSha256))
        && new Set(report.slides.map((slide) => slide.pixelSha256)).size === report.slideCount,
      "visual.slides[].pixelSha256必须逐页唯一，PNG元数据或压缩差异不能绕过同图复用门禁",
    );
    for (const checkName of REQUIRED_VISUAL_CHECKS) {
      requireValue(report.checks?.[checkName] === true, `visual.checks.${checkName}必须为true`);
    }
  } else if (name === "theme-color") {
    requireValue(report.schemaVersion === "ksib-theme-color-gate/1.1", "theme-color schemaVersion无效");
    requireValue(Boolean(report.artifactSha256), "theme-color.artifactSha256缺失");
    requireValue(Boolean(report.inventorySha256), "theme-color.inventorySha256缺失");
    requireValue(Boolean(report.inventorySemanticSha256), "theme-color.inventorySemanticSha256缺失");
    requireValue(Boolean(report.reExtractedInventorySemanticSha256), "theme-color.reExtractedInventorySemanticSha256缺失");
    requireValue(report.inventorySemanticSha256 === report.reExtractedInventorySemanticSha256, "theme-color保存清单与现场重提取结果不一致");
    requireValue(Boolean(report.usageSha256), "theme-color.usageSha256缺失");
    requireValue(Boolean(report.extractorSha256), "theme-color.extractorSha256缺失");
    requireValue(Number.isInteger(report.checkedSlides) && report.checkedSlides > 0, "theme-color.checkedSlides必须为正整数");
    requireValue(Number.isInteger(report.checkedVisibleBindings) && report.checkedVisibleBindings > 0, "theme-color必须逐项核对最终PPTX可见颜色");
  } else if (name === "powerpoint-render") {
    requireValue(
      report.schemaVersion === "ksib-powerpoint-render-gate/1.0",
      "powerpoint-render schemaVersion无效",
    );
    requireValue(Boolean(report.pptx?.sha256), "powerpoint-render.pptx.sha256缺失");
    requireValue(Number.isInteger(report.pptx?.slideCount) && report.pptx.slideCount > 0, "powerpoint-render.pptx.slideCount无效");
    requireValue(
      report.review?.source === "Microsoft PowerPoint"
        && Boolean(report.review?.reviewedBy)
        && Boolean(report.review?.reviewedAt),
      "powerpoint-render必须绑定Microsoft PowerPoint审阅者与时间",
    );
    requireValue(Boolean(report.powerpointScreenshotSetHash), "powerpoint-render.powerpointScreenshotSetHash缺失");
    requireValue(
      report.reviewedSlideCount === report.pptx?.slideCount
        && Array.isArray(report.slides)
        && report.slides.length === report.pptx?.slideCount
        && report.slides.every((slide) => (
          Number.isInteger(slide.slide)
          && slide.passed === true
          && Boolean(slide.sha256)
          && Boolean(slide.pixelSha256)
          && Boolean(slide.reviewedAt)
        )),
      "powerpoint-render必须逐页绑定PowerPoint截图、复核时间与通过状态",
    );
    for (const checkName of [
      "powerpointScreenshots",
      "labelOwnership",
      "numberDisplay",
      "financialChartSemantics",
      "rendererImplementation",
    ]) {
      requireValue(report.checks?.[checkName] === true, `powerpoint-render.checks.${checkName}必须为true`);
    }
    requireValue(Boolean(report.inputHashes?.contentSha256), "powerpoint-render.inputHashes.contentSha256缺失");
    requireValue(Boolean(report.inputHashes?.formatContractSha256), "powerpoint-render.inputHashes.formatContractSha256缺失");
  }
  return issues;
}

function gateArtifactSha256(name, report) {
  if (name === "fingerprint") return report.candidate?.archiveSha256 ?? null;
  if (name === "visual") return report.pptx?.sha256 ?? null;
  if (name === "theme-color") return report.artifactSha256 ?? null;
  if (name === "powerpoint-render") return report.pptx?.sha256 ?? null;
  if (name === "ooxml" && report.reports?.length === 1) {
    return report.reports[0]?.sha256 ?? null;
  }
  return null;
}

async function artifactRecord(filePath) {
  const resolved = path.resolve(filePath);
  const stat = await fs.stat(resolved);
  if (!stat.isFile()) throw new Error(`Artifact is not a file: ${resolved}`);
  return {
    fileName: path.basename(resolved),
    bytes: stat.size,
    sha256: await sha256File(resolved),
  };
}

function addBlocker(blockers, rule, detail) {
  blockers.push({ rule, detail });
}

async function buildManifest(options) {
  const releaseStartedAtMs = Date.now();
  const deliveryMode = options["delivery-mode"] ?? "locked-content";
  if (!DELIVERY_MODES.has(deliveryMode)) {
    throw new Error(`Invalid --delivery-mode: ${deliveryMode}`);
  }
  const required = ["final-pptx", "renderer", "renderer-version", "powerpoint-check"];
  for (const key of required) {
    if (!options[key]) throw new Error(`Missing --${key}`);
  }
  if (deliveryMode === "format-only" && !options["input-pptx"]) {
    throw new Error("format-only模式必须提供--input-pptx");
  }
  if (deliveryMode !== "format-only" && !options["input-pptx"] && !options["input-artifact"]) {
    throw new Error(`${deliveryMode}模式必须提供--input-artifact或--input-pptx`);
  }
  if (deliveryMode !== "format-only" && !options["storyline-lock"]) {
    throw new Error(`${deliveryMode}模式必须提供--storyline-lock`);
  }
  if (deliveryMode !== "format-only" && !options["content-artifact"]) {
    throw new Error(`${deliveryMode}模式必须提供--content-artifact`);
  }
  if (deliveryMode !== "format-only" && !options["evidence-artifact"]) {
    throw new Error(`${deliveryMode}模式必须提供--evidence-artifact`);
  }
  if (!options.gate?.length) throw new Error("At least one --gate name=path is required");
  if (!options.validator?.length) {
    throw new Error("At least one --validator name=path is required");
  }

  const inputPath = options["input-pptx"] ?? options["input-artifact"] ?? null;
  const finalPath = path.resolve(options["final-pptx"]);
  const storylinePath = options["storyline-lock"] ? path.resolve(options["storyline-lock"]) : null;
  const contentArtifactPath = options["content-artifact"]
    ? path.resolve(options["content-artifact"])
    : null;
  const evidenceArtifactPath = options["evidence-artifact"]
    ? path.resolve(options["evidence-artifact"])
    : null;
  const rendererUsagePath = options["renderer-usage"]
    ? path.resolve(options["renderer-usage"])
    : null;
  const powerpointPath = path.resolve(options["powerpoint-check"]);
  const gateArguments = options.gate.map((value) => parseNamedPathArgument(value, "gate"));
  const validatorArguments = options.validator.map(
    (value) => parseNamedPathArgument(value, "validator"),
  );
  const duplicateGateNames = gateArguments
    .map(({ name }) => name)
    .filter((name, index, names) => names.indexOf(name) !== index);
  if (duplicateGateNames.length) {
    throw new Error(`Duplicate gate names: ${[...new Set(duplicateGateNames)].join(", ")}`);
  }
  const duplicateValidatorNames = duplicateValues(validatorArguments.map(({ name }) => name));
  if (duplicateValidatorNames.length) {
    throw new Error(`Duplicate validator names: ${[...new Set(duplicateValidatorNames)].join(", ")}`);
  }
  const gateNames = gateArguments.map(({ name }) => name);
  const allowedValidatorNames = new Set([
    ...gateNames,
    ...(gateNames.includes("storyline") ? ["storyline-upstream"] : []),
  ]);
  const unexpectedValidatorNames = validatorArguments
    .map(({ name }) => name)
    .filter((name) => !allowedValidatorNames.has(name));
  if (unexpectedValidatorNames.length) {
    throw new Error(`Unexpected validator names: ${unexpectedValidatorNames.join(", ")}`);
  }
  const validatorArgumentsByName = new Map(
    validatorArguments.map((argument) => [argument.name, argument]),
  );
  const missingValidatorNames = gateNames.filter(
    (name) => !validatorArgumentsByName.has(name),
  );
  if (gateNames.includes("storyline") && !validatorArgumentsByName.has("storyline-upstream")) {
    missingValidatorNames.push("storyline-upstream");
  }
  if (missingValidatorNames.length) {
    throw new Error(`Missing --validator mappings: ${missingValidatorNames.join(", ")}`);
  }
  await validateCanonicalValidatorArguments(validatorArguments);

  const requiredGates = String(options["required-gates"] ?? gateArguments.map(({ name }) => name).join(","))
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  if (!requiredGates.length) throw new Error("--required-gates cannot be empty");
  const finalPackage = await validatePptxPackage(finalPath);

  const [
    inputArtifact,
    finalArtifactRecord,
    storyline,
    storylineArtifact,
    contentArtifact,
    evidenceArtifact,
    rendererUsage,
    rendererUsageArtifact,
    powerpointCheck,
    currentMatrixSha256,
    currentDesignTokensSha256,
  ] = await Promise.all([
    inputPath ? artifactRecord(inputPath) : Promise.resolve(null),
    artifactRecord(finalPath),
    storylinePath ? readJson(storylinePath, "storyline lock") : Promise.resolve(null),
    storylinePath ? artifactRecord(storylinePath) : Promise.resolve(null),
    contentArtifactPath ? artifactRecord(contentArtifactPath) : Promise.resolve(null),
    evidenceArtifactPath ? artifactRecord(evidenceArtifactPath) : Promise.resolve(null),
    rendererUsagePath ? readJson(rendererUsagePath, "renderer usage") : Promise.resolve(null),
    rendererUsagePath ? artifactRecord(rendererUsagePath) : Promise.resolve(null),
    readJson(powerpointPath, "PowerPoint check"),
    sha256File(MATRIX_PATH),
    sha256File(DESIGN_TOKENS_PATH),
  ]);
  const finalArtifact = {
    ...finalArtifactRecord,
    packageValidation: finalPackage,
  };

  const gates = [];
  const gateReports = new Map();
  const freshnessDependenciesByGate = {
    storyline: [storylinePath],
    evidence: [evidenceArtifactPath, contentArtifactPath],
    content: [contentArtifactPath, MATRIX_PATH],
    handoff: [storylinePath, contentArtifactPath, MATRIX_PATH],
    fingerprint: [inputPath, finalPath],
    ooxml: [finalPath],
    visual: [finalPath],
    "theme-color": [finalPath],
    "powerpoint-render": [finalPath, contentArtifactPath],
  };
  for (const gateArgument of gateArguments) {
    const report = await readJson(gateArgument.filePath, `gate ${gateArgument.name}`);
    gateReports.set(gateArgument.name, report);
    const validatorArgument = validatorArgumentsByName.get(gateArgument.name);
    const validatorSha256 = await sha256File(validatorArgument.filePath);
    const errorCount = Number.isInteger(report.errorCount) ? report.errorCount : null;
    const contractIssues = validateGateContract(gateArgument.name, report);
    if (report.validatorSha256 !== validatorSha256) {
      contractIssues.push(
        `${gateArgument.name}.validatorSha256与--validator ${gateArgument.name}实际脚本不一致`,
      );
    }
    const reportStat = await fs.stat(gateArgument.filePath);
    const dependencyPaths = (freshnessDependenciesByGate[gateArgument.name] ?? [])
      .filter(Boolean);
    const dependencyStats = await Promise.all(
      dependencyPaths.map(async (dependencyPath) => ({
        fileName: path.basename(dependencyPath),
        mtimeMs: (await fs.stat(dependencyPath)).mtimeMs,
      })),
    );
    const maxDependencyMtimeMs = dependencyStats.length
      ? Math.max(...dependencyStats.map((item) => item.mtimeMs))
      : 0;
    const reportFresh = (
      reportStat.mtimeMs + 1 >= maxDependencyMtimeMs
      && reportStat.mtimeMs <= releaseStartedAtMs + 5_000
    );
    if (!reportFresh) {
      contractIssues.push(
        `${gateArgument.name}报告不是当前输入之后生成的本次有效产物`,
      );
    }
    let upstreamValidator = null;
    if (gateArgument.name === "storyline") {
      const upstreamArgument = validatorArgumentsByName.get("storyline-upstream");
      const upstreamSha256 = await sha256File(upstreamArgument.filePath);
      upstreamValidator = {
        fileName: path.basename(upstreamArgument.filePath),
        sha256: upstreamSha256,
        reportedSha256: report.upstreamValidatorSha256 ?? null,
        matched: report.upstreamValidatorSha256 === upstreamSha256,
      };
      if (!upstreamValidator.matched) {
        contractIssues.push(
          "storyline.upstreamValidatorSha256与--validator storyline-upstream实际脚本不一致",
        );
      }
    }
    gates.push({
      name: gateArgument.name,
      fileName: path.basename(gateArgument.filePath),
      sha256: await sha256File(gateArgument.filePath),
      passed: report.passed === true && (errorCount == null || errorCount === 0) && contractIssues.length === 0,
      reportedPassed: report.passed === true,
      contractValid: contractIssues.length === 0,
      contractIssues,
      errorCount,
      warningCount: Number.isFinite(report.warningCount) ? report.warningCount : null,
      schemaVersion: report.schemaVersion ?? null,
      artifactSha256: gateArtifactSha256(gateArgument.name, report),
      inputHashes: report.inputHashes ?? null,
      validator: {
        fileName: path.basename(validatorArgument.filePath),
        sha256: validatorSha256,
        reportedSha256: report.validatorSha256 ?? null,
        matched: report.validatorSha256 === validatorSha256,
      },
      upstreamValidator,
      runAttestation: {
        reportMtimeMs: reportStat.mtimeMs,
        maxDependencyMtimeMs,
        dependencyFiles: dependencyStats,
        releaseStartedAtMs,
        fresh: reportFresh,
      },
    });
  }
  gates.sort((left, right) => left.name.localeCompare(right.name));

  const blockers = [];
  const storylineIds = Array.isArray(storyline?.slides)
    ? storyline.slides.map((slide) => slide?.id)
    : [];
  if (deliveryMode !== "format-only") {
    if (storyline?.lockStatus !== "approved_by_user") {
      addBlocker(blockers, "storyline_not_locked", "storyline lockStatus必须为approved_by_user");
    }
    if (!Array.isArray(storyline?.slides) || storyline.slides.length === 0) {
      addBlocker(blockers, "storyline_slides_missing", "storyline必须包含非空slides[]");
    }
    if (storylineIds.some((id) => !nonEmptyString(id))) {
      addBlocker(blockers, "storyline_slide_id_missing", "storyline每页必须有非空字符串id");
    }
    const duplicateStorylineIds = duplicateValues(storylineIds);
    if (duplicateStorylineIds.length) {
      addBlocker(
        blockers,
        "storyline_slide_id_duplicate",
        [...new Set(duplicateStorylineIds)].join(", "),
      );
    }
  } else {
    const fingerprintReport = gateReports.get("fingerprint");
    if (
      !fingerprintReport?.baseline?.archiveSha256
      || fingerprintReport.baseline.archiveSha256 !== inputArtifact?.sha256
    ) {
      addBlocker(
        blockers,
        "fingerprint_baseline_hash_mismatch",
        "Fingerprint baseline未绑定本次输入PPTX",
      );
    }
  }

  const gatesByName = new Map(gates.map((gate) => [gate.name, gate]));
  for (const gate of gates) {
    if (gate.validator?.matched !== true) {
      addBlocker(
        blockers,
        "gate_validator_hash_mismatch",
        `${gate.name}报告未绑定--validator指定的当前校验脚本`,
      );
    }
    if (gate.upstreamValidator && gate.upstreamValidator.matched !== true) {
      addBlocker(
        blockers,
        "gate_upstream_validator_hash_mismatch",
        `${gate.name}报告未绑定当前上游校验脚本`,
      );
    }
    if (gate.runAttestation?.fresh !== true) {
      addBlocker(
        blockers,
        "gate_run_attestation_failed",
        `${gate.name}报告早于其依赖输入或时间戳晚于本次Release启动`,
      );
    }
  }
  for (const gateName of requiredGates) {
    const gate = gatesByName.get(gateName);
    if (!gate) addBlocker(blockers, "required_gate_missing", gateName);
    else if (!gate.passed) addBlocker(blockers, "required_gate_failed", gateName);
  }
  for (const gateName of MANDATORY_GATES_BY_MODE[deliveryMode]) {
    if (!requiredGates.includes(gateName)) {
      addBlocker(
        blockers,
        "mandatory_gate_not_required",
        `${deliveryMode}必须把${gateName}列为required gate`,
      );
    }
  }
  for (const gateName of ["fingerprint", "ooxml", "visual", "theme-color", "powerpoint-render"]) {
    const gate = gatesByName.get(gateName);
    if (gate && gate.artifactSha256 !== finalArtifact.sha256) {
      addBlocker(
        blockers,
        "gate_artifact_hash_mismatch",
        `${gateName}报告不对应当前最终PPTX`,
      );
    }
  }
  if (deliveryMode !== "format-only") {
    const contentReport = gateReports.get("content");
    const evidenceReport = gateReports.get("evidence");
    const handoffReport = gateReports.get("handoff");
    const expectedBindings = [
      ["storyline", "storyline", gateReports.get("storyline")?.inputHashes?.storylineSha256, storylineArtifact?.sha256],
      ["content", "content", contentReport?.inputHashes?.contentSha256, contentArtifact?.sha256],
      ["evidence", "evidence", evidenceReport?.inputHashes?.evidenceSha256, evidenceArtifact?.sha256],
      ["evidence", "content", evidenceReport?.inputHashes?.contentSha256, contentArtifact?.sha256],
      ["handoff", "storyline", handoffReport?.inputHashes?.storylineSha256, storylineArtifact?.sha256],
      ["handoff", "content", handoffReport?.inputHashes?.contentSha256, contentArtifact?.sha256],
    ];
    for (const [gateName, artifactName, actualHash, expectedHash] of expectedBindings) {
      if (!actualHash || !expectedHash || actualHash !== expectedHash) {
        addBlocker(
          blockers,
          "gate_input_hash_mismatch",
          `${gateName}报告未绑定当前${artifactName}文件`,
        );
      }
    }
    if (
      new Set([
        contentReport?.inputHashes?.matrixSha256,
        evidenceReport?.inputHashes?.matrixSha256,
        handoffReport?.inputHashes?.matrixSha256,
      ]).size !== 1
    ) {
      addBlocker(
        blockers,
        "matrix_contract_hash_mismatch",
        "Evidence、Content与Handoff不是基于同一Layout Matrix运行",
      );
    }
    if (
      contentReport?.inputHashes?.matrixSha256 !== currentMatrixSha256
      || evidenceReport?.inputHashes?.matrixSha256 !== currentMatrixSha256
      || handoffReport?.inputHashes?.matrixSha256 !== currentMatrixSha256
    ) {
      addBlocker(
        blockers,
        "stale_matrix_contract",
        "Evidence、Content或Handoff基于旧版Layout Matrix运行",
      );
    }
    const slideCounts = [
      ["storyline", Array.isArray(storyline?.slides) ? storyline.slides.length : null],
      ["content", contentReport?.slideCount],
      ["evidence", evidenceReport?.coverage?.slides?.total],
      ["handoff", Array.isArray(handoffReport?.semanticHashes) ? handoffReport.semanticHashes.length : null],
      ["visual", gateReports.get("visual")?.slideCount],
    ];
    const finiteCounts = slideCounts.filter(([, value]) => Number.isInteger(value));
    if (
      finiteCounts.length !== slideCounts.length
      || new Set(finiteCounts.map(([, value]) => value)).size !== 1
    ) {
      addBlocker(
        blockers,
        "cross_gate_slide_count_mismatch",
        slideCounts.map(([name, value]) => `${name}=${value ?? "missing"}`).join(", "),
      );
    }
    const contentIds = Array.isArray(contentReport?.results)
      ? contentReport.results.map((result) => result?.storylineId)
      : [];
    const handoffIds = Array.isArray(handoffReport?.semanticHashes)
      ? handoffReport.semanticHashes.map((item) => item?.storylineId)
      : [];
    if (!sameStringSet(contentIds, storylineIds)) {
      addBlocker(
        blockers,
        "content_storyline_id_set_mismatch",
        "Content results[].storylineId必须唯一完整且与storyline slides[].id集合一致",
      );
    }
    if (!sameStringSet(handoffIds, storylineIds)) {
      addBlocker(
        blockers,
        "handoff_storyline_id_set_mismatch",
        "Handoff semanticHashes[].storylineId必须唯一完整且与storyline slides[].id集合一致",
      );
    }
  }

  const rendererMode = options["renderer-mode"] ?? "canonical";
  if (!RENDERER_MODES.has(rendererMode)) {
    addBlocker(blockers, "renderer_mode_invalid", rendererMode);
  }
  const rendererContracts = [];
  if (deliveryMode === "format-only") {
    if (rendererMode === "fallback" && !options["renderer-reason"]) {
      addBlocker(
        blockers,
        "fallback_renderer_reason_missing",
        "format-only使用fallback renderer时必须记录原因",
      );
    }
    if (rendererUsagePath) {
      addBlocker(
        blockers,
        "renderer_usage_not_applicable",
        "format-only没有Content逐页rendererContract，不接受--renderer-usage",
      );
    }
  } else {
    const contentReport = gateReports.get("content");
    const contentResults = Array.isArray(contentReport?.results) ? contentReport.results : [];
    const contentById = new Map(contentResults.map((result) => [result.storylineId, result]));
    const usageSlides = rendererUsageSlides(rendererUsage);
    if (rendererUsagePath && rendererUsage?.schemaVersion !== "ksib-renderer-usage/1.0") {
      addBlocker(
        blockers,
        "renderer_usage_schema_invalid",
        "renderer usage schemaVersion必须为ksib-renderer-usage/1.0",
      );
    }
    if (rendererUsagePath && !usageSlides) {
      addBlocker(
        blockers,
        "renderer_usage_slides_missing",
        "renderer usage必须包含slides[]",
      );
    }
    if (rendererMode === "fallback" && !rendererUsagePath) {
      addBlocker(
        blockers,
        "fallback_renderer_usage_missing",
        "renderer-mode=fallback必须提供--renderer-usage",
      );
    }

    const usageIds = Array.isArray(usageSlides)
      ? usageSlides.map((usage) => usage?.storylineId)
      : [];
    if (Array.isArray(usageSlides)) {
      for (const usage of usageSlides) {
        if (!Object.hasOwn(usage ?? {}, "reason")) {
          addBlocker(
            blockers,
            "renderer_usage_reason_field_missing",
            `${usage?.storylineId ?? "missing"}: renderer usage每页必须显式记录reason；canonical页可为null`,
          );
        }
      }
      if (
        usageIds.some((id) => !nonEmptyString(id))
        || !sameStringSet(usageIds, storylineIds)
      ) {
        addBlocker(
          blockers,
          "renderer_usage_id_set_mismatch",
          "renderer usage storylineId必须唯一完整且与storyline ID集合一致",
        );
      }
    }
    const usageById = new Map(
      Array.isArray(usageSlides)
        ? usageSlides.map((usage) => [usage.storylineId, usage])
        : [],
    );
    let fallbackUseCount = 0;
    for (const storylineId of storylineIds) {
      const contentResult = contentById.get(storylineId);
      const contract = contentResult?.rendererContract ?? {};
      const canonicalRenderer = contract.canonicalRenderer ?? null;
      const fallbackRenderer = contract.fallbackRenderer ?? null;
      const usage = usageById.get(storylineId) ?? null;
      let selectedMode = "canonical";
      let selectedRenderer = canonicalRenderer;
      let reason = null;

      if (usage) {
        if (!["canonical", "fallback"].includes(usage.mode)) {
          addBlocker(
            blockers,
            "renderer_usage_mode_invalid",
            `${storylineId}: mode必须为canonical或fallback`,
          );
        } else {
          selectedMode = usage.mode;
        }
        selectedRenderer = usage.rendererName ?? null;
        reason = usage.reason ?? null;
      }

      if (rendererMode === "canonical") {
        if (usage?.mode === "fallback") {
          addBlocker(
            blockers,
            "canonical_renderer_declares_fallback",
            `${storylineId}: renderer-mode=canonical禁止声明fallback使用`,
          );
        }
        if (usage && usage.rendererName !== canonicalRenderer) {
          addBlocker(
            blockers,
            "canonical_renderer_name_mismatch",
            `${storylineId}: ${usage.rendererName ?? "missing"} != ${canonicalRenderer ?? "missing"}`,
          );
        }
        selectedMode = "canonical";
        selectedRenderer = canonicalRenderer;
        reason = null;
      } else if (rendererMode === "fallback" && usage) {
        if (usage.mode === "canonical") {
          if (usage.rendererName !== canonicalRenderer) {
            addBlocker(
              blockers,
              "canonical_renderer_name_mismatch",
              `${storylineId}: ${usage.rendererName ?? "missing"} != ${canonicalRenderer ?? "missing"}`,
            );
          }
        } else if (usage.mode === "fallback") {
          fallbackUseCount += 1;
          if (!nonEmptyString(usage.reason)) {
            addBlocker(
              blockers,
              "fallback_renderer_reason_missing",
              `${storylineId}: fallback使用必须逐页记录reason`,
            );
          }
          if (!nonEmptyString(fallbackRenderer) || usage.rendererName !== fallbackRenderer) {
            addBlocker(
              blockers,
              "fallback_renderer_not_allowed",
              `${storylineId}: ${usage.rendererName ?? "missing"}不是允许的${fallbackRenderer ?? "none"}`,
            );
          }
        }
      }

      rendererContracts.push({
        storylineId,
        provider: contract.provider ?? null,
        editableNative: contract.editableNative === true,
        canonicalRenderer,
        fallbackRenderer,
        selectedRenderer,
        selectedMode,
        reason,
      });
    }
    if (rendererMode === "fallback" && rendererUsagePath && fallbackUseCount === 0) {
      addBlocker(
        blockers,
        "fallback_renderer_not_used",
        "renderer-mode=fallback至少一页必须明确记录mode=fallback",
      );
    }
  }

  const compactPowerpointCheck = compactCheckStatus(powerpointCheck);
  if (!compactPowerpointCheck.passed) {
    addBlocker(blockers, "powerpoint_check_failed", "人工PowerPoint检查passed必须为true");
  }
  if (!compactPowerpointCheck.checkedBy || !compactPowerpointCheck.checkedAt) {
    addBlocker(blockers, "powerpoint_check_unattributed", "必须记录checkedBy与checkedAt");
  }
  if (compactPowerpointCheck.pptxSha256 !== finalArtifact.sha256) {
    addBlocker(
      blockers,
      "powerpoint_check_hash_mismatch",
      "人工PowerPoint检查记录不对应当前最终PPTX",
    );
  }
  for (const checkName of REQUIRED_POWERPOINT_CHECKS) {
    if (!(checkName in compactPowerpointCheck.checks)) {
      addBlocker(blockers, "powerpoint_subcheck_missing", checkName);
    } else if (compactPowerpointCheck.checks[checkName] !== true) {
      addBlocker(blockers, "powerpoint_subcheck_failed", checkName);
    }
  }
  for (const [objectType, checkNames] of Object.entries(CONDITIONAL_POWERPOINT_CHECKS)) {
    if ((finalPackage.nativeObjectInventory?.[objectType] ?? 0) <= 0) continue;
    for (const checkName of checkNames) {
      if (!(checkName in compactPowerpointCheck.checks)) {
        addBlocker(
          blockers,
          "powerpoint_object_subcheck_missing",
          `${objectType}:${checkName}`,
        );
      } else if (compactPowerpointCheck.checks[checkName] !== true) {
        addBlocker(
          blockers,
          "powerpoint_object_subcheck_failed",
          `${objectType}:${checkName}`,
        );
      }
    }
  }
  const knownPowerpointChecks = new Set([
    ...REQUIRED_POWERPOINT_CHECKS,
    ...Object.values(CONDITIONAL_POWERPOINT_CHECKS).flat(),
  ]);
  for (const [checkName, passed] of Object.entries(compactPowerpointCheck.checks)) {
    if (!knownPowerpointChecks.has(checkName) && passed !== true) {
      addBlocker(blockers, "powerpoint_subcheck_failed", checkName);
    }
  }

  const generatedAt = options["generated-at"] ?? new Date().toISOString();
  const manifest = {
    schemaVersion: SCHEMA_VERSION,
    generatedAt,
    status: blockers.length ? "blocked" : "passed",
    deliveryMode,
    artifacts: {
      inputArtifact,
      parentArtifactSha256: inputArtifact?.sha256 ?? null,
      contentArtifact,
      evidenceArtifact,
      finalPptx: finalArtifact,
    },
    storylineLock: storylinePath ? {
      fileName: path.basename(storylinePath),
      sha256: storylineArtifact.sha256,
      lockStatus: storyline?.lockStatus ?? null,
      slideCount: Array.isArray(storyline?.slides) ? storyline.slides.length : 0,
      slideIds: storylineIds,
    } : null,
    gates,
    requiredGates,
    renderer: {
      name: options.renderer,
      version: options["renderer-version"],
      mode: rendererMode,
      reason: options["renderer-reason"] ?? null,
      usageArtifact: rendererUsageArtifact,
      usageSchemaVersion: rendererUsage?.schemaVersion ?? null,
      contracts: rendererContracts,
    },
    skillContract: {
      layoutMatrixSha256: currentMatrixSha256,
      designTokensSha256: currentDesignTokensSha256,
    },
    manualPowerPointCheck: {
      fileName: path.basename(powerpointPath),
      sha256: await sha256File(powerpointPath),
      ...compactPowerpointCheck,
    },
    blockers,
  };
  manifest.manifestHash = sha256Buffer(Buffer.from(stableJson(manifest), "utf8"));
  return manifest;
}

async function writeManifest(outputPath, manifest) {
  const output = `${JSON.stringify(manifest, null, 2)}\n`;
  if (outputPath) {
    const resolved = path.resolve(outputPath);
    await fs.mkdir(path.dirname(resolved), { recursive: true });
    await fs.writeFile(resolved, output, "utf8");
  }
  process.stdout.write(output);
}

async function selfTest() {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "ksib-release-manifest-"));
  try {
    const write = async (name, value, json = true) => {
      const target = path.join(directory, name);
      await fs.writeFile(target, json ? `${JSON.stringify(value)}\n` : value);
      return target;
    };
    const makeStoredZip = (entries) => {
      const localParts = [];
      const centralParts = [];
      let localOffset = 0;
      for (const [name, value] of Object.entries(entries)) {
        const nameBuffer = Buffer.from(name, "utf8");
        const payload = Buffer.from(value, "utf8");
        const local = Buffer.alloc(30);
        local.writeUInt32LE(0x04034b50, 0);
        local.writeUInt16LE(20, 4);
        local.writeUInt16LE(0, 6);
        local.writeUInt16LE(0, 8);
        local.writeUInt32LE(0, 14);
        local.writeUInt32LE(payload.length, 18);
        local.writeUInt32LE(payload.length, 22);
        local.writeUInt16LE(nameBuffer.length, 26);
        local.writeUInt16LE(0, 28);
        localParts.push(local, nameBuffer, payload);

        const central = Buffer.alloc(46);
        central.writeUInt32LE(0x02014b50, 0);
        central.writeUInt16LE(20, 4);
        central.writeUInt16LE(20, 6);
        central.writeUInt16LE(0, 8);
        central.writeUInt16LE(0, 10);
        central.writeUInt32LE(0, 16);
        central.writeUInt32LE(payload.length, 20);
        central.writeUInt32LE(payload.length, 24);
        central.writeUInt16LE(nameBuffer.length, 28);
        central.writeUInt16LE(0, 30);
        central.writeUInt16LE(0, 32);
        central.writeUInt32LE(0, 38);
        central.writeUInt32LE(localOffset, 42);
        centralParts.push(central, nameBuffer);
        localOffset += local.length + nameBuffer.length + payload.length;
      }
      const localDirectory = Buffer.concat(localParts);
      const centralDirectory = Buffer.concat(centralParts);
      const eocd = Buffer.alloc(22);
      eocd.writeUInt32LE(0x06054b50, 0);
      eocd.writeUInt16LE(Object.keys(entries).length, 8);
      eocd.writeUInt16LE(Object.keys(entries).length, 10);
      eocd.writeUInt32LE(centralDirectory.length, 12);
      eocd.writeUInt32LE(localDirectory.length, 16);
      return Buffer.concat([localDirectory, centralDirectory, eocd]);
    };
    const validPptxBytes = makeStoredZip({
      "[Content_Types].xml": `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>`,
      "_rels/.rels": `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdOffice" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>`,
      "ppt/presentation.xml": `<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
</p:presentation>`,
      "ppt/_rels/presentation.xml.rels": `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>`,
      "ppt/slides/slide1.xml": `<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree><a:tbl/></p:spTree></p:cSld>
</p:sld>`,
      "ppt/charts/chart1.xml": '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"/>',
      "ppt/diagrams/data1.xml": '<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"/>',
    });
    const input = await write("input.pptx", validPptxBytes, false);
    const final = await write("final.pptx", validPptxBytes, false);
    const finalSha256 = await sha256File(final);
    const validatorPaths = {};
    const validatorHashes = {};
    for (const name of [
      "storyline",
      "storyline-upstream",
      "evidence",
      "content",
      "handoff",
      "fingerprint",
      "ooxml",
      "visual",
      "theme-color",
      "powerpoint-render",
    ]) {
      validatorPaths[name] = CANONICAL_VALIDATOR_PATHS[name];
      validatorHashes[name] = await sha256File(validatorPaths[name]);
    }
    const storyline = await write("storyline.json", {
      lockStatus: "approved_by_user",
      slides: [{ id: "S1", actionTitle: "结论" }],
    });
    const contentArtifact = await write("content-artifact.json", {
      slides: [{ storylineId: "S1", title: "结论", slideType: "singleExhibit" }],
    });
    const evidenceArtifact = await write("evidence-artifact.json", {
      contractVersion: "1.0",
      sources: [],
      calculations: [],
      claims: [],
    });
    const [storylineSha256, contentArtifactSha256, evidenceArtifactSha256] = await Promise.all([
      sha256File(storyline),
      sha256File(contentArtifact),
      sha256File(evidenceArtifact),
    ]);
    const matrixSha256 = await sha256File(MATRIX_PATH);
    const contentGate = await write("content.json", {
      schemaVersion: "ksib-content-gate/2.0",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.content,
      slideCount: 1,
      inputHashes: {
        contentSha256: contentArtifactSha256,
        matrixSha256,
      },
      results: [{
        slide: 1,
        storylineId: "S1",
        rendererContract: {
          provider: "system-presentations-artifact-tool-or-validated-project-builder",
          canonicalRenderer: "singleExhibit",
          fallbackRenderer: "evidenceInsight",
          editableNative: true,
        },
      }],
    });
    const storylineGate = await write("storyline-gate.json", {
      schemaVersion: "ksib-storyline-gate/1.0",
      passed: true,
      productionReady: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.storyline,
      upstreamValidatorSha256: validatorHashes["storyline-upstream"],
      inputHashes: { storylineSha256 },
    });
    const evidenceGate = await write("evidence.json", {
      schemaVersion: "ksib-evidence-gate/2.0",
      passed: true,
      mode: "full",
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.evidence,
      inputHashes: {
        evidenceSha256: evidenceArtifactSha256,
        contentSha256: contentArtifactSha256,
        matrixSha256,
      },
      coverage: { slides: { total: 1 } },
    });
    const handoffGate = await write("handoff.json", {
      schemaVersion: "ksib-storyline-handoff/2.0",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.handoff,
      inputHashes: {
        storylineSha256,
        contentSha256: contentArtifactSha256,
        matrixSha256,
      },
      semanticHashes: [{ storylineId: "S1", storylineHash: "a", contentHash: "a" }],
      argumentTree: {
        passed: true,
        pillarCount: 1,
        substantiveSlideCount: 1,
        assignedSlideCount: 1,
      },
    });
    const ooxmlGate = await write("ooxml.json", {
      schemaVersion: "ksib-ooxml-qa/2.0",
      themePolicy: "ksib",
      fontPolicy: "ksib",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.ooxml,
      reports: [{ sha256: finalSha256 }],
    });
    const visualGate = await write("visual.json", {
      schemaVersion: "ksib-visual-review/2.0",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.visual,
      slideCount: 1,
      reviewedSlideCount: 1,
      reviewedBy: "reviewer",
      reviewedAt: "2026-07-20T00:00:00Z",
      checks: Object.fromEntries(REQUIRED_VISUAL_CHECKS.map((name) => [name, true])),
      pptx: { sha256: finalSha256 },
      slides: [{
        slide: 1,
        passed: true,
        sha256: "render-sha",
        pixelSha256: "pixel-sha",
        width: 1280,
        height: 720,
      }],
    });
    const themeColorGate = await write("theme-color.json", {
      schemaVersion: "ksib-theme-color-gate/1.1",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes["theme-color"],
      artifactSha256: finalSha256,
      inventorySha256: "inventory-sha",
      inventorySemanticSha256: "inventory-semantic-sha",
      reExtractedInventorySemanticSha256: "inventory-semantic-sha",
      usageSha256: "usage-sha",
      extractorSha256: "extractor-sha",
      checkedSlides: 1,
      checkedVisibleBindings: 1,
    });
    const powerpointRenderGate = await write("powerpoint-render.json", {
      schemaVersion: "ksib-powerpoint-render-gate/1.0",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes["powerpoint-render"],
      pptx: { sha256: finalSha256, slideCount: 1 },
      inputHashes: {
        contentSha256: contentArtifactSha256,
        formatContractSha256: "format-contract-sha",
      },
      review: {
        source: "Microsoft PowerPoint",
        reviewedBy: "reviewer",
        reviewedAt: "2026-07-20T00:00:00Z",
        reviewerRole: "independent",
      },
      powerpointScreenshotSetHash: "powerpoint-screenshot-set-sha",
      reviewedSlideCount: 1,
      slides: [{
        slide: 1,
        passed: true,
        sha256: "powerpoint-slide-sha",
        pixelSha256: "powerpoint-slide-pixel-sha",
        reviewedAt: "2026-07-20T00:00:00Z",
      }],
      checks: {
        powerpointScreenshots: true,
        labelOwnership: true,
        numberDisplay: true,
        financialChartSemantics: true,
        rendererImplementation: true,
      },
    });
    const powerpoint = await write("powerpoint.json", {
      passed: true,
      checkedBy: "reviewer",
      checkedAt: "2026-07-20T00:00:00Z",
      pptxSha256: finalSha256,
      checks: {
        noRepairPrompt: true,
        textEditUndo: true,
        textColorChangeUndo: true,
        boldToggleUndo: true,
        fontFamilyChangeUndo: true,
        shapeFillChangeUndo: true,
        groupUngroup: true,
        fontDisplay: true,
        finalSlideAndPageNumber: true,
        tableCellFormatUndo: true,
        chartTextFormatUndo: true,
        chartDataEditUndo: true,
        smartArtTextFormatUndo: true,
      },
    });
    const base = {
      "input-pptx": input,
      "final-pptx": final,
      "storyline-lock": storyline,
      "content-artifact": contentArtifact,
      "evidence-artifact": evidenceArtifact,
      "delivery-mode": "locked-content",
      renderer: "test-renderer",
      "renderer-version": "1.0.0",
      "renderer-mode": "canonical",
      "powerpoint-check": powerpoint,
      gate: [
        `storyline=${storylineGate}`,
        `evidence=${evidenceGate}`,
        `content=${contentGate}`,
        `handoff=${handoffGate}`,
        `ooxml=${ooxmlGate}`,
        `visual=${visualGate}`,
        `theme-color=${themeColorGate}`,
        `powerpoint-render=${powerpointRenderGate}`,
      ],
      validator: [
        `storyline=${validatorPaths.storyline}`,
        `storyline-upstream=${validatorPaths["storyline-upstream"]}`,
        `evidence=${validatorPaths.evidence}`,
        `content=${validatorPaths.content}`,
        `handoff=${validatorPaths.handoff}`,
        `ooxml=${validatorPaths.ooxml}`,
        `visual=${validatorPaths.visual}`,
        `theme-color=${validatorPaths["theme-color"]}`,
        `powerpoint-render=${validatorPaths["powerpoint-render"]}`,
      ],
      "required-gates": "storyline,evidence,content,handoff,ooxml,visual,theme-color,powerpoint-render",
      "generated-at": "2026-07-20T00:00:00Z",
    };

    const valid = await buildManifest(base);
    const weakPowerpointRenderGatePath = await write("weak-powerpoint-render.json", {
      ...(await readJson(powerpointRenderGate, "valid PowerPoint render gate")),
      passed: true,
      checks: {
        ...(await readJson(powerpointRenderGate, "valid PowerPoint render gate")).checks,
        labelOwnership: false,
      },
    });
    const weakPowerpointRenderGate = await buildManifest({
      ...base,
      gate: base.gate.map((value) => value.startsWith("powerpoint-render=")
        ? `powerpoint-render=${weakPowerpointRenderGatePath}`
        : value),
    });
    const failedGatePath = await write("failed.json", { passed: false, errorCount: 1 });
    const failedGate = await buildManifest({
      ...base,
      gate: base.gate.map((value) => value.startsWith("content=") ? `content=${failedGatePath}` : value),
    });
    const missingGate = await buildManifest({
      ...base,
      gate: base.gate.filter((value) => !value.startsWith("ooxml=")),
      validator: base.validator.filter((value) => !value.startsWith("ooxml=")),
    });
    const missingThemeColorGate = await buildManifest({
      ...base,
      gate: base.gate.filter((value) => !value.startsWith("theme-color=")),
      validator: base.validator.filter((value) => !value.startsWith("theme-color=")),
      "required-gates": "storyline,evidence,content,handoff,ooxml,visual,powerpoint-render",
    });
    const unlockedPath = await write("unlocked.json", {
      lockStatus: "draft",
      slides: [{ id: "S1", actionTitle: "结论" }],
    });
    const unlocked = await buildManifest({ ...base, "storyline-lock": unlockedPath });
    const incompletePowerpointPath = await write("incomplete-powerpoint.json", {
      passed: true,
      checkedBy: "reviewer",
      checkedAt: "2026-07-20T00:00:00Z",
      pptxSha256: finalSha256,
      checks: { noRepairPrompt: true },
    });
    const incompletePowerpoint = await buildManifest({
      ...base,
      "powerpoint-check": incompletePowerpointPath,
    });
    const missingBoldTogglePath = await write("missing-bold-toggle.json", {
      passed: true,
      checkedBy: "reviewer",
      checkedAt: "2026-07-20T00:00:00Z",
      pptxSha256: finalSha256,
      checks: {
        noRepairPrompt: true,
        textEditUndo: true,
        textColorChangeUndo: true,
        fontFamilyChangeUndo: true,
        shapeFillChangeUndo: true,
        groupUngroup: true,
        fontDisplay: true,
        finalSlideAndPageNumber: true,
        tableCellFormatUndo: true,
        chartTextFormatUndo: true,
        chartDataEditUndo: true,
        smartArtTextFormatUndo: true,
      },
    });
    const missingBoldToggle = await buildManifest({
      ...base,
      "powerpoint-check": missingBoldTogglePath,
    });
    const validPowerpointPayload = await readJson(
      powerpoint,
      "valid PowerPoint check",
    );
    const {
      chartDataEditUndo: omittedChartDataEdit,
      ...checksWithoutChartDataEdit
    } = validPowerpointPayload.checks;
    const missingChartDataEditPath = await write(
      "missing-chart-data-edit.json",
      {
        ...validPowerpointPayload,
        checks: checksWithoutChartDataEdit,
      },
    );
    const missingChartDataEdit = await buildManifest({
      ...base,
      "powerpoint-check": missingChartDataEditPath,
    });
    const {
      tableCellFormatUndo: omittedTableCellFormat,
      ...checksWithoutTableCellFormat
    } = validPowerpointPayload.checks;
    const missingTableCellFormatPath = await write(
      "missing-table-cell-format.json",
      {
        ...validPowerpointPayload,
        checks: checksWithoutTableCellFormat,
      },
    );
    const missingTableCellFormat = await buildManifest({
      ...base,
      "powerpoint-check": missingTableCellFormatPath,
    });
    const {
      smartArtTextFormatUndo: omittedSmartArtTextFormat,
      ...checksWithoutSmartArtTextFormat
    } = validPowerpointPayload.checks;
    const missingSmartArtTextFormatPath = await write(
      "missing-smartart-text-format.json",
      {
        ...validPowerpointPayload,
        checks: checksWithoutSmartArtTextFormat,
      },
    );
    const missingSmartArtTextFormat = await buildManifest({
      ...base,
      "powerpoint-check": missingSmartArtTextFormatPath,
    });
    const stalePowerpointPath = await write("stale-powerpoint.json", {
      passed: true,
      checkedBy: "reviewer",
      checkedAt: "2026-07-20T00:00:00Z",
      pptxSha256: "stale-pptx-sha",
      checks: {
        noRepairPrompt: true,
        textEditUndo: true,
        textColorChangeUndo: true,
        boldToggleUndo: true,
        fontFamilyChangeUndo: true,
        shapeFillChangeUndo: true,
        groupUngroup: true,
        fontDisplay: true,
        finalSlideAndPageNumber: true,
        tableCellFormatUndo: true,
        chartTextFormatUndo: true,
        chartDataEditUndo: true,
        smartArtTextFormatUndo: true,
      },
    });
    const stalePowerpoint = await buildManifest({
      ...base,
      "powerpoint-check": stalePowerpointPath,
    });
    const fingerprintGate = await write("fingerprint.json", {
      schemaVersion: "ksib-pptx-semantic-compare/3.2",
      mode: "format-only",
      fontPolicy: "allow",
      stylePolicy: "preserve",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.fingerprint,
      baseline: { archiveSha256: await sha256File(input) },
      candidate: { archiveSha256: finalSha256 },
    });
    const formatOnly = await buildManifest({
      ...base,
      "delivery-mode": "format-only",
      "storyline-lock": undefined,
      gate: [`fingerprint=${fingerprintGate}`, `ooxml=${ooxmlGate}`, `visual=${visualGate}`, `theme-color=${themeColorGate}`, `powerpoint-render=${powerpointRenderGate}`],
      validator: [
        `fingerprint=${validatorPaths.fingerprint}`,
        `ooxml=${validatorPaths.ooxml}`,
        `visual=${validatorPaths.visual}`,
        `theme-color=${validatorPaths["theme-color"]}`,
        `powerpoint-render=${validatorPaths["powerpoint-render"]}`,
      ],
      "required-gates": "fingerprint,ooxml,visual,theme-color,powerpoint-render",
    });
    const formatOnlyMissingFingerprint = await buildManifest({
      ...base,
      "delivery-mode": "format-only",
      "storyline-lock": undefined,
      gate: [`ooxml=${ooxmlGate}`, `visual=${visualGate}`, `theme-color=${themeColorGate}`, `powerpoint-render=${powerpointRenderGate}`],
      validator: [`ooxml=${validatorPaths.ooxml}`, `visual=${validatorPaths.visual}`, `theme-color=${validatorPaths["theme-color"]}`, `powerpoint-render=${validatorPaths["powerpoint-render"]}`],
      "required-gates": "ooxml,visual,theme-color,powerpoint-render",
    });
    const staleFingerprintBaselinePath = await write("stale-fingerprint-baseline.json", {
      schemaVersion: "ksib-pptx-semantic-compare/3.2",
      mode: "format-only",
      fontPolicy: "allow",
      stylePolicy: "preserve",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.fingerprint,
      baseline: { archiveSha256: "stale-input-sha" },
      candidate: { archiveSha256: finalSha256 },
    });
    const staleFingerprintBaseline = await buildManifest({
      ...base,
      "delivery-mode": "format-only",
      "storyline-lock": undefined,
      gate: [
        `fingerprint=${staleFingerprintBaselinePath}`,
        `ooxml=${ooxmlGate}`,
        `visual=${visualGate}`,
        `theme-color=${themeColorGate}`,
        `powerpoint-render=${powerpointRenderGate}`,
      ],
      validator: [
        `fingerprint=${validatorPaths.fingerprint}`,
        `ooxml=${validatorPaths.ooxml}`,
        `visual=${validatorPaths.visual}`,
        `theme-color=${validatorPaths["theme-color"]}`,
        `powerpoint-render=${validatorPaths["powerpoint-render"]}`,
      ],
      "required-gates": "fingerprint,ooxml,visual,theme-color,powerpoint-render",
    });
    const fallbackWithoutUsage = await buildManifest({
      ...base,
      "renderer-mode": "fallback",
    });
    const emptyVisualGatePath = await write("empty-visual.json", {
      passed: true,
      errorCount: 0,
    });
    const emptyVisualGate = await buildManifest({
      ...base,
      gate: base.gate.map((value) => value.startsWith("visual=") ? `visual=${emptyVisualGatePath}` : value),
    });
    const staleVisualGatePath = await write("stale-visual.json", {
      schemaVersion: "ksib-visual-review/2.0",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.visual,
      slideCount: 1,
      reviewedSlideCount: 1,
      reviewedBy: "reviewer",
      reviewedAt: "2026-07-20T00:00:00Z",
      checks: Object.fromEntries(REQUIRED_VISUAL_CHECKS.map((name) => [name, true])),
      pptx: { sha256: "stale-pptx-sha" },
      slides: [{
        slide: 1,
        passed: true,
        sha256: "render-sha",
        pixelSha256: "pixel-sha",
        width: 1280,
        height: 720,
      }],
    });
    const staleVisualGate = await buildManifest({
      ...base,
      gate: base.gate.map((value) => value.startsWith("visual=") ? `visual=${staleVisualGatePath}` : value),
    });
    const staleContentBindingPath = await write("stale-content-binding.json", {
      schemaVersion: "ksib-content-gate/2.0",
      passed: true,
      errorCount: 0,
      errors: [],
      validatorSha256: validatorHashes.content,
      slideCount: 1,
      inputHashes: {
        contentSha256: "stale-content-sha",
        matrixSha256,
      },
      results: [{
        slide: 1,
        storylineId: "S1",
        rendererContract: {
          provider: "system-presentations-artifact-tool-or-validated-project-builder",
          canonicalRenderer: "singleExhibit",
          fallbackRenderer: "evidenceInsight",
          editableNative: true,
        },
      }],
    });
    const staleContentBinding = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("content=")
          ? `content=${staleContentBindingPath}`
          : value
      )),
    });
    const [
      validStorylineGateReport,
      validContentGateReport,
      validHandoffGateReport,
      validVisualGateReport,
    ] = await Promise.all([
      readJson(storylineGate, "valid storyline gate"),
      readJson(contentGate, "valid content gate"),
      readJson(handoffGate, "valid handoff gate"),
      readJson(visualGate, "valid visual gate"),
    ]);
    const badStorylineSchemaPath = await write("bad-storyline-schema.json", {
      ...validStorylineGateReport,
      schemaVersion: "legacy-storyline-gate/0.1",
    });
    const badStorylineSchema = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("storyline=")
          ? `storyline=${badStorylineSchemaPath}`
          : value
      )),
    });
    const staleStorylineBindingPath = await write("stale-storyline-binding.json", {
      ...validStorylineGateReport,
      inputHashes: { storylineSha256: "stale-storyline-sha" },
    });
    const staleStorylineBinding = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("storyline=")
          ? `storyline=${staleStorylineBindingPath}`
          : value
      )),
    });
    const staleUpstreamValidatorPath = await write("stale-upstream-validator.json", {
      ...validStorylineGateReport,
      upstreamValidatorSha256: "stale-validator-sha",
    });
    const staleUpstreamValidator = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("storyline=")
          ? `storyline=${staleUpstreamValidatorPath}`
          : value
      )),
    });
    const validatorMismatchPath = await write("validator-mismatch.json", {
      ...validContentGateReport,
      validatorSha256: "stale-validator-sha",
    });
    const validatorMismatch = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("content=")
          ? `content=${validatorMismatchPath}`
          : value
      )),
    });
    const { errors: ignoredErrors, ...contentWithoutErrors } = validContentGateReport;
    const missingErrorsArrayPath = await write("missing-errors-array.json", contentWithoutErrors);
    const missingErrorsArray = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("content=")
          ? `content=${missingErrorsArrayPath}`
          : value
      )),
    });
    const nonzeroErrorsPath = await write("nonzero-errors.json", {
      ...validContentGateReport,
      passed: true,
      errorCount: 1,
      errors: [{ rule: "synthetic_failure" }],
    });
    const nonzeroErrors = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("content=")
          ? `content=${nonzeroErrorsPath}`
          : value
      )),
    });
    const contentIdMismatchPath = await write("content-id-mismatch.json", {
      ...validContentGateReport,
      results: [{
        ...validContentGateReport.results[0],
        storylineId: "S2",
      }],
    });
    const contentIdMismatch = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("content=")
          ? `content=${contentIdMismatchPath}`
          : value
      )),
    });
    const handoffIdMismatchPath = await write("handoff-id-mismatch.json", {
      ...validHandoffGateReport,
      semanticHashes: [{
        ...validHandoffGateReport.semanticHashes[0],
        storylineId: "S2",
      }],
    });
    const handoffIdMismatch = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("handoff=")
          ? `handoff=${handoffIdMismatchPath}`
          : value
      )),
    });
    const visualSlideSetMismatchPath = await write("visual-slide-set-mismatch.json", {
      ...validVisualGateReport,
      slides: [{
        ...validVisualGateReport.slides[0],
        slide: 2,
      }],
    });
    const visualSlideSetMismatch = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("visual=")
          ? `visual=${visualSlideSetMismatchPath}`
          : value
      )),
    });
    const duplicateContentIdsPath = await write("duplicate-content-ids.json", {
      ...validContentGateReport,
      slideCount: 2,
      results: [
        validContentGateReport.results[0],
        {
          ...validContentGateReport.results[0],
          storylineId: "S2",
        },
      ],
    });
    const duplicateContentIds = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("content=")
          ? `content=${duplicateContentIdsPath}`
          : value
      )),
    });
    const duplicateHandoffIdsPath = await write("duplicate-handoff-ids.json", {
      ...validHandoffGateReport,
      semanticHashes: [
        validHandoffGateReport.semanticHashes[0],
        validHandoffGateReport.semanticHashes[0],
      ],
    });
    const duplicateHandoffIds = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("handoff=")
          ? `handoff=${duplicateHandoffIdsPath}`
          : value
      )),
    });
    const duplicateVisualSlidesPath = await write("duplicate-visual-slides.json", {
      ...validVisualGateReport,
      slideCount: 2,
      reviewedSlideCount: 2,
      slides: [
        validVisualGateReport.slides[0],
        validVisualGateReport.slides[0],
      ],
    });
    const duplicateVisualSlides = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("visual=")
          ? `visual=${duplicateVisualSlidesPath}`
          : value
      )),
    });
    const duplicateVisualHashesPath = await write("duplicate-visual-hashes.json", {
      ...validVisualGateReport,
      slideCount: 2,
      reviewedSlideCount: 2,
      slides: [
        validVisualGateReport.slides[0],
        {
          ...validVisualGateReport.slides[0],
          slide: 2,
        },
      ],
    });
    const duplicateVisualHashes = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("visual=")
          ? `visual=${duplicateVisualHashesPath}`
          : value
      )),
    });
    let missingValidatorMappingThrows = false;
    try {
      await buildManifest({
        ...base,
        validator: base.validator.filter((value) => !value.startsWith("visual=")),
      });
    } catch (error) {
      missingValidatorMappingThrows = error.message.includes("Missing --validator mappings: visual");
    }
    const noncanonicalVisualValidator = await write(
      "noncanonical-visual-validator.py",
      await fs.readFile(validatorPaths.visual),
      false,
    );
    let noncanonicalValidatorThrows = false;
    try {
      await buildManifest({
        ...base,
        validator: base.validator.map((value) => (
          value.startsWith("visual=")
            ? `visual=${noncanonicalVisualValidator}`
            : value
        )),
      });
    } catch (error) {
      noncanonicalValidatorThrows = error.message.includes(
        "Noncanonical validator path for visual",
      );
    }
    const invalidFinalPptx = await write("invalid-final.pptx", Buffer.from("not-a-zip"), false);
    let invalidFinalPptxThrows = false;
    try {
      await buildManifest({ ...base, "final-pptx": invalidFinalPptx });
    } catch (error) {
      invalidFinalPptxThrows = error.message.includes(
        "Final PPTX is not a valid ZIP package",
      );
    }
    const noSlidePptxBytes = makeStoredZip({
      "[Content_Types].xml": `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
</Types>`,
      "_rels/.rels": `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdOffice" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>`,
      "ppt/presentation.xml": '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>',
      "ppt/_rels/presentation.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
    });
    const noSlideFinalPptx = await write(
      "no-slide-final.pptx",
      noSlidePptxBytes,
      false,
    );
    let noSlideFinalPptxThrows = false;
    try {
      await buildManifest({ ...base, "final-pptx": noSlideFinalPptx });
    } catch (error) {
      noSlideFinalPptxThrows = error.message.includes(
        "Final PPTX presentation contains no slide references",
      );
    }
    const wrongExtensionFinal = await write("final.zip", validPptxBytes, false);
    let wrongExtensionThrows = false;
    try {
      await buildManifest({ ...base, "final-pptx": wrongExtensionFinal });
    } catch (error) {
      wrongExtensionThrows = error.message.includes(
        "Final artifact must have .pptx extension",
      );
    }
    const staleRunReportPath = await write("stale-run-report.json", validContentGateReport);
    await fs.utimes(staleRunReportPath, new Date(0), new Date(0));
    const staleRunReport = await buildManifest({
      ...base,
      gate: base.gate.map((value) => (
        value.startsWith("content=")
          ? `content=${staleRunReportPath}`
          : value
      )),
    });

    const fallbackUsagePath = await write("fallback-usage.json", {
      schemaVersion: "ksib-renderer-usage/1.0",
      slides: [{
        storylineId: "S1",
        rendererName: "evidenceInsight",
        mode: "fallback",
        reason: "canonical renderer在目标环境不可用",
      }],
    });
    const validFallback = await buildManifest({
      ...base,
      "renderer-mode": "fallback",
      "renderer-usage": fallbackUsagePath,
    });
    const canonicalDeclaresFallback = await buildManifest({
      ...base,
      "renderer-mode": "canonical",
      "renderer-usage": fallbackUsagePath,
    });
    const disallowedFallbackUsagePath = await write("disallowed-fallback-usage.json", {
      schemaVersion: "ksib-renderer-usage/1.0",
      slides: [{
        storylineId: "S1",
        rendererName: "unapprovedRenderer",
        mode: "fallback",
        reason: "测试未获批准的renderer",
      }],
    });
    const disallowedFallback = await buildManifest({
      ...base,
      "renderer-mode": "fallback",
      "renderer-usage": disallowedFallbackUsagePath,
    });
    const incompleteRendererUsagePath = await write("incomplete-renderer-usage.json", {
      schemaVersion: "ksib-renderer-usage/1.0",
      slides: [{
        storylineId: "S2",
        rendererName: "evidenceInsight",
        mode: "fallback",
        reason: "测试错误ID",
      }],
    });
    const incompleteRendererUsage = await buildManifest({
      ...base,
      "renderer-mode": "fallback",
      "renderer-usage": incompleteRendererUsagePath,
    });
    const missingReasonUsagePath = await write("missing-reason-usage.json", {
      schemaVersion: "ksib-renderer-usage/1.0",
      slides: [{
        storylineId: "S1",
        rendererName: "evidenceInsight",
        mode: "fallback",
      }],
    });
    const missingReasonUsage = await buildManifest({
      ...base,
      "renderer-mode": "fallback",
      "renderer-usage": missingReasonUsagePath,
    });
    const invalidRendererUsageSchemaPath = await write("invalid-renderer-usage-schema.json", {
      schemaVersion: "legacy-renderer-usage/0.1",
      slides: [{
        storylineId: "S1",
        rendererName: "evidenceInsight",
        mode: "fallback",
        reason: "测试旧版usage schema",
      }],
    });
    const invalidRendererUsageSchema = await buildManifest({
      ...base,
      "renderer-mode": "fallback",
      "renderer-usage": invalidRendererUsageSchemaPath,
    });

    const tests = {
      valid_manifest_passes: valid.status === "passed",
      parent_artifact_is_hash_bound: (
        valid.artifacts?.parentArtifactSha256
        === valid.artifacts?.inputArtifact?.sha256
      ),
      design_tokens_are_hash_bound: (
        valid.skillContract?.designTokensSha256
        === await sha256File(DESIGN_TOKENS_PATH)
      ),
      valid_gate_validators_are_hash_bound: valid.gates.every(
        (gate) => gate.validator?.matched === true,
      ),
      passed_true_cannot_bypass_powerpoint_render_contract: weakPowerpointRenderGate.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "powerpoint-render",
      ),
      storyline_upstream_validator_is_hash_bound: valid.gates.find(
        (gate) => gate.name === "storyline",
      )?.upstreamValidator?.matched === true,
      failed_required_gate_blocks: failedGate.blockers.some((item) => item.rule === "required_gate_failed"),
      missing_required_gate_blocks: missingGate.blockers.some((item) => item.rule === "required_gate_missing"),
      final_pptx_theme_color_gate_is_mandatory: missingThemeColorGate.blockers.some(
        (item) => item.rule === "mandatory_gate_not_required" && item.detail.includes("theme-color"),
      ),
      unlocked_storyline_blocks: unlocked.blockers.some((item) => item.rule === "storyline_not_locked"),
      incomplete_powerpoint_check_blocks: incompletePowerpoint.blockers.some(
        (item) => item.rule === "powerpoint_subcheck_missing",
      ),
      bold_toggle_is_an_independent_release_gate: missingBoldToggle.blockers.some(
        (item) => item.rule === "powerpoint_subcheck_missing"
          && item.detail === "boldToggleUndo",
      ),
      chart_data_editability_is_object_conditional_gate: (
        omittedChartDataEdit === true
        && missingChartDataEdit.blockers.some(
          (item) => item.rule === "powerpoint_object_subcheck_missing"
          && item.detail === "charts:chartDataEditUndo",
        )
      ),
      table_editability_is_object_conditional_gate: (
        omittedTableCellFormat === true
        && missingTableCellFormat.blockers.some(
          (item) => item.rule === "powerpoint_object_subcheck_missing"
            && item.detail === "tables:tableCellFormatUndo",
        )
      ),
      smartart_editability_is_object_conditional_gate: (
        omittedSmartArtTextFormat === true
        && missingSmartArtTextFormat.blockers.some(
          (item) => item.rule === "powerpoint_object_subcheck_missing"
            && item.detail === "smartArt:smartArtTextFormatUndo",
        )
      ),
      stale_powerpoint_check_blocks: stalePowerpoint.blockers.some(
        (item) => item.rule === "powerpoint_check_hash_mismatch",
      ),
      format_only_without_storyline_passes: formatOnly.status === "passed",
      format_only_requires_fingerprint_gate: formatOnlyMissingFingerprint.blockers.some(
        (item) => item.rule === "mandatory_gate_not_required",
      ),
      fingerprint_baseline_is_bound_to_input_pptx: staleFingerprintBaseline.blockers.some(
        (item) => item.rule === "fingerprint_baseline_hash_mismatch",
      ),
      fallback_renderer_requires_usage: fallbackWithoutUsage.blockers.some(
        (item) => item.rule === "fallback_renderer_usage_missing",
      ),
      empty_passed_gate_cannot_bypass_contract: emptyVisualGate.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "visual",
      ),
      stale_gate_cannot_release_new_pptx: staleVisualGate.blockers.some(
        (item) => item.rule === "gate_artifact_hash_mismatch",
      ),
      gate_reports_are_bound_to_exact_inputs: staleContentBinding.blockers.some(
        (item) => item.rule === "gate_input_hash_mismatch",
      ),
      storyline_schema_is_explicit: badStorylineSchema.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "storyline",
      ),
      storyline_gate_is_bound_to_exact_lock: staleStorylineBinding.blockers.some(
        (item) => item.rule === "gate_input_hash_mismatch"
          && item.detail.includes("storyline报告"),
      ),
      storyline_upstream_validator_mismatch_blocks: staleUpstreamValidator.blockers.some(
        (item) => item.rule === "gate_upstream_validator_hash_mismatch"
          && item.detail.includes("storyline"),
      ),
      gate_validator_hash_mismatch_blocks: validatorMismatch.blockers.some(
        (item) => item.rule === "gate_validator_hash_mismatch"
          && item.detail.includes("content"),
      ),
      missing_gate_errors_array_blocks: missingErrorsArray.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "content",
      ),
      nonzero_gate_errors_block: nonzeroErrors.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "content",
      ),
      every_gate_requires_validator_mapping: missingValidatorMappingThrows,
      content_ids_match_storyline_exactly: contentIdMismatch.blockers.some(
        (item) => item.rule === "content_storyline_id_set_mismatch",
      ),
      handoff_ids_match_storyline_exactly: handoffIdMismatch.blockers.some(
        (item) => item.rule === "handoff_storyline_id_set_mismatch",
      ),
      visual_slide_numbers_are_unique_and_complete: visualSlideSetMismatch.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "visual",
      ),
      content_slide_numbers_are_unique_and_complete: duplicateContentIds.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "content",
      ),
      duplicate_handoff_ids_block: duplicateHandoffIds.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "handoff",
      ),
      duplicate_visual_slide_numbers_block: duplicateVisualSlides.blockers.some(
        (item) => item.rule === "required_gate_failed" && item.detail === "visual",
      ),
      duplicate_visual_png_hashes_block: duplicateVisualHashes.gates.find(
        (gate) => gate.name === "visual",
      )?.contractIssues.some((detail) => detail.includes("sha256必须逐页唯一")),
      canonical_validator_paths_are_mandatory: noncanonicalValidatorThrows,
      non_pptx_zip_final_artifact_blocks: invalidFinalPptxThrows,
      empty_presentation_package_blocks: noSlideFinalPptxThrows,
      wrong_final_artifact_extension_blocks: wrongExtensionThrows,
      stale_gate_report_run_attestation_blocks: staleRunReport.blockers.some(
        (item) => item.rule === "gate_run_attestation_failed"
          && item.detail.includes("content"),
      ),
      canonical_mode_forbids_explicit_fallback: canonicalDeclaresFallback.blockers.some(
        (item) => item.rule === "canonical_renderer_declares_fallback",
      ),
      valid_allowed_fallback_passes: validFallback.status === "passed"
        && validFallback.renderer.contracts[0]?.selectedRenderer === "evidenceInsight"
        && validFallback.renderer.contracts[0]?.selectedMode === "fallback"
        && validFallback.renderer.usageSchemaVersion === "ksib-renderer-usage/1.0",
      unapproved_fallback_renderer_blocks: disallowedFallback.blockers.some(
        (item) => item.rule === "fallback_renderer_not_allowed",
      ),
      renderer_usage_ids_must_be_complete: incompleteRendererUsage.blockers.some(
        (item) => item.rule === "renderer_usage_id_set_mismatch",
      ),
      renderer_usage_requires_explicit_reason_field: missingReasonUsage.blockers.some(
        (item) => item.rule === "renderer_usage_reason_field_missing",
      ),
      renderer_usage_schema_is_versioned: invalidRendererUsageSchema.blockers.some(
        (item) => item.rule === "renderer_usage_schema_invalid",
      ),
      canonical_contracts_are_derived_per_slide: valid.renderer.contracts.length === 1
        && valid.storylineLock.slideIds[0] === "S1"
        && valid.renderer.contracts[0]?.storylineId === "S1"
        && valid.renderer.contracts[0]?.canonicalRenderer === "singleExhibit"
        && valid.renderer.contracts[0]?.selectedMode === "canonical",
    };
    if (Object.values(tests).some((passed) => !passed)) {
      throw new Error(`Self-test failed: ${JSON.stringify(tests)}`);
    }
    process.stdout.write(`${JSON.stringify({ passed: true, tests: Object.keys(tests) }, null, 2)}\n`);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["self-test"]) {
    await selfTest();
    return;
  }
  const manifest = await buildManifest(args);
  await writeManifest(args.output, manifest);
  if (manifest.status !== "passed") process.exitCode = 1;
}

main().catch((error) => {
  process.stderr.write(`${JSON.stringify({ passed: false, error: error.message })}\n`);
  process.exitCode = 2;
});
