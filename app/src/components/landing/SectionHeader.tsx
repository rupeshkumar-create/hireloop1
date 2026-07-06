"use client";

import { Reveal } from "@/components/ui/motion";

type SectionHeaderProps = {
  label: string;
  title: string;
  description?: string;
  align?: "left" | "center";
};

export function SectionHeader({
  label,
  title,
  description,
  align = "left",
}: SectionHeaderProps) {
  const centered = align === "center";

  return (
    <Reveal className={centered ? "mx-auto max-w-2xl text-center" : "max-w-xl"}>
      <p className="text-micro font-semibold uppercase tracking-[0.14em] text-accent">
        {label}
      </p>
      <h2 className="mt-3 text-h1 text-ink-900 md:text-[32px] md:leading-tight">
        {title}
      </h2>
      {description ? (
        <p
          className={`mt-3 text-body leading-relaxed text-ink-600 ${
            centered ? "mx-auto max-w-lg" : ""
          }`}
        >
          {description}
        </p>
      ) : null}
    </Reveal>
  );
}
