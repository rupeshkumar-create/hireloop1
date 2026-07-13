import { Metadata } from "next";
import { Suspense } from "react";
import { SignupForm } from "@/components/auth/SignupForm";
import { HireschemaLogo } from "@/components/brand/HireschemaLogo";

// Auth page — skip static prerender so builds succeed without Supabase env at compile time.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Sign up",
};

export default function SignupPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-paper-0 px-4">
      <div className="max-w-md w-full bg-paper-1 rounded-xl shadow-2 border border-ink-100 p-8 space-y-6">
        {/* Logo */}
        <HireschemaLogo size={34} />

        <div className="space-y-1">
          <h1 className="text-h1 text-ink-900">Get started</h1>
          <p className="text-small text-ink-500">
            India&apos;s AI recruiting platform for candidates and hiring teams.
          </p>
        </div>

        <Suspense fallback={<SignupFormSkeleton />}>
          <SignupForm />
        </Suspense>
      </div>
    </main>
  );
}

function SignupFormSkeleton() {
  return (
    <div className="space-y-6" aria-hidden="true">
      <div className="space-y-2">
        <div className="h-4 w-20 rounded bg-ink-100 animate-skeleton" />
        <div className="grid grid-cols-2 gap-3">
          <div className="h-12 rounded-lg bg-ink-100 animate-skeleton" />
          <div className="h-12 rounded-lg bg-ink-100 animate-skeleton" />
        </div>
      </div>
      <div className="h-12 rounded-lg bg-ink-100 animate-skeleton" />
      <div className="h-4 w-3/4 mx-auto rounded bg-ink-100 animate-skeleton" />
    </div>
  );
}
