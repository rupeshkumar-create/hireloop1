import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createElement,
  useEffect,
  type MutableRefObject,
  type ReactNode,
} from "react";
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
const unsubscribe = vi.fn();

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: vi.fn(() =>
        Promise.resolve({ data: { session: null }, error: null }),
      ),
      onAuthStateChange: (cb: AuthCallback) => {
        authCallback = cb;
        return { data: { subscription: { unsubscribe } } };
      },
    },
  }),
}));

import {
  AiOperationsProvider,
  useAiOperations,
} from "@/components/providers/AiOperationsProvider";

type AiOperationsApi = ReturnType<typeof useAiOperations>;

function makeOperation(
  overrides: Partial<AiOperationResponse> = {},
): AiOperationResponse {
  return {
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

function OperationsProbe({
  apiRef,
}: {
  apiRef: MutableRefObject<AiOperationsApi | null>;
}) {
  const api = useAiOperations();
  useEffect(() => {
    apiRef.current = api;
  }, [api, apiRef]);
  return createElement(
    "div",
    { "data-testid": "ops-count" },
    String(Object.keys(api.operations).length),
  );
}

function renderProvider(apiRef: MutableRefObject<AiOperationsApi | null>) {
  return render(
    createElement(
      Wrapper,
      null,
      createElement(OperationsProbe, { apiRef }),
    ),
  );
}

describe("AiOperationsProvider", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    authCallback = null;
    listActiveAiOperations.mockReset();
    cancelAiOperation.mockReset();
    getAiOperation.mockReset();
    retryAiOperation.mockReset();
    unsubscribe.mockReset();
    listActiveAiOperations.mockResolvedValue([]);
    getAiOperation.mockResolvedValue(makeOperation());
  });

  it("restores active operations when auth becomes signed in", async () => {
    const active = makeOperation({ status: "queued", progress_percent: 0 });
    listActiveAiOperations.mockResolvedValue([active]);
    const apiRef: MutableRefObject<AiOperationsApi | null> = { current: null };

    renderProvider(apiRef);

    expect(screen.getByTestId("ops-count")).toHaveTextContent("0");

    await act(async () => {
      authCallback?.("SIGNED_IN", { access_token: "tok" });
    });

    await waitFor(() => {
      expect(listActiveAiOperations).toHaveBeenCalledTimes(1);
      expect(screen.getByTestId("ops-count")).toHaveTextContent("1");
    });
  });

  it("ignores a late restore after SIGNED_OUT", async () => {
    let resolveList: (value: AiOperationResponse[]) => void = () => undefined;
    listActiveAiOperations.mockImplementation(
      () =>
        new Promise<AiOperationResponse[]>((resolve) => {
          resolveList = resolve;
        }),
    );
    const apiRef: MutableRefObject<AiOperationsApi | null> = { current: null };

    renderProvider(apiRef);

    await act(async () => {
      authCallback?.("SIGNED_IN", { access_token: "tok" });
    });

    await waitFor(() => expect(listActiveAiOperations).toHaveBeenCalledTimes(1));

    await act(async () => {
      authCallback?.("SIGNED_OUT", null);
    });

    await act(async () => {
      resolveList([makeOperation({ status: "queued", progress_percent: 0 })]);
    });

    expect(screen.getByTestId("ops-count")).toHaveTextContent("0");
  });

  it("toasts once when a polled operation becomes terminal", async () => {
    const terminal = makeOperation({
      status: "succeeded",
      progress_percent: 100,
      stage: "ready",
      message: "Career path ready.",
      completed_at: "2026-07-22T10:01:00.000Z",
    });
    listActiveAiOperations.mockResolvedValue([
      makeOperation({ status: "running" }),
    ]);
    getAiOperation.mockResolvedValue(terminal);
    const apiRef: MutableRefObject<AiOperationsApi | null> = { current: null };

    renderProvider(apiRef);

    await act(async () => {
      authCallback?.("SIGNED_IN", { access_token: "tok" });
    });

    await waitFor(() => {
      expect(screen.getByText("Career path ready.")).toBeInTheDocument();
    });

    expect(screen.getAllByText("Career path ready.")).toHaveLength(1);
  });

  it("cancel updates state and toasts once", async () => {
    const apiRef: MutableRefObject<AiOperationsApi | null> = { current: null };
    const queued = makeOperation({
      status: "queued",
      progress_percent: 0,
      stage: "queued",
      message: "Your request is queued.",
    });
    const cancelled = makeOperation({
      status: "cancelled",
      progress_percent: 0,
      stage: "cancelled",
      message: "Cancelled by you.",
      completed_at: "2026-07-22T10:02:00.000Z",
    });
    listActiveAiOperations.mockResolvedValue([queued]);
    cancelAiOperation.mockResolvedValue(cancelled);

    renderProvider(apiRef);

    await act(async () => {
      authCallback?.("SIGNED_IN", { access_token: "tok" });
    });

    await waitFor(() => expect(screen.getByTestId("ops-count")).toHaveTextContent("1"));
    await waitFor(() => expect(apiRef.current).not.toBeNull());

    await act(async () => {
      await apiRef.current!.cancelOperation(queued.id);
    });

    expect(cancelAiOperation).toHaveBeenCalledWith(queued.id);
    expect(apiRef.current!.operations[queued.id]?.status).toBe("cancelled");
    expect(screen.getByText("Cancelled by you.")).toBeInTheDocument();

    await act(async () => {
      await apiRef.current!.cancelOperation(queued.id);
    });
    expect(screen.getAllByText("Cancelled by you.")).toHaveLength(1);
  });
});
