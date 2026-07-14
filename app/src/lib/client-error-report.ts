export type ClientErrorClassification = "chunk_load" | "other";

export type ClientErrorReport = {
  name: string;
  message: string;
  digest?: string;
  pathname: string;
  classification: ClientErrorClassification;
};

const CHUNK_ERROR_PATTERN =
  /chunkloaderror|loading chunk [^ ]+ failed|failed to fetch dynamically imported module/i;
const URL_PATTERN = /(?:https?|wss?):\/\/[^\s)\]}]+/gi;
const CONTROL_PATTERN = /[\u0000-\u001f\u007f]+/g;
const RELOAD_RECOVERY_WINDOW_MS = 60_000;

export const CLIENT_RELOAD_MARKER_KEY = "hireschema_client_reload_recovery";

export function sanitizeClientErrorText(value: unknown, maxLength: number): string {
  return String(value ?? "")
    .replace(URL_PATTERN, "[url]")
    .replace(CONTROL_PATTERN, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

export function classifyClientLoadError(error: unknown): ClientErrorClassification {
  if (!(error instanceof Error)) return "other";
  const searchable = `${error.name} ${error.message}`;
  return CHUNK_ERROR_PATTERN.test(searchable) ? "chunk_load" : "other";
}

export function createReloadMarker(pathname: string, now = Date.now()): string {
  return JSON.stringify({ pathname: sanitizePathname(pathname), at: now });
}

export function shouldReloadOnce(
  pathname: string,
  storedMarker: string | null,
  now = Date.now(),
): boolean {
  if (!storedMarker) return true;
  try {
    const marker = JSON.parse(storedMarker) as { pathname?: unknown; at?: unknown };
    const samePath = marker.pathname === sanitizePathname(pathname);
    const ageMs = now - Number(marker.at);
    return !samePath || !Number.isFinite(ageMs) || ageMs > RELOAD_RECOVERY_WINDOW_MS;
  } catch {
    return true;
  }
}

export function createClientErrorReport(
  error: Error & { digest?: string },
  pathname: string,
): ClientErrorReport {
  return sanitizeClientErrorReport({
    name: error.name || "Error",
    message: error.message || "Unexpected client error",
    ...(error.digest ? { digest: error.digest } : {}),
    pathname,
    classification: classifyClientLoadError(error),
  });
}

export function sanitizeClientErrorReport(report: ClientErrorReport): ClientErrorReport {
  const digest = sanitizeClientErrorText(report.digest, 120);
  return {
    name: sanitizeClientErrorText(report.name, 80) || "Error",
    message:
      sanitizeClientErrorText(report.message, 300) || "Unexpected client error",
    ...(digest ? { digest } : {}),
    pathname: sanitizePathname(report.pathname),
    classification: report.classification,
  };
}

export async function reportClientError(
  error: Error & { digest?: string },
  pathname: string,
): Promise<void> {
  try {
    await fetch("/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      keepalive: true,
      body: JSON.stringify(createClientErrorReport(error, pathname)),
    });
  } catch {
    // Diagnostics must never interfere with the recovery UI.
  }
}

function sanitizePathname(value: string): string {
  const path = value.split("?", 1)[0]?.split("#", 1)[0] ?? "/";
  const sanitized = sanitizeClientErrorText(path, 160);
  return sanitized.startsWith("/") ? sanitized : "/";
}
