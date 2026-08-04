#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { buildPayloads, cases } from "./fixtures.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SKILL = path.resolve(HERE, "../../..");
const OUTPUT = path.resolve(process.argv[2] || path.join(HERE, "output"));
const PYTHON = process.env.PYTHON || "python3";

function run(command, args) {
  const result = spawnSync(command, args, { cwd: HERE, encoding: "utf8", stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited with ${result.status}`);
}

await fs.mkdir(OUTPUT, { recursive: true });
const registry = JSON.parse(await fs.readFile(path.join(SKILL, "references", "certified-layout-registry.json"), "utf8"));
const { content, renderPlanInput } = buildPayloads(registry);
const inputPath = path.join(OUTPUT, "render-plan-input.json");
const contentPath = path.join(OUTPUT, "content.json");
const planPath = path.join(OUTPUT, "render-plan.json");
const pptxPath = path.join(OUTPUT, "KSIB_CERTIFIED_CORE_LAYOUT_LIBRARY_V2.pptx");
const previews = path.join(OUTPUT, "render");
const ooxml = path.join(OUTPUT, "ooxml-gate.json");
const fidelity = path.join(OUTPUT, "layout-fidelity-gate.json");

await fs.writeFile(inputPath, `${JSON.stringify(renderPlanInput, null, 2)}\n`, "utf8");
await fs.writeFile(contentPath, `${JSON.stringify(content, null, 2)}\n`, "utf8");
run(process.execPath, [path.join(SKILL, "scripts", "resolve_render_plan.mjs"), "--input", inputPath, "--output", planPath]);
run(process.execPath, [path.join(SKILL, "scripts", "render_certified_layout.mjs"), "--render-plan", planPath, "--content", contentPath, "--output", pptxPath, "--preview-dir", previews]);
run(PYTHON, [path.join(SKILL, "scripts", "ooxml_sanitize.py"), pptxPath, "--in-place"]);
run(PYTHON, [path.join(SKILL, "scripts", "ooxml_qa.py"), pptxPath, "--theme-policy", "ksib", "--font-policy", "ksib", "--allow-unresolved-markers", "--output", ooxml]);
run(PYTHON, [path.join(SKILL, "scripts", "validate_layout_fidelity.py"), "--pptx", pptxPath, "--render-plan", planPath, "--output", fidelity]);

console.log(JSON.stringify({ passed: true, layouts: new Set(cases.map((item) => item.layoutId)).size, slides: cases.length, pptx: pptxPath, previews, ooxml, fidelity }, null, 2));
