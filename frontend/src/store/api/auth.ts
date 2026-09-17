import { http } from "./http";
import type { User } from "@/types/index";

export const authApi = {
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
