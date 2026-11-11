/**
 * AssistantMark: the 22 px near-black square with a rotated brand diamond that
 * sits beside every assistant reply (Phase 39, RUNUI-06). The run chat and the
 * AI Workflow Builder both render it, so the two chats carry the same mark.
 *
 * Decorative: screen readers get the reply's own label instead.
 */
export function AssistantMark() {
  return (
    <div
      aria-hidden="true"
      className="grid h-[22px] w-[22px] place-items-center rounded-[6px] bg-surface-near-black"
    >
      <span className="h-[7px] w-[7px] rotate-45 rounded-[1px] bg-brand" />
    </div>
  );
}

export default AssistantMark;
