"use client";

import { Bookmark, Mail, Send } from "@/components/brand/icons";
import { Button } from "@/components/ui";

type JobActionRowProps = {
  onIntro?: () => void;
  onSave?: () => void;
  onApply?: () => void;
  saved?: boolean;
  introLoading?: boolean;
};

/** Three actions with distinct visual weight: Intro (accent) · Save (ghost) · Apply (secondary). */
export function JobActionRow({
  onIntro,
  onSave,
  onApply,
  saved = false,
  introLoading = false,
}: JobActionRowProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {onIntro && (
        <Button size="sm" onClick={onIntro} loading={introLoading} leftIcon={<Mail className="h-4 w-4" />}>
          Request intro
        </Button>
      )}
      {onSave && (
        <Button variant="ghost" size="sm" onClick={onSave} leftIcon={<Bookmark className="h-4 w-4" />}>
          {saved ? "Saved" : "Save"}
        </Button>
      )}
      {onApply && (
        <Button variant="secondary" size="sm" onClick={onApply} leftIcon={<Send className="h-4 w-4" />}>
          Log application
        </Button>
      )}
    </div>
  );
}
