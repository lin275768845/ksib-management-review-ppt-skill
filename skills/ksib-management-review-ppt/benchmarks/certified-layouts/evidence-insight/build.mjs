#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL = path.resolve(HERE, "../../..");
const OUTPUT = path.resolve(process.argv[2] || path.join(HERE, "output"));
const NODE = process.execPath;
const PYTHON = process.env.PYTHON || "python3";

function run(command, args) {
  const result = spawnSync(command, args, { cwd: HERE, encoding: "utf8", stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited with ${result.status}`);
}

await fs.mkdir(OUTPUT, { recursive: true });
const renderPlan = path.join(OUTPUT, "render-plan.json");
const pptx = path.join(OUTPUT, "KSIB_EVIDENCE_INSIGHT_CERTIFIED_GOLDEN_V1.pptx");
const previews = path.join(OUTPUT, "render");
const fidelity = path.join(OUTPUT, "layout-fidelity-gate.json");
const ooxml = path.join(OUTPUT, "ooxml-gate.json");

run(NODE, [path.join(SKILL, "scripts", "resolve_render_plan.mjs"), "--input", path.join(HERE, "render-plan-input.json"), "--output", renderPlan]);
run(NODE, [path.join(SKILL, "scripts", "render_certified_layout.mjs"), "--render-plan", renderPlan, "--content", path.join(HERE, "content.json"), "--output", pptx, "--preview-dir", previews]);
run(PYTHON, [path.join(SKILL, "scripts", "ooxml_sanitize.py"), pptx, "--in-place"]);
run(PYTHON, [path.join(SKILL, "scripts", "ooxml_qa.py"), pptx, "--theme-policy", "ksib", "--font-policy", "ksib", "--allow-unresolved-markers", "--output", ooxml]);
run(PYTHON, [path.join(SKILL, "scripts", "validate_layout_fidelity.py"), "--pptx", pptx, "--render-plan", renderPlan, "--output", fidelity]);

console.log(JSON.stringify({ passed: true, pptx, renderPlan, ooxml, fidelity, previewDirectory: previews }, null, 2));
