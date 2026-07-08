"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  ArrowLeft, Mail, Lock, Eye, EyeOff, CheckCircle2, AlertCircle,
  User, Zap, Check, Shield, Cpu, FileText, Save, Trash2,
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

// ─── Tier definitions ─────────────────────────────────────────────────────────
const TIER_ORDER: Tier[] = ["basic", "pro", "enterprise"];

// Tier one-liners for the plan progress bar (the styling now routes through the
// Phase-32 token layer — no per-tier palette fork).
const TIER_DESCRIPTION: Record<Tier, string> = {
  basic: "Core pipelines for individuals getting started",
  pro: "Full pipeline access for power users and teams",
  enterprise: "Unlimited access with all workflows and migrations",
};

// Pipeline display names
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

// Unique base pipelines per tier (no revision variants)
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

  // Limits tab state
  const [selectedTierTab, setSelectedTierTab] = useState<Tier>("basic");

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
        setSelectedTierTab(t);
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

  const SECTION_TABS: TabItem[] = [
    { id: "profile", label: "Profile", icon: <User className="h-3.5 w-3.5" /> },
    { id: "model", label: "AI Model", icon: <Cpu className="h-3.5 w-3.5" /> },
    { id: "limits", label: "Limits", icon: <Zap className="h-3.5 w-3.5" /> },
    { id: "constitution", label: "Constitution", icon: <FileText className="h-3.5 w-3.5" /> },
  ];

  // Token-driven feedback banner (success -> done ramp, error -> failed ramp).
  const banner = (type: "success" | "error") =>
    type === "success"
      ? "text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]"
      : "text-status-failed bg-[var(--status-failed-fill)] border-[var(--status-failed-border)]";

  return (
    <div className="h-full flex flex-col bg-surface-paper">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-line-divider bg-surface-white flex-shrink-0">
        <button onClick={onBack} className="flex items-center justify-center h-8 w-8 rounded-[var(--radius-button)] hover:bg-surface-warm transition-colors">
          <ArrowLeft className="h-4 w-4 text-ink-500" />
        </button>
        <div>
          <h1 className="text-[18px] font-semibold text-ink-900 leading-tight font-sans">Account Settings</h1>
          <p className="text-[11px] text-ink-400 mt-0.5">Manage your profile, security and plan limits</p>
        </div>
      </div>

      {/* Section tabs */}
      <div className="px-6 pt-3 bg-surface-white border-b border-line-divider flex-shrink-0">
        <Tabs
          tabs={SECTION_TABS}
          active={section}
          onChange={id => setSection(id as SettingsSection)}
        />
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <AnimatePresence mode="wait">

          {/* ── PROFILE ── */}
          {section === "profile" && (
            <motion.div
              key="profile"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="px-8 py-7 max-w-lg"
            >
              <h2 className="text-[15px] font-semibold text-ink-900 mb-5 font-sans">Profile</h2>

              {/* Email */}
              <Card className="p-5 mb-4 shadow-[var(--elevation-raised)]">
                <div className="flex items-center gap-2 mb-3">
                  <Mail className="h-3.5 w-3.5 text-ink-400" />
                  <span className="text-[11px] font-semibold text-ink-500 uppercase tracking-wider">Email Address</span>
                </div>
                {loading ? (
                  <div className="h-10 rounded-[var(--radius-button)] bg-surface-warm animate-pulse" />
                ) : (
                  <div className="flex items-center gap-3 rounded-[var(--radius-button)] border border-line-divider bg-surface-warm px-4 py-2.5">
                    <span className="text-[13px] text-ink-700">{email}</span>
                  </div>
                )}
              </Card>

              {/* Change Password */}
              <Card className="p-5 shadow-[var(--elevation-raised)]">
                <div className="flex items-center gap-2 mb-4">
                  <Lock className="h-3.5 w-3.5 text-ink-400" />
                  <span className="text-[11px] font-semibold text-ink-500 uppercase tracking-wider">Change Password</span>
                </div>
                <div className="space-y-3.5">
                  <div>
                    <label className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5 block">Current Password</label>
                    <div className="relative">
                      <input type={showCurrent ? "text" : "password"} value={currentPassword}
                        onChange={e => setCurrentPassword(e.target.value)}
                        className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-white px-4 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-brand transition-colors pr-10"
                        placeholder="Enter current password" />
                      <button type="button" onClick={() => setShowCurrent(!showCurrent)} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700">
                        {showCurrent ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5 block">New Password</label>
                    <div className="relative">
                      <input type={showNew ? "text" : "password"} value={newPassword}
                        onChange={e => setNewPassword(e.target.value)}
                        className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-white px-4 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-brand transition-colors pr-10"
                        placeholder="At least 8 characters" />
                      <button type="button" onClick={() => setShowNew(!showNew)} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700">
                        {showNew ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5 block">Confirm New Password</label>
                    <input type="password" value={confirmPassword}
                      onChange={e => setConfirmPassword(e.target.value)}
                      className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-white px-4 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-brand transition-colors"
                      placeholder="Re-enter new password" />
                  </div>
                  {message && (
                    <div className={`flex items-center gap-2 rounded-[var(--radius-button)] border px-3 py-2.5 text-[12px] ${banner(message.type)}`}>
                      {message.type === "success" ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" /> : <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />}
                      {message.text}
                    </div>
                  )}
                  <Button
                    variant="primary"
                    onClick={handleChangePassword}
                    disabled={changing || !currentPassword || !newPassword || !confirmPassword}
                    className="w-full py-2.5 mt-1"
                  >
                    {changing ? "Changing..." : "Change Password"}
                  </Button>
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
              className="px-8 py-7 max-w-lg"
            >
              <h2 className="text-[15px] font-semibold text-ink-900 mb-1 font-sans">AI Model</h2>
              <p className="text-[11px] text-ink-400 mb-5">
                Choose the Claude model used for all your pipeline runs.
              </p>

              <Card className="p-5 shadow-[var(--elevation-raised)]">
                <div className="flex items-center gap-2 mb-4">
                  <Cpu className="h-3.5 w-3.5 text-ink-400" />
                  <span className="text-[11px] font-semibold text-ink-500 uppercase tracking-wider">Pipeline Model</span>
                </div>

                {loading ? (
                  <div className="h-10 rounded-[var(--radius-button)] bg-surface-warm animate-pulse" />
                ) : (
                  <div className="space-y-4">
                    {/* Dropdown */}
                    <div>
                      <label className="text-[10px] font-semibold text-ink-400 uppercase tracking-wide mb-1.5 block">
                        Select Model
                      </label>
                      <select
                        value={pendingModel ?? ""}
                        onChange={e => {
                          setPendingModel(e.target.value === "" ? null : e.target.value);
                          setModelMessage(null);
                        }}
                        className="w-full rounded-[var(--radius-button)] border border-line-control bg-surface-white px-4 py-2.5 text-[13px] text-ink-900 focus:outline-none focus:border-brand transition-colors appearance-none"
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

                    {/* Current saved value */}
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

                    {/* Save button */}
                    <Button
                      variant="primary"
                      onClick={() => handleSaveModel(pendingModel)}
                      disabled={savingModel || selectedModel === pendingModel}
                      className="w-full py-2.5"
                    >
                      {savingModel ? "Saving…" : "Save"}
                    </Button>
                  </div>
                )}
              </Card>
            </motion.div>
          )}

          {/* ── LIMITS ── */}
          {section === "limits" && (
            <motion.div
              key="limits"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="px-8 py-7 max-w-3xl"
            >
              {/* Section header */}
              <div className="flex items-start justify-between mb-1">
                <div>
                  <div className="flex items-center gap-2.5 mb-1">
                    <h2 className="text-[15px] font-semibold text-ink-900 font-sans">Plan &amp; Limits</h2>
                    <Badge status="running" label={TIER_LABELS[userTier]} />
                  </div>
                  <p className="text-[11px] text-ink-400">
                    Your plan determines which pipelines you can run and what features are available.
                  </p>
                </div>
                <Button variant="secondary" size="sm" className="flex-shrink-0">
                  Upgrade plan
                </Button>
              </div>

              {/* Tier progress bar */}
              <div className="mt-5 mb-6">
                <div className="flex items-center gap-0 rounded-[var(--radius-card)] overflow-hidden border border-line-control bg-surface-card">
                  {TIER_ORDER.map((tier, idx) => {
                    const tierIdx = TIER_ORDER.indexOf(userTier);
                    const isPast = idx < tierIdx;
                    const isCurrent = tier === userTier;
                    return (
                      <div
                        key={tier}
                        className={`flex-1 px-4 py-3 border-r last:border-r-0 border-line-control transition-colors ${
                          isCurrent ? "bg-brand" : isPast ? "bg-brand-fill" : "bg-surface-card"
                        }`}
                      >
                        <p className={`text-[11px] font-bold uppercase tracking-wider ${
                          isCurrent ? "text-white" : isPast ? "text-brand" : "text-ink-400"
                        }`}>
                          {TIER_LABELS[tier]}
                          {isCurrent && <span className="ml-1.5 text-[9px] font-semibold opacity-70">(current)</span>}
                        </p>
                        <p className={`text-[10px] mt-0.5 ${
                          isCurrent ? "text-white/70" : isPast ? "text-brand/60" : "text-ink-400"
                        }`}>
                          {TIER_DESCRIPTION[tier]}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Tier tabs — pipeline details */}
              <Card className="shadow-[var(--elevation-raised)] overflow-hidden mb-5">
                {/* Tab bar */}
                <div className="flex items-center border-b border-line-divider px-4 pt-3 gap-4">
                  {TIER_ORDER.map(tier => {
                    const isCurrent = tier === userTier;
                    const isSelected = tier === selectedTierTab;
                    return (
                      <button
                        key={tier}
                        onClick={() => setSelectedTierTab(tier)}
                        className={`-mb-px inline-flex items-center gap-1.5 border-b-2 pb-2 pt-1 text-[11px] font-semibold transition-colors ${
                          isSelected
                            ? "border-brand text-ink-900"
                            : "border-transparent text-ink-400 hover:text-ink-700"
                        }`}
                      >
                        {TIER_LABELS[tier]}
                        {isCurrent && <Badge status="running" label="current" />}
                      </button>
                    );
                  })}
                </div>

                {/* Pipeline table */}
                <div className="p-4">
                  <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-wider mb-3">
                    Available Pipelines
                  </p>
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-line-divider">
                        <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider pb-2 pr-4">Pipeline</th>
                        <th className="text-left text-[10px] font-semibold text-ink-400 uppercase tracking-wider pb-2 pr-4">Description</th>
                        <th className="text-center text-[10px] font-semibold text-ink-400 uppercase tracking-wider pb-2">Access</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(PIPELINE_DISPLAY).map(([key, info]) => {
                        const hasAccess = TIER_PIPELINES[selectedTierTab].has(key);
                        return (
                          <tr key={key} className="border-b border-line-faint-row last:border-0">
                            <td className="py-2.5 pr-4">
                              <span className={`text-[12px] font-medium ${hasAccess ? "text-ink-900" : "text-ink-400"}`}>
                                {info.label}
                              </span>
                            </td>
                            <td className="py-2.5 pr-4">
                              <span className="text-[11px] text-ink-400">{info.description}</span>
                            </td>
                            <td className="py-2.5 text-center">
                              {hasAccess ? (
                                <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-brand-fill">
                                  <Check className="h-3 w-3 text-brand" />
                                </span>
                              ) : (
                                <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-surface-warm">
                                  <span className="h-1.5 w-1.5 rounded-full bg-ink-300" />
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>

              {/* Usage limits table — like Claude's rate limits table */}
              <Card className="shadow-[var(--elevation-raised)] overflow-hidden mb-5">
                <div className="px-5 py-4 border-b border-line-divider">
                  <p className="text-[13px] font-semibold text-ink-900">Usage Limits</p>
                  <p className="text-[11px] text-ink-400 mt-0.5">
                    Limits apply to the <span className="font-semibold text-brand">{TIER_LABELS[selectedTierTab]}</span> plan
                  </p>
                </div>
                <table className="w-full">
                  <thead className="bg-surface-warm">
                    <tr>
                      <th className="text-left text-[10px] font-semibold text-ink-500 uppercase tracking-wider px-5 py-2.5">Limit</th>
                      <th className="text-center text-[10px] font-semibold text-ink-500 uppercase tracking-wider px-4 py-2.5">Basic</th>
                      <th className="text-center text-[10px] font-semibold text-ink-500 uppercase tracking-wider px-4 py-2.5">Pro</th>
                      <th className="text-center text-[10px] font-semibold text-ink-500 uppercase tracking-wider px-4 py-2.5">Enterprise</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { label: "Pipeline runs / month",    basic: "50",        pro: "500",       enterprise: "Unlimited" },
                      { label: "Concurrent pipelines",     basic: "1",         pro: "3",         enterprise: "10" },
                      { label: "Agents per pipeline",      basic: "Default",   pro: "Default",   enterprise: "Custom" },
                      { label: "Custom workflows",         basic: "—",         pro: "✓",         enterprise: "✓" },
                      { label: "Migration pipelines",      basic: "—",         pro: "—",         enterprise: "✓" },
                      { label: "Analytics dashboard",      basic: "✓",         pro: "✓",         enterprise: "✓" },
                      { label: "Workflow history",         basic: "30 days",   pro: "1 year",    enterprise: "Unlimited" },
                      { label: "Priority queue",           basic: "—",         pro: "✓",         enterprise: "✓" },
                      { label: "Support",                  basic: "Community", pro: "Email",     enterprise: "Dedicated" },
                    ].map((row, i) => (
                      <tr key={i} className="border-t border-line-faint-row">
                        <td className="px-5 py-3 text-[12px] font-medium text-ink-700">{row.label}</td>
                        {(["basic", "pro", "enterprise"] as Tier[]).map(tier => {
                          const val = tier === "basic" ? row.basic : tier === "pro" ? row.pro : row.enterprise;
                          const isCurrentCol = tier === userTier;
                          const isSelectedCol = tier === selectedTierTab;
                          return (
                            <td key={tier} className={`px-4 py-3 text-center text-[12px] transition-colors ${
                              isSelectedCol ? "bg-brand-violet-tint" : ""
                            } ${isCurrentCol ? "font-semibold text-brand" : "text-ink-500"}`}>
                              {val}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              {/* Contact sales banner */}
              <Card className="flex items-center justify-between px-5 py-4 shadow-[var(--elevation-raised)]">
                <div className="flex items-center gap-3">
                  <Shield className="h-4 w-4 text-ink-400 flex-shrink-0" />
                  <div>
                    <p className="text-[12px] font-semibold text-ink-800">Need custom limits?</p>
                    <p className="text-[11px] text-ink-400">Contact us to discuss custom plans for your organisation.</p>
                  </div>
                </div>
                <Button variant="primary" className="flex-shrink-0">
                  Contact sales
                </Button>
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
      className="p-6 space-y-5 max-w-3xl"
    >
      <div className="flex items-center gap-2 mb-1">
        <FileText className="h-3.5 w-3.5 text-ink-400" />
        <span className="text-[11px] font-semibold text-ink-500 uppercase tracking-wider">
          My Constitution
        </span>
      </div>
      <p className="text-[12px] text-ink-500 leading-relaxed">
        Your Constitution is injected into every agent&apos;s system prompt as a governing guardrail.
        Write your principles, constraints, and quality standards here — they apply to all pipelines.
      </p>

      {loading ? (
        <div className="h-40 flex items-center justify-center">
          <div className="h-4 w-4 border-2 border-line-control border-t-brand rounded-full animate-spin" />
        </div>
      ) : (
        <textarea
          value={content}
          onChange={(e) => { setContent(e.target.value); setStatus("idle"); }}
          placeholder={"# My Constitution\n\n## Principle 1 — Quality First\nEvery output must be production-ready…\n\n## Principle 2 — Security\nNever expose secrets or PII…"}
          className="w-full h-64 text-[12px] text-ink-800 bg-surface-warm border border-line-control rounded-[var(--radius-card)] px-4 py-3 resize-none focus:outline-none focus:border-brand transition-colors font-mono leading-relaxed"
        />
      )}

      {status === "saved" && (
        <div className="flex items-center gap-1.5 text-[11px] text-status-done bg-[var(--status-done-fill)] rounded-[var(--radius-button)] px-3 py-2">
          <CheckCircle2 className="h-3.5 w-3.5" /> Constitution saved — active on all future runs.
        </div>
      )}
      {status === "deleted" && (
        <div className="flex items-center gap-1.5 text-[11px] text-ink-500 bg-surface-warm rounded-[var(--radius-button)] px-3 py-2">
          <CheckCircle2 className="h-3.5 w-3.5" /> Constitution cleared.
        </div>
      )}
      {status === "error" && (
        <div className="flex items-center gap-1.5 text-[11px] text-status-failed bg-[var(--status-failed-fill)] rounded-[var(--radius-button)] px-3 py-2">
          <AlertCircle className="h-3.5 w-3.5" /> Failed to save. Please try again.
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={saving || loading || !content.trim()}
          className="py-2"
        >
          <Save className="h-3.5 w-3.5" />
          {saving ? "Saving…" : "Save Constitution"}
        </Button>
        {content && (
          <Button
            variant="secondary"
            onClick={handleDelete}
            disabled={deleting || loading}
            className="py-2"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deleting ? "Clearing…" : "Clear"}
          </Button>
        )}
      </div>
    </motion.div>
  );
}
