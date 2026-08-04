#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(SCRIPT_DIR, "..");
const CONTRACT_PATH = path.join(SKILL_ROOT, "references", "powerpoint-master-contract.json");
const TOKENS_PATH = path.join(SKILL_ROOT, "references", "design-tokens.json");
const TEMPLATE_DIR = path.join(SKILL_ROOT, "templates");
const TEMP_DIR = path.join(SKILL_ROOT, ".template-build");
const PX_PER_INCH = 96;
const PX_PER_POINT = 96 / 72;

const inch = (value) => value * PX_PER_INCH;
const pt = (value) => value * PX_PER_POINT;
const hex = (value) => `#${String(value).replace(/^#/, "")}`;

function fail(message) {
  throw new Error(message);
}

async function loadArtifactTool() {
  const explicit = process.env.CODEX_ARTIFACT_TOOL_MODULE;
  const runtimeRoot = path.join(process.env.HOME || process.cwd(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules", "@oai", "artifact-tool", "dist");
  for (const candidate of [explicit, path.join(runtimeRoot, "node", "artifact_tool.mjs"), path.join(runtimeRoot, "artifact_tool.mjs")].filter(Boolean)) {
    try {
      await fs.access(candidate);
      return import(pathToFileURL(candidate).href);
    } catch {
      // Try the next bundled-runtime location.
    }
  }
  fail("@oai/artifact-tool is unavailable; run inside Codex Desktop or set CODEX_ARTIFACT_TOOL_MODULE");
}

async function loadJsZip() {
  const explicit = process.env.CODEX_JSZIP_MODULE;
  const candidate = explicit || path.join(process.env.HOME || process.cwd(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules", "jszip", "lib", "index.js");
  try {
    const loaded = await import(pathToFileURL(candidate).href);
    return loaded.default || loaded;
  } catch {
    fail("jszip is unavailable; run inside Codex Desktop or set CODEX_JSZIP_MODULE");
  }
}

function position(geometry) {
  return { left: inch(geometry.x), top: inch(geometry.y), width: inch(geometry.w), height: inch(geometry.h) };
}

function addText(slide, font, { name, value, geometry, fontSizePt, color, bold = false, alignment = "left", verticalAlignment = "top", fill = "none", line = { style: "solid", fill: "none", width: 0 }, insets = 0 }) {
  const shape = slide.shapes.add({ geometry: "textbox", name, position: position(geometry), fill, line });
  shape.text = value;
  shape.text.style = {
    fontSize: pt(fontSizePt), typeface: font, color, bold, alignment, verticalAlignment,
    autoFit: "none", wrap: "square",
    insets: { top: inch(insets), right: inch(insets), bottom: inch(insets), left: inch(insets) },
  };
  return shape;
}

function addLine(slide, name, geometry, color, width = 1) {
  return slide.shapes.add({ geometry: "line", name, position: position(geometry), fill: "none", line: { style: "solid", fill: color, width } });
}

function addContentChrome(slide, tokens, profile, pageNumber, { includeBody = true } = {}) {
  const font = tokens.type.primaryTypeface;
  const colors = tokens.theme.colors;
  const semantic = tokens.theme.semanticPalette;
  const geometry = tokens.roleGeometry;
  slide.shapes.add({ geometry: "rect", name: "header-accent", position: position(geometry["header-accent"]), fill: hex(colors.accent1), line: { style: "solid", fill: "none", width: 0 } });
  addText(slide, font, { name: "header-text", value: "[页眉／章节]", geometry: geometry["header-text"], fontSizePt: 10, color: hex(colors.dk2), bold: true, verticalAlignment: "middle" });
  const headerMode = profile.sampleSubtitle ? tokens.headerModes["title-subtitle"] : tokens.headerModes["title-only"];
  addText(slide, font, { name: "action-title", value: profile.sampleTitle, geometry: headerMode.actionTitle, fontSizePt: tokens.type.roles.actionTitlePt, color: hex(colors.dk1), bold: true });
  if (profile.sampleSubtitle) addText(slide, font, { name: "subtitle", value: profile.sampleSubtitle, geometry: headerMode.subtitle, fontSizePt: tokens.type.roles.subtitlePt, color: hex(colors.dk2) });
  const bodyBottom = geometry["footer-divider"].y - tokens.spacing.bodyToBottomBandGapIn;
  if (includeBody) {
    addText(slide, font, {
      name: "content-body", value: "[正文由 Certified Layout Renderer 按 Slot 合同填充]",
      geometry: { x: tokens.deck.safeMarginLeftIn, y: headerMode.bodyStartY, w: tokens.deck.widthIn - tokens.deck.safeMarginLeftIn - tokens.deck.safeMarginRightIn, h: bodyBottom - headerMode.bodyStartY },
      fontSizePt: profile.profileId.startsWith("appendix") ? 10 : 14, color: hex(colors.dk2), verticalAlignment: "middle", alignment: "center",
    });
  }
  addLine(slide, "footer-divider", geometry["footer-divider"], hex(colors.accent6), 1);
  addText(slide, font, { name: "source-footnote", value: "数据来源：[填写来源、口径与日期]", geometry: geometry["source-footnote"], fontSizePt: tokens.type.roles.sourceAndPageNumberPt, color: hex(colors.dk2) });
  addText(slide, font, { name: "page-number", value: String(pageNumber), geometry: geometry["page-number"], fontSizePt: tokens.type.roles.sourceAndPageNumberPt, color: hex(colors.dk2), alignment: "right" });
  addText(slide, font, {
    name: "safe-area-note", value: "",
    geometry: { x: tokens.deck.safeMarginLeftIn, y: 0, w: tokens.deck.widthIn - tokens.deck.safeMarginLeftIn - tokens.deck.safeMarginRightIn, h: tokens.deck.heightIn },
    fontSizePt: 9, color: hex(semantic.neutralBaselineStroke), line: { style: "solid", fill: "none", width: 0 },
  });
}

function addCover(slide, tokens, profile) {
  const font = tokens.type.primaryTypeface;
  const colors = tokens.theme.colors;
  slide.shapes.add({ geometry: "rect", name: "cover-accent", position: position({ x: 0.8, y: 1.05, w: 0.08, h: 4.95 }), fill: hex(colors.accent1), line: { style: "solid", fill: "none", width: 0 } });
  addText(slide, font, { name: "action-title", value: profile.sampleTitle, geometry: { x: 1.2, y: 2.05, w: 10.4, h: 1.35 }, fontSizePt: 32, color: hex(colors.dk1), bold: true, verticalAlignment: "middle" });
  addText(slide, font, { name: "subtitle", value: profile.sampleSubtitle, geometry: { x: 1.2, y: 3.65, w: 9.4, h: 0.5 }, fontSizePt: 16, color: hex(colors.dk2) });
  addText(slide, font, { name: "cover-label", value: "KSIB MANAGEMENT REVIEW", geometry: { x: 1.2, y: 1.35, w: 5.5, h: 0.3 }, fontSizePt: 10, color: hex(colors.accent2), bold: true });
}

function addNavigator(slide, tokens, profile, pageNumber) {
  addContentChrome(slide, tokens, profile, pageNumber, { includeBody: false });
  const font = tokens.type.primaryTypeface;
  const colors = tokens.theme.colors;
  const boxes = [
    ["01", "判断", "明确需要支持的决策"],
    ["02", "证据", "用可核验材料证明判断"],
    ["03", "行动", "锁定负责人、节奏与门槛"],
  ];
  boxes.forEach(([number, title, detail], index) => {
    const x = 0.8 + index * 4.03;
    const panel = addText(slide, font, {
      name: `navigator-block-${index + 1}`, value: number, geometry: { x, y: 2.15, w: 3.68, h: 2.55 },
      fontSizePt: 12, color: hex(colors.dk2), fill: index === 0 ? hex(colors.accent3) : hex(colors.lt1),
      line: { style: "solid", fill: index === 0 ? hex(colors.accent4) : hex(colors.accent6), width: 1 }, insets: 0.22,
    });
    panel.text.set([
      [{ run: number, textStyle: { fontSize: "14pt", typeface: font, color: hex(colors.accent2), bold: true } }],
      [{ run: title, textStyle: { fontSize: "18pt", typeface: font, color: hex(colors.dk1), bold: true } }],
      [{ run: detail, textStyle: { fontSize: "12pt", typeface: font, color: hex(colors.dk2), bold: false } }],
    ]);
    panel.text.style = { ...panel.text.style, fontSize: pt(12), typeface: font, color: hex(colors.dk2), lineSpacing: 1.2 };
  });
}

function addDivider(slide, tokens, profile, appendix = false) {
  const font = tokens.type.primaryTypeface;
  const colors = tokens.theme.colors;
  addText(slide, font, { name: "divider-kicker", value: appendix ? "APPENDIX" : "SECTION", geometry: { x: 0.8, y: 1.45, w: 2.0, h: 0.3 }, fontSizePt: 10, color: hex(colors.accent2), bold: true });
  addText(slide, font, { name: "action-title", value: profile.sampleTitle, geometry: { x: 0.8, y: 2.15, w: 10.9, h: 0.85 }, fontSizePt: 28, color: hex(colors.dk1), bold: true });
  addText(slide, font, { name: "subtitle", value: profile.sampleSubtitle, geometry: { x: 0.8, y: 3.25, w: 9.5, h: 0.5 }, fontSizePt: 16, color: hex(colors.dk2) });
  addLine(slide, "divider-rule", { x: 0.8, y: 4.25, w: 3.2, h: 0 }, hex(colors.accent1), 3);
}

function applyTheme(presentation, tokens) {
  const colors = tokens.theme.colors;
  const semantic = tokens.theme.semanticPalette;
  presentation.theme.colorScheme = {
    name: tokens.theme.name,
    themeColors: {
      accent1: hex(colors.accent1), accent2: hex(colors.accent2), accent3: hex(colors.accent3), accent4: hex(colors.accent4),
      accent5: hex(semantic.contrastBase), accent6: hex(colors.accent6), bg1: hex(colors.lt1), bg2: hex(colors.lt2),
      tx1: hex(colors.dk1), tx2: hex(colors.dk2), dk1: hex(colors.dk1), lt1: hex(colors.lt1), dk2: hex(colors.dk2), lt2: hex(colors.lt2),
      hlink: hex(colors.hlink), folHlink: hex(colors.folHlink),
    },
  };
}

function xmlEscape(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function shapeByName(xml, name, transform) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(<p:sp>(?:(?!<p:sp>).)*?<p:cNvPr\\b[^>]*\\bname="${escaped}"[^>]*>?(?:(?!<p:sp>).)*?</p:sp>)`, "s");
  if (!pattern.test(xml)) fail(`shape ${name} is missing from generated layout source`);
  return xml.replace(pattern, (shape) => transform(shape));
}

function promotePlaceholder(xml, name, type, index) {
  return shapeByName(xml, name, (shape) => {
    const placeholder = `<p:ph type="${type}" idx="${index}"/>`;
    if (/<p:nvPr\s*\/>/.test(shape)) return shape.replace(/<p:nvPr\s*\/>/, `<p:nvPr>${placeholder}</p:nvPr>`);
    if (/<p:nvPr>\s*<\/p:nvPr>/.test(shape)) return shape.replace(/<p:nvPr>\s*<\/p:nvPr>/, `<p:nvPr>${placeholder}</p:nvPr>`);
    return shape.replace(/<p:nvPr>/, `<p:nvPr>${placeholder}`);
  });
}

function makeDynamicPageNumber(xml, index) {
  return shapeByName(xml, "page-number", (shape) => shape.replace(/<a:r>(.*?)<a:t>.*?<\/a:t><\/a:r>/s, (_match, runProperties) => {
    const rPr = runProperties.match(/<a:rPr\b[^>]*\/>|<a:rPr\b[^>]*>.*?<\/a:rPr>/s)?.[0] || "<a:rPr/>";
    const guid = `{00000000-0000-0000-0000-${String(index).padStart(12, "0")}}`;
    return `<a:fld id="${guid}" type="slidenum">${rPr}<a:t>${index}</a:t></a:fld>`;
  }));
}

function insertBefore(xml, closingTag, value) {
  if (!xml.includes(closingTag)) fail(`cannot find ${closingTag}`);
  return xml.replace(closingTag, `${value}${closingTag}`);
}

function removeSlidesForTemplate(zip, contentTypes, presentationXml, presentationRels, appXml) {
  for (const name of Object.keys(zip.files)) {
    if (/^ppt\/(slides|notesSlides|comments)\//.test(name)) zip.remove(name);
  }
  const nextContentTypes = contentTypes.replace(/<Override\b[^>]*PartName="\/ppt\/(?:slides|notesSlides|comments)\/[^>]+\/>/g, "");
  const nextPresentation = presentationXml.replace(/<p:sldIdLst>.*?<\/p:sldIdLst>/s, "");
  const nextRels = presentationRels.replace(/<Relationship\b[^>]*Type="[^"]+\/(?:slide|commentAuthors)"[^>]*\/>/g, "");
  const nextApp = appXml.replace(/<Slides>\d+<\/Slides>/, "<Slides>0</Slides>").replace(/<Notes>\d+<\/Notes>/, "<Notes>0</Notes>");
  return { contentTypes: nextContentTypes, presentationXml: nextPresentation, presentationRels: nextRels, appXml: nextApp };
}

async function promoteLayouts(basePath, libraryPath, templatePath, contract, tokens, JSZip) {
  const buffer = await fs.readFile(basePath);
  const zip = await JSZip.loadAsync(buffer);
  let contentTypes = await zip.file("[Content_Types].xml").async("string");
  let masterXml = await zip.file("ppt/slideMasters/slideMaster1.xml").async("string");
  let masterRels = await zip.file("ppt/slideMasters/_rels/slideMaster1.xml.rels").async("string");
  let themePath = Object.keys(zip.files).find((name) => /^ppt\/slideMasters\/theme\/theme\d+\.xml$/.test(name));
  if (!themePath) themePath = Object.keys(zip.files).find((name) => /^ppt\/theme\/theme\d+\.xml$/.test(name));
  if (!themePath) fail("generated presentation has no theme part");

  for (const [profileIndex, profile] of contract.profiles.entries()) {
    const slideXml = await zip.file(`ppt/slides/slide${profileIndex + 1}.xml`).async("string");
    const spTree = slideXml.match(/<p:spTree>.*?<\/p:spTree>/s)?.[0];
    if (!spTree) fail(`slide ${profileIndex + 1} has no shape tree`);
    let layoutXml = `<?xml version="1.0" encoding="utf-8"?><p:sldLayout type="${xmlEscape(profile.layoutType)}" preserve="1" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="${xmlEscape(profile.layoutName)}">${spTree}</p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr><p:hf hdr="1" ftr="1" sldNum="1"/></p:sldLayout>`;
    const placeholderTypes = { "action-title": profile.profileId === "cover" ? "ctrTitle" : "title", subtitle: "subTitle", "content-body": "body", "header-text": "hdr", "source-footnote": "ftr" };
    profile.placeholders.forEach((name, index) => {
      layoutXml = promotePlaceholder(layoutXml, name, placeholderTypes[name] || "body", index + 1);
    });
    if (profile.profileId.includes("content") || profile.profileId.startsWith("appendix-title") || profile.profileId === "navigator") layoutXml = makeDynamicPageNumber(layoutXml, profileIndex + 1);
    const partIndex = profileIndex + 2;
    const relationId = `rIdKSIBLayout${String(profileIndex + 1).padStart(2, "0")}`;
    zip.file(`ppt/slideLayouts/slideLayout${partIndex}.xml`, layoutXml);
    zip.file(`ppt/slideLayouts/_rels/slideLayout${partIndex}.xml.rels`, `<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>`);
    contentTypes = insertBefore(contentTypes, "</Types>", `<Override PartName="/ppt/slideLayouts/slideLayout${partIndex}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>`);
    masterRels = insertBefore(masterRels, "</Relationships>", `<Relationship Id="${relationId}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="/ppt/slideLayouts/slideLayout${partIndex}.xml"/>`);
    masterXml = masterXml.replace("</p:sldLayoutIdLst>", `<p:sldLayoutId id="${2147483650 + profileIndex}" r:id="${relationId}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></p:sldLayoutIdLst>`);
  }

  let themeXml = await zip.file(themePath).async("string");
  themeXml = themeXml.replace(/<a:fontScheme\b[^>]*name="[^"]*"/, `<a:fontScheme name="${xmlEscape(tokens.theme.fontSchemeName)}"`);
  themeXml = themeXml.replace(/<a:(latin|ea|cs)\b[^>]*typeface="[^"]*"\s*\/>/g, (_match, tag) => `<a:${tag} typeface="${xmlEscape(tokens.type.primaryTypeface)}"/>`);
  zip.file(themePath, themeXml);
  zip.file("[Content_Types].xml", contentTypes);
  zip.file("ppt/slideMasters/slideMaster1.xml", masterXml);
  zip.file("ppt/slideMasters/_rels/slideMaster1.xml.rels", masterRels);
  const libraryBuffer = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE", compressionOptions: { level: 9 } });
  await fs.writeFile(libraryPath, libraryBuffer);

  const templateZip = await JSZip.loadAsync(libraryBuffer);
  let templateContentTypes = await templateZip.file("[Content_Types].xml").async("string");
  let presentationXml = await templateZip.file("ppt/presentation.xml").async("string");
  let presentationRels = await templateZip.file("ppt/_rels/presentation.xml.rels").async("string");
  let appXml = await templateZip.file("docProps/app.xml").async("string");
  ({ contentTypes: templateContentTypes, presentationXml, presentationRels, appXml } = removeSlidesForTemplate(templateZip, templateContentTypes, presentationXml, presentationRels, appXml));
  templateContentTypes = templateContentTypes.replace(/application\/vnd\.openxmlformats-officedocument\.presentationml\.presentation\.main\+xml/, "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml");
  templateZip.file("[Content_Types].xml", templateContentTypes);
  templateZip.file("ppt/presentation.xml", presentationXml);
  templateZip.file("ppt/_rels/presentation.xml.rels", presentationRels);
  templateZip.file("docProps/app.xml", appXml);
  const templateBuffer = await templateZip.generateAsync({ type: "nodebuffer", compression: "DEFLATE", compressionOptions: { level: 9 } });
  await fs.writeFile(templatePath, templateBuffer);
  return { libraryBuffer, templateBuffer };
}

async function main() {
  const [contract, tokens, artifactTool, JSZip] = await Promise.all([
    fs.readFile(CONTRACT_PATH, "utf8").then(JSON.parse),
    fs.readFile(TOKENS_PATH, "utf8").then(JSON.parse),
    loadArtifactTool(),
    loadJsZip(),
  ]);
  const { Presentation, PresentationFile } = artifactTool;
  await fs.mkdir(TEMPLATE_DIR, { recursive: true });
  await fs.mkdir(TEMP_DIR, { recursive: true });
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  applyTheme(presentation, tokens);
  for (const [index, profile] of contract.profiles.entries()) {
    const slide = presentation.slides.add();
    slide.background.fill = hex(tokens.theme.colors.lt1);
    if (profile.profileId === "cover") addCover(slide, tokens, profile);
    else if (profile.profileId === "navigator") addNavigator(slide, tokens, profile, index + 1);
    else if (profile.profileId === "section-divider") addDivider(slide, tokens, profile, false);
    else if (profile.profileId === "appendix-divider") addDivider(slide, tokens, profile, true);
    else addContentChrome(slide, tokens, profile, index + 1);
    slide.speakerNotes.textFrame.setText(`[Template Profile]\n- ${profile.profileId}\n- ${profile.layoutName}\n- Generated from ${tokens.schemaVersion}`);
  }
  const basePath = path.join(TEMP_DIR, "KSIB_MBB_Master_base.pptx");
  const baseFile = await PresentationFile.exportPptx(presentation);
  await baseFile.save(basePath);
  const libraryPath = path.join(SKILL_ROOT, contract.layoutLibraryFile);
  const templatePath = path.join(SKILL_ROOT, contract.templateFile);
  const { libraryBuffer, templateBuffer } = await promoteLayouts(basePath, libraryPath, templatePath, contract, tokens, JSZip);
  const manifest = {
    schemaVersion: "ksib-powerpoint-master-build/1.0",
    templateVersion: contract.templateVersion,
    designTokensVersion: tokens.schemaVersion,
    generatedAt: new Date().toISOString(),
    profileCount: contract.profiles.length,
    files: {
      [path.basename(templatePath)]: { bytes: templateBuffer.length, sha256: crypto.createHash("sha256").update(templateBuffer).digest("hex") },
      [path.basename(libraryPath)]: { bytes: libraryBuffer.length, sha256: crypto.createHash("sha256").update(libraryBuffer).digest("hex") },
    },
  };
  await fs.writeFile(path.join(TEMPLATE_DIR, "template-manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ passed: true, ...manifest }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
