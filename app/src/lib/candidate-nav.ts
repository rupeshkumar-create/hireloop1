/**
 * Unified candidate navigation — minimal shell: Chat · Matches · Intros · Profile.
 */

import {
  Briefcase,
  Inbox,
  MessageCircle,
  User,
  FileText,
  Settings,
  type LucideIcon,
} from "@/components/brand/icons";

export type CandidateNavId = "chat" | "matches" | "intros" | "profile" | "resumes" | "settings";

export type CandidateNavItem = {
  id: CandidateNavId;
  label: string;
  href: string;
  panel?: string;
  Icon: LucideIcon;
  match?: string[];
};

/** Primary dashboard destinations (desktop rail + mobile bottom bar). */
export const CANDIDATE_NAV: CandidateNavItem[] = [
  { id: "chat", label: "Chat", href: "/dashboard", Icon: MessageCircle },
  {
    id: "matches",
    label: "Matches",
    href: "/dashboard?panel=jobs",
    panel: "jobs",
    Icon: Briefcase,
    match: ["/matches", "/jobs"],
  },
  {
    id: "intros",
    label: "Intros",
    href: "/dashboard?panel=inbox",
    panel: "inbox",
    Icon: Inbox,
    match: ["/applications", "/intros"],
  },
  {
    id: "profile",
    label: "Profile",
    href: "/dashboard?panel=profile",
    panel: "profile",
    Icon: User,
  },
];

export const CANDIDATE_MOBILE_PRIMARY_NAV: CandidateNavItem[] = CANDIDATE_NAV;

/** Secondary links (mobile More sheet + profile shortcuts). */
export const CANDIDATE_MOBILE_MORE_NAV: CandidateNavItem[] = [
  {
    id: "resumes",
    label: "Resumes",
    href: "/resumes",
    Icon: FileText,
  },
  {
    id: "settings",
    label: "Settings",
    href: "/dashboard?panel=settings",
    panel: "settings",
    Icon: Settings,
    match: ["/settings"],
  },
];

/** @deprecated Use CANDIDATE_MOBILE_PRIMARY_NAV */
export const CANDIDATE_MOBILE_NAV: CandidateNavItem[] = [
  ...CANDIDATE_MOBILE_PRIMARY_NAV,
  ...CANDIDATE_MOBILE_MORE_NAV,
];
