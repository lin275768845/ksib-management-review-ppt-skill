#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import {
  FileBlob,
  PresentationFile,
} from "@oai/artifact-tool";

const input = path.resolve(process.argv[2] ?? "");
const output = path.resolve(process.argv[3] ?? "roundtrip.pptx");
if (!process.argv[2]) {
  throw new Error("Usage: node roundtrip.mjs INPUT.pptx OUTPUT.pptx");
}

const presentation = await PresentationFile.importPptx(
  await FileBlob.load(input),
);
const inspection = await presentation.inspect({
  kind: "slide,textbox,shape,table,chart,notes,layout",
  maxChars: 50000,
});
await fs.writeFile(
  `${output}.inspect.ndjson`,
  inspection.ndjson,
  "utf-8",
);
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(output);
