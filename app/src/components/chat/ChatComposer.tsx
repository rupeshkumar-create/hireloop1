"use client";

import { useState, type KeyboardEvent, type RefObject } from "react";
import {
  Loader2,
  Mic,
  Paperclip,
  Phone,
  Send,
  Settings,
  Square,
} from "@/components/brand/icons";
import { BTN_COMPOSER_ICON, BTN_COMPOSER_SEND } from "@/lib/button-classes";
import { storeVoiceSendOnPause } from "@/lib/chat/aaryaStream";
import { storeChatCoachSeen, type ChatReplyMode } from "@/lib/chat/voicePreferences";
import { preconnectVoicePipeline } from "@/lib/voice/preconnect";
import { cn } from "@/lib/utils";
import { ComposerWaveform } from "./ComposerWaveform";
import { VoiceTranscriptReview } from "./VoiceTranscriptReview";

const CHAT_COLUMN_CLASS = "max-w-2xl mx-auto px-4";

export type ChatComposerProps = {
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onMicClick: () => void;
  onCancelMic: () => void;
  onStopGeneration: () => void;
  onStartCareerCall: () => void;
  onResumeFile: (file: File) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
  fileInputRef: RefObject<HTMLInputElement>;
  isStreaming: boolean;
  isRecording: boolean;
  isPlaying: boolean;
  voiceProcessing: boolean;
  audioLevel: number;
  interimTranscript: string;
  pendingVoiceTranscript: string | null;
  onPendingTranscriptChange: (value: string | null) => void;
  onSendVoiceTranscript: () => void;
  sendImmediately: boolean;
  onSendImmediatelyChange: (value: boolean) => void;
  replyMode: ChatReplyMode;
  onReplyModeChange: (mode: ChatReplyMode) => void;
  hinglishHint: boolean;
  voiceError: string | null;
  showCoachMark: boolean;
  onDismissCoach: () => void;
  isUploading: boolean;
  composerInputDisabled: boolean;
  isAwaitingDraft: boolean;
  voiceEnabled: boolean;
  onComposerFocus: () => void;
  onKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void;
  interruptSpeech: () => void;
};

export function ChatComposer({
  input,
  onInputChange,
  onSend,
  onMicClick,
  onCancelMic,
  onStopGeneration,
  onStartCareerCall,
  onResumeFile,
  textareaRef,
  fileInputRef,
  isStreaming,
  isRecording,
  isPlaying,
  voiceProcessing,
  audioLevel,
  interimTranscript,
  pendingVoiceTranscript,
  onPendingTranscriptChange,
  onSendVoiceTranscript,
  sendImmediately,
  onSendImmediatelyChange,
  replyMode,
  onReplyModeChange,
  hinglishHint,
  voiceError,
  showCoachMark,
  onDismissCoach,
  isUploading,
  composerInputDisabled,
  isAwaitingDraft,
  voiceEnabled,
  onComposerFocus,
  onKeyDown,
  interruptSpeech,
}: ChatComposerProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="bg-paper-0 pt-2 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
      <div className={cn(CHAT_COLUMN_CLASS, "space-y-2")}>
        {showCoachMark && (
          <div className="flex items-start justify-between gap-3 rounded-lg border border-accent/25 bg-accent/5 px-3 py-2.5">
            <p className="text-micro text-ink-700 leading-relaxed">
              Type or tap the mic to talk with Aarya. Your job matches are
              always in <span className="font-medium">Matches</span> on the
              left; chat never blocks them.
            </p>
            <button
              type="button"
              onClick={() => {
                storeChatCoachSeen();
                onDismissCoach();
              }}
              className="shrink-0 text-micro font-medium text-ink-600 hover:text-ink-900"
            >
              Got it
            </button>
          </div>
        )}

        {(isStreaming || isRecording || voiceProcessing || isPlaying || pendingVoiceTranscript) && (
          <div className="flex items-center justify-between gap-2 rounded-lg border border-ink-100 bg-ink-50/80 px-3 py-2">
            <div className="min-w-0 flex-1 flex items-center gap-2">
              <ComposerWaveform
                level={audioLevel}
                active={isRecording || isPlaying}
                mode={isRecording ? "listening" : "speaking"}
              />
              <div className="min-w-0 flex-1">
                <p className="text-micro font-medium text-ink-800">
                  {isRecording
                    ? "Listening — tap mic again to send"
                    : voiceProcessing
                      ? "Processing voice…"
                      : isStreaming
                        ? "Aarya is replying…"
                        : isPlaying
                          ? "Speaking…"
                          : "Review your message"}
                </p>
                {isRecording && interimTranscript && (
                  <p
                    className="text-micro text-ink-600 truncate mt-0.5"
                    aria-live="polite"
                  >
                    {interimTranscript}
                  </p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {isStreaming && (
                <button
                  type="button"
                  onClick={onStopGeneration}
                  className="text-micro text-ink-700 underline underline-offset-2"
                >
                  Stop
                </button>
              )}
              {isPlaying && !isStreaming && (
                <button
                  type="button"
                  onClick={interruptSpeech}
                  className="text-micro text-ink-600 underline underline-offset-2"
                >
                  Stop
                </button>
              )}
              {isRecording && (
                <button
                  type="button"
                  onClick={() => void onCancelMic()}
                  className="text-micro text-ink-700 underline underline-offset-2"
                >
                  Cancel
                </button>
              )}
              {replyMode === "voice" && (isPlaying || isRecording) && (
                <button
                  type="button"
                  onClick={() => onReplyModeChange("text")}
                  className="text-micro text-ink-600 underline underline-offset-2"
                >
                  Text replies
                </button>
              )}
            </div>
          </div>
        )}

        {pendingVoiceTranscript && (
          <VoiceTranscriptReview
            transcript={pendingVoiceTranscript}
            onChange={(value) => onPendingTranscriptChange(value)}
            onSend={onSendVoiceTranscript}
            onDiscard={() => onPendingTranscriptChange(null)}
          />
        )}

        <div
          className={cn(
            "bg-paper-1 rounded-lg border border-ink-200 shadow-1",
            "transition-shadow duration-fast",
            "focus-within:shadow-2 focus-within:border-ink-300",
          )}
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onFocus={onComposerFocus}
            onKeyDown={onKeyDown}
            placeholder={
              isRecording
                ? "Tap here to type instead…"
                : pendingVoiceTranscript
                  ? "Edit your voice message above, then send."
                  : isAwaitingDraft
                    ? "Aarya is thinking… send to barge in"
                    : isStreaming
                      ? "Send to interrupt Aarya…"
                      : "Ask Aarya anything…"
            }
            rows={1}
            disabled={composerInputDisabled && !isStreaming}
            className={cn(
              "w-full bg-transparent resize-none text-body text-ink-900",
              "placeholder:text-ink-400 focus:outline-none leading-relaxed",
              "px-4 pt-2 pb-1 max-h-[80px] disabled:opacity-60",
            )}
          />

          <div className="flex items-center justify-between px-3 pb-2 pt-0.5">
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                title={isUploading ? "Uploading resume…" : "Upload resume (PDF or DOCX)"}
                disabled={isUploading}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  BTN_COMPOSER_ICON,
                  isUploading && "opacity-40 cursor-not-allowed",
                )}
              >
                {isUploading ? (
                  <Loader2 className="h-[18px] w-[18px] animate-spin" strokeWidth={1.5} />
                ) : (
                  <Paperclip className="h-[18px] w-[18px]" strokeWidth={1.5} />
                )}
              </button>
              <div className="relative">
                <button
                  type="button"
                  aria-label="Voice settings"
                  aria-expanded={settingsOpen}
                  title="Voice settings"
                  onClick={() => setSettingsOpen((o) => !o)}
                  className={BTN_COMPOSER_ICON}
                >
                  <Settings className="h-[17px] w-[17px]" strokeWidth={1.5} />
                </button>
                {settingsOpen && (
                  <div
                    className="absolute bottom-full left-0 mb-2 w-56 rounded-lg border border-ink-200 bg-paper-0 p-3 shadow-2 z-20 space-y-3"
                    role="dialog"
                    aria-label="Voice settings"
                  >
                    <div>
                      <p className="text-micro font-medium text-ink-800 mb-1.5">
                        After recording
                      </p>
                      <label className="flex items-center gap-2 text-micro text-ink-700 py-0.5">
                        <input
                          type="radio"
                          name="voice-send-mode"
                          checked={sendImmediately}
                          onChange={() => {
                            storeVoiceSendOnPause(true);
                            onSendImmediatelyChange(true);
                          }}
                        />
                        Send immediately
                      </label>
                      <label className="flex items-center gap-2 text-micro text-ink-700 py-0.5">
                        <input
                          type="radio"
                          name="voice-send-mode"
                          checked={!sendImmediately}
                          onChange={() => {
                            storeVoiceSendOnPause(false);
                            onSendImmediatelyChange(false);
                          }}
                        />
                        Review before send
                      </label>
                    </div>
                    <div>
                      <p className="text-micro font-medium text-ink-800 mb-1.5">
                        Aarya replies
                      </p>
                      <label className="flex items-center gap-2 text-micro text-ink-700 py-0.5">
                        <input
                          type="radio"
                          name="reply-mode"
                          checked={replyMode === "voice"}
                          onChange={() => onReplyModeChange("voice")}
                        />
                        Voice
                      </label>
                      <label className="flex items-center gap-2 text-micro text-ink-700 py-0.5">
                        <input
                          type="radio"
                          name="reply-mode"
                          checked={replyMode === "text"}
                          onChange={() => onReplyModeChange("text")}
                        />
                        Text
                      </label>
                    </div>
                    <button
                      type="button"
                      className="text-micro text-ink-500 underline"
                      onClick={() => setSettingsOpen(false)}
                    >
                      Close
                    </button>
                  </div>
                )}
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onResumeFile(file);
              }}
            />

            <div className="flex items-center gap-1">
              {voiceEnabled && (
                <button
                  type="button"
                  title="Start 15-min career call"
                  aria-label="Start career call"
                  onClick={onStartCareerCall}
                  disabled={isRecording || voiceProcessing}
                  className={cn(
                    BTN_COMPOSER_ICON,
                    (isRecording || voiceProcessing) &&
                      "opacity-40 cursor-not-allowed",
                  )}
                >
                  <Phone className="h-[17px] w-[17px]" strokeWidth={1.5} />
                </button>
              )}

              {(input.trim() || isStreaming) && (
                <button
                  type="button"
                  onClick={onSend}
                  disabled={composerInputDisabled && !isStreaming}
                  aria-label={
                    isStreaming && !input.trim()
                      ? "Stop generation"
                      : "Send message"
                  }
                  title={
                    isStreaming && !input.trim()
                      ? "Stop generation"
                      : undefined
                  }
                  className={cn(
                    BTN_COMPOSER_SEND,
                    composerInputDisabled &&
                      !isStreaming &&
                      "opacity-40 cursor-not-allowed pointer-events-none",
                  )}
                >
                  {isStreaming && !input.trim() ? (
                    <Square className="h-3.5 w-3.5" strokeWidth={2} fill="currentColor" />
                  ) : (
                    <Send className="h-4 w-4" strokeWidth={1.5} />
                  )}
                </button>
              )}

              {voiceEnabled ? (
                <button
                  type="button"
                  onPointerEnter={() => void preconnectVoicePipeline()}
                  onFocus={() => void preconnectVoicePipeline()}
                  onClick={() => void onMicClick()}
                  disabled={voiceProcessing || Boolean(pendingVoiceTranscript)}
                  aria-pressed={isRecording}
                  aria-label={isRecording ? "Stop recording" : "Start voice message"}
                  title={isRecording ? "Tap to stop" : "Tap to talk"}
                  className={cn(
                    BTN_COMPOSER_ICON,
                    "h-10 w-10",
                    isRecording && "text-destructive animate-pulse",
                    voiceProcessing &&
                      "opacity-40 cursor-not-allowed pointer-events-none",
                  )}
                >
                  {isRecording ? (
                    <Square className="h-3.5 w-3.5" strokeWidth={2} fill="currentColor" />
                  ) : (
                    <Mic className="h-[17px] w-[17px]" strokeWidth={2} />
                  )}
                </button>
              ) : (
                !input.trim() && (
                  <button
                    type="button"
                    onClick={onSend}
                    disabled={!input.trim()}
                    aria-label="Send"
                    className={cn(BTN_COMPOSER_ICON, "opacity-50 cursor-not-allowed")}
                  >
                    <Send className="h-4 w-4" strokeWidth={1.5} />
                  </button>
                )
              )}
            </div>
          </div>
        </div>

        {hinglishHint && (
          <p className="text-micro text-ink-500 text-center px-2">
            Hindi/English mix detected —{" "}
            <button
              type="button"
              className="underline underline-offset-2 hover:text-ink-800"
              onClick={() => onReplyModeChange("text")}
            >
              use text replies
            </button>{" "}
            if voice is unclear.
          </p>
        )}

        {voiceError && (
          <div className="text-center space-y-1">
            <p className="text-small text-ink-700">{voiceError}</p>
            <p className="text-micro text-ink-500">
              You can keep typing. Allow microphone access and reload to use voice.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
