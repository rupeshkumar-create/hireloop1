"use client";

/**
 * Mock interview session — P21
 *
 * Full-screen chat UI matching the Aarya design system:
 *   - Assistant messages: ink-100 bg, ink-900 text, subtle border
 *   - User messages: ink-900 bg, paper-0 text
 *   - Feedback card at session end with score + tips
 *   - Mic button via useVoice (same as Aarya chat)
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  CheckCircle,
  Mic,
  Send,
  Square,
  Brain,
} from "lucide-react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import { useVoice } from "@/lib/hooks/useVoice";
import { Badge, Button, Card, CardBody, CardHeader } from "@/components/ui";
import { cn } from "@/lib/utils";

type Message = { role: "user" | "assistant"; content: string };

type Feedback = {
  overall_score?: number;
  communication?: string;
  technical_accuracy?: string;
  areas_to_improve?: string[];
  strengths?: string[];
  summary?: string;
};

export default function MockInterviewSessionPage() {
  const { id } = useParams<{ id: string }>();

  const [messages, setMessages]     = useState<Message[]>([]);
  const [input, setInput]           = useState("");
  const [loading, setLoading]       = useState(false);
  const [completed, setCompleted]   = useState(false);
  const [feedback, setFeedback]     = useState<Feedback | null>(null);
  const [sessionType, setSessionType] = useState<string>("");

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { isRecording, startRecording, stopRecording } = useVoice();

  // ── Fetch session info on mount ─────────────────────────────────────────
  useEffect(() => {
    apiFetch<{ interview_type: string; role_target: string; status: string }>(
      `/api/v1/mock-interview/sessions/${id}`
    )
      .then((s) => {
        setSessionType(s.interview_type.replace(/_/g, " "));
        if (s.status === "completed") setCompleted(true);
      })
      .catch(() => {});
  }, [id]);

  // ── Auto-scroll ─────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── Textarea auto-grow ──────────────────────────────────────────────────
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  // ── Send message ─────────────────────────────────────────────────────────
  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || completed || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content }]);
    setLoading(true);

    try {
      const res = await apiFetch<{
        reply: string;
        completed: boolean;
        feedback: Feedback | null;
      }>(`/api/v1/mock-interview/sessions/${id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      if (res.completed) {
        setCompleted(true);
        if (res.feedback) setFeedback(res.feedback);
      }
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: `⚠ ${(e as Error).message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  // ── Voice ────────────────────────────────────────────────────────────────
  async function handleMic() {
    if (isRecording) {
      const transcript = await stopRecording();
      if (transcript) void send(transcript);
    } else {
      await startRecording();
    }
  }

  return (
    <main className="flex flex-col h-screen bg-paper-0 overflow-hidden">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="shrink-0 h-14 flex items-center gap-3 px-4 bg-paper-1 border-b border-ink-100">
        <Link
          href="/mock-interview"
          className="text-ink-500 hover:text-ink-900 transition-colors p-1 -ml-1"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
        </Link>

        <div className="w-8 h-8 rounded-full bg-ink-900 flex items-center justify-center shrink-0">
          <Brain className="h-4 w-4 text-paper-0" strokeWidth={1.5} />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-body font-semibold text-ink-900 truncate">
            Mock interview
          </p>
          {sessionType && (
            <p className="text-micro text-ink-500 capitalize">{sessionType}</p>
          )}
        </div>

        {completed && (
          <Badge tone="accent">
            <CheckCircle className="h-3 w-3 mr-1" strokeWidth={2} />
            Session complete
          </Badge>
        )}
      </header>

      {/* ── Messages ───────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-2xl mx-auto space-y-4">

          {messages.length === 0 && !loading && (
            <div className="text-center text-ink-500 text-small pt-12 space-y-2">
              <Brain className="h-10 w-10 mx-auto text-ink-300" strokeWidth={1} />
              <p>The interviewer will begin when you&apos;re ready.</p>
              <p className="text-micro text-ink-300">
                Type or use the mic to answer each question.
              </p>
            </div>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "flex",
                m.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              {m.role === "assistant" && (
                <div className="w-7 h-7 rounded-full bg-ink-900 flex items-center justify-center mr-2.5 mt-1 shrink-0">
                  <Brain className="h-3.5 w-3.5 text-paper-0" strokeWidth={1.5} />
                </div>
              )}
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-3 text-body leading-relaxed",
                  m.role === "user"
                    ? "bg-ink-900 text-paper-0 rounded-br-sm"
                    : "bg-paper-1 text-ink-900 border border-ink-100 shadow-1 rounded-bl-sm"
                )}
              >
                <p className="whitespace-pre-wrap">{m.content}</p>
              </div>
            </div>
          ))}

          {/* Typing indicator */}
          {loading && (
            <div className="flex justify-start">
              <div className="w-7 h-7 rounded-full bg-ink-900 flex items-center justify-center mr-2.5 shrink-0">
                <Brain className="h-3.5 w-3.5 text-paper-0" strokeWidth={1.5} />
              </div>
              <div className="bg-paper-1 border border-ink-100 shadow-1 rounded-2xl rounded-bl-sm px-4 py-3">
                <div className="flex items-center gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-1.5 h-1.5 rounded-full bg-ink-300 animate-typing-dot"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Feedback card ─────────────────────────────────────────── */}
          {completed && feedback && (
            <div className="mt-4">
              <FeedbackCard feedback={feedback} />
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Composer ───────────────────────────────────────────────────── */}
      {!completed && (
        <div className="shrink-0 border-t border-ink-100 bg-paper-1 px-4 py-3">
          <div className="max-w-2xl mx-auto">
            <div className="flex items-end gap-2 rounded-xl border border-ink-100 bg-paper-0 px-3 py-2 focus-within:border-ink-300 focus-within:ring-2 focus-within:ring-accent/15 transition-all">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                placeholder="Type your answer… (Enter to send, Shift+Enter for new line)"
                rows={1}
                disabled={loading}
                className="
                  flex-1 resize-none bg-transparent text-body text-ink-900
                  placeholder:text-ink-300 outline-none min-h-[24px] max-h-40
                "
              />

              {/* Mic */}
              <button
                type="button"
                onClick={() => void handleMic()}
                disabled={loading}
                className={cn(
                  "shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
                  isRecording
                    ? "bg-destructive text-paper-0 animate-pulse"
                    : "text-ink-500 hover:text-ink-900 hover:bg-ink-100"
                )}
              >
                {isRecording
                  ? <Square className="h-3.5 w-3.5" strokeWidth={2} />
                  : <Mic className="h-3.5 w-3.5" strokeWidth={1.5} />}
              </button>

              {/* Send */}
              <button
                type="button"
                onClick={() => void send()}
                disabled={!input.trim() || loading}
                className={cn(
                  "shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
                  input.trim() && !loading
                    ? "bg-accent text-on-accent"
                    : "text-ink-300 cursor-not-allowed"
                )}
              >
                <Send className="h-3.5 w-3.5" strokeWidth={1.5} />
              </button>
            </div>
            <p className="text-micro text-ink-300 mt-1.5 text-center">
              Aarya evaluates communication, accuracy, and structure
            </p>
          </div>
        </div>
      )}

    </main>
  );
}

// ── Feedback card ──────────────────────────────────────────────────────────────

function FeedbackCard({ feedback }: { feedback: Feedback }) {
  const score = feedback.overall_score ?? null;

  return (
    <Card className="border-ink-100 shadow-2">
      <CardHeader
        title="Session feedback"
        description="Aarya's structured evaluation of your answers"
        action={
          score !== null ? (
            <div className="flex items-center gap-2">
              <span className="text-small text-ink-500">Overall</span>
              <span
                className={cn(
                  "text-h2 font-semibold",
                  score >= 8 ? "text-accent" :
                  score >= 6 ? "text-ink-700" :
                  "text-destructive"
                )}
              >
                {score}/10
              </span>
            </div>
          ) : undefined
        }
      />
      <CardBody>
        <div className="space-y-4">

          {feedback.summary && (
            <p className="text-body text-ink-700 leading-relaxed">
              {feedback.summary}
            </p>
          )}

          <div className="grid sm:grid-cols-2 gap-4">
            {feedback.strengths && feedback.strengths.length > 0 && (
              <div>
                <p className="text-small font-semibold text-ink-900 mb-2">
                  Strengths
                </p>
                <ul className="space-y-1">
                  {feedback.strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-small text-ink-700">
                      <CheckCircle
                        className="h-3.5 w-3.5 text-accent shrink-0 mt-0.5"
                        strokeWidth={2}
                      />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.areas_to_improve && feedback.areas_to_improve.length > 0 && (
              <div>
                <p className="text-small font-semibold text-ink-900 mb-2">
                  Areas to improve
                </p>
                <ul className="space-y-1">
                  {feedback.areas_to_improve.map((a, i) => (
                    <li key={i} className="flex items-start gap-2 text-small text-ink-700">
                      <span className="w-1.5 h-1.5 rounded-full bg-ink-300 shrink-0 mt-1.5" />
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {(feedback.communication || feedback.technical_accuracy) && (
            <div className="grid sm:grid-cols-2 gap-3 pt-2 border-t border-ink-100">
              {feedback.communication && (
                <div className="rounded-md bg-ink-50 px-3 py-2.5">
                  <p className="text-micro text-ink-500 uppercase mb-1">Communication</p>
                  <p className="text-small text-ink-700">{feedback.communication}</p>
                </div>
              )}
              {feedback.technical_accuracy && (
                <div className="rounded-md bg-ink-50 px-3 py-2.5">
                  <p className="text-micro text-ink-500 uppercase mb-1">Technical accuracy</p>
                  <p className="text-small text-ink-700">{feedback.technical_accuracy}</p>
                </div>
              )}
            </div>
          )}

          <div className="pt-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => window.location.href = "/mock-interview"}
            >
              Start another session
            </Button>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
