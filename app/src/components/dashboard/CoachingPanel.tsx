"use client";

import { useState } from "react";
import {
  Briefcase,
  ChevronRight,
  GraduationCap,
  IndianRupee,
  SlidersHorizontal,
  Sparkles,
  User,
} from "@/components/brand/icons";
import { cn } from "@/lib/utils";

type CoachingCard = { title: string; desc: string; prompt: string };

const COACHING_TABS: {
  id: string;
  label: string;
  Icon: React.ElementType;
  cards: CoachingCard[];
}[] = [
  {
    id: "general",
    label: "General",
    Icon: GraduationCap,
    cards: [
      {
        title: "Recover from a tough interview or rejection",
        desc: "Bad result? Turn it into one specific lesson for next time.",
        prompt:
          "I had a tough interview / rejection recently. Help me recover and turn it into a specific lesson.",
      },
      {
        title: "Reflect on your job search progress",
        desc: "Mid-search check-in. What's working, what's not.",
        prompt:
          "Let's do a mid-search check-in. Help me reflect on what's working and what isn't in my job search.",
      },
      {
        title: "Plan your next career move",
        desc: "Stuck deciding what's next? Map it out together.",
        prompt: "I'm stuck deciding my next career move. Help me map out my options.",
      },
      {
        title: "Work through career anxiety",
        desc: "Feeling stuck, behind, or restless? Talk it through.",
        prompt: "I'm feeling anxious / stuck about my career. Can we talk it through?",
      },
      {
        title: "Get clarity on your career goals",
        desc: "What's your work personality? Find out.",
        prompt: "Help me get clarity on my career goals and what kind of work suits me.",
      },
    ],
  },
  {
    id: "product",
    label: "Product",
    Icon: Sparkles,
    cards: [
      {
        title: "Prep for a product role",
        desc: "Sharpen your product thinking and case answers.",
        prompt: "Help me prepare for a product management role interview.",
      },
      {
        title: "Build a product portfolio story",
        desc: "Frame your impact as crisp product narratives.",
        prompt: "Help me turn my experience into a strong product portfolio story.",
      },
    ],
  },
  {
    id: "salary",
    label: "Salary",
    Icon: IndianRupee,
    cards: [
      {
        title: "Know your market value",
        desc: "Benchmark your CTC for your role and city.",
        prompt: "What's my likely market value / salary range for my role?",
      },
      {
        title: "Negotiate an offer",
        desc: "Get a script for negotiating your next offer.",
        prompt: "Help me negotiate a job offer. Give me a script and strategy.",
      },
    ],
  },
  {
    id: "consulting",
    label: "Consulting",
    Icon: Briefcase,
    cards: [
      {
        title: "Crack a case interview",
        desc: "Practice structured case-solving frameworks.",
        prompt: "Let's practice a consulting case interview.",
      },
      {
        title: "Build a consulting CV",
        desc: "Tailor your resume for consulting roles.",
        prompt: "Help me tailor my CV for consulting roles.",
      },
    ],
  },
  {
    id: "mock",
    label: "Mock interview",
    Icon: User,
    cards: [
      {
        title: "Behavioural mock interview",
        desc: "Practice STAR-style behavioural questions.",
        prompt:
          "Let's run a behavioural mock interview. Ask me real questions and give feedback.",
      },
      {
        title: "Role-specific mock interview",
        desc: "Tailored to your target role and seniority.",
        prompt:
          "Run a role-specific mock interview tailored to my target role and give detailed feedback.",
      },
    ],
  },
  {
    id: "custom",
    label: "Custom",
    Icon: SlidersHorizontal,
    cards: [
      {
        title: "Coach me on anything",
        desc: "Bring your own topic — Aarya adapts.",
        prompt: "I'd like coaching on a specific topic. Let me tell you what it is.",
      },
    ],
  },
];

export type CoachingPanelProps = {
  onSendToChat: (text: string) => void;
};

export function CoachingPanel({ onSendToChat }: CoachingPanelProps) {
  const [activeTab, setActiveTab] = useState(COACHING_TABS[0].id);
  const tab = COACHING_TABS.find((t) => t.id === activeTab) ?? COACHING_TABS[0];

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-5 pt-4 overflow-x-auto border-b border-ink-100">
        {COACHING_TABS.map((t) => {
          const isActive = t.id === activeTab;
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-2 text-small font-medium shrink-0 border-b-2 -mb-px transition-colors duration-fast",
                isActive
                  ? "border-ink-900 text-ink-900"
                  : "border-transparent text-ink-400 hover:text-ink-700",
              )}
            >
              <t.Icon className="h-4 w-4" strokeWidth={1.5} />
              {t.label}
            </button>
          );
        })}
      </div>

      <div
        key={activeTab}
        className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-3 animate-fade-in overflow-y-auto"
      >
        {tab.cards.map((card) => (
          <button
            key={card.title}
            onClick={() => onSendToChat(card.prompt)}
            className="group text-left rounded-xl border border-ink-200 bg-paper-0 p-4 flex flex-col gap-2 hover:border-ink-300 hover:shadow-1 transition-all duration-fast active:scale-[0.99]"
          >
            <div className="w-9 h-9 rounded-lg bg-ink-100 flex items-center justify-center">
              <tab.Icon className="h-4 w-4 text-ink-600" strokeWidth={1.5} />
            </div>
            <p className="text-small font-semibold text-ink-900 leading-snug">{card.title}</p>
            <p className="text-micro text-ink-500 leading-snug flex-1">{card.desc}</p>
            <span className="inline-flex items-center gap-1 text-small font-medium text-ink-700 group-hover:text-ink-900 transition-colors mt-1">
              Begin
              <ChevronRight
                className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform"
                strokeWidth={2}
              />
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
