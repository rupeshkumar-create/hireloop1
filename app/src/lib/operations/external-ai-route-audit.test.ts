import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Intentionally real-time synchronous external-AI routes.
 * Non-interactive generation must go through ai_operations (202) instead.
 */
const REALTIME_EXTERNAL_AI_ALLOWLIST = [
  {
    id: "aarya-chat-message-stream",
    // POST /api/v1/chat/sessions/{id}/messages — OpenRouter SSE turns
    match: /\/api\/v1\/chat\/sessions\/(?:\$\{[^}]+\}|[^"'`\s/]+)\/messages/,
  },
  {
    id: "voice-config",
    match: /\/api\/v1\/voice\/config/,
  },
  {
    id: "voice-stt",
    match: /\/api\/v1\/voice\/stt/,
  },
  {
    id: "voice-tts",
    match: /\/api\/v1\/voice\/tts/,
  },
  {
    id: "voice-live-stream",
    match: /\/api\/v1\/voice\/stream/,
  },
] as const;

/**
 * Frontend-callable routes that still invoke OpenRouter / Deepgram while holding
 * the request open. Keep this list in sync with repository search; only
 * allowlisted entries may appear in app/src.
 */
const SYNCHRONOUS_EXTERNAL_AI_ROUTES = [
  ...REALTIME_EXTERNAL_AI_ALLOWLIST,
  // Converted durable-AI submits — must not reappear as long sync waits.
  // Listed so elevated timeoutMs against them fails the audit below.
] as const;

/** Generation submits that return 202 and must use ordinary request budgets. */
const QUEUED_GENERATION_PATH_MARKERS = [
  "/api/v1/career/path/generate",
  "/api/v1/career/intelligence/generate",
  "/api/v1/career/path-resumes/generate",
  "/api/v1/tailored-resumes/tailor",
  "/api/v1/learning-roadmaps/roadmap",
  "/api/v1/application-kits/jobs/",
  "/api/v1/resumes/upload",
] as const;

const APP_SRC_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".mjs", ".js"]);

async function collectSourceFiles(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") continue;
      files.push(...(await collectSourceFiles(full)));
      continue;
    }
    if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      files.push(full);
    }
  }
  return files;
}

function isAllowlistedPath(sample: string): boolean {
  return REALTIME_EXTERNAL_AI_ALLOWLIST.some((rule) => rule.match.test(sample));
}

describe("external AI route audit", () => {
  it("only allowlisted realtime routes may be called as sync external AI", async () => {
    const files = await collectSourceFiles(APP_SRC_ROOT);
    const violations: string[] = [];

    for (const file of files) {
      if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) continue;
      const source = await readFile(file, "utf8");
      const rel = path.relative(APP_SRC_ROOT, file);

      for (const route of SYNCHRONOUS_EXTERNAL_AI_ROUTES) {
        const matches = source.match(
          new RegExp(route.match.source, route.match.flags.includes("g") ? route.match.flags : `${route.match.flags}g`),
        );
        if (!matches) continue;
        for (const sample of matches) {
          if (!isAllowlistedPath(sample)) {
            violations.push(`${rel}: non-allowlisted sync external-AI call ${sample}`);
          }
        }
      }

      // Catch string-literal API paths that look like known sync AI surfaces
      // beyond the allowlist (e.g. accidental reintroduction of long sync LLM posts).
      const pathLiterals = source.matchAll(
        /["'`](\/api\/v1\/(?:chat\/sessions\/[^"'`]+\/messages|voice\/(?:config|stt|tts|stream)|mock-interview\/sessions\/[^"'`]+\/messages|recruiter\/roles\/[^"'`]+\/chat\/messages|public\/profiles\/[^"'`]+\/chat\/(?:messages|stream)))["'`]/g,
      );
      for (const match of pathLiterals) {
        const apiPath = match[1];
        if (!apiPath) continue;
        // mock-interview / recruiter / public chat are still sync OpenRouter today;
        // this durable-AI gate only enforces the documented allowlist for the
        // Aarya+voice realtime exceptions. Flag them only when they also carry
        // an elevated apiAuthFetch timeout (checked in the next test).
        if (
          apiPath.includes("/chat/sessions/") ||
          apiPath.startsWith("/api/v1/voice/")
        ) {
          if (!isAllowlistedPath(apiPath)) {
            violations.push(`${rel}: ${apiPath} is not on the realtime allowlist`);
          }
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("queued generation submits do not use elevated client timeouts", async () => {
    const files = await collectSourceFiles(APP_SRC_ROOT);
    const violations: string[] = [];
    const elevatedTimeout = /timeoutMs\s*:\s*(\d[\d_]*)/;

    for (const file of files) {
      if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) continue;
      const source = await readFile(file, "utf8");
      const rel = path.relative(APP_SRC_ROOT, file);

      for (const marker of QUEUED_GENERATION_PATH_MARKERS) {
        let from = 0;
        while (from < source.length) {
          const idx = source.indexOf(marker, from);
          if (idx === -1) break;
          const window = source.slice(Math.max(0, idx - 80), idx + 400);
          const timeoutMatch = window.match(elevatedTimeout);
          if (timeoutMatch?.[1]) {
            const ms = Number(timeoutMatch[1].replace(/_/g, ""));
            if (ms > 25_000) {
              violations.push(
                `${rel}: ${marker} uses timeoutMs ${ms} (must enqueue via ai_operations)`,
              );
            }
          }
          from = idx + marker.length;
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("allowlisted realtime surfaces remain present in the frontend", async () => {
    const files = await collectSourceFiles(APP_SRC_ROOT);
    const sources = await Promise.all(
      files
        .filter((f) => !f.endsWith(".test.ts") && !f.endsWith(".test.tsx"))
        .map(async (f) => readFile(f, "utf8")),
    );
    const joined = sources.join("\n");

    for (const rule of REALTIME_EXTERNAL_AI_ALLOWLIST) {
      expect(joined, `missing allowlisted route ${rule.id}`).toMatch(rule.match);
    }
  });
});
