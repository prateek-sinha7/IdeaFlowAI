"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, getChat, addMessage, clearToken, deleteChat, createChat, getWorkflows, getWorkflow } from "@/lib/api";
import { ENV } from "@/lib/env";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useWorkflow } from "@/hooks/useWorkflow";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import type { ChatMessage, ChatSession, StreamMessage, ProcessStep, WorkflowRun } from "@/types/index";
import type { ChatMode } from "@/components/chat/ChatInput";

/**
 * Dashboard page - the main authenticated view.
 * Manages WebSocket connection, workflow runs, and streaming content.
 * Workflow-first: the primary experience is running agent pipelines.
 */
export default function DashboardPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

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

  // Workflow runs state (primary)
  const [recentRuns, setRecentRuns] = useState<WorkflowRun[]>([]);

  // Auth check on mount
  useEffect(() => {
    const storedToken = getToken();
    if (!storedToken) {
      router.replace("/login");
      return;
    }
    setToken(storedToken);
    setIsAuthenticated(true);
  }, [router]);

  // Fetch workflow runs on auth
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
    // Route pipeline messages to the workflow handler
    const pipelineTypes = ["pipeline_start", "agent_start", "agent_thinking", "agent_chunk", "agent_complete", "agent_error", "pipeline_complete"];
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
          if (pipelineType === "user_stories" || pipelineType === "app_builder" || pipelineType === "reverse_engineer" || pipelineType === "custom") {
            setUserStoryContent(finalOutput);
          } else if (pipelineType === "ppt" || pipelineType === "validate_pitch") {
            setPptContent(finalOutput);
          } else if (pipelineType === "prototype") {
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
          setPptContent((prev) => prev + chunk);
          pptContentRef.current += chunk;
          activePreviewSectionRef.current = "ppt";
        } else if (msg.section === "prototype") {
          setPrototypeContent((prev) => prev + chunk);
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
  const { pipelineState, startPipeline, resetPipeline, isRunning: isPipelineRunning, handleMessage: handlePipelineMsg } = useWorkflow(send);

  // Keep pipeline handler ref in sync
  useEffect(() => {
    handlePipelineMsgRef.current = handlePipelineMsg;
  }, [handlePipelineMsg]);

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
          if (fullRun.type === "user_stories") {
            setUserStoryContent(fullRun.output);
          } else if (fullRun.type === "ppt") {
            setPptContent(fullRun.output);
          } else if (fullRun.type === "prototype") {
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

  // Handle logout
  const handleLogout = useCallback(() => {
    clearToken();
    router.replace("/login");
  }, [router]);

  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <div className="text-grey">Loading...</div>
      </div>
    );
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
      onStartPipeline={startPipeline}
      onResetPipeline={resetPipeline}
      recentRuns={recentRuns}
      onSelectWorkflowRun={handleSelectWorkflowRun}
    />
  );
}
