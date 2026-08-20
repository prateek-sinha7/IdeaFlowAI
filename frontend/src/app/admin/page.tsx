"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
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
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";

const TIER_ORDER: Tier[] = ["basic", "pro", "enterprise", "hexaware"];

// Tier -> Badge status key (token-backed chip): basic=neutral grey, pro=brand
// violet, enterprise=green. The tier LABEL is passed explicitly so the chip
// reads "Basic/Pro/Enterprise" while its color routes through the shared
// status-ramp tokens (no per-page palette fork, D-15).
const TIER_BADGE_STATUS: Record<string, string> = {
  basic: "queued",
  pro: "running",
  enterprise: "done",
  hexaware: "amber",
};

function TierBadge({ tier }: { tier: string }) {
  return (
    <Badge
      status={TIER_BADGE_STATUS[tier] ?? "queued"}
      label={TIER_LABELS[tier as Tier] ?? tier}
    />
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
    <div
      className="relative inline-block"
      onKeyDown={(e) => { if (e.key === "Escape" && open) { e.stopPropagation(); setOpen(false); } }}
    >
      <button
        onClick={() => setOpen(!open)}
        disabled={loading}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius-button)] border border-line-control bg-surface-white hover:bg-surface-warm transition-colors text-[11px] font-medium text-ink-700 disabled:opacity-50"
      >
        {loading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <TierBadge tier={localTier} />}
        <ChevronDown className="h-3 w-3 text-ink-400" />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              role="menu"
              initial={{ opacity: 0, y: -4, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.97 }}
              transition={{ duration: 0.1 }}
              className="absolute left-0 top-full mt-1 z-50 bg-surface-card rounded-[var(--radius-menu)] border border-line-border shadow-[var(--elevation-menu)] overflow-hidden min-w-[140px]"
            >
              {TIER_ORDER.map(tier => (
                <button
                  key={tier}
                  role="menuitem"
                  onClick={(e) => { e.stopPropagation(); handleSelect(tier); }}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 text-left text-[12px] hover:bg-surface-warm transition-colors ${tier === localTier ? "bg-surface-warm" : ""}`}
                >
                  <TierBadge tier={tier} />
                  {tier === localTier && <CheckCircle2 className="h-3 w-3 text-brand ml-auto" />}
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

  // Declared BEFORE the boot effect that calls it, and memoized, so the effect
  // can list it as a dependency. Referencing it earlier in the file relied on
  // function-scope hoisting, which pins the effect to whichever closure existed
  // on the first render and never updates it (react-hooks/immutability).
  const loadUsers = useCallback(async (token?: string) => {
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
  }, [showToast]);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace("/login"); return; }

    // Verify admin access
    getMe(token).then(user => {
      if (!user.is_admin) { router.replace("/dashboard"); return; }
      loadUsers(token);
    }).catch(() => router.replace("/login"));
  }, [router, loadUsers]);

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
    <div className="min-h-screen bg-surface-paper">

      {/* Header — near-black shell bar (mirrors the 35-01 dark shell idiom) */}
      <div className="bg-surface-near-black border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-[var(--radius-button)] bg-brand flex items-center justify-center">
            <Shield className="h-4 w-4 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[15px] font-semibold text-white font-sans">Admin Dashboard</h1>
              <Pill className="!bg-white/10 !border-white/15 !text-white uppercase tracking-wide text-[9px] font-semibold px-2 py-0.5">
                Admin
              </Pill>
            </div>
            <p className="text-[10px] text-white/50 font-sans">VelocityAI · User Management</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push("/dashboard")}
            className="text-[11px] font-medium text-white/70 hover:text-white px-3 py-1.5 rounded-[var(--radius-button)] hover:bg-white/10 transition-colors font-sans"
          >
            ← Back to app
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-[11px] font-medium text-white/70 hover:text-white px-3 py-1.5 rounded-[var(--radius-button)] hover:bg-white/10 transition-colors font-sans"
          >
            <LogOut className="h-3.5 w-3.5" /> Logout
          </button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-5">

        {/* Stat cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            { label: "Total Users",  value: stats.total,      color: "text-ink-900" },
            { label: "Basic",        value: stats.basic,      color: "text-ink-500" },
            { label: "Pro",          value: stats.pro,        color: "text-brand" },
            { label: "Enterprise",   value: stats.enterprise, color: "text-ink-900" },
            { label: "Admins",       value: stats.admins,     color: "text-brand" },
          ].map((s, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <Card className="px-4 py-3.5 shadow-sm">
                <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wider mb-1">{s.label}</p>
                <p className={`text-[22px] font-bold leading-none ${s.color}`}>{s.value}</p>
              </Card>
            </motion.div>
          ))}
        </div>

        {/* Users table */}
        <Card className="shadow-sm">{/* No overflow-hidden — TierDropdown needs to overflow the table */}
          {/* Table header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-line-divider">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-ink-400" />
              <span className="text-[13px] font-semibold text-ink-900">Users</span>
              <Pill className="text-[10px] px-1.5 py-0.5">{filtered.length}</Pill>
            </div>
            <div className="flex items-center gap-2">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-ink-400" />
                <input
                  type="text"
                  aria-label="Search users"
                  name="admin-user-search"
                  placeholder="Search users..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="pl-7 pr-3 py-1.5 text-[11px] border border-line-control rounded-[var(--radius-button)] focus:outline-none focus:border-ink-400 bg-surface-warm w-48"
                />
              </div>
              <button
                onClick={() => loadUsers()}
                className="h-7 w-7 flex items-center justify-center rounded-[var(--radius-button)] border border-line-control hover:bg-surface-warm transition-colors"
              >
                <RefreshCw className="h-3 w-3 text-ink-400" />
              </button>
              <Button onClick={() => setShowCreate(true)} size="sm" className="!text-[11px]">
                <Plus className="h-3.5 w-3.5" /> Add user
              </Button>
            </div>
          </div>

          {/* Table */}
          {loading ? (
            <div className="flex items-center justify-center py-16 gap-2">
              <RefreshCw className="h-4 w-4 animate-spin text-ink-400" />
              <span className="text-[12px] text-ink-400">Loading users...</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 gap-2">
              <Users className="h-8 w-8 text-ink-400/50" />
              <p className="text-[12px] text-ink-400">No users found</p>
            </div>
          ) : (
            <table className="w-full">
              <thead className="bg-surface-warm">
                <tr>
                  <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-5 py-2.5">User</th>
                  <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">Plan</th>
                  <th className="text-center text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">Runs</th>
                  <th className="text-center text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">Role</th>
                  <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">Joined</th>
                  <th className="text-right text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-5 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((user, i) => (
                  <motion.tr
                    key={user.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.02 }}
                    className="border-t border-line-divider hover:bg-surface-warm transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <div className="h-7 w-7 rounded-full bg-brand-fill flex items-center justify-center flex-shrink-0">
                          <span className="text-[10px] font-bold text-brand">
                            {user.email[0].toUpperCase()}
                          </span>
                        </div>
                        <div>
                          <p className="text-[12px] font-medium text-ink-900">{user.email}</p>
                          <p className="text-[9px] text-ink-400 font-mono">{user.id.slice(0, 8)}…</p>
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
                      <span className="text-[12px] font-semibold text-ink-700">{user.workflow_run_count}</span>
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      {user.is_admin ? (
                        <Pill className="!bg-brand-fill !border-brand-border !text-brand text-[9px] font-bold uppercase px-1.5 py-0.5">
                          <Shield className="h-2.5 w-2.5" /> Admin
                        </Pill>
                      ) : (
                        <span className="text-[10px] text-ink-400">User</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-[11px] text-ink-400">
                        {new Date(user.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {!user.is_admin && (
                        <button
                          onClick={() => setDeleteConfirm(user.id)}
                          aria-label={`Delete ${user.email}`}
                          className="h-7 w-7 flex items-center justify-center rounded-[var(--radius-button)] text-ink-400 hover:text-status-failed hover:bg-[var(--status-failed-fill)] transition-colors ml-auto"
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
        </Card>
      </div>

      {/* Create user modal */}
      <AnimatePresence>
        {showCreate && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-[var(--scrim)] backdrop-blur-sm"
              onClick={() => setShowCreate(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.15 }}
              className="relative bg-surface-card border border-line-border rounded-[var(--radius-card)] shadow-[var(--elevation-modal)] w-full max-w-md p-6"
            >
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-[14px] font-semibold text-ink-900 font-sans">Create New User</h3>
                <button onClick={() => setShowCreate(false)} className="h-7 w-7 flex items-center justify-center rounded-[var(--radius-button)] hover:bg-surface-warm transition-colors">
                  <X className="h-4 w-4 text-ink-400" />
                </button>
              </div>
              <div className="space-y-3.5">
                <div>
                  <label htmlFor="new-user-email" className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5 block">Email</label>
                  <input id="new-user-email" type="email" value={newEmail} onChange={e => setNewEmail(e.target.value)}
                    className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-white px-3 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-ink-400"
                    placeholder="user@example.com" />
                </div>
                <div>
                  <label htmlFor="new-user-password" className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5 block">Password</label>
                  <input id="new-user-password" type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
                    className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-white px-3 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-ink-400"
                    placeholder="At least 8 characters" />
                </div>
                <div>
                  <label htmlFor="new-user-tier" className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5 block">Plan</label>
                  <select id="new-user-tier" value={newTier} onChange={e => setNewTier(e.target.value as Tier)}
                    aria-label="Select plan tier"
                    name="new-user-tier"
                    className="w-full rounded-[var(--radius-button)] border border-line-control px-3 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-ink-400 bg-surface-white">
                    {TIER_ORDER.map(t => (
                      <option key={t} value={t}>{TIER_LABELS[t]}</option>
                    ))}
                  </select>
                </div>
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input type="checkbox" name="new-user-is-admin" checked={newIsAdmin} onChange={e => setNewIsAdmin(e.target.checked)}
                    className="h-4 w-4 rounded border-line-control accent-brand focus:ring-brand" />
                  <span className="text-[12px] text-ink-700">Grant admin access</span>
                </label>
                <Button
                  onClick={handleCreateUser}
                  disabled={creating || !newEmail || !newPassword}
                  className="w-full mt-1"
                >
                  {creating ? "Creating..." : "Create User"}
                </Button>
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
              className="absolute inset-0 bg-[var(--scrim)] backdrop-blur-sm"
              onClick={() => setDeleteConfirm(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              className="relative bg-surface-card border border-line-border rounded-[var(--radius-card)] shadow-[var(--elevation-modal)] w-full max-w-sm p-6 text-center"
            >
              <div className="h-10 w-10 rounded-full bg-[var(--status-failed-fill)] flex items-center justify-center mx-auto mb-3">
                <Trash2 className="h-5 w-5 text-status-failed" />
              </div>
              <h3 className="text-[14px] font-semibold text-ink-900 mb-1 font-sans">Delete user?</h3>
              <p className="text-[12px] text-ink-500 mb-5">This will permanently delete the user and all their data. This cannot be undone.</p>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setDeleteConfirm(null)} className="flex-1">
                  Cancel
                </Button>
                <button onClick={() => handleDeleteUser(deleteConfirm)}
                  className="flex-1 py-2.5 rounded-[var(--radius-button)] bg-status-failed text-white text-[12.5px] font-semibold font-sans hover:opacity-90 transition-opacity">
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
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-[var(--radius-button)] shadow-[var(--elevation-menu)] text-[12px] font-medium ${
              toast.type === "success"
                ? "bg-surface-card border border-line-border text-ink-900"
                : "bg-[var(--status-failed-fill)] border border-[var(--status-failed-border)] text-status-failed"
            }`}
          >
            {toast.type === "success"
              ? <CheckCircle2 className="h-4 w-4 text-status-done flex-shrink-0" />
              : <AlertCircle className="h-4 w-4 text-status-failed flex-shrink-0" />}
            {toast.text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
