import { Metadata } from "next";
import { Suspense } from "react";
import { SignupForm } from "@/components/auth/SignupForm";

export const metadata: Metadata = {
  title: "Sign up",
};

export default function SignupPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-paper-0 px-4">
      <div className="max-w-md w-full bg-paper-1 rounded-xl shadow-2 border border-ink-100 p-8 space-y-6">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-ink-900 flex items-center justify-center">
            <span className="text-paper-0 text-h3 font-semibold">H</span>
          </div>
          <span className="text-h2 text-ink-900">Hireloop</span>
        </div>

        <div className="space-y-1">
          <h1 className="text-h1 text-ink-900">Get started</h1>
          <p className="text-small text-ink-500">
            India&apos;s AI recruiting platform — now in India, the US &amp; UK.
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
