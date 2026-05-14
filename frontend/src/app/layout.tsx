import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

const inter = Inter({
  variable: "--font-inter",
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
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-white text-gray-900">
        <SkillsHooksProvider>
          {children}
        </SkillsHooksProvider>
      </body>
    </html>
  );
}
