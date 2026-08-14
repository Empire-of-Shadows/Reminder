import { lazy, Suspense } from "react";
import { Routes, Route, Navigate, Link } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import PageSkeleton from "./components/PageSkeleton";
import { AppFooter } from "./_engine/components/AppFooter";

/*
 * Login and the dashboard home are in the main bundle - they are where every
 * visit starts. Everything else is split out and loaded on demand, so the
 * settings forms, the legal pages and the audit table are not downloaded by
 * somebody who only ever looks at their bump timers.
 */
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const SettingsHubPage = lazy(() => import("./pages/SettingsHubPage"));
const AuditLogPage = lazy(() => import("./pages/AuditLogPage"));
const PrivacyPage = lazy(() => import("./pages/PrivacyPage"));
const PrivacyPolicyPage = lazy(() => import("./pages/PrivacyPolicyPage"));
const TermsPage = lazy(() => import("./pages/TermsPage"));

export default function App() {
  return (
    <>
      <Suspense fallback={<PageSkeleton />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          {/* Public legal pages - no auth; canonical URLs for Discord review. */}
          <Route path="/privacy" element={<PrivacyPolicyPage />} />
          <Route path="/terms" element={<TermsPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/me/privacy" element={<PrivacyPage />} />
          <Route path="/settings" element={<SettingsHubPage />} />
          <Route path="/settings/:guildId" element={<SettingsPage />} />
          <Route path="/settings/:guildId/audit-log" element={<AuditLogPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
      <AppFooter
        brand="Empire of Shadows · Imperial Reminder Dashboard"
        extraLinks={
          <>
            <Link to="/dashboard">Stats</Link>
            <a href="https://eosofficial.club" rel="noopener">
              Main Site
            </a>
          </>
        }
      />
    </>
  );
}
