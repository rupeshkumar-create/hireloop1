/**
 * API base URL resolution.
 *
 * In the browser we proxy through Next.js (`/hireloop-api/*` → FastAPI) so
 * requests stay same-origin and avoid CORS / CSP / Safari cross-host issues
 * between localhost:3001 and 127.0.0.1:8000.
 *
 * On the server (RSC, route handlers) we call the backend directly.
 */

export const DIRECT_API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

/** Same-origin proxy path — must match `rewrites()` in next.config.mjs */
export const API_PROXY_PREFIX = "/hireloop-api";

export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return API_PROXY_PREFIX;
  }
  return DIRECT_API_URL;
}

/**
 * API base for server-side route handlers (OAuth callback, RSC).
 *
 * Prefer looping back through this app's `/hireloop-api` rewrite so bootstrap
 * works on Vercel without server-to-server CORS / wrong localhost defaults.
 */
export function getServerApiBaseUrl(appOrigin?: string): string {
  const origin = appOrigin?.replace(/\/$/, "");
  if (origin) {
    return `${origin}${API_PROXY_PREFIX}`;
  }
  if (process.env.NEXT_PUBLIC_APP_URL) {
    return `${process.env.NEXT_PUBLIC_APP_URL.replace(/\/$/, "")}${API_PROXY_PREFIX}`;
  }
  if (process.env.VERCEL_URL) {
    return `https://${process.env.VERCEL_URL}${API_PROXY_PREFIX}`;
  }
  return DIRECT_API_URL;
}

/**
 * WebSocket base URL for the FastAPI backend (e.g. live voice streaming).
 *
 * Unlike HTTP requests, we do NOT route WebSockets through the Next.js rewrite
 * proxy — `rewrites()` is HTTP-level and does not reliably upgrade WS
 * connections (especially in dev). So we connect straight to the backend host
 * and flip the scheme http→ws / https→wss. FastAPI/Starlette WebSockets don't
 * enforce CORS, so cross-origin (localhost:3001 → 127.0.0.1:8000) is fine.
 */
export function getApiWsBaseUrl(): string {
  return DIRECT_API_URL.replace(/^http/, "ws");
}
