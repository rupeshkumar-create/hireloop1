/**
 * Unified candidate navigation — single source for AppShell + Dashboard pills.
 */

import {
  Briefcase,
  GraduationCap,
  Home,
  Inbox,
  User,
  FileText,
  type LucideIcon,
} from "lucide-react";

export type CandidateNavId = "home" | "matches" | "intros" | "profile" | "coaching" | "resumes";

export type CandidateNavItem = {
  id: CandidateNavId;
  label: string;
  href: string;
  panel?: string;
  Icon: LucideIcon;
  match?: string[];
};

/** Canonical candidate nav order (DESIGN.md §6 unified shell). */
export const CANDIDATE_NAV: CandidateNavItem[] = [
  { id: "home", label: "Home", href: "/dashboard", Icon: Home },
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
    href: "/intros",
    panel: "inbox",
    Icon: Inbox,
    match: ["/applications"],
  },
  {
    id: "profile",
    label: "Profile",
    href: "/profile",
    panel: "profile",
    Icon: User,
    match: ["/settings"],
  },
  {
    id: "coaching",
    label: "Coaching",
    href: "/mock-interview",
    panel: "coaching",
    Icon: GraduationCap,
  },
  {
    id: "resumes",
    label: "Resumes",
    href: "/resumes",
    Icon: FileText,
  },
];

/** Mobile bottom bar — chat-first, four primary destinations. */
export const CANDIDATE_MOBILE_NAV: CandidateNavItem[] = CANDIDATE_NAV.filter((n) =>
  ["home", "matches", "intros", "profile"].includes(n.id),
);
