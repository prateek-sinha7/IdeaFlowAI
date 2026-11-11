/**
 * Class strings shared by the run chat (`MessageBubble`) and the AI Workflow
 * Builder transcript, so a user's message looks the same in both chats.
 * Token classes only (Req 14.6 of the builder spec).
 */

/** The user's message bubble: brand tint, squared bottom-right corner. */
export const USER_BUBBLE_CLASS =
  "rounded-[14px_14px_4px_14px] border border-brand-border bg-brand-fill px-[13px] py-[10px]";

/** The text inside the user's message bubble. */
export const USER_BUBBLE_TEXT_CLASS =
  "font-serif text-[13.5px] leading-[1.5] text-ink-800 whitespace-pre-wrap";
