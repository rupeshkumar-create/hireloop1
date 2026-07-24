"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui";
import {
  cancelAiOperation,
  getAiOperation,
  listActiveAiOperations,
  retryAiOperation,
  type AiOperationAccepted,
  type AiOperationResponse,
} from "@/lib/api/aiOperations";
import {
  getAiOperationPollingIntervalMs,
  isTerminalAiOperationStatus,
} from "@/lib/operations/polling";
import type { TrackOperationOptions } from "@/lib/operations/kinds";
import { createClient } from "@/lib/supabase/client";

const AI_OPERATION_QUERY_KEY = "ai-operation" as const;

type OperationsMap = Record<string, AiOperationResponse>;

type OperationWaiter = {
  resolve: (operation: AiOperationResponse) => void;
  reject: (error: Error) => void;
};

export type AiOperationsRestoreState = "idle" | "loading" | "ready";

type AiOperationsContextValue = {
  operations: OperationsMap;
  /** Whether active-op restore after auth has finished (or is idle when logged out). */
  restoreState: AiOperationsRestoreState;
  trackOperation: (
    accepted: AiOperationAccepted,
    options?: TrackOperationOptions,
  ) => void;
  /** Track and resolve when the operation reaches a terminal status. */
  trackAndWait: (
    accepted: AiOperationAccepted,
    options?: TrackOperationOptions,
  ) => Promise<AiOperationResponse>;
  /** Wait for an already-tracked operation id to reach a terminal status. */
  waitForOperation: (operationId: string) => Promise<AiOperationResponse>;
  cancelOperation: (operationId: string) => Promise<void>;
  /** Retry a failed op; returns the replacement attempt (does not re-submit features). */
  retryOperation: (operationId: string) => Promise<AiOperationResponse>;
};

type ToastApi = {
  success: (msg: string) => void;
  error: (msg: string) => void;
  info: (msg: string) => void;
};

const AiOperationsContext = createContext<AiOperationsContextValue | null>(null);

function upsertOperation(
  prev: OperationsMap,
  operation: AiOperationResponse,
): OperationsMap {
  const existing = prev[operation.id];
  if (
    existing &&
    existing.updated_at === operation.updated_at &&
    existing.status === operation.status &&
    existing.progress_percent === operation.progress_percent &&
    existing.message === operation.message
  ) {
    return prev;
  }
  return { ...prev, [operation.id]: operation };
}

function toastMessageFor(operation: AiOperationResponse): string {
  if (operation.status === "succeeded") {
    return operation.message.trim() || "Ready.";
  }
  if (operation.status === "failed") {
    return (
      operation.error_message?.trim() ||
      operation.message.trim() ||
      "Something went wrong. Try again."
    );
  }
  if (operation.status === "cancelled") {
    return operation.message.trim() || "Cancelled.";
  }
  return operation.message.trim() || "Update.";
}

function notifyTerminal(
  operation: AiOperationResponse,
  toasted: Set<string>,
  toast: ToastApi,
): void {
  if (!isTerminalAiOperationStatus(operation.status)) return;
  if (toasted.has(operation.id)) return;
  toasted.add(operation.id);

  const message = toastMessageFor(operation);
  if (operation.status === "succeeded") toast.success(message);
  else if (operation.status === "failed") toast.error(message);
  else toast.info(message);
}

function settleWaiters(
  operation: AiOperationResponse,
  waiters: Map<string, OperationWaiter[]>,
): void {
  if (!isTerminalAiOperationStatus(operation.status)) return;
  const pending = waiters.get(operation.id);
  if (!pending?.length) return;
  waiters.delete(operation.id);
  for (const waiter of pending) {
    if (operation.status === "succeeded") {
      waiter.resolve(operation);
      continue;
    }
    waiter.reject(
      new Error(
        operation.error_message?.trim() ||
          operation.message.trim() ||
          (operation.status === "cancelled"
            ? "Cancelled."
            : "Something went wrong. Try again."),
      ),
    );
  }
}

export function AiOperationsProvider({ children }: { children: ReactNode }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [operations, setOperations] = useState<OperationsMap>({});
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [restoreState, setRestoreState] =
    useState<AiOperationsRestoreState>("idle");
  const [visibilityState, setVisibilityState] =
    useState<DocumentVisibilityState>(() =>
      typeof document === "undefined" ? "visible" : document.visibilityState,
    );
  const toastedRef = useRef<Set<string>>(new Set());
  const waitersRef = useRef<Map<string, OperationWaiter[]>>(new Map());
  /** Latest known operations for immediate waiter settlement. */
  const operationsRef = useRef<OperationsMap>({});
  /** Bumped on SIGNED_OUT so late restore results are ignored. */
  const authGenerationRef = useRef(0);

  const mergeOperations = useCallback((rows: AiOperationResponse[]) => {
    setOperations((prev) => {
      let next = prev;
      for (const row of rows) {
        next = upsertOperation(next, row);
        settleWaiters(row, waitersRef.current);
      }
      operationsRef.current = next;
      return next;
    });
  }, []);

  useEffect(() => {
    operationsRef.current = operations;
  }, [operations]);

  useEffect(() => {
    const onVisibility = () => {
      setVisibilityState(document.visibilityState);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    const supabase = createClient();

    // Drive auth only from onAuthStateChange (INITIAL_SESSION / SIGNED_IN /
    // TOKEN_REFRESHED / SIGNED_OUT). No getSession() — avoids stale resolves
    // flipping auth back on after logout.
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (!session || event === "SIGNED_OUT") {
        authGenerationRef.current += 1;
        setIsAuthenticated(false);
        setRestoreState("idle");
        setOperations({});
        operationsRef.current = {};
        toastedRef.current.clear();
        for (const pending of waitersRef.current.values()) {
          for (const waiter of pending) {
            waiter.reject(new Error("Signed out."));
          }
        }
        waitersRef.current.clear();
        return;
      }

      setIsAuthenticated(true);
      setRestoreState("loading");
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;

    const generation = authGenerationRef.current;
    let cancelled = false;
    setRestoreState("loading");

    void (async () => {
      try {
        const active = await listActiveAiOperations();
        if (cancelled || generation !== authGenerationRef.current) return;
        mergeOperations(active);
      } catch {
        /* non-fatal — polling will retry once track/restore has IDs */
      } finally {
        if (!cancelled && generation === authGenerationRef.current) {
          setRestoreState("ready");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, mergeOperations]);

  const activeIds = useMemo(
    () =>
      Object.values(operations)
        .filter((op) => !isTerminalAiOperationStatus(op.status))
        .map((op) => op.id),
    [operations],
  );

  const pollQueries = useQueries({
    queries: activeIds.map((operationId) => ({
      queryKey: [AI_OPERATION_QUERY_KEY, operationId] as const,
      queryFn: () => getAiOperation(operationId),
      enabled: isAuthenticated && visibilityState === "visible",
      refetchInterval: (query: {
        state: { data: AiOperationResponse | undefined };
      }) => {
        const data = query.state.data ?? operations[operationId];
        if (!data) return 1500;
        return getAiOperationPollingIntervalMs({
          status: data.status,
          createdAt: data.created_at,
          visibilityState,
        });
      },
      refetchIntervalInBackground: false,
      staleTime: 0,
      retry: 1,
    })),
  });

  const pollDataKey = pollQueries
    .map((result) =>
      result.data
        ? `${result.data.id}:${result.dataUpdatedAt}:${result.data.status}:${result.data.progress_percent}`
        : "",
    )
    .join("|");

  const polledOperations = useMemo(() => {
    return pollQueries
      .map((result) => result.data)
      .filter((row): row is AiOperationResponse => row != null);
    // Recompute only when polled payloads change.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by pollDataKey
  }, [pollDataKey]);

  useEffect(() => {
    for (const operation of polledOperations) {
      setOperations((prev) => {
        const next = upsertOperation(prev, operation);
        operationsRef.current = next;
        return next;
      });
      notifyTerminal(operation, toastedRef.current, toast);
      settleWaiters(operation, waitersRef.current);
    }
  }, [polledOperations, toast]);

  const trackOperation = useCallback(
    (accepted: AiOperationAccepted, options?: TrackOperationOptions) => {
      const existing = operationsRef.current[accepted.operation_id];
      const placeholder: AiOperationResponse = {
        id: accepted.operation_id,
        kind: options?.kind?.trim() || existing?.kind || "pending",
        status: accepted.status,
        progress_percent: existing?.progress_percent ?? 0,
        stage: existing?.stage ?? "queued",
        message: existing?.message ?? "Your request is queued.",
        result_type: existing?.result_type ?? null,
        result_id: existing?.result_id ?? null,
        error_code: existing?.error_code ?? null,
        error_message: existing?.error_message ?? null,
        retryable: existing?.retryable ?? false,
        created_at: existing?.created_at ?? new Date().toISOString(),
        updated_at: new Date().toISOString(),
        completed_at: existing?.completed_at ?? null,
      };
      setOperations((prev) => {
        const next = upsertOperation(prev, placeholder);
        operationsRef.current = next;
        settleWaiters(placeholder, waitersRef.current);
        return next;
      });
      void queryClient.invalidateQueries({
        queryKey: [AI_OPERATION_QUERY_KEY, accepted.operation_id],
      });
    },
    [queryClient],
  );

  const waitForOperation = useCallback((operationId: string) => {
    return new Promise<AiOperationResponse>((resolve, reject) => {
      const current = operationsRef.current[operationId];
      if (current && isTerminalAiOperationStatus(current.status)) {
        if (current.status === "succeeded") {
          resolve(current);
          return;
        }
        reject(
          new Error(
            current.error_message?.trim() ||
              current.message.trim() ||
              (current.status === "cancelled"
                ? "Cancelled."
                : "Something went wrong. Try again."),
          ),
        );
        return;
      }
      const existing = waitersRef.current.get(operationId) ?? [];
      existing.push({ resolve, reject });
      waitersRef.current.set(operationId, existing);
    });
  }, []);

  const trackAndWait = useCallback(
    (accepted: AiOperationAccepted, options?: TrackOperationOptions) => {
      return new Promise<AiOperationResponse>((resolve, reject) => {
        const existing = waitersRef.current.get(accepted.operation_id) ?? [];
        existing.push({ resolve, reject });
        waitersRef.current.set(accepted.operation_id, existing);
        trackOperation(accepted, options);
      });
    },
    [trackOperation],
  );

  const cancelOperation = useCallback(
    async (operationId: string) => {
      const updated = await cancelAiOperation(operationId);
      setOperations((prev) => {
        const next = upsertOperation(prev, updated);
        operationsRef.current = next;
        return next;
      });
      notifyTerminal(updated, toastedRef.current, toast);
      settleWaiters(updated, waitersRef.current);
      queryClient.setQueryData([AI_OPERATION_QUERY_KEY, operationId], updated);
    },
    [queryClient, toast],
  );

  const retryOperation = useCallback(
    async (operationId: string) => {
      const replacement = await retryAiOperation(operationId);
      setOperations((prev) => {
        const next = { ...prev };
        // Keep the failed attempt visible until UI decides; always track the new one.
        next[replacement.id] = replacement;
        operationsRef.current = next;
        return next;
      });
      toastedRef.current.delete(replacement.id);
      notifyTerminal(replacement, toastedRef.current, toast);
      settleWaiters(replacement, waitersRef.current);
      queryClient.setQueryData(
        [AI_OPERATION_QUERY_KEY, replacement.id],
        replacement,
      );
      return replacement;
    },
    [queryClient, toast],
  );

  const value = useMemo<AiOperationsContextValue>(
    () => ({
      operations,
      restoreState,
      trackOperation,
      trackAndWait,
      waitForOperation,
      cancelOperation,
      retryOperation,
    }),
    [
      operations,
      restoreState,
      trackOperation,
      trackAndWait,
      waitForOperation,
      cancelOperation,
      retryOperation,
    ],
  );

  return (
    <AiOperationsContext.Provider value={value}>
      {children}
    </AiOperationsContext.Provider>
  );
}

export function useAiOperations(): AiOperationsContextValue {
  const ctx = useContext(AiOperationsContext);
  if (!ctx) {
    throw new Error("useAiOperations must be used inside <AiOperationsProvider>");
  }
  return ctx;
}
