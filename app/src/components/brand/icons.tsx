import { forwardRef } from "react";
import type { LucideIcon, LucideProps } from "lucide-react";
import { HIRELOOP_ARROWS, HIRELOOP_ICONS } from "./hireloop-icons";

/**
 * Drop-in icon adapter — the custom Hireloop icon set exported under the exact
 * lucide names the app already uses. Swap `from "lucide-react"` →
 * `from "@/components/brand/icons"` and every mapped icon becomes the branded
 * line-icon (with its lime "live node"). Icons the custom set doesn't cover
 * fall back to lucide, so nothing ever renders blank.
 *
 * Sizing/props stay lucide-compatible (className h-/w-, strokeWidth, size).
 */
export type { LucideIcon } from "lucide-react";

const LIME = "#B9F84C";

function svgHtml(l: string, n?: string): string {
  return l + (n ? `<g fill="${LIME}" stroke="none">${n}</g>` : "");
}

function makeIcon(html: string): LucideIcon {
  const Icon = forwardRef<SVGSVGElement, LucideProps>(function HireIconAdapter(
    { className, strokeWidth = 1.75, size, color, ...rest },
    ref,
  ) {
    return (
      <svg
        ref={ref}
        width={size ?? 24}
        height={size ?? 24}
        viewBox="0 0 24 24"
        fill="none"
        stroke={color ?? "currentColor"}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        {...(rest as React.SVGProps<SVGSVGElement>)}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  });
  return Icon as unknown as LucideIcon;
}

const ico = (name: keyof typeof HIRELOOP_ICONS) =>
  makeIcon(svgHtml(HIRELOOP_ICONS[name].l, HIRELOOP_ICONS[name].n));
const arr = (name: keyof typeof HIRELOOP_ARROWS) => makeIcon(HIRELOOP_ARROWS[name]);

// ── Mapped to the custom icon set ──────────────────────────────────────────────
export const Activity = ico("pulse");
export const AlertCircle = ico("alert");
export const BarChart3 = ico("chart");
export const Bell = ico("bell");
export const BookOpen = ico("education");
export const Bookmark = ico("bookmark");
export const Brain = ico("brain");
export const Briefcase = ico("briefcase");
export const Building2 = ico("company");
export const Calendar = ico("calendar");
export const Check = ico("check");
export const CheckCircle = ico("check-circle");
export const Circle = ico("dot");
export const Clock = ico("clock");
export const Copy = ico("copy");
export const Download = ico("download");
export const ExternalLink = ico("external");
export const Eye = ico("view");
export const FileText = ico("file");
export const GraduationCap = ico("education");
export const Home = ico("home");
export const Inbox = ico("inbox");
export const IndianRupee = ico("rupee");
export const Info = ico("info");
export const Kanban = ico("board");
export const Linkedin = ico("linkedin");
export const Loader2 = ico("progress");
export const LogOut = ico("logout");
export const Mail = ico("mail");
export const MessageCircle = ico("chat");
export const MessageSquare = ico("message");
export const Mic = ico("mic");
export const MicOff = ico("mic-off");
export const MoreHorizontal = ico("more");
export const Paperclip = ico("attach");
export const PenLine = ico("edit");
export const PencilLine = ico("edit");
export const Phone = ico("phone");
export const Plus = ico("plus");
export const RefreshCw = ico("refresh");
export const Route = ico("pipeline");
export const Search = ico("search");
export const Send = ico("send");
export const Settings = ico("settings");
export const Shield = ico("shield");
export const ShieldAlert = ico("shield");
export const ShieldCheck = ico("shield");
export const SlidersHorizontal = ico("filter");
export const Sparkles = ico("spark");
export const Trash2 = ico("delete");
export const Upload = ico("upload");
export const User = ico("profile");
export const UserPlus = ico("candidate-add");
export const Users = ico("team");
export const X = ico("close");

// Arrows
export const ArrowLeft = arr("arrow-left");
export const ArrowRight = arr("arrow-right");
export const ArrowLeftRight = arr("swap");
export const ChevronDown = arr("chevron-down");
export const ChevronRight = arr("chevron-right");

// ── Fallback to lucide (no close custom equivalent) ────────────────────────────
export {
  ArrowUpRight,
  EyeOff,
  Heart,
  HelpCircle,
  MapPin,
  Pause,
  PhoneOff,
  Play,
  Square,
  Target,
  Volume2,
  XCircle,
  Zap,
} from "lucide-react";
