import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { User } from "../api/types";
import AppHeader from "../components/AppHeader";

/**
 * Public, unauthenticated privacy policy page.
 *
 * Follows the ecosystem "standard" (TheCodex / TheHost): a `dash-hero` header
 * over a numbered `legal-doc` body. Renders without a session — it tries to
 * load the signed-in user only to personalise the header, and ignores failures.
 */
const EFFECTIVE_DATE = "June 8, 2026";

export default function PrivacyPolicyPage() {
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
            <span className="dash-hero__eyebrow">Legal</span>
            <h1 className="dash-hero__title">Privacy Policy</h1>
            <p className="dash-hero__sub">Effective {EFFECTIVE_DATE}</p>
          </div>
        </section>

        <div className="legal-doc">
          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>1. Overview</h2>
            <p>
              This policy explains what data Imperial Reminder ("the bot", "we", "us") collects
              when you use the bot or the web dashboard, how we use it, and the choices you have.
              Imperial Reminder is part of the Empire of Shadows ecosystem and is a bump-reminder
              bot: it reminds your server to bump on listing sites. It does <strong>not</strong>{" "}
              read or store the content of your messages and does not track individual members.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>2. Information we collect</h2>
            <ul>
              <li>
                <strong>Discord account data</strong> provided through Discord login (OAuth): your
                user ID, username, global display name, and avatar, plus the servers you are in and
                your permissions in them, which we use for access control on the dashboard.
              </li>
              <li>
                <strong>Server bump configuration</strong>: which bump bots to track and when each
                was last bumped, the bump channel, the reminder role to ping, the timers channel,
                your custom reminder message, and which roles may manage these settings.
              </li>
              <li>
                <strong>Premium records</strong>: entitlement status for premium features (a user
                ID and when the entitlement expires) and any premium redemption codes.
              </li>
              <li><strong>A session cookie</strong> that keeps you signed in to the dashboard.</li>
            </ul>
            <p className="muted">
              We do not read or store message content, and we do not track individual members'
              messages, activity, or profiles — there is nothing personal to opt out of.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>3. How we use your data</h2>
            <p>
              We use this data to run bump reminders, apply premium features, and gate the
              dashboard's settings to people who can manage a server. We do not sell your data and
              we do not show advertising.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>4. Cookies</h2>
            <p>
              We use a single session cookie to identify your signed-in session on the dashboard.
              It is required for login to work. Sessions expire automatically after about 30 days,
              after which you will need to sign in again.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>5. Third parties</h2>
            <p>
              We rely on Discord for login and as the platform the bot runs on, and on our database
              and hosting infrastructure (MongoDB) to store the configuration above. Your dashboard
              session is shared across the Empire of Shadows ecosystem, so one login covers every
              bot dashboard. We do not share your data with advertisers or data brokers.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>6. Data retention</h2>
            <p>
              We keep a server's bump configuration until a manager changes it or the bot is
              removed from the server, after which related configuration may be cleaned up. Premium
              records are kept for the life of the entitlement. Login sessions expire automatically.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>7. Your choices and rights</h2>
            <p>
              Because the bot stores no personal activity, there is nothing for an individual member
              to opt out of. Server managers can view and change all stored configuration any time
              from the <Link to="/settings">Settings</Link> page, or remove it by removing the bot
              from the server. To request deletion of any data, contact{" "}
              <a href="mailto:support@eosofficial.club">support@eosofficial.club</a>.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>8. Children</h2>
            <p>
              You must meet Discord's minimum age requirement for your region to use the bot or the
              dashboard. We do not knowingly collect data from anyone below that age.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>9. Changes to this policy</h2>
            <p>
              We may update this policy from time to time. The effective date at the top of this
              page reflects the latest version, and we will note material changes where practical.
            </p>
          </section>

          <section className="section card">
            <h2 className="section-title" style={{ marginTop: 0 }}>10. Contact</h2>
            <p>
              Questions about this policy or your data can be sent to
              <a href="mailto:support@eosofficial.club"> support@eosofficial.club</a>.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
