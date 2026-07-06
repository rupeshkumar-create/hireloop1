/** Landing page audience toggle — Aarya serves candidates, Nitya serves recruiters. */
export type LandingAudience = "candidate" | "recruiter";

export const LANDING_AGENTS = {
  candidate: {
    name: "Aarya",
    initial: "A",
    tagline: "AI recruiter for job seekers",
    chatTagline: "AI recruiting copilot",
  },
  recruiter: {
    name: "Nitya",
    initial: "N",
    tagline: "AI sourcer for hiring teams",
    chatTagline: "AI sourcing copilot",
  },
} as const;
