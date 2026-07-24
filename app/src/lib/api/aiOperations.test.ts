import { describe, expect, it } from "vitest";

import {
  AiOperationAcceptedSchema,
  AiOperationResponseSchema,
} from "@/lib/api/aiOperations";

const VALID_OPERATION = {
  id: "22222222-2222-4222-8222-222222222222",
  kind: "career_path_generate",
  status: "running",
  progress_percent: 25,
  stage: "generating",
  message: "Generating your career path.",
  result_type: null,
  result_id: null,
  error_code: null,
  error_message: null,
  retryable: false,
  created_at: "2026-07-22T10:00:00.000Z",
  updated_at: "2026-07-22T10:00:05.000Z",
  completed_at: null,
};

const VALID_ACCEPTED = {
  operation_id: "22222222-2222-4222-8222-222222222222",
  status: "queued",
  status_url: "/api/v1/ai-operations/22222222-2222-4222-8222-222222222222",
  retry_after_ms: 1500,
};

describe("AiOperationResponseSchema", () => {
  it("accepts a well-formed operation status payload", () => {
    expect(AiOperationResponseSchema.parse(VALID_OPERATION).id).toBe(
      VALID_OPERATION.id,
    );
  });

  it("rejects an invalid status", () => {
    expect(() =>
      AiOperationResponseSchema.parse({ ...VALID_OPERATION, status: "pending" }),
    ).toThrow();
  });

  it("rejects progress outside 0–100", () => {
    expect(() =>
      AiOperationResponseSchema.parse({
        ...VALID_OPERATION,
        progress_percent: 101,
      }),
    ).toThrow();
    expect(() =>
      AiOperationResponseSchema.parse({
        ...VALID_OPERATION,
        progress_percent: -1,
      }),
    ).toThrow();
  });

  it("rejects a malformed result_id", () => {
    expect(() =>
      AiOperationResponseSchema.parse({
        ...VALID_OPERATION,
        result_id: "not-a-uuid",
      }),
    ).toThrow();
  });

  it("rejects a malformed operation id", () => {
    expect(() =>
      AiOperationResponseSchema.parse({ ...VALID_OPERATION, id: "bad-id" }),
    ).toThrow();
  });
});

describe("AiOperationAcceptedSchema", () => {
  it("accepts a submit acknowledgement", () => {
    expect(AiOperationAcceptedSchema.parse(VALID_ACCEPTED).operation_id).toBe(
      VALID_ACCEPTED.operation_id,
    );
  });

  it("rejects a malformed operation_id", () => {
    expect(() =>
      AiOperationAcceptedSchema.parse({
        ...VALID_ACCEPTED,
        operation_id: "not-a-uuid",
      }),
    ).toThrow();
  });

  it("rejects a terminal submit status", () => {
    expect(() =>
      AiOperationAcceptedSchema.parse({
        ...VALID_ACCEPTED,
        status: "succeeded",
      }),
    ).toThrow();
  });
});
