import Link from "next/link";

const FOOTER_LINKS = {
  Product: [
    { href: "/how-it-works", label: "How it works" },
    { href: "/candidates", label: "For Candidates" },
    { href: "/recruiters", label: "For Recruiters" },
    { href: "/pricing", label: "Pricing" },
  ],
  Company: [
    { href: "/about", label: "About" },
    { href: "/blog", label: "Blog" },
    { href: "/contact", label: "Contact" },
  ],
  Legal: [
    { href: "/privacy", label: "Privacy Policy" },
    { href: "/terms", label: "Terms of Service" },
  ],
};

export function Footer() {
  return (
    <footer className="bg-ink-900 text-ink-500">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8 lg:gap-12">
          {/* Brand column */}
          <div className="col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <svg viewBox="0 0 48 48" fill="none" className="h-8 w-8 shrink-0" aria-hidden>
                <rect width="48" height="48" fill="#B5FF6B" />
                <g transform="translate(24 24) skewX(-10) translate(-24 -24)">
                  <rect x="10.5" y="9" width="7.5" height="12.5" fill="#141414" />
                  <rect x="10.5" y="26.5" width="7.5" height="12.5" fill="#141414" />
                  <rect x="30" y="9" width="7.5" height="12.5" fill="#141414" />
                  <rect x="30" y="26.5" width="7.5" height="12.5" fill="#141414" />
                  <rect x="10.5" y="20.5" width="27" height="7" fill="#141414" />
                </g>
              </svg>
              <span className="font-bold text-xl text-paper-0">
                Hire<span className="text-accent">schema</span>
              </span>
            </div>
            <p className="text-sm text-ink-500 leading-relaxed max-w-xs">
              India&apos;s first AI recruiting platform. Aarya finds you the right job.
              Nitya finds companies the right talent. Built for Bharat.
            </p>
            <div className="mt-6 space-y-1">
              <p className="text-xs text-ink-700">🇮🇳 India-only platform (+91)</p>
              <p className="text-xs text-ink-700">DPDP Act 2023 compliant</p>
              <p className="text-xs text-ink-700">AWS ap-south-1 (Mumbai)</p>
            </div>
          </div>

          {/* Link columns */}
          {Object.entries(FOOTER_LINKS).map(([section, links]) => (
            <div key={section}>
              <h3 className="text-paper-0 font-semibold text-sm mb-4">{section}</h3>
              <ul className="space-y-3">
                {links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-ink-500 hover:text-ink-300 transition-colors"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 pt-8 border-t border-ink-700 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-ink-700">
            &copy; {new Date().getFullYear()} Hireschema All rights reserved.
          </p>
          <div className="flex items-center gap-4 text-xs text-ink-700">
            <a
              href="mailto:privacy@hireschema.com"
              className="hover:text-ink-500 transition-colors"
            >
              DPO: privacy@hireschema.com
            </a>
            <span>·</span>
            <a
              href="mailto:hello@hireschema.com"
              className="hover:text-ink-500 transition-colors"
            >
              hello@hireschema.com
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
