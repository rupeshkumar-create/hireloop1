import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const careerApiSource = await readFile(
  new URL("../src/lib/api/career.ts", import.meta.url),
  "utf8",
);

test("career-path generation allows a long-running LLM response", () => {
  assert.match(
    careerApiSource,
    /apiAuthFetch\(\s*"\/api\/v1\/career\/path\/generate",\s*\{[\s\S]*?method:\s*"POST"[\s\S]*?\},\s*\{\s*timeoutMs:\s*120_000\s*\},?\s*\)/,
  );
});
