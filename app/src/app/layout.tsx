import type { Metadata } from "next";
import { ToastProvider } from "@/components/ui";
import { CandidateGate } from "@/components/auth/CandidateGate";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { AppWarmup } from "@/components/providers/AppWarmup";
import "./globals.css";

const APP_ORIGIN =
  process.env.NEXT_PUBLIC_APP_URL ??
  (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3001");

export const metadata: Metadata = {
  metadataBase: new URL(APP_ORIGIN),
  title: {
    default: "Hireloop",
    template: "%s | Hireloop",
  },
  description: "Your AI career partner — Aarya is ready to help.",
  robots: {
    // App should not be indexed by search engines
    index: false,
    follow: false,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en-IN" suppressHydrationWarning>
      <body className="font-sans antialiased min-h-screen bg-paper-0 text-ink-900">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-ink-900 focus:px-4 focus:py-2 focus:text-paper-0"
        >
          Skip to content
        </a>
        <ToastProvider>
          <QueryProvider>
            <AppWarmup />
            <CandidateGate>{children}</CandidateGate>
          </QueryProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
