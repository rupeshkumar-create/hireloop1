"use client";

import { Search } from "@/components/brand/icons";
import { Button } from "@/components/ui";

export function MatchesEmptyPanel({
  onAskAarya,
  isSearching = false,
}: {
  onAskAarya?: () => void;
  isSearching?: boolean;
}) {
  return (
    <div className="flex flex-col items-center py-10 px-4 text-center gap-4">
      <p className="text-small text-ink-600 max-w-sm">
        {isSearching
          ? "Finding roles that fit your profile…"
          : "No strong matches yet. Ask Aarya to search for you."}
      </p>
      {onAskAarya && (
        <Button
          variant="primary"
          size="sm"
          onClick={onAskAarya}
          leftIcon={<Search className="h-3.5 w-3.5" strokeWidth={1.5} />}
        >
          Ask Aarya to find roles
        </Button>
      )}
    </div>
  );
}
