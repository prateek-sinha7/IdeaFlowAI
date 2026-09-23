"use client";

import { useState, type InputHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";

/**
 * PasswordInput — a masked text input that owns its own show/hide state
 * (ISS-338, ISS-576, ISS-577).
 *
 * Every password field in the app renders through this primitive so the reveal
 * affordance is structural rather than opt-in per call site — the omission all
 * three cards were instances of. The toggle is the input's immediate next
 * sibling inside a `relative` wrapper, and the caller keeps ownership of
 * `id` / `value` / `onChange` / `placeholder` by spreading them onto the input.
 */
export type PasswordInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "type"
>;

export function PasswordInput({ className = "", ...rest }: PasswordInputProps) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input {...rest} type={show ? "text" : "password"} className={`${className} pr-10`} />
      <button
        type="button"
        onClick={() => setShow(!show)}
        aria-label={show ? "Hide password" : "Show password"}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700"
      >
        {show ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
