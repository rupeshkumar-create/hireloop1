/**
 * Unified candidate navigation — panel links for dashboard + mobile nav.
 */

import {
  Briefcase,
  GraduationCap,
  Home,
  Inbox,
  Kanban,
  Route,
  User,
  FileText,
  Settings,
  type LucideIcon,
} from "@/components/brand/icons";

export type CandidateNavId =
  | "home"
  | "matches"
  | "career_path"
  | "tracker"
  | "intros"
  | "profile"
  | "coaching"
  | "resumes"
  | "settings";

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
    id: "career_path",
    label: "Career path",
    href: "/dashboard?panel=career_path",
    panel: "career_path",
    Icon: Route,
  },
  {
    id: "tracker",
    label: "Job tracker",
    href: "/dashboard?panel=tracker",
    panel: "tracker",
    Icon: Kanban,
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

/** Mobile bottom bar — four primary tabs (More sheet for the rest). */
export const CANDIDATE_MOBILE_PRIMARY_NAV: CandidateNavItem[] = CANDIDATE_NAV.filter((n) =>
  ["home", "matches", "intros", "profile"].includes(n.id),
);

/** Items shown in the mobile More sheet. */
export const CANDIDATE_MOBILE_MORE_NAV: CandidateNavItem[] = [
  ...CANDIDATE_NAV.filter((n) => ["career_path", "tracker", "resumes"].includes(n.id)),
  {
    id: "settings",
    label: "Settings",
    href: "/dashboard?panel=settings",
    panel: "settings",
    Icon: Settings,
    match: ["/settings"],
  },
];

/** @deprecated Use CANDIDATE_MOBILE_PRIMARY_NAV + MORE */
export const CANDIDATE_MOBILE_NAV: CandidateNavItem[] = [
  ...CANDIDATE_MOBILE_PRIMARY_NAV,
  ...CANDIDATE_MOBILE_MORE_NAV,
];
