"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";

const NAV_LINKS = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/candidates", label: "For Candidates" },
  { href: "/recruiters", label: "For Recruiters" },
  { href: "/about", label: "About" },
  { href: "/blog", label: "Blog" },
];

const APP_URL = process.env.NEXT_PUBLIC_APP_URL ?? "https://hireschema.com";

export function Navbar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-paper-1/80 backdrop-blur-md border-b border-ink-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2 shrink-0" aria-label="Hireschema home">
            <div className="w-8 h-8 shrink-0">
              <svg viewBox="0 0 48 48" fill="none" className="h-8 w-8" aria-hidden>
                <rect width="48" height="48" fill="#B9F84C" />
                <g transform="translate(24 24) skewX(-10) translate(-24 -24)">
                  <rect x="10.5" y="9" width="7.5" height="12.5" fill="#141414" />
                  <rect x="10.5" y="26.5" width="7.5" height="12.5" fill="#141414" />
                  <rect x="30" y="9" width="7.5" height="12.5" fill="#141414" />
                  <rect x="30" y="26.5" width="7.5" height="12.5" fill="#141414" />
                  <rect x="10.5" y="20.5" width="27" height="7" fill="#141414" />
                </g>
              </svg>
            </div>
            <span className="text-h2 text-ink-900">
              Hire<span className="text-accent">schema</span>
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  pathname === link.href
                    ? "text-accent bg-ink-50"
                    : "text-ink-700 hover:text-ink-900 hover:bg-ink-50"
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          {/* CTAs */}
          <div className="hidden md:flex items-center gap-3">
            <Link
              href={APP_URL}
              className="text-sm font-medium text-ink-700 hover:text-ink-900 transition-colors"
            >
              Sign in
            </Link>
            <Link
              href={APP_URL + "/signup"}
              className="bg-accent hover:bg-accent-hover text-paper-0 text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
            >
              Start chatting — it&apos;s free
            </Link>
          </div>

          {/* Mobile hamburger */}
          <button
            type="button"
            className="md:hidden p-2 rounded-lg text-ink-700 hover:bg-ink-100 transition-colors"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle menu"
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav-menu"
          >
            {mobileOpen ? (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div id="mobile-nav-menu" className="md:hidden border-t border-ink-100 bg-paper-1 px-4 py-4 space-y-1">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              className={cn(
                "block px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                pathname === link.href
                  ? "text-accent bg-ink-50"
                  : "text-ink-700 hover:bg-ink-50"
              )}
            >
              {link.label}
            </Link>
          ))}
          <div className="pt-3 border-t border-ink-100 space-y-2">
            <Link
              href={APP_URL}
              className="block text-center px-3 py-2.5 rounded-lg text-sm font-medium text-ink-700 hover:bg-ink-50 transition-colors"
            >
              Sign in
            </Link>
            <Link
              href={APP_URL + "/signup"}
              className="block text-center bg-accent hover:bg-accent-hover text-paper-0 text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors"
            >
              Start chatting — it&apos;s free
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
