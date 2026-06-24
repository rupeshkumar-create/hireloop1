import Link from "next/link";
import { ChevronRight } from "lucide-react";

type Crumb = { label: string; href?: string };

export function RecruiterBreadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1 text-micro text-ink-500 mb-4">
      {crumbs.map((c, i) => (
        <span key={`${c.label}-${i}`} className="inline-flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3 w-3 text-ink-300" strokeWidth={1.5} />}
          {c.href ? (
            <Link href={c.href} className="hover:text-ink-900 transition-colors">
              {c.label}
            </Link>
          ) : (
            <span className="text-ink-900 font-medium">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
