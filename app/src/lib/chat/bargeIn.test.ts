import { describe, expect, it, vi } from "vitest";
import { abortActiveTurn, shouldBargeIn } from "@/lib/chat/bargeIn";

describe("bargeIn", () => {
  it("barge-in when streaming or send in flight", () => {
    expect(shouldBargeIn({ isStreaming: true, sendInFlight: false })).toBe(true);
    expect(shouldBargeIn({ isStreaming: false, sendInFlight: true })).toBe(true);
    expect(shouldBargeIn({ isStreaming: false, sendInFlight: false })).toBe(false);
  });

  it("aborts controller, interrupts speech, and clears refs", () => {
    const abort = vi.fn();
    const interruptSpeech = vi.fn();
    const controller = { abort } as unknown as AbortController;
    const result = abortActiveTurn({
      abortRef: { current: controller },
      interruptSpeech,
    });
    expect(abort).toHaveBeenCalledOnce();
    expect(interruptSpeech).toHaveBeenCalledOnce();
    expect(result.aborted).toBe(true);
  });

  it("is a no-op when nothing is active", () => {
    const interruptSpeech = vi.fn();
    const result = abortActiveTurn({
      abortRef: { current: null },
      interruptSpeech,
    });
    expect(interruptSpeech).not.toHaveBeenCalled();
    expect(result.aborted).toBe(false);
  });
});
