/**
 * Unified recruiter navigation — desktop sidebar + mobile bottom bar.
 */

import {
  ArrowLeftRight,
  Briefcase,
  Home,
  Inbox,
  Plus,
  Settings,
  Users,
  type LucideIcon,
} from "@/components/brand/icons";

export type RecruiterNavId =
  | "dashboard"
  | "inbox"
  | "candidates"
  | "roles"
  | "new"
  | "settings"
  | "switch";

export type RecruiterNavItem = {
  id: RecruiterNavId;
  label: string;
  href?: string;
  Icon: LucideIcon;
  match?: string[];
  action?: "switch-candidate";
};

export const RECRUITER_NAV: RecruiterNavItem[] = [
  { id: "dashboard", label: "Dashboard", href: "/recruiter", Icon: Home },
  { id: "inbox", label: "Inbox", href: "/recruiter/inbox", Icon: Inbox },
  {
    id: "candidates",
    label: "Talent",
    href: "/recruiter/candidates",
    Icon: Users,
    match: ["/recruiter/candidates"],
  },
  {
    id: "roles",
    label: "Roles",
    href: "/recruiter/roles",
    Icon: Briefcase,
    match: ["/recruiter/roles"],
  },
];

export const RECRUITER_MOBILE_PRIMARY_NAV: RecruiterNavItem[] = RECRUITER_NAV;

export const RECRUITER_MOBILE_MORE_NAV: RecruiterNavItem[] = [
  { id: "new", label: "New role", href: "/recruiter/roles/new", Icon: Plus },
  {
    id: "settings",
    label: "Settings",
    href: "/recruiter/settings",
    Icon: Settings,
    match: ["/recruiter/settings"],
  },
  {
    id: "switch",
    label: "Candidate view",
    Icon: ArrowLeftRight,
    action: "switch-candidate",
  },
];
