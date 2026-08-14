import { http } from "./http";

export interface ChatSession {
  id: string;
  title: string;
  last_activity: string;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  chat_session_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface ChatDetail extends ChatSession {
  messages: ChatMessage[];
  final_output: string | null;
}

export const chatsApi = {
  create: async (title?: string): Promise<ChatSession> => {
    const { data } = await http.post<ChatSession>("/api/chats", { title: title ?? null });
    return data;
  },

  list: async (): Promise<ChatSession[]> => {
    const { data } = await http.get<ChatSession[]>("/api/chats");
    return data;
  },

  get: async (chatId: string): Promise<ChatDetail> => {
    const { data } = await http.get<ChatDetail>(`/api/chats/${chatId}`);
    return data;
  },

  addMessage: async (
    chatId: string,
    content: string,
    role: string = "user"
  ): Promise<ChatMessage> => {
    const { data } = await http.put<ChatMessage>(`/api/chats/${chatId}/messages`, {
      content,
      role,
    });
    return data;
  },

  delete: async (chatId: string): Promise<void> => {
    await http.delete(`/api/chats/${chatId}`);
  },
};
