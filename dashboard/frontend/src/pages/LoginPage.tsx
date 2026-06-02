import { useEffect, useState } from "react";
import { fetchPublicStats, type PublicStats } from "../api/client";

function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  return String(n);
}

export default function LoginPage() {
  const [stats, setStats] = useState<PublicStats | null>(null);

  useEffect(() => {
    let alive = true;
    fetchPublicStats().then((s) => {
      if (alive) setStats(s);
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <main className="login-main">
      <div className="login-hero">
        <h1>Imperial Reminder</h1>
        <p className="tagline">
          Sign in with Discord to manage your server's bump reminders. Your Empire of Shadows
          session is shared — one login covers every bot dashboard.
        </p>
        <a href="/auth/discord" className="cta">
          Login with Discord
        </a>

        <div className="login-divider">Explore the ecosystem</div>

        <div className="login-tiles">
          <a className="tile-button" href="https://eosofficial.club" target="_blank" rel="noopener noreferrer">
            <span className="tile-title">Main Site</span>
            <span className="tile-desc">Empire of Shadows hub — news, links, community.</span>
          </a>
          <a className="tile-button" href="https://host.eosofficial.club" target="_blank" rel="noopener noreferrer">
            <span className="tile-title">TheHost</span>
            <span className="tile-desc">Games and stats dashboard for TheHost bot.</span>
          </a>
        </div>

        {stats && (
          <div className="login-stats">
            <span>
              <span className="stat-num">{formatCount(stats.servers)}</span>servers
            </span>
            <span className="stat-sep">·</span>
            <span>
              <span className="stat-num">{formatCount(stats.bots_tracked)}</span>bots tracked
            </span>
            <span className="stat-sep">·</span>
            <span>
              <span className="stat-num">{formatCount(stats.premium_servers)}</span>premium
            </span>
          </div>
        )}
      </div>
      <div className="login-below" />
    </main>
  );
}
