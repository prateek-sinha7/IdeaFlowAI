"use client";

/**
 * useBuilderSessionList: the builder conversations for the panel menu
 * (Req 12.1, 12.7 to 12.9; design 3.10.5), scoped to the workflow on the canvas.
 *
 * `workflowId` is the saved workflow being edited. With an id, only the
 * conversations linked to that workflow are listed. With `null` (a new,
 * unsaved workflow) the list is always empty and nothing is fetched.
 *
 * `refresh` loads the first page (newest activity first) and replaces the list.
 * `loadMore` appends the next page. `remove` deletes a session on the server and
 * drops it from the list. A failed call leaves the list as it was. When
 * `workflowId` changes, the previous workflow's items are no longer returned.
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

interface ScopedList {
  /** The workflow these items were loaded for. */
  workflowId: string | null;
  items: SessionSummary[];
  cursor: string | null;
}

const NO_ITEMS: SessionSummary[] = [];

export function useBuilderSessionList(
  workflowId: string | null,
  pageSize = 20,
): UseBuilderSessionListResult {
  const [list, setList] = useState<ScopedList>({ workflowId, items: [], cursor: null });
  // Guards against an older response replacing a newer one.
  const generation = useRef(0);

  // Items loaded for another workflow are never shown for this one.
  const inScope = workflowId !== null && list.workflowId === workflowId;
  const items = inScope ? list.items : NO_ITEMS;
  const cursor = inScope ? list.cursor : null;

  const refresh = useCallback(async () => {
    const mine = ++generation.current;
    if (workflowId === null) return;
    const token = getToken();
    if (!token) return;
    try {
      const page = await listSessions(token, { limit: pageSize, workflowId });
      if (generation.current !== mine) return;
      setList({ workflowId, items: page.items, cursor: page.next_cursor });
    } catch {
      /* the list keeps what it had */
    }
  }, [workflowId, pageSize]);

  const loadMore = useCallback(async () => {
    const token = getToken();
    if (!token || workflowId === null || cursor === null) return;
    const mine = ++generation.current;
    try {
      const page = await listSessions(token, { cursor, limit: pageSize, workflowId });
      if (generation.current !== mine) return;
      setList((current) => {
        if (current.workflowId !== workflowId) return current;
        const known = new Set(current.items.map((s) => s.id));
        return {
          workflowId,
          items: [...current.items, ...page.items.filter((s) => !known.has(s.id))],
          cursor: page.next_cursor,
        };
      });
    } catch {
      /* the list keeps what it had */
    }
  }, [workflowId, cursor, pageSize]);

  const remove = useCallback(async (sessionId: string) => {
    const token = getToken();
    if (!token) throw new Error("Not authenticated");
    await deleteSession(token, sessionId);
    setList((current) => ({
      ...current,
      items: current.items.filter((s) => s.id !== sessionId),
    }));
  }, []);

  return { items, hasMore: cursor !== null, refresh, loadMore, remove };
}
