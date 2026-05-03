"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Palette, Check } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";

export function ThemePicker() {
  const { theme, setTheme, themes } = useTheme();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close popup when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2 py-1.5 text-[11px] font-medium text-grey hover:bg-white/10 hover:text-white transition-all duration-200"
        aria-label="Change theme"
      >
        <Palette className="h-3 w-3" />
        Theme
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.95 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-grey/20 backdrop-blur-md p-3 shadow-xl z-50"
            style={{ backgroundColor: 'var(--theme-input-bg)' }}
          >
            <p className="text-xs text-grey/70 mb-2.5 px-1">Choose a theme</p>
            <div className="grid grid-cols-2 gap-2">
              {themes.map((t) => {
                const isActive = t.id === theme.id;
                return (
                  <motion.button
                    key={t.id}
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => {
                      setTheme(t.id);
                      setOpen(false);
                    }}
                    className={`relative flex items-center gap-2 rounded-lg px-3 py-2.5 text-left text-xs font-medium transition-all duration-150 ${
                      isActive
                        ? "bg-white/15 text-white border border-white/20"
                        : "bg-white/5 text-grey hover:bg-white/10 hover:text-white border border-transparent"
                    }`}
                    aria-label={`Select ${t.name} theme`}
                  >
                    <span
                      className="h-4 w-4 rounded-full border border-white/20 flex-shrink-0"
                      style={{ backgroundColor: t.variables["--theme-bg"] }}
                    />
                    <span className="truncate">{t.icon} {t.name}</span>
                    {isActive && (
                      <Check className="h-3 w-3 text-white absolute top-1.5 right-1.5" />
                    )}
                  </motion.button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
