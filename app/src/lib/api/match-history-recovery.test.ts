import assert from "node:assert/strict";
import test from "node:test";

import { loadMatchHistoryWithRecovery } from "./match-history-recovery.ts";

test("retries a transient history response before returning jobs", async () => {
  let calls = 0;
  const jobs = [{ job_id: "job-1" }];

  const result = await loadMatchHistoryWithRecovery(
    async () => {
      calls += 1;
      return calls === 1
        ? { ok: false, status: 503, jobs: [] }
        : { ok: true, status: 200, jobs };
    },
    { sleep: async () => undefined },
  );

  assert.equal(calls, 2);
  assert.deepEqual(result.jobs, jobs);
});

test("does not retry an authentication failure", async () => {
  let calls = 0;

  const result = await loadMatchHistoryWithRecovery(
    async () => {
      calls += 1;
      return { ok: false, status: 401, jobs: [] };
    },
    { sleep: async () => undefined },
  );

  assert.equal(calls, 1);
  assert.equal(result.status, 401);
});
