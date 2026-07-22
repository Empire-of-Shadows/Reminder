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
    const resp = await fetch(apiUrl("/api/stats/public"), { credentials: "omit" });
    if (!resp.ok) return null;
    return (await resp.json()) as PublicStats;
  } catch {
    return null;
  }
}
