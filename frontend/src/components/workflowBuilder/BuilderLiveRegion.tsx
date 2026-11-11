"use client";

/**
 * BuilderLiveRegion: the Builder panel's one polite live region (Req 14.2 to 14.5).
 *
 * It watches the panel state (the turn and the canvas draft revision), turns
 * each change into an announcement through `liveAnnouncer.ts`, and renders the
 * latest one. The announcements are stage labels, "Workflow updated on the
 * canvas", and the turn-end line. Streamed text never reaches this element.
 *
 * The text node is keyed by a sequence number. Without that, a repeated line
 * such as a second "Reply finished" leaves the DOM unchanged and is not spoken.
 */

import { useEffect, useRef, useState } from "react";

import type { TurnView } from "./builderReducer";
import {
  announcementsBetween,
  createLiveAnnouncer,
  type LiveSnapshot,
} from "./liveAnnouncer";

export interface BuilderLiveRegionProps {
  turn: TurnView;
  /** Revision number of the draft on the canvas; 0 when none. */
  draftRevision: number;
}

interface Announcement {
  text: string;
  seq: number;
}

export function BuilderLiveRegion({ turn, draftRevision }: BuilderLiveRegionProps) {
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);
  const [announcer] = useState(() =>
    createLiveAnnouncer((text) =>
      setAnnouncement((previous) => ({ text, seq: (previous?.seq ?? 0) + 1 })),
    ),
  );
  const previous = useRef<LiveSnapshot | null>(null);

  useEffect(() => {
    const prior = previous.current;
    const next: LiveSnapshot = { turn, draftRevision };
    previous.current = next;
    for (const item of announcementsBetween(prior, next)) {
      if (item.kind === "stage") {
        announcer.stage(item.label);
      } else if (item.kind === "draft") {
        announcer.draftApplied();
      } else {
        announcer.turnEnded(item.end);
      }
    }
  }, [announcer, turn, draftRevision]);

  useEffect(() => () => announcer.dispose(), [announcer]);

  return (
    <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
      {announcement !== null ? <span key={announcement.seq}>{announcement.text}</span> : null}
    </div>
  );
}

export default BuilderLiveRegion;
