#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REFERENCES = path.resolve(HERE, "../references");
const BODY = { x: 0.8, y: 1.52, w: 11.733, h: 5.13 };

const slot = (region, allowedComponents, geometry, options = {}) => ({
  region,
  allowedComponents,
  geometry,
  required: true,
  ...options,
});

const variant = (label, regions, slots, options = {}) => ({
  label,
  headerProfile: "content-title-only",
  geometryToleranceEmu: 0,
  bodyRegion: BODY,
  regions,
  slots,
  ...options,
});

const renderer = (goldenFixture, supportedComponents) => ({
  status: "certified",
  entrypoint: "scripts/render_certified_layout.mjs",
  contentSchema: "references/certified-render-content.schema.json",
  goldenFixture,
  supportedComponents,
});

const layouts = {
  executiveSummary: {
    label: "执行摘要／决策请求",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["summary-lead", "summary-pillar", "summary-ask"]),
    proofShapes: ["decision-to-impact", "portfolio"],
    customLayoutAllowed: false,
    variants: {
      "three-pillar-standard": variant("三支柱决策摘要", { body: BODY }, {
        decisionLead: slot("body", ["summary-lead"], { x: 0.8, y: 1.52, w: 11.733, h: 0.78 }, { typographyRole: "decision-lead-18" }),
        pillar1: slot("body", ["summary-pillar"], { x: 0.8, y: 2.65, w: 3.678, h: 2.65 }, { minItems: 2, maxItems: 4 }),
        pillar2: slot("body", ["summary-pillar"], { x: 4.828, y: 2.65, w: 3.678, h: 2.65 }, { minItems: 2, maxItems: 4 }),
        pillar3: slot("body", ["summary-pillar"], { x: 8.856, y: 2.65, w: 3.677, h: 2.65 }, { minItems: 2, maxItems: 4 }),
        decisionAsk: slot("body", ["summary-ask"], { x: 0.8, y: 5.68, w: 11.733, h: 0.97 }, { minItems: 1, maxItems: 2 }),
      }),
    },
  },
  singleExhibit: {
    label: "单一主证据",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["native-chart", "native-table"]),
    proofShapes: ["trend", "single-exhibit"],
    customLayoutAllowed: false,
    variants: {
      "full-width-chart": variant("全宽原生图表", { mainExhibit: BODY }, {
        mainExhibit: slot("mainExhibit", ["native-chart"], BODY),
      }),
      "full-width-table": variant("全宽原生表格", { mainExhibit: BODY }, {
        mainExhibit: slot("mainExhibit", ["native-table"], BODY, { minItems: 6, maxItems: 42 }),
      }),
    },
  },
  evidenceInsight: {
    label: "证据＋洞察",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["native-chart", "insight-panel", "insight-title", "insight-lead", "insight-list"]),
    proofShapes: ["trend", "decision-to-impact", "single-exhibit"],
    customLayoutAllowed: false,
    variants: {
      "right-panel-standard": variant("主证据左侧＋洞察右侧", {
        mainExhibit: { x: 0.8, y: 1.52, w: 7.7, h: 5.13 },
        insightPanel: { x: 8.85, y: 1.52, w: 3.683, h: 5.13 },
      }, {
        mainExhibit: slot("mainExhibit", ["native-chart"], { x: 0.8, y: 1.52, w: 7.7, h: 5.13 }),
        insightPanel: slot("insightPanel", ["insight-panel"], { x: 8.85, y: 1.52, w: 3.683, h: 5.13 }),
        insightTitle: slot("insightPanel", ["insight-title"], { x: 9.05, y: 1.72, w: 3.283, h: 0.28 }, { typographyRole: "module-title-14" }),
        insightLead: slot("insightPanel", ["insight-lead"], { x: 9.05, y: 2.18, w: 3.283, h: 0.72 }, { typographyRole: "insight-lead-14" }),
        insightItems: slot("insightPanel", ["insight-list"], { x: 9.05, y: 3.1, w: 3.283, h: 3.35 }, { typographyRole: "body-secondary-12", minItems: 2, maxItems: 3 }),
      }),
      "right-panel-subtitle": variant("边界副标题＋洞察右侧", {
        mainExhibit: { x: 0.8, y: 1.66, w: 7.7, h: 4.99 },
        insightPanel: { x: 8.85, y: 1.66, w: 3.683, h: 4.99 },
      }, {
        mainExhibit: slot("mainExhibit", ["native-chart"], { x: 0.8, y: 1.66, w: 7.7, h: 4.99 }),
        insightPanel: slot("insightPanel", ["insight-panel"], { x: 8.85, y: 1.66, w: 3.683, h: 4.99 }),
        insightTitle: slot("insightPanel", ["insight-title"], { x: 9.05, y: 1.86, w: 3.283, h: 0.28 }, { typographyRole: "module-title-14" }),
        insightLead: slot("insightPanel", ["insight-lead"], { x: 9.05, y: 2.32, w: 3.283, h: 0.72 }, { typographyRole: "insight-lead-14" }),
        insightItems: slot("insightPanel", ["insight-list"], { x: 9.05, y: 3.24, w: 3.283, h: 3.21 }, { typographyRole: "body-secondary-12", minItems: 2, maxItems: 3 }),
      }, { headerProfile: "content-title-subtitle", bodyRegion: { x: 0.8, y: 1.66, w: 11.733, h: 4.99 } }),
      "bottom-panel-standard": variant("主证据上方＋洞察底部", {
        mainExhibit: { x: 0.8, y: 1.52, w: 11.733, h: 3.45 },
        insightPanel: { x: 0.8, y: 5.22, w: 11.733, h: 1.43 },
      }, {
        mainExhibit: slot("mainExhibit", ["native-chart"], { x: 0.8, y: 1.52, w: 11.733, h: 3.45 }),
        insightPanel: slot("insightPanel", ["insight-panel"], { x: 0.8, y: 5.22, w: 11.733, h: 1.43 }),
        insightTitle: slot("insightPanel", ["insight-title"], { x: 1.0, y: 5.48, w: 1.35, h: 0.28 }, { typographyRole: "module-title-14" }),
        insightLead: slot("insightPanel", ["insight-lead"], { x: 2.65, y: 5.43, w: 4.35, h: 0.72 }, { typographyRole: "insight-lead-14" }),
        insightItems: slot("insightPanel", ["insight-list"], { x: 7.35, y: 5.42, w: 4.98, h: 0.93 }, { typographyRole: "body-secondary-12", minItems: 2, maxItems: 3 }),
      }),
    },
  },
  tableInsight: {
    label: "表格＋洞察",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["native-table", "insight-panel", "insight-title", "insight-lead", "insight-list"]),
    proofShapes: ["comparison", "portfolio", "single-exhibit"],
    customLayoutAllowed: false,
    variants: {
      "right-panel-standard": variant("原生表格＋右侧洞察", {
        mainExhibit: { x: 0.8, y: 1.52, w: 8.0, h: 5.13 },
        insightPanel: { x: 9.15, y: 1.52, w: 3.383, h: 5.13 },
      }, {
        mainExhibit: slot("mainExhibit", ["native-table"], { x: 0.8, y: 1.52, w: 8.0, h: 5.13 }, { minItems: 9, maxItems: 42 }),
        insightPanel: slot("insightPanel", ["insight-panel"], { x: 9.15, y: 1.52, w: 3.383, h: 5.13 }),
        insightTitle: slot("insightPanel", ["insight-title"], { x: 9.35, y: 1.72, w: 2.983, h: 0.28 }, { typographyRole: "module-title-14" }),
        insightLead: slot("insightPanel", ["insight-lead"], { x: 9.35, y: 2.18, w: 2.983, h: 0.82 }, { typographyRole: "insight-lead-14" }),
        insightItems: slot("insightPanel", ["insight-list"], { x: 9.35, y: 3.2, w: 2.983, h: 3.25 }, { typographyRole: "body-secondary-12", minItems: 2, maxItems: 3 }),
      }),
    },
  },
  sideBySide: {
    label: "左右对比／取舍",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["comparison-column", "divider-line"]),
    proofShapes: ["comparison", "decision-to-impact"],
    customLayoutAllowed: false,
    variants: {
      balanced: variant("左右等宽比较", { left: { x: 0.8, y: 1.52, w: 5.65, h: 5.13 }, right: { x: 6.883, y: 1.52, w: 5.65, h: 5.13 } }, {
        leftColumn: slot("left", ["comparison-column"], { x: 0.8, y: 1.52, w: 5.65, h: 5.13 }, { minItems: 3, maxItems: 6 }),
        divider: slot("body", ["divider-line"], { x: 6.666, y: 1.52, w: 0.001, h: 5.13 }),
        rightColumn: slot("right", ["comparison-column"], { x: 6.883, y: 1.52, w: 5.65, h: 5.13 }, { minItems: 3, maxItems: 6 }),
      }),
    },
  },
  structuredComparison: {
    label: "三／四列结构比较",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["comparison-column"]),
    proofShapes: ["comparison", "portfolio"],
    customLayoutAllowed: false,
    variants: {
      "three-column": variant("三列结构比较", { body: BODY }, {
        column1: slot("body", ["comparison-column"], { x: 0.8, y: 1.52, w: 3.678, h: 5.13 }, { minItems: 3, maxItems: 6 }),
        column2: slot("body", ["comparison-column"], { x: 4.828, y: 1.52, w: 3.678, h: 5.13 }, { minItems: 3, maxItems: 6 }),
        column3: slot("body", ["comparison-column"], { x: 8.856, y: 1.52, w: 3.677, h: 5.13 }, { minItems: 3, maxItems: 6 }),
      }),
      "four-column": variant("四列结构比较", { body: BODY }, {
        column1: slot("body", ["comparison-column"], { x: 0.8, y: 1.52, w: 2.671, h: 5.13 }, { minItems: 3, maxItems: 5 }),
        column2: slot("body", ["comparison-column"], { x: 3.821, y: 1.52, w: 2.671, h: 5.13 }, { minItems: 3, maxItems: 5 }),
        column3: slot("body", ["comparison-column"], { x: 6.842, y: 1.52, w: 2.671, h: 5.13 }, { minItems: 3, maxItems: 5 }),
        column4: slot("body", ["comparison-column"], { x: 9.863, y: 1.52, w: 2.67, h: 5.13 }, { minItems: 3, maxItems: 5 }),
      }),
    },
  },
  matrix2x2: {
    label: "2×2优先级矩阵",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["matrix-quadrant", "axis-label"]),
    proofShapes: ["portfolio", "comparison"],
    customLayoutAllowed: false,
    variants: {
      "quadrant-standard": variant("四象限优先级矩阵", { body: BODY }, {
        yAxisLabel: slot("body", ["axis-label"], { x: 0.8, y: 1.52, w: 2.2, h: 0.28 }, { typographyRole: "small-label-12" }),
        quadrant1: slot("body", ["matrix-quadrant"], { x: 0.8, y: 1.95, w: 5.666, h: 2.08 }, { minItems: 2, maxItems: 4 }),
        quadrant2: slot("body", ["matrix-quadrant"], { x: 6.866, y: 1.95, w: 5.667, h: 2.08 }, { minItems: 2, maxItems: 4 }),
        quadrant3: slot("body", ["matrix-quadrant"], { x: 0.8, y: 4.38, w: 5.666, h: 2.08 }, { minItems: 2, maxItems: 4 }),
        quadrant4: slot("body", ["matrix-quadrant"], { x: 6.866, y: 4.38, w: 5.667, h: 2.08 }, { minItems: 2, maxItems: 4 }),
        xAxisLabel: slot("body", ["axis-label"], { x: 10.333, y: 6.38, w: 2.2, h: 0.27 }, { typographyRole: "small-label-12" }),
      }),
    },
  },
  issueTree: {
    label: "Issue／Driver Tree",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["tree-node", "native-connector"]),
    proofShapes: ["causal-chain", "portfolio"],
    customLayoutAllowed: false,
    variants: {
      "three-branch": variant("一个根问题＋三个分支", { body: BODY }, {
        root: slot("body", ["tree-node"], { x: 0.8, y: 3.05, w: 2.5, h: 1.1 }, { minItems: 1, maxItems: 2 }),
        branch1: slot("body", ["tree-node"], { x: 4.25, y: 1.52, w: 8.283, h: 1.25 }, { minItems: 2, maxItems: 4 }),
        branch2: slot("body", ["tree-node"], { x: 4.25, y: 3.46, w: 8.283, h: 1.25 }, { minItems: 2, maxItems: 4 }),
        branch3: slot("body", ["tree-node"], { x: 4.25, y: 5.4, w: 8.283, h: 1.25 }, { minItems: 2, maxItems: 4 }),
        connector1: slot("body", ["native-connector"], { x: 3.3, y: 2.145, w: 0.95, h: 1.455 }, { geometryToleranceEmu: 27432 }),
        connector2: slot("body", ["native-connector"], { x: 3.3, y: 3.6, w: 0.95, h: 0.485 }, { geometryToleranceEmu: 27432 }),
        connector3: slot("body", ["native-connector"], { x: 3.3, y: 3.6, w: 0.95, h: 2.425 }, { geometryToleranceEmu: 27432 }),
      }),
    },
  },
  problemSolutionMap: {
    label: "问题—解法映射",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["mapping-cell"]),
    proofShapes: ["causal-chain", "decision-to-impact"],
    customLayoutAllowed: false,
    variants: {
      "three-row": variant("三组问题—行动—结果", { body: BODY }, Object.fromEntries([1, 2, 3].flatMap((row, index) => {
        const y = 1.52 + index * 1.72;
        return [
          [`problem${row}`, slot("body", ["mapping-cell"], { x: 0.8, y, w: 3.45, h: 1.42 }, { minItems: 1, maxItems: 2 })],
          [`action${row}`, slot("body", ["mapping-cell"], { x: 4.6, y, w: 4.0, h: 1.42 }, { minItems: 1, maxItems: 2 })],
          [`outcome${row}`, slot("body", ["mapping-cell"], { x: 8.95, y, w: 3.583, h: 1.42 }, { minItems: 1, maxItems: 2 })],
        ];
      }))),
    },
  },
  processValueChain: {
    label: "流程／价值链",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["stage-node", "native-connector"]),
    proofShapes: ["stages", "system", "decision-to-impact"],
    customLayoutAllowed: false,
    variants: {
      "four-stage": variant("四阶段端到端流程", { body: BODY }, Object.fromEntries([
        ...[1, 2, 3, 4].map((stage, index) => [`stage${stage}`, slot("body", ["stage-node"], { x: 0.8 + index * 3.021, y: 2.12, w: 2.671, h: 3.5 }, { minItems: 2, maxItems: 4 })]),
        ...[1, 2, 3].map((connector, index) => [`connector${connector}`, slot("body", ["native-connector"], { x: 3.471 + index * 3.021, y: 3.87, w: 0.35, h: 0 }, { geometryToleranceEmu: 27432 })]),
      ])),
      "five-stage": variant("五阶段端到端流程", { body: BODY }, Object.fromEntries([
        ...[1, 2, 3, 4, 5].map((stage, index) => [`stage${stage}`, slot("body", ["stage-node"], { x: 0.8 + index * 2.367, y: 2.12, w: 2.017, h: 3.5 }, { minItems: 2, maxItems: 4 })]),
        ...[1, 2, 3, 4].map((connector, index) => [`connector${connector}`, slot("body", ["native-connector"], { x: 2.817 + index * 2.367, y: 3.87, w: 0.35, h: 0 }, { geometryToleranceEmu: 27432 })]),
      ])),
    },
  },
  phasePlaybook: {
    label: "阶段打法／Playbook",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["logic-labels", "phase-column"]),
    proofShapes: ["stages", "decision-to-impact"],
    customLayoutAllowed: false,
    variants: {
      "three-stage": variant("三阶段共同逻辑打法", { body: BODY }, {
        logicLabels: slot("body", ["logic-labels"], { x: 0.8, y: 1.78, w: 1.2, h: 1.2 }, { minItems: 3, maxItems: 3, typographyRole: "body-secondary-12" }),
        phase1: slot("body", ["phase-column"], { x: 2.35, y: 1.52, w: 3.161, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase2: slot("body", ["phase-column"], { x: 5.861, y: 1.52, w: 3.161, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase3: slot("body", ["phase-column"], { x: 9.372, y: 1.52, w: 3.161, h: 5.13 }, { minItems: 4, maxItems: 4 }),
      }),
      "four-stage": variant("四阶段共同逻辑打法", { body: BODY }, {
        logicLabels: slot("body", ["logic-labels"], { x: 0.8, y: 1.78, w: 1.2, h: 1.2 }, { minItems: 3, maxItems: 3, typographyRole: "body-secondary-12" }),
        phase1: slot("body", ["phase-column"], { x: 2.35, y: 1.52, w: 2.283, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase2: slot("body", ["phase-column"], { x: 4.983, y: 1.52, w: 2.283, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase3: slot("body", ["phase-column"], { x: 7.616, y: 1.52, w: 2.283, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase4: slot("body", ["phase-column"], { x: 10.249, y: 1.52, w: 2.284, h: 5.13 }, { minItems: 4, maxItems: 4 }),
      }),
    },
  },
  recommendationRoadmap: {
    label: "建议路线图",
    certificationLevel: "certified-core",
    renderer: renderer("benchmarks/certified-layouts/core-library", ["logic-labels", "roadmap-phase"]),
    proofShapes: ["stages", "decision-to-impact"],
    customLayoutAllowed: false,
    variants: {
      "four-phase": variant("四阶段建议—里程碑—Owner", { body: BODY }, {
        logicLabels: slot("body", ["logic-labels"], { x: 0.8, y: 1.78, w: 1.2, h: 1.2 }, { minItems: 3, maxItems: 3, typographyRole: "body-secondary-12" }),
        phase1: slot("body", ["roadmap-phase"], { x: 2.35, y: 1.52, w: 2.283, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase2: slot("body", ["roadmap-phase"], { x: 4.983, y: 1.52, w: 2.283, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase3: slot("body", ["roadmap-phase"], { x: 7.616, y: 1.52, w: 2.283, h: 5.13 }, { minItems: 4, maxItems: 4 }),
        phase4: slot("body", ["roadmap-phase"], { x: 10.249, y: 1.52, w: 2.284, h: 5.13 }, { minItems: 4, maxItems: 4 }),
      }),
    },
  },
};

const components = {
  "native-chart": { objectTypes: ["graphicFrame"], nativeEditable: true, typographyInspection: "component-specific", purposes: ["primary-evidence"] },
  "native-table": { objectTypes: ["graphicFrame"], nativeEditable: true, typographyInspection: "component-specific", minItems: 6, maxItems: 42, purposes: ["primary-evidence"] },
  "editable-diagram": { objectTypes: ["group"], nativeEditable: true, typographyInspection: "component-specific", purposes: ["primary-evidence"] },
  "insight-panel": { objectTypes: ["shape"], nativeEditable: true, purposes: ["insight-panel-container"] },
  "insight-title": { objectTypes: ["shape"], nativeEditable: true, typographyRole: "module-title-14", purposes: ["insight-panel-title"] },
  "insight-lead": { objectTypes: ["shape"], nativeEditable: true, typographyRole: "insight-lead-14", purposes: ["insight-lead"] },
  "insight-list": { objectTypes: ["shape"], nativeEditable: true, typographyRole: "body-secondary-12", minItems: 2, maxItems: 3, maxCharsPerItem: 48, purposes: ["insight-list"] },
  "summary-lead": { objectTypes: ["shape"], nativeEditable: true, typographyRole: "decision-lead-18", purposes: ["decision-lead"] },
  "summary-pillar": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 2, maxItems: 4, purposes: ["summary-pillar"] },
  "summary-ask": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 1, maxItems: 2, purposes: ["decision-ask"] },
  "comparison-column": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 3, maxItems: 6, purposes: ["comparison-column"] },
  "divider-line": { objectTypes: ["shape"], nativeEditable: true, purposes: ["structural-divider"] },
  "matrix-quadrant": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 2, maxItems: 4, purposes: ["matrix-quadrant"] },
  "axis-label": { objectTypes: ["shape"], nativeEditable: true, typographyRole: "small-label-12", purposes: ["axis-label"] },
  "tree-node": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 1, maxItems: 4, purposes: ["tree-node"] },
  "native-connector": { objectTypes: ["connector"], nativeEditable: true, purposes: ["structural-connection"] },
  "mapping-cell": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 1, maxItems: 2, purposes: ["mapping-cell"] },
  "stage-node": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 2, maxItems: 4, purposes: ["process-stage"] },
  "logic-labels": { objectTypes: ["shape"], nativeEditable: true, typographyRole: "body-secondary-12", minItems: 3, maxItems: 3, purposes: ["shared-logic-labels"] },
  "phase-column": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 4, maxItems: 4, purposes: ["phase-playbook"] },
  "roadmap-phase": { objectTypes: ["shape"], nativeEditable: true, typographyInspection: "component-specific", minItems: 4, maxItems: 4, purposes: ["roadmap-phase"] },
};

const typography = {
  schemaVersion: "ksib-typography-roles/1.0",
  defaultTypeface: "PingFang SC",
  fallbackTypefaces: ["苹方-简", "Microsoft YaHei"],
  roles: {
    "action-title-22": { fontSizePt: 22, fontWeight: 700, lineCountMax: 1, purposes: ["action-title"] },
    "decision-lead-18": { fontSizePt: 18, fontWeight: 700, lineCountMax: 2, purposes: ["decision-lead"] },
    "module-title-16": { fontSizePt: 16, fontWeight: 700, lineCountMax: 2, purposes: ["module-title"] },
    "module-title-14": { fontSizePt: 14, fontWeight: 700, lineCountMax: 1, purposes: ["module-title", "insight-panel-title"] },
    "insight-lead-14": { fontSizePt: 14, fontWeight: 700, lineCountMax: 3, purposes: ["insight-lead"] },
    "body-primary-14": { fontSizePt: 14, fontWeight: 400, purposes: ["body-primary"] },
    "body-secondary-12": { fontSizePt: 12, fontWeight: 400, purposes: ["body-secondary", "insight-list"] },
    "chart-label-10": { fontSizePt: 10, fontWeight: 400, purposes: ["chart-label", "annotation"] },
    "small-label-12": { fontSizePt: 12, fontWeight: 700, purposes: ["axis-label", "row-label"] },
    "source-9": { fontSizePt: 9, fontWeight: 400, purposes: ["source", "page-number"] },
  },
  rules: { rendererMayChooseRawFontSize: false, shrinkBelowRoleForbidden: true, overflowMustUseLayoutPolicy: true },
};

const registry = {
  schemaVersion: "ksib-certified-layout-registry/1.0",
  registryVersion: "2.0.0",
  status: "certified-core",
  deck: { widthIn: 13.333, heightIn: 7.5, bodyRightIn: 12.533, bodyBottomIn: 6.65 },
  overflowPolicies: {
    "story-change": ["compress-unlocked-copy", "switch-approved-variant", "split-slide", "block"],
    "locked-content": ["switch-approved-variant", "split-if-authorized", "block"],
    "format-only": ["preserve-compatible-geometry", "block"],
  },
  layouts,
};

const schema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "ksib-certified-render-content/2.0",
  title: "KSIB Certified Core Render Content",
  type: "object",
  additionalProperties: false,
  required: ["schemaVersion", "slides"],
  properties: {
    schemaVersion: { const: "ksib-certified-render-content/2.0" },
    slides: {
      type: "array",
      minItems: 1,
      items: {
        type: "object",
        additionalProperties: false,
        required: ["slide", "storylineId", "layoutId", "header", "title", "source", "slotContent"],
        properties: {
          slide: { type: "integer", minimum: 1 },
          storylineId: { type: "string", minLength: 1 },
          layoutId: { enum: Object.keys(layouts) },
          header: { type: "string", minLength: 1, maxLength: 48 },
          title: { type: "string", minLength: 1, maxLength: 38 },
          subtitle: { type: ["string", "null"], maxLength: 96 },
          source: { type: "string", minLength: 1, maxLength: 180 },
          slotContent: { type: "object", minProperties: 1 },
        },
      },
    },
  },
  $comment: "Layout-specific slot shape and capacity are enforced by the deterministic renderer against the locked Render Plan; the envelope and certified layout enum are schema-validated here.",
};

const outputs = {
  "certified-layout-registry.json": registry,
  "component-registry.json": { schemaVersion: "ksib-component-registry/1.0", components },
  "typography-roles.json": typography,
  "certified-render-content.schema.json": schema,
};

async function main() {
  const check = process.argv.includes("--check");
  const drift = [];
  for (const [name, payload] of Object.entries(outputs)) {
    const target = path.join(REFERENCES, name);
    const expected = `${JSON.stringify(payload, null, 2)}\n`;
    if (check) {
      const actual = await fs.readFile(target, "utf8").catch(() => "");
      if (actual !== expected) drift.push(name);
    } else {
      await fs.writeFile(target, expected, "utf8");
    }
  }
  if (drift.length) throw new Error(`Generated certified layout assets are stale: ${drift.join(", ")}`);
  console.log(JSON.stringify({ passed: true, mode: check ? "check" : "write", layouts: Object.keys(layouts).length, variants: Object.values(layouts).reduce((sum, item) => sum + Object.keys(item.variants).length, 0) }, null, 2));
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
