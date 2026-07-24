export const VOICE_WEBSOCKET_PROTOCOL = "hireschema.voice.v1";

/** Build standards-valid protocols while keeping the bearer token out of URLs. */
export function voiceWebSocketProtocols(accessToken: string): string[] {
  const bytes = new TextEncoder().encode(accessToken);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const encoded = btoa(binary)
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
  return [VOICE_WEBSOCKET_PROTOCOL, `auth.${encoded}`];
}
