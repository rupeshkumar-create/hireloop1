import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ToastProvider } from "@/components/ui";
import { CandidateGate } from "@/components/auth/CandidateGate";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { AppWarmup } from "@/components/providers/AppWarmup";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://app.hireloop.in"),
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
      <head />
      <body
        className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased min-h-screen bg-paper-0 text-ink-900`}
      >
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
