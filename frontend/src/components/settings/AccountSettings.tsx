"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Mail, Lock, Eye, EyeOff, CheckCircle2, AlertCircle } from "lucide-react";
import { getToken, getMe, changePassword } from "@/lib/api";

interface AccountSettingsProps {
  onBack: () => void;
}

export function AccountSettings({ onBack }: AccountSettingsProps) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);

  // Password change form
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [changing, setChanging] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    getMe(token)
      .then((user) => setEmail(user.email))
      .catch(() => {})
      .finally(() => setLoading(false));
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
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to change password";
      setMessage({ type: "error", text: errorMsg });
    } finally {
      setChanging(false);
    }
  }, [currentPassword, newPassword, confirmPassword]);

  return (
    <div className="h-full flex flex-col" style={{ background: "#f5f5f0" }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200 bg-white flex-shrink-0">
        <button onClick={onBack} className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-gray-100 transition-colors">
          <ArrowLeft className="h-4 w-4 text-gray-500" />
        </button>
        <div>
          <h1 className="text-[15px] font-semibold text-gray-900">Account Settings</h1>
          <p className="text-[11px] text-gray-400 mt-0.5">Manage your account and security</p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-8 max-w-lg mx-auto w-full">
        {/* Email Section */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 mb-4 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Mail className="h-4 w-4 text-gray-500" />
            <h2 className="text-[13px] font-semibold text-gray-900">Email Address</h2>
          </div>
          {loading ? (
            <div className="h-10 rounded-lg bg-gray-100 animate-pulse" />
          ) : (
            <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
              <span className="text-[13px] text-gray-700">{email}</span>
            </div>
          )}
        </div>

        {/* Change Password Section */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <Lock className="h-4 w-4 text-gray-500" />
            <h2 className="text-[13px] font-semibold text-gray-900">Change Password</h2>
          </div>

          <div className="space-y-4">
            {/* Current Password */}
            <div>
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5 block">Current Password</label>
              <div className="relative">
                <input
                  type={showCurrent ? "text" : "password"}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-[13px] text-gray-900 focus:outline-none focus:border-gray-400 transition-colors pr-10"
                  placeholder="Enter current password"
                />
                <button type="button" onClick={() => setShowCurrent(!showCurrent)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700">
                  {showCurrent ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>

            {/* New Password */}
            <div>
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5 block">New Password</label>
              <div className="relative">
                <input
                  type={showNew ? "text" : "password"}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-[13px] text-gray-900 focus:outline-none focus:border-gray-400 transition-colors pr-10"
                  placeholder="At least 8 characters"
                />
                <button type="button" onClick={() => setShowNew(!showNew)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700">
                  {showNew ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>

            {/* Confirm Password */}
            <div>
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5 block">Confirm New Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-[13px] text-gray-900 focus:outline-none focus:border-gray-400 transition-colors"
                placeholder="Re-enter new password"
              />
            </div>

            {/* Message */}
            {message && (
              <div className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-[12px] ${message.type === "success" ? "bg-emerald-50 text-emerald-700 border border-emerald-100" : "bg-red-50 text-red-700 border border-red-100"}`}>
                {message.type === "success" ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" /> : <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />}
                {message.text}
              </div>
            )}

            {/* Submit */}
            <button
              onClick={handleChangePassword}
              disabled={changing || !currentPassword || !newPassword || !confirmPassword}
              className="w-full rounded-xl bg-gray-900 text-white py-2.5 text-[13px] font-semibold hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors mt-1"
            >
              {changing ? "Changing..." : "Change Password"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
