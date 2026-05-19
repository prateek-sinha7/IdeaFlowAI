"use client";

import { useEffect, useState, useCallback } from "react";import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  Users, Shield, ChevronDown, Search, Plus, Trash2,
  RefreshCw, CheckCircle2, AlertCircle, X, LogOut,
} from "lucide-react";
import {
  getToken, getMe, logout,
  adminListUsers, adminUpdateTier, adminCreateUser, adminDeleteUser,
} from "@/lib/api";
import type { AdminUser } from "@/lib/api";
import { TIER_LABELS } from "@/lib/entitlements";
import type { Tier } from "@/lib/entitlements";

const TIER_ORDER: Tier[] = ["basic", "pro", "enterprise"];

const TIER_STYLES: Record<string, string> = {
  basic:      "bg-gray-100 text-gray-700 border-gray-200",
  pro:        "bg-[#E8EDF5] text-[#1B2A4A] border-[#1B2A4A]/20",
  enterprise: "bg-[#1B2A4A] text-white border-[#1B2A4A]",
};

function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide border ${TIER_STYLES[tier] ?? TIER_STYLES.basic}`}>
      {TIER_LABELS[tier as Tier] ?? tier}
    </span>
  );
}

function TierDropdown({ userId, currentTier, onUpdate }: {
  userId: string;
  currentTier: string;
  onUpdate: (userId: string, tier: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [localTier, setLocalTier] = useState(currentTier);

  // Sync if parent updates
  useEffect(() => { setLocalTier(currentTier); }, [currentTier]);

  const handleSelect = async (tier: string) => {
    if (tier === localTier) { setOpen(false); return; }
    setLoading(true);
    setOpen(false);
    setLocalTier(tier); // optimistic update
    try {
      await onUpdate(userId, tier);
    } catch {
      setLocalTier(currentTier); // revert on error
    }
    setLoading(false);
  };

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen(!open)}
        disabled={loading}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors text-[11px] font-medium text-gray-700 disabled:opacity-50"
      >
        {loading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <TierBadge tier={localTier} />}
        <ChevronDown className="h-3 w-3 text-gray-400" />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -4, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.97 }}
              transition={{ duration: 0.1 }}
              className="absolute left-0 top-full mt-1 z-50 bg-white rounded-xl border border-gray-200 shadow-xl overflow-hidden min-w-[140px]"
            >
              {TIER_ORDER.map(tier => (
                <button
                  key={tier}
                  onClick={(e) => { e.stopPropagation(); handleSelect(tier); }}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 text-left text-[12px] hover:bg-gray-50 transition-colors ${tier === localTier ? "bg-gray-50" : ""}`}
                >
                  <TierBadge tier={tier} />
                  {tier === localTier && <CheckCircle2 className="h-3 w-3 text-[#1B2A4A] ml-auto" />}
                </button>
              ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [toast, setToast] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Create user form
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newTier, setNewTier] = useState<Tier>("basic");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);

  const showToast = useCallback((type: "success" | "error", text: string) => {
    setToast({ type, text });
    setTimeout(() => setToast(null), 3500);
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace("/login"); return; }

    // Verify admin access
    getMe(token).then(user => {
      if (!user.is_admin) { router.replace("/dashboard"); return; }
      loadUsers(token);
    }).catch(() => router.replace("/login"));
  }, [router]);

  const loadUsers = async (token?: string) => {
    const t = token ?? getToken();
    if (!t) return;
    setLoading(true);
    try {
      const data = await adminListUsers(t);
      setUsers(data);
    } catch {
      showToast("error", "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateTier = async (userId: string, tier: string) => {
    const token = getToken();
    if (!token) return;
    try {
      const updated = await adminUpdateTier(token, userId, tier);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, tier: updated.tier } : u));
      showToast("success", `Tier updated to ${TIER_LABELS[tier as Tier]}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update tier";
      showToast("error", msg);
    }
  };

  const handleCreateUser = async () => {
    if (!newEmail || !newPassword) return;
    const token = getToken();
    if (!token) return;
    setCreating(true);
    try {
      const created = await adminCreateUser(token, newEmail, newPassword, newTier, newIsAdmin);
      setUsers(prev => [created, ...prev]);
      setShowCreate(false);
      setNewEmail(""); setNewPassword(""); setNewTier("basic"); setNewIsAdmin(false);
      showToast("success", `User ${created.email} created`);
    } catch (err: unknown) {
      showToast("error", err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      await adminDeleteUser(token, userId);
      setUsers(prev => prev.filter(u => u.id !== userId));
      setDeleteConfirm(null);
      showToast("success", "User deleted");
    } catch {
      showToast("error", "Failed to delete user");
    }
  };

  const handleLogout = async () => {
    await logout(getToken() ?? "");
    router.replace("/login");
  };

  const filtered = users.filter(u =>
    u.email.toLowerCase().includes(search.toLowerCase())
  );

  const stats = {
    total: users.length,
    basic: users.filter(u => u.tier === "basic").length,
    pro: users.filter(u => u.tier === "pro").length,
    enterprise: users.filter(u => u.tier === "enterprise").length,
    admins: users.filter(u => u.is_admin).length,
  };

  return (
    <div className="min-h-screen" style={{ background: "#F4F5F7" }}>

      {/* Header */}
      <div className="bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-[#1B2A4A] flex items-center justify-center">
            <Shield className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-[15px] font-semibold text-gray-900">Admin Dashboard</h1>
            <p className="text-[10px] text-gray-400">VelocityAI · User Management</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push("/dashboard")}
            className="text-[11px] font-medium text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
          >
            ← Back to app
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 hover:text-gray-900 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <LogOut className="h-3.5 w-3.5" /> Logout
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-5">

        {/* Stat cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            { label: "Total Users",  value: stats.total,      color: "text-gray-900" },
            { label: "Basic",        value: stats.basic,      color: "text-gray-600" },
            { label: "Pro",          value: stats.pro,        color: "text-[#1B2A4A]" },
            { label: "Enterprise",   value: stats.enterprise, color: "text-gray-900" },
            { label: "Admins",       value: stats.admins,     color: "text-[#1B2A4A]" },
          ].map((s, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className="bg-white rounded-xl border border-gray-100 px-4 py-3.5 shadow-sm"
            >
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">{s.label}</p>
              <p className={`text-[22px] font-bold leading-none ${s.color}`}>{s.value}</p>
            </motion.div>
          ))}
        </div>

        {/* Users table */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm">
          {/* Table header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-gray-400" />
              <span className="text-[13px] font-semibold text-gray-900">Users</span>
              <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">{filtered.length}</span>
            </div>
            <div className="flex items-center gap-2">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search users..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="pl-7 pr-3 py-1.5 text-[11px] border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 bg-gray-50 w-48"
                />
              </div>
              <button
                onClick={() => loadUsers()}
                className="h-7 w-7 flex items-center justify-center rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
              >
                <RefreshCw className="h-3 w-3 text-gray-400" />
              </button>
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1B2A4A] text-white rounded-lg text-[11px] font-semibold hover:bg-[#243860] transition-colors"
              >
                <Plus className="h-3.5 w-3.5" /> Add user
              </button>
            </div>
          </div>

          {/* Table */}
          {loading ? (
            <div className="flex items-center justify-center py-16 gap-2">
              <RefreshCw className="h-4 w-4 animate-spin text-gray-300" />
              <span className="text-[12px] text-gray-400">Loading users...</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2">
              <Users className="h-8 w-8 text-gray-200" />
              <p className="text-[12px] text-gray-400">No users found</p>
            </div>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider px-5 py-2.5">User</th>
                  <th className="text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider px-4 py-2.5">Plan</th>
                  <th className="text-center text-[10px] font-semibold text-gray-400 uppercase tracking-wider px-4 py-2.5">Runs</th>
                  <th className="text-center text-[10px] font-semibold text-gray-400 uppercase tracking-wider px-4 py-2.5">Role</th>
                  <th className="text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider px-4 py-2.5">Joined</th>
                  <th className="text-right text-[10px] font-semibold text-gray-400 uppercase tracking-wider px-5 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((user, i) => (
                  <motion.tr
                    key={user.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.02 }}
                    className="border-t border-gray-50 hover:bg-gray-50/50 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <div className="h-7 w-7 rounded-full bg-[#E8EDF5] flex items-center justify-center flex-shrink-0">
                          <span className="text-[10px] font-bold text-[#1B2A4A]">
                            {user.email[0].toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <p className="text-[12px] font-medium text-gray-900">{user.email}</p>
                          <p className="text-[9px] text-gray-400 font-mono">{user.id.slice(0, 8)}…</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <TierDropdown
                        userId={user.id}
                        currentTier={user.tier}
                        onUpdate={handleUpdateTier}
                      />
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      <span className="text-[12px] font-semibold text-gray-700">{user.workflow_run_count}</span>
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      {user.is_admin ? (
                        <span className="inline-flex items-center gap-1 text-[9px] font-bold text-[#1B2A4A] bg-[#E8EDF5] border border-[#1B2A4A]/20 px-1.5 py-0.5 rounded-full uppercase">
                          <Shield className="h-2.5 w-2.5" /> Admin
                        </span>
                      ) : (
                        <span className="text-[10px] text-gray-400">User</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-[11px] text-gray-400">
                        {new Date(user.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {!user.is_admin && (
                        <button
                          onClick={() => setDeleteConfirm(user.id)}
                          className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-red-50 hover:text-red-500 text-gray-300 transition-colors ml-auto"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Create user modal */}
      <AnimatePresence>
        {showCreate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/30 backdrop-blur-sm"
              onClick={() => setShowCreate(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.15 }}
              className="relative bg-white rounded-2xl border border-gray-100 shadow-2xl w-full max-w-md p-6"
            >
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-[14px] font-semibold text-gray-900">Create New User</h3>
                <button onClick={() => setShowCreate(false)} className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-gray-100 transition-colors">
                  <X className="h-4 w-4 text-gray-400" />
                </button>
              </div>
              <div className="space-y-3.5">
                <div>
                  <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 block">Email</label>
                  <input type="email" value={newEmail} onChange={e => setNewEmail(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] focus:outline-none focus:border-gray-400"
                    placeholder="user@example.com" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 block">Password</label>
                  <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] focus:outline-none focus:border-gray-400"
                    placeholder="At least 8 characters" />
                </div>
                <div>
                  <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 block">Plan</label>
                  <select value={newTier} onChange={e => setNewTier(e.target.value as Tier)}
                    className="w-full rounded-lg border border-gray-200 px-3 py-2.5 text-[13px] focus:outline-none focus:border-gray-400 bg-white">
                    {TIER_ORDER.map(t => (
                      <option key={t} value={t}>{TIER_LABELS[t]}</option>
                    ))}
                  </select>
                </div>
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={newIsAdmin} onChange={e => setNewIsAdmin(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-[#1B2A4A] focus:ring-[#1B2A4A]" />
                  <span className="text-[12px] text-gray-700">Grant admin access</span>
                </label>
                <button
                  onClick={handleCreateUser}
                  disabled={creating || !newEmail || !newPassword}
                  className="w-full bg-[#1B2A4A] text-white rounded-xl py-2.5 text-[13px] font-semibold hover:bg-[#243860] disabled:opacity-40 disabled:cursor-not-allowed transition-colors mt-1"
                >
                  {creating ? "Creating..." : "Create User"}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Delete confirm modal */}
      <AnimatePresence>
        {deleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-black/30 backdrop-blur-sm"
              onClick={() => setDeleteConfirm(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              className="relative bg-white rounded-2xl border border-gray-100 shadow-2xl w-full max-w-sm p-6 text-center"
            >
              <div className="h-10 w-10 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-3">
                <Trash2 className="h-5 w-5 text-red-500" />
              </div>
              <h3 className="text-[14px] font-semibold text-gray-900 mb-1">Delete user?</h3>
              <p className="text-[12px] text-gray-400 mb-5">This will permanently delete the user and all their data. This cannot be undone.</p>
              <div className="flex gap-2">
                <button onClick={() => setDeleteConfirm(null)}
                  className="flex-1 py-2.5 rounded-xl border border-gray-200 text-[12px] font-medium text-gray-700 hover:bg-gray-50 transition-colors">
                  Cancel
                </button>
                <button onClick={() => handleDeleteUser(deleteConfirm)}
                  className="flex-1 py-2.5 rounded-xl bg-red-500 text-white text-[12px] font-semibold hover:bg-red-600 transition-colors">
                  Delete
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.97 }}
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-lg text-[12px] font-medium ${
              toast.type === "success"
                ? "bg-white border border-gray-200 text-gray-800"
                : "bg-red-50 border border-red-100 text-red-700"
            }`}
          >
            {toast.type === "success"
              ? <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
              : <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />}
            {toast.text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
