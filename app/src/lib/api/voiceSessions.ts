import { z } from "zod";

import { apiAuthFetch } from "@/lib/api/auth-fetch";

const nullableOptionalDateTime = z.string().datetime({ offset: true }).nullable().optional();

export const CareerCallSchema = z
  .object({
    id: z.string().uuid(),
    conversation_id: z.string().uuid().nullable().optional(),
    status: z.enum(["scheduled", "active", "completed", "cancelled"]),
    scheduled_at: nullableOptionalDateTime,
    started_at: nullableOptionalDateTime,
  })
  .strict();

export type CareerCall = z.infer<typeof CareerCallSchema>;

const apiErrorSchema = z
  .object({
    detail: z.unknown().optional(),
    error: z
      .object({
        message: z.string().optional(),
      })
      .passthrough()
      .optional(),
  })
  .passthrough();

function safeErrorDetail(body: unknown): string | null {
  const parsed = apiErrorSchema.safeParse(body);
  if (!parsed.success) return null;

  const detail = parsed.data.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item) => {
      if (typeof item === "string" && item.trim()) return [item.trim()];
      if (typeof item !== "object" || item === null || !("msg" in item)) return [];
      const message = (item as { msg?: unknown }).msg;
      return typeof message === "string" && message.trim() ? [message.trim()] : [];
    });
    if (messages.length > 0) return messages.join("; ");
  }

  const nestedMessage = parsed.data.error?.message;
  return nestedMessage?.trim() || null;
}

async function parseOrThrow<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(safeErrorDetail(body) ?? `Request failed (${response.status})`);
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new Error("The server returned an invalid career call response.");
  }
  return parsed.data;
}

export async function startCareerCall(input: {
  conversationId: string;
  scheduledSessionId?: string;
  consent: boolean;
}): Promise<CareerCall> {
  const response = await apiAuthFetch("/api/v1/voice-sessions/start", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: input.conversationId,
      scheduled_session_id: input.scheduledSessionId,
      consent: input.consent,
      consent_version: "career-call-v1",
    }),
  });
  return parseOrThrow(response, CareerCallSchema);
}

export async function completeCareerCall(
  sessionId: string,
  input: {
    durationSeconds: number;
    completionReason:
      | "candidate_ended"
      | "time_limit"
      | "coverage_complete"
      | "interrupted";
  }
): Promise<CareerCall> {
  const response = await apiAuthFetch(`/api/v1/voice-sessions/${sessionId}/complete`, {
    method: "POST",
    body: JSON.stringify({
      duration_seconds: input.durationSeconds,
      completion_reason: input.completionReason,
    }),
  });
  return parseOrThrow(response, CareerCallSchema);
}

const bookCareerCallSchema = z
  .object({
    session_id: z.string().uuid(),
    start_time: z.string().datetime({ offset: true }),
  })
  .passthrough();

export async function scheduleCareerCall(isoTime: string): Promise<CareerCall> {
  const response = await apiAuthFetch("/api/v1/voice-sessions/book", {
    method: "POST",
    body: JSON.stringify({ start_time: isoTime, session_type: "career_chat" }),
  });
  const booking = await parseOrThrow(response, bookCareerCallSchema);
  return CareerCallSchema.parse({
    id: booking.session_id,
    conversation_id: null,
    status: "scheduled",
    scheduled_at: booking.start_time,
    started_at: null,
  });
}

const voiceSessionListItemSchema = z
  .object({
    id: z.string().uuid(),
    session_type: z.string(),
    status: z.enum(["scheduled", "active", "completed", "cancelled"]),
    conversation_id: z.string().uuid().nullable().optional(),
    scheduled_at: nullableOptionalDateTime,
    started_at: nullableOptionalDateTime,
  })
  .passthrough();

export async function listCareerCalls(): Promise<CareerCall[]> {
  const response = await apiAuthFetch("/api/v1/voice-sessions", { cache: "no-store" });
  const sessions = await parseOrThrow(response, z.array(voiceSessionListItemSchema));
  return sessions
    .filter((session) => session.session_type === "career_chat")
    .map((session) =>
      CareerCallSchema.parse({
        id: session.id,
        conversation_id: session.conversation_id,
        status: session.status,
        scheduled_at: session.scheduled_at,
        started_at: session.started_at,
      })
    );
}

const cancelResponseSchema = z.object({ message: z.string().min(1) }).passthrough();

export async function cancelCareerCall(sessionId: string): Promise<void> {
  const response = await apiAuthFetch(`/api/v1/voice-sessions/${sessionId}/cancel`, {
    method: "DELETE",
  });
  await parseOrThrow(response, cancelResponseSchema);
}
