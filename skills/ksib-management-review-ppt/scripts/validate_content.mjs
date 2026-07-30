import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MATRIX_PATH = path.resolve(HERE, "../references/layout-matrix.json");
const SCHEMA_VERSION = "ksib-content-gate/2.0";

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

function visibleLength(value) {
  return [...String(value ?? "").replace(/\s+/g, "")].length;
}

function hasText(value) {
  return value != null && String(value).trim().length > 0;
}

function normalizeComparable(value) {
  return String(value ?? "")
    .toLocaleLowerCase("zh-CN")
    .replace(/[“”‘’"'`´.,，。:：;；!?！？、/／\\|｜()[\]{}（）【】《》<>·•—–_\-+\s]/g, "");
}

function characterBigrams(value) {
  const text = [...normalizeComparable(value)];
  if (text.length < 2) return new Set(text);
  return new Set(text.slice(0, -1).map((character, index) => `${character}${text[index + 1]}`));
}

function diceSimilarity(left, right) {
  const leftSet = characterBigrams(left);
  const rightSet = characterBigrams(right);
  if (!leftSet.size || !rightSet.size) return 0;
  let intersection = 0;
  for (const token of leftSet) {
    if (rightSet.has(token)) intersection += 1;
  }
  return (2 * intersection) / (leftSet.size + rightSet.size);
}

function hierarchySimilarity(left, right) {
  const leftNormalized = normalizeComparable(left);
  const rightNormalized = normalizeComparable(right);
  const shorter = leftNormalized.length <= rightNormalized.length ? leftNormalized : rightNormalized;
  const longer = leftNormalized.length > rightNormalized.length ? leftNormalized : rightNormalized;
  const contains = shorter.length >= 8 && longer.includes(shorter);
  return { contains, score: diceSimilarity(left, right) };
}

function expandValues(value, segments) {
  if (!segments.length) return [value];
  const [segment, ...rest] = segments;
  const isArray = segment.endsWith("[]");
  const key = isArray ? segment.slice(0, -2) : segment;
  const next = key ? value?.[key] : value;
  if (isArray) {
    if (!Array.isArray(next)) return [];
    return next.flatMap((item) => expandValues(item, rest));
  }
  return expandValues(next, rest);
}

function getValues(object, pattern) {
  const normalized = pattern.replaceAll("[][]", "[].[]");
  return expandValues(object, normalized.split("."));
}

function requiredPathIssues(value, segments, location = "") {
  if (!segments.length) return isPresent(value) ? [] : [location || "(root)"];
  const [segment, ...rest] = segments;
  const isArray = segment.endsWith("[]");
  const key = isArray ? segment.slice(0, -2) : segment;
  const nextLocation = location ? `${location}.${key}` : key;
  const next = key && value != null && typeof value === "object" ? value[key] : undefined;
  if (isArray) {
    if (!Array.isArray(next) || next.length === 0) return [`${nextLocation}[]`];
    return next.flatMap((item, index) => (
      requiredPathIssues(item, rest, `${nextLocation}[${index}]`)
    ));
  }
  if (!rest.length) return isPresent(next) ? [] : [nextLocation];
  if (next == null || typeof next !== "object") return [nextLocation];
  return requiredPathIssues(next, rest, nextLocation);
}

function canonicalLayoutName(layoutName, matrix) {
  const aliases = matrix.global.layoutAliases || {};
  let canonical = layoutName;
  const visited = new Set();
  while (aliases[canonical] && !visited.has(canonical)) {
    visited.add(canonical);
    canonical = aliases[canonical];
  }
  return canonical;
}

function slideLayoutName(slide, matrix) {
  return canonicalLayoutName(slide.layoutContract || slide.slideType, matrix);
}

function allowedRolesForLayout(layoutName, matrix) {
  const policy = matrix.global?.roleLayoutPolicy || {};
  const restricted = policy.restrictedLayouts?.[layoutName];
  if (Array.isArray(restricted)) return new Set(restricted);
  return new Set(policy.contentRoles || []);
}

function validateRoleLayout(slide, slideIndex, slideType, matrix, errors) {
  const slideRole = String(slide.slideRole ?? "").trim();
  if (!slideRole) {
    addError(
      errors,
      slideIndex,
      slideType,
      "slide_role_missing",
      "每页必须声明slideRole，且Role与Layout必须匹配",
    );
    return;
  }
  const allowedRoles = allowedRolesForLayout(slideType, matrix);
  if (!allowedRoles.has(slideRole)) {
    addError(
      errors,
      slideIndex,
      slideType,
      "slide_role_layout_mismatch",
      `${slideType}仅允许slideRole：${[...allowedRoles].join(", ")}；当前为${slideRole}`,
    );
  }
}

function resolvedRendererContract(slideType, matrix) {
  const spec = matrix.layouts?.[slideType];
  if (!spec) return null;
  const defaults = matrix.global?.rendererDefaults || {};
  const override = spec.rendererContract || {};
  const canonicalRenderer = override.canonicalRenderer
    ?? (defaults.canonicalRendererStrategy === "canonical-layout-name" ? slideType : null);
  return {
    provider: override.provider ?? defaults.provider ?? null,
    canonicalRenderer,
    fallbackRenderer: override.fallbackRenderer ?? null,
    editableNative: override.editableNative ?? defaults.editableNative ?? null,
    fallbackRequiresReason: override.fallbackRequiresReason ?? defaults.fallbackRequiresReason ?? true,
  };
}

function isPresent(value) {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  return hasText(value);
}

function addError(errors, slideIndex, slideType, rule, detail) {
  errors.push({ slide: slideIndex + 1, slideType, rule, detail });
}

function addWarning(warnings, slideIndex, slideType, rule, detail) {
  warnings.push({ slide: slideIndex + 1, slideType, rule, detail });
}

function checkHierarchyPair({
  leftName,
  leftValue,
  rightName,
  rightValue,
  slideIndex,
  slideType,
  matrix,
  errors,
  warnings,
}) {
  if (!hasText(leftValue) || !hasText(rightValue)) return;
  const { contains, score } = hierarchySimilarity(leftValue, rightValue);
  const failThreshold = matrix.global.hierarchySimilarityFail ?? 0.68;
  const warningThreshold = matrix.global.hierarchySimilarityWarning ?? 0.5;
  const detail = `${leftName}↔${rightName}: similarity=${score.toFixed(3)}`;
  if (contains || score >= failThreshold) {
    addError(errors, slideIndex, slideType, "hierarchy_duplication", `${detail}${contains ? "；存在长文本包含关系" : ""}`);
  } else if (score >= warningThreshold) {
    addWarning(warnings, slideIndex, slideType, "hierarchy_similarity_review", detail);
  }
}

function validateSlide(slide, slideIndex, matrix) {
  const errors = [];
  const warnings = [];
  const slideType = slideLayoutName(slide, matrix);
  const spec = matrix.layouts[slideType];
  if (!spec) {
    addError(errors, slideIndex, slideType, "unknown_layout", "必须选择layout-matrix.json中定义的Layout合同");
    return { errors, warnings, rendererContract: null };
  }
  const rendererContract = resolvedRendererContract(slideType, matrix);
  if (
    !rendererContract?.provider
    || !rendererContract?.canonicalRenderer
    || rendererContract.editableNative !== true
  ) {
    addError(
      errors,
      slideIndex,
      slideType,
      "renderer_contract_missing",
      "Layout必须解析到provider、canonicalRenderer和editableNative=true",
    );
  }
  validateRoleLayout(slide, slideIndex, slideType, matrix, errors);
  if (spec.exempt) return { errors, warnings, rendererContract };

  const title = slide.title ?? slide.actionTitle ?? "";
  const subtitle = slide.subtitle ?? "";
  const takeaway = slide.takeaway ?? "";
  const subtitlePurposes = new Set(matrix.global.subtitlePurposes || []);
  const takeawayPurposes = new Set(matrix.global.takeawayPurposes || []);
  const forbiddenTakeawayLayouts = new Set(matrix.global.takeawayForbiddenLayouts || []);

  for (const pattern of spec.requiredFields || []) {
    const missingLocations = requiredPathIssues(
      slide,
      pattern.replaceAll("[][]", "[].[]").split("."),
    );
    if (missingLocations.length) {
      addError(
        errors,
        slideIndex,
        slideType,
        "required_field",
        `${pattern}为必填字段，且每个父节点的数组不得为空；缺失：${missingLocations.join(", ")}`,
      );
    }
  }

  if (hasText(slide.proofShape)) {
    const allowedProofShapes = Array.isArray(spec.proofShape)
      ? spec.proofShape
      : (spec.proofShape ? [spec.proofShape] : []);
    if (allowedProofShapes.length && !allowedProofShapes.includes(slide.proofShape)) {
      addError(
        errors,
        slideIndex,
        slideType,
        "proof_shape_mismatch",
        `${slideType}仅允许Proof Shape：${allowedProofShapes.join(", ")}；当前为${slide.proofShape}`,
      );
    }
    const routedLayouts = (matrix.proofShapeToLayouts[slide.proofShape] || [])
      .map((layoutName) => canonicalLayoutName(layoutName, matrix));
    if (routedLayouts.length && !routedLayouts.includes(slideType)) {
      addError(
        errors,
        slideIndex,
        slideType,
        "proof_shape_route_mismatch",
        `${slide.proofShape}未路由到${slideType}；允许：${routedLayouts.join(", ")}`,
      );
    }
  }

  if (hasText(subtitle)) {
    if (!hasText(slide.subtitlePurpose)) {
      addError(errors, slideIndex, slideType, "subtitle_purpose_missing", "使用Subtitle时必须声明subtitlePurpose");
    } else if (!subtitlePurposes.has(slide.subtitlePurpose)) {
      addError(errors, slideIndex, slideType, "subtitle_purpose_invalid", `subtitlePurpose=${slide.subtitlePurpose}`);
    }
  }

  if (hasText(takeaway)) {
    if (!hasText(slide.takeawayPurpose)) {
      addError(errors, slideIndex, slideType, "takeaway_purpose_missing", "使用Takeaway时必须声明takeawayPurpose");
    } else if (!takeawayPurposes.has(slide.takeawayPurpose)) {
      addError(errors, slideIndex, slideType, "takeaway_purpose_invalid", `takeawayPurpose=${slide.takeawayPurpose}`);
    }
    if (forbiddenTakeawayLayouts.has(slideType)) {
      addError(errors, slideIndex, slideType, "takeaway_forbidden_layout", `${slideType}默认不得设置Takeaway`);
    }
  }

  if (hasText(title) && hasText(subtitle) && hasText(takeaway) && !hasText(slide.hierarchyJustification)) {
    addError(errors, slideIndex, slideType, "triple_layer_stack", "Title＋Subtitle＋Takeaway默认禁止；例外必须声明hierarchyJustification");
  }

  const inlineInsightFields = [
    "insight",
    "insights",
    "implications",
    "insightPanel",
    "managementImplication",
    "decisionImplication",
  ];
  const presentInlineInsights = inlineInsightFields.filter((field) => {
    const value = slide[field];
    return Array.isArray(value) ? value.some(hasText) : hasText(value);
  });
  if (hasText(takeaway) && presentInlineInsights.length) {
    addError(
      errors,
      slideIndex,
      slideType,
      "competing_insight_container",
      `Takeaway不得与主体洞察区共存：${presentInlineInsights.join(", ")}`,
    );
  }

  checkHierarchyPair({
    leftName: "title",
    leftValue: title,
    rightName: "subtitle",
    rightValue: subtitle,
    slideIndex,
    slideType,
    matrix,
    errors,
    warnings,
  });
  checkHierarchyPair({
    leftName: "title",
    leftValue: title,
    rightName: "takeaway",
    rightValue: takeaway,
    slideIndex,
    slideType,
    matrix,
    errors,
    warnings,
  });
  checkHierarchyPair({
    leftName: "subtitle",
    leftValue: subtitle,
    rightName: "takeaway",
    rightValue: takeaway,
    slideIndex,
    slideType,
    matrix,
    errors,
    warnings,
  });

  const globalChecks = [
    ["title", matrix.global.titleChars],
    ["subtitle", matrix.global.subtitleChars],
    ["source", matrix.global.sourceChars],
    ["takeaway", matrix.global.takeawayChars],
  ];
  for (const [field, limit] of globalChecks) {
    if (slide[field] != null && visibleLength(slide[field]) > limit) {
      addError(errors, slideIndex, slideType, "global_char_budget", `${field}: ${visibleLength(slide[field])} > ${limit}`);
    }
  }

  for (const [pattern, limit] of Object.entries(spec.maxItems || {})) {
    const values = getValues(slide, pattern);
    const collections = values.filter(Array.isArray);
    if (collections.length) {
      collections.forEach((collection, collectionIndex) => {
        if (collection.length > limit) {
          const suffix = collections.length > 1 ? `[collection ${collectionIndex + 1}]` : "";
          addError(errors, slideIndex, slideType, "max_items", `${pattern}${suffix}: ${collection.length} > ${limit}`);
        }
      });
    } else {
      const actual = values.filter((value) => value != null).length;
      if (actual > limit) addError(errors, slideIndex, slideType, "max_items", `${pattern}: ${actual} > ${limit}`);
    }
  }

  for (const [pattern, limit] of Object.entries(spec.charBudget || {})) {
    for (const value of getValues(slide, pattern)) {
      if (value == null || typeof value === "object") continue;
      const length = visibleLength(value);
      if (length > limit) addError(errors, slideIndex, slideType, "char_budget", `${pattern}: ${length} > ${limit}`);
    }
  }

  const bottomFields = ["ownerLine", "owner", "unresolved", "bottomConclusion", "secondaryTakeaway"];
  const presentBottomFields = bottomFields.filter((field) => slide[field] != null && String(slide[field]).trim());
  if (slide.takeaway && presentBottomFields.length) {
    addError(errors, slideIndex, slideType, "bottom_stack", `Takeaway之外仍存在：${presentBottomFields.join(", ")}`);
  }
  if ((slide.metrics || []).length > matrix.global.maxMetrics) {
    addError(errors, slideIndex, slideType, "max_metrics", `metrics: ${slide.metrics.length} > ${matrix.global.maxMetrics}`);
  }
  return { errors, warnings, rendererContract };
}

function validateDeck(slides, matrix) {
  const errors = [];
  const warnings = [];
  for (const [layout, spec] of Object.entries(matrix.layouts || {})) {
    if (
      !spec.exempt
      && (!Array.isArray(spec.requiredFields) || spec.requiredFields.length === 0)
    ) {
      errors.push({
        rule: "layout_contract_required_fields_missing",
        detail: `${layout}.requiredFields[]必须非空`,
        slides: [],
      });
    }
    const renderer = resolvedRendererContract(layout, matrix);
    if (!renderer?.provider || !renderer?.canonicalRenderer || renderer.editableNative !== true) {
      errors.push({
        rule: "layout_contract_renderer_missing",
        detail: `${layout}未解析到可编辑Renderer合同`,
        slides: [],
      });
    }
    const allowedRoles = allowedRolesForLayout(layout, matrix);
    if (!allowedRoles.size) {
      errors.push({
        rule: "layout_role_contract_missing",
        detail: `${layout}未解析到允许的slideRole`,
        slides: [],
      });
    }
  }
  for (const [alias, target] of Object.entries(matrix.global?.layoutAliases || {})) {
    if (!matrix.layouts?.[canonicalLayoutName(target, matrix)]) {
      errors.push({
        rule: "layout_alias_target_missing",
        detail: `${alias} -> ${target}`,
        slides: [],
      });
    }
  }
  for (const [proofShape, layouts] of Object.entries(matrix.proofShapeToLayouts || {})) {
    for (const layout of layouts) {
      if (!matrix.layouts?.[canonicalLayoutName(layout, matrix)]) {
        errors.push({
          rule: "proof_shape_route_target_missing",
          detail: `${proofShape} -> ${layout}`,
          slides: [],
        });
      }
    }
  }
  if (!slides.length) {
    errors.push({
      rule: "empty_deck",
      detail: "Content slides[]不能为空",
      slides: [],
    });
  }
  const excludedLayouts = new Set(matrix.global.takeawayShareExcludedLayouts || []);
  const eligibleSlides = slides
    .map((slide, index) => ({ slide, index, slideType: slideLayoutName(slide, matrix) }))
    .filter(({ slideType }) => !excludedLayouts.has(slideType));
  const takeawaySlides = eligibleSlides.filter(({ slide }) => hasText(slide.takeaway));
  const maximumShare = matrix.global.maxTakeawayShare ?? 0.25;
  const maximumCount = eligibleSlides.length
    ? Math.max(1, Math.floor(eligibleSlides.length * maximumShare))
    : 0;

  if (takeawaySlides.length > maximumCount) {
    errors.push({
      rule: "takeaway_overuse",
      detail: `Takeaway pages=${takeawaySlides.length}, eligible content pages=${eligibleSlides.length}, maximum=${maximumCount}`,
      slides: takeawaySlides.map(({ index }) => index + 1),
    });
  }

  for (let index = 1; index < takeawaySlides.length; index += 1) {
    const previous = takeawaySlides[index - 1];
    const current = takeawaySlides[index];
    if (current.index === previous.index + 1) {
      warnings.push({
        rule: "consecutive_takeaways",
        detail: `连续页面均使用Takeaway：${previous.index + 1}, ${current.index + 1}`,
        slides: [previous.index + 1, current.index + 1],
      });
    }
  }

  return {
    errors,
    warnings,
    usage: {
      eligibleContentSlides: eligibleSlides.length,
      takeawaySlides: takeawaySlides.length,
      maximumTakeawaySlides: maximumCount,
      share: eligibleSlides.length ? takeawaySlides.length / eligibleSlides.length : 0,
    },
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["self-test"]) {
    const matrix = JSON.parse(await fs.readFile(MATRIX_PATH, "utf8"));
    const slide = { slideType: "fourColumn", slideRole: "evidence", title: "结论型标题", columns: [1, 2, 3, 4].map((n) => ({ title: `阶段${n}`, problem: "一个问题", decision: "一个关键判断", evidence: "一个结果" })) };
    const requiredBcgLayouts = ["evidenceInsight", "phasePlaybook", "problemSolutionMap", "processModeMatrix", "layeredOperatingModel", "strategyEnablers", "reflectionEvolution"];
    const requiredMachineLayouts = ["singleExhibit", "issueTree", "recommendationRoadmap"];
    const missingBcgLayouts = requiredBcgLayouts.filter((layout) => !matrix.layouts[layout]);
    const invalidLayoutAliases = Object.entries(matrix.global.layoutAliases || {}).filter(
      ([, target]) => !matrix.layouts[canonicalLayoutName(target, matrix)],
    );
    const invalidProofRoutes = Object.entries(matrix.proofShapeToLayouts || {}).flatMap(
      ([proofShape, layouts]) => layouts
        .filter((layout) => !matrix.layouts[canonicalLayoutName(layout, matrix)])
        .map((layout) => ({ proofShape, layout })),
    );
    const unresolvedRendererLayouts = Object.keys(matrix.layouts).filter((layout) => {
      const renderer = resolvedRendererContract(layout, matrix);
      return !renderer?.provider
        || !renderer?.canonicalRenderer
        || renderer.editableNative !== true;
    });
    const incompleteLayoutContracts = Object.entries(matrix.layouts)
      .filter(([, spec]) => !spec.exempt)
      .filter(([, spec]) => !Array.isArray(spec.requiredFields) || spec.requiredFields.length === 0)
      .map(([layout]) => layout);
    const incompleteMachineLayouts = requiredMachineLayouts.filter((layout) => {
      const spec = matrix.layouts[layout];
      return !spec
        || !Array.isArray(spec.proofShape)
        || !spec.proofShape.length
        || !spec.rendererContract?.canonicalRenderer
        || !Array.isArray(spec.requiredFields)
        || !spec.requiredFields.length;
    });
    const semanticExemptLayouts = new Set([
      "cover",
      "toc",
      "agenda",
      "section",
      "sectionDivider",
      "appendixDivider",
      "styleboardSystem",
      "styleboardDensity",
    ]);
    const routedLayouts = new Set(
      Object.values(matrix.proofShapeToLayouts || {})
        .flat()
        .map((layout) => canonicalLayoutName(layout, matrix)),
    );
    const unroutedSubstantiveLayouts = Object.keys(matrix.layouts)
      .filter((layout) => !semanticExemptLayouts.has(layout))
      .filter((layout) => !routedLayouts.has(layout));
    const proofShapeContractMismatches = Object.entries(matrix.layouts)
      .filter(([layout]) => !semanticExemptLayouts.has(layout))
      .flatMap(([layout, spec]) => {
        const declared = Array.isArray(spec.proofShape) ? spec.proofShape : [];
        const missingRoutes = declared.filter(
          (proofShape) => !(matrix.proofShapeToLayouts?.[proofShape] || [])
            .map((candidate) => canonicalLayoutName(candidate, matrix))
            .includes(layout),
        );
        const undeclaredRoutes = Object.entries(matrix.proofShapeToLayouts || {})
          .filter(([, layouts]) => layouts
            .map((candidate) => canonicalLayoutName(candidate, matrix))
            .includes(layout))
          .map(([proofShape]) => proofShape)
          .filter((proofShape) => !declared.includes(proofShape));
        return missingRoutes.length || undeclaredRoutes.length
          ? [{ layout, missingRoutes, undeclaredRoutes }]
          : [];
      });
    const validResult = validateSlide(slide, 0, matrix);
    const validSubtitleResult = validateSlide({ ...slide, subtitle: "数据范围为示例市场过去12个月", subtitlePurpose: "scope" }, 0, matrix);
    const validTakeawayResult = validateSlide({ ...slide, takeaway: "下一阶段应优先验证高潜客群与供给匹配", takeawayPurpose: "decision_implication" }, 0, matrix);
    const validSemanticImplicationWithTakeawayResult = validateSlide({
      ...slide,
      implication: "下一阶段应优先验证高潜客群与供给匹配",
      takeaway: "下一阶段应优先验证高潜客群与供给匹配",
      takeawayPurpose: "decision_implication",
    }, 0, matrix);
    const invalidResult = validateSlide({ ...slide, columns: [...slide.columns, { title: "阶段5" }] }, 0, matrix);
    const stackedResult = validateSlide({ ...slide, takeaway: "一个管理结论", takeawayPurpose: "decision_implication", ownerLine: "额外Owner说明" }, 0, matrix);
    const phaseOverflowResult = validateSlide({ slideType: "phasePlaybook", title: "阶段打法", phases: [1, 2, 3, 4, 5].map((n) => ({ title: `阶段${n}` })) }, 0, matrix);
    const missingPurposeResult = validateSlide({ ...slide, takeaway: "下一阶段应优先验证高潜客群与供给匹配" }, 0, matrix);
    const duplicateSubtitleResult = validateSlide({ ...slide, subtitle: "结论型标题", subtitlePurpose: "scope" }, 0, matrix);
    const duplicateTakeawayResult = validateSlide({ ...slide, title: "平台B品牌格局较平台A更加分散", takeaway: "平台B品牌格局较平台A更加分散，因此需要关注长尾品牌", takeawayPurpose: "decision_implication" }, 0, matrix);
    const tripleLayerResult = validateSlide({ ...slide, subtitle: "数据范围为示例市场过去12个月", subtitlePurpose: "scope", takeaway: "下一阶段应优先验证高潜客群与供给匹配", takeawayPurpose: "decision_implication" }, 0, matrix);
    const competingInsightResult = validateSlide({ ...slide, takeaway: "下一阶段应优先验证高潜客群与供给匹配", takeawayPurpose: "decision_implication", insight: "主体已经存在洞察区域" }, 0, matrix);
    const overuseSlides = Array.from({ length: 8 }, (_, index) => ({
      ...slide,
      title: `第${index + 1}页形成独立结论`,
      ...(index < 3 ? {
        takeaway: `第${index + 1}页给出不同的行动含义`,
        takeawayPurpose: "action",
      } : {}),
    }));
    const overuseResult = validateDeck(overuseSlides, matrix);
    const validSingleExhibit = {
      layoutContract: "single-exhibit",
      slideRole: "evidence",
      title: "单一主证据足以支撑本页核心判断",
      proofShape: "single-exhibit",
      exhibit: {
        type: "horizontalBar",
        title: "各赛道成交额份额",
        unit: "%",
        sourceRef: "KSIB内部竞品数据库",
        annotations: [{ label: "头部赛道", detail: "份额显著领先" }],
      },
      findings: [{ text: "头部赛道贡献超过整体成交额的一半" }],
    };
    const validIssueTree = {
      slideType: "issueTree",
      slideRole: "diagnosis",
      title: "增长问题需要沿需求、供给与转化三条路径验证",
      proofShape: "causal-chain",
      root: { question: "增长为什么低于预期？" },
      branches: [
        {
          question: "需求是否不足？",
          metric: "需求",
          children: [
            { question: "目标人群规模是否足够？", validationPath: "核对渗透率与搜索趋势", evidenceRef: "消费者研究" },
          ],
        },
        {
          question: "供给是否错配？",
          metric: "供给",
          children: [
            { question: "功效与价格带是否匹配？", validationPath: "比较商品结构与成交结构", evidenceRef: "平台榜单" },
          ],
        },
      ],
    };
    const validRecommendationRoadmap = {
      layoutContract: "recommendation-roadmap",
      slideRole: "recommendation",
      title: "先验证产品市场匹配，再分阶段扩大商业投入",
      proofShape: "stages",
      recommendation: "以两轮验证形成从产品适配到规模化增长的决策链",
      keyConditions: ["明确核心人群", "锁定价格与功效组合"],
      milestones: [
        {
          period: "0–4周",
          title: "产品验证",
          action: "验证核心功效与内容表达",
          owner: "产品负责人",
          successCriterion: "形成可复制的成交组合",
        },
        {
          period: "5–12周",
          title: "渠道放大",
          action: "扩大达人与货盘覆盖",
          owner: "渠道负责人",
          successCriterion: "单位投放产出达到门槛",
        },
      ],
    };
    const validSingleExhibitResult = validateSlide(validSingleExhibit, 0, matrix);
    const validIssueTreeResult = validateSlide(validIssueTree, 0, matrix);
    const validRecommendationRoadmapResult = validateSlide(validRecommendationRoadmap, 0, matrix);
    const singleExhibitOverflowResult = validateSlide({
      ...validSingleExhibit,
      findings: [1, 2, 3, 4].map((n) => ({ text: `第${n}项发现` })),
    }, 0, matrix);
    const singleExhibitMissingFieldResult = validateSlide({
      ...validSingleExhibit,
      exhibit: { ...validSingleExhibit.exhibit, sourceRef: "" },
    }, 0, matrix);
    const issueTreeOverflowResult = validateSlide({
      ...validIssueTree,
      branches: [{
        ...validIssueTree.branches[0],
        children: [1, 2, 3, 4].map((n) => ({
          question: `第${n}个验证问题`,
          validationPath: `第${n}条验证路径`,
        })),
      }],
    }, 0, matrix);
    const issueTreeMissingFieldResult = validateSlide({
      ...validIssueTree,
      branches: [{
        ...validIssueTree.branches[0],
        children: [{ question: "目标人群规模是否足够？", validationPath: "" }],
      }],
    }, 0, matrix);
    const issueTreeMissingNestedCollectionResult = validateSlide({
      ...validIssueTree,
      branches: [
        validIssueTree.branches[0],
        {
          ...validIssueTree.branches[1],
          children: undefined,
        },
      ],
    }, 0, matrix);
    const recommendationRoadmapOverflowResult = validateSlide({
      ...validRecommendationRoadmap,
      milestones: [1, 2, 3, 4, 5].map((n) => ({
        period: `阶段${n}`,
        title: `里程碑${n}`,
        action: "完成关键验证动作",
        owner: "业务负责人",
        successCriterion: "达到阶段判断标准",
      })),
    }, 0, matrix);
    const recommendationRoadmapMissingFieldResult = validateSlide({
      ...validRecommendationRoadmap,
      milestones: [{ ...validRecommendationRoadmap.milestones[0], owner: "" }],
    }, 0, matrix);
    const proofShapeMismatchResult = validateSlide({
      ...validIssueTree,
      proofShape: "stages",
    }, 0, matrix);
    const emptyDeckResult = validateDeck([], matrix);
    const emptySlideResult = validateSlide({ slideType: "twoColumn" }, 0, matrix);
    const validCoverResult = validateSlide({
      slideType: "cover",
      slideRole: "cover",
      title: "封面标题",
    }, 0, matrix);
    const coverRoleBypassResult = validateSlide({
      slideType: "cover",
      slideRole: "evidence",
      title: "伪装成封面的证据页",
    }, 0, matrix);
    const validNavigatorResult = validateSlide({
      slideType: "sectionDivider",
      slideRole: "navigator",
      title: "章节导航",
    }, 0, matrix);
    const validExecutiveSummaryResult = validateSlide({
      ...slide,
      slideRole: "executive_summary",
      title: "执行摘要综合核心证据并回答决策问题",
    }, 0, matrix);
    const validMethodologyAppendixResult = validateSlide({
      slideType: "appendixQA",
      slideRole: "methodology",
      title: "方法与边界",
      question: "本研究采用什么口径？",
      directAnswer: "本页只解释抽样、计算与使用边界，不新增客户可见事实主张。",
    }, 0, matrix);
    if (
      missingBcgLayouts.length
      || invalidLayoutAliases.length
      || invalidProofRoutes.length
      || unresolvedRendererLayouts.length
      || incompleteLayoutContracts.length
      || incompleteMachineLayouts.length
      || unroutedSubstantiveLayouts.length
      || proofShapeContractMismatches.length
      || validResult.errors.length
      || validSubtitleResult.errors.length
      || validTakeawayResult.errors.length
      || validSemanticImplicationWithTakeawayResult.errors.length
      || validSingleExhibitResult.errors.length
      || validIssueTreeResult.errors.length
      || validRecommendationRoadmapResult.errors.length
      || !invalidResult.errors.some((error) => error.rule === "max_items")
      || !stackedResult.errors.some((error) => error.rule === "bottom_stack")
      || !phaseOverflowResult.errors.some((error) => error.rule === "max_items")
      || !missingPurposeResult.errors.some((error) => error.rule === "takeaway_purpose_missing")
      || !duplicateSubtitleResult.errors.some((error) => error.rule === "hierarchy_duplication")
      || !duplicateTakeawayResult.errors.some((error) => error.rule === "hierarchy_duplication")
      || !tripleLayerResult.errors.some((error) => error.rule === "triple_layer_stack")
      || !competingInsightResult.errors.some((error) => error.rule === "competing_insight_container")
      || !overuseResult.errors.some((error) => error.rule === "takeaway_overuse")
      || !singleExhibitOverflowResult.errors.some((error) => error.rule === "max_items")
      || !singleExhibitMissingFieldResult.errors.some((error) => error.rule === "required_field")
      || !issueTreeOverflowResult.errors.some((error) => error.rule === "max_items")
      || !issueTreeMissingFieldResult.errors.some((error) => error.rule === "required_field")
      || !issueTreeMissingNestedCollectionResult.errors.some((error) => (
        error.rule === "required_field" && error.detail.includes("branches[1].children[]")
      ))
      || !recommendationRoadmapOverflowResult.errors.some((error) => error.rule === "max_items")
      || !recommendationRoadmapMissingFieldResult.errors.some((error) => error.rule === "required_field")
      || !proofShapeMismatchResult.errors.some((error) => error.rule === "proof_shape_mismatch")
      || !emptyDeckResult.errors.some((error) => error.rule === "empty_deck")
      || !emptySlideResult.errors.some((error) => error.rule === "required_field")
      || validCoverResult.errors.length
      || !coverRoleBypassResult.errors.some((error) => error.rule === "slide_role_layout_mismatch")
      || validNavigatorResult.errors.length
      || validExecutiveSummaryResult.errors.length
      || validMethodologyAppendixResult.errors.length
    ) {
      throw new Error(JSON.stringify({
        missingBcgLayouts,
        invalidLayoutAliases,
        invalidProofRoutes,
        unresolvedRendererLayouts,
        incompleteLayoutContracts,
        incompleteMachineLayouts,
        unroutedSubstantiveLayouts,
        proofShapeContractMismatches,
        validResult,
        validSubtitleResult,
        validTakeawayResult,
        validSemanticImplicationWithTakeawayResult,
        validSingleExhibitResult,
        validIssueTreeResult,
        validRecommendationRoadmapResult,
        invalidResult,
        stackedResult,
        phaseOverflowResult,
        missingPurposeResult,
        duplicateSubtitleResult,
        duplicateTakeawayResult,
        tripleLayerResult,
        competingInsightResult,
        overuseResult,
        singleExhibitOverflowResult,
        singleExhibitMissingFieldResult,
        issueTreeOverflowResult,
        issueTreeMissingFieldResult,
        issueTreeMissingNestedCollectionResult,
        recommendationRoadmapOverflowResult,
        recommendationRoadmapMissingFieldResult,
        proofShapeMismatchResult,
        emptyDeckResult,
        emptySlideResult,
        validCoverResult,
        coverRoleBypassResult,
        validNavigatorResult,
        validExecutiveSummaryResult,
        validMethodologyAppendixResult,
      }));
    }
    console.log(JSON.stringify({
      passed: true,
      tests: [
        "fourColumn_valid",
        "valid_subtitle_contract",
        "valid_takeaway_contract",
        "semantic_implication_is_not_a_competing_visual_box",
        "fourColumn_overflow_rejected",
        "bottom_stack_rejected",
        "bcg_layouts_registered",
        "all_layout_aliases_resolve",
        "all_proof_routes_resolve",
        "all_layouts_resolve_renderer_contract",
        "all_non_exempt_layouts_define_required_fields",
        "all_substantive_layouts_are_proof_routed",
        "layout_proof_shape_contract_is_bidirectional",
        "phasePlaybook_overflow_rejected",
        "takeaway_purpose_required",
        "duplicate_subtitle_rejected",
        "duplicate_takeaway_rejected",
        "triple_layer_rejected",
        "competing_insight_rejected",
        "takeaway_overuse_rejected",
        "singleExhibit_alias_and_valid_contract",
        "issueTree_valid_contract",
        "recommendationRoadmap_alias_and_valid_contract",
        "singleExhibit_overflow_rejected",
        "singleExhibit_required_field_enforced",
        "issueTree_nested_overflow_rejected",
        "issueTree_required_field_enforced",
        "issueTree_each_parent_requires_nested_collection",
        "recommendationRoadmap_overflow_rejected",
        "recommendationRoadmap_required_field_enforced",
        "proof_shape_mismatch_rejected",
        "empty_deck_rejected",
        "empty_slide_rejected",
        "cover_role_layout_contract_valid",
        "content_role_cannot_use_cover_layout",
        "navigator_layout_registered_and_role_bound",
        "executive_summary_role_allowed_on_content_layout",
        "methodology_role_allowed_on_appendix_qa",
      ],
    }, null, 2));
    return;
  }
  if (!args.content) throw new Error("Missing --content");
  const matrixPayload = await fs.readFile(MATRIX_PATH, "utf8");
  const matrix = JSON.parse(matrixPayload);
  const contentPath = path.resolve(args.content);
  const contentPayload = await fs.readFile(contentPath, "utf8");
  const content = JSON.parse(contentPayload);
  const slides = Array.isArray(content) ? content : content.slides;
  if (!Array.isArray(slides)) throw new Error("Content must be an array or contain slides[]");
  const results = slides.map((slide, index) => ({
    slide: index + 1,
    storylineId: slide?.storylineId ?? null,
    slideType: slideLayoutName(slide, matrix),
    ...validateSlide(slide, index, matrix),
  }));
  const deckValidation = validateDeck(slides, matrix);
  const errors = [
    ...deckValidation.errors.map((error) => ({ scope: "deck", ...error })),
    ...results.flatMap((result) => (
      result.errors.map((error) => ({ scope: "slide", slide: result.slide, ...error }))
    )),
  ];
  const warnings = [
    ...deckValidation.warnings.map((warning) => ({ scope: "deck", ...warning })),
    ...results.flatMap((result) => (
      result.warnings.map((warning) => ({ scope: "slide", slide: result.slide, ...warning }))
    )),
  ];
  const validatorPayload = await fs.readFile(fileURLToPath(import.meta.url));
  const report = {
    schemaVersion: SCHEMA_VERSION,
    validatorSha256: sha256(validatorPayload),
    passed: errors.length === 0,
    inputHashes: {
      contentSha256: sha256(contentPayload),
      matrixSha256: sha256(matrixPayload),
    },
    slideCount: results.length,
    errorCount: errors.length,
    warningCount: warnings.length,
    errors,
    warnings,
    deckErrors: deckValidation.errors,
    deckWarnings: deckValidation.warnings,
    takeawayUsage: deckValidation.usage,
    results,
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
