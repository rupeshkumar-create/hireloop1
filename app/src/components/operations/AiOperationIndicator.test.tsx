import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui";
import type { AiOperationResponse } from "@/lib/api/aiOperations";

const listActiveAiOperations = vi.fn();
const cancelAiOperation = vi.fn();
const getAiOperation = vi.fn();
const retryAiOperation = vi.fn();

vi.mock("@/lib/api/aiOperations", () => ({
  listActiveAiOperations: (...args: unknown[]) => listActiveAiOperations(...args),
  cancelAiOperation: (...args: unknown[]) => cancelAiOperation(...args),
  getAiOperation: (...args: unknown[]) => getAiOperation(...args),
  retryAiOperation: (...args: unknown[]) => retryAiOperation(...args),
}));

type AuthCallback = (
  event: string,
  session: { access_token: string } | null,
) => void;

let authCallback: AuthCallback | null = null;

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: vi.fn(() =>
        Promise.resolve({ data: { session: null }, error: null }),
      ),
      onAuthStateChange: (cb: AuthCallback) => {
        authCallback = cb;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
    },
  }),
}));

import { AiOperationsProvider } from "@/components/providers/AiOperationsProvider";

import { AiOperationIndicator } from "./AiOperationIndicator";

function makeOperation(
  overrides: Partial<AiOperationResponse> = {},
): AiOperationResponse {
  return {
    id: "22222222-2222-4222-8222-222222222222",
    kind: "career_path_generate",
    status: "queued",
    progress_percent: 0,
    stage: "queued",
    message: "Your career path is queued.",
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

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return createElement(
    QueryClientProvider,
    { client },
    createElement(
      ToastProvider,
      null,
      createElement(AiOperationsProvider, null, children),
    ),
  );
}

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  authCallback = null;
  listActiveAiOperations.mockReset();
  cancelAiOperation.mockReset();
  getAiOperation.mockReset();
  retryAiOperation.mockReset();
  listActiveAiOperations.mockResolvedValue([]);
  getAiOperation.mockResolvedValue(makeOperation({ status: "running" }));
});

describe("AiOperationIndicator", () => {
  it("shows nothing when there are no operations", () => {
    render(
      createElement(Wrapper, null, createElement(AiOperationIndicator)),
    );
    expect(screen.queryByTestId("ai-operation-indicator")).toBeNull();
  });

  it("recovers and displays active operations after provider mount", async () => {
    const active = makeOperation({
      status: "running",
      stage: "generating",
      progress_percent: 30,
      message: "Generating your career path.",
    });
    listActiveAiOperations.mockResolvedValue([active]);
    getAiOperation.mockResolvedValue(active);

    render(
      createElement(Wrapper, null, createElement(AiOperationIndicator)),
    );

    await act(async () => {
      authCallback?.("SIGNED_IN", { access_token: "tok" });
    });

    await waitFor(() => {
      expect(screen.getByTestId("ai-operation-indicator")).toBeInTheDocument();
    });
    expect(screen.getByText("Generating")).toBeInTheDocument();
    expect(screen.getByText("Generating your career path.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cancel generation" }),
    ).toBeInTheDocument();
  });
});
