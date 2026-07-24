export function shouldBargeIn(state: {
  isStreaming: boolean;
  sendInFlight: boolean;
}): boolean {
  return state.isStreaming || state.sendInFlight;
}

export function abortActiveTurn(args: {
  abortRef: { current: AbortController | null };
  interruptSpeech: () => void;
}): { aborted: boolean } {
  const controller = args.abortRef.current;
  if (!controller) return { aborted: false };
  try {
    controller.abort();
  } catch {
    /* ignore */
  }
  args.abortRef.current = null;
  args.interruptSpeech();
  return { aborted: true };
}
