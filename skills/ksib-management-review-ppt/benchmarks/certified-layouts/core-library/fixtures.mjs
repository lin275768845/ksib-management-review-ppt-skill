const P = "[占位]";

const block = (title, count, prefix = "关键判断") => ({
  title: `${P} ${title}`,
  items: Array.from({ length: count }, (_, index) => `${prefix}${index + 1}需由证据验证`),
});

const chart = (count, percent = false) => ({
  componentId: "native-chart",
  categories: Array.from({ length: count }, (_, index) => `类别${String.fromCharCode(65 + index)}`),
  values: Array.from({ length: count }, (_, index) => percent ? (0.18 + index * 0.09) : (18 + index * 9)),
  seriesName: percent ? "占比" : "指数",
  focusIndex: count - 1,
  valueFormat: percent ? "percent-0" : "integer",
});

const table = (columns, rows) => ({
  componentId: "native-table",
  headers: Array.from({ length: columns }, (_, index) => index === 0 ? "模块" : `指标${index}`),
  rows: Array.from({ length: rows }, (_, row) => Array.from({ length: columns }, (_, column) => column === 0 ? `对象${row + 1}` : `${(row + 1) * (column + 2) * 10}`)),
  focusCell: { row: rows - 1, column: Math.min(columns - 1, 2) },
});

const common = (layoutId, variantId, state, title, slotContent, itemCounts = {}) => ({
  layoutId,
  variantId,
  state,
  storylineId: `GOLDEN-${layoutId.toUpperCase().replace(/[^A-Z0-9]/g, "-")}-${state.toUpperCase()}`,
  header: `CORE｜${layoutId}`,
  title: `${P} ${title}`,
  subtitle: variantId.includes("subtitle") ? `${P} 边界：脱敏Golden样张` : null,
  source: `数据来源：${P} Certified Core Golden Library脱敏虚构数据`,
  slotContent,
  itemCounts,
});

function executive(state, count) {
  const pillars = [block("结构性判断", count), block("关键证据", count), block("决策影响", count)];
  return common("executiveSummary", "three-pillar-standard", state, "决策摘要将三项证据收敛为明确请求", {
    decisionLead: `${P} 当前证据支持聚焦一个主决策，并以三项支柱形成完整论证。`,
    pillars,
    decisionAsk: block("决策请求", state === "sparse" ? 0 : 1, "批准下一步动作"),
    focusIndex: 0,
  }, {
    pillar1: count + 1, pillar2: count + 1, pillar3: count + 1, decisionAsk: state === "sparse" ? 1 : 2,
  });
}
function single(state, variantId, exhibit) {
  return common("singleExhibit", variantId, state, "单一主证据直接支撑本页结论", { mainExhibit: exhibit }, {
    ...(exhibit.componentId === "native-table" ? { mainExhibit: (exhibit.rows.length + 1) * exhibit.headers.length } : {}),
  });
}

function evidence(state, variantId, categories, insights) {
  return common("evidenceInsight", variantId, state, "主证据与管理含义保持唯一对应", {
    mainExhibit: chart(categories, true),
    insightTitle: "管理含义",
    insightLead: `${P} 资源应聚焦最强证据对应的关键路径`,
    insightItems: Array.from({ length: insights }, (_, index) => `洞察${index + 1}保持可验证且不重复标题`),
  }, { insightItems: insights });
}

function tableInsight(state, columns, rows, insights) {
  const exhibit = table(columns, rows);
  return common("tableInsight", "right-panel-standard", state, "表格差异指向清晰的优先级判断", {
    mainExhibit: exhibit,
    insightTitle: "管理含义",
    insightLead: `${P} 横向差异说明资源配置需要重新排序`,
    insightItems: Array.from({ length: insights }, (_, index) => `洞察${index + 1}绑定表格中的明确证据`),
  }, { mainExhibit: (rows + 1) * columns, insightItems: insights });
}

function side(state, count) {
  const columns = [block("方案A｜稳态优化", count), block("方案B｜结构升级", count)];
  return common("sideBySide", "balanced", state, "两种方案在收益、条件与风险上形成明确取舍", { columns, focusIndex: 1 }, {
    leftColumn: count + 1, rightColumn: count + 1,
  });
}

function structured(state, variantId, columnCount, itemCount) {
  const columns = Array.from({ length: columnCount }, (_, index) => block(`路径${index + 1}`, itemCount, "比较维度"));
  return common("structuredComparison", variantId, state, "同构比较让方案差异在统一维度下可判断", { columns, focusIndex: columnCount - 1 }, Object.fromEntries(columns.map((_, index) => [`column${index + 1}`, itemCount + 1])));
}

function matrix(state, itemCount) {
  const quadrants = ["优先投入", "选择性验证", "维持观察", "退出或降级"].map((title) => block(title, itemCount, "判断依据"));
  return common("matrix2x2", "quadrant-standard", state, "组合优先级由价值与可行性共同决定", {
    xAxisLabel: "横轴：实施可行性由低到高",
    yAxisLabel: "纵轴：潜在价值由低到高",
    quadrants,
    focusIndex: 0,
  }, Object.fromEntries(quadrants.map((_, index) => [`quadrant${index + 1}`, itemCount + 1])));
}

function tree(state, branchItems) {
  const root = block("核心决策问题", state === "sparse" ? 0 : 1, "边界条件");
  const branches = [block("需求与价值", branchItems), block("能力与资源", branchItems), block("风险与约束", branchItems)];
  return common("issueTree", "three-branch", state, "三个MECE分支覆盖核心决策的主要验证路径", { root, branches }, {
    root: root.items.length + 1,
    branch1: branchItems + 1, branch2: branchItems + 1, branch3: branchItems + 1,
  });
}

function mapping(state, detailed) {
  const rows = Array.from({ length: 3 }, (_, index) => ({
    problem: block(`问题${index + 1}`, detailed ? 1 : 0, "根因"),
    action: block(`解决动作${index + 1}`, detailed ? 1 : 0, "关键机制"),
    outcome: block(`验证结果${index + 1}`, detailed ? 1 : 0, "判断标准"),
  }));
  const itemCounts = {};
  rows.forEach((row, index) => ["problem", "action", "outcome"].forEach((field) => { itemCounts[`${field}${index + 1}`] = row[field].items.length + 1; }));
  return common("problemSolutionMap", "three-row", state, "问题、行动与验证结果必须逐行一一对应", { rows }, itemCounts);
}

function process(state, variantId, count, items) {
  const stages = Array.from({ length: count }, (_, index) => ({
    title: `${P} 阶段${index + 1}`,
    items: Array.from({ length: items }, (_, itemIndex) => `动作${itemIndex + 1}｜验证`),
  }));
  return common("processValueChain", variantId, state, "端到端流程以清晰交接点形成连续价值链", { stages, focusIndex: Math.floor(count / 2) }, Object.fromEntries(stages.map((_, index) => [`stage${index + 1}`, items + 1])));
}

function playbook(state, variantId, count) {
  const phases = Array.from({ length: count }, (_, index) => ({
    title: `${P} 阶段${index + 1}`,
    logic: `共同逻辑：验证假设${index + 1}`,
    criterion: `判断标准：达到阈值${index + 1}`,
    action: `行动：证据通过后推进`,
  }));
  return common("phasePlaybook", variantId, state, "阶段打法按共同逻辑、标准和行动递进", {
    logicLabels: ["共同逻辑", "判断标准", "关键行动"], phases, focusIndex: 0,
  }, { logicLabels: 3, ...Object.fromEntries(phases.map((_, index) => [`phase${index + 1}`, 4])) });
}

function roadmap(state) {
  const phases = Array.from({ length: 4 }, (_, index) => ({
    title: `${P} 第${index + 1}阶段`,
    recommendation: `建议：完成优先动作${index + 1}`,
    milestone: `里程碑：形成可验证产出${index + 1}`,
    owner: `Owner／条件：角色${index + 1}负责并满足前置条件`,
  }));
  return common("recommendationRoadmap", "four-phase", state, "建议路线图把动作、里程碑与责任条件绑定", {
    logicLabels: ["建议动作", "关键里程碑", "Owner／条件"], phases, focusIndex: 3,
  }, { logicLabels: 3, phase1: 4, phase2: 4, phase3: 4, phase4: 4 });
}

export const cases = [
  executive("sparse", 1), executive("standard", 2), executive("maximum", 3),
  single("sparse", "full-width-chart", chart(2)), single("standard", "full-width-chart", chart(6, true)), single("maximum", "full-width-table", table(6, 6)),
  evidence("sparse", "right-panel-standard", 2, 2), evidence("standard", "bottom-panel-standard", 5, 2), evidence("maximum", "right-panel-subtitle", 6, 3),
  tableInsight("sparse", 3, 2, 2), tableInsight("standard", 4, 4, 3), tableInsight("maximum", 6, 6, 3),
  side("sparse", 2), side("standard", 3), side("maximum", 5),
  structured("sparse", "three-column", 3, 2), structured("standard", "three-column", 3, 4), structured("maximum", "four-column", 4, 4),
  matrix("sparse", 1), matrix("standard", 2), matrix("maximum", 3),
  tree("sparse", 1), tree("standard", 2), tree("maximum", 3),
  mapping("sparse", false), mapping("standard", true), mapping("maximum", true),
  process("sparse", "four-stage", 4, 1), process("standard", "five-stage", 5, 2), process("maximum", "five-stage", 5, 3),
  playbook("sparse", "three-stage", 3), playbook("standard", "four-stage", 4), playbook("maximum", "four-stage", 4),
  roadmap("sparse"), roadmap("standard"), roadmap("maximum"),
];

export function buildPayloads(registry) {
  const slides = cases.map((item, index) => ({
    slide: index + 1,
    storylineId: item.storylineId,
    layoutId: item.layoutId,
    header: item.header,
    title: item.title,
    subtitle: item.subtitle,
    source: item.source,
    slotContent: item.slotContent,
  }));
  const planSlides = cases.map((item, index) => {
    const variant = registry.layouts[item.layoutId].variants[item.variantId];
    const slotBindings = Object.fromEntries(Object.entries(variant.slots).map(([slotId, spec]) => {
      const binding = { componentId: spec.allowedComponents[0], objectName: `${item.storylineId}-${slotId}` };
      if (item.itemCounts[slotId] != null) binding.itemCount = item.itemCounts[slotId];
      return [slotId, binding];
    }));
    return { slide: index + 1, storylineId: item.storylineId, layoutId: item.layoutId, variantId: item.variantId, headerProfile: variant.headerProfile, slotBindings };
  });
  return {
    content: { schemaVersion: "ksib-certified-render-content/2.0", slides },
    renderPlanInput: { schemaVersion: "ksib-render-plan-input/1.0", executionMode: "story-change", slides: planSlides },
  };
}
