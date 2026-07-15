/**
 * Auth session + phone OTP helpers.
 */

import { apiAuthFetch } from "@/lib/api/auth-fetch";
import type { ActiveRole } from "@/lib/api/role";
import type { MarketCode } from "@/lib/markets";

export type AuthMe = {
  id: string;
  email: string;
  role: ActiveRole | "admin";
  phone_verified: boolean;
  full_name: string | null;
  has_candidate: boolean;
  has_recruiter: boolean;
  can_switch_roles: boolean;
};

export function canSwitchRoles(me: Pick<AuthMe, "has_candidate" | "has_recruiter">): boolean {
  return me.has_candidate && me.has_recruiter;
}

export async function fetchAuthMe(): Promise<AuthMe> {
  const res = await apiAuthFetch("/api/v1/auth/me");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `Auth me failed: ${res.status}`);
  }
  return res.json() as Promise<AuthMe>;
}

async function readDetail(res: Response, fallback: string): Promise<string> {
  const err = await res.json().catch(() => ({}));
  const detail = (err as { detail?: string }).detail;
  return detail?.trim() || fallback;
}

export type SavePhoneResult = {
  message: string;
  phone_verified: boolean;
};

export async function savePhone(input: {
  phone: string;
  market?: MarketCode;
}): Promise<SavePhoneResult> {
  const res = await apiAuthFetch("/api/v1/auth/save-phone", {
    method: "POST",
    body: JSON.stringify({
      phone: input.phone,
      market: input.market ?? "IN",
    }),
  });
  if (!res.ok) {
    throw new Error(await readDetail(res, `Save phone failed: ${res.status}`));
  }
  return res.json() as Promise<SavePhoneResult>;
}

export type SendPhoneOtpResult = {
  message: string;
  expires_in_seconds: number;
  resend_available_in_seconds: number;
  delivery_channel: string;
  /** Present only in local development when MSG91 is not configured. */
  dev_otp?: string | null;
};

export async function sendPhoneOtp(input: {
  phone: string;
  market?: MarketCode;
}): Promise<SendPhoneOtpResult> {
  const res = await apiAuthFetch("/api/v1/auth/send-otp", {
    method: "POST",
    body: JSON.stringify({
      phone: input.phone,
      market: input.market ?? "IN",
    }),
  });
  if (!res.ok) {
    throw new Error(await readDetail(res, `Send OTP failed: ${res.status}`));
  }
  return res.json() as Promise<SendPhoneOtpResult>;
}

export type VerifyPhoneOtpResult = {
  message: string;
  phone_verified: boolean;
};

export async function verifyPhoneOtp(input: {
  phone: string;
  otp: string;
  market?: MarketCode;
}): Promise<VerifyPhoneOtpResult> {
  const res = await apiAuthFetch("/api/v1/auth/verify-otp", {
    method: "POST",
    body: JSON.stringify({
      phone: input.phone,
      otp: input.otp,
      market: input.market ?? "IN",
    }),
  });
  if (!res.ok) {
    throw new Error(await readDetail(res, `Verify OTP failed: ${res.status}`));
  }
  return res.json() as Promise<VerifyPhoneOtpResult>;
}
