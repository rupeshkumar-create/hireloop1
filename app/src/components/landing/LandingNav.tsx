"use client";

import Link from "next/link";
import { motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useState } from "react";
import { ArrowRight } from "@/components/brand/icons";
import { BTN_PRIMARY, BTN_GHOST } from "@/lib/button-classes";
import { HireschemaLogo } from "@/components/brand/HireschemaLogo";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

export function LandingNav() {
  const [signedIn, setSignedIn] = useState(false);
  const { scrollY } = useScroll();
  const navBg = useTransform(
    scrollY,
    [0, 48],
    ["rgba(20,20,20,0.72)", "rgba(20,20,20,0.95)"],
  );
  const navBorder = useTransform(
    scrollY,
    [0, 48],
    ["rgba(42,42,42,0.4)", "rgba(42,42,42,1)"],
  );

  useEffect(() => {
    const supabase = createClient();
    void supabase.auth.getSession().then(({ data: { session } }) => {
      setSignedIn(Boolean(session));
    });
  }, []);

  const primaryHref = signedIn ? "/dashboard" : "/signup";
  const primaryLabel = signedIn ? "Dashboard" : "Join beta";

  const links = [
    { href: "#process", label: "Process" },
    { href: "#features", label: "Features" },
    { href: "#trust", label: "Trust" },
  ] as const;

  return (
    <motion.header
      style={{ backgroundColor: navBg, borderBottomColor: navBorder }}
      className="sticky top-0 z-30 border-b backdrop-blur-md"
    >
      <div className="mx-auto flex h-14 max-w-page items-center justify-between px-6">
        <Link
          href="/"
          className="flex items-center gap-2"
          aria-label="Hireschema home"
        >
          <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.98 }}>
            <HireschemaLogo size={30} />
          </motion.div>
          <span className="rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-accent">
            Beta
          </span>
        </Link>

        <nav className="hidden items-center gap-6 md:flex">
          {links.map(({ href, label }) => (
            <a
              key={href}
              href={href}
              className="text-small text-ink-500 transition-colors hover:text-ink-900"
            >
              {label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {!signedIn ? (
            <Link
              href="/login"
              className={cn(BTN_GHOST, "px-3 py-2 text-small")}
            >
              Log in
            </Link>
          ) : null}
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Link
              href={primaryHref}
              className={cn(BTN_PRIMARY, "group gap-1.5 px-4 py-2 text-small")}
            >
              {primaryLabel}
              <ArrowRight
                className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
                strokeWidth={1.5}
              />
            </Link>
          </motion.div>
        </div>
      </div>
    </motion.header>
  );
}
