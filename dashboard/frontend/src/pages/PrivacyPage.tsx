import { useEffect, useState } from "react";
import { api, discordLoginUrl } from "../api/client";
import type { User, ScopeGuild } from "../api/types";
import { formatError } from "../_engine/api/formatError";
import AppHeader from "../components/AppHeader";

export default function PrivacyPage() {
  const [user, setUser] = useState<User | null>(null);
  const [checkedAuth, setCheckedAuth] = useState(false);
  const [guilds, setGuilds] = useState<ScopeGuild[]>([]);
  const [scopeGuildId, setScopeGuildId] = useState<string>("");
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [erasing, setErasing] = useState(false);
  const [eraseResult, setEraseResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .me()
      .then((me) => {
        setUser(me);
        setCheckedAuth(true);
        return api.userGuilds(true);
      })
      .then((g) => setGuilds(g ?? []))
      .catch(() => setCheckedAuth(true));
  }, []);

  const scopeGuild = guilds.find((g) => g.id === scopeGuildId) ?? null;
  const scopeLabel = scopeGuild ? (scopeGuild.name ?? `Server ${scopeGuild.id}`) : "all servers";

  async function runErase() {
    setError(null);
    setEraseResult(null);
    setErasing(true);
    try {
      const r = await api.deleteUserData(scopeGuildId || null);
      const total = Object.values(r.deleted).reduce((a, n) => a + n, 0);
      const where = scopeGuild ? `in ${scopeLabel}` : "across all servers";
      setEraseResult(
        total === 0
          ? `Nothing to erase ${where} - no records name you.`
          : `Removed your name and ID from ${total} record${total === 1 ? "" : "s"} ${where}.`,
      );
      setShowDeleteModal(false);
      setConfirmText("");
      setGuilds(await api.userGuilds(true));
    } catch (e) {
      setError(formatError(e));
      setShowDeleteModal(false);
    } finally {
      setErasing(false);
    }
  }

  return (
    <div className="app-layout privacy-page">
      <AppHeader user={user} />
      <div style={{ padding: "0 24px 24px" }}>
        <section className="dash-hero">
          <div className="dash-hero__copy">
            <span className="dash-hero__eyebrow">Account Control</span>
            <h1 className="dash-hero__title">Privacy &amp; Data</h1>
            <p className="dash-hero__sub">
              What Imperial Reminder stores, and how to take it back.
            </p>
          </div>
        </section>

        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        <section className="section card" style={{ marginTop: 16 }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>No personal tracking</h2>
          <p className="muted">
            Imperial Reminder is a bump-reminder bot. It does <strong>not</strong> track
            individual members - no messages, no activity, no profiles. There are no stats
            or leaderboards to opt out of.
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
            The only records tied to <em>you personally</em> are the audit entries written
            when you change a server's settings, plus any premium grants involving your
            account. Those are what the tools below cover.
          </p>
          <p className="muted">
            Server managers can change the setup any time on the <strong>Settings</strong> page.
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

        {!user && checkedAuth && (
          <section className="section card" style={{ marginTop: 16 }}>
            <h2 className="section-title" style={{ marginTop: 0 }}>Your data</h2>
            <p className="muted">
              Sign in with Discord to export or erase the records tied to your account.
            </p>
            <a className="btn btn-primary" href={discordLoginUrl("/me/privacy")}>
              Sign in with Discord
            </a>
          </section>
        )}

        {user && (
          <>
            <section className="section card" style={{ marginTop: 16 }}>
              <h2 className="section-title" style={{ marginTop: 0 }}>Data scope</h2>
              <p className="muted">
                Choose whether export and erase cover every server or just one. Only servers
                that actually hold a record of yours are listed.
              </p>
              <div className="field">
                <label htmlFor="privacy-scope">Servers</label>
                <select
                  id="privacy-scope"
                  value={scopeGuildId}
                  onChange={(e) => setScopeGuildId(e.target.value)}
                >
                  <option value="">All servers</option>
                  {guilds.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name ?? `Server ${g.id}`}
                    </option>
                  ))}
                </select>
              </div>
              {guilds.length === 0 && (
                <p className="muted" style={{ marginBottom: 0 }}>
                  No server currently holds a record naming you.
                </p>
              )}
            </section>

            <section
              className="section card card--accent"
              style={{ marginTop: 16, ["--card-accent" as string]: "var(--success)" } as React.CSSProperties}
            >
              <h2 className="section-title" style={{ marginTop: 0 }}>Export data</h2>
              <p className="muted">
                Download a JSON file with every record Imperial Reminder holds against your
                account in {scopeLabel}.
              </p>
              <a
                href={api.exportUserDataUrl(scopeGuildId || null)}
                className="btn btn-secondary"
                download
              >
                Download my data
              </a>
            </section>

            <section
              className="section card card--accent"
              style={{ marginTop: 16, ["--card-accent" as string]: "var(--danger)" } as React.CSSProperties}
            >
              <h2 className="section-title" style={{ marginTop: 0, color: "var(--danger)" }}>
                Erase my data
              </h2>
              <p className="muted">
                Strips your name and Discord ID from every audit entry you appear in, in{" "}
                {scopeLabel}. The server keeps the record that a setting changed - admins rely
                on that history - but it no longer points at you. Premium grants stay; they are
                grant records, not personal data. This cannot be undone.
              </p>
              <button className="btn btn-danger" onClick={() => setShowDeleteModal(true)}>
                Erase my data...
              </button>
              {eraseResult && (
                <p style={{ marginTop: 12, marginBottom: 0, color: "var(--success)" }}>
                  {eraseResult}
                </p>
              )}
            </section>
          </>
        )}
      </div>

      {showDeleteModal && (
        <div className="modal-backdrop" onClick={() => setShowDeleteModal(false)}>
          <div
            className="card modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="privacy-erase-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="privacy-erase-title" style={{ marginTop: 0 }}>
              Erase your data in {scopeLabel}?
            </h3>
            <p className="muted">
              Type <code>DELETE</code> to confirm. This removes your name and Discord ID from
              every audit entry tied to your account in {scopeLabel}.
            </p>
            <div className="field">
              <input
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="Type DELETE"
                aria-label="Type DELETE to confirm"
                autoFocus
              />
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setShowDeleteModal(false);
                  setConfirmText("");
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                disabled={confirmText !== "DELETE" || erasing}
                onClick={() => void runErase()}
              >
                {erasing ? "Erasing..." : "Erase everything"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
