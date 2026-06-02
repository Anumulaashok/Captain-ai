import { useEffect, useState } from "react";
import { api, AccountService, AccountsStatus } from "../lib/api";

const statusColor: Record<string, string> = {
  connected: "text-green-400",
  running: "text-green-400",
  configured: "text-green-400",
  stopped: "text-yellow-400",
  not_configured: "text-zinc-500",
  error: "text-red-400",
};

const statusLabel: Record<string, string> = {
  connected: "Connected",
  running: "Running",
  configured: "Configured",
  stopped: "Stopped",
  not_configured: "Not configured",
  error: "Error",
};

function ServiceCard({ service }: { service: AccountService }) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-zinc-800/60 px-4 py-3 border border-zinc-700/50">
      <div className="flex items-center gap-3">
        <div
          className={`h-2.5 w-2.5 rounded-full ${
            ["connected", "running", "configured"].includes(service.status)
              ? "bg-green-400"
              : service.status === "stopped"
              ? "bg-yellow-400"
              : service.status === "error"
              ? "bg-red-400"
              : "bg-zinc-600"
          }`}
        />
        <div>
          <div className="text-sm font-medium text-white">{service.provider}</div>
          <div className="text-xs text-zinc-400">{service.type.replace(/_/g, " ")}</div>
        </div>
      </div>
      <div className="text-right">
        <div className={`text-xs font-medium ${statusColor[service.status]}`}>
          {statusLabel[service.status]}
        </div>
        {service.status === "connected" && service.vectors !== undefined && (
          <div className="text-xs text-zinc-500">{service.vectors.toLocaleString()} vectors</div>
        )}
        {service.status === "running" && service.active_model && (
          <div className="text-xs text-zinc-500 truncate max-w-[140px]">{service.active_model}</div>
        )}
        {service.error && (
          <div className="text-xs text-red-400 truncate max-w-[160px]">{service.error}</div>
        )}
      </div>
    </div>
  );
}

function CloudConnect({
  service,
  label,
  onConnected,
}: {
  service: string;
  label: string;
  onConnected: () => void;
}) {
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    if (!key.trim()) return;
    setSaving(true);
    setError("");
    try {
      await api.accounts.addCloudKey(service, key.trim());
      setKey("");
      onConnected();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex gap-2">
      <input
        type="password"
        placeholder={`${label} API Key`}
        value={key}
        onChange={(e) => setKey(e.target.value)}
        className="flex-1 rounded-lg bg-zinc-700 border border-zinc-600 px-3 py-1.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        onKeyDown={(e) => e.key === "Enter" && handleSave()}
      />
      <button
        onClick={handleSave}
        disabled={saving || !key.trim()}
        className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm font-medium text-white transition-colors"
      >
        {saving ? "Saving…" : "Connect"}
      </button>
      {error && <div className="text-xs text-red-400 mt-1">{error}</div>}
    </div>
  );
}

export default function Accounts() {
  const [data, setData] = useState<AccountsStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      setLoading(true);
      const result = await api.accounts.getAll();
      setData(result);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15_000);
    return () => clearInterval(id);
  }, []);

  const cloudServiceLabels: Record<string, string> = {
    "OpenAI": "OpenAI",
    "Anthropic": "Anthropic",
    "Google Gemini": "Gemini",
  };

  const serviceToId: Record<string, string> = {
    "OpenAI": "openai",
    "Anthropic": "anthropic",
    "Google Gemini": "gemini",
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Accounts & Connections</h1>
          <p className="text-sm text-zinc-400 mt-0.5">
            Manage your local and cloud service connections
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="text-xs text-zinc-400 hover:text-white px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 transition-colors"
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {/* Local services */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-3">
          Local Services
        </h2>
        <div className="flex flex-col gap-2">
          {loading && !data ? (
            <div className="text-sm text-zinc-500">Checking connections…</div>
          ) : (
            data?.local.map((svc) => <ServiceCard key={svc.provider} service={svc} />)
          )}
        </div>
      </section>

      {/* Cloud plugins */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-1">
          Cloud Plugins (optional)
        </h2>
        <p className="text-xs text-zinc-500 mb-3">
          Connect cloud models as fallback or for specific tasks. Keys are stored in macOS Keychain.
        </p>
        <div className="flex flex-col gap-3">
          {data?.cloud.map((svc) => (
            <div
              key={svc.provider}
              className="rounded-xl bg-zinc-800/60 border border-zinc-700/50 p-4 flex flex-col gap-3"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={`h-2.5 w-2.5 rounded-full ${
                      svc.status === "configured" ? "bg-green-400" : "bg-zinc-600"
                    }`}
                  />
                  <div>
                    <div className="text-sm font-medium text-white">{svc.provider}</div>
                    <div className="text-xs text-zinc-400">Cloud LLM</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${statusColor[svc.status]}`}>
                    {statusLabel[svc.status]}
                  </span>
                  {svc.status === "configured" && (
                    <button
                      onClick={async () => {
                        await api.accounts.removeCloudKey(serviceToId[svc.provider]);
                        refresh();
                      }}
                      className="text-xs text-red-400 hover:text-red-300 ml-2"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
              {svc.status !== "configured" && (
                <CloudConnect
                  service={serviceToId[svc.provider]}
                  label={cloudServiceLabels[svc.provider]}
                  onConnected={refresh}
                />
              )}
              {svc.source && (
                <div className="text-xs text-zinc-500">
                  Key source: {svc.source}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Connection details */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-3">
          Connection Details
        </h2>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-zinc-500">Database</div>
            <div className="text-zinc-300 font-mono truncate">Neon PostgreSQL (pooler)</div>
          </div>
          <div>
            <div className="text-zinc-500">Vector Store</div>
            <div className="text-zinc-300 font-mono">Pinecone (serverless)</div>
          </div>
          <div>
            <div className="text-zinc-500">LLM Runtime</div>
            <div className="text-zinc-300 font-mono">Ollama localhost:11434</div>
          </div>
          <div>
            <div className="text-zinc-500">Backend</div>
            <div className="text-zinc-300 font-mono">FastAPI localhost:8765</div>
          </div>
        </div>
      </section>
    </div>
  );
}
