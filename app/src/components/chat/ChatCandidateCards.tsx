"use client";

import { useEffect, useState } from "react";
import { MapPin, User } from "@/components/brand/icons";
import { Button, ScoreDot } from "@/components/ui";
import { formatCompRange } from "@/lib/api/recruiter";
import type { RankedCandidate, SearchMeta } from "@/lib/api/recruiter";
import { getCachedProfile } from "@/lib/api/profile";
import { marketByCode, type MarketCode } from "@/lib/markets";

type ChatCandidateCardsProps = {
  candidates: RankedCandidate[];
  introingId?: string | null;
  published?: boolean;
  searchMeta?: SearchMeta | null;
  onRequestIntro?: (candidate: RankedCandidate) => void;
  onPublishAndIntro?: (candidate: RankedCandidate) => void;
  onShortlist?: (candidate: RankedCandidate) => void;
  onPass?: (candidate: RankedCandidate) => void;
};

function candidateLabel(c: RankedCandidate): string {
  return c.display_name || c.current_title || c.headline || "Matched profile";
}

function formatLocation(c: RankedCandidate): string | null {
  const parts = [c.location_city, c.location_state].filter(Boolean);
  return parts.length ? parts.join(", ") : null;
}

const STAGE_LABEL: Record<string, string> = {
  search: "Sourced",
  shortlisted: "Shortlisted",
  intro_requested: "Intro requested",
  intro_made: "Intro made",
  hired: "Hired",
};

export function ChatCandidateCards({
  candidates,
  introingId,
  published = false,
  searchMeta,
  onRequestIntro,
  onPublishAndIntro,
  onShortlist,
  onPass,
}: ChatCandidateCardsProps) {
  const [market, setMarket] = useState<MarketCode>("IN");

  useEffect(() => {
    const m = getCachedProfile()?.user?.market;
    if (m) setMarket(marketByCode(m).code);
  }, []);

  if (!candidates.length) {
    return (
      <div className="rounded-lg border border-ink-100 bg-ink-50 px-3 py-3 text-left">
        <p className="text-small text-ink-600 font-medium">No matches yet</p>
        <p className="text-micro text-ink-500 mt-1 leading-relaxed">
          {searchMeta?.message ??
            "Ask Nitya to find candidates, or publish the role so candidates can discover it."}
        </p>
        {!published && (
          <p className="text-micro text-ink-500 mt-2">
            Tip: publish the role before requesting intros — or use{" "}
            <span className="font-medium text-ink-700">Publish & request intro</span> on a card.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="w-full max-w-xl space-y-3">
      <p className="text-small font-medium text-ink-600">
        {candidates.length} candidate{candidates.length !== 1 ? "s" : ""} matched
        {!published && (
          <span className="text-ink-400 font-normal"> · role not published yet</span>
        )}
      </p>
      <div className="space-y-3">
        {candidates.map((c) => {
          const canIntro = ["search", "shortlisted"].includes(c.stage ?? "search");
          const introBusy = introingId === c.candidate_id;
          const location = formatLocation(c);
          const expectedComp = formatCompRange(
            c.expected_ctc_min,
            c.expected_ctc_max,
            { market },
          );
          return (
            <div
              key={c.candidate_id}
              className="rounded-xl border border-ink-100 bg-paper-1 p-4 shadow-1"
            >
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-full bg-ink-100 flex items-center justify-center shrink-0">
                  <User className="h-4 w-4 text-ink-500" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-body font-semibold text-ink-900 truncate">
                        {candidateLabel(c)}
                      </p>
                      {(c.current_title || c.current_company) && (
                        <p className="text-small text-ink-700 mt-0.5 truncate">
                          {c.current_title}
                          {c.current_company ? ` @ ${c.current_company}` : ""}
                        </p>
                      )}
                    </div>
                    {c.overall_score > 0 && (
                      <ScoreDot value={c.overall_score} size="sm" label="match" />
                    )}
                  </div>

                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-micro text-ink-500">
                    {location && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="h-3 w-3 shrink-0" strokeWidth={1.5} />
                        {location}
                      </span>
                    )}
                    {expectedComp !== "Not set" && <span>{expectedComp}</span>}
                    <span>{STAGE_LABEL[c.stage ?? "search"] ?? c.stage}</span>
                  </div>

                  {c.match_explanation && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-micro text-ink-600 hover:text-ink-900">
                        Why this match
                      </summary>
                      <p className="mt-1 text-micro text-ink-500 leading-relaxed line-clamp-3">
                        {c.match_explanation}
                      </p>
                    </details>
                  )}
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {canIntro && published && onRequestIntro && (
                  <Button
                    variant="primary"
                    size="sm"
                    className="flex-1 min-w-[120px]"
                    loading={introBusy}
                    disabled={introBusy}
                    onClick={() => onRequestIntro(c)}
                  >
                    Request intro
                  </Button>
                )}
                {canIntro && !published && onPublishAndIntro && (
                  <Button
                    variant="primary"
                    size="sm"
                    className="flex-1 min-w-[140px]"
                    loading={introBusy}
                    disabled={introBusy}
                    onClick={() => onPublishAndIntro(c)}
                  >
                    Publish & request intro
                  </Button>
                )}
                {c.stage === "search" && onShortlist && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onShortlist(c)}
                  >
                    Shortlist
                  </Button>
                )}
                {onPass && c.stage === "search" && (
                  <Button variant="ghost" size="sm" onClick={() => onPass(c)}>
                    Pass
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
