import { useState, useEffect, useRef, useCallback } from "react";
import {
  Activity, GitPullRequest, Mail, Calendar, DollarSign,
  Bell, Mic, Bot, CheckCircle, XCircle, Loader2, Radio,
} from "lucide-react";
import { wsClient } from "../lib/ws";
import { api, BriefingItem } from "../lib/api";

// ── Types ─────────────────────────────────────────────────────────────

interface AgentActivity {
  agent_id: string;
  agent_name: string;
  subtask_id?: string;
  status: "running" | "done" | "failed";
  subtask?: string;
  started: number;  // Date.now()
}

interface Notification {
  id: string;
  category: string;
  title: string;
  summary: string;
  priority: number;
  ts: number;
}

// ── Radar canvas backdrop ─────────────────────────────────────────────

function RadarCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    let raf: number;
    let angle = 0;
    const dots = Array.from({ length: 60 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.6 + 0.1,
    }));

    function draw() {
      const { width: w, height: h } = canvas!;
      ctx.clearRect(0, 0, w, h);

      const cx = w / 2;
      const cy = h / 2;
      const maxR = Math.min(w, h) * 0.42;

      // Grid rings
      for (let i = 1; i <= 4; i++) {
        ctx.beginPath();
        ctx.arc(cx, cy, (maxR * i) / 4, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(6,182,212,${0.06 + i * 0.02})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Cross-hair lines
      ctx.strokeStyle = "rgba(6,182,212,0.08)";
      ctx.beginPath(); ctx.moveTo(cx, cy - maxR); ctx.lineTo(cx, cy + maxR); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx - maxR, cy); ctx.lineTo(cx + maxR, cy); ctx.stroke();

      // Sweep
      // sweep gradient (no conical gradient in canvas2D — use linear approximation)
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle);
      const sweep = ctx.createLinearGradient(0, 0, maxR, 0);
      sweep.addColorStop(0, "rgba(6,182,212,0.35)");
      sweep.addColorStop(1, "rgba(6,182,212,0)");
      ctx.fillStyle = sweep;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, maxR, -0.3, 0.3);
      ctx.closePath();
      ctx.fill();
      ctx.restore();

      // Particles
      dots.forEach((d) => {
        const px = cx + (d.x - 0.5) * maxR * 2;
        const py = cy + (d.y - 0.5) * maxR * 2;
        const dist = Math.sqrt((px - cx) ** 2 + (py - cy) ** 2);
        if (dist > maxR) return;
        ctx.beginPath();
        ctx.arc(px, py, d.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(6,182,212,${d.opacity})`;
        ctx.fill();
      });

      // Center glow
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, 40);
      glow.addColorStop(0, "rgba(6,182,212,0.4)");
      glow.addColorStop(1, "rgba(6,182,212,0)");
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(cx, cy, 40, 0, Math.PI * 2); ctx.fill();

      angle += 0.012;
      raf = requestAnimationFrame(draw);
    }

    function resize() {
      canvas!.width = canvas!.offsetWidth;
      canvas!.height = canvas!.offsetHeight;
    }

    resize();
    draw();
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      className="absolute inset-0 w-full h-full opacity-60 pointer-events-none"
    />
  );
}

// ── Agent status grid ─────────────────────────────────────────────────

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  prs: GitPullRequest,
  emails: Mail,
  calendar: Calendar,
  finance: DollarSign,
  notifications: Bell,
  agents: Bot,
};

const CATEGORY_COLORS: Record<string, string> = {
  prs: "text-violet-400",
  emails: "text-blue-400",
  calendar: "text-emerald-400",
  finance: "text-amber-400",
  notifications: "text-orange-400",
  agents: "text-cyan-400",
};

function AgentCard({ activity }: { activity: AgentActivity }) {
  const elapsed = Math.floor((Date.now() - activity.started) / 1000);
  return (
    <div className={`flex items-start gap-3 p-3 rounded-xl border transition-all
      ${activity.status === "running"
        ? "border-cyan-500/30 bg-cyan-500/5"
        : activity.status === "done"
          ? "border-emerald-500/20 bg-emerald-500/5"
          : "border-red-500/20 bg-red-500/5"
      }`}
    >
      <div className="mt-0.5">
        {activity.status === "running"
          ? <Loader2 size={14} className="text-cyan-400 animate-spin" />
          : activity.status === "done"
            ? <CheckCircle size={14} className="text-emerald-400" />
            : <XCircle size={14} className="text-red-400" />
        }
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-white capitalize">{activity.agent_name || activity.agent_id}</p>
        {activity.subtask && (
          <p className="text-[11px] text-zinc-500 truncate">{activity.subtask}</p>
        )}
        <p className="text-[10px] text-zinc-600 mt-0.5">{elapsed}s</p>
      </div>
    </div>
  );
}

function NotificationCard({ item }: { item: Notification }) {
  const Icon = CATEGORY_ICONS[item.category] ?? Bell;
  const color = CATEGORY_COLORS[item.category] ?? "text-zinc-400";
  return (
    <div className="flex items-start gap-3 p-3 rounded-xl border border-zinc-800 bg-zinc-900/60 hover:border-zinc-700 transition-colors">
      <Icon size={14} className={`mt-0.5 flex-shrink-0 ${color}`} />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-white truncate">{item.title}</p>
        <p className="text-[11px] text-zinc-500 line-clamp-2 mt-0.5">{item.summary}</p>
      </div>
      {item.priority <= 2 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 flex-shrink-0">urgent</span>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────

export default function CommandCenter() {
  const [agents, setAgents] = useState<AgentActivity[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [briefingItems, setBriefingItems] = useState<BriefingItem[]>([]);
  const [briefingText, setBriefingText] = useState("");
  const [isBriefing, setIsBriefing] = useState(false);
  const [planInfo, setPlanInfo] = useState<{ count: number; agents: string[] } | null>(null);

  // Load existing briefing items on mount
  useEffect(() => {
    api.briefing.items(false).then(setBriefingItems).catch(() => {});
  }, []);

  // WebSocket event subscriptions
  useEffect(() => {
    const offs = [
      wsClient.on("agent_started", (d) => {
        const data = d as { agent_id: string; agent_name: string; subtask_id?: string; subtask?: string };
        setAgents((prev) => {
          const exists = prev.find((a) => a.subtask_id === data.subtask_id && data.subtask_id);
          if (exists) return prev;
          return [
            { ...data, status: "running" as const, started: Date.now() },
            ...prev.slice(0, 19),
          ];
        });
      }),

      wsClient.on("agent_finished", (d) => {
        const data = d as { agent_id: string; subtask_id?: string; success: boolean };
        setAgents((prev) =>
          prev.map((a) =>
            (data.subtask_id ? a.subtask_id === data.subtask_id : a.agent_id === data.agent_id)
              ? { ...a, status: data.success ? "done" : "failed" }
              : a
          )
        );
      }),

      wsClient.on("plan_created", (d) => {
        const data = d as { subtask_count: number; agents: string[] };
        setPlanInfo({ count: data.subtask_count, agents: data.agents });
        setTimeout(() => setPlanInfo(null), 8000);
      }),

      wsClient.on("notification", (d) => {
        const data = d as { category: string; title: string; summary: string; priority: number };
        setNotifications((prev) => [
          {
            id: `${Date.now()}`,
            ...data,
            ts: Date.now(),
          },
          ...prev.slice(0, 29),
        ]);
        // Also refresh briefing items
        api.briefing.items(false).then(setBriefingItems).catch(() => {});
      }),

      wsClient.on("voice_briefing", (d) => {
        const data = d as { text: string };
        setBriefingText(data.text);
        setIsBriefing(true);
      }),

      wsClient.on("voice_done", () => {
        setIsBriefing(false);
      }),
    ];

    return () => offs.forEach((off) => off());
  }, []);

  async function requestBriefing() {
    setIsBriefing(true);
    try {
      await api.voice.triggerBriefing();
    } catch {
      setIsBriefing(false);
    }
  }

  const runningCount = agents.filter((a) => a.status === "running").length;

  const itemsByCategory = briefingItems.reduce((acc, item) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category].push(item);
    return acc;
  }, {} as Record<string, BriefingItem[]>);

  return (
    <div className="relative flex flex-col h-full bg-zinc-950 overflow-hidden">
      {/* Holographic grid background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(6,182,212,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(6,182,212,0.03) 1px, transparent 1px)
          `,
          backgroundSize: "40px 40px",
        }}
      />

      {/* Header bar */}
      <div className="relative z-10 flex items-center justify-between px-6 py-3 border-b border-cyan-500/10 bg-zinc-950/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <Radio size={16} className="text-cyan-400 animate-pulse" />
          <span className="text-sm font-semibold text-cyan-300 tracking-wider uppercase">
            Command Center
          </span>
          {runningCount > 0 && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400">
              {runningCount} active
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {planInfo && (
            <span className="text-xs text-zinc-400 animate-pulse">
              Plan: {planInfo.count} tasks — {planInfo.agents.join(", ")}
            </span>
          )}
          <button
            onClick={requestBriefing}
            disabled={isBriefing}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
              ${isBriefing
                ? "bg-cyan-500/20 text-cyan-400 cursor-wait"
                : "bg-cyan-600 hover:bg-cyan-500 text-white"
              }`}
          >
            <Mic size={12} />
            {isBriefing ? "Briefing…" : "What's the update?"}
          </button>
        </div>
      </div>

      {/* Main grid layout */}
      <div className="relative z-10 flex flex-1 overflow-hidden gap-0">

        {/* Left: Radar + live agents */}
        <div className="w-64 flex flex-col border-r border-cyan-500/10">
          {/* Radar */}
          <div className="relative h-52 flex-shrink-0 border-b border-cyan-500/10 overflow-hidden">
            <RadarCanvas />
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <p className="text-[10px] text-cyan-400/60 uppercase tracking-widest mt-24">
                {runningCount > 0 ? `${runningCount} agent${runningCount > 1 ? "s" : ""} active` : "all idle"}
              </p>
            </div>
          </div>

          {/* Live agent status */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-2">Agent activity</p>
            {agents.length === 0 && (
              <p className="text-xs text-zinc-700 text-center py-4">No recent activity</p>
            )}
            {agents.map((a, i) => (
              <AgentCard key={`${a.agent_id}-${a.subtask_id ?? i}`} activity={a} />
            ))}
          </div>
        </div>

        {/* Center: live notifications */}
        <div className="flex-1 flex flex-col border-r border-cyan-500/10 overflow-hidden">
          <div className="px-4 py-3 border-b border-cyan-500/10 flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-widest text-zinc-500">Live notifications</p>
            <Activity size={12} className="text-zinc-600" />
          </div>

          {/* Briefing text panel */}
          {briefingText && (
            <div className="mx-3 mt-3 p-3 rounded-xl border border-cyan-500/20 bg-cyan-500/5">
              <p className="text-[10px] uppercase tracking-widest text-cyan-500 mb-1">Last briefing</p>
              <p className="text-xs text-zinc-300 leading-relaxed">{briefingText}</p>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {notifications.length === 0 && (
              <p className="text-xs text-zinc-700 text-center py-8">No notifications yet</p>
            )}
            {notifications.map((n) => (
              <NotificationCard key={n.id} item={n} />
            ))}
          </div>
        </div>

        {/* Right: category widgets */}
        <div className="w-64 flex flex-col overflow-y-auto">
          <div className="px-4 py-3 border-b border-cyan-500/10">
            <p className="text-[10px] uppercase tracking-widest text-zinc-500">Dashboard</p>
          </div>
          <div className="p-3 space-y-3">
            {(["prs", "emails", "calendar", "finance", "notifications"] as const).map((cat) => {
              const Icon = CATEGORY_ICONS[cat] ?? Bell;
              const color = CATEGORY_COLORS[cat] ?? "text-zinc-400";
              const items = itemsByCategory[cat] ?? [];
              const catLabels: Record<string, string> = {
                prs: "GitHub PRs",
                emails: "Email",
                calendar: "Calendar",
                finance: "Finance",
                notifications: "Notifications",
              };
              return (
                <div key={cat} className="rounded-xl border border-zinc-800 bg-zinc-900/60 overflow-hidden">
                  <div className={`flex items-center gap-2 px-3 py-2 border-b border-zinc-800/80`}>
                    <Icon size={12} className={color} />
                    <p className="text-[10px] uppercase tracking-widest text-zinc-500">{catLabels[cat]}</p>
                    {items.length > 0 && (
                      <span className={`ml-auto text-[10px] px-1.5 rounded-full bg-zinc-800 ${color}`}>
                        {items.length}
                      </span>
                    )}
                  </div>
                  <div className="p-2 space-y-1.5">
                    {items.length === 0 && (
                      <p className="text-[11px] text-zinc-700 px-1 py-1">No updates</p>
                    )}
                    {items.slice(0, 3).map((item) => (
                      <div key={item.id} className="px-1">
                        <p className="text-[11px] text-zinc-300 truncate">{item.title}</p>
                        <p className="text-[10px] text-zinc-600 truncate">{item.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
