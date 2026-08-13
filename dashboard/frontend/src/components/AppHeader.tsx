import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { User } from "../api/types";
import { AppShell } from "../_engine/components/AppShell";

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

/** ImperialReminder's header: the shared AppShell wired with this bot's brand
 *  and nav. The shell owns the bar, the ecosystem switcher and the user block;
 *  the brand slot stays here because the bot renders it. */
export default function AppHeader({
  user,
  title = "Imperial Reminder",
  left,
  right,
  hideUser = false,
}: AppHeaderProps) {
  return (
    <AppShell
      user={user}
      hideUser={hideUser}
      left={left}
      right={right}
      brand={
        <h1>
          <span className="app-header__title-text">{title}</span>
        </h1>
      }
      nav={user ? (
        <>
          <NavLink to="/dashboard" className={navClass}>Stats</NavLink>
          <NavLink to="/me/privacy" className={navClass}>Privacy</NavLink>
          {user.can_access_settings_any && (
            <NavLink to="/settings" className={navClass}>Settings</NavLink>
          )}
        </>
      ) : null}
    />
  );
}
