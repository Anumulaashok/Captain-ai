import { useEffect, useState } from "react";
import { Play, Power, Shield } from "lucide-react";
import { api, Agent } from "../lib/api";

const healthColor: Record<string, string> = {
  healthy: "bg-green-400",
  degraded: "bg-yellow-400",
  unhealthy: "bg-red-400",
};

function AgentCard({
  agent,
  onToggle,
  onRun,
}: {
  agent: Agent;
  onToggle: () => void;
  onRun: () => void;
}) {
  return (
    <div
      className={`rounded-xl border p-4 flex flex-col gap-3 ${
        agent.is_enabled ? "border-zinc-700/60 bg-zinc-800/40" : "border-zinc-800/50 bg-zinc-900/30 opacity-60"
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${healthColor[agent.health] ?? "bg-zinc-600"}`} />
          <span className="text-sm font-semibold text-white">{agent.name}</span>
        </div>
        <button
          onClick={onToggle}
          className={`p-1.5 rounded-lg transition-colors ${
            agent.is_enabled ? "bg-indigo-600/30 text-indigo-300 hover:bg-indigo-600/50" : "bg-zinc-700/40 text-zinc-500 hover:bg-zinc-700"
          }`}
          title={agent.is_enabled ? "Disable agent" : "Enable agent"}
        >
          <Power size={14} />
        </button>
      </div>

      <p className="text-xs text-zinc-400 leading-relaxed">{agent.description}</p>

      <div className="flex flex-wrap gap-1">
        {agent.capabilities.map((cap) => (
          <span key={cap} className="text-xs px-1.5 py-0.5 rounded-md bg-zinc-700/60 text-zinc-400">
            {cap.replace(/_/g, " ")}
          </span>
        ))}
      </div>

      {agent.required_permissions.length > 0 && (
        <div className="flex items-start gap-1.5 text-xs text-zinc-500">
          <Shield size={11} className="mt-0.5 flex-shrink-0" />
          <span>{agent.required_permissions.join(", ")}</span>
        </div>
      )}

      <button
        onClick={onRun}
        disabled={!agent.is_enabled}
        className="flex items-center gap-2 justify-center py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 disabled:opacity-30 text-xs text-zinc-300 transition-colors"
      >
        <Play size={12} /> Run agent
      </button>
    </div>
  );
}

export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningAgent, setRunningAgent] = useState<string | null>(null);
  const [runInput, setRunInput] = useState("");
  const [runResult, setRunResult] = useState("");

  const load = async () => {
    const data = await api.agents.list();
    setAgents(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleToggle = async (agent: Agent) => {
    if (agent.is_enabled) {
      await api.agents.disable(agent.id);
    } else {
      await api.agents.enable(agent.id);
    }
    load();
  };

  const handleRun = async () => {
    if (!runningAgent || !runInput.trim()) return;
    const result = await api.agents.run(runningAgent, runInput) as { response: string };
    setRunResult(result.response || JSON.stringify(result, null, 2));
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 gap-5">
      <div>
        <h1 className="text-xl font-semibold text-white">Agents</h1>
        <p className="text-sm text-zinc-400 mt-0.5">Enable and configure AI agents</p>
      </div>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading agents…</div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onToggle={() => handleToggle(agent)}
              onRun={() => setRunningAgent(agent.id)}
            />
          ))}
        </div>
      )}

      {/* Direct run panel */}
      {runningAgent && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6">
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 w-full max-w-lg flex flex-col gap-3">
            <h3 className="text-sm font-semibold text-white">
              Run {agents.find((a) => a.id === runningAgent)?.name}
            </h3>
            <textarea
              value={runInput}
              onChange={(e) => setRunInput(e.target.value)}
              placeholder="What should this agent do?"
              rows={3}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none resize-none"
            />
            {runResult && (
              <div className="bg-zinc-800 rounded-lg p-3 text-xs text-zinc-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {runResult}
              </div>
            )}
            <div className="flex gap-2">
              <button
                onClick={handleRun}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm text-white"
              >
                Run
              </button>
              <button
                onClick={() => { setRunningAgent(null); setRunInput(""); setRunResult(""); }}
                className="px-4 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-sm text-zinc-300"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
