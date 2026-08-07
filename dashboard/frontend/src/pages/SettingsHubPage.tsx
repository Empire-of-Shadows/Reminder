import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, inviteLink } from "../api/client";
import type { Guild, User } from "../api/types";
import { formatError } from "../_engine/api/formatError";
import AppHeader from "../components/AppHeader";
import { GuildWeb } from "../components/GuildWeb";

export default function SettingsHubPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[] | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch(() => {});
    api.guilds().then(setGuilds).catch((e) => setError(formatError(e)));
    api.botInviteUrl().then((r) => setInviteUrl(r.url)).catch(() => {});
  }, []);

  // Client guard: only admins reach Settings; everyone else has no Settings nav
  // link. Server-side routes re-check access on their own.
  useEffect(() => {
    if (user && !user.can_access_settings_any) navigate("/dashboard", { replace: true });
  }, [user, navigate]);

  const webGuilds = useMemo(
    () => (guilds ?? []).filter((g) => g.panel_role && g.panel_role !== "none"),
    [guilds],
  );
  const counts = useMemo(() => ({
    total: webGuilds.length,
    admin: webGuilds.filter((g) => g.panel_role === "admin").length,
  }), [webGuilds]);
  const selected = webGuilds.find((g) => g.id === selectedId) ?? null;

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <section className="dash-hero">
        <div className="dash-hero__orb" />
        <img className="dash-hero__sigil" src="/brand/artifact-belltower.svg" alt="" />
        <div className="dash-hero__copy">
          <span className="dash-hero__eyebrow">Configuration</span>
          <h1 className="dash-hero__title">The Web of Servers</h1>
          <p className="dash-hero__sub">
            Every server you steward, woven together. Pluck a node to manage it.
          </p>
        </div>
        <div className="dash-hero__strip">
          <div className="empire-stat">
            <div className="empire-stat__value">{counts.total}</div>
            <div className="empire-stat__label">Servers</div>
          </div>
          <div className="empire-stat">
            <div className="empire-stat__value">{counts.admin}</div>
            <div className="empire-stat__label">Admin</div>
          </div>
        </div>
      </section>

      <div style={{ padding: "0 24px 24px" }}>
        {error ? (
          <div className="alert danger" role="alert">{error}</div>
        ) : !guilds ? (
          <p className="muted">Loading servers...</p>
        ) : webGuilds.length === 0 ? (
          <div className="card">
            <h3>No manageable servers</h3>
            <p className="muted">
              You need Manage Server permission (or a configured admin role) in a Discord
              server to manage Imperial Reminder.
              {inviteUrl && (
                <>
                  {" "}
                  <a href={inviteUrl} target="_blank" rel="noreferrer">
                    Invite Imperial Reminder to a server
                  </a>.
                </>
              )}
            </p>
          </div>
        ) : (
          <div className="guild-web-layout">
            <GuildWeb guilds={webGuilds} selectedId={selectedId} onSelect={setSelectedId} />
            <SettingsActionPanel
              guild={selected}
              inviteUrl={inviteUrl}
              onNavigate={(path) => navigate(path)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function SettingsActionPanel({
  guild,
  inviteUrl,
  onNavigate,
}: {
  guild: Guild | null;
  inviteUrl: string | null;
  onNavigate: (path: string) => void;
}) {
  if (!guild) {
    return (
      <aside className="card guild-web__panel guild-web__panel--empty">
        <p className="muted" style={{ margin: 0 }}>Select a server node to manage it.</p>
      </aside>
    );
  }

  const iconUrl = guild.icon
    ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=64`
    : null;

  return (
    <aside className="card guild-web__panel">
      <div className="guild-web__panel-head">
        <div className="guild-icon" style={{ width: 44, height: 44 }}>
          {iconUrl ? <img src={iconUrl} alt="" /> : (guild.name ?? "?")[0]}
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            className="guild-name"
            style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {guild.name}
          </div>
          <span className="status-badge status-badge--approved">Admin</span>
        </div>
      </div>

      <div className="guild-web__panel-actions">
        {!guild.bot_in_guild ? (
          inviteUrl && (
            <a
              className="btn btn-primary"
              href={inviteLink(inviteUrl, guild.id)}
              target="_blank"
              rel="noopener noreferrer"
            >
              Invite Imperial Reminder
            </a>
          )
        ) : (
          <button className="btn btn-primary" onClick={() => onNavigate(`/settings/${guild.id}`)}>
            Settings
          </button>
        )}
      </div>

      {!guild.bot_in_guild && (
        <p className="guild-invite-hint" style={{ marginTop: 0 }}>
          Bot not in this server yet. Use the link above to add it, then return here.
        </p>
      )}
      {guild.bot_in_guild && !guild.has_config && (
        <p className="guild-invite-hint" style={{ marginTop: 0 }}>
          Not set up yet - open settings to pick a bump channel and reminder role.
        </p>
      )}
    </aside>
  );
}
