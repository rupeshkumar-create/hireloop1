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
 * Base URL for browser multipart uploads (CV, etc.).
 * Same as getApiBaseUrl() — always proxy through /hireloop-api so production
 * never needs cross-origin CORS to Railway. Vercel rewrites stream to the API.
 */
export function getUploadApiBaseUrl(): string {
  return getApiBaseUrl();
}

/**
 * API base for server-side route handlers (OAuth callback, RSC).
 *
 * Always call the FastAPI host directly — never loop back through the Next.js
 * `/hireloop-api` proxy. A route handler that fetches its own origin (e.g.
 * `localhost:3001/hireloop-api/...` during `/auth/callback`) can deadlock the
 * dev server or fail on Vercel. Browser requests still use `getApiBaseUrl()`.
 */
export function getServerApiBaseUrl(_appOrigin?: string): string {
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
