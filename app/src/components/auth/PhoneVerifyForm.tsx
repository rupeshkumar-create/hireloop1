"use client";

/**
 * Phone capture (signup) — collects the candidate's +91 number and saves it.
 *
 * No OTP: we store the number for WhatsApp job-match and intro alerts.
 * Uses Field / Input / Button primitives from the design system.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, Phone, RefreshCw } from "lucide-react";
import {
  apiAuthFetch,
  ApiUnreachableError,
  probeApiHealth,
} from "@/lib/api/auth-fetch";
import { Button, Field, Input } from "@/components/ui";

type FailureReason = "api_down" | "needs_login" | "validation" | "unknown";

interface FormError {
  reason: FailureReason;
  message: string;
}

export function PhoneVerifyForm() {
  const router = useRouter();
  const [phone, setPhone] = useState("+91");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<FormError | null>(null);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.match(/^\+91[6-9]\d{9}$/)) {
      setError({
        reason: "validation",
        message:
          "Enter a valid Indian mobile number (10 digits, starting 6–9).",
      });
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const res = await apiAuthFetch("/api/v1/auth/save-phone", {
        method: "POST",
        body: JSON.stringify({ phone }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = (data as { detail?: string }).detail;

        if (res.status === 401) {
          setError({
            reason: "needs_login",
            message: detail ?? "Your session expired. Sign in again to continue.",
          });
          return;
        }
        if (res.status === 409 || res.status === 422) {
          setError({
            reason: "validation",
            message: detail ?? "We couldn't save that number.",
          });
          return;
        }
        setError({
          reason: "unknown",
          message: detail ?? `Couldn't save your number (status ${res.status}).`,
        });
        return;
      }

      window.location.href = "/onboarding";
    } catch (err) {
      setError(await classifyError(err));
    } finally {
      setIsLoading(false);
    }
  }

  // ── UI ──────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      <p className="text-body text-ink-700 leading-relaxed">
        Add your <span className="text-ink-900 font-medium">+91 number</span> for
        WhatsApp alerts on matches and intros.
      </p>

      <p className="text-small text-ink-500 leading-relaxed rounded-lg border border-ink-100 bg-ink-50/80 px-3 py-2.5">
        We&apos;ll use this number on WhatsApp for job match alerts and intro
        updates. You can change notification preferences in Settings.
      </p>

      <form onSubmit={handleSave} className="space-y-4">
        <Field
          label="Mobile number"
          htmlFor="phone"
          helper="India only — must start with 6, 7, 8, or 9."
        >
          <div className="flex">
            <span
              className="
                inline-flex items-center gap-1.5 px-3 py-2
                rounded-l-md border border-r-0 border-ink-100
                bg-ink-50 text-ink-500 text-body
              "
            >
              <Phone className="h-4 w-4" strokeWidth={1.5} />
              +91
            </span>
            <Input
              id="phone"
              type="tel"
              inputMode="numeric"
              value={phone.replace("+91", "")}
              onChange={(e) =>
                setPhone("+91" + e.target.value.replace(/\D/g, "").slice(0, 10))
              }
              placeholder="98765 43210"
              maxLength={10}
              required
              className="rounded-l-none border-l-0"
              autoComplete="tel-national"
              autoFocus
            />
          </div>
        </Field>

        <Button
          type="submit"
          variant="primary"
          size="lg"
          fullWidth
          loading={isLoading}
          disabled={phone.length < 13}
          rightIcon={
            !isLoading && <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
          }
        >
          {isLoading ? "Saving…" : "Save & continue"}
        </Button>
      </form>

      {error && (
        <ErrorPanel
          err={error}
          onRetry={() => setError(null)}
          onSignIn={() => router.push("/signup")}
        />
      )}
    </div>
  );
}

// ── Error panel ─────────────────────────────────────────────────────────────

function ErrorPanel({
  err,
  onRetry,
  onSignIn,
}: {
  err: FormError;
  onRetry: () => void;
  onSignIn: () => void;
}) {
  return (
    <div
      role="alert"
      className="
        flex items-start gap-2.5 rounded-md
        bg-destructive-bg px-3 py-2.5
        text-small text-destructive
      "
    >
      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" strokeWidth={1.5} />
      <div className="flex-1 leading-snug space-y-2">
        <p>{err.message}</p>

        {err.reason === "api_down" && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onRetry}
              className="
                inline-flex items-center gap-1 rounded-sm
                bg-destructive text-paper-0 px-2 py-0.5 text-micro uppercase
                hover:opacity-90 transition-opacity
              "
            >
              <RefreshCw className="h-3 w-3" strokeWidth={1.5} />
              Retry
            </button>
            <span className="text-ink-500 normal-case">
              Backend should be on{" "}
              <code className="font-mono">
                {process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}
              </code>
              .
            </span>
          </div>
        )}

        {err.reason === "needs_login" && (
          <button
            type="button"
            onClick={onSignIn}
            className="
              inline-flex items-center gap-1 rounded-sm
              bg-destructive text-paper-0 px-2 py-0.5 text-micro uppercase
              hover:opacity-90 transition-opacity
            "
          >
            Sign in again
          </button>
        )}
      </div>
    </div>
  );
}

// ── Error classifier ─────────────────────────────────────────────────────────

/**
 * Turn any thrown error into a structured FormError.
 * We always run a health probe before blaming the API — this distinguishes
 * true "server down" from CORS errors, browser extension interference, etc.
 */
async function classifyError(err: unknown): Promise<FormError> {
  if (typeof window !== "undefined" && process.env.NODE_ENV === "development") {
    // eslint-disable-next-line no-console
    console.error("[PhoneVerifyForm] caught:", err);
  }

  const raw = err instanceof Error ? err.message : String(err);
  const lc = raw.toLowerCase();

  if (
    err instanceof ApiUnreachableError ||
    lc.includes("failed to fetch") ||
    lc.includes("networkerror") ||
    lc.includes("load failed") // Safari's wording
  ) {
    const probe = await probeApiHealth();
    if (!probe.ok) {
      const msg =
        probe.reason === "timeout"
          ? "API request timed out. Is the backend running?"
          : "Can't reach the Hireloop API. Make sure the backend is running.";
      return { reason: "api_down", message: msg };
    }
    return {
      reason: "unknown",
      message:
        "A network request was blocked — but the API appears to be up. " +
        "Try opening a private/incognito window. If that works, a browser " +
        "extension or ad-blocker is likely interfering.",
    };
  }

  if (lc.includes("401") || lc.includes("authentication")) {
    return {
      reason: "needs_login",
      message: "Session expired. Sign in again to continue.",
    };
  }

  return { reason: "unknown", message: raw };
}
