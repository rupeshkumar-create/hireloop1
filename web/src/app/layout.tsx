import type { Metadata } from "next";
import { Navbar } from "@/components/layout/Navbar";
import { Footer } from "@/components/layout/Footer";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://hireloop.in"),
  title: {
    default: "Hireloop — AI Recruiting for India",
    template: "%s | Hireloop",
  },
  description:
    "Hireloop's AI agents Aarya and Nitya match top Indian talent with the right opportunities — and make the intro happen.",
  keywords: [
    "AI recruiting India",
    "job search India",
    "hiring AI",
    "Aarya AI",
    "Nitya AI",
    "hireloop",
  ],
  openGraph: {
    type: "website",
    locale: "en_IN",
    url: "https://hireloop.in",
    siteName: "Hireloop",
    title: "Hireloop — AI Recruiting for India",
    description:
      "Hireloop's AI agents Aarya and Nitya match top Indian talent with the right opportunities — and make the intro happen.",
    images: [{ url: "/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Hireloop — AI Recruiting for India",
    description: "AI agents that match talent to opportunities and make the intro happen.",
    images: ["/og-image.png"],
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN" suppressHydrationWarning>
      <body className="font-sans antialiased bg-paper-0 text-ink-900">
        <Navbar />
        <div className="pt-16">{children}</div>
        <Footer />
      </body>
    </html>
  );
}
