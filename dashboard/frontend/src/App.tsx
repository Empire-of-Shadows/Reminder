import { Routes, Route, Navigate, Link } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/settings/:guildId" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      <footer className="site-footer">
        <span className="site-footer__brand">Empire of Shadows &middot; Imperial Reminder Dashboard</span>
        <nav className="site-footer__links" aria-label="Ecosystem">
          <Link to="/dashboard">Servers</Link>
          <a href="https://empireofshadows.club" rel="noopener">Main Site</a>
        </nav>
      </footer>
    </>
  );
}
