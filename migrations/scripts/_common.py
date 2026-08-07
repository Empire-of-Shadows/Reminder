"""Shared helpers for ImperialReminder data migrations.

Loads MongoDB credentials from the bot's local env exactly like the entrypoint
(``docker/.env`` then ``docker/.env.local`` override), connects, and provides the
standard dry-run / apply / rollback argument parsing every migration shares.

Every migration is a standalone script:

    python -m migrations.scripts.<name>                       # dry run (default, no writes)
    python -m migrations.scripts.<name> --apply               # perform the writes
    python -m migrations.scripts.<name> --rollback <file>     # restore from a backup file

All migrations are idempotent - re-running after --apply is a no-op. A migration that
removes data writes a JSON backup next to the script before it writes, and --rollback
replays that file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse as up
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

# migrations/scripts/_common.py -> the bot root is two parents up.
_BOT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = _BOT_ROOT / "migrations" / "backups"


def load_env() -> None:
    """Load env the way Reminder.py does: docker/.env then docker/.env.local wins."""
    load_dotenv(_BOT_ROOT / "docker" / ".env")
    load_dotenv(_BOT_ROOT / "docker" / ".env.local", override=True)


def _direct(uri: str) -> str:
    """Rewrite a URI for a single-node direct connection (drop replicaSet)."""
    p = up.urlsplit(uri)
    q = [(k, v) for k, v in up.parse_qsl(p.query)
         if k.lower() not in ("replicaset", "directconnection")]
    q.append(("directConnection", "true"))
    return up.urlunsplit((p.scheme, p.netloc, p.path, up.urlencode(q), p.fragment))


def connect(timeout_ms: int = 8000) -> MongoClient:
    """Return a connected MongoClient using the bot's MONGO_URI.

    Tries the URI as-is first (works inside the bot's container/network). If
    replica-set discovery cannot reach the members (e.g. running from a host that
    cannot resolve the RS member names), retries with a direct single-node
    connection. A direct connection is fine for a dry run; run --apply where the
    normal RS connection works so writes reach the primary.
    """
    load_env()
    uri = os.getenv("MONGO_URI")
    if not uri:
        print("MONGO_URI not set (checked docker/.env and docker/.env.local).", file=sys.stderr)
        raise SystemExit(1)
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
        return client
    except ServerSelectionTimeoutError:
        print("Replica-set connection failed; retrying with a direct connection.", file=sys.stderr)
        client = MongoClient(_direct(uri), serverSelectionTimeoutMS=timeout_ms)
        client.admin.command("ping")
        return client


def parse_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--apply",
        action="store_true",
        help="Perform the writes. Omit for a dry run (default).",
    )
    group.add_argument(
        "--rollback",
        metavar="BACKUP_FILE",
        help="Restore the values recorded in a backup file written by --apply.",
    )
    return parser.parse_args()


def write_backup(name: str, payload: Any) -> Path:
    """Persist `payload` as JSON under migrations/backups and return the path."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def read_backup(path_str: str) -> Any:
    """Load a backup file written by write_backup."""
    path = Path(path_str)
    if not path.is_absolute():
        candidate = BACKUP_DIR / path_str
        path = candidate if candidate.exists() else path
    if not path.exists():
        print(f"Backup file not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(path.read_text(encoding="utf-8"))
