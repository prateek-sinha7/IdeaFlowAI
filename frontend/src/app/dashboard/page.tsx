"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, getChat, addMessage, logout, deleteChat, createChat, getWorkflows, getWorkflow, getMe } from "@/lib/api";
import { ENV } from "@/lib/env";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useWorkflow } from "@/hooks/useWorkflow";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import type { ChatMessage, ChatSession, StreamMessage, ProcessStep, WorkflowRun, User, WaveGroup } from "@/types/index";
import type { ChatMode } from "@/components/chat/ChatInput";

/**
 * Dashboard page - the main authenticated view.
 * Manages WebSocket connection, workflow runs, and streaming content.
 * Workflow-first: the primary experience is running agent pipelines.
 */
export default function DashboardPage() {
  const router = useRouter();
  // Keep initial state false/null to match SSR — avoids hydration mismatch.
  // `mounted` flips to true after the first client render so we never show
  // the black loading screen; instead we show nothing until hydration is done.
  const [mounted, setMounted] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  // Run synchronously after DOM paint but before the browser repaints —
  // this is the earliest safe point to read localStorage on the client.
  useEffect(() => {
    setMounted(true);
  }, []);

  // Chat state (secondary — used for refinement)
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");

  // Preview content per section
  const [userStoryContent, setUserStoryContent] = useState<string>("");
  const [pptContent, setPptContent] = useState<string>("");
  const [prototypeContent, setPrototypeContent] = useState<string>("");
  const [currentMode, setCurrentMode] = useState<ChatMode>("default");
  const [chatTitleUpdate, setChatTitleUpdate] = useState<{ chat_session_id: string; title: string } | null>(null);
  const [processSteps, setProcessSteps] = useState<ProcessStep[]>([]);
  const processStepsRef = useRef<ProcessStep[]>([]);
  const activePreviewSectionRef = useRef<string | null>(null);
  const pptContentRef = useRef("");
  const prototypeContentRef = useRef("");
  const userStoryContentRef = useRef("");
  const handlePipelineMsgRef = useRef<((msg: { type: string; [key: string]: unknown }) => boolean) | null>(null);
  // Staged od_prototype run — written when authenticated, consumed when connected.
  // `gateAgentIds` (Phase 6, T5b) is present ONLY when the templates wizard's
  // Review-gates section was touched; absent ⇒ backend static gate default.
  const pendingOdProtoRef = useRef<{
    templateId: string; designSystemId: string; brief: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
  } | null>(null);

  // Staged od_ppt run — written when authenticated, consumed when connected.
  const pendingOdPptRef = useRef<{
    templateId: string; designSystemId: string | null; brief: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
  } | null>(null);

  // Phase 12 (§22 / RESUME-03) — wave/subagent tree state assembled from the
  // additive wave_*/subagent_* lifecycle events, fed to the WaveTreePanel.
  const [waveGroups, setWaveGroups] = useState<WaveGroup[]>([]);
  // Per-run dedup substrate for the durable reconnect replay (RESUME-03 FE half):
  // every applied event_id is recorded so a replayed event is applied at most
  // once, and the max-seen seq is tracked so the reconnect can send after_seq.
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const lastSeqRef = useRef<number>(0);
  // Stable getter so DashboardLayout's reconnect effect reads the current
  // last-received seq without re-subscribing.
  const getLastSeq = useCallback(() => lastSeqRef.current, []);

  // Workflow runs state (primary)
  const [recentRuns, setRecentRuns] = useState<WorkflowRun[]>([]);
  const [questionnaireData, setQuestionnaireData] = useState<{ questions: { id: string; question: string; options: string[]; answerType?: string }[] } | null>(null);
  // Phase 2 — pipeline_run_id of the run currently paused at the clarify gate,
  // used to address submit_questionnaire back to the correct paused run.
  const [activePipelineRunId, setActivePipelineRunId] = useState<string | null>(null);
  // Review gate state — set when review_gate_ready fires
  const [reviewGateData, setReviewGateData] = useState<{
    gateKey: string;
    agentId: string;
    agentName: string;
    output: string;
    pipelineRunId: string;
  } | null>(null);
  // Pending od_prototype params — set when questionnaire is triggered, consumed by DashboardLayout.
  // `gateAgentIds` (Phase 6, T5b) flows into DashboardLayout's `gate_agent_ids`
  // extraParam; it is set ONLY when the wizard's Review-gates section was touched.
  const [pendingOdProtoParams, setPendingOdProtoParams] = useState<{
    brief: string; templateId: string; designSystemId: string; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
  } | null>(null);
  // Pending od_ppt params
  const [pendingOdPptParams, setPendingOdPptParams] = useState<{
    brief: string; templateId: string; designSystemId: string | null; discovery: unknown;
    customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
  } | null>(null);

  // Auth check on mount — redirect if no token, otherwise fetch user profile.
  useEffect(() => {
    const storedToken = getToken();
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    setIsAuthenticated(true);
    // Fetch user profile (includes tier)
    getMe(storedToken)
      .then((u) => setUser(u))
      .catch(() => {
        // Non-fatal — tier defaults to "basic" if fetch fails
      });
  }, [router]);

  // Stage an od_prototype run into a ref as soon as we're authenticated.
  // NOTE: We do NOT remove od_prototype.pending here — we remove it only
  // when the WebSocket connects and we actually fire the questionnaire.
  useEffect(() => {
    if (!isAuthenticated) return;
    const pending = sessionStorage.getItem("od_prototype.pending");
    if (!pending) return;
    try {
      const draft = JSON.parse(sessionStorage.getItem("prototype.draft") ?? "{}") as {
        templateId?: string; designSystemId?: string; brief?: string; customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
      };
      const discovery = JSON.parse(sessionStorage.getItem("prototype.discovery") ?? "null");
      if (!draft.templateId || !draft.designSystemId || !draft.brief) return;
      pendingOdProtoRef.current = {
        templateId: draft.templateId,
        designSystemId: draft.designSystemId,
        brief: draft.brief,
        discovery,
        customDsBody: draft.customDsBody,
        customTemplateBody: draft.customTemplateBody,
        sourceRunId: draft.sourceRunId,
        // Present only when the wizard's Review-gates section was touched.
        gateAgentIds: draft.gateAgentIds,
      };
    } catch { /* ignore malformed session data */ }
  }, [isAuthenticated]);

  // Stage an od_ppt run into a ref as soon as we're authenticated.
  // NOTE: We do NOT remove od_ppt.pending here — we remove it only when
  // the WebSocket connects and we actually fire the questionnaire. This
  // makes the flow resilient to backend restarts between auth and connect.
  useEffect(() => {
    if (!isAuthenticated) return;
    const pending = sessionStorage.getItem("od_ppt.pending");
    if (!pending) return;
    try {
      const draft = JSON.parse(sessionStorage.getItem("ppt.draft") ?? "{}") as {
        templateId?: string; designSystemId?: string | null; brief?: string;
        customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
      };
      if (!draft.templateId || !draft.brief) return;
      pendingOdPptRef.current = {
        templateId: draft.templateId,
        designSystemId: draft.designSystemId ?? null,
        brief: draft.brief,
        discovery: null,
        customDsBody: draft.customDsBody,
        customTemplateBody: draft.customTemplateBody,
        sourceRunId: draft.sourceRunId,
        // Present only when the wizard's Review-gates section was touched.
        gateAgentIds: draft.gateAgentIds,
      };
    } catch { /* ignore malformed session data */ }
  }, [isAuthenticated]);
  useEffect(() => {
    if (!isAuthenticated) return;
    const currentToken = getToken();
    if (!currentToken) return;

    getWorkflows(currentToken, { limit: 50 })
      .then((runs) => setRecentRuns(runs))
      .catch(() => {
        // Silently fail — workflows will load when backend is available
        // This prevents the error from showing on the UI
      });
  }, [isAuthenticated]);

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = useCallback((msg: StreamMessage) => {
    // Phase 12 (RESUME-03 FE half) — track the last-received seq per run so the
    // reconnect can send it as after_seq (durable replay, 12-03). Every backend
    // event has carried seq/event_id since Phase 5. The max-seen seq is the
    // resume offset; the seen-event_id set dedupes replayed events so a durable
    // reconnect replay applies each event at most once (idempotent).
    const evData = (msg.data as Record<string, unknown> | undefined) ?? undefined;
    const evSeq = evData && typeof evData.seq === "number" ? (evData.seq as number) : undefined;
    if (typeof evSeq === "number" && evSeq > lastSeqRef.current) {
      lastSeqRef.current = evSeq;
    }

    // Phase 12 (§22) — wave/subagent lifecycle events route into the wave-tree
    // state (statuses only, D-14). Dedup by event_id FIRST (RESUME-03), then
    // fold the event into the wave groups, then return (these events do not flow
    // to the pipeline handler or the legacy switch below).
    const WAVE_EVENT_TYPES = [
      "wave_started", "wave_completed", "wave_failed",
      "subagent_spawned", "subagent_result",
    ];
    if (WAVE_EVENT_TYPES.includes(msg.type)) {
      const data = evData ?? {};
      const eventId = typeof data.event_id === "string" ? (data.event_id as string) : undefined;
      // Idempotent replay: ignore an already-applied event_id.
      if (eventId) {
        if (seenEventIdsRef.current.has(eventId)) return;
        seenEventIdsRef.current.add(eventId);
      }

      const waveIndex =
        typeof data.wave_index === "number" ? (data.wave_index as number) : undefined;
      if (waveIndex === undefined) return;

      setWaveGroups((prev) => {
        const next = prev.map((w) => ({ ...w, workers: [...w.workers] }));
        let group = next.find((w) => w.waveIndex === waveIndex);
        if (!group) {
          group = { waveIndex, taskIds: [], status: "pending", workers: [] };
          next.push(group);
        }

        if (msg.type === "wave_started") {
          const taskIds = Array.isArray(data.task_ids)
            ? (data.task_ids as unknown[]).map((t) => String(t))
            : group.taskIds;
          group.taskIds = taskIds;
          group.status = "running";
        } else if (msg.type === "wave_completed") {
          group.status = "completed";
        } else if (msg.type === "wave_failed") {
          group.status = "failed";
        } else if (msg.type === "subagent_spawned" || msg.type === "subagent_result") {
          const agent =
            typeof data.agent === "string"
              ? (data.agent as string)
              : typeof data.agent_id === "string"
              ? (data.agent_id as string)
              : "worker";
          const status =
            typeof data.status === "string"
              ? (data.status as string)
              : msg.type === "subagent_spawned"
              ? "running"
              : "completed";
          const existing = group.workers.find((wk) => wk.agent === agent);
          if (existing) {
            existing.status = status;
          } else {
            group.workers.push({ agent, status });
          }
        }

        return next;
      });
      return;
    }

    // Route pipeline messages to the workflow handler.
    // pipeline_cancelled was omitted previously, which left
    // `pipelineState.isRunning` stuck true after Stop — the BE cancelled
    // and emitted the event, but the FE never transitioned out of the
    // running state.
    // Phase 2 (Universal Engine): planner_*/gate_status/clarification events
    // are also routed to the workflow handler so the planning stage is visible.
    const pipelineTypes = [
      "pipeline_start", "agent_start", "agent_thinking", "agent_chunk",
      "agent_complete", "agent_error", "pipeline_complete", "pipeline_cancelled",
      "planner_start", "planner_complete", "planner_timeout", "planner_error",
      "gate_status", "clarification_limit_reached",
      // Phase 3 (T043/T044) — Thinking tab: agent_input carries inputPrompt +
      // contextSources; tool_call/tool_result carry tool execution data;
      // workflow_validated carries DAG edges for the dependency graph.
      "agent_input", "tool_call", "tool_result", "workflow_validated",
      // task_progress — prototype build agent reports per-task completion
      "task_progress",
      // task_loop_progress — engine-level build loop iteration counter
      "task_loop_progress",
      // pipeline_reconnected — backend confirmed reconnection to running pipeline
      "pipeline_reconnected",
      // Note: review_gate_ready and review_gate_approved are NOT here —
      // they go through the switch statement below to update reviewGateData state.
    ];
    if (pipelineTypes.includes(msg.type)) {
      handlePipelineMsgRef.current?.({
        type: msg.type,
        ...(msg.data as Record<string, unknown> || {}),
      });

      // When pipeline completes, route final output to preview panel
      if (msg.type === "pipeline_complete" && msg.data) {
        const data = msg.data as Record<string, unknown>;
        const finalOutput = data.final_output as string;
        const pipelineType = data.pipeline_type as string;

        if (finalOutput && pipelineType) {
          if (pipelineType === "user_stories" || pipelineType === "user_stories_revision" || pipelineType === "app_builder" || pipelineType === "app_builder_revision" || pipelineType === "custom") {
            setUserStoryContent(finalOutput);
          } else if (pipelineType === "ppt" || pipelineType === "ppt_revision" || pipelineType === "od_ppt" || pipelineType === "od_ppt_revision") {
            setPptContent(finalOutput);
          } else if (pipelineType === "prototype" || pipelineType === "prototype_revision" || pipelineType === "od_prototype") {
            setPrototypeContent(finalOutput);
          }
        }

        // Refresh workflow runs from backend after pipeline completes
        const currentToken = getToken();
        if (currentToken) {
          getWorkflows(currentToken, { limit: 50 })
            .then((runs) => setRecentRuns(runs))
            .catch(() => {});
        }
      }

      return;
    }

    switch (msg.type) {
      case "stream": {
        setIsStreaming(true);
        const chunk = msg.chunk || "";

        // Route content to the appropriate preview section
        if (msg.section === "user_stories") {
          setUserStoryContent((prev) => prev + chunk);
          setStreamingContent((prev) => prev + chunk);
          userStoryContentRef.current += chunk;
          activePreviewSectionRef.current = "user_stories";
        } else if (msg.section === "ppt") {
          // PPT content comes from pipeline_complete, not streaming
          // Only accumulate in ref for legacy chat mode
          pptContentRef.current += chunk;
          activePreviewSectionRef.current = "ppt";
        } else if (msg.section === "prototype") {
          // Prototype content comes from pipeline_complete, not streaming
          prototypeContentRef.current += chunk;
          activePreviewSectionRef.current = "prototype";
        } else {
          setStreamingContent((prev) => prev + chunk);
        }
        break;
      }

      case "phase_start": {
        break;
      }

      case "phase_end": {
        break;
      }

      case "complete": {
        setIsStreaming(false);
        const stepsSnapshot = [...(processStepsRef.current || [])];
        processStepsRef.current = [];
        const previewSection = activePreviewSectionRef.current;
        activePreviewSectionRef.current = null;

        setStreamingContent((prev) => {
          let chatContent = prev;

          if (!chatContent && previewSection) {
            if (previewSection === "ppt") {
              chatContent = "✅ **Presentation generated!** Check the Preview panel → PPT tab to see your slides.";
            } else if (previewSection === "prototype") {
              chatContent = "✅ **Prototype generated!** Check the Preview panel → Prototype tab to see the UI definition.";
            }
          }

          if (chatContent) {
            let artifact: { type: "user-stories" | "ppt" | "prototype"; filename: string; content: string; summary: string } | undefined;

            if (previewSection === "ppt" && pptContentRef.current) {
              artifact = {
                type: "ppt",
                filename: "presentation.pptx",
                content: pptContentRef.current,
                summary: "Slide deck with charts, tables, and comparisons",
              };
            } else if (previewSection === "prototype" && prototypeContentRef.current) {
              artifact = {
                type: "prototype",
                filename: "prototype.json",
                content: prototypeContentRef.current,
                summary: "Interactive prototype with component hierarchy and navigation",
              };
            } else if (previewSection === "user_stories" && userStoryContentRef.current) {
              artifact = {
                type: "user-stories",
                filename: "user-stories.md",
                content: userStoryContentRef.current,
                summary: "Structured backlog with epics, stories, and acceptance criteria",
              };
            }

            setMessages((msgs) => {
              const lastMsg = msgs[msgs.length - 1];
              if (lastMsg && lastMsg.role === "assistant") {
                return msgs;
              }
              return [...msgs, {
                id: crypto.randomUUID(),
                chatSessionId: "",
                role: "assistant" as const,
                content: chatContent,
                createdAt: new Date().toISOString(),
                steps: stepsSnapshot.length > 0 ? stepsSnapshot : undefined,
                artifact,
              }];
            });
          }
          return "";
        });

        setProcessSteps([]);

        if (msg.data && "user_stories" in msg.data) {
          const finalOutput = msg.data;
          if (finalOutput.user_stories) {
            setUserStoryContent(JSON.stringify(finalOutput.user_stories));
          }
          if (finalOutput.ppt) {
            setPptContent(JSON.stringify(finalOutput.ppt));
          }
          if (finalOutput.prototype) {
            setPrototypeContent(JSON.stringify(finalOutput.prototype));
          }
        }
        break;
      }

      case "error": {
        setIsStreaming(false);

        let errorMessage = "An error occurred during processing.";
        let errorCode: string | undefined;
        let recoverable = true;

        if (msg.data && "error" in msg.data) {
          const errorData = msg.data as { error?: string; code?: string; recoverable?: boolean };
          errorMessage = errorData.error || errorMessage;
          errorCode = errorData.code;
          recoverable = errorData.recoverable !== false;
        } else if (msg.chunk) {
          errorMessage = msg.chunk;
        }

        let content = `Error: ${errorMessage}`;
        if (errorCode) {
          content += ` [code:${errorCode}]`;
        }
        content += ` [recoverable:${recoverable}]`;

        const errorMsg: ChatMessage = {
          id: crypto.randomUUID(),
          chatSessionId: "",
          role: "assistant",
          content,
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMsg]);
        setStreamingContent("");
        break;
      }

      case "title_update": {
        if (msg.data && "title" in msg.data && "chat_session_id" in msg.data) {
          const titleData = msg.data as { chat_session_id: string; title: string };
          setChatTitleUpdate(titleData);
        }
        break;
      }

      case "workflow_title_update": {
        // Claude generated a clean title for the workflow run — update the list
        if (msg.data && "workflow_id" in msg.data && "title" in msg.data) {
          const { workflow_id, title } = msg.data as { workflow_id: string; title: string };
          setRecentRuns((prev) =>
            prev.map((r) => r.id === workflow_id ? { ...r, title } : r)
          );
        }
        break;
      }

      case "questionnaire": {
        if (msg.data && "questions" in msg.data) {
          setQuestionnaireData(msg.data as { questions: { id: string; question: string; options: string[] }[] });
        }
        break;
      }

      case "questionnaire_ready": {
        if (msg.data && "questions" in msg.data) {
          const data = msg.data as {
            pipeline_run_id?: string;
            questions: Array<{ question_id: string; question_text: string; options?: string[] | null; answer_type?: string }>;
          };
          const mapped = (data.questions || []).map((q) => ({
            id: q.question_id,
            question: q.question_text,
            options: q.options || [],
            answerType: q.answer_type || "single_choice",
          }));
          setQuestionnaireData({ questions: mapped });
          if (data.pipeline_run_id) {
            setActivePipelineRunId(data.pipeline_run_id);
          }
        }
        break;
      }

      case "questionnaire_complete": {
        // Clarify gate resolved — clear the pending questionnaire UI.
        setQuestionnaireData(null);
        break;
      }

      case "review_gate_ready": {
        // Agent completed and declared Human_Gate — pause for user review.
        if (msg.data) {
          const data = msg.data as {
            gate_key: string;
            agent_id: string;
            agent_name: string;
            output: string;
            pipeline_run_id: string;
          };
          setReviewGateData({
            gateKey: data.gate_key,
            agentId: data.agent_id,
            agentName: data.agent_name,
            output: data.output,
            pipelineRunId: data.pipeline_run_id,
          });
        }
        break;
      }

      case "review_gate_approved": {
        // User approved — clear the review gate UI and continue.
        setReviewGateData(null);
        break;
      }

      case "step": {
        if (msg.data && "id" in msg.data && "status" in msg.data) {
          const stepData = msg.data as ProcessStep;
          setProcessSteps((prev) => {
            const existing = prev.findIndex((s) => s.id === stepData.id);
            let updated: ProcessStep[];
            if (existing >= 0) {
              updated = [...prev];
              updated[existing] = stepData;
            } else {
              updated = [...prev, stepData];
            }
            processStepsRef.current = updated;
            return updated;
          });
        }
        break;
      }
    }
  }, []);

  // WebSocket connection
  const { send, connectionStatus, reconnect } = useWebSocket({
    url: ENV.WS_URL,
    token,
    onMessage: handleWebSocketMessage,
  });

  // Workflow pipeline state
  const { pipelineState, startPipeline, resetPipeline, isRunning: isPipelineRunning, handleMessage: handlePipelineMsg, submitQuestionnaire } = useWorkflow(send);

  // Keep pipeline handler ref in sync
  useEffect(() => {
    handlePipelineMsgRef.current = handlePipelineMsg;
  }, [handlePipelineMsg]);

  // Fire a staged od_prototype run as soon as the WebSocket is open.
  // Re-reads from sessionStorage on every connect so backend restarts
  // don't lose the pending run.
  useEffect(() => {
    if (connectionStatus !== "connected") return;

    let pending = pendingOdProtoRef.current;
    if (!pending) {
      const flag = sessionStorage.getItem("od_prototype.pending");
      if (!flag) return;
      try {
        const draft = JSON.parse(sessionStorage.getItem("prototype.draft") ?? "{}") as {
          templateId?: string; designSystemId?: string; brief?: string;
          customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
        };
        const discovery = JSON.parse(sessionStorage.getItem("prototype.discovery") ?? "null");
        if (!draft.templateId || !draft.designSystemId || !draft.brief) return;
        pending = {
          templateId: draft.templateId,
          designSystemId: draft.designSystemId,
          brief: draft.brief,
          discovery,
          customDsBody: draft.customDsBody,
          customTemplateBody: draft.customTemplateBody,
          sourceRunId: draft.sourceRunId,
          gateAgentIds: draft.gateAgentIds,
        };
      } catch { return; }
    }

    pendingOdProtoRef.current = null;
    sessionStorage.removeItem("od_prototype.pending");

    setUserStoryContent("");
    setPptContent("");
    setPrototypeContent("");
    pptContentRef.current = "";
    prototypeContentRef.current = "";
    userStoryContentRef.current = "";
    // Phase 2 (Universal Engine): skip the legacy generate_questions pre-flight.
    // The backend no longer handles that message type. The pipeline starts
    // immediately via run_pipeline; the Deep_Planner_Agent will emit
    // questionnaire_ready mid-run if clarification is needed.
    setPendingOdProtoParams({
      brief: pending.brief,
      templateId: pending.templateId,
      designSystemId: pending.designSystemId,
      discovery: pending.discovery,
      customDsBody: pending.customDsBody,
      customTemplateBody: pending.customTemplateBody,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pending.sourceRunId ? { sourceRunId: pending.sourceRunId } : {}),
      // Phase 6 (T5b): per-run gate selection. Present ONLY when the wizard's
      // Review-gates section was touched (the draft carried gateAgentIds). Guard on
      // presence (!== undefined), NOT truthiness — an empty array is a valid
      // "no gates" choice. Absent ⇒ left undefined ⇒ DashboardLayout omits
      // gate_agent_ids ⇒ backend static default (byte-identical to today).
      ...(pending.gateAgentIds !== undefined ? { gateAgentIds: pending.gateAgentIds } : {}),
    });
  // send and connectionStatus drive the re-run.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionStatus]);

  // Fire a staged od_ppt run as soon as the WebSocket is open.
  // Re-reads from sessionStorage on every connect so backend restarts
  // don't lose the pending run.
  useEffect(() => {
    if (connectionStatus !== "connected") return;

    // Try ref first, then fall back to sessionStorage (handles reconnects)
    let pending = pendingOdPptRef.current;
    if (!pending) {
      const flag = sessionStorage.getItem("od_ppt.pending");
      if (!flag) return;
      try {
        const draft = JSON.parse(sessionStorage.getItem("ppt.draft") ?? "{}") as {
          templateId?: string; designSystemId?: string | null; brief?: string;
          customDsBody?: string; customTemplateBody?: string; sourceRunId?: string; gateAgentIds?: string[];
        };
        if (!draft.templateId || !draft.brief) return;
        pending = {
          templateId: draft.templateId,
          designSystemId: draft.designSystemId ?? null,
          brief: draft.brief,
          discovery: null,
          customDsBody: draft.customDsBody,
          customTemplateBody: draft.customTemplateBody,
          sourceRunId: draft.sourceRunId,
          gateAgentIds: draft.gateAgentIds,
        };
      } catch { return; }
    }

    // Consume — clear both ref and sessionStorage key
    pendingOdPptRef.current = null;
    sessionStorage.removeItem("od_ppt.pending");

    setUserStoryContent("");
    setPptContent("");
    setPrototypeContent("");
    pptContentRef.current = "";
    prototypeContentRef.current = "";
    userStoryContentRef.current = "";
    // Phase 2 (Universal Engine): skip the legacy generate_questions pre-flight.
    // The backend no longer handles that message type. The pipeline starts
    // immediately via run_pipeline; the Deep_Planner_Agent will emit
    // questionnaire_ready mid-run if clarification is needed.
    setPendingOdPptParams({
      brief: pending.brief,
      templateId: pending.templateId,
      designSystemId: pending.designSystemId,
      discovery: pending.discovery,
      customDsBody: pending.customDsBody,
      customTemplateBody: pending.customTemplateBody,
      // Phase 3 (T056): pass source_workflow_run_id for revision chaining
      ...(pending.sourceRunId ? { sourceRunId: pending.sourceRunId } : {}),
      // Phase 6 (T5b): per-run gate selection. Present ONLY when the wizard's
      // Review-gates section was touched. Guard on presence (!== undefined), NOT
      // truthiness — [] is a valid "no gates" choice. Absent ⇒ undefined ⇒
      // DashboardLayout omits gate_agent_ids ⇒ backend static default.
      ...(pending.gateAgentIds !== undefined ? { gateAgentIds: pending.gateAgentIds } : {}),
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionStatus]);

  // Send a message via WebSocket (for refinement chat)
  const sendingRef = useRef(false);

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (sendingRef.current) return;
      sendingRef.current = true;

      try {
        let chatId = activeChatId;

        if (!chatId) {
          const currentToken = getToken();
          if (!currentToken) { sendingRef.current = false; return; }
          try {
            const newSession = await createChat(currentToken, content.slice(0, 50));
            chatId = newSession.id;
            setActiveChatId(chatId);
          } catch (err) {
            console.error("Failed to auto-create chat:", err);
            sendingRef.current = false;
            return;
          }
        }

        const userMessage: ChatMessage = {
          id: crypto.randomUUID(),
          chatSessionId: chatId,
          role: "user",
          content,
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, userMessage]);

        setIsStreaming(true);
        setStreamingContent("");
        setCurrentMode("default");
        setProcessSteps([]);
        activePreviewSectionRef.current = null;
        pptContentRef.current = "";
        prototypeContentRef.current = "";
        userStoryContentRef.current = "";
        setUserStoryContent("");
        setPptContent("");
        setPrototypeContent("");

        send(
          JSON.stringify({
            type: "user_message",
            content,
            chat_session_id: chatId,
          })
        );
      } finally {
        setTimeout(() => { sendingRef.current = false; }, 500);
      }
    },
    [activeChatId, send]
  );

  // Send a message with a specific mode
  const handleSendMessageWithMode = useCallback(
    async (content: string, mode: ChatMode) => {
      let chatId = activeChatId;

      if (!chatId) {
        const currentToken = getToken();
        if (!currentToken) return;
        try {
          const newSession = await createChat(currentToken, content.slice(0, 50));
          chatId = newSession.id;
          setActiveChatId(chatId);
        } catch (err) {
          console.error("Failed to auto-create chat:", err);
          return;
        }
      }

      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        chatSessionId: chatId,
        role: "user",
        content,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      setIsStreaming(true);
      setStreamingContent("");
      setCurrentMode(mode);
      setProcessSteps([]);
      pptContentRef.current = "";
      prototypeContentRef.current = "";
      userStoryContentRef.current = "";
      setUserStoryContent("");
      setPptContent("");
      setPrototypeContent("");

      send(
        JSON.stringify({
          type: "user_message",
          content,
          chat_session_id: chatId,
          mode,
        })
      );
    },
    [activeChatId, send]
  );

  // Select a chat session and load its messages
  const handleSelectChat = useCallback(
    async (chatId: string) => {
      setActiveChatId(chatId);
      setStreamingContent("");
      setIsStreaming(false);
      setProcessSteps([]);

      const currentToken = getToken();
      if (!currentToken) return;

      try {
        const chatDetail = await getChat(currentToken, chatId);
        const loadedMessages: ChatMessage[] = chatDetail.messages.map((m) => {
          let content = m.content;
          let steps: ProcessStep[] | undefined;

          const stepsMatch = content.match(/^<!--steps:(.*?)-->/);
          if (stepsMatch) {
            try {
              steps = JSON.parse(stepsMatch[1]);
            } catch { /* ignore parse errors */ }
            content = content.replace(/^<!--steps:.*?-->/, "");
          }

          return {
            id: m.id,
            chatSessionId: m.chat_session_id,
            role: m.role as "user" | "assistant" | "system",
            content,
            createdAt: m.created_at,
            steps,
          };
        });
        setMessages(loadedMessages);

        if (chatDetail.final_output) {
          try {
            const finalOutput = JSON.parse(chatDetail.final_output);
            if (finalOutput.user_stories) {
              setUserStoryContent(JSON.stringify(finalOutput.user_stories));
            }
            if (finalOutput.ppt) {
              setPptContent(JSON.stringify(finalOutput.ppt));
            }
            if (finalOutput.prototype) {
              setPrototypeContent(JSON.stringify(finalOutput.prototype));
            }
          } catch {
            // Ignore parse errors
          }
        } else {
          setUserStoryContent("");
          setPptContent("");
          setPrototypeContent("");
        }
      } catch (err) {
        console.error("Failed to load chat:", err);
      }
    },
    []
  );

  // Handle selecting a workflow run from sidebar/hub
  const handleSelectWorkflowRun = useCallback(
    async (run: WorkflowRun) => {
      // Clear existing content
      setUserStoryContent("");
      setPptContent("");
      setPrototypeContent("");

      // Load the workflow output from backend
      const currentToken = getToken();
      if (!currentToken) return;

      try {
        const fullRun = await getWorkflow(currentToken, run.id);

        if (fullRun.output && fullRun.status === "completed") {
          if (fullRun.type === "user_stories" || fullRun.type === "user_stories_revision") {
            setUserStoryContent(fullRun.output);
          } else if (fullRun.type === "ppt" || fullRun.type === "ppt_revision" || fullRun.type === "od_ppt" || fullRun.type === "od_ppt_revision") {
            setPptContent(fullRun.output);
          } else if (fullRun.type === "prototype" || fullRun.type === "prototype_revision" || fullRun.type === "od_prototype") {
            setPrototypeContent(fullRun.output);
          }
        }
      } catch (err) {
        console.error("Failed to load workflow output:", err);
      }
    },
    []
  );

  // Handle new chat creation from sidebar
  const handleNewChat = useCallback((chatSession: ChatSession) => {
    setActiveChatId(chatSession.id);
    setMessages([]);
    setStreamingContent("");
    setIsStreaming(false);
    setUserStoryContent("");
    setPptContent("");
    setPrototypeContent("");
  }, []);

  // Handle deleting a chat session
  const handleDeleteChat = useCallback(
    async (chatId: string) => {
      const currentToken = getToken();
      if (!currentToken) return;

      try {
        await deleteChat(currentToken, chatId);
      } catch (err) {
        console.error("Failed to delete chat:", err);
      }

      if (chatId === activeChatId) {
        setActiveChatId(null);
        setMessages([]);
        setStreamingContent("");
        setIsStreaming(false);
        setUserStoryContent("");
        setPptContent("");
        setPrototypeContent("");
      }
    },
    [activeChatId]
  );

  // Handle logout: revoke the JWT on the backend, then drop it locally and
  // redirect. We await the logout call so the token is reliably revoked
  // before navigation — fire-and-forget would be at the mercy of the page
  // unload aborting the request. logout() swallows network errors and always
  // clears the local token in its finally block, so navigation is safe even
  // if the backend is unreachable.
  const handleLogout = useCallback(async () => {
    await logout(getToken() ?? "");
    router.replace("/login");
  }, [router]);

  if (!mounted || !isAuthenticated) {
    // Return null (not a loading screen) until the client has hydrated and
    // confirmed auth. This avoids both the hydration mismatch (server renders
    // null, client renders null — they match) and the black flash.
    return null;
  }

  return (
    <DashboardLayout
      activeChatId={activeChatId}
      messages={messages}
      isStreaming={isStreaming}
      streamingContent={streamingContent}
      userStoryContent={userStoryContent}
      pptContent={pptContent}
      prototypeContent={prototypeContent}
      connectionStatus={connectionStatus}
      onSendMessage={handleSendMessage}
      onSendMessageWithMode={handleSendMessageWithMode}
      onSelectChat={handleSelectChat}
      onNewChat={handleNewChat}
      onDeleteChat={handleDeleteChat}
      onLogout={handleLogout}
      onReconnect={reconnect}
      messageMode={currentMode}
      chatTitleUpdate={chatTitleUpdate}
      processSteps={processSteps}
      websocketSend={send}
      pipelineState={pipelineState}
      onStartPipeline={(type, message, agentIds, attachedSkills, attachedHooks, extraParams) => {
        const isRevision = type.endsWith("_revision");
        if (!isRevision) {
          // Fresh run — clear previous preview content
          setUserStoryContent("");
          setPptContent("");
          setPrototypeContent("");
          pptContentRef.current = "";
          prototypeContentRef.current = "";
          userStoryContentRef.current = "";
        }
        // For revisions, keep existing content visible until new output arrives
        startPipeline(type, message, agentIds, attachedSkills, attachedHooks, extraParams);
      }}
      onResetPipeline={resetPipeline}
      recentRuns={recentRuns}
      onSelectWorkflowRun={handleSelectWorkflowRun}
      questionnaireData={questionnaireData}
      activePipelineRunId={activePipelineRunId}
      getLastSeq={getLastSeq}
      onSubmitQuestionnaire={submitQuestionnaire}
      reviewGateData={reviewGateData}
      onApproveReview={(gateKey, editedContent) => {
        send(JSON.stringify({ type: "approve_review", gate_key: gateKey, approved: true, edited_content: editedContent ?? null }));
      }}
      onRejectReview={(gateKey) => {
        send(JSON.stringify({ type: "approve_review", gate_key: gateKey, approved: false }));
        setReviewGateData(null);
      }}
      pendingOdProtoParams={pendingOdProtoParams}
      onClearPendingOdProto={() => setPendingOdProtoParams(null)}
      pendingOdPptParams={pendingOdPptParams}
      onClearPendingOdPpt={() => setPendingOdPptParams(null)}
      userTier={user?.tier ?? "basic"}
      userEmail={user?.email}
    />
  );
}
