import assert from "node:assert/strict";
import test from "node:test";

import {
  canReportClientError,
  classifyClientLoadError,
  createClientErrorReport,
  createReloadMarker,
  sanitizeClientErrorText,
  sanitizeClientErrorReport,
  shouldReloadOnce,
} from "./client-error-report.ts";

test("client error reports require an authenticated user", () => {
  assert.equal(canReportClientError(null), false);
  assert.equal(canReportClientError(""), false);
  assert.equal(canReportClientError("authenticated-user"), true);
});

test("classifies deployment-transition chunk failures", () => {
  assert.equal(
    classifyClientLoadError(new Error("ChunkLoadError: Loading chunk 123 failed")),
    "chunk_load",
  );
  assert.equal(
    classifyClientLoadError(
      new Error("Failed to fetch dynamically imported module: /_next/static/chunk.js"),
    ),
    "chunk_load",
  );
  assert.equal(classifyClientLoadError(new Error("ordinary render bug")), "other");
});

test("reload guard permits one reload per path inside the recovery window", () => {
  const now = 1_000_000;
  const marker = createReloadMarker("/dashboard", now);

  assert.equal(shouldReloadOnce("/dashboard", null, now), true);
  assert.equal(shouldReloadOnce("/dashboard", marker, now + 30_000), false);
  assert.equal(shouldReloadOnce("/dashboard", marker, now + 61_000), true);
  assert.equal(shouldReloadOnce("/jobs", marker, now + 1_000), true);
});

test("sanitizes URLs, query strings, and control characters", () => {
  const sanitized = sanitizeClientErrorText(
    "fetch https://secret.example/path?token=abc\nFailed to fetch",
    300,
  );

  assert.doesNotMatch(sanitized, /https|secret\.example|token=abc|\n/);
  assert.match(sanitized, /\[url\]/);
});

test("client report is bounded and never includes stack or query data", () => {
  const error = Object.assign(
    new Error(`ChunkLoadError ${"x".repeat(500)}`),
    { digest: "digest-value", stack: "Bearer secret-token" },
  );

  const report = createClientErrorReport(error, "/dashboard?token=secret");

  assert.equal(report.classification, "chunk_load");
  assert.equal(report.pathname, "/dashboard");
  assert.ok(report.name.length <= 80);
  assert.ok(report.message.length <= 300);
  assert.ok(report.digest === undefined || report.digest.length <= 120);
  assert.equal("stack" in report, false);
  assert.doesNotMatch(JSON.stringify(report), /secret-token|token=secret/);
});

test("server-side report sanitization removes hostile URLs and query data", () => {
  const report = sanitizeClientErrorReport({
    name: "ChunkLoadError",
    message: "failed at https://railway.example/private?token=abc",
    digest: "digest",
    pathname: "/dashboard?access_token=secret",
    classification: "chunk_load",
  });

  assert.equal(report.pathname, "/dashboard");
  assert.doesNotMatch(JSON.stringify(report), /railway|token=abc|access_token/);
});
