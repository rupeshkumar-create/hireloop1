"use client";

const TOOL_LABELS: Record<string, string> = {
  profile_read: "Reading your profile",
  job_search: "Searching India roles",
  get_match_score: "Scoring this role",
  match_score: "Scoring this role",
  request_intro: "Preparing your intro",
  build_career_path: "Mapping your career path",
  save_job: "Saving this role",
  update_profile: "Updating your profile",
};

export function ActivityStatusLine({ toolName }: { toolName?: string }) {
  const label = toolName
    ? TOOL_LABELS[toolName] ?? "Working on your request"
    : "Thinking";
  return (
    <p className="text-micro text-ink-500 animate-pulse" aria-live="polite">
      {label}…
    </p>
  );
}
