import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { User } from "../api/types";
import AppHeader from "../components/AppHeader";

export default function PrivacyPage() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch(() => {});
  }, []);

  return (
    <div className="app-layout">
      <AppHeader user={user} />
      <div style={{ padding: "0 24px 24px" }}>
        <section className="dash-hero">
          <div className="dash-hero__copy">
            <span className="dash-hero__eyebrow">Your Data</span>
            <h1 className="dash-hero__title">Privacy</h1>
            <p className="dash-hero__sub">
              What Imperial Reminder stores, and what it doesn't.
            </p>
          </div>
        </section>

        <section className="section card" style={{ marginTop: 16 }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>No personal tracking</h2>
          <p className="muted">
            Imperial Reminder is a bump-reminder bot. It does <strong>not</strong> track
            individual members — no messages, no activity, no profiles. There's nothing
            personal to opt out of.
          </p>
        </section>

        <section className="section card" style={{ marginTop: 16 }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>What it does store</h2>
          <p className="muted">For each server, the bot keeps only its setup:</p>
          <ul className="muted" style={{ marginTop: 0 }}>
            <li>Which bump bots to track and when each was last bumped</li>
            <li>The bump channel, the reminder role to ping, and the timers channel</li>
            <li>Your custom reminder message, and which roles can manage these settings</li>
          </ul>
          <p className="muted">
            Server managers can change all of this any time on the <strong>Settings</strong> page.
          </p>
        </section>

        <section className="section card" style={{ marginTop: 16 }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>Signing in</h2>
          <p className="muted">
            Logging in uses Discord to confirm who you are and which servers you can manage.
            That sign-in session is shared across the Empire of Shadows dashboards and expires
            on its own. Logging out clears it.
          </p>
        </section>
      </div>
    </div>
  );
}
