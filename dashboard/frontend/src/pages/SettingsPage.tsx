import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  BumpBot,
  Channel,
  GuildOverview,
  GuildSettings,
  Role,
} from "../api/types";
import { formatError } from "../_engine/api/formatError";
import {
  ChannelField,
  Fieldset,
  FRow,
  MultiOptionField,
  MultiRoleField,
  PickerStatusProvider,
  RoleField,
  TextareaField,
  ToggleField,
} from "../_engine/components/settings/fields";
import AppHeader from "../components/AppHeader";
import PageSkeleton from "../components/PageSkeleton";
import ContextColumn from "../components/settings/ContextColumn";

/*
 * Per-guild settings.
 *
 * The four full-width cards this replaced sat in one uncapped column, so a
 * single dropdown got a box as wide as the monitor. The layout is now the
 * shared engine one: a rail with a search box, a reading-width form column,
 * and a context column showing what the selected setting is actually doing.
 *
 * The save model is unchanged on purpose. There is one Save button and it
 * sends the same whole-form payload it always did, which the API turns into a
 * surgical dotted $set of the whitelisted keys. Edits survive moving around the
 * rail, so nothing is lost by looking at another section before saving.
 */

type Slug = "bumps" | "bots" | "timers" | "message" | "access";

interface RailItem {
  slug: Slug;
  /** Rail label. */
  label: string;
  /** Heading over the form column. */
  title: string;
  /** Plain-language description of what this does for the server. */
  blurb: string;
  /** Field labels and help text, for the rail search box. */
  search: string[];
}

const RAIL_GROUPS: { name: string; items: RailItem[] }[] = [
  {
    name: "Reminders",
    items: [
      {
        slug: "bumps",
        label: "Bumping",
        title: "Bumping",
        blurb:
          "The channel you bump in, and the role the bot pings when it is time to bump again. Without both of these there is nothing to watch and nobody to tell.",
        search: ["Bump channel", "Reminder role", "Role to ping", "Where you bump"],
      },
      {
        slug: "bots",
        label: "Bump bots",
        title: "Bump bots to track",
        blurb:
          "The listing services this server bumps on. The bot only times the ones you tick here, so leave out anything you do not use.",
        search: ["Disboard", "BumpIt", "Bump4You", "WeBump", "OneBump", "Unfocused", "Services"],
      },
      {
        slug: "timers",
        label: "Live countdown",
        title: "Live countdown",
        blurb:
          "An optional message the bot keeps up to date with how long is left on each bump, so anyone can check without asking.",
        search: ["Timers channel", "Countdown", "Timer message"],
      },
      {
        slug: "message",
        label: "Reminder wording",
        title: "Custom reminder message",
        blurb:
          "Replace the standard reminder with your own wording. This is a premium feature - the standard reminder is used until this server has premium.",
        search: ["Custom message", "Wording", "bump_role", "bots", "Premium"],
      },
    ],
  },
  {
    name: "Access",
    items: [
      {
        slug: "access",
        label: "Who can manage",
        title: "Who can manage",
        blurb:
          "Members holding any of these roles get the same access to this dashboard and the in-Discord admin panel as someone with Manage Server. Everyone else sees nothing here.",
        search: ["Panel access", "Admin roles", "Permissions", "Manage Server"],
      },
    ],
  },
];

const RAIL_ITEMS: RailItem[] = RAIL_GROUPS.flatMap((g) => g.items);

const DEFAULT_SLUG: Slug = "bumps";

function parseSlug(raw: string | null): Slug {
  const hit = RAIL_ITEMS.find((i) => i.slug === raw);
  return hit ? hit.slug : DEFAULT_SLUG;
}

type BadgeTone = "ok" | "warn" | "";

interface Badge {
  text: string;
  tone: BadgeTone;
}

/**
 * What the rail badge says about a section.
 *
 * "Set up" is the load-bearing one: switched on but missing something it cannot
 * run without, which is the state that looks fine and silently does nothing.
 */
function railBadge(slug: Slug, d: GuildSettings): Badge {
  switch (slug) {
    case "bumps":
      if (!d.bump_channel) return { text: "Set up", tone: "warn" };
      return d.bump_role ? { text: "On", tone: "ok" } : { text: "Set up", tone: "warn" };
    case "bots": {
      const count = (d.enabled_bots ?? []).length;
      return count > 0 ? { text: String(count), tone: "ok" } : { text: "Set up", tone: "warn" };
    }
    case "timers":
      if (!d.timers_message) return { text: "Off", tone: "" };
      return d.timers_channel ? { text: "On", tone: "ok" } : { text: "Set up", tone: "warn" };
    case "message":
      return (d.custom_message ?? "").trim()
        ? { text: "Written", tone: "ok" }
        : { text: "Default", tone: "" };
    case "access": {
      const count = (d.roles?.admin_role_ids ?? []).length;
      return { text: String(count), tone: count > 0 ? "ok" : "" };
    }
  }
}

export default function SettingsPage() {
  const { guildId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [channelsFailed, setChannelsFailed] = useState(false);
  const [rolesFailed, setRolesFailed] = useState(false);
  const [bots, setBots] = useState<BumpBot[]>([]);
  const [lastSaved, setLastSaved] = useState<GuildSettings | null>(null);
  const [settings, setSettings] = useState<GuildSettings | null>(null);
  const [overview, setOverview] = useState<GuildOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [query, setQuery] = useState("");

  const slug = parseSlug(searchParams.get("s"));

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = await api.settings(guildId);
        if (!alive) return;
        setSettings(s);
        setLastSaved(s);
      } catch (e) {
        if (alive) setError(formatError(e));
      } finally {
        if (alive) setLoading(false);
      }
    })();

    // The channel and role lists load separately from the settings, so a
    // permission problem on one of them cannot blank the whole page. When one
    // fails the picker says so instead of showing an empty dropdown that reads
    // as "this server has no channels".
    api
      .getChannels(guildId)
      .then((c) => {
        if (!alive) return;
        setChannels(c);
        setChannelsFailed(false);
      })
      .catch(() => {
        if (!alive) return;
        setChannels([]);
        setChannelsFailed(true);
      });

    api
      .getRoles(guildId)
      .then((r) => {
        if (!alive) return;
        setRoles([...r].sort((a, b) => b.position - a.position));
        setRolesFailed(false);
      })
      .catch(() => {
        if (!alive) return;
        setRoles([]);
        setRolesFailed(true);
      });

    api.bumpBots().then((b) => { if (alive) setBots(b); }).catch(() => {});

    // Optional. The context column drops the rows it cannot fill.
    api.guildOverview(guildId).then((o) => { if (alive) setOverview(o); }).catch(() => {
      if (alive) setOverview(null);
    });

    return () => {
      alive = false;
    };
  }, [guildId]);

  const enabled = useMemo(() => new Set(settings?.enabled_bots ?? []), [settings]);

  function update<K extends keyof GuildSettings>(key: K, value: GuildSettings[K]) {
    setSettings((s) => (s ? { ...s, [key]: value } : s));
    setSaved(false);
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
        },
      });
      setSettings(updated);
      setLastSaved(updated);
      setSaved(true);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <PageSkeleton />;

  const active = RAIL_ITEMS.find((i) => i.slug === slug) ?? RAIL_ITEMS[0];

  const goTo = (next: Slug) => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("s", next);
        return params;
      },
      { replace: true },
    );
  };

  const dirty =
    !!settings && !!lastSaved && JSON.stringify(stableForm(settings)) !== JSON.stringify(stableForm(lastSaved));

  const q = query.trim().toLowerCase();
  const itemMatches = (item: RailItem): boolean => {
    if (!q) return true;
    if (item.label.toLowerCase().includes(q)) return true;
    if (item.title.toLowerCase().includes(q)) return true;
    return item.search.some((s) => s.toLowerCase().includes(q));
  };
  const anyMatch = RAIL_ITEMS.some(itemMatches);

  return (
    <div className="app-layout">
      <AppHeader
        title="Server Settings"
        left={
          <Link to="/dashboard" className="btn btn-secondary" style={{ marginLeft: 12 }}>
            &larr; Servers
          </Link>
        }
      />

      <div className="page">
        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}
        {saved && (
          <div className="alert success" role="status" style={{ marginTop: 16 }}>
            Settings saved.
          </div>
        )}

        {settings && (
          <div className="set-layout">
            <div>
              <div className="set-search">
                <span className="set-search__i" aria-hidden="true">
                  &#8981;
                </span>
                <input
                  type="search"
                  value={query}
                  placeholder="Search settings"
                  aria-label="Search settings"
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>

              <nav className="set-rail" aria-label="Settings sections">
                {RAIL_GROUPS.map((group) => {
                  const items = group.items.filter(itemMatches);
                  if (items.length === 0) return null;
                  return (
                    <Fragment key={group.name}>
                      <div className="set-rail__grp">{group.name}</div>
                      {items.map((item) => {
                        const badge = railBadge(item.slug, settings);
                        return (
                          <button
                            key={item.slug}
                            type="button"
                            className={
                              "set-rail__item" + (item.slug === slug ? " is-active" : "")
                            }
                            aria-current={item.slug === slug ? "page" : undefined}
                            onClick={() => goTo(item.slug)}
                          >
                            <span>{item.label}</span>
                            <span
                              className={
                                "set-rail__badge" +
                                (badge.tone ? ` set-rail__badge--${badge.tone}` : "")
                              }
                            >
                              {badge.text}
                            </span>
                          </button>
                        );
                      })}
                    </Fragment>
                  );
                })}
                {!anyMatch && (
                  <p className="set-rail__empty">Nothing here matches "{query.trim()}".</p>
                )}
              </nav>
            </div>

            <PickerStatusProvider value={{ channelsFailed, rolesFailed }}>
              <div className="set-main">
                <div className="set-head">
                  <h1>{active.title}</h1>
                  <p>{active.blurb}</p>
                </div>

                {slug === "bumps" && (
                  <Fieldset>
                    <FRow>
                      <ChannelField
                        label="Bump channel"
                        value={settings.bump_channel || null}
                        channels={channels}
                        onChange={(v) => update("bump_channel", v ?? "")}
                        description="Where you run the bump commands. The bot watches only this channel."
                      />
                      <RoleField
                        label="Reminder role to ping"
                        value={settings.bump_role || null}
                        roles={roles}
                        onChange={(v) => update("bump_role", v ?? "")}
                        description="The only role the reminder is ever allowed to mention."
                      />
                    </FRow>
                  </Fieldset>
                )}

                {slug === "bots" && (
                  <Fieldset>
                    <MultiOptionField
                      label="Bump bots to track"
                      description="Reminders are only scheduled for the services ticked here."
                      value={bots.filter((b) => enabled.has(b.key)).map((b) => b.key)}
                      options={bots.map((b) => [b.key, b.name] as [string, string])}
                      onChange={(v) => update("enabled_bots", v)}
                    />
                  </Fieldset>
                )}

                {slug === "timers" && (
                  <Fieldset>
                    <FRow full>
                      <ToggleField
                        label="Show a live countdown message"
                        value={!!settings.timers_message}
                        onChange={(v) => update("timers_message", v)}
                        description="The bot keeps one message updated with the time left on each bump."
                      />
                    </FRow>
                    <FRow full>
                      <ChannelField
                        label="Timers display channel"
                        value={settings.timers_channel || null}
                        channels={channels}
                        onChange={(v) => update("timers_channel", v ?? "")}
                        description="Optional. Leave unset to keep the countdown out of your server."
                      />
                    </FRow>
                  </Fieldset>
                )}

                {slug === "message" && (
                  <Fieldset>
                    <TextareaField
                      label="Custom reminder message"
                      value={settings.custom_message ?? ""}
                      rows={3}
                      onChange={(v) => update("custom_message", v)}
                      placeholder="It's time to bump! {bump_role} - {bots}"
                      description="Optional. {bump_role} becomes the ping and {bots} becomes the list of bump bots."
                    />
                  </Fieldset>
                )}

                {slug === "access" && (
                  <Fieldset>
                    <MultiRoleField
                      label="Manager roles"
                      description="Members with Manage Server can always manage this bot. Roles ticked here get the same full access, on this dashboard and on the in-Discord admin panel."
                      value={settings.roles?.admin_role_ids ?? []}
                      roles={roles}
                      onChange={(v) => update("roles", { admin_role_ids: v })}
                    />
                  </Fieldset>
                )}

                <div className="savebar">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={saving}
                    onClick={() => void save()}
                  >
                    {saving ? "Saving..." : "Save settings"}
                  </button>
                  <span className="eos-muted" style={{ fontSize: 13 }}>
                    {dirty
                      ? "Unsaved changes. Saving writes every section on this page."
                      : "Everything here is saved"}
                  </span>
                </div>
              </div>
            </PickerStatusProvider>

            <aside className="set-ctx" aria-label="Current state">
              <ContextColumn
                slug={slug}
                draft={settings}
                channels={channels}
                roles={roles}
                bots={bots}
                overview={overview}
              />
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}

/** The saved-versus-draft comparison, over the fields the Save button sends. */
function stableForm(s: GuildSettings) {
  return {
    bump_channel: s.bump_channel || "",
    bump_role: s.bump_role || "",
    timers_channel: s.timers_channel || "",
    timers_message: !!s.timers_message,
    enabled_bots: [...(s.enabled_bots ?? [])].sort(),
    custom_message: s.custom_message ?? "",
    admin_role_ids: [...(s.roles?.admin_role_ids ?? [])].sort(),
  };
}
