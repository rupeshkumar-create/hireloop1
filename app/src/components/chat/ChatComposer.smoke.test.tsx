import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatComposer } from "./ChatComposer";

afterEach(() => cleanup());

function renderComposer(
  overrides: Partial<React.ComponentProps<typeof ChatComposer>> = {},
) {
  const props: React.ComponentProps<typeof ChatComposer> = {
    input: "",
    onInputChange: vi.fn(),
    onSend: vi.fn(),
    onMicClick: vi.fn(),
    onCancelMic: vi.fn(),
    onStopGeneration: vi.fn(),
    onStartCareerCall: vi.fn(),
    onResumeFile: vi.fn(),
    textareaRef: createRef<HTMLTextAreaElement>() as React.RefObject<HTMLTextAreaElement>,
    fileInputRef: createRef<HTMLInputElement>() as React.RefObject<HTMLInputElement>,
    isStreaming: false,
    isRecording: false,
    isPlaying: false,
    voiceProcessing: false,
    audioLevel: 0.4,
    interimTranscript: "",
    pendingVoiceTranscript: null,
    onPendingTranscriptChange: vi.fn(),
    onSendVoiceTranscript: vi.fn(),
    sendImmediately: true,
    onSendImmediatelyChange: vi.fn(),
    replyMode: "voice",
    onReplyModeChange: vi.fn(),
    hinglishHint: false,
    voiceError: null,
    showCoachMark: false,
    onDismissCoach: vi.fn(),
    isUploading: false,
    composerInputDisabled: false,
    isAwaitingDraft: false,
    voiceEnabled: true,
    onComposerFocus: vi.fn(),
    onKeyDown: vi.fn(),
    interruptSpeech: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<ChatComposer {...props} />) };
}

describe("ChatComposer smoke", () => {
  it("exposes toggle mic, settings, and career call entry", () => {
    const { props } = renderComposer();
    expect(screen.getByRole("button", { name: /start voice message/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /voice settings/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start career call/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start voice message/i }));
    expect(props.onMicClick).toHaveBeenCalledOnce();
  });

  it("shows stop recording affordance while recording", () => {
    renderComposer({ isRecording: true, audioLevel: 0.8 });
    expect(screen.getByRole("button", { name: /stop recording/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /listening/i })).toBeInTheDocument();
    expect(screen.getByText(/listening — tap mic again to send/i)).toBeInTheDocument();
  });

  it("settings can switch to review-before-send", () => {
    const { props } = renderComposer();
    fireEvent.click(screen.getByRole("button", { name: /voice settings/i }));
    fireEvent.click(screen.getByLabelText(/review before send/i));
    expect(props.onSendImmediatelyChange).toHaveBeenCalledWith(false);
  });

  it("send while streaming with empty input stops generation", () => {
    const { props } = renderComposer({ isStreaming: true, input: "" });
    fireEvent.click(screen.getByRole("button", { name: /stop generation/i }));
    expect(props.onSend).toHaveBeenCalledOnce();
  });

  it("career call button fires", () => {
    const { props } = renderComposer();
    fireEvent.click(screen.getByRole("button", { name: /start career call/i }));
    expect(props.onStartCareerCall).toHaveBeenCalledOnce();
  });
});
