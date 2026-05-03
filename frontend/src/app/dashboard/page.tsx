"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, getChat, addMessage, clearToken, deleteChat, createChat } from "@/lib/api";
import { ENV } from "@/lib/env";
import { useWebSocket } from "@/hooks/useWebSocket";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import type { ChatMessage, ChatSession, StreamMessage, ProcessStep } from "@/types/index";
import type { ChatMode } from "@/components/chat/ChatInput";

/**
 * Dashboard page - the main authenticated view.
 * Manages WebSocket connection, active chat state, and streaming content.
 * Passes all handlers and state down to DashboardLayout.
 */
export default function DashboardPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Chat state
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

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = useCallback((msg: StreamMessage) => {
    switch (msg.type) {
      case "stream": {
        setIsStreaming(true);
        const chunk = msg.chunk || "";

        // Route content to the appropriate preview section
        if (msg.section === "user_stories") {
          setUserStoryContent((prev) => prev + chunk);
          setStreamingContent((prev) => prev + chunk);
          activePreviewSectionRef.current = "user_stories";
        } else if (msg.section === "ppt") {
          setPptContent((prev) => prev + chunk);
          activePreviewSectionRef.current = "ppt";
        } else if (msg.section === "prototype") {
          setPrototypeContent((prev) => prev + chunk);
          activePreviewSectionRef.current = "prototype";
        } else {
          setStreamingContent((prev) => prev + chunk);
        }
        break;
      }

      case "phase_start": {
        // A new phase is starting — could reset section content if needed
        break;
      }

      case "phase_end": {
        // Phase completed — content for this phase is finalized
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

          // If no chat content (went to preview only), add a summary
          if (!chatContent && previewSection) {
            if (previewSection === "ppt") {
              chatContent = "✅ **Presentation generated!** Check the Preview panel → PPT tab to see your slides.";
            } else if (previewSection === "prototype") {
              chatContent = "✅ **Prototype generated!** Check the Preview panel → Prototype tab to see the UI definition.";
            }
          }

          if (chatContent) {
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
              }];
            });
          }
          return "";
        });

        // Clear live steps display
        setProcessSteps([]);

        // If complete message has final output data, update preview sections
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

        // Parse structured error data
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

        // Build content string with metadata for the ErrorMessage component
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
        // Backend generated a title for the chat — update sidebar
        if (msg.data && "title" in msg.data && "chat_session_id" in msg.data) {
          const titleData = msg.data as { chat_session_id: string; title: string };
          setChatTitleUpdate(titleData);
        }
        break;
      }

      case "step": {
        // Process step indicator from backend
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

  // Send a message via WebSocket
  const handleSendMessage = useCallback(
    async (content: string) => {
      let chatId = activeChatId;

      // Auto-create a chat session if none is selected (like ChatGPT/Claude)
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

      // Add user message to local state
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        chatSessionId: chatId,
        role: "user",
        content,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Reset streaming state for new response
      setIsStreaming(true);
      setStreamingContent("");
      setCurrentMode("default");
      setProcessSteps([]);
      activePreviewSectionRef.current = null;

      // Send via WebSocket (backend persists the message)
      send(
        JSON.stringify({
          type: "user_message",
          content,
          chat_session_id: chatId,
        })
      );
    },
    [activeChatId, send]
  );

  // Send a message with a specific mode
  const handleSendMessageWithMode = useCallback(
    async (content: string, mode: ChatMode) => {
      let chatId = activeChatId;

      // Auto-create a chat session if none is selected
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

      // Add user message to local state
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        chatSessionId: chatId,
        role: "user",
        content,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Reset streaming state for new response
      setIsStreaming(true);
      setStreamingContent("");
      setCurrentMode(mode);
      setProcessSteps([]);

      // Send via WebSocket with mode (backend persists the message)
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
        // Map backend messages and parse embedded steps
        const loadedMessages: ChatMessage[] = chatDetail.messages.map((m) => {
          let content = m.content;
          let steps: ProcessStep[] | undefined;

          // Parse embedded steps marker: <!--steps:JSON-->
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

        // Load final output into preview panels if available
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
            // Ignore parse errors for final_output
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

      // If the deleted chat was the active chat, clear state
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
    />
  );
}
