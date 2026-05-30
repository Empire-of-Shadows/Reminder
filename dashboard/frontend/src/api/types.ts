export interface User {
  id: string;
  username?: string | null;
  global_name?: string | null;
  avatar?: string | null;
  discriminator?: string | null;
}

export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  bot_in_guild: boolean;
  has_config: boolean;
  setup_required: boolean;
}

export interface Channel {
  id: string;
  name: string;
  type: number;
  position: number;
}

export interface Role {
  id: string;
  name: string;
  color: number;
  position: number;
}

export interface BumpBot {
  key: string;
  name: string;
}

/** Per-guild bump configuration (mirrors the dashboard settings API).
 * Snowflake IDs are strings ('' = unset) — they exceed JS's safe-integer range. */
export interface GuildSettings {
  guild_id?: string;
  enabled_bots: string[];
  bump_channel: string;
  bump_role: string;
  timers_channel: string;
  timers_message: boolean;
  custom_message: string;
  [key: string]: unknown;
}

export type SettingsResponse = GuildSettings;

export interface SettingsPatch {
  bump_channel?: string;
  bump_role?: string;
  enabled_bots?: string[];
  timers_channel?: string;
  timers_message?: boolean;
  custom_message?: string;
}

/** One bump bot's live status within a guild. Unix timestamps in seconds. */
export interface BumpBotStatus {
  key: string;
  name: string;
  last_bump: number | null;
  cooldown: number;
  next_due: number | null;
  status: "ready" | "waiting";
}

export interface GuildBumpStats {
  guild_id: string;
  premium: boolean;
  config_complete: boolean;
  enabled_count: number;
  /** Server's current unix time — anchor client countdowns to avoid clock skew. */
  server_time: number;
  bots: BumpBotStatus[];
}
