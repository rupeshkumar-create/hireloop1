"use client";

import { Briefcase, Search } from "@/components/brand/icons";
import { AaryaBubble } from "@/components/aarya/AaryaBubble";
import { AaryaFace } from "@/components/aarya/AaryaFace";
import { Button } from "@/components/ui";

export function MatchesEmptyPanel({
  onAskAarya,
  isSearching = false,
}: {
  onAskAarya?: () => void;
  isSearching?: boolean;
}) {
  return (
    <div className="flex flex-col items-center py-10 px-4 text-center">
      <div className="flex items-start gap-3 max-w-sm w-full mb-6 text-left">
        <AaryaFace size="md" />
        <AaryaBubble className="flex-1 min-w-0">
          <p className="text-small text-ink-800 leading-relaxed">
            I&apos;m checking fresh roles against your CV and only keeping the ones that look
            genuinely relevant. Strong matches will appear here as soon as they clear the ranking.
          </p>
        </AaryaBubble>
      </div>

      <div className="w-full max-w-xs rounded-xl border border-dashed border-ink-200 bg-ink-50/80 p-6 space-y-3">
        <div className="mx-auto w-12 h-12 rounded-full bg-paper-1 border border-ink-100 flex items-center justify-center text-ink-400">
          {isSearching ? (
            <Search className="h-5 w-5 animate-pulse" strokeWidth={1.5} />
          ) : (
            <Briefcase className="h-5 w-5" strokeWidth={1.5} />
          )}
        </div>
        <p className="text-small font-medium text-ink-700">
          {isSearching ? "Finding relevant starter matches" : "No strong matches yet"}
        </p>
        <p className="text-micro text-ink-500">
          {isSearching
            ? "Aarya is still narrowing the feed for your market."
            : "Aarya filtered out broad roles that did not fit your profile."}
        </p>
      </div>

      {onAskAarya && (
        <Button
          variant="primary"
          size="sm"
          className="mt-6"
          onClick={onAskAarya}
          leftIcon={<Search className="h-3.5 w-3.5" strokeWidth={1.5} />}
        >
          Ask Aarya to find roles
        </Button>
      )}
    </div>
  );
}
