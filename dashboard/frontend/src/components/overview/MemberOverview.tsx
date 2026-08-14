import type { GuildBumpStats, MemberReminder } from "../../api/types";
import {
  KeyValue,
  Rule,
  SectionUnavailable,
  Stat,
  Tile,
} from "../../_engine/components/overview/Tile";
import BumpStatusGrid from "../BumpStatusGrid";
import { formatCountdown, formatRelative } from "./format";

/**
 * The member's half of the dashboard home: what this server's bump reminder is
 * doing for the person reading the page.
 *
 * Both halves are independently nullable because they are fetched separately -
 * "will you be pinged" needs a live Discord roles lookup and must never be able
 * to take the timings down with it. A null half says so; it is never drawn as
 * an empty or zeroed one.
 *
 * `detailed` is the difference between the two panes. A plain member gets the
 * per-bot breakdown here because nothing else on their page has it. An admin
 * gets the roll-up only - the full per-bot grid is already in their Server
 * overview below, and printing it twice is noise, not density.
 */
export default function MemberOverview({
  bumps,
  reminder,
  detailed,
}: {
  bumps: GuildBumpStats | null;
  reminder: MemberReminder | null;
  detailed: boolean;
}) {
  // The wide half is whichever one has more to say. With the per-bot breakdown
  // in it, that is the timings; without it, the roll-up is four lines and the
  // ping answer is a paragraph plus three rows.
  const bumpSpan = detailed ? 7 : 5;
  const pingSpan = detailed ? 5 : 7;

  return (
    <div className="ov-grid">
      <YourBumps bumps={bumps} detailed={detailed} span={bumpSpan} />
      <WillYouBePinged reminder={reminder} span={pingSpan} />
    </div>
  );
}

/* ── What is due ───────────────────────────────────────────────────── */

interface RollUp {
  ready: number;
  waiting: number;
  nextDue: number | null;
  lastBump: number | null;
}

/** The roll-up, computed from the rows rather than asked for separately, so a
 *  member and a manager can never be shown two different counts. */
function rollUp(bumps: GuildBumpStats): RollUp {
  let ready = 0;
  let waiting = 0;
  let nextDue: number | null = null;
  let lastBump: number | null = null;

  for (const bot of bumps.bots) {
    if (bot.status === "ready") {
      ready += 1;
    } else {
      waiting += 1;
      if (bot.next_due !== null) {
        nextDue = nextDue === null ? bot.next_due : Math.min(nextDue, bot.next_due);
      }
    }
    if (bot.last_bump !== null) {
      lastBump = lastBump === null ? bot.last_bump : Math.max(lastBump, bot.last_bump);
    }
  }
  return { ready, waiting, nextDue, lastBump };
}

function YourBumps({
  bumps,
  detailed,
  span,
}: {
  bumps: GuildBumpStats | null;
  detailed: boolean;
  span: 5 | 7;
}) {
  if (!bumps) {
    return (
      <Tile span={span} title="What is due">
        <SectionUnavailable what="This server's bump timings" />
      </Tile>
    );
  }

  if (bumps.bots.length === 0) {
    return (
      <Tile span={span} title="What is due">
        <p className="ov-body">
          Nobody has chosen which listing services this server bumps on yet, so there is
          nothing being timed here. A server manager picks them in the bot's settings.
        </p>
      </Tile>
    );
  }

  const { ready, waiting, nextDue, lastBump } = rollUp(bumps);
  const now = bumps.server_time;

  return (
    <Tile
      span={span}
      title="What is due"
      live
      chips={
        ready > 0 ? (
          <span className="ov-chip ov-chip--good">
            {ready} ready to bump now
          </span>
        ) : (
          <span className="ov-chip">Everything is on cooldown</span>
        )
      }
    >
      <div className="ov-statrow">
        <Stat
          value={nextDue !== null ? formatCountdown(nextDue, now).replace(/^in /, "") : "-"}
          label={nextDue !== null ? "Until the next bump" : "Nothing waiting"}
        />
        <Stat small value={ready} sub={`/${bumps.bots.length}`} label="Ready now" />
      </div>
      <div>
        <KeyValue
          k="Last bump seen"
          v={lastBump !== null ? formatRelative(lastBump, now) : "None seen yet"}
        />
        <KeyValue k="Still cooling down" v={waiting} />
      </div>
      {detailed && (
        <>
          <Rule />
          <BumpStatusGrid stats={bumps} />
        </>
      )}
    </Tile>
  );
}

/* ── Will you be pinged ────────────────────────────────────────────── */

function WillYouBePinged({
  reminder,
  span,
}: {
  reminder: MemberReminder | null;
  span: 5 | 7;
}) {
  if (!reminder) {
    return (
      <Tile span={span} title="Will you be pinged">
        <SectionUnavailable what="Whether the reminder reaches you" />
      </Tile>
    );
  }

  const answer =
    reminder.status === "yes"
      ? "Yes"
      : reminder.status === "no"
        ? "No"
        : reminder.status === "no_role"
          ? "Nobody is"
          : "Not confirmed";

  const chip =
    reminder.status === "yes" ? (
      <span className="ov-chip ov-chip--good">You get the ping</span>
    ) : reminder.status === "no" ? (
      <span className="ov-chip">Not your role</span>
    ) : (
      <span className="ov-chip ov-chip--warn">
        {reminder.status === "no_role" ? "No role chosen" : "Could not confirm"}
      </span>
    );

  return (
    <Tile span={span} title="Will you be pinged" chips={chip}>
      <Stat value={answer} label="When a bump is due" />

      <p className="ov-body">
        {reminder.status === "yes"
          ? "You hold this server's reminder role, so the bot mentions you when a bump comes off cooldown."
          : reminder.status === "no"
            ? "The reminder pings one role in this server, and you do not have it. Ask a server manager if you want to be reminded."
            : reminder.status === "no_role"
              ? "No reminder role has been chosen in this server yet, so the bot has nobody to ping when a bump is due."
              : "We could not confirm your roles in this server just now, so we will not guess. Reload the page to try again."}
      </p>

      <Rule />

      <div>
        <KeyValue k="Reminder role chosen" v={reminder.reminder_role_set ? "Yes" : "No"} />
        <KeyValue k="Watching a bump channel" v={reminder.bump_channel_set ? "Yes" : "No"} />
        <KeyValue k="Bump bots tracked" v={reminder.bots_tracked} />
      </div>
    </Tile>
  );
}
