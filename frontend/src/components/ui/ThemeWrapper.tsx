"use client";

import { ThemeProvider } from "@/hooks/useTheme";

export function ThemeWrapper({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}
