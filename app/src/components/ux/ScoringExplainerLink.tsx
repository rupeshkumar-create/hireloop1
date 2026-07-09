"use client";

import { useState } from "react";
import { HelpCircle } from "@/components/brand/icons";

export function ScoringExplainerLink() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-micro text-ink-500 hover:text-ink-900"
      >
        <HelpCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
        How we score
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/30 p-4"
          role="dialog"
          aria-modal
        >
          <div className="max-w-md rounded-lg border border-ink-100 bg-paper-0 p-5 shadow-2 space-y-3">
            <h3 className="text-h3 text-ink-900">How Hireschema scores matches</h3>
            <ul className="text-small text-ink-600 space-y-2 list-disc pl-4">
              <li>Market-scoped roles — jobs match your home market and eligible remote roles.</li>
              <li>Skills, experience, location, and salary fit — no demographic fields.</li>
              <li>Semantic embeddings plus lexical signals; bias audit on every score row.</li>
            </ul>
            <button
              type="button"
              className="text-small font-medium text-accent"
              onClick={() => setOpen(false)}
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  );
}
