import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, fetchPublicStats, type PublicStats } from "../api/client";
import type { User, Guild, GuildBumpStats } from "../api/types";
import { formatError } from "../utils/formatError";
import AppHeader from "../components/AppHeader";
import PageSkeleton from "../components/PageSkeleton";
import BumpStatusGrid from "../components/BumpStatusGrid";

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

function GuildIcon({ id, icon, name, size = 96 }: { id: string; icon: string | null; name: string; size?: number }) {
  const [broken, setBroken] = useState(false);
  if (!icon || broken) {
    return <span className="guild-icon-fallback">{name[0]?.toUpperCase()}</span>;
  }
  return (
    <img
      src={`https://cdn.discordapp.com/icons/${id}/${icon}.png?size=${size}`}
      alt=""
      onError={() => setBroken(true)}
      loading="lazy"
    />
  );
}

function StatsHero({ stats }: { stats: PublicStats | null }) {
  return (
    <section className="dash-hero">
      <div className="dash-hero__copy">
        <span className="dash-hero__eyebrow">Empire Overview</span>
        <h1 className="dash-hero__title">Imperial Reminder</h1>
        <p className="dash-hero__sub">
          {stats ? (
            <>
              Keeping <strong>{formatCount(stats.bots_tracked)}</strong> bump bots on schedule
              across {formatCount(stats.servers)} servers.
            </>
          ) : (
            <>Never miss a bump again.</>
          )}
        </p>
      </div>
      {stats && (
        <div className="dash-hero__strip">
          <div className="empire-stat">
            <div className="empire-stat__value">{formatCount(stats.servers)}</div>
            <div className="empire-stat__label">Servers</div>
          </div>
          <div className="empire-stat">
            <div className="empire-stat__value">{formatCount(stats.bots_tracked)}</div>
            <div className="empire-stat__label">Bots Tracked</div>
          </div>
          <div className="empire-stat">
            <div className="empire-stat__value">{formatCount(stats.premium_servers)}</div>
            <div className="empire-stat__label">Premium Servers</div>
          </div>
        </div>
      )}
    </section>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const selectedGuildId = searchParams.get("guild");
  const [bumpStats, setBumpStats] = useState<GuildBumpStats | null>(null);
  const [bumpLoading, setBumpLoading] = useState(false);

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
    fetchPublicStats().then((s) => {
      if (alive) setStats(s);
    });
    return () => {
      alive = false;
    };
  }, []);

  // Fetch the selected guild's bump status whenever the selection changes.
  useEffect(() => {
    if (!selectedGuildId) {
      setBumpStats(null);
      return;
    }
    let alive = true;
    setBumpLoading(true);
    api
      .guildBumpStats(selectedGuildId)
      .then((s) => {
        if (alive) setBumpStats(s);
      })
      .catch(() => {
        if (alive) setBumpStats(null);
      })
      .finally(() => {
        if (alive) setBumpLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedGuildId]);

  function selectGuild(id: string | null) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id) next.set("guild", id);
        else next.delete("guild");
        return next;
      },
      { replace: true },
    );
  }

  function handleGuildClick(g: Guild) {
    if (g.bot_in_guild) {
      navigate(`/settings/${g.id}`);
    } else if (inviteUrl) {
      window.open(`${inviteUrl}&guild_id=${g.id}`, "_blank", "noopener");
    }
  }

  if (loading) return <PageSkeleton />;

  // Pills = guilds where the bot is installed (those have bump stats to show).
  const installedGuilds = guilds.filter((g) => g.bot_in_guild);
  const selectedGuild = selectedGuildId
    ? guilds.find((g) => g.id === selectedGuildId) ?? null
    : null;

  return (
    <div className="app-layout">
      <AppHeader user={user} />
      <div style={{ padding: "0 24px 24px" }}>
        <StatsHero stats={stats} />

        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        {installedGuilds.length > 0 && (
          <div className="guild-filter-bar">
            <button
              className={`guild-pill${selectedGuildId === null ? " active" : ""}`}
              onClick={() => selectGuild(null)}
            >
              All Servers
            </button>
            {installedGuilds.map((g) => (
              <button
                key={g.id}
                className={`guild-pill${selectedGuildId === g.id ? " active" : ""}`}
                onClick={() => selectGuild(g.id)}
              >
                <span className="guild-pill__icon">
                  <GuildIcon id={g.id} icon={g.icon} name={g.name} size={32} />
                </span>
                {g.name}
              </button>
            ))}
          </div>
        )}

        {selectedGuild ? (
          <>
            <div className="dash-section-head">
              <h2 className="section-title" style={{ margin: 0 }}>
                {selectedGuild.name}
              </h2>
              <button className="btn btn-secondary" onClick={() => navigate(`/settings/${selectedGuild.id}`)}>
                Manage settings
              </button>
            </div>
            {bumpLoading ? (
              <div className="bump-grid" aria-busy="true">
                <div className="skeleton-card" />
                <div className="skeleton-card" />
                <div className="skeleton-card" />
              </div>
            ) : bumpStats ? (
              <BumpStatusGrid stats={bumpStats} />
            ) : (
              <div className="empty-state" role="status">
                Couldn't load bump status for this server.
              </div>
            )}
          </>
        ) : (
          <>
            <h2 className="section-title" style={{ margin: "24px 0 16px" }}>
              Your Servers
            </h2>
            {!error && guilds.length === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>
                No servers found where you have Manage Server permission.
              </p>
            ) : (
              <div className="guild-grid" style={{ padding: 0 }}>
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
          </>
        )}
      </div>
    </div>
  );
}
