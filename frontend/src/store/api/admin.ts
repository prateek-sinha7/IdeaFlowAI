import { http } from "./http";
import type { AdminUser } from "@/lib/api";

export const adminApi = {
  listUsers: async (): Promise<AdminUser[]> => {
    const { data } = await http.get<AdminUser[]>("/api/admin/users");
    return data;
  },
  updateTier: async (userId: string, tier: string): Promise<AdminUser> => {
    const { data } = await http.patch<AdminUser>(`/api/admin/users/${userId}/tier`, { tier });
    return data;
  },
  createUser: async (
    email: string,
    password: string,
    tier: string,
    is_admin: boolean
  ): Promise<AdminUser> => {
    const { data } = await http.post<AdminUser>("/api/admin/users", {
      email,
      password,
      tier,
      is_admin,
    });
    return data;
  },
  deleteUser: async (userId: string): Promise<void> => {
    await http.delete(`/api/admin/users/${userId}`);
  },
};
