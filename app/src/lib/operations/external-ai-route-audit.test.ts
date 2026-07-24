import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

type RouteRule = {
  id: string;
  /** Matches path fragments as written in frontend sources (including `${…}`). */
  match: RegExp;
};

/**
 * Intentionally real-time / interactive synchronous external-AI routes.
 * Holding the HTTP/WS request open is required for conversational latency.
 * Paths mirror the string templates in app/src (Aarya, Nitya, voice, mock interview,
 * public portfolio chat).
 */
const REALTIME_EXTERNAL_AI_ALLOWLIST: readonly RouteRule[] = [
  {
    id: "aarya-chat-message-stream",
    // `/api/v1/chat/sessions/${conversationId}/messages`
    match: /\/api\/v1\/chat\/sessions\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/messages/,
  },
  {
    id: "voice-config",
    // `/api/v1/voice/config`
    match: /\/api\/v1\/voice\/config/,
  },
  {
    id: "voice-stt",
    // `/api/v1/voice/stt`
    match: /\/api\/v1\/voice\/stt/,
  },
  {
    id: "voice-tts",
    // `/api/v1/voice/tts`
    match: /\/api\/v1\/voice\/tts/,
  },
  {
    id: "voice-live-stream",
    // `/api/v1/voice/stream?sr=…`
    match: /\/api\/v1\/voice\/stream/,
  },
  {
    id: "nitya-chat-messages",
    // `/api/v1/recruiter/roles/${roleId}/chat/messages`
    match: /\/api\/v1\/recruiter\/roles\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/chat\/messages/,
  },
  {
    id: "mock-interview-messages",
    // `/api/v1/mock-interview/sessions/${id}/messages`
    match: /\/api\/v1\/mock-interview\/sessions\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/messages/,
  },
  {
    id: "public-profile-chat-messages",
    // `/api/v1/public/profiles/${encodeURIComponent(slug)}/chat/messages`
    match:
      /\/api\/v1\/public\/profiles\/(?:\$\{[^}]+\}|encodeURIComponent\([^)]+\)|[^"'`\s?/]+)\/chat\/messages/,
  },
  {
    id: "public-profile-chat-stream",
    // `/api/v1/public/profiles/${encodeURIComponent(slug)}/chat/stream`
    match:
      /\/api\/v1\/public\/profiles\/(?:\$\{[^}]+\}|encodeURIComponent\([^)]+\)|[^"'`\s?/]+)\/chat\/stream/,
  },
] as const;

/**
 * Sync frontend→API surfaces that still run analysis / extraction on the request
 * thread. They remain callable so CI stays green, but must be explicitly listed;
 * new undocumented sync AI routes still fail the inventory check below.
 * Pending durable `ai_operations` conversion when cost/latency warrants it.
 */
const DEFERRED_SYNC_AI_ROUTES: readonly RouteRule[] = [
  {
    id: "candidate-analyze-jd",
    // `/api/v1/me/chat/analyze-jd` — ChatInterface JD paste analysis
    match: /\/api\/v1\/me\/chat\/analyze-jd/,
  },
  {
    id: "candidate-analyze-resume",
    // `/api/v1/me/chat/analyze-resume`
    match: /\/api\/v1\/me\/chat\/analyze-resume/,
  },
  {
    id: "recruiter-analyze-resume",
    // `/api/v1/recruiter/roles/${roleId}/analyze-resume`
    match: /\/api\/v1\/recruiter\/roles\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/analyze-resume/,
  },
  {
    id: "recruiter-import-role-url",
    // `/api/v1/recruiter/roles/import-url` — sync OpenRouter JD extract
    match: /\/api\/v1\/recruiter\/roles\/import-url/,
  },
  {
    id: "recruiter-re-extract-role",
    // `/api/v1/recruiter/roles/${roleId}/re-extract` — sync OpenRouter JD extract
    match: /\/api\/v1\/recruiter\/roles\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/re-extract/,
  },
] as const;

/**
 * Known synchronous external-AI (or sync analysis) routes the frontend may call.
 * Every frontend reference must be allowlisted (realtime) or deferred.
 */
const SYNCHRONOUS_EXTERNAL_AI_INVENTORY: readonly RouteRule[] = [
  ...REALTIME_EXTERNAL_AI_ALLOWLIST,
  ...DEFERRED_SYNC_AI_ROUTES,
] as const;

/**
 * Broad discovery patterns for sync AI-shaped paths. A frontend hit that matches
 * discovery but is missing from the inventory fails as "undocumented".
 */
const SYNC_AI_DISCOVERY_PATTERNS: readonly RegExp[] = [
  /\/api\/v1\/chat\/sessions\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/messages/,
  /\/api\/v1\/voice\/(?:config|stt|tts|stream)/,
  /\/api\/v1\/recruiter\/roles\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/chat\/messages/,
  /\/api\/v1\/mock-interview\/sessions\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/messages/,
  /\/api\/v1\/public\/profiles\/(?:\$\{[^}]+\}|encodeURIComponent\([^)]+\)|[^"'`\s?/]+)\/chat\/(?:messages|stream)/,
  /\/api\/v1\/me\/chat\/analyze-(?:jd|resume)/,
  /\/api\/v1\/recruiter\/roles\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/analyze-resume/,
  /\/api\/v1\/recruiter\/roles\/import-url/,
  /\/api\/v1\/recruiter\/roles\/(?:\$\{[^}]+\}|[^"'`\s?/]+)\/re-extract/,
];

/** Generation submits that return 202 — must use the ordinary ≤25s request budget. */
const QUEUED_GENERATION_PATH_MARKERS = [
  "/api/v1/career/path/generate",
  "/api/v1/career/intelligence/generate",
  "/api/v1/career/path-resumes/generate",
  "/api/v1/tailored-resumes/tailor",
  "/api/v1/learning-roadmaps/roadmap",
  "/api/v1/application-kits/jobs/",
  "/api/v1/resumes/upload",
] as const;

const ORDINARY_REQUEST_BUDGET_MS = 25_000;

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

function globalize(pattern: RegExp): RegExp {
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  return new RegExp(pattern.source, flags);
}

function isAllowlisted(sample: string): boolean {
  return REALTIME_EXTERNAL_AI_ALLOWLIST.some((rule) => rule.match.test(sample));
}

function isDeferred(sample: string): boolean {
  return DEFERRED_SYNC_AI_ROUTES.some((rule) => rule.match.test(sample));
}

function isInventoried(sample: string): boolean {
  return SYNCHRONOUS_EXTERNAL_AI_INVENTORY.some((rule) => rule.match.test(sample));
}

function collectMatches(source: string, pattern: RegExp): string[] {
  return [...source.matchAll(globalize(pattern))].map((m) => m[0]);
}

describe("external AI route audit", () => {
  it("fails when frontend calls inventory sync-AI routes outside allowlist/deferred", async () => {
    const files = await collectSourceFiles(APP_SRC_ROOT);
    const violations: string[] = [];

    for (const file of files) {
      if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) continue;
      const source = await readFile(file, "utf8");
      const rel = path.relative(APP_SRC_ROOT, file);

      for (const rule of SYNCHRONOUS_EXTERNAL_AI_INVENTORY) {
        for (const sample of collectMatches(source, rule.match)) {
          if (isAllowlisted(sample) || isDeferred(sample)) continue;
          violations.push(
            `${rel}: inventory route ${rule.id} (${sample}) is not allowlisted or deferred`,
          );
        }
      }

      for (const discovery of SYNC_AI_DISCOVERY_PATTERNS) {
        for (const sample of collectMatches(source, discovery)) {
          if (isInventoried(sample)) continue;
          violations.push(
            `${rel}: undocumented sync AI-shaped path ${sample} — add to allowlist or DEFERRED_SYNC_AI_ROUTES`,
          );
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
          // Look at a window around the call site (path + nearby options).
          const window = source.slice(Math.max(0, idx - 120), idx + 500);
          const timeoutMatch = window.match(elevatedTimeout);
          if (timeoutMatch?.[1]) {
            const ms = Number(timeoutMatch[1].replace(/_/g, ""));
            if (ms > ORDINARY_REQUEST_BUDGET_MS) {
              violations.push(
                `${rel}: ${marker} uses timeoutMs ${ms} (must enqueue via ai_operations; budget ≤${ORDINARY_REQUEST_BUDGET_MS})`,
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

  it("deferred sync AI routes remain explicitly listed while still referenced", async () => {
    const files = await collectSourceFiles(APP_SRC_ROOT);
    const sources = await Promise.all(
      files
        .filter((f) => !f.endsWith(".test.ts") && !f.endsWith(".test.tsx"))
        .map(async (f) => readFile(f, "utf8")),
    );
    const joined = sources.join("\n");

    for (const rule of DEFERRED_SYNC_AI_ROUTES) {
      expect(joined, `deferred route ${rule.id} no longer referenced — remove from deferred list`).toMatch(
        rule.match,
      );
    }
  });
});
