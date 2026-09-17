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
  // Invitation-only (Cognito migration Phase 3, Decision 6) -- no password
  // parameter. The backend's CreateUserRequest is extra=forbid and rejects
  // one entirely; Cognito emails a temporary password directly to the new
  // account.
  createUser: async (
    email: string,
    tier: string,
    is_admin: boolean
  ): Promise<AdminUser> => {
    const { data } = await http.post<AdminUser>("/api/admin/users", {
      email,
      tier,
      is_admin,
    });
    return data;
  },
  deleteUser: async (userId: string): Promise<void> => {
    await http.delete(`/api/admin/users/${userId}`);
  },
  disableUser: async (userId: string): Promise<AdminUser> => {
    const { data } = await http.post<AdminUser>(`/api/admin/users/${userId}/disable`);
    return data;
  },
  enableUser: async (userId: string): Promise<AdminUser> => {
    const { data } = await http.post<AdminUser>(`/api/admin/users/${userId}/enable`);
    return data;
  },
};
