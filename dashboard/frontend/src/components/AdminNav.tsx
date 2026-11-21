import { NavLink, useSearchParams } from "react-router-dom";

function navClass({ isActive }: { isActive: boolean }) {
  return "nav-button" + (isActive ? " active" : "");
}

/** Marks an admin link as opened from a server's overview, so the admin tree's
 *  back link returns there instead of to the settings hub.
 *
 *  A query parameter rather than router state on purpose: the settings and audit
 *  log pages rewrite their own query string (`?s=`, `?section=`), which would
 *  drop router state but merges into existing parameters, and the vendored
 *  FeatureStrip only takes a plain href string. */
export function fromOverview(path: string): string {
  return path + (path.includes("?") ? "&" : "?") + "from=overview";
}

/** For a link from one admin page to another: keeps the from-overview marker
 *  when the current page carries it, so the way back survives the move. */
export function useAdminHref(): (path: string) => string {
  const [searchParams] = useSearchParams();
  const cameFromOverview = searchParams.get("from") === "overview";
  return (path) => (cameFromOverview ? fromOverview(path) : path);
}

/** The admin tab bar for one server's management pages, so the admin tree
 *  navigates within itself instead of dropping back into the member view.
 *
 *  The back link follows where the admin came in. Opened from the server's
 *  overview (the member side), it returns to that overview and every tab keeps
 *  the marker so the way back survives moving between tabs. Opened from the
 *  settings hub, or from a bare link, it returns to the hub.
 *
 *  Both tabs are always shown. Hiding a link was never the gate - the server
 *  re-checks the panel tier on every read and every write, so a link somebody
 *  should not have leads to a refusal rather than to data.
 *
 *  "Change history" is what this bot calls the audit log everywhere a person can
 *  read it, so the tab says the same thing rather than introducing a second name
 *  for one page. */
export default function AdminNav({ guildId }: { guildId: string }) {
  const [searchParams] = useSearchParams();
  const cameFromOverview = searchParams.get("from") === "overview";
  const tab = useAdminHref();
  return (
    <nav className="nav-links" style={{ marginBottom: 20 }}>
      {cameFromOverview ? (
        <NavLink to={`/me/guilds/${guildId}/overview`} end className="nav-button">
          &larr; Overview
        </NavLink>
      ) : (
        <NavLink to="/settings" end className="nav-button">&larr; Your servers</NavLink>
      )}
      <NavLink to={tab(`/settings/guilds/${guildId}/settings`)} className={navClass}>
        Settings
      </NavLink>
      <NavLink to={tab(`/settings/guilds/${guildId}/audit-log`)} className={navClass}>
        Change history
      </NavLink>
    </nav>
  );
}
