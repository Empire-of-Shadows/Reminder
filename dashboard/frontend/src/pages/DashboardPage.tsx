import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { api, fetchPublicStats, inviteLink, type PublicStats } from "../api/client";
import type { Guild, GuildOverview, User } from "../api/types";
import { formatError } from "../_engine/api/formatError";
import { formatCount } from "../_engine/format";
import ServerPicker, { pickerMeta } from "../_engine/components/overview/ServerPicker";
import SignalStrip, { type Signal } from "../_engine/components/overview/SignalStrip";
import AppHeader from "../components/AppHeader";
import PageSkeleton from "../components/PageSkeleton";
import AdminOverview from "../components/overview/AdminOverview";
import { formatCountdown, formatRelative } from "../components/overview/format";

/*
 * The dashboard home.
 *
 * What this replaced: a horizontally-scrolling pill bar of servers over one
 * grid of bump cards, with no width cap - on a wide monitor the cards held a
 * countdown in a box the width of the screen, and nothing on the page answered
 * "is any of this actually working". The layout is now the shared engine one:
 * a command row (which server, and the numbers that are only numbers) above a
 * 12-column grid of tiles, fed by a single per-guild overview request.
 */

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
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<Guild[]>([]);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const selectedGuildId = searchParams.get("guild");
  const [overview, setOverview] = useState<GuildOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  // The ?guild= value the page was opened with. A shared link always wins over
  // the default-to-your-own-server behaviour below.
  const openedWith = useRef<string | null>(searchParams.get("guild"));

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
        if (!openedWith.current) {
          // Land on a server the bot is actually in, so the page has something
          // to say on arrival. Written with replace, so the URL stays shareable.
          const own = g.find((entry) => entry.bot_in_guild && !entry.setup_required);
          if (own) selectGuild(own.id);
        }
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
    // Runs once: the initial guild comes from the URL, captured above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedGuild = useMemo(
    () => (selectedGuildId ? guilds.find((g) => g.id === selectedGuildId) ?? null : null),
    [guilds, selectedGuildId],
  );

  // Fetch the selected server's overview whenever the selection changes.
  useEffect(() => {
    if (!selectedGuildId || !selectedGuild || selectedGuild.setup_required) {
      setOverview(null);
      setOverviewError(null);
      return;
    }
    let alive = true;
    setOverviewLoading(true);
    setOverviewError(null);
    api
      .guildOverview(selectedGuildId)
      .then((data) => {
        if (alive) setOverview(data);
      })
      .catch((e) => {
        if (!alive) return;
        setOverview(null);
        if ((e as Error).message === "Unauthorized") return;
        setOverviewError(formatError(e, "Could not load this server."));
      })
      .finally(() => {
        if (alive) setOverviewLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [selectedGuildId, selectedGuild]);

  if (loading) return <PageSkeleton />;

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <div className="page">
        <StatsHero stats={stats} />

        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        {guilds.length > 0 && (
          <div className="ov-command">
            <ServerPicker
              guilds={guilds}
              selectedGuildId={selectedGuildId}
              onSelect={selectGuild}
              meta={pickerMeta(selectedGuild, guilds.length, "Imperial Reminder")}
            />
            <SignalStrip signals={signalsFor(overview)} />
          </div>
        )}

        {guilds.length === 0 ? (
          <QuietCard title="No servers">
            {error
              ? "Your servers could not be loaded just now."
              : "No servers found where you have Manage Server permission, or a role that manages Imperial Reminder."}
          </QuietCard>
        ) : !selectedGuild ? (
          <QuietCard title="Pick a server">
            Choose a server above to see its bump timers and setup.
          </QuietCard>
        ) : selectedGuild.setup_required ? (
          <QuietCard title="Not added yet" chip="Bot missing">
            <p className="ov-body">
              Imperial Reminder is not in <strong>{selectedGuild.name}</strong> yet. Add it, then
              come back here to set the bump channel and reminder role.
            </p>
            {inviteUrl && (
              <div className="admin-actions">
                <a
                  className="btn btn-primary"
                  href={inviteLink(inviteUrl, selectedGuild.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Invite the bot
                </a>
              </div>
            )}
          </QuietCard>
        ) : overviewLoading ? (
          <div className="ov-grid" role="status" aria-busy="true">
            <div className="skeleton-card s12" />
            <div className="skeleton-card s12" />
            <div className="skeleton-card s4" />
            <div className="skeleton-card s3" />
            <div className="skeleton-card s5" />
            <span className="visually-hidden">Loading this server</span>
          </div>
        ) : overviewError ? (
          <QuietCard title="Not loaded">
            <p className="ov-body" role="alert">
              {overviewError}
            </p>
          </QuietCard>
        ) : overview ? (
          <AdminOverview overview={overview} />
        ) : (
          <QuietCard title="Nothing to show">
            This server has no bump data yet.
          </QuietCard>
        )}
      </div>
    </div>
  );
}

/** A single dashed full-width tile, for the states that are not an overview. */
function QuietCard({
  title,
  chip,
  children,
}: {
  title: string;
  chip?: string;
  children: ReactNode;
}) {
  return (
    <div className="ov-grid">
      <section className="ov-card ov-card--quiet s12">
        <div className="ov-card__head">
          <span className="ov-card__title">{title}</span>
          {chip && <span className="ov-chip ov-chip--warn">{chip}</span>}
        </div>
        {typeof children === "string" ? <p className="ov-body">{children}</p> : children}
      </section>
    </div>
  );
}

/* ── The command-row numbers ───────────────────────────────────────── */

function signalsFor(overview: GuildOverview | null): Signal[] {
  if (!overview) return [];
  const bumps = overview.bumps;
  const premium = overview.premium;

  const signals: Signal[] = [
    {
      key: "tracked",
      value: bumps ? formatCount(bumps.enabled_count) : "-",
      label: "Bots tracked",
    },
    {
      key: "ready",
      value: bumps ? formatCount(bumps.ready_count) : "-",
      label: "Ready to bump",
    },
    {
      key: "next",
      value:
        bumps && bumps.next_due !== null
          ? formatCountdown(bumps.next_due, bumps.now).replace(/^in /, "")
          : "-",
      label: bumps && bumps.next_due !== null ? "Until next bump" : "Next bump - none due",
    },
    {
      key: "last",
      value: bumps && bumps.last_bump !== null ? formatRelative(bumps.last_bump, bumps.now) : "-",
      label: bumps && bumps.last_bump !== null ? "Last bump" : "Last bump - none seen",
    },
  ];

  if (premium?.is_premium) {
    signals.push({ key: "premium", value: premium.tier ?? "Yes", label: "Premium" });
  }

  return signals;
}
