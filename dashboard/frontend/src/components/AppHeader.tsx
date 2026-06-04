import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { User } from "../api/types";
import { EcosystemNav } from "./EcosystemNav";

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
            <NavLink to="/dashboard" className={navClass}>Stats</NavLink>
            <NavLink to="/me/privacy" className={navClass}>Privacy</NavLink>
            {user.can_access_settings_any && (
              <NavLink to="/settings" className={navClass}>Settings</NavLink>
            )}
          </nav>
        ))}
      </div>
      <div style={{ marginLeft: "auto", marginRight: 12 }}>
        <EcosystemNav />
      </div>
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
