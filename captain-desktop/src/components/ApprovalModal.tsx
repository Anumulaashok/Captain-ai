import { useState, useEffect } from "react";
import { Bot, X, Check } from "lucide-react";
import { wsClient } from "../lib/ws";
import { post } from "../lib/api";

interface ApprovalRequest {
  request_id: string;
  agent_id: string;
  reason: string;
  spec?: Record<string, unknown>;
  pr_title?: string;
  type: "build" | "merge";
}

export default function ApprovalModal() {
  const [queue, setQueue] = useState<ApprovalRequest[]>([]);
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    const offBuild = wsClient.on("build_approval_request", (data) => {
      setQueue((q) => [...q, { ...(data as ApprovalRequest), type: "build" }]);
    });
    const offMerge = wsClient.on("merge_approval_request", (data) => {
      setQueue((q) => [...q, { ...(data as ApprovalRequest), type: "merge" }]);
    });
    return () => { offBuild(); offMerge(); };
  }, []);

  const current = queue[0];

  async function resolve(approved: boolean) {
    if (!current || resolving) return;
    setResolving(true);
    try {
      await post(`/api/agents/approvals/${current.request_id}`, { approved });
    } finally {
      setQueue((q) => q.slice(1));
      setResolving(false);
    }
  }

  if (!current) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-md mx-4 bg-zinc-900 border border-indigo-500/40 rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-3 px-6 py-4 bg-indigo-500/10 border-b border-indigo-500/20">
          <Bot size={20} className="text-indigo-400" />
          <div>
            <p className="text-sm font-semibold text-indigo-300">
              {current.type === "build" ? "Build New Agent?" : "Create Pull Request?"}
            </p>
            <p className="text-xs text-zinc-400">Captain needs your approval</p>
          </div>
        </div>
        <div className="px-6 py-5 space-y-3">
          <p className="text-white font-medium capitalize">{current.agent_id} Agent</p>
          <p className="text-zinc-300 text-sm">{current.reason}</p>
          {current.pr_title && (
            <p className="text-xs text-zinc-500">PR: {current.pr_title}</p>
          )}
        </div>
        <div className="flex gap-3 px-6 pb-5">
          <button
            onClick={() => resolve(false)}
            disabled={resolving}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl border border-zinc-700 text-zinc-400 hover:text-red-400 text-sm"
          >
            <X size={15} /> Decline
          </button>
          <button
            onClick={() => resolve(true)}
            disabled={resolving}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium"
          >
            <Check size={15} /> Approve
          </button>
        </div>
      </div>
    </div>
  );
}
