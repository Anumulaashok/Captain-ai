import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Settings() {
  const [prefs, setPrefs] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.settings.get().then((p) => {
      setPrefs(p);
      setLoading(false);
    });
  }, []);

  const update = (key: string, value: unknown) => {
    setPrefs((p) => ({ ...p, [key]: value }));
  };

  const save = async () => {
    await api.settings.update(prefs);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (loading) return <div className="p-6 text-sm text-zinc-500">Loading settings…</div>;

  return (
    <div className="flex flex-col h-full overflow-y-auto p-6 gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Settings</h1>
        <button
          onClick={save}
          className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm text-white"
        >
          {saved ? "Saved!" : "Save"}
        </button>
      </div>

      {/* UI */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Appearance</h2>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Theme</span>
          <select
            value={prefs.ui_theme as string}
            onChange={(e) => update("ui_theme", e.target.value)}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200"
          >
            <option value="system">System</option>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Font size</span>
          <select
            value={prefs.font_size as string}
            onChange={(e) => update("font_size", e.target.value)}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200"
          >
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
          </select>
        </label>
      </section>

      {/* Voice */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Voice</h2>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Voice mode</span>
          <select
            value={prefs.voice_mode as string}
            onChange={(e) => update("voice_mode", e.target.value)}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200"
          >
            <option value="disabled">Disabled</option>
            <option value="wake_word">Wake word ("Hey Captain")</option>
            <option value="push_to_talk">Push to talk (⌃Space)</option>
            <option value="continuous">Continuous listening</option>
          </select>
        </label>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Text-to-speech</span>
          <input
            type="checkbox"
            checked={!!prefs.voice_tts_enabled}
            onChange={(e) => update("voice_tts_enabled", e.target.checked)}
            className="w-4 h-4"
          />
        </label>
      </section>

      {/* Memory */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Memory</h2>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Auto-consolidate memories</span>
          <input
            type="checkbox"
            checked={!!prefs.memory_auto_consolidate}
            onChange={(e) => update("memory_auto_consolidate", e.target.checked)}
            className="w-4 h-4"
          />
        </label>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Consolidate after N messages</span>
          <input
            type="number"
            min={5}
            max={50}
            value={prefs.memory_consolidate_after_n as number}
            onChange={(e) => update("memory_consolidate_after_n", parseInt(e.target.value))}
            className="w-20 bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200"
          />
        </label>
      </section>

      {/* About */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-3">About</h2>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="text-zinc-500">Version</div>
          <div className="text-zinc-300">Captain AI v1.0.0</div>
          <div className="text-zinc-500">Backend</div>
          <div className="text-zinc-300">FastAPI + Python 3.11</div>
          <div className="text-zinc-500">Database</div>
          <div className="text-zinc-300">Neon PostgreSQL</div>
          <div className="text-zinc-500">Vector store</div>
          <div className="text-zinc-300">Pinecone</div>
          <div className="text-zinc-500">Desktop</div>
          <div className="text-zinc-300">Tauri 2 + React</div>
        </div>
      </section>
    </div>
  );
}
