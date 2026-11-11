"use client";

/**
 * useBuilderSessionList: the user's builder conversations for the popup and the
 * panel menu (Req 12.1, 12.7 to 12.9; design 3.10.5).
 *
 * `refresh` loads the first page (newest activity first) and replaces the list.
 * `loadMore` appends the next page. `remove` deletes a session on the server and
 * drops it from the list. A failed call leaves the list as it was.
 */

import { useCallback, useRef, useState } from "react";

import { getToken } from "@/lib/api";
import { deleteSession, listSessions } from "@/lib/workflowBuilderApi";
import type { SessionSummary } from "@/types/workflowBuilder";

export interface UseBuilderSessionListResult {
  items: SessionSummary[];
  hasMore: boolean;
  refresh: () => Promise<void>;
  loadMore: () => Promise<void>;
  /** Delete on the server, then drop from the list. Rejects when the delete fails. */
  remove: (sessionId: string) => Promise<void>;
}

export function useBuilderSessionList(pageSize = 20): UseBuilderSessionListResult {
  const [items, setItems] = useState<SessionSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  // Guards against an older response replacing a newer one.
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const mine = ++generation.current;
    try {
      const page = await listSessions(token, { limit: pageSize });
      if (generation.current !== mine) return;
      setItems(page.items);
      setCursor(page.next_cursor);
    } catch {
      /* the list keeps what it had */
    }
  }, [pageSize]);

  const loadMore = useCallback(async () => {
    const token = getToken();
    if (!token || cursor === null) return;
    const mine = ++generation.current;
    try {
      const page = await listSessions(token, { cursor, limit: pageSize });
      if (generation.current !== mine) return;
      setItems((current) => {
        const known = new Set(current.map((s) => s.id));
        return [...current, ...page.items.filter((s) => !known.has(s.id))];
      });
      setCursor(page.next_cursor);
    } catch {
      /* the list keeps what it had */
    }
  }, [cursor, pageSize]);

  const remove = useCallback(async (sessionId: string) => {
    const token = getToken();
    if (!token) throw new Error("Not authenticated");
    await deleteSession(token, sessionId);
    setItems((current) => current.filter((s) => s.id !== sessionId));
  }, []);

  return { items, hasMore: cursor !== null, refresh, loadMore, remove };
}
