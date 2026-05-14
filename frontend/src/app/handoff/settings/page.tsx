"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { getToken } from "@/lib/api";
import { IntegrationsCard } from "@/components/handoff/IntegrationsCard";

/**
 * Standalone settings page for /flowin-handoff integrations:
 * install command, GitHub PAT, and VelocityAI API keys.
 *
 * Lives at /handoff/settings (NOT under /settings) so the entire
 * handoff feature is one route family. The existing AccountSettings
 * panel inside the dashboard is untouched.
 */
export default function HandoffSettingsPage() {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const t = getToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    setAuthed(true);
  }, [router]);

  if (!authed) return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-5 py-3 flex items-center gap-3">
        <Link
          href="/dashboard"
          className="inline-flex items-center justify-center h-8 w-8 rounded-lg hover:bg-gray-100"
        >
          <ArrowLeft className="h-4 w-4 text-gray-500" />
        </Link>
        <div>
          <h1 className="text-[14px] font-semibold text-gray-900">
            Handoff integrations
          </h1>
          <p className="text-[10px] text-gray-500 mt-0.5">
            Install the slash command, save your GitHub PAT, manage VelocityAI API keys.
          </p>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-5 py-8">
        <IntegrationsCard />
      </main>
    </div>
  );
}
