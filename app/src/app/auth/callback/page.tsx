import { Suspense } from "react";
import { AuthCallbackClient } from "./AuthCallbackClient";

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-paper-0 px-6">
          <p className="text-body text-ink-900">Finishing LinkedIn sign-in…</p>
        </main>
      }
    >
      <AuthCallbackClient />
    </Suspense>
  );
}
