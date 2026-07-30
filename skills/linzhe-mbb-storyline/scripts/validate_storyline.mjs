import fs from "node:fs/promises";
import path from "node:path";

const ALLOWED_ROLES = new Set([
  "cover", "navigator", "context", "diagnosis", "evidence", "recommendation",
  "plan", "organization", "reflection", "closing", "appendix",
]);
const ALLOWED_EVIDENCE_STATUS = new Set(["verified", "assumption", "tbd"]);
const ALLOWED_LOCK_STATUS = new Set(["draft", "reviewed", "approved_by_user"]);
const CONTENT_ROLES = new Set([
  "context", "diagnosis", "evidence", "recommendation", "plan",
  "organization", "reflection",
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

function visibleLength(value) {
  return [...String(value ?? "").replace(/\s+/g, "")].length;
}

function present(value) {
  return value != null && String(value).trim().length > 0;
}

function add(items, rule, location, detail) {
  items.push({ rule, location, detail });
}

function validateDocument(doc, requireLock = false) {
  const errors = [];
  const warnings = [];
  const requiredTop = [
    "version", "deckTitle", "deckType", "audience", "decisionQuestion",
    "desiredOutcome", "governingThought", "storyArc", "slides", "review", "lockStatus",
  ];
  for (const field of requiredTop) {
    if (doc[field] == null || doc[field] === "") add(errors, "required_field", field, "缺少必填字段");
  }

  if (!ALLOWED_LOCK_STATUS.has(doc.lockStatus)) {
    add(errors, "invalid_lock_status", "lockStatus", `允许值：${[...ALLOWED_LOCK_STATUS].join(", ")}`);
  }
  if (requireLock && doc.lockStatus !== "approved_by_user") {
    add(errors, "human_lock_required", "lockStatus", "进入PPT生产前必须由用户批准");
  }
  if (!present(doc.audience?.primary) || !present(doc.audience?.decisionRole)) {
    add(errors, "audience_contract", "audience", "primary与decisionRole均为必填");
  }
  if (!Array.isArray(doc.storyArc?.narrativeReadThrough) || doc.storyArc.narrativeReadThrough.length < 3) {
    add(errors, "narrative_readthrough", "storyArc.narrativeReadThrough", "至少需要3句标题串读叙事");
  }
  if (!Array.isArray(doc.slides) || doc.slides.length === 0) {
    add(errors, "slides_required", "slides", "至少需要1页");
    return { errors, warnings };
  }

  const ids = new Set();
  doc.slides.forEach((slide, index) => {
    const loc = `slides[${index}]`;
    const requiredSlide = ["id", "section", "slideRole", "purpose", "actionTitle"];
    for (const field of requiredSlide) {
      if (!present(slide[field])) add(errors, "slide_required_field", `${loc}.${field}`, "缺少必填字段");
    }
    if (ids.has(slide.id)) add(errors, "duplicate_slide_id", `${loc}.id`, slide.id);
    ids.add(slide.id);
    if (!ALLOWED_ROLES.has(slide.slideRole)) {
      add(errors, "invalid_slide_role", `${loc}.slideRole`, slide.slideRole);
    }
    if (visibleLength(slide.actionTitle) > 40) {
      add(errors, "action_title_length", `${loc}.actionTitle`, `${visibleLength(slide.actionTitle)} > 40`);
    }
    if (CONTENT_ROLES.has(slide.slideRole)) {
      const requiredContent = [
        "proofQuestion", "implication", "visualLogic", "continuityFrom",
        "continuityTo", "audienceObjection",
      ];
      for (const field of requiredContent) {
        if (!present(slide[field])) add(errors, "proof_contract", `${loc}.${field}`, "实质内容页必须填写");
      }
      if (!Array.isArray(slide.evidence) || slide.evidence.length === 0) {
        add(errors, "evidence_required", `${loc}.evidence`, "实质内容页至少需要1项证据");
      }
      if (!Number.isFinite(slide.actionTitleScore) || slide.actionTitleScore < 90) {
        add(errors, "action_title_score", `${loc}.actionTitleScore`, "必须≥90");
      }
      if (!Number.isFinite(slide.verticalLogicScore) || slide.verticalLogicScore < 90) {
        add(errors, "vertical_logic_score", `${loc}.verticalLogicScore`, "必须≥90");
      }
    }

    for (const [evidenceIndex, evidence] of (slide.evidence || []).entries()) {
      const evidenceLoc = `${loc}.evidence[${evidenceIndex}]`;
      if (!present(evidence.claim)) add(errors, "evidence_claim", `${evidenceLoc}.claim`, "证据主张不能为空");
      if (!ALLOWED_EVIDENCE_STATUS.has(evidence.status)) {
        add(errors, "evidence_status", `${evidenceLoc}.status`, `允许值：${[...ALLOWED_EVIDENCE_STATUS].join(", ")}`);
      }
      if (evidence.status === "verified" && !present(evidence.sourceRef)) {
        add(errors, "verified_source_required", `${evidenceLoc}.sourceRef`, "verified证据必须可追溯");
      }
    }
    if (!Array.isArray(slide.speakerNotes) || slide.speakerNotes.length === 0) {
      add(warnings, "speaker_notes_missing", `${loc}.speakerNotes`, "建议补充讲述顺序");
    }
  });

  if (!Number.isFinite(doc.review?.horizontalLogicScore) || doc.review.horizontalLogicScore < 90) {
    add(errors, "horizontal_logic_score", "review.horizontalLogicScore", "必须≥90");
  }
  if (!Number.isFinite(doc.review?.decisionReadinessScore) || doc.review.decisionReadinessScore < 85) {
    add(errors, "decision_readiness_score", "review.decisionReadinessScore", "必须≥85");
  }
  if (!Array.isArray(doc.review?.unresolvedCriticalIssues)) {
    add(errors, "critical_issues_contract", "review.unresolvedCriticalIssues", "必须为数组");
  } else if (doc.review.unresolvedCriticalIssues.length > 0) {
    add(errors, "critical_issues_open", "review.unresolvedCriticalIssues", "严重未解问题必须清零");
  }
  if (!Array.isArray(doc.review?.topObjections) || doc.review.topObjections.length === 0) {
    add(warnings, "objections_missing", "review.topObjections", "建议记录受众主要异议及回应位置");
  }
  return { errors, warnings };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["self-test"]) {
    const base = {
      version: 1,
      deckTitle: "测试Deck",
      deckType: "strategy",
      audience: { primary: "管理层", decisionRole: "批准方向" },
      decisionQuestion: "是否批准？",
      desiredOutcome: "批准方向",
      governingThought: "证据支持进入下一阶段。",
      storyArc: { type: "recommendation", narrativeReadThrough: ["现状明确。", "矛盾出现。", "建议可行。"] },
      slides: [{
        id: "S1",
        section: "分析",
        slideRole: "evidence",
        purpose: "证明建议成立",
        actionTitle: "核心证据支持进入下一阶段",
        proofQuestion: "证据是否足够？",
        evidence: [{ claim: "结果已验证", sourceRef: "source-1", status: "verified" }],
        implication: "可以继续。",
        visualLogic: "comparison",
        continuityFrom: "提出问题。",
        continuityTo: "进入建议。",
        audienceObjection: "样本是否充分？",
        speakerNotes: ["先证据，后含义。"],
        sourceRefs: ["source-1"],
        actionTitleScore: 92,
        verticalLogicScore: 93,
      }],
      review: {
        horizontalLogicScore: 92,
        decisionReadinessScore: 88,
        topObjections: [{ objection: "风险？", responseLocation: "S1" }],
        unresolvedCriticalIssues: [],
      },
      lockStatus: "approved_by_user",
    };
    const valid = validateDocument(base, true);
    const invalid = validateDocument({
      ...base,
      lockStatus: "draft",
      slides: [{ ...base.slides[0], evidence: [{ claim: "无来源", status: "verified" }] }],
    }, true);
    if (valid.errors.length || !invalid.errors.some((item) => item.rule === "human_lock_required") ||
        !invalid.errors.some((item) => item.rule === "verified_source_required")) {
      throw new Error(JSON.stringify({ valid, invalid }, null, 2));
    }
    console.log(JSON.stringify({
      passed: true,
      tests: ["valid_locked_storyline", "human_lock_required", "verified_source_required"],
    }, null, 2));
    return;
  }

  if (!args.storyline) throw new Error("Missing --storyline");
  const storylinePath = path.resolve(args.storyline);
  const doc = JSON.parse(await fs.readFile(storylinePath, "utf8"));
  const { errors, warnings } = validateDocument(doc, Boolean(args["require-lock"]));
  const report = {
    passed: errors.length === 0,
    productionReady: errors.length === 0 && doc.lockStatus === "approved_by_user",
    lockStatus: doc.lockStatus,
    slideCount: Array.isArray(doc.slides) ? doc.slides.length : 0,
    errorCount: errors.length,
    warningCount: warnings.length,
    errors,
    warnings,
  };
  const output = `${JSON.stringify(report, null, 2)}\n`;
  if (args.report) {
    const reportPath = path.resolve(args.report);
    await fs.mkdir(path.dirname(reportPath), { recursive: true });
    await fs.writeFile(reportPath, output, "utf8");
  }
  console.log(output);
  if (!report.passed) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
