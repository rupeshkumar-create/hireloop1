import { LandingPage } from "@/components/landing/LandingPage";

export const metadata = {
  title: "Hireschema Beta — AI recruiting for India",
  description:
    "Candidates use Aarya to find and understand relevant roles. Recruiters use Nitya to build consent-first shortlists. Now in beta in India.",
};

/** App landing page (hireschema.com) — static shell, animated client sections. */
export const dynamic = "force-static";

export default function RootPage() {
  return <LandingPage />;
}
