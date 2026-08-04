#!/usr/bin/env node

import fs from "node:fs/promises";
import { readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const CONTENT_SCHEMA = "ksib-certified-render-content/2.0";
const PLAN_SCHEMA = "ksib-render-plan/1.0";
const PX_PER_INCH = 96;
const PX_PER_POINT = 96 / 72;
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SKILL_ROOT = path.resolve(SCRIPT_DIR, "..");
const DESIGN_TOKENS = JSON.parse(readFileSync(path.join(SKILL_ROOT, "references", "design-tokens.json"), "utf8"));
const MASTER_CONTRACT = JSON.parse(readFileSync(path.join(SKILL_ROOT, "references", "powerpoint-master-contract.json"), "utf8"));
const tokenHex = (value) => `#${String(value).replace(/^#/, "")}`;
const FONT = DESIGN_TOKENS.type.primaryTypeface;
const THEME_COLORS = DESIGN_TOKENS.theme.colors;
const SEMANTIC_COLORS = DESIGN_TOKENS.theme.semanticPalette;
const COLORS = {
  primary: tokenHex(THEME_COLORS.accent1),
  primaryDark: tokenHex(THEME_COLORS.accent2),
  primaryPale: tokenHex(THEME_COLORS.accent3),
  primaryLight: tokenHex(THEME_COLORS.accent4),
  contrast: tokenHex(SEMANTIC_COLORS.contrastBase),
  text: tokenHex(THEME_COLORS.dk1),
  textMuted: tokenHex(THEME_COLORS.dk2),
  series: tokenHex(SEMANTIC_COLORS.neutralSeries),
  divider: tokenHex(THEME_COLORS.accent6),
  surface: tokenHex(THEME_COLORS.lt2),
  white: tokenHex(THEME_COLORS.lt1),
};

const inch = (value) => value * PX_PER_INCH;
const pt = (value) => value * PX_PER_POINT;

function fail(message) {
  throw new Error(message);
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) fail(`Unexpected argument: ${token}`);
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

async function loadArtifactTool() {
  const explicit = process.env.CODEX_ARTIFACT_TOOL_MODULE;
  const runtimeRoot = path.join(process.env.HOME || process.cwd(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules", "@oai", "artifact-tool", "dist");
  const candidates = [explicit, path.join(runtimeRoot, "node", "artifact_tool.mjs"), path.join(runtimeRoot, "artifact_tool.mjs")].filter(Boolean);
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return import(pathToFileURL(candidate).href);
    } catch {
      // Continue to the next verified bundled-runtime location.
    }
  }
  fail("@oai/artifact-tool is unavailable; run inside Codex Desktop or set CODEX_ARTIFACT_TOOL_MODULE");
}

function text(value, label, maximum) {
  if (typeof value !== "string" || !value.trim()) fail(`${label} is required`);
  const result = value.trim();
  if (/\r|\n/.test(result)) fail(`${label} cannot contain line breaks`);
  if (maximum && [...result].length > maximum) fail(`${label} exceeds ${maximum} characters`);
  return result;
}

function array(value, label, minimum, maximum) {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) fail(`${label} must contain ${minimum}-${maximum} items`);
  return value;
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(`${label} is required`);
  return value;
}

function expectedBySlot(planSlide) {
  return Object.fromEntries(planSlide.expectedObjects.map((item) => [item.slotId, item]));
}

function requireSlots(planSlide, ids) {
  const slots = expectedBySlot(planSlide);
  for (const id of ids) if (!slots[id]) fail(`slide ${planSlide.slide} render plan is missing ${id}`);
  return slots;
}

function assertItemCount(expected, actual, label) {
  if (expected?.itemCount != null && expected.itemCount !== actual) fail(`${label} must contain exactly ${expected.itemCount} rendered paragraphs/items`);
}

function validateChart(chart, label) {
  object(chart, label);
  if (chart.componentId !== "native-chart") fail(`${label}.componentId must be native-chart`);
  const categories = array(chart.categories, `${label}.categories`, 2, 8);
  const values = array(chart.values, `${label}.values`, categories.length, categories.length);
  categories.forEach((value, index) => text(value, `${label}.categories[${index}]`, 18));
  if (values.some((value) => typeof value !== "number" || !Number.isFinite(value))) fail(`${label}.values must be finite numbers`);
  text(chart.seriesName, `${label}.seriesName`, 24);
  if (!Number.isInteger(chart.focusIndex) || chart.focusIndex < 0 || chart.focusIndex >= values.length) fail(`${label}.focusIndex is outside the data range`);
  if (!["integer", "percent-0"].includes(chart.valueFormat)) fail(`${label}.valueFormat is unsupported`);
  if (chart.valueFormat === "percent-0" && values.some((value) => value < 0 || value > 1)) fail(`${label}.percent-0 values must be between 0 and 1`);
}

function validateTable(table, expected, label) {
  object(table, label);
  if (table.componentId !== "native-table") fail(`${label}.componentId must be native-table`);
  const headers = array(table.headers, `${label}.headers`, 2, 6);
  headers.forEach((value, index) => text(value, `${label}.headers[${index}]`, 18));
  const rows = array(table.rows, `${label}.rows`, 1, 6);
  rows.forEach((row, rowIndex) => {
    if (!Array.isArray(row) || row.length !== headers.length) fail(`${label}.rows[${rowIndex}] must match header count`);
    row.forEach((value, columnIndex) => text(String(value), `${label}.rows[${rowIndex}][${columnIndex}]`, 36));
  });
  assertItemCount(expected, (rows.length + 1) * headers.length, label);
}

function validateBlock(block, expected, label, limits = {}) {
  object(block, label);
  text(block.title, `${label}.title`, limits.title ?? 28);
  const items = array(block.items ?? [], `${label}.items`, limits.minItems ?? 0, limits.maxItems ?? 5);
  items.forEach((value, index) => text(value, `${label}.items[${index}]`, limits.item ?? 56));
  assertItemCount(expected, items.length + 1, label);
}

function validateInsight(body, slots, label) {
  text(body.insightTitle, `${label}.insightTitle`, 18);
  text(body.insightLead, `${label}.insightLead`, 60);
  const items = array(body.insightItems, `${label}.insightItems`, 2, 3);
  items.forEach((value, index) => text(value, `${label}.insightItems[${index}]`, 48));
  assertItemCount(slots.insightItems, items.length, `${label}.insightItems`);
}

const LAYOUT_VALIDATORS = {
  executiveSummary(planSlide, body) {
    const slots = requireSlots(planSlide, ["decisionLead", "pillar1", "pillar2", "pillar3", "decisionAsk"]);
    text(body.decisionLead, "decisionLead", 90);
    const pillars = array(body.pillars, "pillars", 3, 3);
    pillars.forEach((value, index) => validateBlock(value, slots[`pillar${index + 1}`], `pillars[${index}]`, { minItems: 1, maxItems: 3, item: 52 }));
    validateBlock(body.decisionAsk, slots.decisionAsk, "decisionAsk", { minItems: 0, maxItems: 1, item: 70 });
  },
  singleExhibit(planSlide, body) {
    const slots = requireSlots(planSlide, ["mainExhibit"]);
    if (slots.mainExhibit.componentId === "native-chart") validateChart(body.mainExhibit, "mainExhibit");
    else validateTable(body.mainExhibit, slots.mainExhibit, "mainExhibit");
  },
  evidenceInsight(planSlide, body) {
    const slots = requireSlots(planSlide, ["mainExhibit", "insightPanel", "insightTitle", "insightLead", "insightItems"]);
    validateChart(body.mainExhibit, "mainExhibit");
    validateInsight(body, slots, "slotContent");
  },
  tableInsight(planSlide, body) {
    const slots = requireSlots(planSlide, ["mainExhibit", "insightPanel", "insightTitle", "insightLead", "insightItems"]);
    validateTable(body.mainExhibit, slots.mainExhibit, "mainExhibit");
    validateInsight(body, slots, "slotContent");
  },
  sideBySide(planSlide, body) {
    const slots = requireSlots(planSlide, ["leftColumn", "divider", "rightColumn"]);
    const columns = array(body.columns, "columns", 2, 2);
    validateBlock(columns[0], slots.leftColumn, "columns[0]", { minItems: 2, maxItems: 5 });
    validateBlock(columns[1], slots.rightColumn, "columns[1]", { minItems: 2, maxItems: 5 });
  },
  structuredComparison(planSlide, body) {
    const expected = Object.values(expectedBySlot(planSlide)).filter((item) => item.slotId.startsWith("column"));
    const columns = array(body.columns, "columns", expected.length, expected.length);
    columns.forEach((value, index) => validateBlock(value, expected[index], `columns[${index}]`, { minItems: 2, maxItems: expected.length === 4 ? 4 : 5, item: 48 }));
  },
  matrix2x2(planSlide, body) {
    const slots = requireSlots(planSlide, ["yAxisLabel", "quadrant1", "quadrant2", "quadrant3", "quadrant4", "xAxisLabel"]);
    text(body.xAxisLabel, "xAxisLabel", 28);
    text(body.yAxisLabel, "yAxisLabel", 28);
    const quadrants = array(body.quadrants, "quadrants", 4, 4);
    quadrants.forEach((value, index) => validateBlock(value, slots[`quadrant${index + 1}`], `quadrants[${index}]`, { minItems: 1, maxItems: 3, item: 44 }));
    if (body.focusIndex != null && (!Number.isInteger(body.focusIndex) || body.focusIndex < 0 || body.focusIndex > 3)) fail("focusIndex must be 0-3");
  },
  issueTree(planSlide, body) {
    const slots = requireSlots(planSlide, ["root", "branch1", "branch2", "branch3", "connector1", "connector2", "connector3"]);
    validateBlock(body.root, slots.root, "root", { minItems: 0, maxItems: 1, item: 40 });
    const branches = array(body.branches, "branches", 3, 3);
    branches.forEach((value, index) => validateBlock(value, slots[`branch${index + 1}`], `branches[${index}]`, { minItems: 1, maxItems: 3, item: 52 }));
  },
  problemSolutionMap(planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const rows = array(body.rows, "rows", 3, 3);
    rows.forEach((row, index) => {
      for (const field of ["problem", "action", "outcome"]) validateBlock(row[field], slots[`${field}${index + 1}`], `rows[${index}].${field}`, { minItems: 0, maxItems: 1, item: 46 });
    });
  },
  processValueChain(planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const stageSlots = Object.values(slots).filter((item) => item.slotId.startsWith("stage"));
    const stages = array(body.stages, "stages", stageSlots.length, stageSlots.length);
    stages.forEach((value, index) => validateBlock(value, stageSlots[index], `stages[${index}]`, { minItems: 1, maxItems: 3, item: 48 }));
    if (body.focusIndex != null && (!Number.isInteger(body.focusIndex) || body.focusIndex < 0 || body.focusIndex >= stages.length)) fail("focusIndex is outside stages");
  },
  phasePlaybook(planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const labels = array(body.logicLabels, "logicLabels", 3, 3);
    labels.forEach((value, index) => text(value, `logicLabels[${index}]`, 16));
    assertItemCount(slots.logicLabels, labels.length, "logicLabels");
    const phaseSlots = Object.values(slots).filter((item) => item.slotId.startsWith("phase"));
    const phases = array(body.phases, "phases", phaseSlots.length, phaseSlots.length);
    phases.forEach((phase, index) => {
      for (const field of ["title", "logic", "criterion", "action"]) text(phase[field], `phases[${index}].${field}`, field === "title" ? 18 : 46);
      assertItemCount(phaseSlots[index], 4, `phases[${index}]`);
    });
  },
  recommendationRoadmap(planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const labels = array(body.logicLabels, "logicLabels", 3, 3);
    labels.forEach((value, index) => text(value, `logicLabels[${index}]`, 16));
    assertItemCount(slots.logicLabels, labels.length, "logicLabels");
    const phaseSlots = Object.values(slots).filter((item) => item.slotId.startsWith("phase"));
    const phases = array(body.phases, "phases", phaseSlots.length, phaseSlots.length);
    phases.forEach((phase, index) => {
      for (const field of ["title", "recommendation", "milestone", "owner"]) text(phase[field], `phases[${index}].${field}`, field === "title" ? 18 : 46);
      assertItemCount(phaseSlots[index], 4, `phases[${index}]`);
    });
  },
};

export function validateCertifiedRenderInput(plan, content) {
  if (plan?.schemaVersion !== PLAN_SCHEMA) fail(`render plan schema must be ${PLAN_SCHEMA}`);
  if (content?.schemaVersion !== CONTENT_SCHEMA) fail(`content schema must be ${CONTENT_SCHEMA}`);
  if (!Array.isArray(plan.slides) || !plan.slides.length) fail("render plan slides[] must be non-empty");
  if (!Array.isArray(content.slides) || content.slides.length !== plan.slides.length) fail("content slides[] must exactly cover the render plan");
  for (const [index, planSlide] of plan.slides.entries()) {
    const slide = content.slides[index];
    if (planSlide.slide !== index + 1 || slide?.slide !== index + 1) fail(`slide sequence must be contiguous at ${index + 1}`);
    if (slide.storylineId !== planSlide.storylineId) fail(`slide ${index + 1} storylineId does not match the render plan`);
    if (slide.layoutId !== planSlide.layoutId) fail(`slide ${index + 1} layoutId does not match the render plan`);
    if (!LAYOUT_VALIDATORS[planSlide.layoutId]) fail(`slide ${index + 1} uses unsupported layout ${planSlide.layoutId}`);
    text(slide.header, `slides[${index}].header`, 48);
    text(slide.title, `slides[${index}].title`, 38);
    text(slide.source, `slides[${index}].source`, 180);
    if (planSlide.headerProfile === "content-title-subtitle") text(slide.subtitle, `slides[${index}].subtitle`, 96);
    if (planSlide.headerProfile === "content-title-only" && slide.subtitle != null && String(slide.subtitle).trim()) fail(`slides[${index}].subtitle is forbidden for title-only`);
    const body = object(slide.slotContent, `slides[${index}].slotContent`);
    LAYOUT_VALIDATORS[planSlide.layoutId](planSlide, body);
  }
  return true;
}

function position(geometry) {
  return { left: inch(geometry.x), top: inch(geometry.y), width: inch(geometry.w), height: inch(geometry.h) };
}

function addText(slide, { name, value, geometry, fontSizePt, color = COLORS.text, bold = false, alignment = "left", verticalAlignment = "top", fill = "none", line = { style: "solid", fill: "none", width: 0 }, insets = 0 }) {
  const shape = slide.shapes.add({ geometry: "textbox", name, position: position(geometry), fill, line });
  shape.text = value;
  shape.text.style = {
    fontSize: pt(fontSizePt), typeface: FONT, color, bold, alignment, verticalAlignment,
    autoFit: "none", wrap: "square",
    insets: typeof insets === "number" ? { top: inch(insets), right: inch(insets), bottom: inch(insets), left: inch(insets) } : insets,
  };
  return shape;
}

function setParagraphs(shape, paragraphs, { fontSizePt = 12, titleSizePt = 14, titleColor = COLORS.text, itemColor = COLORS.text, lineSpacing = 1.2, prefixes = true, firstIsTitle = true } = {}) {
  shape.text.set(paragraphs.map((value, index) => [{
    run: !prefixes || (firstIsTitle && index === 0) ? value : `${String(firstIsTitle ? index : index + 1).padStart(2, "0")}｜${value}`,
    textStyle: { fontSize: `${firstIsTitle && index === 0 ? titleSizePt : fontSizePt}pt`, typeface: FONT, color: firstIsTitle && index === 0 ? titleColor : itemColor, bold: firstIsTitle && index === 0 },
  }]));
  shape.text.style = { ...shape.text.style, fontSize: pt(fontSizePt), typeface: FONT, color: itemColor, lineSpacing };
}

function addCompositePanel(slide, expected, block, { fill = COLORS.white, lineColor = COLORS.divider, focus = false, titleColor = COLORS.text, fontSizePt = 12, titleSizePt = 14, prefixes = true } = {}) {
  const shape = addText(slide, {
    name: expected.objectName,
    value: block.title,
    geometry: expected.geometry,
    fontSizePt,
    fill: focus ? COLORS.primaryPale : fill,
    line: { style: "solid", fill: focus ? COLORS.primaryLight : lineColor, width: 1 },
    insets: 0.15,
  });
  setParagraphs(shape, [block.title, ...(block.items ?? [])], { fontSizePt, titleSizePt, titleColor: focus ? COLORS.primaryDark : titleColor, prefixes });
  return shape;
}

function addChrome(slide, content, planSlide) {
  const roleGeometry = DESIGN_TOKENS.roleGeometry;
  const headerMode = DESIGN_TOKENS.headerModes[planSlide.headerProfile === "content-title-subtitle" ? "title-subtitle" : "title-only"];
  const roles = DESIGN_TOKENS.type.roles;
  slide.shapes.add({ geometry: "rect", name: "header-accent", position: position(roleGeometry["header-accent"]), fill: COLORS.primary, line: { style: "solid", fill: "none", width: 0 } });
  addText(slide, { name: "header-text", value: content.header, geometry: roleGeometry["header-text"], fontSizePt: 10, color: COLORS.textMuted, bold: true, verticalAlignment: "middle" });
  addText(slide, { name: "action-title", value: content.title, geometry: headerMode.actionTitle, fontSizePt: roles.actionTitlePt, bold: true });
  if (planSlide.headerProfile === "content-title-subtitle") addText(slide, { name: "subtitle", value: content.subtitle, geometry: headerMode.subtitle, fontSizePt: roles.subtitlePt, color: COLORS.textMuted });
  slide.shapes.add({ geometry: "line", name: "footer-divider", position: position(roleGeometry["footer-divider"]), fill: "none", line: { style: "solid", fill: COLORS.divider, width: 1 } });
  addText(slide, { name: "source-footnote", value: content.source, geometry: roleGeometry["source-footnote"], fontSizePt: roles.sourceAndPageNumberPt, color: COLORS.textMuted });
  addText(slide, { name: "page-number", value: String(content.slide), geometry: roleGeometry["page-number"], fontSizePt: roles.sourceAndPageNumberPt, color: COLORS.textMuted, alignment: "right" });
}

function addNativeChart(slide, spec, expected) {
  const formatCode = spec.valueFormat === "percent-0" ? "0%" : "0";
  const chart = slide.charts.add("bar", {
    position: position(expected.geometry),
    categories: spec.categories,
    series: [{
      name: spec.seriesName,
      values: spec.values,
      valuesFormatCode: formatCode,
      fill: COLORS.series,
      points: [{ idx: spec.focusIndex, fill: COLORS.primary }],
      dataLabelOverrides: spec.values.map((_, index) => ({ idx: index, showValue: true, position: "outEnd", textStyle: { fill: index === spec.focusIndex ? COLORS.primaryDark : COLORS.textMuted, fontSize: pt(index === spec.focusIndex ? 12 : 10), bold: true } })),
    }],
    hasLegend: false,
    barOptions: { direction: "bar", grouping: "clustered", gapWidth: 78 },
    chartFill: COLORS.white,
    chartLine: { style: "solid", fill: "none", width: 0 },
    plotAreaFill: COLORS.white,
    plotAreaLine: { style: "solid", fill: "none", width: 0 },
    xAxis: { visible: true, tickLabelPosition: "nextTo", textStyle: { fill: COLORS.textMuted, fontSize: pt(10) }, line: { style: "solid", fill: "none", width: 0 }, majorGridlines: null },
    yAxis: { visible: false, numberFormatCode: formatCode, tickLabelPosition: "none", line: { style: "solid", fill: "none", width: 0 }, majorGridlines: null },
    dataLabels: { showValue: true, position: "outEnd", textStyle: { fill: COLORS.textMuted, fontSize: pt(10), bold: true } },
  });
  chart.data.name = expected.objectName;
  return chart;
}

function setCellRules(cell, { topFill = null, topWidth = 0, bottomFill = null, bottomWidth = 0 } = {}) {
  for (const side of ["left", "right", "top", "bottom"]) cell.borders[side].visible = false;
  if (topFill && topWidth > 0) { cell.borders.top.visible = true; cell.borders.top.fill = topFill; cell.borders.top.width = topWidth; }
  if (bottomFill && bottomWidth > 0) { cell.borders.bottom.visible = true; cell.borders.bottom.fill = bottomFill; cell.borders.bottom.width = bottomWidth; }
}

function addNativeTable(slide, spec, expected) {
  const values = [spec.headers, ...spec.rows].map((row) => row.map(String));
  const columns = spec.headers.length;
  const table = slide.tables.add({
    rows: values.length,
    columns,
    left: inch(expected.geometry.x), top: inch(expected.geometry.y), width: inch(expected.geometry.w), height: inch(expected.geometry.h),
    columnWidths: Array.from({ length: columns }, () => inch(expected.geometry.w / columns)),
    values,
  });
  table.data.name = expected.objectName;
  const all = table.cells.block({ row: 0, column: 0, rowCount: values.length, columnCount: columns });
  all.fill = COLORS.white;
  all.textStyle.fontSize = pt(12);
  all.textStyle.color = COLORS.text;
  const header = table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: columns });
  header.textStyle.fontSize = pt(12);
  header.textStyle.bold = true;
  for (let row = 0; row < values.length; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const cell = table.getCell(row, column);
      cell.text.typeface = FONT;
      cell.textStyle.alignment = column === 0 ? "left" : "center";
      cell.margins = { top: inch(0.08), right: inch(0.1), bottom: inch(0.08), left: inch(0.1) };
      cell.anchor = "middle";
      setCellRules(cell, { topFill: row === 0 ? COLORS.primary : null, topWidth: row === 0 ? 2 : 0, bottomFill: row === 0 ? COLORS.divider : null, bottomWidth: row === 0 ? 1 : 0 });
    }
  }
  if (spec.focusCell && Number.isInteger(spec.focusCell.row) && Number.isInteger(spec.focusCell.column)) {
    const cell = table.getCell(spec.focusCell.row + 1, spec.focusCell.column);
    if (cell) { cell.fill = COLORS.primaryPale; cell.textStyle.color = COLORS.primaryDark; cell.textStyle.bold = true; }
  }
  return table;
}

function addInsight(slide, body, slots) {
  slide.shapes.add({ geometry: "rect", name: slots.insightPanel.objectName, position: position(slots.insightPanel.geometry), fill: COLORS.primaryPale, line: { style: "solid", fill: COLORS.primaryLight, width: 1 } });
  addText(slide, { name: slots.insightTitle.objectName, value: body.insightTitle, geometry: slots.insightTitle.geometry, fontSizePt: slots.insightTitle.expectedFontSizePt, color: COLORS.primaryDark, bold: true });
  addText(slide, { name: slots.insightLead.objectName, value: body.insightLead, geometry: slots.insightLead.geometry, fontSizePt: slots.insightLead.expectedFontSizePt, bold: true });
  const list = addText(slide, { name: slots.insightItems.objectName, value: body.insightItems[0], geometry: slots.insightItems.geometry, fontSizePt: slots.insightItems.expectedFontSizePt });
  setParagraphs(list, body.insightItems, { fontSizePt: slots.insightItems.expectedFontSizePt, titleSizePt: slots.insightItems.expectedFontSizePt, prefixes: true, firstIsTitle: false });
}

function addDivider(slide, expected) {
  return slide.shapes.add({ geometry: "line", name: expected.objectName, position: position(expected.geometry), fill: "none", line: { style: "solid", fill: COLORS.divider, width: 1 } });
}

function connect(slide, source, target, expected, options = {}) {
  const arrow = options.arrow === false ? {} : { tail: { type: "arrow", width: "sm", length: "sm" } };
  const connector = slide.shapes.connect(source, target, {
    kind: options.kind ?? "straight", fromSide: options.fromSide ?? "right", toSide: options.toSide ?? "left",
    line: { style: "solid", fill: COLORS.textMuted, width: 1.5 }, ...arrow,
  });
  connector.data.name = expected.objectName;
  return connector;
}

const LAYOUT_RENDERERS = {
  executiveSummary(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    addText(slide, { name: slots.decisionLead.objectName, value: body.decisionLead, geometry: slots.decisionLead.geometry, fontSizePt: 18, bold: true, fill: COLORS.primaryPale, line: { style: "solid", fill: COLORS.primaryLight, width: 1 }, insets: 0.15, verticalAlignment: "middle" });
    body.pillars.forEach((pillar, index) => addCompositePanel(slide, slots[`pillar${index + 1}`], pillar, { focus: index === (body.focusIndex ?? 0), fontSizePt: 12, titleSizePt: 14 }));
    addCompositePanel(slide, slots.decisionAsk, body.decisionAsk, { fill: COLORS.surface, fontSizePt: 12, titleSizePt: 14, prefixes: false });
  },
  singleExhibit(slide, planSlide, body) {
    const expected = expectedBySlot(planSlide).mainExhibit;
    if (expected.componentId === "native-chart") addNativeChart(slide, body.mainExhibit, expected);
    else addNativeTable(slide, body.mainExhibit, expected);
  },
  evidenceInsight(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    addNativeChart(slide, body.mainExhibit, slots.mainExhibit);
    addInsight(slide, body, slots);
  },
  tableInsight(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    addNativeTable(slide, body.mainExhibit, slots.mainExhibit);
    addInsight(slide, body, slots);
  },
  sideBySide(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    addCompositePanel(slide, slots.leftColumn, body.columns[0], { focus: body.focusIndex === 0, fontSizePt: 12, titleSizePt: 16 });
    addDivider(slide, slots.divider);
    addCompositePanel(slide, slots.rightColumn, body.columns[1], { focus: body.focusIndex === 1, fontSizePt: 12, titleSizePt: 16 });
  },
  structuredComparison(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    body.columns.forEach((column, index) => addCompositePanel(slide, slots[`column${index + 1}`], column, { focus: body.focusIndex === index, fontSizePt: 12, titleSizePt: 14 }));
  },
  matrix2x2(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    addText(slide, { name: slots.yAxisLabel.objectName, value: body.yAxisLabel, geometry: slots.yAxisLabel.geometry, fontSizePt: 12, color: COLORS.textMuted, bold: true });
    body.quadrants.forEach((quadrant, index) => addCompositePanel(slide, slots[`quadrant${index + 1}`], quadrant, { focus: body.focusIndex === index, fontSizePt: 12, titleSizePt: 14 }));
    addText(slide, { name: slots.xAxisLabel.objectName, value: body.xAxisLabel, geometry: slots.xAxisLabel.geometry, fontSizePt: 12, color: COLORS.textMuted, bold: true, alignment: "right" });
  },
  issueTree(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const root = addCompositePanel(slide, slots.root, body.root, { focus: true, fontSizePt: 12, titleSizePt: 14, prefixes: false });
    const branches = body.branches.map((branch, index) => addCompositePanel(slide, slots[`branch${index + 1}`], branch, { fontSizePt: 12, titleSizePt: 14 }));
    branches.forEach((branch, index) => connect(slide, root, branch, slots[`connector${index + 1}`], { kind: "elbow", arrow: false }));
  },
  problemSolutionMap(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    body.rows.forEach((row, index) => {
      addCompositePanel(slide, slots[`problem${index + 1}`], row.problem, { fill: COLORS.surface, fontSizePt: 12, titleSizePt: 14, prefixes: false });
      addCompositePanel(slide, slots[`action${index + 1}`], row.action, { focus: true, fontSizePt: 12, titleSizePt: 14, prefixes: false });
      addCompositePanel(slide, slots[`outcome${index + 1}`], row.outcome, { fontSizePt: 12, titleSizePt: 14, prefixes: false });
    });
  },
  processValueChain(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const stages = body.stages.map((stage, index) => addCompositePanel(slide, slots[`stage${index + 1}`], stage, { focus: body.focusIndex === index, fontSizePt: 12, titleSizePt: 14 }));
    for (let index = 0; index < stages.length - 1; index += 1) connect(slide, stages[index], stages[index + 1], slots[`connector${index + 1}`]);
  },
  phasePlaybook(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const labels = addText(slide, { name: slots.logicLabels.objectName, value: body.logicLabels[0], geometry: slots.logicLabels.geometry, fontSizePt: 12, color: COLORS.textMuted, bold: true });
    setParagraphs(labels, body.logicLabels, { fontSizePt: 12, titleSizePt: 12, prefixes: false, firstIsTitle: false, titleColor: COLORS.textMuted, itemColor: COLORS.textMuted, lineSpacing: 1.2 });
    body.phases.forEach((phase, index) => addCompositePanel(slide, slots[`phase${index + 1}`], { title: phase.title, items: [phase.logic, phase.criterion, phase.action] }, { focus: index === (body.focusIndex ?? 0), fontSizePt: 12, titleSizePt: 14, prefixes: false }));
  },
  recommendationRoadmap(slide, planSlide, body) {
    const slots = expectedBySlot(planSlide);
    const labels = addText(slide, { name: slots.logicLabels.objectName, value: body.logicLabels[0], geometry: slots.logicLabels.geometry, fontSizePt: 12, color: COLORS.textMuted, bold: true });
    setParagraphs(labels, body.logicLabels, { fontSizePt: 12, titleSizePt: 12, prefixes: false, firstIsTitle: false, titleColor: COLORS.textMuted, itemColor: COLORS.textMuted, lineSpacing: 1.2 });
    body.phases.forEach((phase, index) => addCompositePanel(slide, slots[`phase${index + 1}`], { title: phase.title, items: [phase.recommendation, phase.milestone, phase.owner] }, { focus: index === (body.focusIndex ?? body.phases.length - 1), fontSizePt: 12, titleSizePt: 14, prefixes: false }));
  },
};

function applyTheme(presentation) {
  presentation.theme.colorScheme = {
    name: DESIGN_TOKENS.theme.name,
    themeColors: {
      accent1: COLORS.primary, accent2: COLORS.primaryDark, accent3: COLORS.primaryPale, accent4: COLORS.primaryLight,
      accent5: COLORS.contrast, accent6: COLORS.divider, bg1: COLORS.white, bg2: COLORS.surface,
      tx1: COLORS.text, tx2: COLORS.textMuted, dk1: COLORS.text, lt1: COLORS.white, dk2: COLORS.textMuted, lt2: COLORS.surface,
      hlink: tokenHex(THEME_COLORS.hlink), folHlink: tokenHex(THEME_COLORS.folHlink),
    },
  };
}

export async function renderCertifiedLayout(plan, content, outputPath, previewDirectory = null) {
  validateCertifiedRenderInput(plan, content);
  const { Presentation, PresentationFile } = await loadArtifactTool();
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  applyTheme(presentation);
  for (const [index, planSlide] of plan.slides.entries()) {
    const contentSlide = content.slides[index];
    const slide = presentation.slides.add();
    slide.background.fill = COLORS.white;
    addChrome(slide, contentSlide, planSlide);
    LAYOUT_RENDERERS[planSlide.layoutId](slide, planSlide, contentSlide.slotContent);
    slide.speakerNotes.textFrame.setText(`[Sources]\n- ${contentSlide.source}`);
    slide.speakerNotes.setVisible(true);
    if (previewDirectory) {
      await fs.mkdir(previewDirectory, { recursive: true });
      const stem = `slide-${String(index + 1).padStart(2, "0")}`;
      const png = await presentation.export({ slide, format: "png", scale: 1 });
      await fs.writeFile(path.join(previewDirectory, `${stem}.png`), new Uint8Array(await png.arrayBuffer()));
      const layout = await slide.export({ format: "layout" });
      await fs.writeFile(path.join(previewDirectory, `${stem}.layout.json`), await layout.text(), "utf8");
    }
  }
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(outputPath);
  return { slideCount: plan.slides.length, outputPath, templateVersion: MASTER_CONTRACT.templateVersion, designTokensVersion: DESIGN_TOKENS.schemaVersion };
}

async function selfTest() {
  const plan = {
    schemaVersion: PLAN_SCHEMA,
    slides: [{
      slide: 1, storylineId: "S01", layoutId: "singleExhibit", variantId: "full-width-chart", headerProfile: "content-title-only",
      expectedObjects: [{ slotId: "mainExhibit", componentId: "native-chart", objectName: "S01-main-exhibit", geometry: { x: 0.8, y: 1.52, w: 11.733, h: 5.13 } }],
    }],
  };
  const content = {
    schemaVersion: CONTENT_SCHEMA,
    slides: [{ slide: 1, storylineId: "S01", layoutId: "singleExhibit", header: "I-1｜确定性版式", title: "[占位] 单一证据支持唯一管理判断", subtitle: null, source: "数据来源：[占位] 脱敏基准数据", slotContent: { mainExhibit: { componentId: "native-chart", categories: ["A", "B"], values: [1, 2], seriesName: "指数", focusIndex: 1, valueFormat: "integer" } } }],
  };
  validateCertifiedRenderInput(plan, content);
  const invalid = structuredClone(content);
  invalid.slides[0].layoutId = "evidenceInsight";
  let blocked = false;
  try { validateCertifiedRenderInput(plan, invalid); } catch { blocked = true; }
  if (!blocked) fail("self-test did not block layout drift");
  console.log(JSON.stringify({ passed: true, tests: 2, schemaVersion: CONTENT_SCHEMA, layouts: Object.keys(LAYOUT_RENDERERS).length, templateVersion: MASTER_CONTRACT.templateVersion, designTokensVersion: DESIGN_TOKENS.schemaVersion }, null, 2));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["self-test"]) return selfTest();
  if (!args["render-plan"] || !args.content || !args.output) fail("--render-plan, --content and --output are required");
  const plan = JSON.parse(await fs.readFile(path.resolve(args["render-plan"]), "utf8"));
  const content = JSON.parse(await fs.readFile(path.resolve(args.content), "utf8"));
  const result = await renderCertifiedLayout(plan, content, path.resolve(args.output), args["preview-dir"] ? path.resolve(args["preview-dir"]) : null);
  console.log(JSON.stringify({ passed: true, ...result }, null, 2));
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(error.message); process.exitCode = 1; });
}
