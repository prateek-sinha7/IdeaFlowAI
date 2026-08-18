import type { Metadata } from "next";
import Script from "next/script";
import { Manrope, Heebo } from "next/font/google";
import "./globals.css";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import { RunConnectionProvider } from "@/providers/RunConnectionProvider";
import { StoreProvider } from "@/store/StoreProvider";
import { GlobalPreloadIndicator } from "@/store/GlobalPreloadIndicator";

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
    <html lang="en" className={`${manrope.variable} ${heebo.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full flex flex-col bg-surface-white text-ink-900">
        <Script id="theme-init" strategy="beforeInteractive">
          {`try{var t=localStorage.getItem('velocity-theme');if(t==='dark'){document.documentElement.setAttribute('data-theme','dark');}}catch(e){}`}
        </Script>
        <StoreProvider>
          <GlobalPreloadIndicator />
          <SkillsHooksProvider>
            {/*
              43-06 (A.2): mount the app-level SSE run connection ABOVE the router
              so per-run streams survive route changes (D-14a). SSE is the sole,
              unconditional run transport (44-06 hard cutoff) — the provider always
              attaches; there is no transport flag and no legacy WS path.
            */}
            <RunConnectionProvider>
              {children}
            </RunConnectionProvider>
          </SkillsHooksProvider>
        </StoreProvider>
      </body>
    </html>
  );
}
