"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";
import { buildLoginRedirect } from "@/lib/authRedirect";
import { routes } from "@/lib/routes";
import { WorkflowView } from "@/components/workflow/WorkflowView";
import { AgentLibrary } from "@/components/workflow/AgentLibrary";
import { BookOpen } from "lucide-react";
import type { PipelineRunState } from "@/types/index";

// Default inert pipeline state — matches WorkflowView's own internal fallback
// so the initial render is stable and step stays at "build" until a real run
// starts (ISS-492: wiring the prop enables the step machine to transition).
const INITIAL_PIPELINE_STATE: PipelineRunState = {
  isRunning: false,
  pipeline_type: "",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
};

/**
 * Standalone Workflow page — accessible via /workflow route.
 * Provides the full agent pipeline execution experience.
 */
export default function WorkflowPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [libraryOpen, setLibraryOpen] = useState(false);
  // ISS-492: wire pipelineState and callbacks so WorkflowView's step machine
  // can transition out of "build" (running/complete steps were dead code when
  // these props were absent). onStartPipeline triggers the run; onResetPipeline
  // resets state for "Run Another"; onViewResults navigates to results.
  const [pipelineState, setPipelineState] = useState<PipelineRunState>(INITIAL_PIPELINE_STATE);

  useEffect(() => {
    const storedToken = getToken();
    if (!storedToken) {
      router.replace(buildLoginRedirect());
      return;
    }
    setIsAuthenticated(true);
  }, [router]);

  const handleStartPipeline = (type: string, message: string, _agentIds?: string[]) => {
    // Mark the pipeline as running so WorkflowView advances to "running" step.
    // A real integration would dispatch to the run API; this standalone page
    // marks running immediately and navigates to the full create flow which
    // owns the actual submission.
    setPipelineState(prev => ({
      ...prev,
      isRunning: true,
      pipeline_type: type,
    }));
    // Navigate to the create route with the user's message pre-filled
    router.push(`${routes.create()}?mode=prototype&message=${encodeURIComponent(message)}`);
  };

  const handleResetPipeline = () => {
    setPipelineState(INITIAL_PIPELINE_STATE);
  };

  const handleViewResults = (_pipelineType: string) => {
    router.push(routes.runHistory());
  };

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
          <h1 className="text-sm font-semibold text-white">VelocityAI — Agent Workflows</h1>
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
            onClose={() => router.push(routes.dashboard())}
            pipelineState={pipelineState}
            onStartPipeline={handleStartPipeline}
            onResetPipeline={handleResetPipeline}
            onViewResults={handleViewResults}
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
