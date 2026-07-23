import { z } from "zod";

import { apiAuthFetch } from "@/lib/api/auth-fetch";

const isoDateTime = z.string().datetime({ offset: true });

export const AiOperationStatusSchema = z.enum([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
]);

export type AiOperationStatus = z.infer<typeof AiOperationStatusSchema>;

export const AiOperationAcceptedSchema = z
  .object({
    operation_id: z.string().uuid(),
    status: z.enum(["queued", "running"]),
    status_url: z.string().min(1),
    retry_after_ms: z.number().int().positive(),
  })
  .passthrough();

export type AiOperationAccepted = z.infer<typeof AiOperationAcceptedSchema>;

export const AiOperationResponseSchema = z
  .object({
    id: z.string().uuid(),
    kind: z.string().min(1),
    status: AiOperationStatusSchema,
    progress_percent: z.number().int().min(0).max(100),
    stage: z.string(),
    message: z.string(),
    result_type: z.string().nullable().optional(),
    result_id: z.string().uuid().nullable().optional(),
    error_code: z.string().nullable().optional(),
    error_message: z.string().nullable().optional(),
    retryable: z.boolean(),
    created_at: isoDateTime,
    updated_at: isoDateTime,
    completed_at: isoDateTime.nullable(),
  })
  .passthrough();

export type AiOperationResponse = z.infer<typeof AiOperationResponseSchema>;

const operationIdSchema = z.string().uuid();

function validOperationId(operationId: string): string {
  const parsed = operationIdSchema.safeParse(operationId);
  if (!parsed.success) throw new Error("Invalid AI operation id.");
  return parsed.data;
}

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
    throw new Error("The server returned an invalid AI operation response.");
  }
  return parsed.data;
}

export async function getAiOperation(operationId: string): Promise<AiOperationResponse> {
  const id = validOperationId(operationId);
  const response = await apiAuthFetch(`/api/v1/ai-operations/${id}`, {
    cache: "no-store",
  });
  return parseOrThrow(response, AiOperationResponseSchema);
}

export async function listActiveAiOperations(): Promise<AiOperationResponse[]> {
  const response = await apiAuthFetch("/api/v1/ai-operations?status=active", {
    cache: "no-store",
  });
  return parseOrThrow(response, z.array(AiOperationResponseSchema));
}

export async function cancelAiOperation(
  operationId: string,
): Promise<AiOperationResponse> {
  const id = validOperationId(operationId);
  const response = await apiAuthFetch(`/api/v1/ai-operations/${id}/cancel`, {
    method: "POST",
  });
  return parseOrThrow(response, AiOperationResponseSchema);
}

export async function retryAiOperation(
  operationId: string,
): Promise<AiOperationResponse> {
  const id = validOperationId(operationId);
  const response = await apiAuthFetch(`/api/v1/ai-operations/${id}/retry`, {
    method: "POST",
  });
  return parseOrThrow(response, AiOperationResponseSchema);
}
