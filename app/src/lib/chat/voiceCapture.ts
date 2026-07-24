/** Ignore accidental mic taps that are too short to contain speech. */
export const MIN_VOICE_CAPTURE_MS = 350;

export function shouldDiscardVoiceCapture(elapsedMs: number): boolean {
  return elapsedMs < MIN_VOICE_CAPTURE_MS;
}
