import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AiOperationResponse } from "@/lib/api/aiOperations";

import { AiOperationProgress } from "./AiOperationProgress";

function makeOperation(
  overrides: Partial<AiOperationResponse> = {},
): AiOperationResponse {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    kind: "career_path_generate",
    status: "running",
    progress_percent: 40,
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
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("AiOperationProgress", () => {
  it("renders queued status with cancel and progressbar", () => {
    const onCancel = vi.fn();
    render(
      <AiOperationProgress
        operation={makeOperation({
          status: "queued",
          stage: "queued",
          progress_percent: 0,
          message: "Your request is queued.",
        })}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByRole("status")).toHaveAttribute(
      "data-operation-status",
      "queued",
    );
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("Your request is queued.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    fireEvent.click(screen.getByRole("button", { name: "Cancel generation" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("renders running status with progress", () => {
    render(
      <AiOperationProgress
        operation={makeOperation({ status: "running", progress_percent: 55 })}
        onCancel={() => undefined}
      />,
    );
    expect(screen.getByRole("status")).toHaveAttribute(
      "data-operation-status",
      "running",
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "55");
    expect(screen.getByText("55%")).toBeInTheDocument();
  });

  it("renders succeeded without cancel or retry", () => {
    render(
      <AiOperationProgress
        operation={makeOperation({
          status: "succeeded",
          progress_percent: 100,
          stage: "ready",
          message: "Ready.",
          completed_at: "2026-07-22T10:01:00.000Z",
        })}
        onCancel={() => undefined}
        onRetry={() => undefined}
      />,
    );
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel generation" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry generation" })).toBeNull();
  });

  it("shows retry only for retryable failures", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <AiOperationProgress
        operation={makeOperation({
          status: "failed",
          retryable: false,
          error_message: "Not enough profile data.",
          completed_at: "2026-07-22T10:01:00.000Z",
        })}
        onRetry={onRetry}
      />,
    );
    expect(screen.queryByRole("button", { name: "Retry generation" })).toBeNull();
    expect(screen.getByText("Not enough profile data.")).toBeInTheDocument();

    rerender(
      <AiOperationProgress
        operation={makeOperation({
          status: "failed",
          retryable: true,
          error_message: "Provider timed out.",
          completed_at: "2026-07-22T10:01:00.000Z",
        })}
        onRetry={onRetry}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry generation" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("hides cancel for cancelled terminal state", () => {
    render(
      <AiOperationProgress
        operation={makeOperation({
          status: "cancelled",
          message: "Cancelled.",
          completed_at: "2026-07-22T10:01:00.000Z",
        })}
        onCancel={() => undefined}
      />,
    );
    expect(screen.getByText("Cancelled.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel generation" })).toBeNull();
  });
});
