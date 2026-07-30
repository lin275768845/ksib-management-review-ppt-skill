#!/usr/bin/env node

import crypto from "node:crypto";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const SELF_PATH = fileURLToPath(import.meta.url);
const SCHEMA_VERSION = "ksib-storyline-gate/1.0";

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) throw new Error(`Unexpected argument: ${token}`);
    const key = token.slice(2);
    if (["self-test", "require-lock"].includes(key)) {
      args[key] = true;
      continue;
    }
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`Missing value for --${key}`);
    args[key] = value;
    index += 1;
  }
  return args;
}

function defaultUpstreamPath() {
  const codexHome = process.env.CODEX_HOME
    ? path.resolve(process.env.CODEX_HOME)
    : path.join(os.homedir(), ".codex");
  return path.join(
    codexHome,
    "skills",
    "linzhe-mbb-storyline",
    "scripts",
    "validate_storyline.mjs",
  );
}

async function runUpstream(upstreamPath, storylinePath, requireLock) {
  const commandArgs = [upstreamPath, "--storyline", storylinePath];
  if (requireLock) commandArgs.push("--require-lock");
  try {
    const { stdout } = await execFileAsync(process.execPath, commandArgs, {
      encoding: "utf8",
      maxBuffer: 8 * 1024 * 1024,
    });
    return JSON.parse(stdout);
  } catch (error) {
    const stdout = String(error?.stdout ?? "").trim();
    if (stdout) {
      try {
        return JSON.parse(stdout);
      } catch {
        // Fall through to the actionable execution error below.
      }
    }
    throw new Error(`Upstream storyline validator failed without a JSON report: ${error.message}`);
  }
}

function buildReport({
  upstreamReport,
  storylinePayload,
  validatorPayload,
  upstreamValidatorPayload,
}) {
  const errors = Array.isArray(upstreamReport.errors) ? upstreamReport.errors : [];
  const warnings = Array.isArray(upstreamReport.warnings) ? upstreamReport.warnings : [];
  const errorCount = Number.isInteger(upstreamReport.errorCount)
    ? upstreamReport.errorCount
    : errors.length;
  const warningCount = Number.isInteger(upstreamReport.warningCount)
    ? upstreamReport.warningCount
    : warnings.length;
  const contractErrors = [];
  if (upstreamReport.passed !== (errorCount === 0)) {
    contractErrors.push({
      rule: "upstream_report_inconsistent",
      detail: "upstream passed状态必须与errorCount一致",
    });
  }
  if (errors.length !== errorCount) {
    contractErrors.push({
      rule: "upstream_error_count_inconsistent",
      detail: `errors.length=${errors.length}, errorCount=${errorCount}`,
    });
  }
  const mergedErrors = [...errors, ...contractErrors];
  return {
    schemaVersion: SCHEMA_VERSION,
    validatorSha256: sha256(validatorPayload),
    upstreamValidatorSha256: sha256(upstreamValidatorPayload),
    inputHashes: {
      storylineSha256: sha256(storylinePayload),
    },
    passed: upstreamReport.passed === true && mergedErrors.length === 0,
    productionReady: upstreamReport.productionReady === true && mergedErrors.length === 0,
    lockStatus: upstreamReport.lockStatus ?? null,
    slideCount: Number.isInteger(upstreamReport.slideCount) ? upstreamReport.slideCount : 0,
    errorCount: mergedErrors.length,
    warningCount,
    errors: mergedErrors,
    warnings,
  };
}

async function validate({ storylinePath, upstreamPath, requireLock }) {
  const [storylinePayload, validatorPayload, upstreamValidatorPayload] = await Promise.all([
    fs.readFile(storylinePath),
    fs.readFile(SELF_PATH),
    fs.readFile(upstreamPath),
  ]);
  const upstreamReport = await runUpstream(upstreamPath, storylinePath, requireLock);
  return buildReport({
    upstreamReport,
    storylinePayload,
    validatorPayload,
    upstreamValidatorPayload,
  });
}

function runSelfTest() {
  const base = {
    upstreamReport: {
      passed: true,
      productionReady: true,
      lockStatus: "approved_by_user",
      slideCount: 2,
      errorCount: 0,
      warningCount: 0,
      errors: [],
      warnings: [],
    },
    storylinePayload: Buffer.from('{"slides":[{},{}]}'),
    validatorPayload: Buffer.from("wrapper-v1"),
    upstreamValidatorPayload: Buffer.from("storyline-validator-v1"),
  };
  const valid = buildReport(base);
  const invalid = buildReport({
    ...base,
    upstreamReport: {
      ...base.upstreamReport,
      passed: false,
      productionReady: false,
      errorCount: 1,
      errors: [{ rule: "human_lock_required" }],
    },
  });
  const inconsistent = buildReport({
    ...base,
    upstreamReport: {
      ...base.upstreamReport,
      passed: true,
      errorCount: 1,
      errors: [],
    },
  });
  const tests = {
    valid_storyline_gate_passes: valid.passed === true,
    failed_upstream_gate_blocks: invalid.passed === false && invalid.errorCount === 1,
    inconsistent_upstream_report_blocks: inconsistent.errors.some(
      (error) => error.rule === "upstream_report_inconsistent",
    ),
    storyline_input_hash_recorded:
      valid.inputHashes.storylineSha256 === sha256(base.storylinePayload),
    validator_hashes_recorded:
      valid.validatorSha256 === sha256(base.validatorPayload)
      && valid.upstreamValidatorSha256 === sha256(base.upstreamValidatorPayload),
  };
  if (Object.values(tests).some((passed) => !passed)) {
    throw new Error(`Self-test failed: ${JSON.stringify(tests)}`);
  }
  process.stdout.write(`${JSON.stringify({ passed: true, tests: Object.keys(tests) }, null, 2)}\n`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args["self-test"]) {
    runSelfTest();
    return;
  }
  if (!args.storyline) throw new Error("Missing --storyline");
  const storylinePath = path.resolve(args.storyline);
  const upstreamPath = path.resolve(args.upstream ?? defaultUpstreamPath());
  const report = await validate({
    storylinePath,
    upstreamPath,
    requireLock: args["require-lock"] === true,
  });
  const output = `${JSON.stringify(report, null, 2)}\n`;
  if (args.report) {
    const reportPath = path.resolve(args.report);
    await fs.mkdir(path.dirname(reportPath), { recursive: true });
    await fs.writeFile(reportPath, output, "utf8");
  }
  process.stdout.write(output);
  if (!report.passed) process.exitCode = 1;
}

main().catch((error) => {
  process.stderr.write(`${JSON.stringify({ passed: false, error: error.message })}\n`);
  process.exitCode = 2;
});
