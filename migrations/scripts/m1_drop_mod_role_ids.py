"""m1: remove the retired ``roles.mod_role_ids`` field from stored guild configs.

The moderator access tier was removed fleet-wide on 2026-08-06 (owner ruling of
2026-08-04: admin surfaces are admin-only). Nothing in ImperialReminder reads
``roles.mod_role_ids`` any more - the admin panel resolver collapses everything that is
not "admin" to "none", the dashboard resolver only reads ``roles.admin_role_ids``, the
panel's mod role picker is gone, and ``GuildConfig`` no longer models the key. This
migration removes the orphaned storage so no future reader can resurrect it.

Holding a listed mod role already grants NOTHING once the new code is deployed, so
running this changes no behavior - it only cleans up dead data.

Idempotent: the ``$unset`` filter only matches documents that still carry the key, so a
re-run after --apply matches nothing.

    python -m migrations.scripts.m1_drop_mod_role_ids                      # dry run
    python -m migrations.scripts.m1_drop_mod_role_ids --apply              # write
    python -m migrations.scripts.m1_drop_mod_role_ids --rollback <file>    # restore

Run the DRY RUN first and read its report: it prints every guild whose ``mod_role_ids``
is non-empty, so you can tell affected servers that those roles now need to be added to
Panel Access Roles (or left out deliberately). --apply writes a JSON backup under
``migrations/backups/`` before it removes anything, and --rollback replays that file.

Run it AFTER the admin-only code is deployed. Nothing writes ``mod_role_ids`` any more,
so there is no race - the field can only sit there until this removes it.

APPLIED against production 2026-08-06 (bot down): matched=1 modified=1, verify 0
remaining. The one carrying doc held an empty list - no server had delegated the tier.
Re-running is a no-op.
"""

from __future__ import annotations

from migrations.scripts._common import connect, parse_args, read_backup, write_backup

_DB = "ImperialReminder"
_COLL = "GuildData"
_PATH = "roles.mod_role_ids"
_BACKUP_NAME = "m1_mod_role_ids"


def _rollback(coll, backup) -> None:
    restored = 0
    for entry in backup:
        result = coll.update_one(
            {"_id": entry["_id"]}, {"$set": {_PATH: entry["mod_role_ids"]}}
        )
        restored += result.modified_count
    print(f"ROLLBACK: restored {_PATH} on {restored} of {len(backup)} doc(s).")


def main() -> None:
    args = parse_args("Remove the retired roles.mod_role_ids field from guild configs.")
    client = connect()
    try:
        coll = client[_DB][_COLL]

        if args.rollback:
            _rollback(coll, read_backup(args.rollback))
            return

        total = coll.count_documents({})
        carrying = coll.count_documents({_PATH: {"$exists": True}})
        print(f"{_DB}.{_COLL}: {total} doc(s); {carrying} carry {_PATH}.")

        if not carrying:
            print("Nothing to remove. (Idempotent no-op.)")
            return

        # Record every current value, and call out the non-empty ones: dropping []
        # is uninteresting, dropping real role ids is worth a human look first.
        backup = []
        non_empty = 0
        for doc in coll.find({_PATH: {"$exists": True}}, {"_id": 1, "roles": 1}):
            value = (doc.get("roles") or {}).get("mod_role_ids")
            backup.append({"_id": doc["_id"], "mod_role_ids": value})
            if value:
                non_empty += 1
                print(f"  NON-EMPTY {_PATH} on guild {doc['_id']!r}: {value!r}")
        if non_empty:
            print(f"  ^ {non_empty} guild(s) still list mod roles. Those roles already "
                  f"grant nothing under the admin-only rule; tell those servers to add "
                  f"them to Panel Access Roles if they should keep access.")
        else:
            print("  All stored values are empty - nothing of substance is lost.")

        if not args.apply:
            print(f"DRY RUN: would unset {_PATH} on {carrying} doc(s). "
                  f"Re-run with --apply to write.")
            return

        path = write_backup(_BACKUP_NAME, backup)
        print(f"Backup written to {path}")

        result = coll.update_many({_PATH: {"$exists": True}}, {"$unset": {_PATH: ""}})
        print(f"APPLIED unset {_PATH}: matched={result.matched_count} "
              f"modified={result.modified_count}.")

        remaining = coll.count_documents({_PATH: {"$exists": True}})
        print(f"Verify: remaining docs carrying {_PATH} = {remaining} (should be 0).")
    finally:
        client.close()


if __name__ == "__main__":
    main()
