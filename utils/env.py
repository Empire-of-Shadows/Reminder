"""Single source of truth for environment loading.

Every process/module loads from `docker/.env` (the deploy env), regardless of
the current working directory or which module is imported first. Falls back to
the default `.env` search only if `docker/.env` doesn't exist.
"""

from pathlib import Path

from dotenv import load_dotenv

_loaded = False


def load_project_env() -> Path | None:
    """Load docker/.env once. Returns the path loaded, or None for the fallback."""
    global _loaded
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docker" / ".env"
        if candidate.exists():
            load_dotenv(candidate)
            _loaded = True
            return candidate
    load_dotenv()
    _loaded = True
    return None
