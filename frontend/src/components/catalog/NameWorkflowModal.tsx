"use client";

/**
 * NameWorkflowModal — a hand-rolled name + description modal used by BOTH the
 * composer "Save workflow" entry point and the catalog per-row "Rename" action
 * (Phase 21, SAVE-FROM-BOTH).
 *
 * REUSE-MANDATE (UI-SPEC §1/§4 — NO new visual language): this is a CLONE of
 * `DeleteModal` (`WorkflowHistory.tsx:923-969`) — the backdrop + scale-in
 * `motion.div` + header + two-button footer (Cancel + gray-900 Save pill) — with
 * the name `<input>` + description `<textarea>` styling lifted verbatim from
 * `AgentsPopup.tsx:374-393`. The ONLY changes vs the DeleteModal analog: copy
 * text, the two inputs, Save disabled on an empty name, and a bumped z-index
 * (`z-50 → z-[80]`) so it opens ABOVE the AgentsPopup.
 */

import { useState } from "react";
import { motion } from "motion/react";
import { Save } from "lucide-react";

interface NameWorkflowModalProps {
  initialName?: string;
  initialDescription?: string;
  /** Title copy — "Save workflow" (default) or "Rename workflow". */
  title?: string;
  onSave: (name: string, description: string) => void;
  onCancel: () => void;
}

export function NameWorkflowModal({
  initialName = "",
  initialDescription = "",
  title = "Save workflow",
  onSave,
  onCancel,
}: NameWorkflowModalProps) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const canSave = name.trim().length > 0;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/20 backdrop-blur-sm"
      onClick={onCancel}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.15 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl border border-gray-200 shadow-2xl p-6 max-w-[340px] w-full mx-4"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
            <Save className="h-5 w-5 text-gray-600" />
          </div>
          <div>
            <h3 className="text-[13px] font-semibold text-gray-900">{title}</h3>
            <p className="text-[11px] text-gray-400">Name it to find it later</p>
          </div>
        </div>

        {/* Workflow name — input analog AgentsPopup.tsx:374-381 */}
        <div className="mb-3">
          <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide block mb-1">
            Workflow name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Competitive research"
            autoFocus
            className="w-full px-3 py-2 text-[12px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400 transition-colors"
          />
        </div>

        {/* Description — textarea analog AgentsPopup.tsx:387-393 */}
        <div className="mb-5">
          <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide block mb-1">
            Description <span className="text-gray-400 normal-case font-normal">(optional)</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="What does this workflow produce?"
            className="w-full px-3 py-2 text-[11px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400 resize-none transition-colors"
          />
        </div>

        {/* Footer — two-button shell, DeleteModal.tsx:952-965 */}
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => canSave && onSave(name.trim(), description.trim())}
            disabled={!canSave}
            className="flex-1 rounded-xl bg-gray-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-gray-800 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Save
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
