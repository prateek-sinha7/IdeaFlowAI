import type { Metadata } from "next";
import { Manrope, Heebo } from "next/font/google";
import "./globals.css";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import { RunConnectionProvider } from "@/providers/RunConnectionProvider";

// Structural/sans font (evidence 11 §B2) — bound to --font-sans in globals.css.
const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

// Reading font occupying the serif slot (evidence 11 §B2) — bound to
// --font-serif in globals.css. SF Mono (code) is a system stack in the
// --font-mono token; no google-font loader is needed for it.
const heebo = Heebo({
  variable: "--font-heebo",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "VelocityAI",
  description: "Enterprise-grade AI delivery platform — transform ideas into structured deliverables through specialist AI agents",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${manrope.variable} ${heebo.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-white text-gray-900">
        <SkillsHooksProvider>
          {/*
            43-06 (A.2): mount the app-level SSE run connection ABOVE the router
            so per-run streams survive route changes (D-14a). Self-gating per
            LOCK-B — `enabled` follows NEXT_PUBLIC_SSE_TRANSPORT; when the flag is
            OFF this is an inert pass-through and the legacy WS transport stays
            active (byte-identical). Flipping the flag ON is the supervised Part-C
            cutover — no other FE change needed (dashboard/page.tsx already selects
            subscribe/sendCommand on runConnection.enabled).
          */}
          <RunConnectionProvider>
            {children}
          </RunConnectionProvider>
        </SkillsHooksProvider>
      </body>
    </html>
  );
}
