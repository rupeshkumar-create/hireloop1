import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: vi.fn(() =>
        Promise.resolve({ data: { session: null }, error: null }),
      ),
    },
  }),
}));

import {
  ApiUnreachableError,
  apiAuthFetch,
} from "@/lib/api/auth-fetch";
import { API_PROXY_PREFIX } from "@/lib/api/base-url";
import { sanitizeChatError } from "@/lib/chat/aaryaStream";
import type { AiOperationResponse } from "@/lib/api/aiOperations";

const originalFetch = globalThis.fetch;

describe("apiAuthFetch error classification", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
  });

  afterEach(() => {
    vi.stubGlobal("fetch", originalFetch);
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reports the same-origin proxy path, not the Railway hostname", async () => {
    await expect(
      apiAuthFetch("/api/v1/career/path/generate", { method: "POST" }),
    ).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiUnreachableError);
      const unreachable = err as ApiUnreachableError;
      expect(unreachable.path).toBe("/api/v1/career/path/generate");
      expect(unreachable.reason).toBe("network");
      expect(unreachable.timeoutMs).toBe(25_000);
      expect(unreachable.url).toBe(
        `${API_PROXY_PREFIX}/api/v1/career/path/generate`,
      );
      expect(unreachable.message).toContain(API_PROXY_PREFIX);
      expect(unreachable.message).toContain("/api/v1/career/path/generate");
      expect(unreachable.message).not.toMatch(/railway\.app/i);
      expect(unreachable.message).not.toMatch(/https?:\/\/\d+\.\d+\.\d+\.\d+/);
      return true;
    });
  });

  it("keeps operation error_code distinct from network unreachable reasons", () => {
    const failedOperation: Pick<
      AiOperationResponse,
      "error_code" | "error_message" | "status"
    > = {
      status: "failed",
      error_code: "provider_rate_limited",
      error_message: "The AI provider is busy. Try again shortly.",
    };

    const networkErr = new ApiUnreachableError({
      path: "/api/v1/ai-operations/22222222-2222-4222-8222-222222222222",
      reason: "network",
      timeoutMs: 25_000,
      cause: new TypeError("Failed to fetch"),
    });

    expect(failedOperation.error_code).toBe("provider_rate_limited");
    expect(networkErr.reason).toBe("network");
    expect(networkErr.message).not.toContain("provider_rate_limited");
    expect(networkErr).not.toHaveProperty("error_code");
  });

  it("does not rewrite caller AbortSignal cancellation as a server timeout", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            const signal = init?.signal;
            if (!signal) {
              reject(new Error("expected caller signal"));
              return;
            }
            if (signal.aborted) {
              reject(new DOMException("The operation was aborted.", "AbortError"));
              return;
            }
            signal.addEventListener(
              "abort",
              () => {
                reject(new DOMException("The operation was aborted.", "AbortError"));
              },
              { once: true },
            );
          }),
      ),
    );

    const pending = apiAuthFetch(
      "/api/v1/chat/sessions/abc/messages",
      { method: "POST", signal: controller.signal },
    );
    controller.abort();

    await expect(pending).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(DOMException);
      expect((err as DOMException).name).toBe("AbortError");
      expect(err).not.toBeInstanceOf(ApiUnreachableError);
      if (err instanceof Error) {
        expect(err.message.toLowerCase()).not.toContain("timed out");
        expect(err.message.toLowerCase()).not.toContain("servers may be busy");
      }
      return true;
    });
  });

  it("classifies client-enforced deadlines as timeout with path + timeoutMs", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            const signal = init?.signal;
            if (!signal) {
              reject(new Error("expected timeout signal"));
              return;
            }
            signal.addEventListener(
              "abort",
              () => {
                const name =
                  "reason" in signal &&
                  signal.reason instanceof Error &&
                  signal.reason.name === "TimeoutError"
                    ? "TimeoutError"
                    : "AbortError";
                reject(new DOMException("The operation was aborted.", name));
              },
              { once: true },
            );
          }),
      ),
    );

    const pending = apiAuthFetch(
      "/api/v1/me/profile",
      { method: "GET" },
      { timeoutMs: 1_000 },
    );
    const expectation = expect(pending).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiUnreachableError);
      const unreachable = err as ApiUnreachableError;
      expect(unreachable.path).toBe("/api/v1/me/profile");
      expect(unreachable.reason).toBe("timeout");
      expect(unreachable.timeoutMs).toBe(1_000);
      expect(unreachable.message).toContain("/hireloop-api/api/v1/me/profile");
      expect(unreachable.message.toLowerCase()).toContain("timed out");
      return true;
    });
    await vi.advanceTimersByTimeAsync(1_000);
    await expectation;
  });

  it("chat error sanitization stays purpose-specific (not Railway/API-host copy)", () => {
    expect(sanitizeChatError("OpenRouter 402 requires more credits")).toBe(
      "Failed.",
    );
    expect(
      sanitizeChatError("Aarya is busy right now — wait a few seconds and try again."),
    ).toBe("Aarya is busy right now — wait a few seconds and try again.");
    expect(sanitizeChatError("Aarya took too long to respond. Please try again.")).toBe(
      "Aarya took too long to respond. Please try again.",
    );
    expect(sanitizeChatError("Aarya took too long to respond. Please try again.")).not.toMatch(
      /railway|hireloop-api|can't reach api/i,
    );
  });
});
