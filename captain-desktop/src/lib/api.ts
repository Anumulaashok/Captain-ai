const BASE = "http://127.0.0.1:8765";

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export async function del(path: string): Promise<void> {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

/** Stream chat with SSE — yields individual events */
export async function* streamChat(
  message: string,
  conversationId?: string
): AsyncGenerator<{ type: string; data: Record<string, unknown> }> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
  if (!r.ok) throw new Error(`Chat error: ${r.status}`);

  const reader = r.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const payload = line.slice(6);
        if (payload === "[DONE]") return;
        try {
          yield JSON.parse(payload);
        } catch {
          // ignore malformed chunks
        }
      }
    }
  }
}

// ── Typed API methods ──────────────────────────────────────────────

export const api = {
  health: () => get<{ status: string; ollama: boolean; pinecone: boolean; active_model: string }>("/health"),

  conversations: {
    list: () => get<Conversation[]>("/api/conversations"),
    get: (id: string) => get<Conversation>(`/api/conversations/${id}`),
    create: () => post<{ id: string }>("/api/conversations"),
    delete: (id: string) => del(`/api/conversations/${id}`),
  },

  agents: {
    list: () => get<Agent[]>("/api/agents"),
    enable: (id: string) => post(`/api/agents/${id}/enable`),
    disable: (id: string) => post(`/api/agents/${id}/disable`),
    run: (id: string, message: string) => post(`/api/agents/${id}/run`, { message }),
    getPermissions: (id: string) => get<{ permissions: string[] }>(`/api/agents/${id}/permissions`),
    setPermissions: (id: string, permissions: string[]) =>
      post(`/api/agents/${id}/permissions`, { permissions }),
  },

  models: {
    list: () => get<ModelEntry[]>("/api/models"),
    catalog: () => get<ModelCatalogEntry[]>("/api/models/catalog"),
    active: () => get<{ model_id: string }>("/api/models/active"),
    activate: (id: string) => post(`/api/models/${id}/activate`),
    delete: (id: string) => del(`/api/models/${id}`),
    storage: () => get<StorageInfo>("/api/models/storage"),
  },

  memory: {
    search: (q: string) => get<MemoryEntry[]>(`/api/memory?q=${encodeURIComponent(q)}`),
    recent: () => get<MemoryEntry[]>("/api/memory"),
    create: (entry: { type: string; key?: string; value: string; source?: string }) =>
      post<{ id: string }>("/api/memory", entry),
    delete: (id: string) => del(`/api/memory/${id}`),
    stats: () => get<MemoryStats>("/api/memory/stats"),
  },

  settings: {
    get: () => get<Record<string, unknown>>("/api/settings"),
    update: (updates: Record<string, unknown>) => put<Record<string, unknown>>("/api/settings", updates),
  },

  accounts: {
    getAll: () => get<AccountsStatus>("/api/accounts"),
    addCloudKey: (service: string, apiKey: string) =>
      post("/api/accounts/cloud-key", { service, api_key: apiKey }),
    removeCloudKey: (service: string) => del(`/api/accounts/cloud-key/${service}`),
  },

  voice: {
    setMode: (mode: string, conversationId?: string) =>
      post("/api/voice/mode", { mode, conversation_id: conversationId }),
    getMode: () => get<{ mode: string }>("/api/voice/mode"),
    speak: (text: string) => post<{ audio_base64: string }>("/api/voice/speak", { text }),
  },
};

// ── Types ──────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  model_id: string | null;
  messages?: Message[];
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at: string;
  tokens_used?: number;
  latency_ms?: number;
  meta?: Record<string, unknown>;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  capabilities: string[];
  required_permissions: string[];
  health: "healthy" | "degraded" | "unhealthy";
  is_enabled: boolean;
}

export interface ModelEntry {
  id: string;
  name: string;
  provider: string;
  size_gb: number;
  ram_required_gb: number;
  quantization: string;
  description: string;
  recommended_for: string[];
  quality_stars: number;
  is_downloaded: boolean;
  is_active: boolean;
  performance_tps?: number;
}

export interface ModelCatalogEntry extends ModelEntry {}

export interface StorageInfo {
  installed_count: number;
  total_gb: number;
  models: Array<{ name: string; size_gb: number }>;
}

export interface MemoryEntry {
  id: string;
  type: string;
  key?: string;
  value: string;
  source?: string;
  score?: number;
  created_at?: string;
}

export interface MemoryStats {
  total_entries: number;
  pinecone: {
    configured: boolean;
    index_name?: string;
    total_vectors?: number;
  };
}

export interface AccountService {
  status: "connected" | "running" | "stopped" | "configured" | "not_configured" | "error";
  provider: string;
  type: string;
  error?: string;
  index?: string;
  vectors?: number;
  active_model?: string;
  installed_models?: number;
  source?: string;
}

export interface AccountsStatus {
  local: AccountService[];
  cloud: AccountService[];
}
