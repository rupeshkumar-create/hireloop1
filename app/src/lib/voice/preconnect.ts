/**
 * Pre-warm voice STT WebSocket + config on mic hover (cuts first-word latency).
 */

import { getAccessToken } from "@/lib/api/auth-fetch";
import { getApiWsBaseUrl } from "@/lib/api/base-url";

let configInflight: Promise<void> | null = null;
let wsWarm: WebSocket | null = null;

export async function preconnectVoicePipeline(): Promise<void> {
  if (configInflight) return configInflight;

  configInflight = (async () => {
    try {
      const { apiAuthFetch } = await import("@/lib/api/auth-fetch");
      await apiAuthFetch("/api/v1/voice/config", { method: "GET" });
    } catch {
      /* optional */
    }

    try {
      const token = await getAccessToken();
      if (!token || typeof WebSocket === "undefined") return;

      if (wsWarm && wsWarm.readyState <= WebSocket.OPEN) return;

      const url =
        `${getApiWsBaseUrl()}/api/v1/voice/stream` +
        `?token=${encodeURIComponent(token)}&sr=48000`;
      wsWarm = new WebSocket(url);
      wsWarm.onopen = () => {
        // Close immediately — TCP/TLS + auth handshake is what we wanted warm.
        setTimeout(() => {
          try {
            wsWarm?.close();
          } catch {
            /* ignore */
          }
          wsWarm = null;
        }, 100);
      };
      wsWarm.onerror = () => {
        wsWarm = null;
      };
    } catch {
      wsWarm = null;
    } finally {
      configInflight = null;
    }
  })();

  return configInflight;
}
