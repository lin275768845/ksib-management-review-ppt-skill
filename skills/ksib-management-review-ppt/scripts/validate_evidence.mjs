import fs from "node:fs/promises";
import { readFileSync } from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const SCHEMA_VERSION = "ksib-evidence-gate/2.0";
const VALIDATOR_PATH = fileURLToPath(import.meta.url);
const HERE = path.dirname(VALIDATOR_PATH);
const MATRIX_PATH = path.resolve(HERE, "../references/layout-matrix.json");
const MATRIX_PAYLOAD = readFileSync(MATRIX_PATH, "utf8");
const LAYOUT_MATRIX = JSON.parse(MATRIX_PAYLOAD);
const SUPPORTED_CONTRACT_VERSIONS = new Set(["1.0"]);
const ID_PATTERN = /^[A-Za-z][A-Za-z0-9_.:-]*$/;
const INPUT_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_]*$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DATE_LIKE_PATTERN = /\b\d{4}-\d{1,2}-\d{1,2}\b/g;
const FORMULA_FUNCTIONS = new Set([
  "abs",
  "avg",
  "ceil",
  "exp",
  "floor",
  "log",
  "max",
  "min",
  "pow",
  "round",
  "sqrt",
  "sum",
]);
const CLAIM_TYPES = new Set(["quantitative", "qualitative", "recommendation", "methodology"]);
const EXEMPT_LAYOUTS = new Set([
  "cover",
  "toc",
  "agenda",
  "section",
  "sectionDivider",
  "section_divider",
  "appendixDivider",
  "appendix_divider",
  "styleboards",
  "styleboardSystem",
  "styleboardDensity",
]);
const EXEMPT_LAYOUT_ROLES = new Map([
  ["cover", new Set(["cover"])],
  ["toc", new Set(["navigator"])],
  ["agenda", new Set(["navigator"])],
  ["section", new Set(["navigator"])],
  ["sectionDivider", new Set(["navigator"])],
  ["section_divider", new Set(["navigator"])],
  ["appendixDivider", new Set(["appendix"])],
  ["appendix_divider", new Set(["appendix"])],
  ["styleboards", new Set(["navigator"])],
  ["styleboardSystem", new Set(["navigator"])],
  ["styleboardDensity", new Set(["navigator"])],
]);
const EXPLICIT_EVIDENCE_EXEMPTIONS = new Map([
  ["methodology", {
    type: "method_boundary",
    layouts: new Set(["appendixTable", "appendixQA"]),
  }],
  ["scope_boundary", {
    type: "scope_boundary",
    layouts: new Set(["appendixTable", "appendixQA"]),
  }],
  ["legal_disclaimer", {
    type: "legal_boundary",
    layouts: new Set(["appendixQA"]),
  }],
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

function hasText(value) {
  return value != null && String(value).trim().length > 0;
}

function hasStructuredValue(value) {
  if (hasText(value)) return true;
  if (Array.isArray(value)) return value.length > 0;
  return value != null && typeof value === "object" && Object.keys(value).length > 0;
}

function isPlainObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function normalizeUnit(value) {
  return String(value ?? "").trim().toLocaleLowerCase("en");
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (isPlainObject(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function uniqueValues(values) {
  return [...new Set(values)];
}

function canonicalLayoutName(layoutName, matrix = LAYOUT_MATRIX) {
  const aliases = matrix?.global?.layoutAliases || {};
  let canonical = layoutName;
  const visited = new Set();
  while (aliases[canonical] && !visited.has(canonical)) {
    visited.add(canonical);
    canonical = aliases[canonical];
  }
  return canonical;
}

function parseIsoDate(value) {
  const text = String(value ?? "").trim();
  if (!DATE_PATTERN.test(text)) return null;
  const [year, month, day] = text.split("-").map(Number);
  const epoch = Date.UTC(year, month - 1, day);
  const date = new Date(epoch);
  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) {
    return null;
  }
  return { text, epoch };
}

function parsePeriodRange(period) {
  if (typeof period === "string") {
    const dateTokens = period.match(DATE_LIKE_PATTERN) || [];
    if (!dateTokens.length) return null;
    const parsed = dateTokens.map(parseIsoDate);
    if (parsed.some((value) => value == null)) return null;
    const range = {
      start: parsed[0].epoch,
      end: parsed[parsed.length - 1].epoch,
    };
    return range.start <= range.end ? range : null;
  }
  if (!isPlainObject(period)) return null;
  if (hasText(period.asOfDate)) {
    const asOf = parseIsoDate(period.asOfDate);
    return asOf ? { start: asOf.epoch, end: asOf.epoch } : null;
  }
  const start = parseIsoDate(period.startDate);
  const end = parseIsoDate(period.endDate);
  if (!start || !end) return null;
  return start.epoch <= end.epoch ? { start: start.epoch, end: end.epoch } : null;
}

function validatePeriodField(period, scope, id, errors) {
  if (!hasStructuredValue(period)) {
    addError(errors, "period_missing", scope, id, "period为必填字段");
    return null;
  }
  if (typeof period === "string") {
    const text = period.trim();
    const durationMatches = [...text.matchAll(/(-?\d+(?:\.\d+)?)\s*(?:日|天|周|月|季|年)/g)];
    if (durationMatches.some((match) => Number(match[1]) <= 0)) {
      addError(errors, "period_duration_invalid", scope, id, "期间长度必须大于0");
    }
    const dateTokens = text.match(DATE_LIKE_PATTERN) || [];
    const parsed = dateTokens.map(parseIsoDate);
    if (parsed.some((value) => value == null)) {
      addError(errors, "period_date_invalid", scope, id, "period中的日期必须为真实存在的YYYY-MM-DD");
      return null;
    }
    if (parsed.length >= 2 && parsed[0].epoch > parsed[parsed.length - 1].epoch) {
      addError(errors, "period_range_invalid", scope, id, "period开始日期不得晚于结束日期");
    }
    return parsed.length
      ? { start: parsed[0].epoch, end: parsed[parsed.length - 1].epoch }
      : null;
  }
  if (!isPlainObject(period)) {
    addError(errors, "period_invalid", scope, id, "period必须为非空字符串或日期范围对象");
    return null;
  }
  const hasAsOf = hasText(period.asOfDate);
  const hasStart = hasText(period.startDate);
  const hasEnd = hasText(period.endDate);
  if (hasAsOf && (hasStart || hasEnd)) {
    addError(errors, "period_contract_ambiguous", scope, id, "period不得同时声明asOfDate与startDate/endDate");
    return null;
  }
  if (hasAsOf) {
    const asOf = parseIsoDate(period.asOfDate);
    if (!asOf) {
      addError(errors, "period_date_invalid", scope, id, "period.asOfDate必须为真实存在的YYYY-MM-DD");
      return null;
    }
    return { start: asOf.epoch, end: asOf.epoch };
  }
  if (!hasStart || !hasEnd) {
    addError(errors, "period_range_incomplete", scope, id, "period日期范围必须同时声明startDate与endDate");
    return null;
  }
  const start = parseIsoDate(period.startDate);
  const end = parseIsoDate(period.endDate);
  if (!start || !end) {
    addError(errors, "period_date_invalid", scope, id, "period日期必须为真实存在的YYYY-MM-DD");
    return null;
  }
  if (start.epoch > end.epoch) {
    addError(errors, "period_range_invalid", scope, id, "period.startDate不得晚于period.endDate");
  }
  return { start: start.epoch, end: end.epoch };
}

function formulaIdentifiers(formula) {
  const variables = new Set();
  const unsupportedFunctions = new Set();
  const text = String(formula ?? "");
  const pattern = /[A-Za-z_][A-Za-z0-9_]*/g;
  for (const match of text.matchAll(pattern)) {
    if (match.index > 0 && /[A-Za-z0-9_]/.test(text[match.index - 1])) continue;
    const token = match[0];
    const isFunction = /^\s*\(/.test(text.slice(match.index + token.length));
    if (isFunction) {
      if (!FORMULA_FUNCTIONS.has(token.toLocaleLowerCase("en"))) {
        unsupportedFunctions.add(token);
      }
    } else {
      variables.add(token);
    }
  }
  return { variables, unsupportedFunctions };
}

function validateInputPeriodCoverage(calculation, referenced, inputIndex, errors) {
  const calculationRange = parsePeriodRange(calculation.period);
  const referencedRange = parsePeriodRange(referenced?.period);
  if (!calculationRange || !referencedRange) return;
  if (
    calculationRange.start < referencedRange.start
    || calculationRange.end > referencedRange.end
  ) {
    addError(
      errors,
      "calculation_input_period_out_of_range",
      `calculations.inputs[${inputIndex}]`,
      calculation.id,
      `Calculation期间必须落在引用对象${referenced.id ?? "unknown"}的期间内`,
    );
  }
}

function addError(errors, rule, scope, id, detail) {
  errors.push({ rule, scope, id: id ?? null, detail });
}

function addWarning(warnings, rule, scope, id, detail) {
  warnings.push({ rule, scope, id: id ?? null, detail });
}

function validateId(value, scope, index, registry, errors) {
  const location = `${scope}[${index}]`;
  if (!hasText(value)) {
    addError(errors, "id_missing", scope, location, "id为必填字段");
    return null;
  }
  if (!ID_PATTERN.test(value)) {
    addError(errors, "id_invalid", scope, value, "id必须以英文字母开头，且只能包含字母、数字、_、.、:、-");
  }
  if (registry.has(value)) {
    addError(errors, "duplicate_id", scope, value, `与${registry.get(value)}重复；Source、Calculation和Claim共用全局ID命名空间`);
  } else {
    registry.set(value, location);
  }
  return value;
}

function validateStringField(object, field, scope, id, errors) {
  if (!hasText(object?.[field])) {
    addError(errors, `${field}_missing`, scope, id, `${field}为必填字段`);
  }
}

function validateStructuredField(object, field, scope, id, errors) {
  if (!hasStructuredValue(object?.[field])) {
    addError(errors, `${field}_missing`, scope, id, `${field}为必填字段`);
  }
}

function validateReferenceArray(object, field, scope, id, errors) {
  const value = object?.[field];
  if (value == null) return [];
  if (!Array.isArray(value)) {
    addError(errors, `${field}_not_array`, scope, id, `${field}必须为数组`);
    return [];
  }
  const usable = value.filter(hasText);
  if (usable.length !== value.length) {
    addError(errors, `${field}_contains_empty`, scope, id, `${field}不得包含空ID`);
  }
  if (uniqueValues(usable).length !== usable.length) {
    addError(errors, `${field}_duplicate_reference`, scope, id, `${field}不得重复引用同一ID`);
  }
  return usable;
}

function isRatioMetric(metricType, unit) {
  const metric = String(metricType ?? "").toLocaleLowerCase("en");
  const ratioWords = [
    "share",
    "rate",
    "ratio",
    "penetration",
    "conversion",
    "concentration",
    "percentage",
    "margin",
  ];
  return normalizeUnit(unit) === "%" || normalizeUnit(unit) === "pct" || ratioWords.some((word) => metric.includes(word)) || /^cr\d*$/.test(metric);
}

function isBrandShareMetric(metricType) {
  const metric = String(metricType ?? "").toLocaleLowerCase("en");
  return /^cr\d+$/.test(metric)
    || /brand.*(?:share|concentration|cr\d*)/.test(metric);
}

function denominatorSignature(denominator) {
  if (!isPlainObject(denominator)) return "";
  return stableStringify({
    scope: denominator.scope,
    includesUnidentified: denominator.includesUnidentified,
    exclusions: Array.isArray(denominator.exclusions)
      ? [...denominator.exclusions].map((value) => String(value).trim()).sort()
      : [],
  });
}

function validateDenominator(denominator, { scope, id, metricType, errors }) {
  if (!isPlainObject(denominator)) {
    addError(errors, "denominator_missing", scope, id, "比率类指标必须声明denominator对象");
    return;
  }
  validateStringField(denominator, "name", `${scope}.denominator`, id, errors);
  validateStringField(denominator, "scope", `${scope}.denominator`, id, errors);
  if (typeof denominator.includesUnidentified !== "boolean") {
    addError(
      errors,
      "includes_unidentified_missing",
      `${scope}.denominator`,
      id,
      "includesUnidentified必须显式设置为true或false",
    );
  }
  if (denominator.exclusions != null && !Array.isArray(denominator.exclusions)) {
    addError(errors, "denominator_exclusions_not_array", `${scope}.denominator`, id, "exclusions必须为数组");
  }
  const exclusions = Array.isArray(denominator.exclusions)
    ? denominator.exclusions.map((value) => String(value).toLocaleLowerCase("zh-CN"))
    : [];
  const excludesUnidentified = exclusions.some((value) => /unidentified|unknown|未识别/.test(value));
  if (denominator.includesUnidentified === true && excludesUnidentified) {
    addError(
      errors,
      "denominator_policy_contradiction",
      `${scope}.denominator`,
      id,
      "includesUnidentified=true但exclusions排除了未识别品牌",
    );
  }
  if (isBrandShareMetric(metricType) && denominator.includesUnidentified !== true) {
    addError(
      errors,
      "unidentified_denominator_excluded",
      `${scope}.denominator`,
      id,
      "品牌份额或集中度必须以包含未识别品牌GMV的全样本为分母",
    );
  }
}

function validateSource(source, index, registry, errors) {
  const id = validateId(source?.id, "sources", index, registry, errors) ?? `sources[${index}]`;
  if (!isPlainObject(source)) {
    addError(errors, "source_not_object", "sources", id, "Source必须为对象");
    return;
  }
  for (const field of ["title", "sourceType", "locator", "dataVersion", "verificationMethod"]) {
    validateStringField(source, field, "sources", id, errors);
  }
  const periodRange = validatePeriodField(source.period, "sources", id, errors);
  if (source.verificationStatus !== "verified") {
    addError(
      errors,
      "source_not_verified",
      "sources",
      id,
      `verificationStatus必须为verified，当前为${source.verificationStatus ?? "missing"}`,
    );
  }
  const verifiedAt = parseIsoDate(source.verifiedAt);
  if (!verifiedAt) {
    addError(errors, "verified_at_invalid", "sources", id, "verifiedAt必须为真实存在的YYYY-MM-DD");
  } else if (periodRange && periodRange.end > verifiedAt.epoch) {
    addError(errors, "source_period_after_verification", "sources", id, "Source期间结束日期不得晚于verifiedAt");
  }
}

function validateCalculation(calculation, index, registry, errors) {
  const id = validateId(calculation?.id, "calculations", index, registry, errors) ?? `calculations[${index}]`;
  if (!isPlainObject(calculation)) {
    addError(errors, "calculation_not_object", "calculations", id, "Calculation必须为对象");
    return;
  }
  for (const field of ["label", "metricType", "formula", "unit", "dataVersion"]) {
    validateStringField(calculation, field, "calculations", id, errors);
  }
  validatePeriodField(calculation.period, "calculations", id, errors);
  const inputNames = new Set();
  if (!Array.isArray(calculation.inputs) || calculation.inputs.length === 0) {
    addError(errors, "calculation_inputs_missing", "calculations", id, "inputs[]至少包含一个计算输入");
  } else {
    calculation.inputs.forEach((input, inputIndex) => {
      const inputScope = `calculations.inputs[${inputIndex}]`;
      if (!isPlainObject(input)) {
        addError(errors, "calculation_input_not_object", inputScope, id, "每个input必须为对象");
        return;
      }
      if (!hasText(input.name) || !INPUT_NAME_PATTERN.test(input.name)) {
        addError(errors, "calculation_input_name_invalid", inputScope, id, "input.name必须为英文字段名");
      } else if (inputNames.has(input.name)) {
        addError(errors, "calculation_input_name_duplicate", inputScope, id, `重复input.name：${input.name}`);
      } else {
        inputNames.add(input.name);
      }
      const referenceFields = ["sourceId", "claimId", "calculationId"].filter((field) => hasText(input[field]));
      if (referenceFields.length !== 1) {
        addError(
          errors,
          "calculation_input_reference_invalid",
          inputScope,
          id,
          "每个input必须且只能设置sourceId、claimId、calculationId中的一个",
        );
      }
      if (hasText(input.sourceId) && !hasText(input.locator)) {
        addError(errors, "calculation_input_locator_missing", inputScope, id, "引用Source时必须精确声明locator");
      }
    });
  }
  if (hasText(calculation.formula)) {
    if (!/^[A-Za-z0-9_+\-*/%^().,\s]+$/.test(calculation.formula)) {
      addError(
        errors,
        "formula_character_invalid",
        "calculations",
        id,
        "公式只能使用显式input英文字段名、数字、支持函数和算术符号",
      );
    }
    const { variables, unsupportedFunctions } = formulaIdentifiers(calculation.formula);
    for (const functionName of unsupportedFunctions) {
      addError(
        errors,
        "formula_function_unsupported",
        "calculations",
        id,
        `公式使用了未支持函数：${functionName}`,
      );
    }
    for (const inputName of inputNames) {
      if (!variables.has(inputName)) {
        addError(
          errors,
          "formula_input_not_used",
          "calculations",
          id,
          `公式未使用input：${inputName}`,
        );
      }
    }
    for (const variable of variables) {
      if (!inputNames.has(variable)) {
        addError(
          errors,
          "formula_variable_unresolved",
          "calculations",
          id,
          `公式变量未解析到显式input：${variable}`,
        );
      }
    }
  }
  if (isRatioMetric(calculation.metricType, calculation.unit)) {
    validateDenominator(calculation.denominator, {
      scope: "calculations",
      id,
      metricType: calculation.metricType,
      errors,
    });
    if (hasText(calculation.formula) && !calculation.formula.includes("/")) {
      addError(errors, "ratio_formula_missing_division", "calculations", id, "比率类公式必须显式包含除法符号/");
    }
  }
}

function validateClaim(claim, index, registry, errors) {
  const id = validateId(claim?.id, "claims", index, registry, errors) ?? `claims[${index}]`;
  if (!isPlainObject(claim)) {
    addError(errors, "claim_not_object", "claims", id, "Claim必须为对象");
    return;
  }
  for (const field of ["statement", "claimType"]) validateStringField(claim, field, "claims", id, errors);
  if (hasText(claim.claimType) && !CLAIM_TYPES.has(claim.claimType)) {
    addError(errors, "claim_type_invalid", "claims", id, `claimType=${claim.claimType}`);
  }
  const sourceIds = validateReferenceArray(claim, "sourceIds", "claims", id, errors);
  const calculationIds = validateReferenceArray(claim, "calculationIds", "claims", id, errors);
  if (sourceIds.length + calculationIds.length === 0) {
    addError(errors, "claim_evidence_missing", "claims", id, "Claim必须至少引用一个Source或Calculation");
  }
  if (claim.claimType === "quantitative") {
    validateStringField(claim, "metricType", "claims", id, errors);
    validatePeriodField(claim.period, "claims", id, errors);
    validateStringField(claim, "unit", "claims", id, errors);
    validateStringField(claim, "dataVersion", "claims", id, errors);
    if (isRatioMetric(claim.metricType, claim.unit)) {
      validateDenominator(claim.denominator, {
        scope: "claims",
        id,
        metricType: claim.metricType,
        errors,
      });
    }
  }
}

function validateRetainedReason(object, scope, errors) {
  if (object?.retainedForAudit === true && !hasText(object.retainedReason)) {
    addError(errors, "retained_reason_missing", scope, object.id, "retainedForAudit=true时必须填写retainedReason");
  }
}

function validateCrossReferences({ sources, calculations, claims, sourceById, calculationById, claimById, errors }) {
  for (const claim of claims) {
    if (!isPlainObject(claim)) continue;
    for (const sourceId of Array.isArray(claim.sourceIds) ? claim.sourceIds : []) {
      if (!sourceById.has(sourceId)) {
        addError(errors, "claim_source_reference_missing", "claims", claim.id, `不存在Source：${sourceId}`);
      }
    }
    for (const calculationId of Array.isArray(claim.calculationIds) ? claim.calculationIds : []) {
      const calculation = calculationById.get(calculationId);
      if (!calculation) {
        addError(errors, "claim_calculation_reference_missing", "claims", claim.id, `不存在Calculation：${calculationId}`);
        continue;
      }
      if (claim.claimType !== "quantitative") continue;
      if (stableStringify(claim.period) !== stableStringify(calculation.period)) {
        addError(errors, "claim_calculation_period_mismatch", "claims", claim.id, `${calculationId}的period不一致`);
      }
      if (normalizeUnit(claim.unit) !== normalizeUnit(calculation.unit)) {
        addError(errors, "claim_calculation_unit_mismatch", "claims", claim.id, `${calculationId}的unit不一致`);
      }
      if (claim.dataVersion !== calculation.dataVersion) {
        addError(errors, "claim_calculation_version_mismatch", "claims", claim.id, `${calculationId}的dataVersion不一致`);
      }
      if (
        isRatioMetric(claim.metricType, claim.unit)
        && denominatorSignature(claim.denominator) !== denominatorSignature(calculation.denominator)
      ) {
        addError(errors, "claim_calculation_denominator_mismatch", "claims", claim.id, `${calculationId}的分母口径不一致`);
      }
    }
  }

  for (const calculation of calculations) {
    if (!isPlainObject(calculation) || !Array.isArray(calculation.inputs)) continue;
    calculation.inputs.forEach((input, index) => {
      if (!isPlainObject(input)) return;
      if (hasText(input.sourceId)) {
        const source = sourceById.get(input.sourceId);
        if (!source) {
          addError(
            errors,
            "calculation_source_reference_missing",
            `calculations.inputs[${index}]`,
            calculation.id,
            `不存在Source：${input.sourceId}`,
          );
        } else {
          validateInputPeriodCoverage(calculation, source, index, errors);
        }
      }
      if (hasText(input.claimId)) {
        const claim = claimById.get(input.claimId);
        if (!claim) {
          addError(
            errors,
            "calculation_claim_reference_missing",
            `calculations.inputs[${index}]`,
            calculation.id,
            `不存在Claim：${input.claimId}`,
          );
        } else {
          validateInputPeriodCoverage(calculation, claim, index, errors);
        }
      }
      if (hasText(input.calculationId)) {
        const dependency = calculationById.get(input.calculationId);
        if (!dependency) {
          addError(
            errors,
            "calculation_reference_missing",
            `calculations.inputs[${index}]`,
            calculation.id,
            `不存在Calculation：${input.calculationId}`,
          );
        } else {
          validateInputPeriodCoverage(calculation, dependency, index, errors);
        }
      }
    });
  }

  for (const object of [...sources, ...calculations, ...claims]) {
    if (isPlainObject(object)) validateRetainedReason(object, "evidence", errors);
  }
}

function validateDependencyCycles({ calculations, claims, calculationById, claimById, errors }) {
  const graph = new Map();
  for (const claim of claims) {
    if (!isPlainObject(claim) || !hasText(claim.id)) continue;
    graph.set(
      `claim:${claim.id}`,
      (Array.isArray(claim.calculationIds) ? claim.calculationIds : [])
        .filter((id) => calculationById.has(id))
        .map((id) => `calculation:${id}`),
    );
  }
  for (const calculation of calculations) {
    if (!isPlainObject(calculation) || !hasText(calculation.id)) continue;
    const dependencies = [];
    for (const input of Array.isArray(calculation.inputs) ? calculation.inputs : []) {
      if (hasText(input?.claimId) && claimById.has(input.claimId)) dependencies.push(`claim:${input.claimId}`);
      if (hasText(input?.calculationId) && calculationById.has(input.calculationId)) {
        dependencies.push(`calculation:${input.calculationId}`);
      }
    }
    graph.set(`calculation:${calculation.id}`, dependencies);
  }

  const state = new Map();
  const stack = [];
  const reportedCycles = new Set();
  function visit(node) {
    if (state.get(node) === "done") return;
    if (state.get(node) === "visiting") {
      const start = stack.indexOf(node);
      const cycle = [...stack.slice(start), node];
      const signature = [...new Set(cycle)].sort().join("|");
      if (!reportedCycles.has(signature)) {
        reportedCycles.add(signature);
        addError(errors, "evidence_dependency_cycle", "evidence", node, cycle.join(" → "));
      }
      return;
    }
    state.set(node, "visiting");
    stack.push(node);
    for (const dependency of graph.get(node) || []) visit(dependency);
    stack.pop();
    state.set(node, "done");
  }
  for (const node of graph.keys()) visit(node);
}

function validateContent(content, claimById, errors) {
  const slides = Array.isArray(content) ? content : content?.slides;
  if (!Array.isArray(slides)) {
    addError(errors, "content_slides_missing", "content", null, "Content必须为数组或包含slides[]");
    return { slides: [], rootClaimIds: new Set(), stats: { total: 0, withClaims: 0, exempt: 0 } };
  }
  if (slides.length === 0) {
    addError(errors, "content_slides_empty", "content", null, "完整Evidence门禁不接受空slides[]");
  }
  const rootClaimIds = new Set();
  let withClaims = 0;
  let exempt = 0;
  slides.forEach((slide, index) => {
    const slideId = slide?.storylineId ?? slide?.id ?? `slide-${index + 1}`;
    const rawSlideType = slide?.layoutContract ?? slide?.slideType ?? "";
    const slideType = canonicalLayoutName(rawSlideType);
    const defaultExemptRoles = EXEMPT_LAYOUT_ROLES.get(slideType);
    const defaultExempt = defaultExemptRoles?.has(slide?.slideRole) === true;
    if (EXEMPT_LAYOUTS.has(slideType) && !defaultExempt) {
      addError(
        errors,
        "evidence_exempt_layout_role_mismatch",
        "content",
        slideId,
        `${slideType}只有在slideRole=${[...(defaultExemptRoles || [])].join("或")}时才可获得Evidence豁免；当前为${slide?.slideRole ?? "(missing)"}`,
      );
    }
    const explicitExemptRequested = slide?.evidenceExempt === true;
    let explicitExempt = false;
    if (explicitExemptRequested) {
      const exemptionContract = EXPLICIT_EVIDENCE_EXEMPTIONS.get(slide?.slideRole);
      if (!exemptionContract) {
        addError(
          errors,
          "evidence_exempt_role_invalid",
          "content",
          slideId,
          "只有methodology、scope_boundary或legal_disclaimer角色允许显式Evidence豁免",
        );
      } else if (slide?.evidenceExemptType !== exemptionContract.type) {
        addError(
          errors,
          "evidence_exempt_type_invalid",
          "content",
          slideId,
          `slideRole=${slide?.slideRole}时evidenceExemptType必须为${exemptionContract.type}`,
        );
      } else if (!exemptionContract.layouts.has(slideType)) {
        addError(
          errors,
          "evidence_exempt_layout_invalid",
          "content",
          slideId,
          `slideRole=${slide?.slideRole}只允许在${[...exemptionContract.layouts].join(", ")}申请Evidence豁免`,
        );
      } else if (!hasText(slide.evidenceExemptReason) || String(slide.evidenceExemptReason).trim().length < 12) {
        addError(
          errors,
          "evidence_exempt_reason_missing",
          "content",
          slideId,
          "Evidence豁免必须提供至少12个字符的具体边界说明",
        );
      } else {
        explicitExempt = true;
      }
    }
    const isExempt = defaultExempt || explicitExempt;
    if (isExempt) exempt += 1;
    if (slide?.claimIds != null && !Array.isArray(slide.claimIds)) {
      addError(errors, "slide_claim_ids_not_array", "content", slideId, "claimIds必须为数组");
      return;
    }
    const claimIds = Array.isArray(slide?.claimIds) ? slide.claimIds.filter(hasText) : [];
    if (claimIds.length) withClaims += 1;
    if (uniqueValues(claimIds).length !== claimIds.length) {
      addError(errors, "slide_claim_ids_duplicate", "content", slideId, "同一页面不得重复引用同一Claim");
    }
    if (!isExempt && claimIds.length === 0) {
      addError(errors, "slide_claim_ids_missing", "content", slideId, "实质内容页必须引用至少一个Claim");
    }
    for (const claimId of claimIds) {
      if (!claimById.has(claimId)) {
        addError(errors, "slide_claim_reference_missing", "content", slideId, `不存在Claim：${claimId}`);
      } else {
        rootClaimIds.add(claimId);
      }
    }
  });
  return { slides, rootClaimIds, stats: { total: slides.length, withClaims, exempt } };
}

function computeReachability({
  rootClaimIds,
  sources,
  calculations,
  claims,
  sourceById,
  calculationById,
  claimById,
}) {
  const reachableSources = new Set();
  const reachableCalculations = new Set();
  const reachableClaims = new Set();

  function visitSource(id) {
    if (sourceById.has(id)) reachableSources.add(id);
  }
  function visitClaim(id) {
    if (!claimById.has(id) || reachableClaims.has(id)) return;
    reachableClaims.add(id);
    const claim = claimById.get(id);
    for (const sourceId of Array.isArray(claim.sourceIds) ? claim.sourceIds : []) visitSource(sourceId);
    for (const calculationId of Array.isArray(claim.calculationIds) ? claim.calculationIds : []) {
      visitCalculation(calculationId);
    }
  }
  function visitCalculation(id) {
    if (!calculationById.has(id) || reachableCalculations.has(id)) return;
    reachableCalculations.add(id);
    const calculation = calculationById.get(id);
    for (const input of Array.isArray(calculation.inputs) ? calculation.inputs : []) {
      if (hasText(input?.sourceId)) visitSource(input.sourceId);
      if (hasText(input?.claimId)) visitClaim(input.claimId);
      if (hasText(input?.calculationId)) visitCalculation(input.calculationId);
    }
  }

  for (const id of rootClaimIds) visitClaim(id);
  for (const source of sources) if (source?.retainedForAudit === true) visitSource(source.id);
  for (const calculation of calculations) if (calculation?.retainedForAudit === true) visitCalculation(calculation.id);
  for (const claim of claims) if (claim?.retainedForAudit === true) visitClaim(claim.id);

  return { reachableSources, reachableCalculations, reachableClaims };
}

function validateOrphans({ sources, calculations, claims, reachability, errors }) {
  const collections = [
    ["sources", sources, reachability.reachableSources],
    ["calculations", calculations, reachability.reachableCalculations],
    ["claims", claims, reachability.reachableClaims],
  ];
  for (const [scope, items, reachable] of collections) {
    for (const item of items) {
      if (!isPlainObject(item) || !hasText(item.id)) continue;
      if (!reachable.has(item.id)) {
        addError(
          errors,
          "orphan_evidence",
          scope,
          item.id,
          "对象不能从任何slide.claimIds追溯；如确需保留，请设置retainedForAudit和retainedReason",
        );
      }
    }
  }
}

function validateEvidence(evidence, content, options = {}) {
  const errors = [];
  const warnings = [];
  const registry = new Map();

  if (!isPlainObject(evidence)) {
    addError(errors, "evidence_not_object", "evidence", null, "Evidence Contract必须为对象");
    return {
      passed: false,
      errorCount: errors.length,
      warningCount: 0,
      errors,
      warnings,
      coverage: {},
    };
  }
  validateStringField(evidence, "contractVersion", "evidence", null, errors);
  if (
    hasText(evidence.contractVersion)
    && !SUPPORTED_CONTRACT_VERSIONS.has(String(evidence.contractVersion).trim())
  ) {
    addError(
      errors,
      "contract_version_unsupported",
      "evidence",
      null,
      `contractVersion仅支持：${[...SUPPORTED_CONTRACT_VERSIONS].join(", ")}`,
    );
  }
  validateStringField(evidence, "deckId", "evidence", null, errors);
  const arrayFields = ["sources", "calculations", "claims"];
  for (const field of arrayFields) {
    if (!Array.isArray(evidence[field])) {
      addError(errors, `${field}_missing`, "evidence", null, `${field}必须存在且为数组`);
    }
  }
  const sources = Array.isArray(evidence.sources) ? evidence.sources : [];
  const calculations = Array.isArray(evidence.calculations) ? evidence.calculations : [];
  const claims = Array.isArray(evidence.claims) ? evidence.claims : [];

  sources.forEach((source, index) => validateSource(source, index, registry, errors));
  calculations.forEach((calculation, index) => validateCalculation(calculation, index, registry, errors));
  claims.forEach((claim, index) => validateClaim(claim, index, registry, errors));

  const sourceById = new Map(sources.filter((item) => isPlainObject(item) && hasText(item.id)).map((item) => [item.id, item]));
  const calculationById = new Map(calculations.filter((item) => isPlainObject(item) && hasText(item.id)).map((item) => [item.id, item]));
  const claimById = new Map(claims.filter((item) => isPlainObject(item) && hasText(item.id)).map((item) => [item.id, item]));

  validateCrossReferences({
    sources,
    calculations,
    claims,
    sourceById,
    calculationById,
    claimById,
    errors,
  });
  validateDependencyCycles({ calculations, claims, calculationById, claimById, errors });

  const hasBrandShare = [...calculations, ...claims].some((item) => isPlainObject(item) && isBrandShareMetric(item.metricType));
  if (hasBrandShare && evidence.policies?.brandShareDenominator !== "all_sample_including_unidentified") {
    addError(
      errors,
      "brand_denominator_policy_missing_or_invalid",
      "evidence.policies",
      null,
      "存在品牌份额指标时，brandShareDenominator必须为all_sample_including_unidentified",
    );
  }

  const registryOnly = options.registryOnly === true;
  const contentValidation = registryOnly
    ? { rootClaimIds: new Set(), stats: { total: 0, withClaims: 0, exempt: 0 } }
    : validateContent(content, claimById, errors);
  const reachability = registryOnly
    ? {
        reachableSources: new Set(sources.map((item) => item?.id).filter(hasText)),
        reachableCalculations: new Set(calculations.map((item) => item?.id).filter(hasText)),
        reachableClaims: new Set(claims.map((item) => item?.id).filter(hasText)),
      }
    : computeReachability({
        rootClaimIds: contentValidation.rootClaimIds,
        sources,
        calculations,
        claims,
        sourceById,
        calculationById,
        claimById,
      });
  if (!registryOnly) {
    validateOrphans({ sources, calculations, claims, reachability, errors });
  }

  const coverage = {
    sources: {
      total: sources.length,
      verified: sources.filter((source) => source?.verificationStatus === "verified").length,
      reachable: reachability.reachableSources.size,
    },
    calculations: {
      total: calculations.length,
      reachable: reachability.reachableCalculations.size,
    },
    claims: {
      total: claims.length,
      referencedBySlides: contentValidation.rootClaimIds.size,
      reachable: reachability.reachableClaims.size,
    },
    slides: contentValidation.stats,
  };
  if (sources.length === 0) addWarning(warnings, "no_sources", "evidence", null, "合同中没有Source");
  if (claims.length === 0) addWarning(warnings, "no_claims", "evidence", null, "合同中没有Claim");

  return {
    passed: errors.length === 0,
    contractVersion: evidence.contractVersion ?? null,
    deckId: evidence.deckId ?? null,
    errorCount: errors.length,
    warningCount: warnings.length,
    errors,
    warnings,
    mode: registryOnly ? "registry-only" : "full",
    coverage,
  };
}

function validFixture() {
  const evidence = {
    contractVersion: "1.0",
    deckId: "self-test",
    policies: { brandShareDenominator: "all_sample_including_unidentified" },
    sources: [
      {
        id: "SRC_PLATFORM_A",
        title: "平台A审计底表",
        sourceType: "internal_dataset",
        locator: "platform_a.xlsx",
        period: "8周榜单",
        dataVersion: "V1.0",
        verificationStatus: "verified",
        verifiedAt: "2026-07-20",
        verificationMethod: "与商品周均汇总重算",
      },
    ],
    calculations: [
      {
        id: "CAL_CR5",
        label: "品牌CR5",
        metricType: "brand_concentration",
        formula: "top5_gmv / all_sample_gmv",
        inputs: [
          { name: "top5_gmv", sourceId: "SRC_PLATFORM_A", locator: "品牌汇总Top5 GMV" },
          { name: "all_sample_gmv", sourceId: "SRC_PLATFORM_A", locator: "全样本GMV" },
        ],
        period: "8周榜单",
        unit: "%",
        denominator: {
          name: "全样本GMV",
          scope: "all_sample",
          includesUnidentified: true,
          exclusions: [],
        },
        dataVersion: "V1.0",
      },
    ],
    claims: [
      {
        id: "CLM_CR5",
        statement: "品牌CR5为42.0%",
        claimType: "quantitative",
        metricType: "brand_concentration",
        sourceIds: [],
        calculationIds: ["CAL_CR5"],
        period: "8周榜单",
        unit: "%",
        denominator: {
          name: "全样本GMV",
          scope: "all_sample",
          includesUnidentified: true,
          exclusions: [],
        },
        dataVersion: "V1.0",
      },
    ],
  };
  const content = {
    slides: [
      { storylineId: "S1", slideType: "cover", slideRole: "cover", title: "封面" },
      { storylineId: "S2", slideType: "evidenceInsight", slideRole: "evidence", title: "品牌集中度较高", claimIds: ["CLM_CR5"] },
    ],
  };
  return { evidence, content };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function expectRule(name, evidence, content, rule, results) {
  const report = validateEvidence(evidence, content);
  if (!report.errors.some((error) => error.rule === rule)) {
    throw new Error(`${name} did not emit ${rule}:\n${JSON.stringify(report, null, 2)}`);
  }
  results.push(name);
}

function expectPass(name, evidence, content, results) {
  const report = validateEvidence(evidence, content);
  if (!report.passed) {
    throw new Error(`${name} did not pass:\n${JSON.stringify(report, null, 2)}`);
  }
  results.push(name);
}

async function runSelfTest() {
  const results = [];
  const base = validFixture();
  const valid = validateEvidence(base.evidence, base.content);
  if (!valid.passed) throw new Error(`valid_contract failed:\n${JSON.stringify(valid, null, 2)}`);
  results.push("valid_contract");
  {
    const fixture = clone(base);
    fixture.content.slides[0] = {
      storylineId: "S1",
      slideType: "section-divider",
      slideRole: "navigator",
      title: "章节导航",
    };
    expectPass(
      "layout_alias_uses_canonical_role_exemption",
      fixture.evidence,
      fixture.content,
      results,
    );
  }
  const registryOnly = validateEvidence(base.evidence, null, { registryOnly: true });
  if (!registryOnly.passed || registryOnly.mode !== "registry-only") {
    throw new Error(`registry_only failed:\n${JSON.stringify(registryOnly, null, 2)}`);
  }
  results.push("registry_only_contract");

  {
    const fixture = clone(base);
    fixture.evidence.contractVersion = "2.0";
    expectRule(
      "unsupported_contract_version_rejected",
      fixture.evidence,
      fixture.content,
      "contract_version_unsupported",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.sources[0].verifiedAt = "2026-02-30";
    expectRule(
      "impossible_verification_date_rejected",
      fixture.evidence,
      fixture.content,
      "verified_at_invalid",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.sources[0].period = {
      startDate: "2026-06-30",
      endDate: "2026-06-01",
    };
    expectRule(
      "reversed_period_rejected",
      fixture.evidence,
      fixture.content,
      "period_range_invalid",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.sources[0].period = {
      startDate: "2026-07-01",
      endDate: "2026-07-21",
    };
    expectRule(
      "source_period_after_verification_rejected",
      fixture.evidence,
      fixture.content,
      "source_period_after_verification",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.sources[0].period = {
      startDate: "2026-01-01",
      endDate: "2026-06-30",
    };
    fixture.evidence.calculations[0].period = {
      startDate: "2026-01-01",
      endDate: "2026-07-31",
    };
    fixture.evidence.claims[0].period = clone(fixture.evidence.calculations[0].period);
    expectRule(
      "calculation_input_period_out_of_range_rejected",
      fixture.evidence,
      fixture.content,
      "calculation_input_period_out_of_range",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.sources.push({ ...fixture.evidence.sources[0] });
    expectRule("global_duplicate_id_rejected", fixture.evidence, fixture.content, "duplicate_id", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.sources[0].verificationStatus = "draft";
    expectRule("unverified_source_rejected", fixture.evidence, fixture.content, "source_not_verified", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.claims[0].sourceIds = [];
    fixture.evidence.claims[0].calculationIds = [];
    expectRule("claim_without_evidence_rejected", fixture.evidence, fixture.content, "claim_evidence_missing", results);
  }
  {
    const fixture = clone(base);
    delete fixture.evidence.claims[0].period;
    expectRule("quantitative_metadata_required", fixture.evidence, fixture.content, "period_missing", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.claims[0].denominator.includesUnidentified = false;
    expectRule("unidentified_brand_denominator_rejected", fixture.evidence, fixture.content, "unidentified_denominator_excluded", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.claims[0].metricType = "cr5";
    fixture.evidence.calculations[0].metricType = "cr5";
    fixture.evidence.claims[0].denominator.includesUnidentified = false;
    expectRule("bare_cr_metric_denominator_rejected", fixture.evidence, fixture.content, "unidentified_denominator_excluded", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.policies.brandShareDenominator = "identified_only";
    expectRule("brand_denominator_policy_rejected", fixture.evidence, fixture.content, "brand_denominator_policy_missing_or_invalid", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.claims[0].calculationIds = ["CAL_MISSING"];
    expectRule("missing_claim_calculation_rejected", fixture.evidence, fixture.content, "claim_calculation_reference_missing", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.calculations[0].formula = "top5_gmv / denominator";
    expectRule("unused_calculation_input_rejected", fixture.evidence, fixture.content, "formula_input_not_used", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.calculations[0].formula = "top5_gmv / unknown_denominator";
    expectRule(
      "unknown_formula_variable_rejected",
      fixture.evidence,
      fixture.content,
      "formula_variable_unresolved",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.calculations[0].formula = "top5_gmv / 未知分母";
    expectRule(
      "non_contract_formula_token_rejected",
      fixture.evidence,
      fixture.content,
      "formula_character_invalid",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.calculations.push({
      id: "CAL_BASE",
      label: "样本GMV基数",
      metricType: "gmv",
      formula: "base_gmv",
      inputs: [
        { name: "base_gmv", sourceId: "SRC_PLATFORM_A", locator: "全样本GMV" },
      ],
      period: "8周榜单",
      unit: "LCY",
      dataVersion: "V1.0",
    });
    fixture.evidence.calculations[0].inputs.push({
      name: "base_metric",
      calculationId: "CAL_BASE",
    });
    fixture.evidence.calculations[0].formula = "(top5_gmv + base_metric) / all_sample_gmv";
    expectPass(
      "calculation_reference_named_input_supported",
      fixture.evidence,
      fixture.content,
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.calculations.push({
      id: "CAL_BASE",
      label: "样本GMV基数",
      metricType: "gmv",
      formula: "base_gmv",
      inputs: [
        { name: "base_gmv", sourceId: "SRC_PLATFORM_A", locator: "全样本GMV" },
      ],
      period: "8周榜单",
      unit: "LCY",
      dataVersion: "V1.0",
    });
    fixture.evidence.calculations[0].inputs.push({
      name: "base_metric",
      calculationId: "CAL_BASE",
    });
    fixture.evidence.calculations[0].formula = "(top5_gmv + CAL_BASE) / all_sample_gmv";
    expectRule(
      "calculation_reference_must_use_input_name",
      fixture.evidence,
      fixture.content,
      "formula_variable_unresolved",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.evidence.calculations[0].formula = "mystery(top5_gmv) / all_sample_gmv";
    expectRule(
      "unsupported_formula_function_rejected",
      fixture.evidence,
      fixture.content,
      "formula_function_unsupported",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.content.slides[1].claimIds = [];
    expectRule("slide_without_claim_rejected", fixture.evidence, fixture.content, "slide_claim_ids_missing", results);
  }
  {
    const fixture = clone(base);
    fixture.content.slides[0].slideRole = "evidence";
    expectRule(
      "content_role_cannot_gain_cover_evidence_exemption",
      fixture.evidence,
      fixture.content,
      "evidence_exempt_layout_role_mismatch",
      results,
    );
    expectRule(
      "cover_layout_role_bypass_still_requires_claim",
      fixture.evidence,
      fixture.content,
      "slide_claim_ids_missing",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.content.slides[1] = {
      ...fixture.content.slides[1],
      evidenceExempt: true,
      evidenceExemptReason: "随便写一个理由也不应绕过证据门禁",
    };
    expectRule("arbitrary_evidence_exemption_rejected", fixture.evidence, fixture.content, "evidence_exempt_role_invalid", results);
  }
  {
    const fixture = clone(base);
    fixture.content.slides.push({
      storylineId: "S3",
      slideType: "appendixQA",
      slideRole: "methodology",
      title: "方法与边界",
      evidenceExempt: true,
      evidenceExemptType: "method_boundary",
      evidenceExemptReason: "本页仅说明抽样和计算方法边界，不承载新的客户可见事实主张",
    });
    expectPass(
      "valid_methodology_exemption_contract",
      fixture.evidence,
      fixture.content,
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.content.slides[1] = {
      ...fixture.content.slides[1],
      slideRole: "methodology",
      evidenceExempt: true,
      evidenceExemptType: "method_boundary",
      evidenceExemptReason: "把实质证据页伪装成方法页不能绕过Evidence门禁",
    };
    expectRule(
      "substantive_layout_cannot_impersonate_methodology",
      fixture.evidence,
      fixture.content,
      "evidence_exempt_layout_invalid",
      results,
    );
  }
  {
    const fixture = clone(base);
    fixture.content.slides[1].claimIds = ["CLM_MISSING"];
    expectRule("missing_slide_claim_rejected", fixture.evidence, fixture.content, "slide_claim_reference_missing", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.sources.push({
      ...fixture.evidence.sources[0],
      id: "SRC_UNUSED",
      title: "未使用来源",
    });
    expectRule("orphan_source_rejected", fixture.evidence, fixture.content, "orphan_evidence", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.calculations[0].inputs.push({
      name: "loop_value",
      calculationId: "CAL_CR5",
    });
    fixture.evidence.calculations[0].formula = "(top5_gmv + loop_value) / all_sample_gmv";
    expectRule("dependency_cycle_rejected", fixture.evidence, fixture.content, "evidence_dependency_cycle", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.claims[0].dataVersion = "V2.1";
    expectRule("claim_calculation_version_drift_rejected", fixture.evidence, fixture.content, "claim_calculation_version_mismatch", results);
  }
  {
    const fixture = clone(base);
    fixture.evidence.claims[0].period = "8周周榜";
    expectRule(
      "claim_calculation_period_drift_rejected",
      fixture.evidence,
      fixture.content,
      "claim_calculation_period_mismatch",
      results,
    );
  }

  console.log(JSON.stringify({ passed: true, tests: results }, null, 2));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["self-test"]) {
    await runSelfTest();
    return;
  }
  if (!args.evidence || (!args.content && !args["registry-only"])) {
    throw new Error("Missing --evidence；完整门禁还需--content，或使用--registry-only");
  }
  const evidencePath = path.resolve(args.evidence);
  const evidencePayload = await fs.readFile(evidencePath, "utf8");
  const evidence = JSON.parse(evidencePayload);
  const contentPath = args.content ? path.resolve(args.content) : null;
  const contentPayload = contentPath ? await fs.readFile(contentPath, "utf8") : null;
  const validatorPayload = await fs.readFile(VALIDATOR_PATH);
  const content = contentPayload
    ? JSON.parse(contentPayload)
    : null;
  const report = validateEvidence(evidence, content, {
    registryOnly: args["registry-only"] === true,
  });
  report.schemaVersion = SCHEMA_VERSION;
  report.validatorSha256 = sha256(validatorPayload);
  report.inputHashes = {
    evidenceSha256: sha256(evidencePayload),
    contentSha256: contentPayload ? sha256(contentPayload) : null,
    matrixSha256: sha256(MATRIX_PAYLOAD),
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
