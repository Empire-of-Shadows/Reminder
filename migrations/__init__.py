"""One-off data migrations for ImperialReminder.

ImperialReminder runs in production with real guild config and bump timestamps, so
schema changes ship an idempotent migration here rather than a collection drop.
See ``migrations/scripts/`` for the scripts and ``_common.py`` for the harness.
"""
