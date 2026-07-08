import type { EmailOtpType } from "@supabase/supabase-js";
import { redirect } from "next/navigation";
import { EmailConfirmClient } from "./EmailConfirmClient";

type PageProps = {
  searchParams: Promise<{
    token_hash?: string;
    type?: string;
    code?: string;
    signup_role?: string;
    role?: string;
  }>;
};

const OTP_TYPES = new Set<string>([
  "signup",
  "invite",
  "magiclink",
  "recovery",
  "email_change",
  "email",
]);

export default async function EmailConfirmPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const code = params.code?.trim();
  if (code) {
    // Preserve Job Seeker vs Recruiter when a code lands on /auth/confirm.
    const qs = new URLSearchParams();
    qs.set("code", code);
    const signupRole = params.signup_role?.trim() || params.role?.trim();
    if (signupRole === "recruiter" || signupRole === "candidate") {
      qs.set("signup_role", signupRole);
    }
    redirect(`/auth/callback?${qs.toString()}`);
  }

  const tokenHash = params.token_hash?.trim() ?? "";
  const rawType = params.type?.trim() ?? "email";
  const type: EmailOtpType = OTP_TYPES.has(rawType)
    ? (rawType as EmailOtpType)
    : "email";

  if (!tokenHash) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-paper-0 px-6">
        <div className="max-w-md space-y-3 text-center">
          <h1 className="text-h2 text-ink-900">Sign-in link incomplete</h1>
          <p className="text-small text-ink-600">
            Request a new link from the signup page, or enter the 6-digit code from your email
            there.
          </p>
          <a href="/signup" className="inline-block text-small font-medium text-accent hover:underline">
            Back to sign up
          </a>
        </div>
      </main>
    );
  }

  return <EmailConfirmClient tokenHash={tokenHash} type={type} />;
}
