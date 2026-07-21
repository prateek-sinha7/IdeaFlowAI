"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  ArrowLeft, Eye, EyeOff, CheckCircle2, AlertCircle, Check, ShieldCheck, Info,
} from "lucide-react";
import { getToken, getMe, changePassword, getPreferences, updatePreferences, getCapabilities } from "@/lib/api";
import type { ModelOption, CapabilityModelEntry } from "@/lib/api";
import { TIER_PIPELINES, TIER_LABELS } from "@/lib/entitlements";
import type { Tier } from "@/lib/entitlements";
import { Tabs, type TabItem } from "@/components/ui/Tabs";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge, type BadgeStatus } from "@/components/ui/Badge";

interface AccountSettingsProps {
  onBack: () => void;
}

type SettingsSection = "profile" | "model" | "limits" | "constitution";

// Pipeline display names — used by the Usage & Limits deliverable-access grid.
const PIPELINE_DISPLAY: Record<string, { label: string; description: string }> = {
  user_stories:           { label: "Product Requirements",     description: "Epics, user stories, Gherkin criteria" },
  ppt:                    { label: "Presentation",             description: "Executive-grade slide decks" },
  prototype:              { label: "Interactive Prototype",    description: "High-fidelity HTML prototypes" },
  app_builder:            { label: "App Builder",              description: "Full-stack code, tests, infrastructure" },
  custom:                 { label: "Custom Workflow",          description: "Compose specialist agent pipelines" },
  migration:              { label: "Platform Workflows",       description: "Mulesoft → AWS, .NET → Azure" },
  mulesoft_to_springboot: { label: "Mulesoft Migration",       description: "Mulesoft to Spring Boot" },
  dotnet_to_azure:        { label: ".NET Migration",           description: ".NET to Azure modernisation" },
};

// Model capability tier -> canonical Badge status key (token-driven chip color).
const MODEL_TIER_BADGE: Record<string, BadgeStatus> = {
  fast: "done",
  balanced: "running",
  powerful: "cancelled",
};

// Unique base pipelines available to a tier (no revision variants) — the real
// deliverable-access entitlement set for the current user's plan (ND-D).
function getBasePipelines(tier: Tier): string[] {
  const all = Array.from(TIER_PIPELINES[tier]);
  return all.filter(p => !p.endsWith("_revision")).filter(p => PIPELINE_DISPLAY[p]);
}

export function AccountSettings({ onBack }: AccountSettingsProps) {
  const [section, setSection] = useState<SettingsSection>("profile");
  const [email, setEmail] = useState("");
  const [userTier, setUserTier] = useState<Tier>("basic");
  const [loading, setLoading] = useState(true);

  // Password change
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [changing, setChanging] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // AI Model preference
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [richModels, setRichModels] = useState<CapabilityModelEntry[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [pendingModel, setPendingModel] = useState<string | null>(null); // dropdown value before save
  const [savingModel, setSavingModel] = useState(false);
  const [modelMessage, setModelMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);

    Promise.all([
      getMe(token),
      getPreferences(token),
      getCapabilities(token).catch(() => null),
    ])
      .then(([user, prefs, palette]) => {
        setEmail(user.email);
        const t = (user.tier as Tier) || "basic";
        setUserTier(t);
        setAvailableModels(prefs.available_models);
        setSelectedModel(prefs.preferred_model);
        setPendingModel(prefs.preferred_model);
        if (palette) setRichModels(palette.model_catalog);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSaveModel = useCallback(async (modelId: string | null) => {
    setModelMessage(null);
    const token = getToken();
    if (!token) return;
    setSavingModel(true);
    try {
      await updatePreferences(token, modelId);
      setSelectedModel(modelId);
      setModelMessage({ type: "success", text: "Model preference saved" });
    } catch (err: unknown) {
      setModelMessage({ type: "error", text: err instanceof Error ? err.message : "Failed to save preference" });
    } finally {
      setSavingModel(false);
    }
  }, []);

  const handleChangePassword = useCallback(async () => {
    setMessage(null);
    if (!currentPassword || !newPassword || !confirmPassword) {
      setMessage({ type: "error", text: "All fields are required" });
      return;
    }
    if (newPassword.length < 8) {
      setMessage({ type: "error", text: "New password must be at least 8 characters" });
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage({ type: "error", text: "New passwords do not match" });
      return;
    }
    const token = getToken();
    if (!token) return;
    setChanging(true);
    try {
      await changePassword(token, currentPassword, newPassword);
      setMessage({ type: "success", text: "Password changed successfully" });
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
    } catch (err: unknown) {
      setMessage({ type: "error", text: err instanceof Error ? err.message : "Failed to change password" });
    } finally {
      setChanging(false);
    }
  }, [currentPassword, newPassword, confirmPassword]);

  // The mock relabels "Limits" → "Usage & Limits" (pure fidelity fix); the
  // internal id + data-testid ("limits" / tab-limits) stay stable. No tab
  // icons — the mock's settings tab row is plain text.
  const SECTION_TABS: TabItem[] = [
    { id: "profile", label: "Profile" },
    { id: "model", label: "AI Model" },
    { id: "limits", label: "Usage & Limits" },
    { id: "constitution", label: "Constitution" },
  ];

  // Token-driven feedback banner (success -> done ramp, error -> failed ramp).
  const banner = (type: "success" | "error") =>
    type === "success"
      ? "text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]"
      : "text-status-failed bg-[var(--status-failed-fill)] border-[var(--status-failed-border)]";

  const inputClass =
    "w-full rounded-[9px] border border-line-control bg-surface-white px-3.5 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-brand transition-colors";

  // Avatar initials derived from the real email (no fabricated name — ND-Y).
  const initials = email ? email.trim().slice(0, 2).toUpperCase() : "";

  return (
    <div className="h-full overflow-y-auto bg-surface-paper">
      <div className="max-w-[880px] mx-auto px-10 pt-7 pb-16">

        {/* Header row — inline back button + light-weight title (mock chrome) */}
        <div className="flex items-center gap-3.5 mb-5">
          <button
            onClick={onBack}
            className="h-9 w-9 flex-none grid place-items-center rounded-[9px] border border-line-border bg-surface-card text-ink-700 hover:border-line-control transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex-1">
            <h1 className="text-[24px] font-light tracking-tight text-ink-900 leading-none font-sans">Account Settings</h1>
            <p className="text-[12.5px] text-ink-400 mt-1.5">Profile, model preference, usage limits and your agent constitution.</p>
          </div>
        </div>

        {/* Section tabs (ND-C purple underline active-state) */}
        <div className="mb-6">
          <Tabs
            tabs={SECTION_TABS}
            active={section}
            onChange={id => setSection(id as SettingsSection)}
          />
        </div>

        <AnimatePresence mode="wait">

          {/* ── PROFILE ── */}
          {section === "profile" && (
            <motion.div
              key="profile"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="pt-1"
            >
              {/* Identity block — avatar initials + real plan (no fabricated
                  name / role / organization / photo — ND-Y). */}
              <div className="flex items-center gap-4 mb-6">
                <div className="h-[60px] w-[60px] flex-none grid place-items-center rounded-full bg-brand text-white font-semibold text-[21px] font-sans">
                  {initials}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[16px] font-semibold text-ink-900 leading-tight">{TIER_LABELS[userTier]} plan</p>
                  <p className="text-[12.5px] text-ink-400 mt-0.5">Signed in to VelocityAI</p>
                </div>
              </div>

              {/* Profile card — real user fields only (email, plan) */}
              <Card className="p-[22px] mb-3.5 shadow-[var(--elevation-raised)]">
                <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.12em] mb-4">Profile</p>
                <div className="grid grid-cols-2 gap-3.5">
                  <div>
                    <p className="text-[11.5px] font-medium text-ink-400 mb-1.5">Email <span className="text-ink-300">· read only</span></p>
                    {loading ? (
                      <div className="h-[42px] rounded-[9px] bg-surface-warm animate-pulse" />
                    ) : (
                      <div className="rounded-[9px] border border-line-divider bg-surface-warm px-3.5 py-3 text-[13px] text-ink-500">{email}</div>
                    )}
                  </div>
                  <div>
                    <p className="text-[11.5px] font-medium text-ink-400 mb-1.5">Plan</p>
                    <div className="rounded-[9px] border border-line-control bg-surface-white px-3.5 py-3 text-[13px] text-ink-700">{TIER_LABELS[userTier]}</div>
                  </div>
                </div>
              </Card>

              {/* Password card — the real change-password flow */}
              <Card className="p-[22px] shadow-[var(--elevation-raised)]">
                <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.12em] mb-4">Password</p>
                <div className="space-y-3.5 max-w-md">
                  <div>
                    <label className="text-[11.5px] font-medium text-ink-400 mb-1.5 block">Current password</label>
                    <div className="relative">
                      <input type={showCurrent ? "text" : "password"} value={currentPassword}
                        onChange={e => setCurrentPassword(e.target.value)}
                        className={`${inputClass} pr-10`}
                        placeholder="Enter current password" />
                      <button type="button" onClick={() => setShowCurrent(!showCurrent)} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700">
                        {showCurrent ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="text-[11.5px] font-medium text-ink-400 mb-1.5 block">New password</label>
                    <div className="relative">
                      <input type={showNew ? "text" : "password"} value={newPassword}
                        onChange={e => setNewPassword(e.target.value)}
                        className={`${inputClass} pr-10`}
                        placeholder="At least 8 characters" />
                      <button type="button" onClick={() => setShowNew(!showNew)} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700">
                        {showNew ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="text-[11.5px] font-medium text-ink-400 mb-1.5 block">Confirm new password</label>
                    <input type="password" value={confirmPassword}
                      onChange={e => setConfirmPassword(e.target.value)}
                      className={inputClass}
                      placeholder="Re-enter new password" />
                  </div>
                  {message && (
                    <div className={`flex items-center gap-2 rounded-[var(--radius-button)] border px-3 py-2.5 text-[12px] ${banner(message.type)}`}>
                      {message.type === "success" ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" /> : <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />}
                      {message.text}
                    </div>
                  )}
                  <div className="flex justify-end pt-1">
                    <Button
                      variant="primary"
                      onClick={handleChangePassword}
                      disabled={changing || !currentPassword || !newPassword || !confirmPassword}
                      className="px-5 py-2.5"
                    >
                      {changing ? "Changing..." : "Change Password"}
                    </Button>
                  </div>
                </div>
              </Card>
            </motion.div>
          )}

          {/* ── AI MODEL ── */}
          {section === "model" && (
            <motion.div
              key="model"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="pt-1"
            >
              <p className="text-[13px] text-ink-500 leading-relaxed mb-4 max-w-2xl">
                The default reasoning model applied across all your runs. Individual agents can still override this in the workflow composer.
              </p>

              <Card className="p-[22px] shadow-[var(--elevation-raised)]">
                <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.12em] mb-4">Pipeline model</p>

                {loading ? (
                  <div className="h-10 rounded-[9px] bg-surface-warm animate-pulse" />
                ) : (
                  <div className="space-y-4 max-w-md">
                    {/* Live model selector (ND-D — never the mock's fixed list). */}
                    <div>
                      <label className="text-[11.5px] font-medium text-ink-400 mb-1.5 block">
                        Select model
                      </label>
                      <select
                        value={pendingModel ?? ""}
                        onChange={e => {
                          setPendingModel(e.target.value === "" ? null : e.target.value);
                          setModelMessage(null);
                        }}
                        className={`${inputClass} appearance-none`}
                      >
                        <option value="">System Default (Claude Haiku 4.5)</option>
                        {availableModels.map(m => (
                          <option key={m.id} value={m.id}>{m.name} · {m.tier}</option>
                        ))}
                      </select>
                      {/* Description + tier badge of selected model */}
                      {pendingModel && (() => {
                        const m = availableModels.find(x => x.id === pendingModel);
                        if (!m) return null;
                        const rich = richModels.find(r => r.id === pendingModel);
                        const ctxK = rich
                          ? rich.context_window >= 1_000_000
                            ? `${(rich.context_window / 1_000_000).toFixed(0)}M ctx`
                            : `${Math.round(rich.context_window / 1000)}K ctx`
                          : null;
                        return (
                          <div className="mt-2 flex items-start gap-2">
                            <Badge status={MODEL_TIER_BADGE[m.tier] ?? "queued"} label={m.tier} className="flex-shrink-0 mt-0.5" />
                            {ctxK && (
                              <span className="text-[9px] text-ink-400 flex-shrink-0 mt-0.5">{ctxK}</span>
                            )}
                            <p className="text-[11px] text-ink-400 leading-relaxed">{m.description}</p>
                          </div>
                        );
                      })()}
                      {!pendingModel && (
                        <p className="mt-1.5 text-[11px] text-ink-400">Fastest and most cost-efficient. Great for high-volume tasks.</p>
                      )}
                    </div>

                    {/* Unsaved indicator */}
                    {selectedModel !== pendingModel && (
                      <p className="text-[11px] text-status-amber">
                        Unsaved — currently using{" "}
                        <span className="font-semibold">
                          {selectedModel
                            ? (availableModels.find(m => m.id === selectedModel)?.name ?? selectedModel)
                            : "System Default"}
                        </span>
                      </p>
                    )}

                    {/* Feedback */}
                    {modelMessage && (
                      <div className={`flex items-center gap-2 rounded-[var(--radius-button)] border px-3 py-2.5 text-[12px] ${banner(modelMessage.type)}`}>
                        {modelMessage.type === "success"
                          ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
                          : <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />}
                        {modelMessage.text}
                      </div>
                    )}

                    <div className="flex justify-end">
                      <Button
                        variant="primary"
                        onClick={() => handleSaveModel(pendingModel)}
                        disabled={savingModel || selectedModel === pendingModel}
                        className="px-6 py-2.5"
                      >
                        {savingModel ? "Saving…" : "Save"}
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            </motion.div>
          )}

          {/* ── USAGE & LIMITS ── */}
          {section === "limits" && (
            <motion.div
              key="limits"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="pt-1"
            >
              {/* Plan banner (real tier — ND-D) */}
              <div className="flex items-center gap-3 rounded-[var(--radius-card)] border border-brand/20 bg-brand-violet-tint px-4 py-3.5 mb-4">
                <ShieldCheck className="h-5 w-5 text-brand flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-[13.5px] font-semibold text-ink-900">{TIER_LABELS[userTier]} plan</p>
                  <p className="text-[11.5px] text-ink-500 mt-0.5">Your plan determines which deliverables you can run and the features available to you.</p>
                </div>
                <Button variant="secondary" size="sm" className="flex-shrink-0 px-3.5 py-2 text-brand">
                  Manage plan
                </Button>
              </div>

              {/* Deliverable access — the live entitlement set for this plan (ND-D) */}
              <Card className="p-[22px] shadow-[var(--elevation-raised)]">
                <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.12em] mb-4">Deliverable access</p>
                <div className="grid grid-cols-2 gap-2.5">
                  {getBasePipelines(userTier).map(p => (
                    <div key={p} className="flex items-center gap-2.5 rounded-[9px] border border-line-faint-row bg-surface-white px-3 py-2.5">
                      <CheckCircle2 className="h-4 w-4 text-status-done flex-shrink-0" />
                      <span className="text-[12.5px] font-medium text-ink-800">{PIPELINE_DISPLAY[p].label}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </motion.div>
          )}

          {/* ── CONSTITUTION ── */}
          {section === "constitution" && (
            <ConstitutionSection />
          )}

        </AnimatePresence>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Constitution Section (T074b — FR-012)
// ---------------------------------------------------------------------------

function ConstitutionSection() {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "deleted" | "error">("idle");

  // Load current constitution on mount
  useEffect(() => {
    const token = getToken();
    if (!token) { setLoading(false); return; }
    fetch("/api/settings/constitution", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => { setContent(data.content || ""); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    const token = getToken();
    if (!token || !content.trim()) return;
    setSaving(true);
    setStatus("idle");
    try {
      const r = await fetch("/api/settings/constitution", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: content.trim() }),
      });
      if (r.ok) setStatus("saved");
      else setStatus("error");
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    const token = getToken();
    if (!token) return;
    setDeleting(true);
    setStatus("idle");
    try {
      const r = await fetch("/api/settings/constitution", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (r.ok) { setContent(""); setStatus("deleted"); }
      else setStatus("error");
    } catch {
      setStatus("error");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <motion.div
      key="constitution"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
      className="pt-1"
    >
      {/* Info banner (mock chrome) */}
      <div className="flex items-start gap-3 rounded-[var(--radius-card)] border border-line-faint-row bg-surface-warm px-4 py-3.5 mb-4">
        <Info className="h-4 w-4 text-ink-400 flex-shrink-0 mt-0.5" />
        <p className="text-[12.5px] text-ink-500 leading-relaxed">
          Your constitution is prepended to <span className="font-semibold text-ink-700">every agent</span> on{" "}
          <span className="font-semibold text-ink-700">every run</span>. Use it for standing instructions — tone,
          house rules, tech constraints, things you never want to repeat.
        </p>
      </div>

      {/* Editor card */}
      <Card className="overflow-hidden shadow-[var(--elevation-raised)]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-line-divider">
          <span className="text-[11.5px] font-semibold text-ink-700">Global instructions</span>
          <span className="text-[11px] text-ink-300 tabular-nums">{content.length} / 4000 chars</span>
        </div>
        {loading ? (
          <div className="h-56 flex items-center justify-center">
            <div className="h-4 w-4 border-2 border-line-control border-t-brand rounded-full animate-spin" />
          </div>
        ) : (
          <textarea
            value={content}
            onChange={(e) => { setContent(e.target.value); setStatus("idle"); }}
            placeholder={"# My Constitution\n\n## Principle 1 — Quality First\nEvery output must be production-ready…\n\n## Principle 2 — Security\nNever expose secrets or PII…"}
            className="w-full h-64 text-[13px] text-ink-800 bg-surface-card px-4 py-3.5 resize-none focus:outline-none font-mono leading-relaxed"
          />
        )}
      </Card>

      {status === "saved" && (
        <div className="flex items-center gap-1.5 text-[11px] text-status-done bg-[var(--status-done-fill)] rounded-[var(--radius-button)] px-3 py-2 mt-3">
          <CheckCircle2 className="h-3.5 w-3.5" /> Constitution saved — active on all future runs.
        </div>
      )}
      {status === "deleted" && (
        <div className="flex items-center gap-1.5 text-[11px] text-ink-500 bg-surface-warm rounded-[var(--radius-button)] px-3 py-2 mt-3">
          <CheckCircle2 className="h-3.5 w-3.5" /> Constitution cleared.
        </div>
      )}
      {status === "error" && (
        <div className="flex items-center gap-1.5 text-[11px] text-status-failed bg-[var(--status-failed-fill)] rounded-[var(--radius-button)] px-3 py-2 mt-3">
          <AlertCircle className="h-3.5 w-3.5" /> Failed to save. Please try again.
        </div>
      )}

      <div className="flex items-center justify-end gap-2.5 mt-3.5">
        {content && (
          <Button
            variant="secondary"
            onClick={handleDelete}
            disabled={deleting || loading}
            className="px-4 py-2.5"
          >
            {deleting ? "Clearing…" : "Clear"}
          </Button>
        )}
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={saving || loading || !content.trim()}
          className="px-5 py-2.5"
        >
          {saving ? "Saving…" : "Save constitution"}
        </Button>
      </div>
    </motion.div>
  );
}
