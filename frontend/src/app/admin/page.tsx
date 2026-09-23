"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  Users, Shield, ChevronDown, Search, Plus, Trash2,
  RefreshCw, CheckCircle2, AlertCircle, X, LogOut, Ban, PlayCircle, Key,
} from "lucide-react";
import {
  ApiError, getToken, getMe, logout,
  adminListUsers, adminUpdateTier, adminCreateUser, adminDeleteUser,
  adminUpdateRole, adminDisableUser, adminEnableUser, adminResetUserPassword,
  onAdminMfaRequired,
} from "@/lib/api";
import type { AdminUser } from "@/lib/api";
import { buildLoginRedirect } from "@/lib/authRedirect";
import { TIER_LABELS } from "@/lib/entitlements";
import { routes } from "@/lib/routes";
import type { Tier } from "@/lib/entitlements";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Pill } from "@/components/ui/Pill";
import { Tabs } from "@/components/ui/Tabs";
import { CapacityMatrix } from "@/components/admin/CapacityMatrix";
import { useCapacityMatrix } from "@/hooks/useCapacityMatrix";

const TIER_ORDER: Tier[] = ["basic", "pro", "enterprise", "hexaware"];

// The Create-User modal is a plain <div>, not a <form>, so the Email input's
// type="email" never fires a native constraint check (ISS-295). Gate on shape
// explicitly instead; the backend's EmailStr on CreateUserRequest is the real
// authority — this only stops the submit before it leaves the page.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; email: string } | null>(null);
  // specs/014 §3.7 — Users | Machines tabs. Users stays the default so the
  // existing landing behavior (and every render test that awaits
  // "alice@example.com" without first switching tabs) is unaffected.
  const [activeTab, setActiveTab] = useState<"users" | "machines">("users");
  const capacityState = useCapacityMatrix(getToken());

  // Create user form -- invitation-only (Cognito migration Phase 3): no
  // password field. Cognito emails a temporary password directly to the new
  // account; this admin panel never sees or sets one.
  const [newEmail, setNewEmail] = useState("");
  const [newTier, setNewTier] = useState<Tier>("basic");
  const [newIsAdmin, setNewIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);

  // ISS-818: Delete and the admin-role toggle had no in-flight guard, so a
  // fast double-click fired two concurrent mutations (the second DELETE 404s
  // once the first lands, flashing a "Failed to delete user" toast on a
  // deletion that actually succeeded). Same shape as `creating` above and
  // TierDropdown's own `loading`. Role is keyed by user id — separate rows
  // are genuinely independent actions and must not block each other.
  const [deleting, setDeleting] = useState(false);
  const [rolePending, setRolePending] = useState<string[]>([]);

  // Every toast on this page shares one dismiss timer. Without cancelling the
  // pending one, an earlier call's 3.5s timeout nulls a NEWER toast that
  // replaced it — e.g. the create-success toast erasing the duplicate-email
  // 409 error toast that follows it within 3.5s (ISS-324/ISS-487).
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((type: "success" | "error", text: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ type, text });
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  }, []);

  // An admin who holds no second factor is refused by `require_admin` on every
  // route this page needs, so there is nothing here worth rendering — send them
  // to the enrolment view the server named instead of leaving them on a page
  // that can only show "Failed to load users".
  //
  // The subscription is on the ApiError seam rather than on any single call:
  // `loadUsers` swallows its error to render that generic message, so a
  // per-call handler would never see the 403 that matters most.
  //
  // `replace`, not `push`: the blocked admin page is not a step worth keeping in
  // history — going Back from enrolment would land on the same 403.
  useEffect(() => {
    return onAdminMfaRequired((detail) => {
      router.replace(
        `/settings/security?enroll=${encodeURIComponent(detail.enroll_path)}`,
      );
    });
  }, [router]);

  // Declared BEFORE the effect that calls it, and memoized, so the effect can
  // list it as a real dependency. Previously it was a plain function declared
  // after the effect: the effect captured it via hoisting, which the React
  // lint rules flag as an access-before-declaration because the effect would
  // keep an outdated reference if the function ever closed over changing state.
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
      setUsers(Array.isArray(data) ? data : []);
    } catch {
      showToast("error", "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    const token = getToken();
    if (!token) { router.replace(buildLoginRedirect()); return; }

    // Verify admin access — a non-admin is sent to the main application, not
    // back through login (they ARE authenticated, just not authorized here).
    getMe(token).then(user => {
      if (!user.is_admin) { router.replace(routes.dashboard()); return; }
      loadUsers(token);
    }).catch((err: unknown) => {
      // FR-015: on a 401 getMe() has ALREADY gone through lib/api.ts's shared
      // handleSessionExpiry() — token cleared, full-page nav to
      // /login?expired=true queued. Racing that with a client-side
      // router.replace() can land the user on a bare /login with no expiry
      // message, so 401 returns here and lets the shared redirect win.
      // Any other failure keeps the plain login bounce — via
      // buildLoginRedirect() so they return to /admin after signing back in.
      if (err instanceof ApiError && err.status === 401) return;
      router.replace(buildLoginRedirect());
    });
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

  const handleUpdateRole = async (userId: string, isAdmin: boolean) => {
    const token = getToken();
    if (!token || rolePending.includes(userId)) return;
    setRolePending(prev => [...prev, userId]);
    try {
      const updated = await adminUpdateRole(token, userId, isAdmin);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_admin: updated.is_admin } : u));
      showToast("success", isAdmin ? "Admin access granted" : "Admin access removed");
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as { code?: string } | string;
        if (typeof detail === "object" && detail.code === "last_admin") {
          showToast("error", "Cannot remove the last administrator.");
          return;
        }
      }
      const msg = err instanceof Error ? err.message : "Failed to update role";
      showToast("error", msg);
    } finally {
      setRolePending(prev => prev.filter(id => id !== userId));
    }
  };

  const handleCreateUser = async () => {
    if (!EMAIL_PATTERN.test(newEmail)) return;
    const token = getToken();
    if (!token) return;
    setCreating(true);
    try {
      const created = await adminCreateUser(token, newEmail, newTier, newIsAdmin);
      setUsers(prev => [created, ...prev]);
      setShowCreate(false);
      setNewEmail(""); setNewTier("basic"); setNewIsAdmin(false);
      showToast("success", `Invited ${created.email}`);
    } catch (err: unknown) {
      showToast("error", err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setCreating(false);
    }
  };

  const handleDisableUser = async (userId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      const updated = await adminDisableUser(token, userId);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: updated.status } : u));
      showToast("success", "User disabled");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to disable user";
      showToast("error", msg);
    }
  };

  const handleEnableUser = async (userId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      const updated = await adminEnableUser(token, userId);
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: updated.status } : u));
      showToast("success", "User re-enabled");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to enable user";
      showToast("error", msg);
    }
  };

  const handleResetPassword = async (userId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      await adminResetUserPassword(token, userId);
      showToast("success", "Temporary password issued; user must change it at next login.");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reset password";
      showToast("error", msg);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    const token = getToken();
    if (!token || deleting) return;
    setDeleting(true);
    try {
      await adminDeleteUser(token, userId);
      setUsers(prev => prev.filter(u => u.id !== userId));
      setDeleteConfirm(null);
      showToast("success", "User removed. Cognito deletion is pending and will be retried automatically.");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          const detail = err.detail as { code?: string } | string;
          if (typeof detail === "object" && detail.code === "last_admin") {
            showToast("error", "Cannot remove the last administrator.");
            return;
          }
        }
        if (err.status === 202) {
          showToast("success", "User removed. Cognito deletion is pending and will be retried automatically.");
          setDeleteConfirm(null);
          return;
        }
      }
      showToast("error", "Failed to delete user");
    } finally {
      setDeleting(false);
    }
  };

  const handleLogout = async () => {
    await logout(getToken() ?? "");
    router.replace(routes.login());
  };

  const filtered = users.filter(u =>
    u.email.toLowerCase().includes(search.toLowerCase())
  );

  const stats = {
    total: users.length,
    basic: users.filter(u => u.tier === "basic").length,
    pro: users.filter(u => u.tier === "pro").length,
    enterprise: users.filter(u => u.tier === "enterprise").length,
    hexaware: users.filter(u => u.tier === "hexaware").length,
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
            onClick={() => router.push(routes.dashboard())}
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

        <Tabs
          tabs={[
            { id: "users", label: "Users" },
            { id: "machines", label: "Machines" },
          ]}
          active={activeTab}
          onChange={(id) => setActiveTab(id as "users" | "machines")}
        />

        {activeTab === "machines" ? (
          <CapacityMatrix state={capacityState} />
        ) : (
        <>
        {/* Stat cards */}
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          {[
            { label: "Total Users",  value: stats.total,      color: "text-ink-900" },
            { label: "Basic",        value: stats.basic,      color: "text-ink-500" },
            { label: "Pro",          value: stats.pro,        color: "text-brand" },
            { label: "Enterprise",   value: stats.enterprise, color: "text-ink-900" },
            { label: "Hexaware",     value: stats.hexaware,   color: "text-ink-900" },
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
                  <th className="text-center text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">Status</th>
                  <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-4 py-2.5">Joined</th>
                  <th className="text-right text-[10px] font-semibold text-ink-400 uppercase tracking-wider px-5 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((user, i) => {
                  const isDisabled = user.status === "disabled";
                  return (
                  <motion.tr
                    key={user.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.02 }}
                    className={`border-t border-line-divider hover:bg-surface-warm transition-colors ${isDisabled ? "opacity-60" : ""}`}
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <div className="h-7 w-7 rounded-full bg-brand-fill flex items-center justify-center flex-shrink-0">
                          {/* ISS-405: user.email[0] throws TypeError when email is an empty
                              string (e.g. persisted via a direct API POST that bypasses the
                              client's presence check). Guard with || '?' so the avatar still
                              renders rather than crashing the whole /admin table. */}
                          <span className="text-[10px] font-bold text-brand">
                            {(user.email || "?")[0].toUpperCase()}
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
                      <button
                        onClick={() => handleUpdateRole(user.id, !user.is_admin)}
                        disabled={rolePending.includes(user.id)}
                        aria-label={user.is_admin ? `Remove admin access from ${user.email}` : `Grant admin access to ${user.email}`}
                        className="inline-flex items-center"
                        title={user.is_admin ? "Click to remove admin access" : "Click to grant admin access"}
                      >
                        {user.is_admin ? (
                          <Pill className="!bg-brand-fill !border-brand-border !text-brand text-[9px] font-bold uppercase px-1.5 py-0.5">
                            <Shield className="h-2.5 w-2.5" /> Admin
                          </Pill>
                        ) : (
                          <span className="text-[10px] text-ink-400 hover:text-ink-700 hover:underline">User</span>
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      {isDisabled ? (
                        <Pill className="!bg-[var(--status-failed-fill)] !border-[var(--status-failed-border)] !text-status-failed text-[9px] font-bold uppercase px-1.5 py-0.5">
                          Disabled
                        </Pill>
                      ) : (
                        <Pill className="text-[9px] font-bold uppercase px-1.5 py-0.5">
                          Active
                        </Pill>
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-[11px] text-ink-400">
                        {new Date(user.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleResetPassword(user.id)}
                          aria-label={`Reset password for ${user.email}`}
                          title="Issue temporary password"
                          className="h-7 w-7 flex items-center justify-center rounded-[var(--radius-button)] text-ink-400 hover:text-brand hover:bg-brand-fill transition-colors"
                        >
                          <Key className="h-3.5 w-3.5" />
                        </button>
                        {isDisabled ? (
                          <button
                            onClick={() => handleEnableUser(user.id)}
                            aria-label={`Enable ${user.email}`}
                            title="Re-enable this account"
                            className="h-7 w-7 flex items-center justify-center rounded-[var(--radius-button)] text-ink-400 hover:text-status-done hover:bg-[var(--status-done-fill)] transition-colors"
                          >
                            <PlayCircle className="h-3.5 w-3.5" />
                          </button>
                        ) : (
                          <button
                            onClick={() => handleDisableUser(user.id)}
                            aria-label={`Disable ${user.email}`}
                            title="Disable this account (reversible)"
                            className="h-7 w-7 flex items-center justify-center rounded-[var(--radius-button)] text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-colors"
                          >
                            <Ban className="h-3.5 w-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => setDeleteConfirm({ id: user.id, email: user.email })}
                          aria-label={`Delete ${user.email}`}
                          title="Permanently delete this account"
                          className="h-7 w-7 flex items-center justify-center rounded-[var(--radius-button)] text-ink-400 hover:text-status-failed hover:bg-[var(--status-failed-fill)] transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </motion.tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
        </>
        )}
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
                {/* Invitation-only creation (Cognito migration Phase 3, Decision
                    6): there is no password field. A temporary password is
                    generated and emailed directly to the new account -- this
                    admin panel never sees or sets it. */}
                <p className="text-[11px] text-ink-500 leading-relaxed bg-surface-warm rounded-[var(--radius-button)] px-3 py-2.5">
                  This creates an invitation. The new user receives a temporary
                  password by email and sets their own password on first sign-in.
                </p>
                <Button
                  onClick={handleCreateUser}
                  disabled={creating || !EMAIL_PATTERN.test(newEmail)}
                  className="w-full mt-1"
                >
                  {creating ? "Sending invite..." : "Send Invitation"}
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
              {/* ISS-415: show the email so the admin can confirm they are
                  deleting the right account. deleteConfirm now carries {id, email}
                  instead of just the id string. */}
              <p className="text-[11px] font-medium text-ink-700 mb-1 truncate px-2">{deleteConfirm.email || "(no email)"}</p>
              <p className="text-[12px] text-ink-500 mb-5">
                This will permanently delete the user and all their data. This cannot be undone.
                The account is disabled immediately; if the identity-provider cleanup can&apos;t
                complete right away it finishes automatically in the background.
              </p>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setDeleteConfirm(null)} className="flex-1">
                  Cancel
                </Button>
                <button onClick={() => handleDeleteUser(deleteConfirm.id)}
                  disabled={deleting}
                  className="flex-1 py-2.5 rounded-[var(--radius-button)] bg-status-failed text-white text-[12.5px] font-semibold font-sans hover:opacity-90 transition-opacity disabled:cursor-not-allowed disabled:opacity-60">
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
