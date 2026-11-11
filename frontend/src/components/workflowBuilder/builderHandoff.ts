/**
 * In-memory hand-offs that must outlive one `BuilderComposerHost` instance
 * (design 3.10.2, 3.10.6, 3.10.5).
 *
 * A real navigation (`router.push`) remounts the host, so three things that the
 * old instance knew have to reach the new one:
 *
 *   - the popup's first message, sent once when the new session's stream opens
 *     (Req 1.10), also when the popup was opened on `/workflows`;
 *   - the Model and Thinking choice, which "New conversation" keeps [pending G-26];
 *   - the "open the panel with no session yet" flag that "New conversation"
 *     leaves behind when it navigates to `/workflows/new` [pending G-26].
 *
 * Module state is safe here: it lives in one client bundle and one tab, the same
 * trade-off `shallowNavGuard.ts` makes. Nothing is persisted and nothing leaves
 * the tab.
 */

import type { PickerChoice } from "./modelPicker";

/** The first message of a session created from the popup. */
export interface PendingFirstMessage {
  text: string;
  modelId: string;
  effort: string | null;
}

const pendingFirstMessages = new Map<string, PendingFirstMessage>();
let rememberedChoice: PickerChoice | null = null;
let newConversationPending = false;

/** Keep the popup's text for `sessionId` until its stream opens. */
export function stashFirstMessage(sessionId: string, message: PendingFirstMessage): void {
  pendingFirstMessages.set(sessionId, message);
}

/** Take the stashed first message for `sessionId`: returns it once, then `null`. */
export function takeFirstMessage(sessionId: string): PendingFirstMessage | null {
  const message = pendingFirstMessages.get(sessionId) ?? null;
  pendingFirstMessages.delete(sessionId);
  return message;
}

/** Remember the picker choice so a remounted host starts from it. */
export function rememberPickerChoice(choice: PickerChoice | null): void {
  rememberedChoice = choice;
}

/** The last remembered picker choice, or `null`. */
export function recallPickerChoice(): PickerChoice | null {
  return rememberedChoice;
}

/** Ask the next host instance to open its panel with no session. */
export function markNewConversationPending(): void {
  newConversationPending = true;
}

/** True while a "New conversation" navigation is waiting for its host. Does not consume. */
export function isNewConversationPending(): boolean {
  return newConversationPending;
}

/** Clear the flag once the new host instance has read it. Safe to call twice. */
export function clearNewConversationPending(): void {
  newConversationPending = false;
}

/** Reset every hand-off. For tests. */
export function resetBuilderHandoff(): void {
  pendingFirstMessages.clear();
  rememberedChoice = null;
  newConversationPending = false;
}
