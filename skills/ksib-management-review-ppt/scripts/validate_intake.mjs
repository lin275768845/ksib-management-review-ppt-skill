#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_CONTRACT_PATH = path.resolve(HERE, "../references/intake-contract.json");
export const CONTRACT_VERSION = "ksib-intake-contract/1.1";
export const PAGE_INTENT_CONTRACT_VERSION = "ksib-page-intent-contract/1.0";
export const THEME_COLOR_CONTRACT_VERSION = "ksib-theme-color-contract/1.0";
export const REPORT_VERSION = "ksib-intake-gate/1.0";
const REQUIRED_QUESTION_FIELDS = [
  "question_id",
  "applies_to_modes",
  "question",
  "required_level",
  "default_value",
  "choices",
  "trigger_condition",
  "blocking_when_missing",
  "answer_source",
];
const REQUIRED_LEVELS = new Set(["required", "visible_optional", "conditional"]);
const EXTERNAL_MODES = ["topic-to-deck", "story-rebuild", "format-only"];
const TWO_LINE_HEADER_VALUES = new Set([
  "title-only-two-line",
  "title-two-line",
  "title-two-line-subtitle",
  "title-two-line-subtitle-exception",
  "content-title-two-line",
  "content-title-two-line-subtitle",
]);

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

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function isPresent(value) {
  if (typeof value === "boolean") return true;
  if (Array.isArray(value)) return value.length > 0;
  if (isPlainObject(value)) return Object.keys(value).length > 0;
  return value != null && String(value).trim().length > 0;
}

function getPath(value, dottedPath) {
  return String(dottedPath ?? "")
    .split(".")
    .filter(Boolean)
    .reduce((current, key) => current?.[key], value);
}

function evaluatePredicate(predicate, context) {
  if (!isPlainObject(predicate)) return false;
  if (Array.isArray(predicate.any)) return predicate.any.some((item) => evaluatePredicate(item, context));
  if (Array.isArray(predicate.all)) return predicate.all.every((item) => evaluatePredicate(item, context));
  const actual = getPath(context, predicate.path);
  if (predicate.operator === "present") return isPresent(actual);
  if (predicate.operator === "equals") return actual === predicate.value;
  if (predicate.operator === "not_equals") return actual !== predicate.value;
  if (predicate.operator === "in" && Array.isArray(predicate.value)) return predicate.value.includes(actual);
  return false;
}

function inputPresentationPaths(payload) {
  const values = [];
  for (const item of [...(payload.inputs || []), ...(payload.references || [])]) {
    const candidate = typeof item === "string"
      ? item
      : item?.path ?? item?.relativePath ?? item?.name;
    if (candidate && /\.pptx?$/i.test(candidate)) values.push(candidate);
  }
  return [...new Set(values)];
}

function inputArtifactInventory(payload) {
  const records = [];
  for (const [kind, items] of [
    ["upload", payload.inputs || []],
    ["reference", payload.references || []],
  ]) {
    for (const item of items) {
      const candidate = typeof item === "string"
        ? item
        : item?.path ?? item?.relativePath ?? item?.name;
      const extension = candidate ? path.extname(String(candidate)).toLowerCase() : "";
      const providedHash = typeof item === "object" ? String(item?.sha256 ?? "").toLowerCase() : "";
      records.push({
        kind,
        extension: /^\.[a-z0-9]+$/i.test(extension) ? extension : null,
        size: Number.isSafeInteger(item?.size) && item.size >= 0 ? item.size : null,
        sha256: /^[a-f0-9]{64}$/.test(providedHash) ? providedHash : null,
      });
    }
  }
  return {
    count: records.length,
    presentationCount: records.filter((item) => [".ppt", ".pptx"].includes(item.extension)).length,
    hashBoundCount: records.filter((item) => item.sha256).length,
    artifacts: records,
  };
}

function audienceDecision(config) {
  const value = {
    audience: config.audience,
    occasion: config.occasion,
    decision: config.decisionGoal ?? config.decisionSupport ?? config.audienceOutcome,
  };
  return Object.values(value).some(isPresent) ? value : undefined;
}

function lengthOrDuration(config) {
  const value = {
    durationMinutes: config.durationMinutes,
    targetSlides: config.targetSlides,
  };
  return Object.values(value).some(isPresent) ? value : undefined;
}

function deliveryRequirements(config) {
  const value = {
    language: config.language,
    deliveryStage: config.deliveryStage,
    previewPolicy: config.previewPolicy,
    nativeEditable: config.nativeEditable,
    qaReport: config.qaReport,
    versionRecord: config.versionRecord,
  };
  return Object.values(value).some(isPresent) ? value : undefined;
}

function dataDefinition(config) {
  const value = {
    period: config.dataPeriod,
    unit: config.dataUnit,
    denominator: config.dataDenominator,
    formula: config.dataFormula,
    version: config.dataVersion,
  };
  return Object.values(value).some(isPresent) ? value : undefined;
}

function derivedFormatScope(config) {
  if (isPresent(config.authorizedScope)) return config.authorizedScope;
  const styleChange = config.stylePolicy === "allow"
    || ![undefined, null, "", "preserve"].includes(config.themePolicy)
    || ![undefined, null, "", "preserve"].includes(config.fontPolicy);
  const geometryChange = ["geometry", "all"].includes(config.chromePolicy)
    || ["preserve", "auto"].includes(config.layoutStrategy);
  if (styleChange && geometryChange) return "geometry-and-style";
  if (styleChange) return "style-only";
  if (geometryChange) return "geometry-only";
  return undefined;
}

const WORKBENCH_RESOLVERS = {
  topic_audience_decision_job: ({ config }) => audienceDecision(config),
  topic_scope_core_questions: ({ config }) => config.requirements,
  topic_materials_and_public_sources: ({ config }) => config.sourceScope,
  topic_required_sections_and_exclusions: ({ config }) => config.requiredSections ?? config.prohibitedChanges,
  topic_length_or_duration: ({ config }) => lengthOrDuration(config),
  topic_theme_strategy: ({ config }) => ({
    themePolicy: config.themePolicy,
    themeColor: config.themeColor,
    themeContrastColor: config.themeContrastColor,
    fontPolicy: config.fontPolicy,
  }),
  topic_reference_and_layout: ({ config }) => ({
    referencePolicy: config.referencePolicy,
    layoutStrategy: config.layoutStrategy,
    proofShape: config.proofShape,
    actionTitlePolicy: config.actionTitlePolicy,
    subtitlePolicy: config.subtitlePolicy,
  }),
  topic_data_definition: ({ config }) => dataDefinition(config),
  topic_delivery_requirements: ({ config }) => deliveryRequirements(config),
  rebuild_audience_decision_job: ({ config }) => audienceDecision(config),
  rebuild_source_presentation: ({ payload }) => inputPresentationPaths(payload),
  rebuild_story_scope: ({ config }) => config.storyScope ?? config.restructureScope ?? config.requirements,
  rebuild_locked_elements: ({ config }) => config.lockedElements ?? config.prohibitedChanges,
  rebuild_evidence_policy: ({ config }) => config.evidencePolicy ?? config.sourceScope,
  rebuild_length_or_duration: ({ config }) => lengthOrDuration(config),
  rebuild_visual_strategy: ({ config }) => ({
    themePolicy: config.themePolicy,
    themeColor: config.themeColor,
    themeContrastColor: config.themeContrastColor,
    fontPolicy: config.fontPolicy,
  }),
  rebuild_layout_strategy: ({ config }) => ({
    layoutStrategy: config.layoutStrategy,
    referencePolicy: config.referencePolicy,
    actionTitlePolicy: config.actionTitlePolicy,
    subtitlePolicy: config.subtitlePolicy,
  }),
  rebuild_delivery_requirements: ({ config }) => deliveryRequirements(config),
  format_source_presentation: ({ payload }) => inputPresentationPaths(payload),
  format_audience_and_occasion: ({ config }) => ({ audience: config.audience, occasion: config.occasion }),
  format_authorized_scope: ({ config }) => derivedFormatScope(config),
  format_content_freeze_confirmation: ({ config }) => config.contentFreezeConfirmed,
  format_font_policy: ({ config }) => config.fontPolicy,
  format_theme_policy: ({ config }) => config.themePolicy,
  format_chrome_policy: ({ config }) => config.chromePolicy,
  format_reference_and_density: ({ config }) => ({
    layoutStrategy: config.layoutStrategy,
    densityPolicy: config.densityPolicy,
    referencePolicy: config.referencePolicy,
    actionTitlePolicy: config.actionTitlePolicy,
    subtitlePolicy: config.subtitlePolicy,
  }),
  format_delivery_requirements: ({ config }) => deliveryRequirements(config),
};

function cleanObject(value) {
  if (!isPlainObject(value)) return value;
  return Object.fromEntries(Object.entries(value).filter(([, item]) => isPresent(item)));
}

function resolveAnswer(question, context) {
  const explicit = context.answers?.[question.question_id];
  if (isPresent(explicit)) {
    return {
      value: explicit,
      source: context.answerSources?.[question.question_id] ?? "user",
      explicit: true,
    };
  }
  const resolver = WORKBENCH_RESOLVERS[question.question_id];
  const workbenchValue = cleanObject(resolver?.(context));
  if (isPresent(workbenchValue)) return { value: workbenchValue, source: "workbench", explicit: true };
  return { value: undefined, source: null, explicit: false };
}

function answerIsComplete(questionId, value) {
  if (!isPresent(value)) return false;
  if (questionId.endsWith("audience_decision_job")) {
    return isPlainObject(value)
      && [value.audience, value.occasion, value.decision].every(isPresent);
  }
  if (questionId === "topic_data_definition") {
    return isPlainObject(value)
      && [value.period, value.unit, value.denominator, value.formula, value.version].every(isPresent);
  }
  if (questionId.endsWith("source_presentation")) {
    return Array.isArray(value) ? value.length > 0 : /\.pptx?$/i.test(String(value));
  }
  if (questionId === "format_content_freeze_confirmation") return value === true;
  return true;
}

export function validateContract(contract) {
  const errors = [];
  if (contract?.schemaVersion !== CONTRACT_VERSION) {
    errors.push({ rule: "contract_version_invalid", expected: CONTRACT_VERSION, actual: contract?.schemaVersion ?? null });
  }
  const modes = isPlainObject(contract?.modes) ? Object.keys(contract.modes) : [];
  if (JSON.stringify([...modes].sort()) !== JSON.stringify([...EXTERNAL_MODES].sort())) {
    errors.push({ rule: "external_modes_invalid", expected: EXTERNAL_MODES, actual: modes });
  }
  const pageIntentContract = contract?.pageIntentContract;
  if (pageIntentContract?.schemaVersion !== PAGE_INTENT_CONTRACT_VERSION) {
    errors.push({ rule: "page_intent_contract_version_invalid", expected: PAGE_INTENT_CONTRACT_VERSION, actual: pageIntentContract?.schemaVersion ?? null });
  }
  if (contract?.themeColorContract?.schemaVersion !== THEME_COLOR_CONTRACT_VERSION) {
    errors.push({ rule: "theme_color_contract_version_invalid", expected: THEME_COLOR_CONTRACT_VERSION, actual: contract?.themeColorContract?.schemaVersion ?? null });
  }
  if (!Array.isArray(pageIntentContract?.requiredFields) || !pageIntentContract.requiredFields.length) {
    errors.push({ rule: "page_intent_required_fields_missing" });
  }
  if (pageIntentContract?.defaults?.bodyToBottomBandGapIn !== 0.3) {
    errors.push({ rule: "page_intent_default_bottom_gap_invalid", expected: 0.3, actual: pageIntentContract?.defaults?.bodyToBottomBandGapIn ?? null });
  }
  if (!Array.isArray(pageIntentContract?.actionTitlePolicies) || !pageIntentContract.actionTitlePolicies.includes("auto-conclusion")) {
    errors.push({ rule: "page_intent_action_title_policies_invalid" });
  }
  if (!Array.isArray(pageIntentContract?.subtitlePolicies) || !pageIntentContract.subtitlePolicies.includes("boundary-only")) {
    errors.push({ rule: "page_intent_subtitle_policies_invalid" });
  }
  const taskQuestion = contract?.taskTypeQuestion;
  const questionIds = new Set();
  const inspectQuestion = (question, expectedMode, location) => {
    if (!isPlainObject(question)) {
      errors.push({ rule: "question_invalid", location });
      return;
    }
    const missingFields = REQUIRED_QUESTION_FIELDS.filter((field) => !Object.hasOwn(question, field));
    if (missingFields.length) errors.push({ rule: "question_fields_missing", location, fields: missingFields });
    if (questionIds.has(question.question_id)) errors.push({ rule: "question_id_duplicate", location, questionId: question.question_id });
    else if (isPresent(question.question_id)) questionIds.add(question.question_id);
    if (!REQUIRED_LEVELS.has(question.required_level)) errors.push({ rule: "required_level_invalid", location, actual: question.required_level });
    if (!Array.isArray(question.applies_to_modes) || !question.applies_to_modes.length) {
      errors.push({ rule: "applies_to_modes_invalid", location });
    } else {
      if (expectedMode && !question.applies_to_modes.includes(expectedMode)) {
        errors.push({ rule: "applies_to_mode_missing", location, expectedMode });
      }
      if (question.applies_to_modes.some((mode) => mode !== "*" && !EXTERNAL_MODES.includes(mode))) {
        errors.push({ rule: "applies_to_unknown_mode", location, actual: question.applies_to_modes });
      }
    }
    if (question.required_level === "required" && question.blocking_when_missing !== true) {
      errors.push({ rule: "required_question_not_blocking", location });
    }
    if (question.required_level === "visible_optional" && question.default_value == null) {
      errors.push({ rule: "visible_optional_default_missing", location });
    }
    if (question.required_level === "conditional") {
      if (!isPlainObject(question.trigger_condition)) errors.push({ rule: "conditional_trigger_missing", location });
      if (question.blocking_when_missing !== true) errors.push({ rule: "conditional_question_not_blocking", location });
    }
    if (!Array.isArray(question.choices) || !Array.isArray(question.answer_source)) {
      errors.push({ rule: "question_array_field_invalid", location });
    }
  };
  inspectQuestion(taskQuestion, null, "taskTypeQuestion");
  if (taskQuestion?.question_id !== "task_type" || taskQuestion?.required_level !== "required") {
    errors.push({ rule: "task_type_question_invalid" });
  }
  for (const mode of modes) {
    const questions = contract.modes[mode]?.questions;
    if (!Array.isArray(questions)) {
      errors.push({ rule: "mode_questions_invalid", mode });
      continue;
    }
    if (questions.length > 9) errors.push({ rule: "mode_question_limit_exceeded", mode, actual: questions.length, maximum: 9 });
    if (questions.length + 1 > 10) errors.push({ rule: "total_question_limit_exceeded", mode, actual: questions.length + 1, maximum: 10 });
    questions.forEach((question, index) => inspectQuestion(question, mode, `modes.${mode}.questions[${index}]`));
  }
  return errors;
}

function normalizeTask(payload) {
  const task = isPlainObject(payload.task) ? payload.task : payload;
  const config = isPlainObject(task.config) ? task.config : (isPlainObject(payload.config) ? payload.config : {});
  const answers = isPlainObject(task.answers) ? task.answers : (isPlainObject(payload.answers) ? payload.answers : {});
  const answerSources = isPlainObject(task.answer_sources)
    ? task.answer_sources
    : (isPlainObject(task.answerSources) ? task.answerSources : {});
  const mode = answers.task_type ?? task.task_type ?? task.taskType ?? task.mode ?? payload.mode ?? config.mode;
  const intakeVersion = task.intake_contract_version
    ?? task.intakeContractVersion
    ?? payload.intake_contract_version
    ?? payload.intakeContractVersion;
  const pageIntentVersion = task.page_intent_contract_version
    ?? task.pageIntentContractVersion
    ?? payload.page_intent_contract_version
    ?? payload.pageIntentContractVersion;
  const themeColorVersion = task.theme_color_contract_version
    ?? task.themeColorContractVersion
    ?? payload.theme_color_contract_version
    ?? payload.themeColorContractVersion;
  return {
    payload: { ...payload, ...task, config },
    config,
    answers,
    answerSources,
    mode,
    intakeVersion,
    pageIntentVersion,
    themeColorVersion,
  };
}

function conflictFindings(context, resolvedAnswers) {
  const conflicts = [];
  const config = context.config;
  if (TWO_LINE_HEADER_VALUES.has(config.headerModePolicy)) {
    conflicts.push({
      rule: "two_line_action_title_forbidden",
      field: "config.headerModePolicy",
      actual: config.headerModePolicy,
      required: "title-only-one-line or title-subtitle",
    });
  }
  if (context.mode !== "format-only") return conflicts;
  const freeze = resolvedAnswers.get("format_content_freeze_confirmation")?.value;
  if (freeze === false) conflicts.push({ rule: "format_only_freeze_rejected", questionId: "format_content_freeze_confirmation" });
  if (isPresent(config.layoutStrategy) && config.layoutStrategy !== "preserve") {
    conflicts.push({ rule: "format_only_layout_strategy_conflict", field: "config.layoutStrategy", actual: config.layoutStrategy, required: "preserve" });
  }
  if (isPresent(config.sourceScope) && config.sourceScope !== "provided-only") {
    conflicts.push({ rule: "format_only_source_scope_conflict", field: "config.sourceScope", actual: config.sourceScope, required: "provided-only" });
  }
  const scope = resolvedAnswers.get("format_authorized_scope")?.value;
  const changesStyle = config.stylePolicy === "allow"
    || ![undefined, null, "", "preserve"].includes(config.themePolicy)
    || ![undefined, null, "", "preserve"].includes(config.fontPolicy);
  if (changesStyle && scope === "geometry-only") {
    conflicts.push({ rule: "format_only_style_without_authorization", questionId: "format_authorized_scope" });
  }
  return conflicts;
}

function executionMode(mode, resolvedAnswers) {
  if (mode === "format-only") return "format-only";
  if (mode === "story-rebuild") {
    const scope = resolvedAnswers.get("rebuild_story_scope")?.value;
    if (scope === "locked-content" || scope?.state === "locked-content") return "locked-content";
  }
  return "story-change";
}

export function validateIntake(contract, taskPayload) {
  const contractErrors = validateContract(contract);
  const context = normalizeTask(taskPayload);
  const taskHash = sha256(JSON.stringify(taskPayload));
  const contractHash = sha256(JSON.stringify(contract));
  const errors = [...contractErrors];
  if (!EXTERNAL_MODES.includes(context.mode)) {
    errors.push({ rule: "task_type_invalid", actual: context.mode ?? null, expected: EXTERNAL_MODES });
  }
  if (context.intakeVersion !== CONTRACT_VERSION) {
    errors.push({ rule: "intake_contract_version_mismatch", actual: context.intakeVersion ?? null, expected: CONTRACT_VERSION });
  }
  if ((contract.pageIntentContract?.requiredForModes || []).includes(context.mode)
    && context.pageIntentVersion !== PAGE_INTENT_CONTRACT_VERSION) {
    errors.push({ rule: "page_intent_contract_version_mismatch", actual: context.pageIntentVersion ?? null, expected: PAGE_INTENT_CONTRACT_VERSION });
  }
  if (context.themeColorVersion !== THEME_COLOR_CONTRACT_VERSION) {
    errors.push({ rule: "theme_color_contract_version_mismatch", actual: context.themeColorVersion ?? null, expected: THEME_COLOR_CONTRACT_VERSION });
  }
  const modeContract = contract.modes?.[context.mode];
  const questions = modeContract?.questions ?? [];
  const resolvedAnswers = new Map();
  const blockingQuestions = [];
  const visibleOptionalQuestions = [];
  const defaultsAvailable = [];
  for (const question of questions) {
    const resolved = resolveAnswer(question, context);
    const triggered = question.required_level === "conditional"
      ? evaluatePredicate(question.trigger_condition, context)
      : question.required_level === "required";
    const complete = answerIsComplete(question.question_id, resolved.value);
    resolvedAnswers.set(question.question_id, { ...resolved, triggered, complete });
    if ((question.required_level === "required" || triggered) && !complete) {
      blockingQuestions.push({
        questionId: question.question_id,
        label: "必填",
        reason: question.required_level === "conditional" ? "condition-triggered" : "required",
      });
    } else if (question.required_level === "visible_optional" && !complete) {
      visibleOptionalQuestions.push({ questionId: question.question_id, label: "选填" });
      defaultsAvailable.push({ questionId: question.question_id, defaultValue: question.default_value });
    }
  }
  const conflicts = conflictFindings(context, resolvedAnswers);
  const report = {
    schemaVersion: REPORT_VERSION,
    contractVersion: contract.schemaVersion ?? null,
    contractSha256: contractHash,
    taskSha256: taskHash,
    mode: context.mode ?? null,
    executionMode: EXTERNAL_MODES.includes(context.mode) ? executionMode(context.mode, resolvedAnswers) : null,
    passed: errors.length === 0 && blockingQuestions.length === 0 && conflicts.length === 0,
    errors,
    blockingQuestions,
    conflicts,
    visibleOptionalQuestions,
    defaultsAvailable,
    clarificationBatch: [
      ...blockingQuestions.map((item) => ({ ...item, question: questions.find((question) => question.question_id === item.questionId)?.question })),
      ...visibleOptionalQuestions.map((item) => ({
        ...item,
        question: questions.find((question) => question.question_id === item.questionId)?.question,
        defaultValue: questions.find((question) => question.question_id === item.questionId)?.default_value,
      })),
    ],
    resolvedQuestionStatus: questions.map((question) => {
      const resolved = resolvedAnswers.get(question.question_id);
      return {
        questionId: question.question_id,
        requiredLevel: question.required_level,
        triggered: resolved.triggered,
        complete: resolved.complete,
        source: resolved.source,
        answerSha256: resolved.complete ? sha256(JSON.stringify(resolved.value)) : null,
      };
    }),
    guardrailIds: (contract.guardrails || [])
      .filter((item) => item.applies_to_modes?.includes(context.mode))
      .map((item) => item.id),
    questionCount: {
      taskType: 1,
      modeQuestions: questions.length,
      total: questions.length ? questions.length + 1 : 1,
    },
    inputArtifacts: inputArtifactInventory(context.payload),
    privacy: {
      rawAnswersIncluded: false,
      note: "报告只记录状态、来源和哈希，不回显完整用户答案。",
    },
  };
  return report;
}

function completeTopicTask() {
  return {
    intake_contract_version: CONTRACT_VERSION,
    page_intent_contract_version: PAGE_INTENT_CONTRACT_VERSION,
    theme_color_contract_version: THEME_COLOR_CONTRACT_VERSION,
    mode: "topic-to-deck",
    answers: {
      topic_audience_decision_job: { audience: "管理层", occasion: "决策会", decision: "是否进入市场" },
      topic_scope_core_questions: "验证市场规模、竞争与进入条件",
      topic_data_definition: { period: "2026", unit: "R$", denominator: "全市场", formula: "销量×成交均价", version: "v1" },
      contains_data: true,
    },
    config: {},
  };
}

export async function selfTest(contract = null) {
  const effectiveContract = contract
    ?? JSON.parse(await fs.readFile(DEFAULT_CONTRACT_PATH, "utf8"));
  const contractErrors = validateContract(effectiveContract);
  if (contractErrors.length) throw new Error(`Contract self-test failed: ${JSON.stringify(contractErrors)}`);
  const topic = validateIntake(effectiveContract, completeTopicTask());
  if (!topic.passed || topic.questionCount.total !== 10 || topic.visibleOptionalQuestions.length !== 6) {
    throw new Error(`Valid topic task failed: ${JSON.stringify(topic)}`);
  }
  const missing = validateIntake(effectiveContract, {
    intake_contract_version: CONTRACT_VERSION,
    page_intent_contract_version: PAGE_INTENT_CONTRACT_VERSION,
    theme_color_contract_version: THEME_COLOR_CONTRACT_VERSION,
    mode: "story-rebuild",
    config: {},
  });
  if (missing.passed || !missing.blockingQuestions.some((item) => item.questionId === "rebuild_source_presentation")) {
    throw new Error(`Missing input was not blocked: ${JSON.stringify(missing)}`);
  }
  const formatConflict = validateIntake(effectiveContract, {
    intake_contract_version: CONTRACT_VERSION,
    theme_color_contract_version: THEME_COLOR_CONTRACT_VERSION,
    mode: "format-only",
    answers: {
      format_source_presentation: "/tmp/source.pptx",
      format_authorized_scope: "geometry-only",
      format_content_freeze_confirmation: true,
    },
    config: { layoutStrategy: "auto", stylePolicy: "allow", themePolicy: "ksib" },
  });
  if (formatConflict.passed || formatConflict.conflicts.length < 2) {
    throw new Error(`Format conflicts were not blocked: ${JSON.stringify(formatConflict)}`);
  }
  const twoLine = validateIntake(effectiveContract, {
    ...completeTopicTask(),
    config: { headerModePolicy: "title-only-two-line" },
  });
  if (!twoLine.conflicts.some((item) => item.rule === "two_line_action_title_forbidden")) {
    throw new Error(`Two-line header was not blocked: ${JSON.stringify(twoLine)}`);
  }
  return {
    passed: true,
    checks: [
      "contract_shape_and_question_budget",
      "valid_topic_task",
      "missing_rebuild_input",
      "format_permission_conflicts",
      "two_line_title_rejected",
      "privacy_redaction",
    ],
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const contractPath = path.resolve(String(args.contract ?? DEFAULT_CONTRACT_PATH));
  const contract = JSON.parse(await fs.readFile(contractPath, "utf8"));
  if (args["self-test"]) {
    process.stdout.write(`${JSON.stringify(await selfTest(contract), null, 2)}\n`);
    return;
  }
  if (!args.task) throw new Error("--task is required unless --self-test is used");
  const taskPath = path.resolve(String(args.task));
  const taskPayload = JSON.parse(await fs.readFile(taskPath, "utf8"));
  const report = validateIntake(contract, taskPayload);
  if (args.report) {
    const reportPath = path.resolve(String(args.report));
    await fs.mkdir(path.dirname(reportPath), { recursive: true });
    await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (!report.passed) process.exitCode = 2;
}

const isMain = process.argv[1]
  && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (isMain) main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
