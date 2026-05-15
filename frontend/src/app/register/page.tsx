"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

// Self-registration is disabled. Users must contact an administrator to
// have an account created for them. We keep this route alive (rather than
// 404'ing) so any cached external link redirects cleanly to /login instead
// of failing.
export default function RegisterPage() {
  const router = useRouter();
  useEffect(() => { router.replace("/login"); }, [router]);
  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{ background: "#f5f5f0" }}
    >
      <p className="text-[13px] text-gray-500">Redirecting…</p>
    </div>
  );
}
