"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";
import { ENV } from "@/lib/env";
import { useWebSocket } from "@/hooks/useWebSocket";
import { WorkflowView } from "@/components/workflow/WorkflowView";
import { AgentLibrary } from "@/components/workflow/AgentLibrary";
import { BookOpen } from "lucide-react";

/**
 * Standalone Workflow page — accessible via /workflow route.
 * Provides the full agent pipeline execution experience.
 */
export default function WorkflowPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);

  useEffect(() => {
    const storedToken = getToken();
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    setIsAuthenticated(true);
  }, [router]);

  const { send } = useWebSocket({
    url: ENV.WS_URL,
    token,
  });

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ backgroundColor: "var(--theme-bg)" }}>
        <div className="text-grey">Loading...</div>
      </div>
    );
  }

  return (
    <div className="flex h-screen" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Main workflow area */}
      <div className="flex-1 flex flex-col">
        {/* Top bar with library button */}
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: "var(--theme-border)" }}>
          <h1 className="text-sm font-semibold text-white">IdeaFlow AI — Agent Workflows</h1>
          <button
            onClick={() => setLibraryOpen(true)}
            className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-[11px] font-medium text-grey/70 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
          >
            <BookOpen className="h-3.5 w-3.5" />
            Agent Library
          </button>
        </div>

        {/* Workflow view */}
        <div className="flex-1 min-h-0">
          <WorkflowView
            pipelineType="user_stories"
            userMessage=""
            onClose={() => router.push("/dashboard")}
            websocketSend={send}
          />
        </div>
      </div>

      {/* Agent Library slide-out */}
      <AgentLibrary
        isOpen={libraryOpen}
        onClose={() => setLibraryOpen(false)}
      />
    </div>
  );
}
