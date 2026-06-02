import { useEffect, useState } from "react";
import { Search, Plus, Trash2 } from "lucide-react";
import { api, MemoryEntry, MemoryStats } from "../lib/api";

export default function Memory() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [newEntry, setNewEntry] = useState({ key: "", value: "", type: "fact" });
  const [showAdd, setShowAdd] = useState(false);

  const load = async (q = "") => {
    setSearching(true);
    try {
      const [e, s] = await Promise.all([
        q ? api.memory.search(q) : api.memory.recent(),
        api.memory.stats(),
      ]);
      setEntries(e);
      setStats(s);
    } finally {
      setSearching(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSearch = () => load(query);

  const handleAdd = async () => {
    if (!newEntry.value.trim()) return;
    await api.memory.create(newEntry);
    setNewEntry({ key: "", value: "", type: "fact" });
    setShowAdd(false);
    load(query);
  };

  const handleDelete = async (id: string) => {
    await api.memory.delete(id);
    setEntries((prev) => prev.filter((e) => e.id !== id));
  };

  const typeColor: Record<string, string> = {
    fact: "bg-blue-900/40 text-blue-300 border-blue-700/30",
    preference: "bg-purple-900/40 text-purple-300 border-purple-700/30",
    entity: "bg-green-900/40 text-green-300 border-green-700/30",
    event: "bg-amber-900/40 text-amber-300 border-amber-700/30",
    document: "bg-zinc-700/60 text-zinc-300 border-zinc-600/30",
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Memory</h1>
          <p className="text-sm text-zinc-400 mt-0.5">Long-term memories stored in Pinecone</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white"
        >
          <Plus size={13} /> Add memory
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-xl bg-zinc-800/50 border border-zinc-700/40 p-3">
            <div className="text-lg font-semibold text-white">{stats.total_entries}</div>
            <div className="text-xs text-zinc-500">Total entries</div>
          </div>
          <div className="rounded-xl bg-zinc-800/50 border border-zinc-700/40 p-3">
            <div className={`text-lg font-semibold ${stats.pinecone.configured ? "text-green-400" : "text-zinc-500"}`}>
              {stats.pinecone.configured ? (stats.pinecone.total_vectors ?? 0) : "—"}
            </div>
            <div className="text-xs text-zinc-500">Pinecone vectors</div>
          </div>
          <div className="rounded-xl bg-zinc-800/50 border border-zinc-700/40 p-3">
            <div className={`text-xs font-medium mt-1 ${stats.pinecone.configured ? "text-green-400" : "text-zinc-500"}`}>
              {stats.pinecone.configured ? "Connected" : "Not configured"}
            </div>
            <div className="text-xs text-zinc-500">Pinecone status</div>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="flex gap-2">
        <div className="flex-1 flex items-center gap-2 bg-zinc-800 rounded-lg border border-zinc-700 px-3">
          <Search size={14} className="text-zinc-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Search memories semantically…"
            className="flex-1 bg-transparent py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={searching}
          className="px-4 py-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-sm text-zinc-200 transition-colors"
        >
          {searching ? "…" : "Search"}
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div className="rounded-xl bg-zinc-800/60 border border-zinc-700 p-4 flex flex-col gap-3">
          <h3 className="text-sm font-medium text-white">Add Memory</h3>
          <select
            value={newEntry.type}
            onChange={(e) => setNewEntry((p) => ({ ...p, type: e.target.value }))}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200 focus:outline-none"
          >
            {["fact", "preference", "entity", "event"].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <input
            placeholder="Key (optional)"
            value={newEntry.key}
            onChange={(e) => setNewEntry((p) => ({ ...p, key: e.target.value }))}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none"
          />
          <textarea
            placeholder="Memory content *"
            value={newEntry.value}
            onChange={(e) => setNewEntry((p) => ({ ...p, value: e.target.value }))}
            rows={3}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none resize-none"
          />
          <div className="flex gap-2">
            <button onClick={handleAdd} className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm text-white">
              Save
            </button>
            <button onClick={() => setShowAdd(false)} className="px-4 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-sm text-zinc-300">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Entries */}
      <div className="flex flex-col gap-2">
        {entries.map((e) => (
          <div
            key={e.id}
            className="flex items-start justify-between rounded-xl bg-zinc-800/40 border border-zinc-700/30 px-4 py-3 gap-3"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs px-2 py-0.5 rounded-full border ${typeColor[e.type] ?? "bg-zinc-700 text-zinc-400 border-zinc-600"}`}>
                  {e.type}
                </span>
                {e.key && <span className="text-xs text-zinc-500 truncate">{e.key}</span>}
                {e.score !== undefined && (
                  <span className="text-xs text-zinc-600">score: {e.score}</span>
                )}
              </div>
              <p className="text-sm text-zinc-300 leading-relaxed">{e.value}</p>
              {e.source && <div className="text-xs text-zinc-600 mt-1">source: {e.source}</div>}
            </div>
            <button
              onClick={() => handleDelete(e.id)}
              className="flex-shrink-0 text-zinc-600 hover:text-red-400 mt-0.5"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {entries.length === 0 && !searching && (
          <div className="text-sm text-zinc-600 text-center py-8">
            {query ? "No memories matching your search" : "No memories yet — start chatting!"}
          </div>
        )}
      </div>
    </div>
  );
}
