"use client";

import Link from "next/link";
import { MessageCircle } from "@/components/brand/icons";
import { AppShell } from "@/components/layout/AppShell";
import { IntrosList } from "@/components/intros/IntrosList";
import { BackToAaryaLink, ScoringExplainerLink } from "@/components/ux";
import { Button } from "@/components/ui";

export default function IntrosPage() {
  return (
    <AppShell
      title="Intro requests"
      backContext="Continue in chat"
      action={
        <Link href="/dashboard?panel=inbox">
          <Button
            variant="primary"
            size="sm"
            leftIcon={<MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />}
          >
            Ask for intro
          </Button>
        </Link>
      }
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <BackToAaryaLink />
          <ScoringExplainerLink />
        </div>
        <IntrosList variant="page" />
      </div>
    </AppShell>
  );
}
