import { http } from "./http";
import { setToken } from "@/lib/api";
import type { AuthResponse, User } from "@/types/index";

export const authApi = {
  register: async (email: string, password: string): Promise<AuthResponse> => {
    const { data } = await http.post<AuthResponse>("/api/auth/register", { email, password });
    setToken(data.token);
    return data;
  },

  login: async (email: string, password: string): Promise<AuthResponse> => {
    const { data } = await http.post<AuthResponse>("/api/auth/login", { email, password });
    setToken(data.token);
    return data;
  },

  me: async (): Promise<User> => {
    const { data } = await http.get<User>("/api/auth/me");
    return data;
  },

  logout: async (): Promise<void> => {
    await http.post("/api/auth/logout");
  },

  changePassword: async (
    current_password: string,
    new_password: string
  ): Promise<{ message: string }> => {
    const { data } = await http.post<{ message: string }>("/api/auth/change-password", {
      current_password,
      new_password,
    });
    return data;
  },
};
