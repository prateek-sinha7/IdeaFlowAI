"use client";

import { useParams } from "next/navigation";

import { HandoffWorkflow } from "@/components/handoff/HandoffWorkflow";

/**
 * Route entrypoint. Thin by design — all of the page's logic and visuals
 * live inside ``components/handoff/`` so the feature is one folder.
 */
export default function HandoffPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? "";
  if (!token) return null;
  return <HandoffWorkflow token={token} />;
}
