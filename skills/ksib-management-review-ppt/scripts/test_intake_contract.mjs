import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import test from "node:test";
import {
  CONTRACT_VERSION,
  DEFAULT_CONTRACT_PATH,
  PAGE_INTENT_CONTRACT_VERSION,
  THEME_COLOR_CONTRACT_VERSION,
  validateContract,
  validateIntake,
} from "./validate_intake.mjs";

const contract = JSON.parse(await fs.readFile(DEFAULT_CONTRACT_PATH, "utf8"));
const certifiedRegistry = JSON.parse(await fs.readFile(new URL("../references/certified-layout-registry.json", import.meta.url), "utf8"));
const clone = (value) => structuredClone(value);

function topicTask() {
  return {
    intake_contract_version: CONTRACT_VERSION,
    page_intent_contract_version: PAGE_INTENT_CONTRACT_VERSION,
    theme_color_contract_version: THEME_COLOR_CONTRACT_VERSION,
    mode: "topic-to-deck",
    answers: {
      topic_audience_decision_job: { audience: "管理层", occasion: "决策会", decision: "是否进入市场" },
      topic_scope_core_questions: "验证市场规模、竞争和进入条件",
      contains_data: false,
    },
    config: {},
  };
}

function rebuildTask() {
  return {
    intake_contract_version: CONTRACT_VERSION,
    page_intent_contract_version: PAGE_INTENT_CONTRACT_VERSION,
    theme_color_contract_version: THEME_COLOR_CONTRACT_VERSION,
    mode: "story-rebuild",
    answers: {
      rebuild_audience_decision_job: { audience: "客户管理层", occasion: "正式汇报", decision: "是否批准方案" },
      rebuild_source_presentation: "/tmp/source.pptx",
      rebuild_story_scope: "major-rebuild",
      rebuild_locked_elements: "保留已核验数字与品牌元素",
    },
    config: {},
  };
}

function formatTask() {
  return {
    intake_contract_version: CONTRACT_VERSION,
    page_intent_contract_version: PAGE_INTENT_CONTRACT_VERSION,
    theme_color_contract_version: THEME_COLOR_CONTRACT_VERSION,
    mode: "format-only",
    answers: {
      format_source_presentation: "/tmp/source.pptx",
      format_authorized_scope: "geometry-only",
      format_content_freeze_confirmation: true,
    },
    config: {
      layoutStrategy: "preserve",
      stylePolicy: "preserve",
      themePolicy: "preserve",
      fontPolicy: "preserve",
      sourceScope: "provided-only",
    },
  };
}

test("canonical contract has one task question and nine questions per mode", () => {
  assert.deepEqual(validateContract(contract), []);
  assert.equal(contract.taskTypeQuestion.question_id, "task_type");
  for (const mode of Object.values(contract.modes)) assert.equal(mode.questions.length, 9);
});

test("mode policy defaults match the PPT Studio 2026-08-04 contract", () => {
  assert.deepEqual(contract.modes["topic-to-deck"].policy_defaults, {
    chromePolicy: "all",
    fontPolicy: "ksib",
    stylePolicy: "allow",
    headerPolicy: "ksib",
    headerModePolicy: "auto",
    footerPolicy: "ksib",
    sourcePolicy: "evidence",
    pageNumberPolicy: "dynamic",
    themePolicy: "ksib",
    themeColor: "#FF4906",
    themeContrastColor: "#006B8F",
    layoutStrategy: "auto",
    sourceScope: "public-supplement",
    imagePolicy: "public-research",
    actionTitlePolicy: "auto-conclusion",
    subtitlePolicy: "boundary-only",
    bodyToBottomBandGapPolicy: "standard",
  });
  assert.equal(contract.modes["story-rebuild"].policy_defaults.sourceScope, "provided-only");
  assert.equal(contract.modes["story-rebuild"].policy_defaults.imagePolicy, "provided-only");
  assert.deepEqual(contract.modes["format-only"].policy_defaults, {
    chromePolicy: "geometry",
    fontPolicy: "preserve",
    stylePolicy: "preserve",
    headerPolicy: "preserve",
    headerModePolicy: "preserve",
    footerPolicy: "preserve",
    sourcePolicy: "preserve",
    pageNumberPolicy: "preserve",
    themePolicy: "preserve",
    layoutStrategy: "preserve",
    sourceScope: "provided-only",
    imagePolicy: "provided-only",
    actionTitlePolicy: "preserve",
    subtitlePolicy: "preserve",
    bodyToBottomBandGapPolicy: "preserve",
  });
});

test("page intent contract defines general title, subtitle, and spacing defaults", () => {
  assert.equal(contract.pageIntentContract.schemaVersion, PAGE_INTENT_CONTRACT_VERSION);
  assert.equal(contract.pageIntentContract.defaults.actionTitlePolicy, "auto-conclusion");
  assert.equal(contract.pageIntentContract.defaults.subtitlePolicy, "boundary-only");
  assert.equal(contract.pageIntentContract.defaults.bodyToBottomBandGapIn, 0.3);
  assert(contract.pageIntentContract.requiredFields.includes("questionToAnswer"));
  assert(contract.pageIntentContract.requiredFields.includes("acceptanceChecks"));
});

test("intake hands layout planning to the certified registry without adding a user question", () => {
  assert.equal(contract.certifiedLayoutContract.registrySchemaVersion, "ksib-certified-layout-registry/1.0");
  assert.equal(contract.certifiedLayoutContract.renderPlanSchemaVersion, "ksib-render-plan/1.0");
  assert.equal(contract.certifiedLayoutContract.layoutFidelityGateSchemaVersion, "ksib-layout-fidelity-gate/1.0");
  assert.equal(contract.certifiedLayoutContract.userClarificationRequired, false);
  assert.equal(contract.certifiedLayoutContract.customLayoutRequiresApproval, true);
  assert.deepEqual(
    Object.fromEntries(contract.certifiedLayoutContract.certifiedLayouts.map((item) => [item.layoutId, [...item.variants].sort()])),
    Object.fromEntries(Object.entries(certifiedRegistry.layouts).map(([layoutId, layout]) => [layoutId, Object.keys(layout.variants).sort()])),
  );
  for (const mode of Object.values(contract.modes)) assert.equal(mode.questions.length, 9);
});

test("intake contract validation blocks an incompatible certified layout toolchain", () => {
  const payload = clone(contract);
  payload.certifiedLayoutContract.renderPlanSchemaVersion = "ksib-render-plan/0.9";
  assert(validateContract(payload).some((item) => item.rule === "certified_layout_contract_version_invalid" && item.field === "renderPlanSchemaVersion"));
});

test("question ids are globally unique", () => {
  const ids = [
    contract.taskTypeQuestion.question_id,
    ...Object.values(contract.modes).flatMap((mode) => mode.questions.map((question) => question.question_id)),
  ];
  assert.equal(new Set(ids).size, ids.length);
});

test("duplicate question id is rejected", () => {
  const payload = clone(contract);
  payload.modes["story-rebuild"].questions[0].question_id = payload.modes["topic-to-deck"].questions[0].question_id;
  assert(validateContract(payload).some((item) => item.rule === "question_id_duplicate"));
});

test("unknown applies_to mode is rejected", () => {
  const payload = clone(contract);
  payload.modes["topic-to-deck"].questions[0].applies_to_modes = ["legacy-mode"];
  assert(validateContract(payload).some((item) => item.rule === "applies_to_unknown_mode"));
});

test("more than nine mode questions is rejected", () => {
  const payload = clone(contract);
  payload.modes["topic-to-deck"].questions.push({
    ...clone(payload.modes["topic-to-deck"].questions[0]),
    question_id: "topic_tenth_question",
  });
  const rules = validateContract(payload).map((item) => item.rule);
  assert(rules.includes("mode_question_limit_exceeded"));
  assert(rules.includes("total_question_limit_exceeded"));
});

test("visible optional requires a default", () => {
  const payload = clone(contract);
  payload.modes["topic-to-deck"].questions[2].default_value = null;
  assert(validateContract(payload).some((item) => item.rule === "visible_optional_default_missing"));
});

test("conditional question requires a structured trigger and blocking behavior", () => {
  const payload = clone(contract);
  const conditional = payload.modes["topic-to-deck"].questions.find((item) => item.required_level === "conditional");
  conditional.trigger_condition = null;
  conditional.blocking_when_missing = false;
  const rules = validateContract(payload).map((item) => item.rule);
  assert(rules.includes("conditional_trigger_missing"));
  assert(rules.includes("conditional_question_not_blocking"));
});

test("topic task passes with required answers and exposes optional defaults", () => {
  const report = validateIntake(contract, topicTask());
  assert.equal(report.passed, true);
  assert.equal(report.mode, "topic-to-deck");
  assert.equal(report.executionMode, "story-change");
  assert.equal(report.questionCount.total, 10);
  assert(report.visibleOptionalQuestions.length > 0);
});

test("latest explicit user answer takes precedence over workbench values", () => {
  const task = topicTask();
  task.config = {
    audience: "旧工作台受众",
    occasion: "旧工作台场合",
    decisionGoal: "旧工作台决策",
  };
  task.answers.topic_audience_decision_job = {
    audience: "最新用户受众",
    occasion: "最新用户场合",
    decision: "最新用户决策",
  };
  task.answer_sources = { topic_audience_decision_job: "user" };
  const report = validateIntake(contract, task);
  const status = report.resolvedQuestionStatus.find((item) => item.questionId === "topic_audience_decision_job");
  assert.equal(status.source, "user");
  assert.equal(
    status.answerSha256,
    crypto.createHash("sha256")
      .update(JSON.stringify(task.answers.topic_audience_decision_job))
      .digest("hex"),
  );
});

test("data definition becomes blocking only when data is present", () => {
  const inactive = validateIntake(contract, topicTask());
  assert(!inactive.blockingQuestions.some((item) => item.questionId === "topic_data_definition"));
  const activeTask = topicTask();
  activeTask.answers.contains_data = true;
  const active = validateIntake(contract, activeTask);
  assert(active.blockingQuestions.some((item) => item.questionId === "topic_data_definition"));
});

test("data definition requires period, unit, denominator, formula, and version", () => {
  const task = topicTask();
  task.answers.contains_data = true;
  task.answers.topic_data_definition = { period: "2026", unit: "R$", denominator: "全市场", version: "v1" };
  const report = validateIntake(contract, task);
  assert(report.blockingQuestions.some((item) => item.questionId === "topic_data_definition"));
  task.answers.topic_data_definition.formula = "销量×成交均价";
  assert(!validateIntake(contract, task).blockingQuestions.some((item) => item.questionId === "topic_data_definition"));
});

test("rebuild requires an input presentation", () => {
  const task = rebuildTask();
  delete task.answers.rebuild_source_presentation;
  const report = validateIntake(contract, task);
  assert.equal(report.passed, false);
  assert(report.blockingQuestions.some((item) => item.questionId === "rebuild_source_presentation"));
});

test("PPT Studio manifest inputs satisfy the rebuild source question", () => {
  const task = rebuildTask();
  delete task.answers.rebuild_source_presentation;
  task.inputs = [{ relativePath: "input/source.pptx", sha256: "abc" }];
  const report = validateIntake(contract, task);
  assert(!report.blockingQuestions.some((item) => item.questionId === "rebuild_source_presentation"));
  const status = report.resolvedQuestionStatus.find((item) => item.questionId === "rebuild_source_presentation");
  assert.equal(status.source, "workbench");
});

test("input inventory preserves upstream hashes without exposing file names", () => {
  const task = rebuildTask();
  delete task.answers.rebuild_source_presentation;
  task.inputs = [{
    name: "PRIVATE-CUSTOMER-NAME.pptx",
    relativePath: "input/PRIVATE-CUSTOMER-NAME.pptx",
    size: 12345,
    sha256: "a".repeat(64),
  }];
  const reportText = JSON.stringify(validateIntake(contract, task));
  const report = JSON.parse(reportText);
  assert.equal(report.inputArtifacts.count, 1);
  assert.equal(report.inputArtifacts.presentationCount, 1);
  assert.equal(report.inputArtifacts.hashBoundCount, 1);
  assert.equal(report.inputArtifacts.artifacts[0].sha256, "a".repeat(64));
  assert(!reportText.includes("PRIVATE-CUSTOMER-NAME"));
});

test("locked content is derived inside story-rebuild instead of becoming a fourth task type", () => {
  const task = rebuildTask();
  task.answers.rebuild_story_scope = "locked-content";
  assert.equal(validateIntake(contract, task).executionMode, "locked-content");
  const legacy = validateIntake(contract, { intake_contract_version: CONTRACT_VERSION, mode: "locked-content" });
  assert(legacy.errors.some((item) => item.rule === "task_type_invalid"));
});

test("format-only requires explicit freeze confirmation", () => {
  const task = formatTask();
  delete task.answers.format_content_freeze_confirmation;
  const report = validateIntake(contract, task);
  assert.equal(report.passed, false);
  assert(report.blockingQuestions.some((item) => item.questionId === "format_content_freeze_confirmation"));
});

test("format-only rejects style changes under geometry-only authorization", () => {
  const task = formatTask();
  task.config.stylePolicy = "allow";
  task.config.themePolicy = "ksib";
  const report = validateIntake(contract, task);
  assert(report.conflicts.some((item) => item.rule === "format_only_style_without_authorization"));
});

test("all modes reject two-line title profiles", () => {
  for (const task of [topicTask(), rebuildTask(), formatTask()]) {
    task.config.headerModePolicy = "title-two-line-subtitle-exception";
    const report = validateIntake(contract, task);
    assert(report.conflicts.some((item) => item.rule === "two_line_action_title_forbidden"));
  }
});

test("version mismatch blocks execution", () => {
  const task = topicTask();
  task.intake_contract_version = "legacy/0.1";
  assert(validateIntake(contract, task).errors.some((item) => item.rule === "intake_contract_version_mismatch"));
});

test("new and rebuilt decks require a compatible page intent contract", () => {
  const task = topicTask();
  delete task.page_intent_contract_version;
  assert(validateIntake(contract, task).errors.some((item) => item.rule === "page_intent_contract_version_mismatch"));
  const format = formatTask();
  delete format.page_intent_contract_version;
  assert.equal(validateIntake(contract, format).errors.some((item) => item.rule === "page_intent_contract_version_mismatch"), false);
});

test("all modes require a compatible theme color contract", () => {
  const task = topicTask();
  delete task.theme_color_contract_version;
  assert(validateIntake(contract, task).errors.some((item) => item.rule === "theme_color_contract_version_mismatch"));
});

test("report does not expose raw answer text", () => {
  const task = topicTask();
  task.answers.topic_scope_core_questions = "PRIVATE-MARKER-DO-NOT-ECHO";
  const reportText = JSON.stringify(validateIntake(contract, task));
  assert(!reportText.includes("PRIVATE-MARKER-DO-NOT-ECHO"));
  assert(reportText.includes("answerSha256"));
});

test("UI labels remain limited to 必填 and 选填", () => {
  assert.deepEqual(new Set(Object.values(contract.ui.labels)), new Set(["必填", "选填"]));
});
