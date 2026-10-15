"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";

/**
 * The in-app "Leave without saving?" dialog (ISS-917), on the shared Modal
 * primitive. Escape and a backdrop click are Stay. In-app only: S-19-17 bans a
 * native browser dialog.
 */
export function UnsavedChangesDialog({ onStay, onLeave }: { onStay: () => void; onLeave: () => void }) {
  return (
    <Modal
      onClose={onStay}
      title="Leave without saving?"
      description="You have unsaved changes. Leaving now will discard them."
      hideCloseButton
    >
      <div className="flex justify-end gap-3">
        <Button variant="secondary" onClick={onStay}>Stay</Button>
        <Button onClick={onLeave}>Leave anyway</Button>
      </div>
    </Modal>
  );
}
