import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Channel, Role, BumpBot, GuildSettings } from "../api/types";
import { formatError } from "../utils/formatError";
import AppHeader from "../components/AppHeader";
import PageSkeleton from "../components/PageSkeleton";

export default function SettingsPage() {
  const { guildId = "" } = useParams();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [bots, setBots] = useState<BumpBot[]>([]);
  const [settings, setSettings] = useState<GuildSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [s, ch, rl, bb] = await Promise.all([
          api.settings(guildId),
          api.getChannels(guildId),
          api.getRoles(guildId),
          api.bumpBots(),
        ]);
        if (!alive) return;
        setSettings(s);
        setChannels(ch);
        setRoles([...rl].sort((a, b) => b.position - a.position));
        setBots(bb);
      } catch (e) {
        if (alive) setError(formatError(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [guildId]);

  const enabled = useMemo(() => new Set(settings?.enabled_bots ?? []), [settings]);
  const readOnly = settings?.panel_role === "mod";
  const adminRoleIds = useMemo(
    () => new Set(settings?.roles?.admin_role_ids ?? []),
    [settings],
  );
  const modRoleIds = useMemo(
    () => new Set(settings?.roles?.mod_role_ids ?? []),
    [settings],
  );

  function update<K extends keyof GuildSettings>(key: K, value: GuildSettings[K]) {
    setSettings((s) => (s ? { ...s, [key]: value } : s));
    setSaved(false);
  }

  function togglePanelRole(tier: "admin_role_ids" | "mod_role_ids", roleId: string) {
    if (!settings) return;
    const current = new Set(settings.roles?.[tier] ?? []);
    if (current.has(roleId)) current.delete(roleId);
    else current.add(roleId);
    update("roles", {
      admin_role_ids: tier === "admin_role_ids" ? Array.from(current) : (settings.roles?.admin_role_ids ?? []),
      mod_role_ids: tier === "mod_role_ids" ? Array.from(current) : (settings.roles?.mod_role_ids ?? []),
    });
  }

  function toggleBot(key: string) {
    if (!settings) return;
    const next = new Set(settings.enabled_bots ?? []);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    update("enabled_bots", Array.from(next));
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.saveSettings(guildId, {
        bump_channel: settings.bump_channel || "",
        bump_role: settings.bump_role || "",
        timers_channel: settings.timers_channel || "",
        timers_message: !!settings.timers_message,
        enabled_bots: settings.enabled_bots ?? [],
        custom_message: settings.custom_message ?? "",
        roles: {
          admin_role_ids: settings.roles?.admin_role_ids ?? [],
          mod_role_ids: settings.roles?.mod_role_ids ?? [],
        },
      });
      setSettings(updated);
      setSaved(true);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <PageSkeleton />;

  return (
    <div className="app-layout admin-settings-page">
      <AppHeader
        left={
          <Link to="/dashboard" className="btn btn-secondary" style={{ marginLeft: 12 }}>
            &larr; Servers
          </Link>
        }
      />

      {error && (
        <div className="alert danger" role="alert" style={{ margin: 24 }}>
          {error}
        </div>
      )}
      {saved && (
        <div className="alert success" role="status" style={{ margin: 24 }}>
          Settings saved.
        </div>
      )}

      {settings && (
        <div style={{ padding: 24 }}>
          <section className="section card" style={{ marginBottom: 16 }}>
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Bump Reminders
            </h2>
            <p className="muted" style={{ marginTop: 0 }}>
              Where the bot watches for bumps and who it pings when it's time again.
            </p>

            <div className="field">
              <label>Bump channel</label>
              <select
                value={settings.bump_channel || ""}
                onChange={(e) => update("bump_channel", e.target.value)}
              >
                <option value="">-- not set --</option>
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>#{c.name}</option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>Reminder role to ping</label>
              <select
                value={settings.bump_role || ""}
                onChange={(e) => update("bump_role", e.target.value)}
              >
                <option value="">-- not set --</option>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>Timers display channel</label>
              <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
                Optional channel for a live countdown message.
              </p>
              <select
                value={settings.timers_channel || ""}
                onChange={(e) => update("timers_channel", e.target.value)}
              >
                <option value="">-- not set --</option>
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>#{c.name}</option>
                ))}
              </select>
            </div>

            <div className="field">
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={!!settings.timers_message}
                  onChange={(e) => update("timers_message", e.target.checked)}
                />
                <span>Show a live countdown message in the timers channel</span>
              </label>
            </div>
          </section>

          <section className="section card" style={{ marginBottom: 16 }}>
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Bump bots to track
            </h2>
            <p className="muted" style={{ marginTop: 0 }}>
              The bot only schedules reminders for the services you enable here.
            </p>
            {bots.map((b) => (
              <div className="field" key={b.key}>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={enabled.has(b.key)}
                    onChange={() => toggleBot(b.key)}
                  />
                  <span>{b.name}</span>
                </label>
              </div>
            ))}
          </section>

          <section className="section card" style={{ marginBottom: 16 }}>
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Panel access roles
            </h2>
            <p className="muted" style={{ marginTop: 0 }}>
              Members with Manage Server can always manage this bot. Grant extra access by role:
              <strong> Admin</strong> roles can change everything here; <strong>Mod</strong> roles
              can view settings (read-only).
            </p>
            <div className="field">
              <label>Admin roles</label>
              <div className="role-checklist" style={{ maxHeight: 180, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
                {roles.map((r) => (
                  <label className="toggle" key={`a-${r.id}`}>
                    <input
                      type="checkbox"
                      checked={adminRoleIds.has(r.id)}
                      disabled={readOnly}
                      onChange={() => togglePanelRole("admin_role_ids", r.id)}
                    />
                    <span>{r.name}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="field">
              <label>Mod roles (read-only access)</label>
              <div className="role-checklist" style={{ maxHeight: 180, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
                {roles.map((r) => (
                  <label className="toggle" key={`m-${r.id}`}>
                    <input
                      type="checkbox"
                      checked={modRoleIds.has(r.id)}
                      disabled={readOnly}
                      onChange={() => togglePanelRole("mod_role_ids", r.id)}
                    />
                    <span>{r.name}</span>
                  </label>
                ))}
              </div>
            </div>
          </section>

          <section className="section card" style={{ marginBottom: 16 }}>
            <h2 className="section-title" style={{ marginTop: 0 }}>
              Custom reminder message
            </h2>
            <div className="field">
              <label>Message</label>
              <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
                Optional. Supports <code>{"{bump_role}"}</code> and <code>{"{bots}"}</code> placeholders.
              </p>
              <textarea
                rows={3}
                value={settings.custom_message ?? ""}
                onChange={(e) => update("custom_message", e.target.value)}
                placeholder="It's time to bump! {bump_role} — {bots}"
              />
            </div>
          </section>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {readOnly ? (
              <span className="muted">You have read-only (Mod) access — changes are disabled.</span>
            ) : (
              <button className="btn btn-primary" disabled={saving} onClick={() => void save()}>
                {saving ? "Saving..." : "Save settings"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}