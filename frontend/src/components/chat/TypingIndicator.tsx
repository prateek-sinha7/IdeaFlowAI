"use client";

/**
 * Animated typing indicator displayed while AI is streaming a response.
 * Uses the typing-dot CSS classes defined in globals.css for the animation.
 */
export function TypingIndicator() {
  return (
    <div className="fade-in flex items-center justify-start mb-4">
      <div className="flex items-center gap-1 rounded-lg bg-navy px-4 py-3">
        <span className="typing-dot h-2 w-2 rounded-full bg-grey" />
        <span className="typing-dot h-2 w-2 rounded-full bg-grey" />
        <span className="typing-dot h-2 w-2 rounded-full bg-grey" />
      </div>
    </div>
  );
}
