import { describe, expect, it } from "vitest";
import {
  MIN_VOICE_CAPTURE_MS,
  shouldDiscardVoiceCapture,
} from "@/lib/chat/voiceCapture";

describe("voiceCapture", () => {
  it("exports a ~350ms minimum", () => {
    expect(MIN_VOICE_CAPTURE_MS).toBe(350);
  });

  it("discards captures shorter than the minimum", () => {
    expect(shouldDiscardVoiceCapture(0)).toBe(true);
    expect(shouldDiscardVoiceCapture(200)).toBe(true);
    expect(shouldDiscardVoiceCapture(349)).toBe(true);
  });

  it("keeps captures at or above the minimum", () => {
    expect(shouldDiscardVoiceCapture(350)).toBe(false);
    expect(shouldDiscardVoiceCapture(2000)).toBe(false);
  });
});
