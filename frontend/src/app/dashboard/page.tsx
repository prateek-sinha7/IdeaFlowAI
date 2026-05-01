"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, getChat, addMessage } from "@/lib/api";
import { ENV } from "@/lib/env";
import { useWebSocket } from "@/hooks/useWebSocket";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import type { ChatMessage, ChatSession, StreamMessage } from "@/types/index";

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

        // Accumulate streaming content for the chat panel
        setStreamingContent((prev) => prev + chunk);

        // Route content to the appropriate preview section
        if (msg.section === "user_stories") {
          setUserStoryContent((prev) => prev + chunk);
        } else if (msg.section === "ppt") {
          setPptContent((prev) => prev + chunk);
        } else if (msg.section === "prototype") {
          setPrototypeContent((prev) => prev + chunk);
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
        // Streaming is done — finalize the assistant message
        setIsStreaming(false);
        setStreamingContent((prev) => {
          if (prev) {
            const assistantMessage: ChatMessage = {
              id: crypto.randomUUID(),
              chatSessionId: "",
              role: "assistant",
              content: prev,
              createdAt: new Date().toISOString(),
            };
            setMessages((msgs) => [...msgs, assistantMessage]);
          }
          return "";
        });

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
        const errorContent = msg.chunk || "An error occurred during processing.";
        const errorMessage: ChatMessage = {
          id: crypto.randomUUID(),
          chatSessionId: "",
          role: "assistant",
          content: `Error: ${errorContent}`,
          createdAt: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMessage]);
        setStreamingContent("");
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
    (content: string) => {
      if (!activeChatId) return;

      // Add user message to local state
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        chatSessionId: activeChatId,
        role: "user",
        content,
        createdAt: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Reset streaming state for new response
      setIsStreaming(true);
      setStreamingContent("");

      // Send via WebSocket
      send(
        JSON.stringify({
          type: "user_message",
          content,
          chat_session_id: activeChatId,
        })
      );

      // Also persist the message to the backend via REST
      const currentToken = getToken();
      if (currentToken) {
        addMessage(currentToken, activeChatId, content, "user").catch((err) =>
          console.error("Failed to persist message:", err)
        );
      }
    },
    [activeChatId, send]
  );

  // Select a chat session and load its messages
  const handleSelectChat = useCallback(
    async (chatId: string) => {
      setActiveChatId(chatId);
      setStreamingContent("");
      setIsStreaming(false);

      const currentToken = getToken();
      if (!currentToken) return;

      try {
        const chatDetail = await getChat(currentToken, chatId);
        // Map backend messages (snake_case) to frontend ChatMessage format (camelCase)
        const loadedMessages: ChatMessage[] = chatDetail.messages.map((m) => ({
          id: m.id,
          chatSessionId: m.chat_session_id,
          role: m.role as "user" | "assistant" | "system",
          content: m.content,
          createdAt: m.created_at,
        }));
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
      onSelectChat={handleSelectChat}
      onNewChat={handleNewChat}
      onReconnect={reconnect}
    />
  );
}
