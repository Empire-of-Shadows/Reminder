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
  GuildOverview,
  ScopeGuild,
  DeleteUserDataResponse,
} from "./types";
import { apiFetch, apiUrl } from "../_engine/api/http";

// Re-export the shared transport surface so pages keep importing from "./api/client".
export {
  UnauthorizedError,
  ApiError,
  TimeoutError,
  discordLoginUrl,
  logoutUrl,
} from "../_engine/api/http";

export const api = {
  // suppressAuthHandler: the "am I logged in?" probe. Public pages (privacy)
  // call this to show login state - a 401 there is a valid answer, not a
  // session expiry, and must not bounce the visitor to /login.
  me: () => apiFetch<User>("/api/me", { suppressAuthHandler: true }),
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

  // Everything the dashboard home renders for one server, in one round trip.
  guildOverview: (guildId: string) =>
    apiFetch<GuildOverview>(`/api/guilds/${guildId}/overview`),

  // The bump half of the overview on its own. Kept as a public endpoint - the
  // home page now reads it through /overview, so nothing in the SPA calls this.
  guildBumpStats: (guildId: string) =>
    apiFetch<GuildBumpStats>(`/api/guilds/${guildId}/bump-stats`),

  // Privacy page (mirrors TheHost's /api/user/* surface).
  userGuilds: (withData = false) =>
    apiFetch<ScopeGuild[]>(`/api/user/guilds${withData ? "?with_data=true" : ""}`),
  exportUserDataUrl: (guildId?: string | null) =>
    apiUrl(
      guildId
        ? `/api/user/data/export?guild_id=${encodeURIComponent(guildId)}`
        : "/api/user/data/export",
    ),
  deleteUserData: (guildId?: string | null) =>
    apiFetch<DeleteUserDataResponse>("/api/user/data", {
      method: "DELETE",
      body: JSON.stringify({ confirm: true, guild_id: guildId ?? null }),
    }),
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
    const resp = await fetch(apiUrl("/api/stats/public"), { credentials: "omit" });
    if (!resp.ok) return null;
    return (await resp.json()) as PublicStats;
  } catch {
    return null;
  }
}
