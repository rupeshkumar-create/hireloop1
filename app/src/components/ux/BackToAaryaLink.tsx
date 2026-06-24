"use client";

import Link from "next/link";
import { MessageCircle } from "lucide-react";

export function BackToAaryaLink({
  context,
  href = "/dashboard",
}: {
  context?: string;
  href?: string;
}) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-2 text-small text-ink-500 hover:text-ink-900 transition-colors"
    >
      <MessageCircle className="h-4 w-4" strokeWidth={1.5} />
      <span>
        Back to Aarya
        {context ? (
          <>
            {" "}
            <span className="text-ink-400">· {context}</span>
          </>
        ) : null}
      </span>
    </Link>
  );
}
