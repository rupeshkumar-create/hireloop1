"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, MoreHorizontal } from "@/components/brand/icons";
import {
  RECRUITER_MOBILE_MORE_NAV,
  RECRUITER_MOBILE_PRIMARY_NAV,
  type RecruiterNavItem,
} from "@/lib/recruiter-nav";
import { useDualRoleAccess } from "@/hooks/useDualRoleAccess";
import { switchActiveRole } from "@/lib/api/role";
import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui";
import { cn } from "@/lib/utils";

const tabClass = (active: boolean) =>
  cn(
    "relative flex flex-1 min-w-0 flex-col items-center justify-center gap-0.5 py-1 transition-colors duration-fast",
    active ? "text-ink-900" : "text-ink-500 hover:text-ink-900",
  );

function isItemActive(item: RecruiterNavItem, pathname: string | null) {
  if (!item.href) return false;
  const base = item.href.split("?")[0];
  if (pathname === base) return true;
  return item.match?.some((m) => pathname?.startsWith(m)) ?? false;
}

export function RecruiterMobileNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { toast } = useToast();
  const { canSwitch } = useDualRoleAccess();
  const [moreOpen, setMoreOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  const moreActive = RECRUITER_MOBILE_MORE_NAV.some((item) => isItemActive(item, pathname));

  const moreItems = RECRUITER_MOBILE_MORE_NAV.filter(
    (item) => item.action !== "switch-candidate" || canSwitch,
  );

  async function switchToCandidate() {
    if (switching) return;
    setSwitching(true);
    try {
      await switchActiveRole("candidate");
      router.push("/dashboard");
    } catch {
      toast.error("Couldn't switch roles — try again");
      setSwitching(false);
    }
  }

  return (
    <>
      <nav
        className="fixed inset-x-0 bottom-0 z-30 flex h-16 items-stretch border-t border-ink-100 bg-paper-1 md:hidden pb-[env(safe-area-inset-bottom)] px-1"
        aria-label="Recruiter navigation"
      >
        {RECRUITER_MOBILE_PRIMARY_NAV.map((item) => {
          const active = isItemActive(item, pathname);
          return (
            <Link
              key={item.id}
              href={item.href!}
              aria-current={active ? "page" : undefined}
              className={tabClass(active)}
            >
              {active && (
                <span className="absolute top-1 h-1 w-6 rounded-full bg-accent" aria-hidden />
              )}
              <item.Icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
              <span className="text-[10px] font-medium truncate max-w-full px-0.5 leading-tight">
                {item.label}
              </span>
            </Link>
          );
        })}

        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          aria-label="More navigation"
          aria-expanded={moreOpen}
          className={tabClass(moreActive)}
        >
          {moreActive && (
            <span className="absolute top-1 h-1 w-6 rounded-full bg-accent" aria-hidden />
          )}
          <MoreHorizontal className="h-5 w-5 shrink-0" strokeWidth={1.5} />
          <span className="text-[10px] font-medium">More</span>
        </button>
      </nav>

      <Modal open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <ul className="space-y-1 -mx-1">
          {moreItems.map((item) => {
            const active = isItemActive(item, pathname);

            if (item.action === "switch-candidate") {
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => {
                      setMoreOpen(false);
                      void switchToCandidate();
                    }}
                    className={cn(
                      "w-full flex items-center gap-3 rounded-lg px-3 py-3 text-left transition-colors",
                      "hover:bg-ink-50 text-ink-700 disabled:opacity-50",
                    )}
                  >
                    {switching ? (
                      <Loader2 className="h-5 w-5 shrink-0 animate-spin" strokeWidth={1.5} />
                    ) : (
                      <item.Icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
                    )}
                    <span className="text-body font-medium">{item.label}</span>
                  </button>
                </li>
              );
            }

            return (
              <li key={item.id}>
                <Link
                  href={item.href!}
                  onClick={() => setMoreOpen(false)}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-3 transition-colors",
                    active ? "bg-ink-50 text-ink-900" : "hover:bg-ink-50 text-ink-700",
                  )}
                >
                  <item.Icon className="h-5 w-5 shrink-0" strokeWidth={1.5} />
                  <span className="text-body font-medium">{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </Modal>
    </>
  );
}
