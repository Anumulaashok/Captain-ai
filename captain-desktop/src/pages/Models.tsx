import { useEffect, useState } from "react";
import { Download, Trash2, Zap, HardDrive, CheckCircle } from "lucide-react";
import { api, ModelEntry } from "../lib/api";
import { wsClient } from "../lib/ws";

function StarRating({ stars }: { stars: number }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className={`h-1.5 w-1.5 rounded-full ${i <= stars ? "bg-yellow-400" : "bg-zinc-700"}`} />
      ))}
    </div>
  );
}

function ModelCard({
  model,
  onDownload,
  onActivate,
  onDelete,
  downloadProgress,
}: {
  model: ModelEntry;
  onDownload: () => void;
  onActivate: () => void;
  onDelete: () => void;
  downloadProgress?: number;
}) {
  return (
    <div
      className={`rounded-xl border p-4 flex flex-col gap-3 transition-colors ${
        model.is_active
          ? "border-indigo-500/60 bg-indigo-950/30"
          : "border-zinc-700/50 bg-zinc-800/40 hover:border-zinc-600/60"
      }`}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white">{model.name}</span>
            {model.is_active && (
              <span className="text-xs px-1.5 py-0.5 rounded-full bg-indigo-600/40 text-indigo-300 border border-indigo-500/30">
                Active
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1">
            <StarRating stars={model.quality_stars} />
            <span className="text-xs text-zinc-500">{model.quantization}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm font-medium text-zinc-300">{model.size_gb} GB</div>
          <div className="text-xs text-zinc-500">{model.ram_required_gb} GB RAM</div>
        </div>
      </div>

      <p className="text-xs text-zinc-400 leading-relaxed">{model.description}</p>

      <div className="flex flex-wrap gap-1.5">
        {model.recommended_for.map((tag) => (
          <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-zinc-700/60 text-zinc-400">
            {tag}
          </span>
        ))}
      </div>

      {model.performance_tps && (
        <div className="flex items-center gap-1.5 text-xs text-zinc-500">
          <Zap size={12} className="text-yellow-400" />
          {model.performance_tps} tokens/sec
        </div>
      )}

      {downloadProgress !== undefined && (
        <div>
          <div className="flex justify-between text-xs text-zinc-500 mb-1">
            <span>Downloading…</span>
            <span>{downloadProgress}%</span>
          </div>
          <div className="h-1.5 bg-zinc-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 transition-all"
              style={{ width: `${downloadProgress}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex gap-2 pt-1">
        {!model.is_downloaded ? (
          <button
            onClick={onDownload}
            disabled={downloadProgress !== undefined}
            className="flex-1 flex items-center justify-center gap-2 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-xs font-medium text-white transition-colors"
          >
            <Download size={13} />
            Download
          </button>
        ) : (
          <>
            {!model.is_active && (
              <button
                onClick={onActivate}
                className="flex-1 flex items-center justify-center gap-2 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-xs font-medium text-white transition-colors"
              >
                <CheckCircle size={13} />
                Activate
              </button>
            )}
            <button
              onClick={onDelete}
              disabled={model.is_active}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-red-900/40 hover:text-red-400 disabled:opacity-30 text-xs text-zinc-500 transition-colors"
            >
              <Trash2 size={13} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function Models() {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [storage, setStorage] = useState<{ total_gb: number; installed_count: number } | null>(null);
  const [downloading, setDownloading] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const [m, s] = await Promise.all([api.models.list(), api.models.storage()]);
    setModels(m);
    setStorage(s);
    setLoading(false);
  };

  useEffect(() => {
    load();
    const unsub = wsClient.on("download_progress", (data) => {
      const { model_id, pct } = data as { model_id: string; pct: number };
      setDownloading((prev) => ({ ...prev, [model_id]: Math.round(pct) }));
      if (pct >= 100) {
        setTimeout(() => {
          setDownloading((prev) => {
            const next = { ...prev };
            delete next[model_id];
            return next;
          });
          load();
        }, 1000);
      }
    });
    const unsubSwitch = wsClient.on("model_switched", () => load());
    return () => {
      unsub();
      unsubSwitch();
    };
  }, []);

  const handleDownload = async (modelId: string) => {
    setDownloading((prev) => ({ ...prev, [modelId]: 0 }));
    // Progress comes via WebSocket
    await fetch(`http://127.0.0.1:8765/api/models/${modelId}/download`, { method: "POST" });
  };

  const handleActivate = async (modelId: string) => {
    await api.models.activate(modelId);
    await load();
  };

  const handleDelete = async (modelId: string) => {
    if (!confirm("Delete this model?")) return;
    await api.models.delete(modelId);
    await load();
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-white">Model Manager</h1>
          <p className="text-sm text-zinc-400 mt-0.5">Download and manage local LLMs</p>
        </div>
        {storage && (
          <div className="flex items-center gap-1.5 text-sm text-zinc-400">
            <HardDrive size={15} />
            {storage.installed_count} installed · {storage.total_gb} GB used
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading models…</div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {models.map((m) => (
            <ModelCard
              key={m.id}
              model={m}
              onDownload={() => handleDownload(m.id)}
              onActivate={() => handleActivate(m.id)}
              onDelete={() => handleDelete(m.id)}
              downloadProgress={downloading[m.id]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
