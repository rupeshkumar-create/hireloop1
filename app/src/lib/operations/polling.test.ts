import { describe, expect, it } from "vitest";

import {
  SUSTAINED_WORK_MS,
  getAiOperationPollingIntervalMs,
} from "@/lib/operations/polling";

describe("getAiOperationPollingIntervalMs", () => {
  const now = new Date("2026-07-22T10:01:00.000Z");
  const createdAt = new Date("2026-07-22T10:00:55.000Z");
  const sustainedCreatedAt = new Date(
    now.getTime() - SUSTAINED_WORK_MS - 1_000,
  );

  it("polls every 1500ms for newly queued work", () => {
    expect(
      getAiOperationPollingIntervalMs({
        status: "queued",
        createdAt,
        now,
        visibilityState: "visible",
      }),
    ).toBe(1500);
  });

  it("polls every 3000ms while running before sustained work", () => {
    expect(
      getAiOperationPollingIntervalMs({
        status: "running",
        createdAt,
        now,
        visibilityState: "visible",
      }),
    ).toBe(3000);
  });

  it("backs off to 5000ms after sustained work", () => {
    expect(
      getAiOperationPollingIntervalMs({
        status: "running",
        createdAt: sustainedCreatedAt,
        now,
        visibilityState: "visible",
      }),
    ).toBe(5000);
  });

  it("pauses while the document is hidden", () => {
    expect(
      getAiOperationPollingIntervalMs({
        status: "running",
        createdAt,
        now,
        visibilityState: "hidden",
      }),
    ).toBe(false);
  });

  it("stops polling for terminal statuses", () => {
    for (const status of ["succeeded", "failed", "cancelled"] as const) {
      expect(
        getAiOperationPollingIntervalMs({
          status,
          createdAt,
          now,
          visibilityState: "visible",
        }),
      ).toBe(false);
    }
  });
});
