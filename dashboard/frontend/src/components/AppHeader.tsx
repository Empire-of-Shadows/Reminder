import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { User } from "../api/types";

function navClass({ isActive }: { isActive: boolean }) {
  return "nav-button" + (isActive ? " active" : "");
}

interface AppHeaderProps {
  user?: User | null;
  /** Optional override for the title text. */
  title?: string;
  /** Slot rendered between the title and the user-info (e.g. a back button). */
  left?: ReactNode;
  /** Slot rendered to the right of the user-info. */
  right?: ReactNode;
  /** Hide the user-info block entirely (title only). */
  hideUser?: boolean;
}

export default function AppHeader({
  user,
  title = "Imperial Reminder",
  left,
  right,
  hideUser = false,
}: AppHeaderProps) {
  const avatarUrl =
    user?.avatar && user?.id
      ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=64`
      : null;
  const displayName = user?.global_name || user?.username;

  return (
    <header className="app-header">
      <div style={{ display: "flex", alignItems: "center", gap: 16, minWidth: 0 }}>
        <h1>
          <span className="app-header__title-text">{title}</span>
        </h1>
        {left ?? (user && (
          <nav className="nav-links" style={{ marginLeft: 8 }}>
            <NavLink to="/dashboard" className={navClass}>Servers</NavLink>
          </nav>
        ))}
      </div>
      <nav
        className="ecosystem-links"
        aria-label="Empire of Shadows ecosystem"
        style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto", marginRight: 12 }}
      >
        <a
          href="https://empireofshadows.club"
          className="btn btn-secondary"
          rel="noopener"
          style={{ fontSize: 12, padding: "4px 10px" }}
          title="Empire of Shadows — main site"
        >
          Empire &#x2197;
        </a>
        <a
          href="https://host.empireofshadows.club"
          className="btn btn-secondary"
          rel="noopener"
          style={{ fontSize: 12, padding: "4px 10px" }}
          title="TheHost dashboard"
        >
          TheHost &#x2197;
        </a>
      </nav>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {right}
        {!hideUser && user && (
          <div className="user-info">
            {avatarUrl && <img src={avatarUrl} alt="" />}
            <span>{displayName}</span>
            <a
              href="/auth/logout"
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "4px 10px" }}
            >
              Logout
            </a>
          </div>
        )}
      </div>
    </header>
  );
}
