import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, inviteLink } from "../api/client";
import type { Guild, User } from "../api/types";
import { formatError } from "../utils/formatError";
import AppHeader from "../components/AppHeader";
import PageSkeleton from "../components/PageSkeleton";

function GuildIcon({ id, icon, name }: { id: string; icon: string | null; name: string }) {
  const [broken, setBroken] = useState(false);
  if (!icon || broken) return <span className="guild-icon-fallback">{name[0]?.toUpperCase()}</span>;
  return (
    <img
      src={`https://cdn.discordapp.com/icons/${id}/${icon}.png?size=64`}
      alt=""
      onError={() => setBroken(true)}
      loading="lazy"
    />
  );
}

export default function SettingsHubPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [u, g, invite] = await Promise.all([
          api.me(),
          api.guilds(),
          api.botInviteUrl().catch(() => ({ url: null })),
        ]);
        if (!alive) return;
        setUser(u);
        setGuilds(g);
        setInviteUrl(invite.url);
      } catch (e) {
        if (alive) setError(formatError(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  if (loading) return <PageSkeleton />;

  const manageable = guilds.filter((g) => g.panel_role && g.panel_role !== "none");

  return (
    <div className="app-layout">
      <AppHeader user={user} />
      <div style={{ padding: "0 24px 24px" }}>
        <section className="dash-hero">
          <div className="dash-hero__copy">
            <span className="dash-hero__eyebrow">Configuration</span>
            <h1 className="dash-hero__title">Settings</h1>
            <p className="dash-hero__sub">
              The servers you can manage. Pick one to set up its bump reminders.
            </p>
          </div>
        </section>

        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>{error}</div>
        )}

        {manageable.length === 0 ? (
          <div className="empty-state" role="status" style={{ marginTop: 24 }}>
            You need Manage Server permission (or a configured admin/mod role) in a server where
            Imperial Reminder is active to manage it.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 16 }}>
            {manageable.map((g) => (
              <div
                key={g.id}
                className="card"
                style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px" }}
              >
                <span className="guild-pill__icon">
                  <GuildIcon id={g.id} icon={g.icon} name={g.name} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <strong>{g.name}</strong>{" "}
                  <span className="badge">{g.panel_role === "admin" ? "Admin" : "Mod"}</span>
                </div>
                {g.setup_required ? (
                  inviteUrl && (
                    <a
                      className="btn btn-primary"
                      href={inviteLink(inviteUrl, g.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Invite the bot
                    </a>
                  )
                ) : (
                  <button className="btn btn-primary" onClick={() => navigate(`/settings/${g.id}`)}>
                    Open settings
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
