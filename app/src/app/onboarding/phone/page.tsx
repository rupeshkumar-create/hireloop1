import { redirect } from "next/navigation";

export const metadata = {
  title: "Onboarding",
};

export default async function OnboardingPhonePage() {
  redirect("/onboarding");
}
