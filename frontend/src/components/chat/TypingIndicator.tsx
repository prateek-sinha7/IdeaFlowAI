"use client";

import { motion } from "motion/react";
import { Sparkles } from "lucide-react";

/**
 * Elegant typing indicator with shimmer wave animation.
 * Shows "IdeaFlow AI is generating..." with a subtle gradient background.
 */
export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex items-start gap-4 mb-8"
    >
      {/* Bot avatar with glow */}
      <div className="flex-shrink-0 pt-1">
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-navy/60 border border-grey/15 avatar-streaming">
          <Sparkles className="h-3.5 w-3.5 text-white/80" />
        </div>
      </div>

      {/* Shimmer indicator */}
      <div className="flex items-center gap-3 py-2">
        {/* Animated shimmer bar */}
        <div className="flex items-center gap-2">
          <div className="flex gap-[3px]">
            {[0, 1, 2, 3].map((i) => (
              <motion.div
                key={i}
                className="h-[3px] w-4 rounded-full bg-grey/40"
                animate={{
                  opacity: [0.3, 0.8, 0.3],
                  scaleX: [0.8, 1.2, 0.8],
                }}
                transition={{
                  duration: 1.5,
                  repeat: Infinity,
                  delay: i * 0.15,
                  ease: "easeInOut",
                }}
              />
            ))}
          </div>
          <span className="text-[13px] text-grey/50 font-light">
            IdeaFlow AI is generating...
          </span>
        </div>
      </div>
    </motion.div>
  );
}
