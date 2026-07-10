"use client";

import { useEffect, useState } from "react";
import { BarChart3 } from "@/components/brand/icons";
import { Button, Card, CardBody } from "@/components/ui";
import { fetchSalarySuggestion, formatCompRange } from "@/lib/api/recruiter";
import { marketByCode, type MarketCode } from "@/lib/markets";

export function RoleSalarySuggestionPanel({
  roleId,
  market = "IN",
  onApply,
}: {
  roleId: string;
  market?: MarketCode;
  onApply?: (minLpa: number, maxLpa: number) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [suggestion, setSuggestion] = useState<{
    comp_min: number | null;
    comp_max: number | null;
    suggestion: Record<string, unknown>;
  } | null>(null);

  useEffect(() => {
    void fetchSalarySuggestion(roleId)
      .then(setSuggestion)
      .catch(() => setSuggestion(null))
      .finally(() => setLoading(false));
  }, [roleId]);

  const bench = suggestion?.suggestion?.benchmark as Record<string, unknown> | undefined;
  const corpus = suggestion?.suggestion?.corpus as Record<string, number> | undefined;
  const competitive = suggestion?.suggestion?.competitive as string | undefined;

  const suggestedMin = corpus?.p25 ?? (bench?.market_min_inr as number | undefined);
  const suggestedMax = corpus?.p75 ?? (bench?.market_max_inr as number | undefined);

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-accent" strokeWidth={1.5} />
          <h3 className="text-small font-semibold text-ink-900">Market salary suggestion</h3>
        </div>
        {loading ? (
          <p className="text-micro text-ink-500">Loading market data…</p>
        ) : !suggestedMin && !suggestedMax ? (
          <p className="text-micro text-ink-500">
            Not enough live job data yet for this title. Add comp manually or publish to gather
            signals.
          </p>
        ) : (
          <>
            <p className="text-small text-ink-800">
              Suggested band:{" "}
              <span className="font-semibold">
                {formatCompRange(suggestedMin ?? null, suggestedMax ?? null, {
                  market: marketByCode(market).code,
                })}
              </span>
              {corpus?.sample_size ? (
                <span className="text-micro text-ink-500"> ({corpus.sample_size} similar roles)</span>
              ) : null}
            </p>
            {competitive && competitive !== "competitive" && (
              <p className="text-micro text-warning">
                {competitive === "below_market"
                  ? "Your current band may be below market — consider raising comp."
                  : competitive === "missing_comp"
                    ? "No salary set — roles with comp get more applicants."
                    : "Your band is above typical market for this title."}
              </p>
            )}
            {onApply && suggestedMin && suggestedMax && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  onApply(
                    Math.round(suggestedMin / 100_000),
                    Math.round(suggestedMax / 100_000),
                  )
                }
              >
                Apply suggestion to brief
              </Button>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}
