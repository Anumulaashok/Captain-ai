import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Settings() {
  const [prefs, setPrefs] = useState<Record<string, unknown>>({});
  const [voiceStatus, setVoiceStatus] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([api.settings.get(), api.voice.getMode()]).then(([p]) => {
      setPrefs(p);
      setLoading(false);
    });
    fetch("http://127.0.0.1:8765/api/voice/status")
      .then((r) => r.json())
      .then(setVoiceStatus)
      .catch(() => {});
  }, []);

  const update = (key: string, value: unknown) =>
    setPrefs((p) => ({ ...p, [key]: value }));

  const save = async () => {
    await api.settings.update(prefs);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const activateVoice = async (mode: string) => {
    update("voice_mode", mode);
    await api.voice.setMode(mode);
    const s = await fetch("http://127.0.0.1:8765/api/voice/status").then((r) => r.json());
    setVoiceStatus(s);
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

      {/* Voice */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Voice</h2>

        {/* Status card */}
        <div className="rounded-lg bg-zinc-900/60 border border-zinc-700/30 p-3 grid grid-cols-2 gap-2 text-xs">
          <div><span className="text-zinc-500">STT:</span> <span className="text-zinc-300">Whisper base.en (local)</span></div>
          <div><span className="text-zinc-500">TTS:</span> <span className="text-zinc-300">{(voiceStatus.tts_backend as string) === "piper" ? "Piper Amy (neural)" : "macOS Samantha"}</span></div>
          <div><span className="text-zinc-500">Wake word:</span> <span className="text-zinc-300">Hey Jarvis</span></div>
          <div><span className="text-zinc-500">Status:</span> <span className={`${voiceStatus.mode === "disabled" ? "text-zinc-500" : "text-green-400"}`}>{(voiceStatus.mode as string) || "disabled"}</span></div>
        </div>

        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Voice mode</span>
          <select
            value={prefs.voice_mode as string}
            onChange={(e) => activateVoice(e.target.value)}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200"
          >
            <option value="disabled">Disabled</option>
            <option value="wake_word">Wake word — say "Hey Jarvis"</option>
            <option value="push_to_talk">Push to talk — hold mic button</option>
            <option value="continuous">Continuous listening</option>
          </select>
        </label>

        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Speak responses aloud</span>
          <input
            type="checkbox"
            checked={!!prefs.voice_tts_enabled}
            onChange={(e) => update("voice_tts_enabled", e.target.checked)}
            className="w-4 h-4"
          />
        </label>

        {prefs.voice_mode !== "disabled" && (
          <div className="rounded-lg bg-indigo-900/20 border border-indigo-700/20 p-3 text-xs text-indigo-300">
            <strong>How to use:</strong><br/>
            {prefs.voice_mode === "wake_word" && '1. Say "Hey Jarvis" → Captain activates\n2. Speak your command\n3. Captain responds aloud'}
            {prefs.voice_mode === "push_to_talk" && "1. Hold the mic button in Chat\n2. Speak your command\n3. Release → Captain responds"}
            {prefs.voice_mode === "continuous" && "Captain is always listening and transcribing. High CPU usage."}
          </div>
        )}
      </section>

      {/* Appearance */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Appearance</h2>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Theme</span>
          <select value={prefs.ui_theme as string} onChange={(e) => update("ui_theme", e.target.value)}
            className="bg-zinc-700 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm text-zinc-200">
            <option value="system">System</option>
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>
      </section>

      {/* Memory */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Memory</h2>
        <label className="flex items-center justify-between">
          <span className="text-sm text-zinc-300">Auto-consolidate memories</span>
          <input type="checkbox" checked={!!prefs.memory_auto_consolidate}
            onChange={(e) => update("memory_auto_consolidate", e.target.checked)} className="w-4 h-4" />
        </label>
      </section>

      {/* About */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-3">About</h2>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="text-zinc-500">Version</div><div className="text-zinc-300">Captain AI v1.0.0</div>
          <div className="text-zinc-500">Database</div><div className="text-zinc-300">Neon PostgreSQL</div>
          <div className="text-zinc-500">Vector store</div><div className="text-zinc-300">Pinecone</div>
          <div className="text-zinc-500">Desktop</div><div className="text-zinc-300">Tauri 2 + React</div>
        </div>
      </section>
    </div>
  );
}
