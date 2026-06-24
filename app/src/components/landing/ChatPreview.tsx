"use client";

/**
 * ChatPreview — the animated "chat-first" hero demo on the app landing page.
 *
 * Auto-plays a short scripted conversation with Aarya to show logged-out
 * visitors exactly what they land in after signup: a single chat surface you
 * can either type into or talk to. The composer at the bottom shows both the
 * text field and a pulsing mic so "type or talk" reads at a glance.
 *
 * Honors prefers-reduced-motion: the full transcript renders instantly with no
 * typing animation or looping.
 */

import { useEffect, useRef, useState } from "react";
import { Mic, Send, Sparkles, Zap } from "lucide-react";

type Line =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; actions?: string };

/** Scripted demo conversation — illustrative only, never hits the API. */
const SCRIPT: Line[] = [
  {
    role: "assistant",
    text: "Hi, I'm Aarya. Tell me what you're after — type it or tap the mic and talk.",
  },
  { role: "user", text: "Senior backend roles in Bangalore, ₹40L+, remote-friendly." },
  {
    role: "assistant",
    text: "On it. Found 12 live roles in India that fit. Your strongest match is a Staff Backend role at a Series B fintech — 91% fit. Want a warm intro?",
    actions: "Aarya performed 3 actions",
  },
  { role: "user", text: "Yes, request the intro." },
  {
    role: "assistant",
    text: "Done — I've asked their recruiter for a warm intro and flagged your profile. I'll ping you the moment they reply.",
    actions: "Aarya performed 2 actions",
  },
];

const TYPING_MS = 900;
const READ_MS = 1600;
const RESTART_MS = 3200;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function ChatPreview() {
  // How many lines of the script are currently visible.
  const [shown, setShown] = useState(1);
  const [typing, setTyping] = useState(false);
  const reduced = useRef(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    reduced.current = prefersReducedMotion();
    if (reduced.current) {
      setShown(SCRIPT.length);
      return;
    }

    const schedule = (fn: () => void, ms: number) => {
      const t = setTimeout(fn, ms);
      timers.current.push(t);
    };

    const step = (count: number) => {
      if (count >= SCRIPT.length) {
        // Pause on the finished conversation, then loop.
        schedule(() => {
          setShown(1);
          setTyping(false);
          step(1);
        }, RESTART_MS);
        return;
      }

      const next = SCRIPT[count];
      if (next.role === "assistant") {
        setTyping(true);
        schedule(() => {
          setTyping(false);
          setShown(count + 1);
          schedule(() => step(count + 1), READ_MS);
        }, TYPING_MS);
      } else {
        setShown(count + 1);
        schedule(() => step(count + 1), READ_MS);
      }
    };

    // Kick off after the greeting has had a beat to land.
    schedule(() => step(1), READ_MS);

    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, []);

  // Keep the latest line in view as the demo plays.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [shown, typing]);

  const visible = SCRIPT.slice(0, shown);

  return (
    <div className="w-full rounded-xl border border-ink-100 bg-paper-1 shadow-2 overflow-hidden">
      {/* Window chrome / agent header */}
      <div className="flex items-center gap-2.5 border-b border-ink-100 px-4 py-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-ink-900 shrink-0">
          <span className="text-paper-0 text-micro font-semibold">A</span>
        </div>
        <div className="min-w-0">
          <p className="text-small font-semibold text-ink-900 leading-none">Aarya</p>
          <p className="text-micro text-ink-400 mt-0.5">India-first AI recruiting copilot</p>
        </div>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-paper-0 px-2 py-1 text-micro text-ink-500 ring-1 ring-ink-100">
          <Sparkles className="h-3 w-3 text-accent" strokeWidth={1.5} />
          Live demo
        </span>
      </div>

      {/* Transcript */}
      <div
        ref={scrollRef}
        className="h-[320px] overflow-y-auto px-4 py-4 space-y-3 bg-paper-0"
      >
        {visible.map((line, i) =>
          line.role === "user" ? (
            <div key={i} className="flex justify-end animate-slide-up">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-ink-900 px-3.5 py-2.5 text-small text-paper-0 leading-relaxed">
                {line.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start gap-2 animate-slide-up">
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-900">
                <span className="text-paper-0 text-[10px] font-semibold">A</span>
              </div>
              <div className="max-w-[80%] space-y-1.5">
                <div className="rounded-2xl rounded-bl-sm border border-ink-100 bg-paper-1 px-3.5 py-2.5 text-small text-ink-900 leading-relaxed shadow-1">
                  {line.text}
                </div>
                {line.actions && (
                  <span className="inline-flex items-center gap-1.5 text-micro text-ink-500">
                    <Zap className="h-3 w-3 text-accent" strokeWidth={1.5} />
                    {line.actions}
                  </span>
                )}
              </div>
            </div>
          )
        )}

        {typing && (
          <div className="flex justify-start gap-2">
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-900">
              <span className="text-paper-0 text-[10px] font-semibold">A</span>
            </div>
            <div className="rounded-2xl rounded-bl-sm border border-ink-100 bg-paper-1 px-3.5 py-3 shadow-1">
              <div className="flex items-center gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="h-1.5 w-1.5 rounded-full bg-ink-300 animate-typing-dot"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Composer — shows "type or talk" without being interactive */}
      <div className="border-t border-ink-100 bg-paper-1 px-4 py-3">
        <div className="flex items-center gap-2 rounded-xl border border-ink-100 bg-paper-0 px-3 py-2">
          <span className="flex-1 text-small text-ink-300 select-none">
            Message Aarya…
          </span>
          {/* Mic — the voice half of "type or talk" */}
          <span className="relative flex h-8 w-8 items-center justify-center">
            <span className="absolute inset-0 rounded-lg bg-accent/10 animate-pulse" />
            <Mic className="relative h-4 w-4 text-accent" strokeWidth={1.75} />
          </span>
          {/* Send */}
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent">
            <Send className="h-3.5 w-3.5 text-paper-0" strokeWidth={1.5} />
          </span>
        </div>
      </div>
    </div>
  );
}
