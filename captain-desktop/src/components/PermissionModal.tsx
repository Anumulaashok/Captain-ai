import { useState, useEffect } from "react";
import { Shield, X, Check, ShieldCheck } from "lucide-react";
import { wsClient } from "../lib/ws";
import { post } from "../lib/api";

interface PermissionRequest {
  request_id: string;
  agent_id: string;
  permission: string;
  reason: string;
  requested_at: string;
  timeout_seconds: number;
}

export default function PermissionModal() {
  const [queue, setQueue] = useState<PermissionRequest[]>([]);
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    const off = wsClient.on("permission_request", (data) => {
      setQueue((q) => [...q, data as unknown as PermissionRequest]);
    });
    return off;
  }, []);

  const current = queue[0];

  async function resolve(approved: boolean) {
    if (!current || resolving) return;
    setResolving(true);
    try {
      await post(`/api/agents/approvals/${current.request_id}`, {
        approved,
        agent_id: current.agent_id,
        permission: current.permission,
      });
    } catch {
      // Server may have reloaded — the endpoint handles this gracefully
    } finally {
      setQueue((q) => q.slice(1));
      setResolving(false);
    }
  }

  // "Always allow" = approve the current request AND pre-grant the permission
  // so the modal never appears again for this agent+permission combo.
  async function alwaysAllow() {
    if (!current || resolving) return;
    setResolving(true);
    try {
      // Grant the permission persistently first
      await post(`/api/agents/${current.agent_id}/permissions`, {
        permissions: [current.permission],
      });
      // Then resolve the current request
      await post(`/api/agents/approvals/${current.request_id}`, {
        approved: true,
        agent_id: current.agent_id,
        permission: current.permission,
      });
    } catch {
      // best-effort
    } finally {
      setQueue((q) => q.slice(1));
      setResolving(false);
    }
  }

  if (!current) return null;

  const agentLabel = current.agent_id.charAt(0).toUpperCase() + current.agent_id.slice(1);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-md mx-4 bg-zinc-900 border border-cyan-500/40 rounded-2xl shadow-2xl shadow-cyan-500/10 overflow-hidden">

        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 bg-cyan-500/10 border-b border-cyan-500/20">
          <Shield size={20} className="text-cyan-400" />
          <div>
            <p className="text-sm font-semibold text-cyan-300">Permission Required</p>
            <p className="text-xs text-zinc-400">
              {queue.length > 1 ? `${queue.length} pending requests` : "Agent is paused"}
            </p>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Agent</p>
            <p className="text-white font-medium">{agentLabel}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Requesting access to</p>
            <code className="text-cyan-400 text-sm bg-zinc-800 px-2 py-1 rounded">
              {current.permission}
            </code>
          </div>
          <div>
            <p className="text-xs text-zinc-500 uppercase tracking-widest mb-1">Reason</p>
            <p className="text-zinc-300 text-sm">{current.reason}</p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-2 px-6 pb-5">
          {/* Primary row */}
          <div className="flex gap-3">
            <button
              onClick={() => resolve(false)}
              disabled={resolving}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl border border-zinc-700 text-zinc-400 hover:border-red-500/50 hover:text-red-400 transition-colors text-sm disabled:opacity-40"
            >
              <X size={15} /> Deny
            </button>
            <button
              onClick={() => resolve(true)}
              disabled={resolving}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-cyan-700 hover:bg-cyan-600 text-white transition-colors text-sm font-medium disabled:opacity-40"
            >
              <Check size={15} /> Approve once
            </button>
          </div>

          {/* Always allow — saves the permission so modal never shows again */}
          <button
            onClick={alwaysAllow}
            disabled={resolving}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-zinc-900 transition-colors text-sm font-semibold disabled:opacity-40"
          >
            <ShieldCheck size={15} /> Always allow this session
          </button>
        </div>
      </div>
    </div>
  );
}
