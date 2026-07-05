"use client";

import { Building2 } from "@/components/brand/icons";
import { Card, CardBody } from "@/components/ui";

type WarmHandoffCardProps = {
  recruiterName?: string | null;
  companyName?: string | null;
  jobTitle?: string | null;
};

export function WarmHandoffCard({
  recruiterName,
  companyName,
  jobTitle,
}: WarmHandoffCardProps) {
  if (!recruiterName && !companyName) return null;
  return (
    <Card className="border-ink-100 bg-ink-50">
      <CardBody className="flex gap-3 items-start">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-ink-900">
          <Building2 className="h-5 w-5 text-paper-0" strokeWidth={1.5} />
        </div>
        <div>
          <p className="text-small font-medium text-ink-900">
            Intro to {recruiterName ?? "the hiring team"}
            {companyName ? ` at ${companyName}` : ""}
          </p>
          {jobTitle && <p className="text-micro text-ink-500 mt-0.5">{jobTitle}</p>}
          <p className="text-micro text-ink-400 mt-1">Usually responds within 48 hours</p>
        </div>
      </CardBody>
    </Card>
  );
}
