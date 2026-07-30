import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const VALIDATOR_PATH = fileURLToPath(import.meta.url);
const HERE = path.dirname(VALIDATOR_PATH);
const MATRIX_PATH = path.resolve(HERE, "../references/layout-matrix.json");
const SCHEMA_VERSION = "ksib-storyline-handoff/2.0";
const SEMANTIC_EXEMPT_LAYOUTS = new Set([
  "cover",
  "toc",
  "agenda",
  "section",
  "sectionDivider",
  "appendixDivider",
  "styleboardSystem",
  "styleboardDensity",
]);
const ARGUMENT_TREE_EXEMPT_LAYOUTS = new Set([
  "cover",
  "toc",
  "agenda",
  "section",
  "sectionDivider",
  "appendixDivider",
  "appendixProject",
  "appendixTable",
  "appendixQA",
  "styleboardSystem",
  "styleboardDensity",
]);
const EXPLICIT_ARGUMENT_TREE_EXEMPTIONS = new Map([
  ["executive_summary", "cross_pillar_synthesis"],
  ["methodology", "method_boundary"],
  ["scope_boundary", "scope_boundary"],
  ["closing", "cross_pillar_synthesis"],
]);

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

function normalize(value) {
  return String(value ?? "").replace(/\s+/g, "").replace(/[“”"'`]/g, "");
}

function normalizeLogic(value) {
  return normalize(value).toLocaleLowerCase("zh-CN").replaceAll("_", "-");
}

function normalizeRole(value) {
  return String(value ?? "").trim();
}

function normalizedIdSet(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map((item) => String(item ?? "").trim()).filter(Boolean))].sort();
}

function canonicalLayoutName(layoutName, matrix) {
  const aliases = matrix?.global?.layoutAliases || {};
  let canonical = layoutName;
  const visited = new Set();
  while (aliases[canonical] && !visited.has(canonical)) {
    visited.add(canonical);
    canonical = aliases[canonical];
  }
  return canonical;
}

function allowedRolesForLayout(layoutName, matrix) {
  const policy = matrix?.global?.roleLayoutPolicy || {};
  const restricted = policy.restrictedLayouts?.[layoutName];
  if (Array.isArray(restricted)) return new Set(restricted);
  return new Set(policy.contentRoles || []);
}

function roleLayoutAllowed(layoutName, slideRole, matrix) {
  const role = normalizeRole(slideRole);
  return Boolean(role) && allowedRolesForLayout(layoutName, matrix).has(role);
}

function claimIdsFromStorySlide(slide) {
  const direct = normalizedIdSet(slide.claimIds);
  if (direct.length) return direct;
  return normalizedIdSet((slide.evidence || []).map((item) => item?.claimId));
}

function semanticPayload(slide, claimIds) {
  return {
    actionTitle: normalize(slide.actionTitle ?? slide.title),
    proofQuestion: normalize(slide.proofQuestion),
    implication: normalize(slide.implication),
    visualLogic: normalizeLogic(slide.visualLogic),
    continuityFrom: normalize(slide.continuityFrom),
    continuityTo: normalize(slide.continuityTo),
    audienceObjection: normalize(slide.audienceObjection),
    claimIds: normalizedIdSet(claimIds),
  };
}

function semanticHash(payload) {
  return crypto.createHash("sha256").update(JSON.stringify(payload)).digest("hex");
}

function add(errors, rule, detail) {
  errors.push({ rule, detail });
}

function addWarning(warnings, rule, detail) {
  warnings.push({ rule, detail });
}

function validateArgumentTree(storyline, storySlides, contentByStorylineId, matrix, errors) {
  const errorStart = errors.length;
  const validExplicitExemptIds = new Set();
  for (const slide of storySlides) {
    if (slide.argumentTreeExempt !== true) continue;
    const expectedType = EXPLICIT_ARGUMENT_TREE_EXEMPTIONS.get(slide.slideRole);
    if (!expectedType) {
      add(
        errors,
        "argument_tree_exempt_role_invalid",
        `${slide.id}: 只有executive_summary、methodology、scope_boundary或closing角色允许显式豁免`,
      );
    } else if (slide.argumentTreeExemptType !== expectedType) {
      add(
        errors,
        "argument_tree_exempt_type_invalid",
        `${slide.id}: slideRole=${slide.slideRole}时argumentTreeExemptType必须为${expectedType}`,
      );
    } else if (
      !String(slide.argumentTreeExemptReason ?? "").trim()
      || String(slide.argumentTreeExemptReason).trim().length < 12
    ) {
      add(
        errors,
        "argument_tree_exempt_reason_missing",
        `${slide.id}: 显式豁免必须提供至少12个字符的具体边界说明`,
      );
    } else {
      validExplicitExemptIds.add(slide.id);
    }
  }
  const substantiveSlides = storySlides.filter(
    (slide) => {
      const contentSlide = contentByStorylineId.get(slide.id)?.slide;
      const slideType = canonicalLayoutName(
        contentSlide?.slideType ?? contentSlide?.layoutContract,
        matrix,
      );
      const validRoleBoundExemption = ARGUMENT_TREE_EXEMPT_LAYOUTS.has(slideType)
        && roleLayoutAllowed(slideType, slide.slideRole, matrix)
        && roleLayoutAllowed(slideType, contentSlide?.slideRole, matrix);
      return !validRoleBoundExemption
        && !validExplicitExemptIds.has(slide.id);
    },
  );
  if (!substantiveSlides.length) {
    return {
      passed: errors.length === errorStart,
      pillarCount: 0,
      substantiveSlideCount: 0,
      assignedSlideCount: 0,
    };
  }

  const tree = storyline.argumentTree;
  if (!tree || typeof tree !== "object" || Array.isArray(tree)) {
    add(errors, "argument_tree_missing", "storyline.argumentTree必须存在并形成Governing Thought到页面证据的支撑树");
    return {
      passed: false,
      pillarCount: 0,
      substantiveSlideCount: substantiveSlides.length,
      assignedSlideCount: 0,
    };
  }

  const rootStatement = String(tree.rootStatement ?? "").trim();
  if (!rootStatement) {
    add(errors, "argument_tree_root_missing", "argumentTree.rootStatement不能为空");
  } else if (
    storyline.governingThought != null
    && normalize(rootStatement) !== normalize(storyline.governingThought)
  ) {
    add(
      errors,
      "argument_tree_root_drift",
      "argumentTree.rootStatement必须与storyline.governingThought一致",
    );
  }

  const pillars = Array.isArray(tree.pillars) ? tree.pillars : [];
  const minimumPillars = substantiveSlides.length > 1 ? 2 : 1;
  if (pillars.length < minimumPillars || pillars.length > 4) {
    add(
      errors,
      "argument_tree_pillar_count",
      `支撑论点必须为${minimumPillars}–4个；当前${pillars.length}个`,
    );
  }

  const substantiveById = new Map(substantiveSlides.map((slide) => [slide.id, slide]));
  const allStoryIds = new Set(storySlides.map((slide) => slide.id));
  const assignmentCounts = new Map();
  const pillarIds = new Set();
  const pillarStatements = new Set();
  const allPillarClaimIds = new Set();

  pillars.forEach((pillar, pillarIndex) => {
    const prefix = `argumentTree.pillars[${pillarIndex}]`;
    if (!pillar || typeof pillar !== "object" || Array.isArray(pillar)) {
      add(errors, "argument_tree_pillar_invalid", `${prefix}必须为对象`);
      return;
    }
    const pillarId = String(pillar.id ?? "").trim();
    if (!pillarId) {
      add(errors, "argument_tree_pillar_id_missing", `${prefix}.id不能为空`);
    } else if (pillarIds.has(pillarId)) {
      add(errors, "argument_tree_pillar_id_duplicate", `${prefix}.id=${pillarId}`);
    } else {
      pillarIds.add(pillarId);
    }
    const statement = String(pillar.statement ?? "").trim();
    const normalizedStatement = normalize(statement);
    if (!statement) {
      add(errors, "argument_tree_pillar_statement_missing", `${prefix}.statement不能为空`);
    } else if (pillarStatements.has(normalizedStatement)) {
      add(errors, "argument_tree_pillar_statement_duplicate", `${prefix}.statement重复`);
    } else {
      pillarStatements.add(normalizedStatement);
    }
    if (!String(pillar.supportLogic ?? "").trim()) {
      add(errors, "argument_tree_support_logic_missing", `${prefix}.supportLogic必须解释为何支撑根结论`);
    }

    const slideIds = normalizedIdSet(pillar.slideIds);
    if (!slideIds.length) {
      add(errors, "argument_tree_slide_ids_missing", `${prefix}.slideIds[]不能为空`);
    }
    const expectedClaimIds = new Set();
    for (const slideId of slideIds) {
      if (!allStoryIds.has(slideId)) {
        add(errors, "argument_tree_slide_unknown", `${prefix}引用不存在页面${slideId}`);
        continue;
      }
      if (!substantiveById.has(slideId)) {
        add(errors, "argument_tree_exempt_slide_assigned", `${prefix}不得把${slideId}纳入核心论证树`);
        continue;
      }
      assignmentCounts.set(slideId, (assignmentCounts.get(slideId) ?? 0) + 1);
      for (const claimId of claimIdsFromStorySlide(substantiveById.get(slideId))) {
        expectedClaimIds.add(claimId);
      }
    }
    const actualClaimIds = normalizedIdSet(pillar.claimIds);
    for (const claimId of actualClaimIds) allPillarClaimIds.add(claimId);
    const expected = [...expectedClaimIds].sort();
    if (JSON.stringify(actualClaimIds) !== JSON.stringify(expected)) {
      add(
        errors,
        "argument_tree_claim_ids_mismatch",
        `${prefix}.claimIds=${JSON.stringify(actualClaimIds)}；页面证据应为${JSON.stringify(expected)}`,
      );
    }
  });

  for (const slide of substantiveSlides) {
    const count = assignmentCounts.get(slide.id) ?? 0;
    if (count === 0) {
      add(errors, "argument_tree_slide_unassigned", `${slide.id}未归入任何支撑论点`);
    } else if (count > 1) {
      add(errors, "argument_tree_slide_multi_assigned", `${slide.id}同时归入${count}个支撑论点`);
    }
  }
  for (const slide of storySlides.filter((item) => validExplicitExemptIds.has(item.id))) {
    const slideClaimIds = claimIdsFromStorySlide(slide);
    const newClaimIds = slideClaimIds.filter((claimId) => !allPillarClaimIds.has(claimId));
    if (newClaimIds.length) {
      add(
        errors,
        "argument_tree_exempt_new_claim",
        `${slide.id}: 豁免页只能综合既有Pillar证据，不得引入新Claim：${newClaimIds.join(", ")}`,
      );
    }
    if (
      slide.argumentTreeExemptType === "cross_pillar_synthesis"
      && slide.slideRole === "executive_summary"
      && slideClaimIds.length < 2
    ) {
      add(
        errors,
        "argument_tree_summary_claims_insufficient",
        `${slide.id}: executive_summary至少综合两个已存在Claim`,
      );
    }
  }
  return {
    passed: errors.length === errorStart,
    pillarCount: pillars.length,
    substantiveSlideCount: substantiveSlides.length,
    assignedSlideCount: [...assignmentCounts.values()].filter((count) => count === 1).length,
  };
}

function validate(storyline, content, matrix) {
  const errors = [];
  const warnings = [];
  const semanticHashes = [];
  if (storyline.lockStatus !== "approved_by_user") {
    add(errors, "storyline_not_locked", "lockStatus必须为approved_by_user");
  }
  const storySlides = Array.isArray(storyline.slides) ? storyline.slides : [];
  if (!storySlides.length) {
    add(errors, "storyline_slides_empty", "storyline.slides[]不能为空");
  }
  const storyIds = new Set();
  for (const [index, storySlide] of storySlides.entries()) {
    if (!storySlide?.id) {
      add(errors, "storyline_slide_id_missing", `storyline slide ${index + 1}`);
    } else if (storyIds.has(storySlide.id)) {
      add(errors, "storyline_slide_id_duplicate", storySlide.id);
    } else {
      storyIds.add(storySlide.id);
    }
  }
  const contentSlides = Array.isArray(content) ? content : content.slides;
  if (!Array.isArray(contentSlides)) {
    add(errors, "content_slides_missing", "content必须为数组或包含slides[]");
    return { errors, warnings };
  }
  const contentByStorylineId = new Map();
  contentSlides.forEach((slide, index) => {
    if (!slide.storylineId) {
      add(errors, "storyline_id_missing", `content slide ${index + 1}`);
      return;
    }
    if (contentByStorylineId.has(slide.storylineId)) {
      add(errors, "duplicate_storyline_id", slide.storylineId);
    }
    contentByStorylineId.set(slide.storylineId, { slide, index });
  });

  storySlides.forEach((storySlide, storyIndex) => {
    const match = contentByStorylineId.get(storySlide.id);
    if (!match) {
      add(errors, "storyline_slide_missing", storySlide.id);
      return;
    }
    if (match.index !== storyIndex) {
      add(errors, "slide_order_drift", `${storySlide.id}: storyline ${storyIndex + 1}, content ${match.index + 1}`);
    }
    const storylineSlideRole = normalizeRole(storySlide.slideRole);
    const contentSlideRole = normalizeRole(match.slide.slideRole);
    if (!storylineSlideRole) {
      add(errors, "storyline_slide_role_missing", `${storySlide.id}: storyline.slideRole不能为空`);
    }
    if (!contentSlideRole) {
      add(errors, "content_slide_role_missing", `${storySlide.id}: content.slideRole不能为空`);
    } else if (storylineSlideRole && contentSlideRole !== storylineSlideRole) {
      add(
        errors,
        "slide_role_mismatch",
        `${storySlide.id}: content.slideRole=${contentSlideRole} storyline.slideRole=${storylineSlideRole}`,
      );
    }
    const contentTitle = match.slide.title ?? match.slide.actionTitle;
    if (normalize(contentTitle) !== normalize(storySlide.actionTitle)) {
      add(errors, "action_title_drift", `${storySlide.id}: "${contentTitle}" != "${storySlide.actionTitle}"`);
    }
    const rawSlideType = match.slide.slideType ?? match.slide.layoutContract;
    const slideType = canonicalLayoutName(rawSlideType, matrix);
    if (!slideType) {
      add(errors, "layout_contract_missing", storySlide.id);
    }
    const storylineRoleLayoutAllowed = roleLayoutAllowed(
      slideType,
      storylineSlideRole,
      matrix,
    );
    const contentRoleLayoutAllowed = roleLayoutAllowed(
      slideType,
      contentSlideRole,
      matrix,
    );
    if (
      slideType
      && (!storylineRoleLayoutAllowed || !contentRoleLayoutAllowed)
    ) {
      add(
        errors,
        "slide_role_layout_mismatch",
        `${storySlide.id}: ${slideType}允许slideRole=${[...allowedRolesForLayout(slideType, matrix)].join(", ")}；storyline=${storylineSlideRole || "(missing)"}，content=${contentSlideRole || "(missing)"}`,
      );
    }
    const semanticExempt = SEMANTIC_EXEMPT_LAYOUTS.has(slideType)
      && storylineRoleLayoutAllowed
      && contentRoleLayoutAllowed;
    if (semanticExempt) {
      const payload = semanticPayload(storySlide, []);
      semanticHashes.push({
        storylineId: storySlide.id,
        storylineHash: semanticHash(payload),
        contentHash: semanticHash(semanticPayload(match.slide, [])),
        semanticExempt: true,
      });
      return;
    }

    const semanticFields = [
      "proofQuestion",
      "implication",
      "visualLogic",
      "continuityFrom",
      "continuityTo",
      "audienceObjection",
    ];
    for (const field of semanticFields) {
      if (storySlide[field] == null || String(storySlide[field]).trim() === "") {
        add(errors, "storyline_semantic_field_missing", `${storySlide.id}.${field}`);
        continue;
      }
      if (match.slide[field] == null || String(match.slide[field]).trim() === "") {
        add(errors, "content_semantic_field_missing", `${storySlide.id}.${field}`);
        continue;
      }
      const left = field === "visualLogic" ? normalizeLogic(storySlide[field]) : normalize(storySlide[field]);
      const right = field === "visualLogic" ? normalizeLogic(match.slide[field]) : normalize(match.slide[field]);
      if (left !== right) {
        add(errors, `${field}_drift`, `${storySlide.id}: "${match.slide[field]}" != "${storySlide[field]}"`);
      }
    }

    const storyEvidence = Array.isArray(storySlide.evidence) ? storySlide.evidence : [];
    storyEvidence.forEach((evidence, evidenceIndex) => {
      if (!String(evidence?.claimId ?? "").trim()) {
        add(
          errors,
          "storyline_evidence_claim_id_missing",
          `${storySlide.id}.evidence[${evidenceIndex}]: 必须显式填写claimId；通用id不能替代`,
        );
      }
    });
    const storyClaimIds = claimIdsFromStorySlide(storySlide);
    const contentClaimIds = normalizedIdSet(match.slide.claimIds);
    if (storyEvidence.length && !storyClaimIds.length) {
      add(errors, "storyline_claim_ids_missing", `${storySlide.id}: evidence[]必须逐项携带claimId`);
    }
    if (storyClaimIds.length && !contentClaimIds.length) {
      add(errors, "content_claim_ids_missing", `${storySlide.id}: content必须声明claimIds[]`);
    } else if (JSON.stringify(storyClaimIds) !== JSON.stringify(contentClaimIds)) {
      add(errors, "claim_ids_drift", `${storySlide.id}: content=${JSON.stringify(contentClaimIds)} storyline=${JSON.stringify(storyClaimIds)}`);
    }

    const visualLogic = normalizeLogic(storySlide.visualLogic);
    if (
      match.slide.proofShape != null
      && normalizeLogic(match.slide.proofShape) !== visualLogic
    ) {
      add(
        errors,
        "proof_shape_drift",
        `${storySlide.id}: content.proofShape=${match.slide.proofShape} storyline.visualLogic=${storySlide.visualLogic}`,
      );
    }
    const allowedLayouts = matrix?.proofShapeToLayouts?.[visualLogic];
    if (!Array.isArray(allowedLayouts)) {
      add(errors, "proof_shape_mapping_missing", `${storySlide.id}: ${visualLogic}`);
    } else if (slideType && !allowedLayouts.includes(slideType)) {
      add(errors, "layout_proof_shape_mismatch", `${storySlide.id}: ${slideType}不支持${visualLogic}；允许${allowedLayouts.join(", ")}`);
    }

    const storyPayload = semanticPayload(storySlide, storyClaimIds);
    const contentPayload = semanticPayload(match.slide, contentClaimIds);
    semanticHashes.push({
      storylineId: storySlide.id,
      storylineHash: semanticHash(storyPayload),
      contentHash: semanticHash(contentPayload),
    });
  });

  for (const id of contentByStorylineId.keys()) {
    if (!storySlides.some((slide) => slide.id === id)) {
      add(errors, "unapproved_content_slide", id);
    }
  }
  const argumentTree = validateArgumentTree(
    storyline,
    storySlides,
    contentByStorylineId,
    matrix,
    errors,
  );
  return { errors, warnings, semanticHashes, argumentTree };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const matrix = JSON.parse(await fs.readFile(MATRIX_PATH, "utf8"));
  if (args["self-test"]) {
    const storyline = {
      lockStatus: "approved_by_user",
      governingThought: "证据支持进入下一阶段",
      argumentTree: {
        rootStatement: "证据支持进入下一阶段",
        pillars: [{
          id: "P1",
          statement: "核心指标已达标",
          supportLogic: "关键指标达到门槛，直接支持继续验证",
          slideIds: ["S1"],
          claimIds: ["C1"],
        }],
      },
      slides: [{
        id: "S1",
        slideRole: "evidence",
        actionTitle: "结论支持下一阶段",
        proofQuestion: "现有证据是否支持进入下一阶段？",
        evidence: [{ claimId: "C1", claim: "核心指标已达标", sourceRef: "SRC1", status: "verified" }],
        implication: "可以进入下一阶段验证",
        visualLogic: "comparison",
        continuityFrom: "前页提出是否继续验证的核心命题",
        continuityTo: "下一页进入具体执行建议",
        audienceObjection: "现有证据是否足以支持继续投入",
      }],
    };
    const content = {
      slides: [{
        storylineId: "S1",
        slideRole: "evidence",
        title: "结论支持下一阶段",
        slideType: "twoColumn",
        proofQuestion: "现有证据是否支持进入下一阶段？",
        claimIds: ["C1"],
        implication: "可以进入下一阶段验证",
        visualLogic: "comparison",
        continuityFrom: "前页提出是否继续验证的核心命题",
        continuityTo: "下一页进入具体执行建议",
        audienceObjection: "现有证据是否足以支持继续投入",
      }],
    };
    const valid = validate(storyline, content, matrix);
    const titleDrift = validate(storyline, {
      slides: [{ ...content.slides[0], title: "另一个标题" }],
    }, matrix);
    const proofDrift = validate(storyline, {
      slides: [{ ...content.slides[0], proofQuestion: "换了另一个问题" }],
    }, matrix);
    const implicationDrift = validate(storyline, {
      slides: [{ ...content.slides[0], implication: "暂缓进入下一阶段" }],
    }, matrix);
    const visualDrift = validate(storyline, {
      slides: [{ ...content.slides[0], visualLogic: "trend" }],
    }, matrix);
    const continuityFromDrift = validate(storyline, {
      slides: [{ ...content.slides[0], continuityFrom: "改写了前页承接关系" }],
    }, matrix);
    const continuityToDrift = validate(storyline, {
      slides: [{ ...content.slides[0], continuityTo: "改写了后页引导关系" }],
    }, matrix);
    const audienceObjectionDrift = validate(storyline, {
      slides: [{ ...content.slides[0], audienceObjection: "替换了受众最可能的反驳" }],
    }, matrix);
    const claimDrift = validate(storyline, {
      slides: [{ ...content.slides[0], claimIds: ["C2"] }],
    }, matrix);
    const layoutMismatch = validate(storyline, {
      slides: [{ ...content.slides[0], slideType: "timeline" }],
    }, matrix);
    const proofShapeDrift = validate(storyline, {
      slides: [{ ...content.slides[0], proofShape: "trend" }],
    }, matrix);
    const missingContentSlideRole = validate(storyline, {
      slides: [{ ...content.slides[0], slideRole: undefined }],
    }, matrix);
    const slideRoleMismatch = validate(storyline, {
      slides: [{ ...content.slides[0], slideRole: "recommendation" }],
    }, matrix);
    const unknownProofShape = validate({
      ...storyline,
      slides: [{
        ...storyline.slides[0],
        visualLogic: "unsupported-proof-shape",
      }],
    }, {
      slides: [{
        ...content.slides[0],
        visualLogic: "unsupported-proof-shape",
        proofShape: "unsupported-proof-shape",
      }],
    }, matrix);
    const missingStoryClaimIds = validate({
      ...storyline,
      slides: [{ ...storyline.slides[0], evidence: [{ claim: "没有ID" }], claimIds: undefined }],
    }, content, matrix);
    const genericEvidenceIdCannotSubstituteClaimId = validate({
      ...storyline,
      slides: [{
        ...storyline.slides[0],
        evidence: [{ id: "C1", claim: "通用id不能替代claimId" }],
        claimIds: undefined,
      }],
    }, content, matrix);
    const missingArgumentTree = validate({
      ...storyline,
      argumentTree: undefined,
    }, content, matrix);
    const misassignedArgumentTree = validate({
      ...storyline,
      argumentTree: {
        ...storyline.argumentTree,
        pillars: [{
          ...storyline.argumentTree.pillars[0],
          claimIds: ["C2"],
        }],
      },
    }, content, matrix);
    const unjustifiedArgumentExemption = validate({
      ...storyline,
      slides: [{
        ...storyline.slides[0],
        argumentTreeExempt: true,
        argumentTreeExemptReason: "任意核心证据页不能凭理由跳出论证树",
      }],
    }, content, matrix);
    const closingSemanticDrift = validate({
      ...storyline,
      slides: [{ ...storyline.slides[0], slideRole: "closing" }],
    }, {
      slides: [{
        ...content.slides[0],
        slideRole: "closing",
        proofQuestion: "收尾页也不能偷换证明问题",
      }],
    }, matrix);
    const exemptCover = validate({
      lockStatus: "approved_by_user",
      slides: [{ id: "S0", slideRole: "cover", actionTitle: "封面标题" }],
    }, {
      slides: [{
        storylineId: "S0",
        slideRole: "cover",
        slideType: "cover",
        title: "封面标题",
      }],
    }, matrix);
    const coverRoleBypass = validate({
      lockStatus: "approved_by_user",
      governingThought: "伪装成封面的证据页不得获得豁免",
      slides: [{
        id: "S0",
        slideRole: "evidence",
        actionTitle: "伪装成封面的证据页",
      }],
    }, {
      slides: [{
        storylineId: "S0",
        slideRole: "evidence",
        slideType: "cover",
        title: "伪装成封面的证据页",
      }],
    }, matrix);
    const validMethodologyAppendixHandoff = validate({
      lockStatus: "approved_by_user",
      slides: [{
        id: "S_APP",
        slideRole: "methodology",
        actionTitle: "附录口径表明确研究边界",
        proofQuestion: "研究口径与边界是什么？",
        evidence: [{ claimId: "C_METHOD", claim: "口径边界已明确" }],
        implication: "正文结论应在该口径内解释",
        visualLogic: "comparison",
        continuityFrom: "正文结论需要补充方法边界",
        continuityTo: "附录后进入问答",
        audienceObjection: "不同口径是否会改变结论",
      }],
    }, {
      slides: [{
        storylineId: "S_APP",
        slideRole: "methodology",
        slideType: "appendixTable",
        title: "附录口径表明确研究边界",
        proofQuestion: "研究口径与边界是什么？",
        claimIds: ["C_METHOD"],
        implication: "正文结论应在该口径内解释",
        visualLogic: "comparison",
        proofShape: "comparison",
        continuityFrom: "正文结论需要补充方法边界",
        continuityTo: "附录后进入问答",
        audienceObjection: "不同口径是否会改变结论",
      }],
    }, matrix);
    if (
      valid.errors.length
      || !titleDrift.errors.some((item) => item.rule === "action_title_drift")
      || !proofDrift.errors.some((item) => item.rule === "proofQuestion_drift")
      || !implicationDrift.errors.some((item) => item.rule === "implication_drift")
      || !visualDrift.errors.some((item) => item.rule === "visualLogic_drift")
      || !continuityFromDrift.errors.some((item) => item.rule === "continuityFrom_drift")
      || !continuityToDrift.errors.some((item) => item.rule === "continuityTo_drift")
      || !audienceObjectionDrift.errors.some((item) => item.rule === "audienceObjection_drift")
      || !claimDrift.errors.some((item) => item.rule === "claim_ids_drift")
      || !layoutMismatch.errors.some((item) => item.rule === "layout_proof_shape_mismatch")
      || !proofShapeDrift.errors.some((item) => item.rule === "proof_shape_drift")
      || !missingContentSlideRole.errors.some((item) => item.rule === "content_slide_role_missing")
      || !slideRoleMismatch.errors.some((item) => item.rule === "slide_role_mismatch")
      || !unknownProofShape.errors.some((item) => item.rule === "proof_shape_mapping_missing")
      || unknownProofShape.warnings.some((item) => item.rule === "proof_shape_mapping_missing")
      || !missingStoryClaimIds.errors.some((item) => item.rule === "storyline_claim_ids_missing")
      || !genericEvidenceIdCannotSubstituteClaimId.errors.some((item) => (
        item.rule === "storyline_evidence_claim_id_missing"
      ))
      || !missingArgumentTree.errors.some((item) => item.rule === "argument_tree_missing")
      || !misassignedArgumentTree.errors.some((item) => item.rule === "argument_tree_claim_ids_mismatch")
      || !unjustifiedArgumentExemption.errors.some((item) => item.rule === "argument_tree_exempt_role_invalid")
      || !closingSemanticDrift.errors.some((item) => item.rule === "proofQuestion_drift")
      || exemptCover.errors.length
      || !coverRoleBypass.errors.some((item) => item.rule === "slide_role_layout_mismatch")
      || !coverRoleBypass.errors.some((item) => item.rule === "storyline_semantic_field_missing")
      || !coverRoleBypass.errors.some((item) => item.rule === "argument_tree_missing")
      || validMethodologyAppendixHandoff.errors.length
    ) {
      throw new Error(JSON.stringify({
        valid,
        titleDrift,
        proofDrift,
        implicationDrift,
        visualDrift,
        continuityFromDrift,
        continuityToDrift,
        audienceObjectionDrift,
        claimDrift,
        layoutMismatch,
        proofShapeDrift,
        missingContentSlideRole,
        slideRoleMismatch,
        unknownProofShape,
        missingStoryClaimIds,
        genericEvidenceIdCannotSubstituteClaimId,
        missingArgumentTree,
        misassignedArgumentTree,
        unjustifiedArgumentExemption,
        closingSemanticDrift,
        exemptCover,
        coverRoleBypass,
        validMethodologyAppendixHandoff,
      }, null, 2));
    }
    console.log(JSON.stringify({
      passed: true,
      tests: [
        "valid_semantic_handoff",
        "action_title_drift_rejected",
        "proof_question_drift_rejected",
        "implication_drift_rejected",
        "visual_logic_drift_rejected",
        "continuity_from_drift_rejected",
        "continuity_to_drift_rejected",
        "audience_objection_drift_rejected",
        "claim_ids_drift_rejected",
        "layout_proof_shape_mismatch_rejected",
        "proof_shape_drift_rejected",
        "content_slide_role_required",
        "slide_role_drift_rejected",
        "unknown_proof_shape_is_error",
        "storyline_claim_ids_required",
        "generic_evidence_id_cannot_substitute_claim_id",
        "argument_tree_required",
        "argument_tree_claim_ids_must_match_slides",
        "argument_tree_exemption_requires_allowed_role_type_and_reason",
        "closing_slide_is_not_semantically_exempt",
        "non_content_slide_semantic_exemption",
        "content_role_cannot_use_cover_layout",
        "layout_exemption_requires_matching_role",
        "methodology_appendix_layout_is_proof_routed",
      ],
    }, null, 2));
    return;
  }
  if (!args.storyline || !args.content) throw new Error("Missing --storyline or --content");
  const storylinePath = path.resolve(args.storyline);
  const contentPath = path.resolve(args.content);
  const [storylinePayload, contentPayload, matrixPayload, validatorPayload] = await Promise.all([
    fs.readFile(storylinePath, "utf8"),
    fs.readFile(contentPath, "utf8"),
    fs.readFile(MATRIX_PATH, "utf8"),
    fs.readFile(VALIDATOR_PATH),
  ]);
  const storyline = JSON.parse(storylinePayload);
  const content = JSON.parse(contentPayload);
  const {
    errors,
    warnings,
    semanticHashes,
    argumentTree,
  } = validate(storyline, content, matrix);
  const report = {
    schemaVersion: SCHEMA_VERSION,
    validatorSha256: sha256(validatorPayload),
    passed: errors.length === 0,
    inputHashes: {
      storylineSha256: sha256(storylinePayload),
      contentSha256: sha256(contentPayload),
      matrixSha256: sha256(matrixPayload),
    },
    errorCount: errors.length,
    warningCount: warnings.length,
    errors,
    warnings,
    semanticHashes,
    argumentTree,
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
