import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, inviteLink } from "../api/client";
import type { Guild, User } from "../api/types";
import { formatError } from "../_engine/api/formatError";
import AppHeader from "../components/AppHeader";
import { GuildWebScene } from "../_engine/components/GuildWebScene";

/** Real Discord icon for a guild, or null so the scene draws its generated orb.
 *  Typed on the two fields it reads rather than on this bot's Guild, so it also
 *  satisfies the scene's callback, which hands over the wider engine Guild. */
function guildIconUrl(g: { id: string; icon: string | null }): string | null {
  return g.icon ? `https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=64` : null;
}

export default function SettingsHubPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[] | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // The scene draws its tether to this element, so the panel has to be a real
  // node in the layout even while it is closed.
  const blobRef = useRef<HTMLElement>(null);

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
    () => (guilds ?? []).filter((g) => g.panel_role !== "none"),
    [guilds],
  );
  const counts = useMemo(() => ({
    total: webGuilds.length,
    admin: webGuilds.filter((g) => g.panel_role === "admin").length,
  }), [webGuilds]);
  const selected = webGuilds.find((g) => g.id === selectedId) ?? null;

  const message = error ? (
    <div className="alert danger" role="alert">{error}</div>
  ) : !guilds ? (
    <p className="eos-muted">Loading servers...</p>
  ) : webGuilds.length === 0 ? (
    <div className="card">
      <h3>No manageable servers</h3>
      <p className="eos-muted">
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
  ) : null;

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <div className="settings-scene">
        {message ? (
          <div className="settings-scene__message">{message}</div>
        ) : (
          <>
            <GuildWebScene
              guilds={webGuilds}
              selectedId={selectedId}
              onSelect={setSelectedId}
              tetherTo={blobRef}
              iconUrl={guildIconUrl}
              hubIcon="/brand/logo-mark.png"
            >
              <span className="gw-eyebrow">Configuration</span>
              <h1 className="gw-title" data-gw-collide>The Web of Servers</h1>
              <p className="gw-sub" data-gw-collide>
                Every server you steward, woven together. Pluck a node to manage it.
              </p>
              <p className="gw-counts">
                {counts.total} servers - {counts.admin} admin
              </p>
            </GuildWebScene>

            <aside
              ref={blobRef}
              className={"gw-blob" + (selected ? " is-show" : "")}
              aria-live="polite"
            >
              {selected && (
                <>
                  <button
                    type="button"
                    className="gw-blob-close"
                    aria-label="Close"
                    onClick={() => setSelectedId(null)}
                  >
                    x
                  </button>
                  <SettingsActionPanel
                    guild={selected}
                    inviteUrl={inviteUrl}
                    onNavigate={(path) => navigate(path)}
                  />
                </>
              )}
            </aside>
          </>
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
  guild: Guild;
  inviteUrl: string | null;
  onNavigate: (path: string) => void;
}) {
  const iconUrl = guildIconUrl(guild);

  return (
    <>
      <div className="settings-blob__head">
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

      <div className="settings-blob__actions">
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
    </>
  );
}
