import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { User, Guild } from "../api/types";
import { formatError } from "../utils/formatError";
import AppHeader from "../components/AppHeader";
import PageSkeleton from "../components/PageSkeleton";

function GuildIcon({ id, icon, name }: { id: string; icon: string | null; name: string }) {
  const [broken, setBroken] = useState(false);
  if (!icon || broken) {
    return <span className="guild-icon-fallback">{name[0]?.toUpperCase()}</span>;
  }
  return (
    <img
      src={`https://cdn.discordapp.com/icons/${id}/${icon}.png?size=96`}
      alt=""
      onError={() => setBroken(true)}
      loading="lazy"
    />
  );
}

export default function DashboardPage() {
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
    return () => {
      alive = false;
    };
  }, []);

  function handleGuildClick(g: Guild) {
    if (g.bot_in_guild) {
      navigate(`/settings/${g.id}`);
    } else if (inviteUrl) {
      window.open(`${inviteUrl}&guild_id=${g.id}`, "_blank", "noopener");
    }
  }

  if (loading) return <PageSkeleton />;

  return (
    <div className="app-layout">
      <AppHeader user={user} />
      <div style={{ padding: "0 24px 24px" }}>
        <h2 className="section-title" style={{ margin: "24px 0 16px" }}>
          Your Servers
        </h2>

        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}

        {!error && guilds.length === 0 ? (
          <p style={{ color: "var(--text-muted)" }}>
            No servers found where you have Manage Server permission.
          </p>
        ) : (
          <div className="guild-grid">
            {guilds.map((g) => (
              <div
                key={g.id}
                className={`card guild-card${g.setup_required ? " guild-card--setup" : ""}`}
                onClick={() => handleGuildClick(g)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") handleGuildClick(g);
                }}
              >
                <div className="guild-icon">
                  <GuildIcon id={g.id} icon={g.icon} name={g.name} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="guild-name">{g.name}</div>
                  {g.setup_required && (
                    <div className="guild-invite-hint">Bot not installed — click to invite</div>
                  )}
                </div>
                {g.setup_required && <div className="guild-invite-badge">Invite</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
