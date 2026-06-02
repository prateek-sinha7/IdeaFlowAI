"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  ArrowLeft, Mail, Lock, Eye, EyeOff, CheckCircle2, AlertCircle,
  User, Zap, Check, Shield, Cpu, FileText, Save, Trash2,
} from "lucide-react";
import { getToken, getMe, changePassword, getPreferences, updatePreferences } from "@/lib/api";
import type { ModelOption } from "@/lib/api";
import { TIER_PIPELINES, TIER_LABELS } from "@/lib/entitlements";
import type { Tier } from "@/lib/entitlements";

interface AccountSettingsProps {
  onBack: () => void;
}

type SettingsSection = "profile" | "model" | "limits" | "constitution";

// ─── Tier definitions ─────────────────────────────────────────────────────────
const TIER_ORDER: Tier[] = ["basic", "pro", "enterprise"];

const TIER_DETAILS: Record<Tier, {
  price: string;
  description: string;
  color: string;
  bgColor: string;
  borderColor: string;
}> = {
  basic: {
    price: "Starter",
    description: "Core pipelines for individuals getting started",
    color: "text-gray-700",
    bgColor: "bg-gray-50",
    borderColor: "border-gray-200",
  },
  pro: {
    price: "Professional",
    description: "Full pipeline access for power users and teams",
    color: "text-[#1B2A4A]",
    bgColor: "bg-[#E8EDF5]",
    borderColor: "border-[#1B2A4A]/20",
  },
  enterprise: {
    price: "Enterprise",
    description: "Unlimited access with all workflows and migrations",
    color: "text-gray-900",
    bgColor: "bg-gray-900",
    borderColor: "border-gray-900",
  },
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
    ])
      .then(([user, prefs]) => {
        setEmail(user.email);
        const t = (user.tier as Tier) || "basic";
        setUserTier(t);
        setSelectedTierTab(t);
        setAvailableModels(prefs.available_models);
        setSelectedModel(prefs.preferred_model);
        setPendingModel(prefs.preferred_model);
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

  const NAV_ITEMS: { id: SettingsSection; label: string; icon: typeof User }[] = [
    { id: "profile", label: "Profile", icon: User },
    { id: "model",   label: "AI Model", icon: Cpu },
    { id: "limits",  label: "Limits",  icon: Zap },
    { id: "constitution", label: "Constitution", icon: FileText },
  ];

  return (
    <div className="h-full flex flex-col" style={{ background: "#f5f5f0" }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-100 bg-white flex-shrink-0">
        <button onClick={onBack} className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-gray-100 transition-colors">
          <ArrowLeft className="h-4 w-4 text-gray-500" />
        </button>
        <div>
          <h1 className="text-[18px] font-normal italic text-gray-900 leading-tight font-serif">Account Settings</h1>
          <p className="text-[11px] text-gray-400 mt-0.5">Manage your profile, security and plan limits</p>
        </div>
      </div>

      {/* Body — sidebar + content */}
      <div className="flex-1 flex min-h-0">

        {/* Sidebar nav */}
        <div className="w-[180px] flex-shrink-0 border-r border-gray-100 bg-white py-4 px-3">
          <nav className="space-y-0.5">
            {NAV_ITEMS.map(item => {
              const Icon = item.icon;
              const active = section === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setSection(item.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[12px] font-medium transition-all text-left ${
                    active
                      ? "bg-[#1B2A4A] text-white"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5 flex-shrink-0" />
                  {item.label}
                </button>
              );
            })}
          </nav>
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
                <h2 className="text-[15px] font-semibold text-gray-900 mb-5">Profile</h2>

                {/* Email */}
                <div className="bg-white rounded-xl border border-gray-100 p-5 mb-4 shadow-sm">
                  <div className="flex items-center gap-2 mb-3">
                    <Mail className="h-3.5 w-3.5 text-gray-400" />
                    <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Email Address</span>
                  </div>
                  {loading ? (
                    <div className="h-10 rounded-lg bg-gray-100 animate-pulse" />
                  ) : (
                    <div className="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-4 py-2.5">
                      <span className="text-[13px] text-gray-700">{email}</span>
                    </div>
                  )}
                </div>

                {/* Change Password */}
                <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <Lock className="h-3.5 w-3.5 text-gray-400" />
                    <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Change Password</span>
                  </div>
                  <div className="space-y-3.5">
                    <div>
                      <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 block">Current Password</label>
                      <div className="relative">
                        <input type={showCurrent ? "text" : "password"} value={currentPassword}
                          onChange={e => setCurrentPassword(e.target.value)}
                          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-[13px] text-gray-900 focus:outline-none focus:border-gray-400 transition-colors pr-10"
                          placeholder="Enter current password" />
                        <button type="button" onClick={() => setShowCurrent(!showCurrent)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700">
                          {showCurrent ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 block">New Password</label>
                      <div className="relative">
                        <input type={showNew ? "text" : "password"} value={newPassword}
                          onChange={e => setNewPassword(e.target.value)}
                          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-[13px] text-gray-900 focus:outline-none focus:border-gray-400 transition-colors pr-10"
                          placeholder="At least 8 characters" />
                        <button type="button" onClick={() => setShowNew(!showNew)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700">
                          {showNew ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 block">Confirm New Password</label>
                      <input type="password" value={confirmPassword}
                        onChange={e => setConfirmPassword(e.target.value)}
                        className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-[13px] text-gray-900 focus:outline-none focus:border-gray-400 transition-colors"
                        placeholder="Re-enter new password" />
                    </div>
                    {message && (
                      <div className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-[12px] ${message.type === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-100" : "bg-red-50 text-red-700 border border-red-100"}`}>
                        {message.type === "success" ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" /> : <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />}
                        {message.text}
                      </div>
                    )}
                    <button onClick={handleChangePassword}
                      disabled={changing || !currentPassword || !newPassword || !confirmPassword}
                      className="w-full rounded-xl bg-[#1B2A4A] text-white py-2.5 text-[13px] font-semibold hover:bg-[#243860] disabled:opacity-40 disabled:cursor-not-allowed transition-colors mt-1">
                      {changing ? "Changing..." : "Change Password"}
                    </button>
                  </div>
                </div>
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
                <h2 className="text-[15px] font-semibold text-gray-900 mb-1">AI Model</h2>
                <p className="text-[11px] text-gray-400 mb-5">
                  Choose the Claude model used for all your pipeline runs.
                </p>

                <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
                  <div className="flex items-center gap-2 mb-4">
                    <Cpu className="h-3.5 w-3.5 text-gray-400" />
                    <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Pipeline Model</span>
                  </div>

                  {loading ? (
                    <div className="h-10 rounded-lg bg-gray-100 animate-pulse" />
                  ) : (
                    <div className="space-y-4">
                      {/* Dropdown */}
                      <div>
                        <label className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1.5 block">
                          Select Model
                        </label>
                        <select
                          value={pendingModel ?? ""}
                          onChange={e => {
                            setPendingModel(e.target.value === "" ? null : e.target.value);
                            setModelMessage(null);
                          }}
                          className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-[13px] text-gray-900 focus:outline-none focus:border-[#1B2A4A] transition-colors appearance-none"
                        >
                          <option value="">System Default (Claude Haiku 4.5)</option>
                          {availableModels.map(m => (
                            <option key={m.id} value={m.id}>{m.name}</option>
                          ))}
                        </select>
                        {/* Description of selected model */}
                        {pendingModel && (() => {
                          const m = availableModels.find(x => x.id === pendingModel);
                          return m ? (
                            <p className="mt-1.5 text-[11px] text-gray-400">{m.description}</p>
                          ) : null;
                        })()}
                        {!pendingModel && (
                          <p className="mt-1.5 text-[11px] text-gray-400">Fastest and most cost-efficient. Great for high-volume tasks.</p>
                        )}
                      </div>

                      {/* Current saved value */}
                      {selectedModel !== pendingModel && (
                        <p className="text-[11px] text-amber-600">
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
                        <div className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-[12px] ${
                          modelMessage.type === "success"
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-100"
                            : "bg-red-50 text-red-700 border border-red-100"
                        }`}>
                          {modelMessage.type === "success"
                            ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
                            : <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />}
                          {modelMessage.text}
                        </div>
                      )}

                      {/* Save button */}
                      <button
                        type="button"
                        onClick={() => handleSaveModel(pendingModel)}
                        disabled={savingModel || selectedModel === pendingModel}
                        className="w-full rounded-xl bg-[#1B2A4A] text-white py-2.5 text-[13px] font-semibold hover:bg-[#243860] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {savingModel ? "Saving…" : "Save"}
                      </button>
                    </div>
                  )}
                </div>
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
                      <h2 className="text-[15px] font-semibold text-gray-900">Plan &amp; Limits</h2>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#1B2A4A] text-white uppercase tracking-wide">
                        {TIER_LABELS[userTier]}
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-400">
                      Your plan determines which pipelines you can run and what features are available.
                    </p>
                  </div>
                  <button className="flex-shrink-0 text-[11px] font-semibold text-[#1B2A4A] border border-[#1B2A4A]/30 hover:bg-[#1B2A4A] hover:text-white px-3 py-1.5 rounded-lg transition-all">
                    Upgrade plan
                  </button>
                </div>

                {/* Tier progress bar */}
                <div className="mt-5 mb-6">
                  <div className="flex items-center gap-0 rounded-xl overflow-hidden border border-gray-200 bg-white">
                    {TIER_ORDER.map((tier, idx) => {
                      const tierIdx = TIER_ORDER.indexOf(userTier);
                      const isPast = idx < tierIdx;
                      const isCurrent = tier === userTier;
                      const isFuture = idx > tierIdx;
                      return (
                        <div
                          key={tier}
                          className={`flex-1 px-4 py-3 border-r last:border-r-0 border-gray-200 transition-colors ${
                            isCurrent ? "bg-[#1B2A4A]" : isPast ? "bg-[#E8EDF5]" : "bg-white"
                          }`}
                        >
                          <p className={`text-[11px] font-bold uppercase tracking-wider ${
                            isCurrent ? "text-white" : isPast ? "text-[#1B2A4A]" : "text-gray-400"
                          }`}>
                            {TIER_LABELS[tier]}
                            {isCurrent && <span className="ml-1.5 text-[9px] font-semibold opacity-70">(current)</span>}
                          </p>
                          <p className={`text-[10px] mt-0.5 ${
                            isCurrent ? "text-white/70" : isPast ? "text-[#1B2A4A]/60" : "text-gray-400"
                          }`}>
                            {TIER_DETAILS[tier].description}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Tier tabs — pipeline details */}
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden mb-5">
                  {/* Tab bar */}
                  <div className="flex items-center border-b border-gray-100 px-4 pt-3 gap-1">
                    {TIER_ORDER.map(tier => {
                      const isCurrent = tier === userTier;
                      const isSelected = tier === selectedTierTab;
                      return (
                        <button
                          key={tier}
                          onClick={() => setSelectedTierTab(tier)}
                          className={`flex items-center gap-1.5 px-3 py-2 rounded-t-lg text-[11px] font-semibold transition-all border-b-2 -mb-px ${
                            isSelected
                              ? "border-[#1B2A4A] text-[#1B2A4A]"
                              : "border-transparent text-gray-400 hover:text-gray-700"
                          }`}
                        >
                          {TIER_LABELS[tier]}
                          {isCurrent && (
                            <span className="text-[8px] font-bold bg-[#1B2A4A] text-white px-1.5 py-0.5 rounded-full">
                              current
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>

                  {/* Pipeline table */}
                  <div className="p-4">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
                      Available Pipelines
                    </p>
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-gray-100">
                          <th className="text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider pb-2 pr-4">Pipeline</th>
                          <th className="text-left text-[10px] font-semibold text-gray-400 uppercase tracking-wider pb-2 pr-4">Description</th>
                          <th className="text-center text-[10px] font-semibold text-gray-400 uppercase tracking-wider pb-2">Access</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(PIPELINE_DISPLAY).map(([key, info]) => {
                          const hasAccess = TIER_PIPELINES[selectedTierTab].has(key);
                          const isCurrentTierAccess = TIER_PIPELINES[userTier].has(key);
                          return (
                            <tr key={key} className="border-b border-gray-50 last:border-0">
                              <td className="py-2.5 pr-4">
                                <span className={`text-[12px] font-medium ${hasAccess ? "text-gray-900" : "text-gray-400"}`}>
                                  {info.label}
                                </span>
                              </td>
                              <td className="py-2.5 pr-4">
                                <span className="text-[11px] text-gray-400">{info.description}</span>
                              </td>
                              <td className="py-2.5 text-center">
                                {hasAccess ? (
                                  <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-[#E8EDF5]">
                                    <Check className="h-3 w-3 text-[#1B2A4A]" />
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center justify-center h-5 w-5 rounded-full bg-gray-100">
                                    <span className="h-1.5 w-1.5 rounded-full bg-gray-300" />
                                  </span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Usage limits table — like Claude's rate limits table */}
                <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden mb-5">
                  <div className="px-5 py-4 border-b border-gray-100">
                    <p className="text-[13px] font-semibold text-gray-900">Usage Limits</p>
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      Limits apply to the <span className="font-semibold text-[#1B2A4A]">{TIER_LABELS[selectedTierTab]}</span> plan
                    </p>
                  </div>
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left text-[10px] font-semibold text-gray-500 uppercase tracking-wider px-5 py-2.5">Limit</th>
                        <th className="text-center text-[10px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-2.5">Basic</th>
                        <th className="text-center text-[10px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-2.5">Pro</th>
                        <th className="text-center text-[10px] font-semibold text-gray-500 uppercase tracking-wider px-4 py-2.5">Enterprise</th>
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
                        <tr key={i} className="border-t border-gray-50">
                          <td className="px-5 py-3 text-[12px] font-medium text-gray-700">{row.label}</td>
                          {(["basic", "pro", "enterprise"] as Tier[]).map(tier => {
                            const val = tier === "basic" ? row.basic : tier === "pro" ? row.pro : row.enterprise;
                            const isCurrentCol = tier === userTier;
                            const isSelectedCol = tier === selectedTierTab;
                            return (
                              <td key={tier} className={`px-4 py-3 text-center text-[12px] transition-colors ${
                                isSelectedCol ? "bg-[#F4F7FC]" : ""
                              } ${isCurrentCol ? "font-semibold text-[#1B2A4A]" : "text-gray-500"}`}>
                                {val}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Contact sales banner */}
                <div className="flex items-center justify-between bg-white rounded-xl border border-gray-100 px-5 py-4 shadow-sm">
                  <div className="flex items-center gap-3">
                    <Shield className="h-4 w-4 text-gray-400 flex-shrink-0" />
                    <div>
                      <p className="text-[12px] font-semibold text-gray-800">Need custom limits?</p>
                      <p className="text-[11px] text-gray-400">Contact us to discuss custom plans for your organisation.</p>
                    </div>
                  </div>
                  <button className="flex-shrink-0 text-[11px] font-semibold text-white bg-[#1B2A4A] hover:bg-[#243860] px-4 py-2 rounded-lg transition-colors">
                    Contact sales
                  </button>
                </div>

              </motion.div>
            )}

            {/* ── CONSTITUTION ── */}
            {section === "constitution" && (
              <ConstitutionSection />
            )}

          </AnimatePresence>
        </div>
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
      className="p-6 space-y-5"
    >
      <div className="flex items-center gap-2 mb-1">
        <FileText className="h-3.5 w-3.5 text-gray-400" />
        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
          My Constitution
        </span>
      </div>
      <p className="text-[12px] text-gray-500 leading-relaxed">
        Your Constitution is injected into every agent&apos;s system prompt as a governing guardrail.
        Write your principles, constraints, and quality standards here — they apply to all pipelines.
      </p>

      {loading ? (
        <div className="h-40 flex items-center justify-center">
          <div className="h-4 w-4 border-2 border-gray-200 border-t-[#1B2A4A] rounded-full animate-spin" />
        </div>
      ) : (
        <textarea
          value={content}
          onChange={(e) => { setContent(e.target.value); setStatus("idle"); }}
          placeholder={"# My Constitution\n\n## Principle 1 — Quality First\nEvery output must be production-ready…\n\n## Principle 2 — Security\nNever expose secrets or PII…"}
          className="w-full h-64 text-[12px] text-gray-800 bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 resize-none focus:outline-none focus:border-[#1B2A4A] transition-colors font-mono leading-relaxed"
        />
      )}

      {status === "saved" && (
        <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 bg-emerald-50 rounded-lg px-3 py-2">
          <CheckCircle2 className="h-3.5 w-3.5" /> Constitution saved — active on all future runs.
        </div>
      )}
      {status === "deleted" && (
        <div className="flex items-center gap-1.5 text-[11px] text-gray-500 bg-gray-50 rounded-lg px-3 py-2">
          <CheckCircle2 className="h-3.5 w-3.5" /> Constitution cleared.
        </div>
      )}
      {status === "error" && (
        <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-3 py-2">
          <AlertCircle className="h-3.5 w-3.5" /> Failed to save. Please try again.
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={handleSave}
          disabled={saving || loading || !content.trim()}
          className="flex items-center gap-1.5 rounded-xl bg-[#1B2A4A] px-4 py-2 text-[12px] font-semibold text-white hover:bg-[#2a3d5e] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Save className="h-3.5 w-3.5" />
          {saving ? "Saving…" : "Save Constitution"}
        </button>
        {content && (
          <button
            onClick={handleDelete}
            disabled={deleting || loading}
            className="flex items-center gap-1.5 rounded-xl border border-gray-200 px-4 py-2 text-[12px] font-medium text-gray-500 hover:border-red-300 hover:text-red-600 disabled:opacity-50 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {deleting ? "Clearing…" : "Clear"}
          </button>
        )}
      </div>
    </motion.div>
  );
}
