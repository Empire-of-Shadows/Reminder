import type {
  User,
  Guild,
  Channel,
  Role,
  BumpBot,
  SettingsResponse,
  SettingsPatch,
  GuildSettings,
  GuildBumpStats,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 15000;
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let _csrfToken: string | null = null;
let _csrfInFlight: Promise<string | null> | null = null;

async function fetchCsrfToken(): Promise<string | null> {
  const res = await fetch(`${API_BASE}/auth/csrf`, { credentials: "include" });
  if (res.status === 401) return null;
  if (!res.ok) return null;
  const body = (await res.json().catch(() => ({}))) as { csrf_token?: string };
  return body.csrf_token ?? null;
}

async function ensureCsrf(force = false): Promise<string | null> {
  if (force) _csrfToken = null;
  if (_csrfToken) return _csrfToken;
  if (!_csrfInFlight) {
    _csrfInFlight = fetchCsrfToken().finally(() => {
      _csrfInFlight = null;
    });
  }
  const token = await _csrfInFlight;
  if (token) _csrfToken = token;
  return token;
}

function buildUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path}`;
}

async function rawFetch(url: string, init: RequestInit): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), DEFAULT_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const isUnsafe = UNSAFE_METHODS.has(method);
  const url = buildUrl(path);

  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (isUnsafe) {
    const token = await ensureCsrf();
    if (token) baseHeaders["X-CSRF-Token"] = token;
  }

  let res: Response;
  try {
    res = await rawFetch(url, {
      credentials: "include",
      ...init,
      method,
      headers: baseHeaders,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw e;
  }

  if (isUnsafe && res.status === 403) {
    const body = await res.clone().json().catch(() => ({}));
    const detail = String(body?.detail ?? "");
    if (/csrf/i.test(detail)) {
      const token = await ensureCsrf(true);
      if (token) {
        baseHeaders["X-CSRF-Token"] = token;
        res = await rawFetch(url, {
          credentials: "include",
          ...init,
          method,
          headers: baseHeaders,
        });
      }
    }
  }

  if (res.status === 401) {
    _csrfToken = null;
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  me: () => apiFetch<User>("/api/me"),
  guilds: () => apiFetch<Guild[]>("/api/guilds"),
  botInviteUrl: () => apiFetch<{ url: string | null }>("/api/bot-invite-url"),
  bumpBots: () => apiFetch<BumpBot[]>("/api/bump-bots"),

  getChannels: (guildId: string) =>
    apiFetch<Channel[]>(`/api/guilds/${guildId}/channels`),
  getRoles: (guildId: string) =>
    apiFetch<Role[]>(`/api/guilds/${guildId}/roles`),

  settings: (guildId: string) =>
    apiFetch<SettingsResponse>(`/api/guilds/${guildId}/settings`),
  saveSettings: (guildId: string, patch: SettingsPatch) =>
    apiFetch<GuildSettings>(`/api/guilds/${guildId}/settings`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  guildBumpStats: (guildId: string) =>
    apiFetch<GuildBumpStats>(`/api/guilds/${guildId}/bump-stats`),
};

/** Build the bot-invite link for a specific guild (explicit click, no popup). */
export function inviteLink(baseUrl: string, guildId: string): string {
  return `${baseUrl}&guild_id=${guildId}`;
}

export interface PublicStats {
  servers: number;
  bots_tracked: number;
  premium_servers: number;
}

export async function fetchPublicStats(): Promise<PublicStats | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/stats/public`, { credentials: "omit" });
    if (!resp.ok) return null;
    return (await resp.json()) as PublicStats;
  } catch {
    return null;
  }
}
