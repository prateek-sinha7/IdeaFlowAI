"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  GitBranch,
  KeyRound,
  Terminal,
  CheckCircle2,
  AlertCircle,
  Plus,
  Trash2,
  Copy,
  EyeOff,
  Eye,
} from "lucide-react";

import { getToken } from "@/lib/api";
import { ENV } from "@/lib/env";
import {
  createApiKey,
  deleteGithubPat,
  getGithubPatStatus,
  listApiKeys,
  revokeApiKey,
  saveGithubPat,
  type ApiKeyCreated,
  type ApiKeySummary,
  type GithubPatStatus,
} from "@/lib/api-handoff";

/**
 * Self-contained integrations panel for the /flowin-handoff feature.
 *
 *   - Install card (one-line `curl | bash`).
 *   - GitHub PAT (paste, save, delete).
 *   - Long-lived Flowin API keys (create, list, revoke).
 *
 * Used in two surfaces:
 *
 *   1. The standalone ``/handoff/settings`` page, when the user wants to
 *      manage credentials independently of a running handoff.
 *   2. The onboarding state inside the handoff page itself, when the user
 *      opens a handoff URL but hasn't yet configured a GitHub PAT.
 *
 * Lives under ``components/handoff/`` so the entire feature is one folder.
 */
export function IntegrationsCard({
  compact = false,
}: {
  compact?: boolean;
}) {
  const [pat, setPat] = useState("");
  const [showPat, setShowPat] = useState(false);
  const [patStatus, setPatStatus] = useState<GithubPatStatus | null>(null);
  const [patBusy, setPatBusy] = useState(false);
  const [patMessage, setPatMessage] = useState<
    { type: "success" | "error"; text: string } | null
  >(null);

  const [keys, setKeys] = useState<ApiKeySummary[]>([]);
  const [keyName, setKeyName] = useState("Default");
  const [newlyMinted, setNewlyMinted] = useState<ApiKeyCreated | null>(null);
  const [keyBusy, setKeyBusy] = useState(false);
  const [keyMessage, setKeyMessage] = useState<
    { type: "success" | "error"; text: string } | null
  >(null);

  const installCommand = useMemo(() => {
    const base = ENV.API_URL.replace(/\/$/, "");
    return `curl -fsSL ${base}/install/flowin-handoff | bash`;
  }, []);
  const [installCopied, setInstallCopied] = useState(false);
  const handleCopyInstall = useCallback(() => {
    navigator.clipboard.writeText(installCommand).then(() => {
      setInstallCopied(true);
      setTimeout(() => setInstallCopied(false), 2000);
    });
  }, [installCommand]);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const [p, ks] = await Promise.all([
        getGithubPatStatus(token),
        listApiKeys(token),
      ]);
      setPatStatus(p);
      setKeys(ks);
    } catch {
      /* dashboard auth already gated this surface */
    }
  }, []);
  useEffect(() => void refresh(), [refresh]);

  const handleSavePat = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    if (pat.length < 10) {
      setPatMessage({ type: "error", text: "PAT looks too short to be valid" });
      return;
    }
    setPatBusy(true);
    setPatMessage(null);
    try {
      const next = await saveGithubPat(token, pat);
      setPatStatus(next);
      setPat("");
      setPatMessage({
        type: "success",
        text: `Saved for ${next.github_username ?? "unknown user"}`,
      });
    } catch (err) {
      setPatMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to save PAT",
      });
    } finally {
      setPatBusy(false);
    }
  }, [pat]);

  const handleDeletePat = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setPatBusy(true);
    try {
      await deleteGithubPat(token);
      setPatStatus(null);
      setPatMessage({ type: "success", text: "PAT removed" });
    } catch (err) {
      setPatMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to delete PAT",
      });
    } finally {
      setPatBusy(false);
    }
  }, []);

  const handleCreateKey = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setKeyBusy(true);
    setKeyMessage(null);
    try {
      const created = await createApiKey(token, keyName || "Default");
      setNewlyMinted(created);
      setKeyName("Default");
      await refresh();
    } catch (err) {
      setKeyMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to create key",
      });
    } finally {
      setKeyBusy(false);
    }
  }, [keyName, refresh]);

  const handleRevoke = useCallback(
    async (id: string) => {
      const token = getToken();
      if (!token) return;
      setKeyBusy(true);
      try {
        await revokeApiKey(token, id);
        await refresh();
      } catch (err) {
        setKeyMessage({
          type: "error",
          text: err instanceof Error ? err.message : "Failed to revoke key",
        });
      } finally {
        setKeyBusy(false);
      }
    },
    [refresh]
  );

  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      {/* Install */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <Terminal className="h-4 w-4 text-gray-500" />
          <h2 className="text-[13px] font-semibold text-gray-900">
            Install the /flowin-handoff slash command
          </h2>
        </div>
        <p className="text-[11px] text-gray-500 mb-3">
          Run on each machine where you use Claude Code. Idempotent — safe to
          re-run to pull updates.
        </p>
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5">
          <code className="flex-1 text-[12px] font-mono text-gray-800 truncate">
            {installCommand}
          </code>
          <button
            onClick={handleCopyInstall}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-gray-700 hover:bg-gray-200"
          >
            {installCopied ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                Copied
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                Copy
              </>
            )}
          </button>
        </div>
      </div>

      {/* GitHub PAT */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <GitBranch className="h-4 w-4 text-gray-500" />
          <h2 className="text-[13px] font-semibold text-gray-900">
            GitHub access token
          </h2>
        </div>
        <p className="text-[11px] text-gray-500 mb-3">
          Needs <code className="px-1 rounded bg-gray-100">repo</code> scope.
          Encrypted at rest, never returned by any API.
        </p>
        {patStatus ? (
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 mb-3 flex items-center justify-between">
            <div>
              <div className="text-[12px] text-gray-700">
                Saved for{" "}
                <span className="font-semibold">
                  {patStatus.github_username ?? "unknown"}
                </span>
              </div>
              <div className="text-[10px] text-gray-500 mt-0.5">
                Ends in ····{patStatus.last_4}
                {patStatus.scopes ? ` · scopes: ${patStatus.scopes}` : ""}
              </div>
            </div>
            <button
              onClick={handleDeletePat}
              disabled={patBusy}
              className="text-[11px] text-red-600 hover:underline disabled:opacity-50"
            >
              Remove
            </button>
          </div>
        ) : (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 mb-3 text-[12px] text-amber-800 flex items-center gap-2">
            <AlertCircle className="h-4 w-4" /> No GitHub token saved yet.
          </div>
        )}
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <input
              type={showPat ? "text" : "password"}
              value={pat}
              onChange={(e) => setPat(e.target.value)}
              placeholder="github_pat_..."
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-[13px] bg-white outline-none input-focus"
            />
            <button
              type="button"
              onClick={() => setShowPat((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              {showPat ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <button
            onClick={handleSavePat}
            disabled={patBusy || pat.length < 10}
            className="rounded-lg bg-blue-600 px-4 py-2 text-[12px] font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {patBusy ? "Saving..." : patStatus ? "Replace" : "Save"}
          </button>
        </div>
        {patMessage && (
          <div
            className={`mt-2 text-[11px] inline-flex items-center gap-1 ${
              patMessage.type === "success" ? "text-green-700" : "text-red-700"
            }`}
          >
            {patMessage.type === "success" ? (
              <CheckCircle2 className="h-3 w-3" />
            ) : (
              <AlertCircle className="h-3 w-3" />
            )}
            {patMessage.text}
          </div>
        )}
      </div>

      {/* API keys */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <KeyRound className="h-4 w-4 text-gray-500" />
          <h2 className="text-[13px] font-semibold text-gray-900">
            Flowin API keys
          </h2>
        </div>
        <p className="text-[11px] text-gray-500 mb-3">
          Used by the slash command / MCP client. Plaintext shown once.
        </p>
        {newlyMinted && (
          <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 mb-3 text-[12px]">
            <div className="font-semibold mb-1">New key — copy now</div>
            <div className="flex items-center gap-2 font-mono break-all text-[11px]">
              <span className="flex-1">{newlyMinted.token}</span>
              <button
                onClick={() =>
                  navigator.clipboard.writeText(newlyMinted.token).then(() => {})
                }
                className="flex items-center gap-1 rounded-md px-2 py-1 text-blue-700 hover:bg-blue-100"
              >
                <Copy className="h-3 w-3" />
              </button>
            </div>
            <button
              onClick={() => setNewlyMinted(null)}
              className="mt-2 text-[11px] text-blue-700 hover:underline"
            >
              Dismiss
            </button>
          </div>
        )}
        <div className="space-y-2 mb-3">
          {keys.length === 0 ? (
            <div className="text-[11px] text-gray-500">No API keys yet.</div>
          ) : (
            keys.map((k) => (
              <div
                key={k.id}
                className="flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-[12px]"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-gray-800 flex items-center gap-2">
                    {k.name}
                    {k.revoked_at && (
                      <span className="text-[9px] text-red-600 bg-red-50 rounded px-1.5 py-0.5">
                        revoked
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-gray-500 font-mono">
                    {k.token_prefix}···
                    {k.last_used_at
                      ? ` · last used ${new Date(k.last_used_at).toLocaleString()}`
                      : " · never used"}
                  </div>
                </div>
                {!k.revoked_at && (
                  <button
                    onClick={() => handleRevoke(k.id)}
                    disabled={keyBusy}
                    className="text-[10px] text-red-600 hover:underline disabled:opacity-50 inline-flex items-center gap-1"
                  >
                    <Trash2 className="h-3 w-3" />
                    Revoke
                  </button>
                )}
              </div>
            ))
          )}
        </div>
        <div className="flex gap-2">
          <input
            value={keyName}
            onChange={(e) => setKeyName(e.target.value)}
            placeholder="Key name (e.g. Laptop)"
            className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-[13px] bg-white outline-none input-focus"
          />
          <button
            onClick={handleCreateKey}
            disabled={keyBusy}
            className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-4 py-2 text-[12px] font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            Create key
          </button>
        </div>
        {keyMessage && (
          <div className="mt-2 text-[11px] text-red-700 inline-flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {keyMessage.text}
          </div>
        )}
      </div>
    </div>
  );
}
