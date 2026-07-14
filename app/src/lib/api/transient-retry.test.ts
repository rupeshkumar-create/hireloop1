import assert from "node:assert/strict";
import test from "node:test";

import { withTransientRetry } from "./transient-retry.ts";

const noWait = async (_delayMs: number): Promise<void> => undefined;

test("retries a transient network error then returns success", async () => {
  let calls = 0;
  const retries: number[] = [];

  const result = await withTransientRetry(
    async () => {
      calls += 1;
      if (calls === 1) throw Object.assign(new Error("offline"), { name: "ApiUnreachableError" });
      return { status: 200 };
    },
    { sleep: noWait, onRetry: ({ delayMs }) => retries.push(delayMs) },
  );

  assert.equal(result.status, 200);
  assert.equal(calls, 2);
  assert.deepEqual(retries, [350]);
});

test("retries a 503 response then returns success", async () => {
  let calls = 0;
  const result = await withTransientRetry(
    async () => ({ status: ++calls === 1 ? 503 : 200 }),
    { sleep: noWait },
  );

  assert.equal(result.status, 200);
  assert.equal(calls, 2);
});

test("does not retry a validation response", async () => {
  let calls = 0;
  const result = await withTransientRetry(
    async () => ({ status: (++calls, 400) }),
    { sleep: noWait },
  );

  assert.equal(result.status, 400);
  assert.equal(calls, 1);
});

test("stops after three total attempts", async () => {
  let calls = 0;
  await assert.rejects(
    withTransientRetry(
      async () => {
        calls += 1;
        throw Object.assign(new Error("offline"), { name: "ApiUnreachableError" });
      },
      { sleep: noWait },
    ),
    /offline/,
  );

  assert.equal(calls, 3);
});
