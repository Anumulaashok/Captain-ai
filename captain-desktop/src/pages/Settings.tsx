import { useEffect, useState } from "react";
import { api, IntegrationStatus } from "../lib/api";

export default function Settings() {
  const [prefs, setPrefs] = useState<Record<string, unknown>>({});
  const [voiceStatus, setVoiceStatus] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);
  const [gmailAddress, setGmailAddress] = useState("");
  const [gmailPassword, setGmailPassword] = useState("");
  const [gmailSaved, setGmailSaved] = useState(false);
  const [gmailTesting, setGmailTesting] = useState(false);
  const [gmailTestResult, setGmailTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [connecting, setConnecting] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.settings.get(), api.voice.getMode(), api.integrations.list()]).then(([p, , ints]) => {
      setPrefs(p);
      setIntegrations(ints);
      setLoading(false);
      if (p.gmail_address) setGmailAddress(p.gmail_address as string);
      if (p.gmail_app_password) setGmailPassword("••••••••••••••••");
    });
    const params = new URLSearchParams(window.location.search);
    if (params.get("connected")) {
      api.integrations.list().then(setIntegrations);
    }
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

  const saveGmail = async () => {
    const updates: Record<string, unknown> = { gmail_address: gmailAddress };
    if (gmailPassword && !gmailPassword.startsWith("••")) {
      updates.gmail_app_password = gmailPassword;
    }
    await api.settings.update(updates);
    setGmailSaved(true);
    setTimeout(() => setGmailSaved(false), 2000);
  };

  const connectIntegration = async (id: string) => {
    setConnecting(id);
    try {
      const res = await api.integrations.auth(id);
      if (res.error === "env_missing" && res.missing_keys) {
        alert(`Add to .env:\n${res.missing_keys.join("\n")}`);
        return;
      }
      if (res.auth_url) {
        window.open(res.auth_url, "_blank");
      }
    } catch (e) {
      alert(`Connect failed: ${e}`);
    } finally {
      setConnecting(null);
    }
  };

  const disconnectIntegration = async (id: string) => {
    await api.integrations.disconnect(id);
    setIntegrations(await api.integrations.list());
  };

  const testGmail = async () => {
    setGmailTesting(true);
    setGmailTestResult(null);
    try {
      const res = await api.agents.run("gmail", "List my 3 most recent emails") as { response: string; success: boolean };
      const response = res?.response ?? "";
      const ok = res?.success && !response.toLowerCase().includes("not configured") && !response.toLowerCase().includes("opened gmail");
      setGmailTestResult({ ok, msg: ok ? "Connected! Gmail is working." : "Not configured yet — add your App Password below." });
    } catch {
      setGmailTestResult({ ok: false, msg: "Could not reach the Gmail agent. Make sure Captain is running." });
    } finally {
      setGmailTesting(false);
    }
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

      {/* Integrations */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Integrations</h2>
        <p className="text-xs text-zinc-500">
          Connect services via OAuth. Add client IDs/secrets to your <code className="text-indigo-400">.env</code> file first.
        </p>
        <div className="grid gap-3">
          {integrations.map((int) => (
            <div
              key={int.id}
              className="flex items-center justify-between rounded-lg bg-zinc-900/60 border border-zinc-700/30 p-3"
            >
              <div>
                <p className="text-sm text-zinc-200 font-medium">{int.name}</p>
                <p className="text-xs text-zinc-500">{int.description}</p>
                {!int.env_configured && (
                  <p className="text-xs text-amber-400 mt-1">
                    Missing: {int.missing_env_keys.join(", ")}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  int.connected ? "bg-green-900/40 text-green-400" : "bg-zinc-700 text-zinc-400"
                }`}>
                  {int.connected ? "Connected" : "Disconnected"}
                </span>
                {int.connected ? (
                  <button
                    onClick={() => disconnectIntegration(int.id)}
                    className="px-3 py-1 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-xs text-zinc-300"
                  >
                    Disconnect
                  </button>
                ) : (
                  <button
                    onClick={() => connectIntegration(int.id)}
                    disabled={connecting === int.id || !int.env_configured}
                    className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs text-white disabled:opacity-50"
                  >
                    {connecting === int.id ? "…" : "Connect"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Gmail (IMAP fallback) */}
      <section className="rounded-xl bg-zinc-800/40 border border-zinc-700/30 p-4 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Gmail</h2>
          <div className="flex gap-2">
            <button
              onClick={testGmail}
              disabled={gmailTesting}
              className="px-3 py-1 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-xs text-zinc-200 disabled:opacity-50"
            >
              {gmailTesting ? "Testing…" : "Test"}
            </button>
            <button
              onClick={saveGmail}
              className="px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs text-white"
            >
              {gmailSaved ? "Saved!" : "Save"}
            </button>
          </div>
        </div>

        <p className="text-xs text-zinc-500">
          Connect Gmail via IMAP using a Google App Password — no OAuth, fully local.
        </p>

        {gmailTestResult && (
          <div className={`rounded-lg p-3 text-xs ${gmailTestResult.ok ? "bg-green-900/30 text-green-300 border border-green-700/30" : "bg-amber-900/30 text-amber-300 border border-amber-700/30"}`}>
            {gmailTestResult.msg}
          </div>
        )}

        <label className="flex flex-col gap-1">
          <span className="text-xs text-zinc-400">Gmail address</span>
          <input
            type="email"
            value={gmailAddress}
            onChange={(e) => setGmailAddress(e.target.value)}
            placeholder="you@gmail.com"
            className="bg-zinc-900/60 border border-zinc-700/30 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-zinc-400">Google App Password</span>
          <input
            type="password"
            value={gmailPassword}
            onChange={(e) => setGmailPassword(e.target.value)}
            placeholder="16-character app password"
            className="bg-zinc-900/60 border border-zinc-700/30 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500"
          />
        </label>

        <div className="rounded-lg bg-zinc-900/40 border border-zinc-700/20 p-3 text-xs text-zinc-500 space-y-1">
          <p className="font-medium text-zinc-400">One-time setup</p>
          <p>1. Go to <span className="text-indigo-400">myaccount.google.com/apppasswords</span></p>
          <p>2. Create a password named "Captain AI"</p>
          <p>3. Paste the 16-character code above and click Save</p>
        </div>
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
