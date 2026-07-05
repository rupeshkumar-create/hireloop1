"use client";

import Link from "next/link";
import { MessageCircle } from "@/components/brand/icons";
import { AppShell } from "@/components/layout/AppShell";
import { IntrosInboxPanel } from "@/components/intros/IntrosInboxPanel";
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
      <div className="h-[calc(100vh-8rem)] min-h-[480px] -mx-4 md:-mx-6 border border-ink-100 rounded-lg overflow-hidden bg-paper-0">
        <IntrosInboxPanel />
      </div>
    </AppShell>
  );
}
