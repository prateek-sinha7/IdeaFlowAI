/**
 * TodoCard — a TodoWrite-backed multi-step plan-progress card
 * (open-design borrow #7).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of upstream's `runtime/todos.ts` + `TodoCard`
 * (`ToolCard.tsx:214`) — the conversation-level plan-progress strip fed by the
 * generic TodoWrite tool. The lane projects a TodoWrite tool block's payload
 * into this flat `Todo[]`; the component is purely presentational.
 *
 * CURRENT SKIN (D-15): raw Tailwind + lucide-react. Rendered inert.
 */

"use client";

import { Circle, CircleCheck, CircleDot } from "lucide-react";

/** A single plan step. Status is a GENERIC lifecycle, never a workflow name. */
export interface Todo {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

const STATUS_ICON = {
  completed: { Icon: CircleCheck, tone: "text-green-400" },
  in_progress: { Icon: CircleDot, tone: "text-blue-400" },
  pending: { Icon: Circle, tone: "text-grey/40" },
} as const;

export function TodoCard({ todos }: { todos: Todo[] }) {
  const done = todos.filter((t) => t.status === "completed").length;

  return (
    <div
      data-testid="chat-todo-card"
      role="group"
      aria-label={`Plan progress: ${done} of ${todos.length} complete`}
      className="my-2 rounded-lg border border-grey/15 bg-navy/40 px-3 py-2"
    >
      <div className="mb-1.5 flex items-center gap-2 text-[12px] text-grey/70">
        <span className="font-medium text-white/90">Plan</span>
        <span className="ml-auto tabular-nums">
          {done}/{todos.length}
        </span>
      </div>
      <ul className="flex flex-col gap-1">
        {todos.map((todo, i) => {
          const { Icon, tone } = STATUS_ICON[todo.status];
          return (
            <li
              key={i}
              data-todo-status={todo.status}
              className="flex items-center gap-2 text-[13px] text-grey/80"
            >
              <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${tone}`} aria-hidden="true" />
              <span
                className={
                  todo.status === "completed"
                    ? "line-through text-grey/50"
                    : undefined
                }
              >
                {todo.content}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
