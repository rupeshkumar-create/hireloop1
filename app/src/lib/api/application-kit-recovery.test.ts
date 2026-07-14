import assert from "node:assert/strict";
import test from "node:test";

import {
  APPLICATION_KIT_CONNECTIVITY_MESSAGE,
  createApplicationKitError,
  retryApplicationKitRequest,
  toApplicationKitFailure,
} from "./application-kit-recovery.ts";

const noWait = async (_delayMs: number): Promise<void> => undefined;

test("retries a transient application-kit request", async () => {
  let calls = 0;

  const result = await retryApplicationKitRequest(
    async () => {
      calls += 1;
      if (calls === 1) {
        throw Object.assign(new Error("offline"), { name: "ApiUnreachableError" });
      }
      return { status: 200 };
    },
    { sleep: noWait },
  );

  assert.equal(result.status, 200);
  assert.equal(calls, 2);
});

test("retries a transient application-kit gateway response", async () => {
  let calls = 0;

  const result = await retryApplicationKitRequest(
    async () => ({ status: ++calls === 1 ? 503 : 200 }),
    { sleep: noWait },
  );

  assert.equal(result.status, 200);
  assert.equal(calls, 2);
});

test("connectivity failures never expose infrastructure", () => {
  const raw = Object.assign(
    new Error("Can't reach API at https://railway.example: Failed to fetch"),
    { name: "ApiUnreachableError" },
  );

  const safe = toApplicationKitFailure(raw);

  assert.equal(safe.kind, "connectivity");
  assert.equal(safe.message, APPLICATION_KIT_CONNECTIVITY_MESSAGE);
  assert.doesNotMatch(safe.message, /railway|failed to fetch/i);
});

test("non-connectivity failures use generic recovery copy", () => {
  const safe = toApplicationKitFailure(new Error("secret provider detail"));

  assert.equal(safe.kind, "failed");
  assert.equal(safe.message, "We couldn't finish your application kit. Please retry.");
  assert.doesNotMatch(safe.message, /secret provider detail/i);
});

test("safe application-kit errors preserve recovery kind without raw details", () => {
  const raw = Object.assign(new Error("Failed to fetch https://railway.example"), {
    name: "ApiUnreachableError",
  });

  const safeError = createApplicationKitError(raw);
  const failure = toApplicationKitFailure(safeError);

  assert.equal(failure.kind, "connectivity");
  assert.equal(safeError.message, APPLICATION_KIT_CONNECTIVITY_MESSAGE);
  assert.doesNotMatch(safeError.message, /railway|failed to fetch/i);
});
