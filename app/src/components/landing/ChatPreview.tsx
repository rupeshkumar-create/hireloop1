"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Mic, Send, Sparkles, Zap } from "@/components/brand/icons";
import {
  LANDING_AGENTS,
  type LandingAudience,
} from "@/components/landing/landing-audience";
import { BTN_COMPOSER_ICON, BTN_COMPOSER_SEND } from "@/lib/button-classes";
import { cn } from "@/lib/utils";

type Line =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; actions?: string };

const TYPING_MS = 850;
const READ_MS = 1500;
const RESTART_MS = 3000;

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

const CANDIDATE_SCRIPT: Line[] = [
  {
    role: "assistant",
    text: "Hi, I'm Aarya. Tell me what you're after — type or tap the mic.",
  },
  { role: "user", text: "Senior backend in Vienna, €90k+, remote-friendly." },
  {
    role: "assistant",
    text: "Found 14 live roles — 8 in Vienna, 4 across Austria, 2 EU-remote. Top match: Staff Engineer at a Series B fintech, 89% fit. Want a warm intro?",
    actions: "Aarya performed 4 actions",
  },
  { role: "user", text: "Yes — request the intro." },
  {
    role: "assistant",
    text: "Done. CV tailored, intro sent from your Gmail. I'll notify you when they reply.",
    actions: "Aarya performed 2 actions",
  },
];

const RECRUITER_SCRIPT: Line[] = [
  {
    role: "assistant",
    text: "Hi, I'm Nitya. Describe the role you're hiring for — I'll find interested, pre-scored candidates.",
  },
  { role: "user", text: "Staff backend engineer, Bangalore, ₹45–55L, Python + Postgres." },
  {
    role: "assistant",
    text: "Brief saved. Surfaced 6 candidates above 80% fit who opted in this week. Top match: 7 yrs fintech, actively looking. Warm intro draft ready.",
    actions: "Nitya performed 3 actions",
  },
  { role: "user", text: "Send the intro to the top two." },
  {
    role: "assistant",
    text: "Intros queued. Candidates notified — you'll see replies in your inbox.",
    actions: "Nitya performed 2 actions",
  },
];

const SCRIPTS: Record<LandingAudience, Line[]> = {
  candidate: CANDIDATE_SCRIPT,
  recruiter: RECRUITER_SCRIPT,
};

type ChatPreviewProps = {
  audience?: LandingAudience;
};

export function ChatPreview({ audience = "candidate" }: ChatPreviewProps) {
  const script = SCRIPTS[audience];
  const agent = LANDING_AGENTS[audience];

  const [shown, setShown] = useState(1);
  const [typing, setTyping] = useState(false);
  const reduced = useRef(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Reset demo when audience toggles
  useEffect(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    reduced.current = prefersReducedMotion();

    if (reduced.current) {
      setShown(script.length);
      setTyping(false);
      return;
    }

    setShown(1);
    setTyping(false);

    const schedule = (fn: () => void, ms: number) => {
      const t = setTimeout(fn, ms);
      timers.current.push(t);
    };

    const step = (count: number) => {
      if (count >= script.length) {
        schedule(() => {
          setShown(1);
          setTyping(false);
          step(1);
        }, RESTART_MS);
        return;
      }

      const next = script[count];
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

    schedule(() => step(1), READ_MS);

    return () => {
      timers.current.forEach(clearTimeout);
      timers.current = [];
    };
  }, [audience, script]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [shown, typing]);

  const visible = script.slice(0, shown);

  return (
    <motion.div
      layout
      className="w-full overflow-hidden rounded-xl border border-ink-100 bg-paper-1 shadow-2"
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, ease: [0.21, 0.47, 0.32, 0.98] }}
    >
      <div className="flex items-center gap-2.5 border-b border-ink-100 px-4 py-3">
        <motion.div
          key={agent.initial}
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink-900"
        >
          <span className="text-micro font-semibold text-paper-0">{agent.initial}</span>
        </motion.div>
        <div className="min-w-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={agent.name}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 6 }}
              transition={{ duration: 0.2 }}
            >
              <p className="text-small font-semibold leading-none text-ink-900">{agent.name}</p>
              <p className="mt-0.5 text-micro text-ink-400">{agent.chatTagline}</p>
            </motion.div>
          </AnimatePresence>
        </div>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-paper-0 px-2 py-1 text-micro text-ink-500 ring-1 ring-ink-100">
          <motion.span
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <Sparkles className="h-3 w-3 text-accent" strokeWidth={1.5} />
          </motion.span>
          Live demo
        </span>
      </div>

      <div
        ref={scrollRef}
        className="h-[320px] space-y-3 overflow-y-auto bg-paper-0 px-4 py-4"
      >
        <AnimatePresence initial={false}>
          {visible.map((line, i) =>
            line.role === "user" ? (
              <motion.div
                key={`${audience}-u-${i}`}
                initial={{ opacity: 0, y: 10, x: 8 }}
                animate={{ opacity: 1, y: 0, x: 0 }}
                transition={{ duration: 0.28, ease: [0.21, 0.47, 0.32, 0.98] }}
                className="flex justify-end"
              >
                <div className="max-w-[82%] rounded-2xl rounded-br-sm border-2 border-black bg-accent px-3.5 py-2.5 text-small leading-relaxed text-on-accent shadow-[0_0_0_2px_#b9f84c,0_0_0_4px_#000000]">
                  {line.text}
                </div>
              </motion.div>
            ) : (
              <motion.div
                key={`${audience}-a-${i}`}
                initial={{ opacity: 0, y: 10, x: -8 }}
                animate={{ opacity: 1, y: 0, x: 0 }}
                transition={{ duration: 0.28, ease: [0.21, 0.47, 0.32, 0.98] }}
                className="flex justify-start gap-2"
              >
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-900">
                  <span className="text-[10px] font-semibold text-paper-0">{agent.initial}</span>
                </div>
                <div className="max-w-[82%] space-y-1.5">
                  <div className="rounded-2xl rounded-bl-sm border border-ink-100 bg-paper-1 px-3.5 py-2.5 text-small leading-relaxed text-ink-900 shadow-1">
                    {line.text}
                  </div>
                  {line.actions ? (
                    <motion.span
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.15 }}
                      className="inline-flex items-center gap-1.5 text-micro text-ink-500"
                    >
                      <Zap className="h-3 w-3 text-accent" strokeWidth={1.5} />
                      {line.actions}
                    </motion.span>
                  ) : null}
                </div>
              </motion.div>
            ),
          )}
        </AnimatePresence>

        <AnimatePresence>
          {typing ? (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex justify-start gap-2"
            >
              <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink-900">
                <span className="text-[10px] font-semibold text-paper-0">{agent.initial}</span>
              </div>
              <div className="rounded-2xl rounded-bl-sm border border-ink-100 bg-paper-1 px-3.5 py-3 shadow-1">
                <div className="flex items-center gap-1">
                  {[0, 1, 2].map((dot) => (
                    <motion.span
                      key={dot}
                      className="h-1.5 w-1.5 rounded-full bg-ink-300"
                      animate={{ scale: [0.4, 1, 0.4], opacity: [0.4, 1, 0.4] }}
                      transition={{
                        duration: 1.2,
                        repeat: Infinity,
                        delay: dot * 0.15,
                      }}
                    />
                  ))}
                </div>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>

      <div className="border-t border-ink-100 bg-paper-1 px-4 py-3">
        <div className="flex items-center gap-2 rounded-xl border border-ink-100 bg-paper-0 px-3 py-2">
          <span className="flex-1 select-none text-small text-ink-300">
            Message {agent.name}…
          </span>
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            className={cn(BTN_COMPOSER_ICON, "relative shrink-0")}
          >
            <Mic className="h-4 w-4" strokeWidth={1.75} />
          </button>
          <button
            type="button"
            aria-hidden
            tabIndex={-1}
            className={cn(BTN_COMPOSER_SEND, "shrink-0")}
          >
            <Send className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </motion.div>
  );
}
