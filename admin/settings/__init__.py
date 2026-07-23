"""ImperialReminder's admin panel seam (bot-owned, NEVER vendored).

The vendored engine beside this package reaches every reminder-specific backend
through the names defined here: ``bindings`` (config/audit/premium/cache +
static branding text), ``panel_configs`` (the MAIN_PANEL tree), ``panel_branding``
(titles and guide text), and ``role_auth`` (the access-tier resolver). Engine files
import them as ``from .settings.bindings import ...`` /
``from .settings.panel_configs import MAIN_PANEL``.
"""
