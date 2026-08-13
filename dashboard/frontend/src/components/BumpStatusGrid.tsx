import { useEffect, useState } from "react";
import type { BumpBotStatus, GuildBumpStats } from "../api/types";
// Same two helpers this file has always used; they moved to the shared
// overview formatter so the home-page tiles report timings identically.
import { formatDuration, formatRelative } from "./overview/format";

function BotCard({ bot, now }: { bot: BumpBotStatus; now: number }) {
  const ready = bot.status === "ready" || bot.next_due === null || now >= (bot.next_due ?? 0);
  const remaining = bot.next_due ? bot.next_due - now : 0;

  return (
    <article className={`bump-card${ready ? " bump-card--ready" : ""}`}>
      <header className="bump-card__head">
        <span className="bump-card__name">{bot.name}</span>
        <span className={`bump-badge ${ready ? "bump-badge--ready" : "bump-badge--wait"}`}>
          {ready ? "Ready now" : "Cooling down"}
        </span>
      </header>

      <div className="bump-card__timer">
        {ready ? (
          <span className="bump-card__ready-text">Bump available</span>
        ) : (
          <span className="bump-card__count">{formatDuration(remaining)}</span>
        )}
      </div>
      <div className="bump-card__sub">{ready ? "Ready to bump" : "until next bump"}</div>

      <dl className="bump-card__meta">
        <div>
          <dt>Last bumped</dt>
          <dd>{bot.last_bump ? formatRelative(bot.last_bump, now) : "Never"}</dd>
        </div>
        <div>
          <dt>Cooldown</dt>
          <dd>{formatDuration(bot.cooldown)}</dd>
        </div>
      </dl>
    </article>
  );
}

/** Per-guild bump status: summary header + one card per enabled bump bot.
 *  Countdowns tick every second, anchored to the server's clock to avoid skew. */
export default function BumpStatusGrid({ stats }: { stats: GuildBumpStats }) {
  // Offset (seconds) between this browser's clock and the server's, computed once.
  const [offset] = useState(() => Date.now() / 1000 - stats.server_time);
  const [now, setNow] = useState(() => Date.now() / 1000 - offset);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000 - offset), 1000);
    return () => clearInterval(id);
  }, [offset]);

  return (
    <div className="bump-stats">
      <div className="bump-summary">
        <span className="bump-summary__item">
          <strong>{stats.enabled_count}</strong> {stats.enabled_count === 1 ? "bot" : "bots"} tracked
        </span>
        <span className={`bump-chip ${stats.config_complete ? "bump-chip--ok" : "bump-chip--warn"}`}>
          {stats.config_complete ? "✓ Setup complete" : "⚠ Setup incomplete"}
        </span>
        {stats.premium && <span className="bump-chip bump-chip--premium">★ Premium</span>}
      </div>

      {stats.bots.length === 0 ? (
        <div className="empty-state" role="status">
          No bump bots enabled for this server yet. Open settings to add some.
        </div>
      ) : (
        <div className="bump-grid">
          {stats.bots.map((bot) => (
            <BotCard key={bot.key} bot={bot} now={now} />
          ))}
        </div>
      )}
    </div>
  );
}
