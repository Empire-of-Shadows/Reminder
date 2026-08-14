import type { MemberEntitlements as Entitlements } from "../../api/types";
import { KeyValue, Rule, Stat, Tile } from "../../_engine/components/overview/Tile";
import { formatRelative as formatIsoRelative } from "../../_engine/format";
import { formatDuration } from "./format";

/**
 * "What you can use" - the member's view of what this server unlocks.
 *
 * Premium on Imperial Reminder is a property of the SERVER, not of the person
 * reading the page, and the copy says so rather than implying a personal
 * subscription. Nothing here is actionable by a member, so nothing here is a
 * button: it is status plus the two commands they can actually run.
 */
export default function MemberEntitlements({
  entitlements,
}: {
  entitlements: Entitlements;
}) {
  return (
    <div className="ov-grid">
      <ServerUnlocks entitlements={entitlements} />
      <Commands entitlements={entitlements} />
    </div>
  );
}

function ServerUnlocks({ entitlements }: { entitlements: Entitlements }) {
  const { custom_wording, faster_cooldowns } = entitlements;
  const activeFaster = faster_cooldowns.filter((bot) => bot.active).length;

  return (
    <Tile
      span={7}
      title="What this server unlocks"
      chips={
        entitlements.is_premium ? (
          <span className="ov-chip ov-chip--good">Premium</span>
        ) : (
          <span className="ov-chip">Free</span>
        )
      }
    >
      <Stat
        value={entitlements.is_premium ? entitlements.tier ?? "Premium" : "Free"}
        label="This server's plan"
      />

      <div>
        <KeyValue
          k="Reminder wording"
          v={
            custom_wording.in_use
              ? "This server's own wording"
              : custom_wording.written
                ? "Written, but the standard reminder is sent"
                : "The standard reminder"
          }
        />
        {entitlements.expires_at && (
          <KeyValue k="Premium runs out" v={formatIsoRelative(entitlements.expires_at)} />
        )}
      </div>

      {faster_cooldowns.length > 0 && (
        <>
          <Rule />
          <span className="ov-card__title">Shorter waits available here</span>
          <div>
            {faster_cooldowns.map((bot) => (
              <KeyValue
                key={bot.key}
                k={bot.name}
                v={
                  bot.active
                    ? `Every ${formatDuration(bot.premium_cooldown)}`
                    : `Every ${formatDuration(bot.standard_cooldown)} - premium can make it ${formatDuration(bot.premium_cooldown)}`
                }
              />
            ))}
          </div>
          <p className="ov-muted">
            {activeFaster > 0
              ? "A shorter cooldown means this server can bump again sooner, so you will be pinged more often."
              : "These services allow a shorter wait on a premium server. Nothing changes for you until a server manager turns it on."}
          </p>
        </>
      )}

      {!entitlements.is_premium && faster_cooldowns.length === 0 && (
        <p className="ov-muted">
          Premium here unlocks a custom reminder wording, and a shorter wait on the listing
          services that offer one. None of the services this server tracks offer a shorter
          wait.
        </p>
      )}
    </Tile>
  );
}

function Commands({ entitlements }: { entitlements: Entitlements }) {
  return (
    <Tile span={5} title="What you can run">
      <p className="ov-body">
        Imperial Reminder is mostly quiet - it watches the bump channel and pings when a bump
        is due. These are the two commands anyone in this server can use.
      </p>
      <Rule />
      <div className="ov-queue">
        {entitlements.commands.map((command) => (
          <div className="ov-qrow" key={command.name}>
            <span className="ov-qrow__dot" style={{ background: "var(--text-accent)" }} />
            <span className="ov-qrow__txt">
              <code>{command.name}</code> {command.detail}
            </span>
          </div>
        ))}
      </div>
    </Tile>
  );
}
