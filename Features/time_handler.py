import asyncio
from typing import Callable, Dict, Optional, Any, List, Tuple
import time
import random
from dataclasses import dataclass, asdict
from storage.logging import get_logger

logger = get_logger("TimeHandler")

@dataclass
class TimerMeta:
    guild_id: int
    channel_id: int
    name: str
    timer_type: str
    delay: float
    scheduled_delay: float  # delay after applying jitter
    created_mono: float
    end_mono: float
    attempts: int = 0
    max_retries: int = 0
    backoff: float = 2.0
    jitter: float = 0.0
    callback_timeout: Optional[float] = 15.0  # seconds, None = no timeout


class TimerHandler:
    def __init__(self, bot):
        self.bot = bot
        self.active_timers: Dict[str, asyncio.Task] = {}
        self.timer_ends: Dict[str, float] = {}  # monotonic end times
        self.timer_meta: Dict[str, TimerMeta] = {}  # additional metadata for visibility and control
        self._lock = asyncio.Lock()

    @staticmethod
    def make_timer_id(guild_id: int, channel_id: int, timer_type: str, name: str) -> str:
        return f"{guild_id}:{channel_id}:{timer_type}:{name}"

    async def run_timer(
        self,
        channel_id: int,
        guild_id: int,
        name: str,
        delay: float,
        callback: Callable[..., Any],
        timer_type: str = "generic",
        *,
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        jitter: float = 0.0,                 # up to N seconds of random jitter added once on schedule
        max_retries: int = 0,                # retry callback failures
        backoff: float = 2.0,                # exponential backoff base (seconds)
        callback_timeout: Optional[float] = 15.0,  # timeout for callback execution
        replace_if_sooner_than: float = 2.0  # if an existing timer would fire within this many seconds earlier, keep it
    ) -> str:
        """
        Schedule and run a timer with the specified parameters.

        Args:
            channel_id: Discord channel ID
            guild_id: Discord guild ID
            name: Name/identifier for this timer
            delay: Delay in seconds before timer triggers
            callback: Async function to call when timer expires
            timer_type: Type of timer (e.g., "bump", "reminder", etc.)
            args/kwargs: Arguments to pass to callback
            jitter: Random jitter added to delay to reduce coordination spikes
            max_retries: Number of times to retry callback on failure
            backoff: Base seconds for exponential backoff between retries
            callback_timeout: Max seconds to allow callback to run
            replace_if_sooner_than: Keep existing timer if it fires earlier than the new one by this margin
        """
        args = args or ()
        kwargs = kwargs or {}

        timer_id = self.make_timer_id(guild_id, channel_id, timer_type, name)

        # Calculate scheduled delay with jitter (one-time)
        scheduled_delay = max(0.0, float(delay)) + (random.uniform(0, jitter) if jitter > 0 else 0.0)
        end_mono = time.monotonic() + scheduled_delay

        async with self._lock:
            # If an earlier timer already exists, keep it to avoid drifting reminders later
            if timer_id in self.active_timers and not self.active_timers[timer_id].done():
                existing_remaining = self.get_remaining_time(timer_id)
                if existing_remaining is not None and existing_remaining + replace_if_sooner_than <= scheduled_delay:
                    logger.info(f"Keeping existing timer (earlier or similar): {timer_id} "
                                f"(existing ~{existing_remaining:.2f}s, new ~{scheduled_delay:.2f}s)")
                    return timer_id
                # Otherwise, replace it
                self.active_timers[timer_id].cancel()
                logger.info(f"Cancelled existing timer to reschedule: {timer_id}")

            meta = TimerMeta(
                guild_id=guild_id,
                channel_id=channel_id,
                name=name,
                timer_type=timer_type,
                delay=float(delay),
                scheduled_delay=scheduled_delay,
                created_mono=time.monotonic(),
                end_mono=end_mono,
                attempts=0,
                max_retries=int(max_retries),
                backoff=float(backoff),
                jitter=float(jitter),
                callback_timeout=callback_timeout,
            )
            self.timer_meta[timer_id] = meta
            self.timer_ends[timer_id] = end_mono

            async def timer_task():
                try:
                    logger.info(f"Timer started: {timer_id} for {scheduled_delay:.2f} seconds")
                    # Use a single sleep; end time recorded with monotonic prevents drift for remaining queries
                    await asyncio.sleep(scheduled_delay)

                    attempt = 0
                    while True:
                        try:
                            meta.attempts = attempt + 1
                            if meta.callback_timeout is not None:
                                await asyncio.wait_for(callback(*args, **kwargs), timeout=meta.callback_timeout)
                            else:
                                await callback(*args, **kwargs)
                            logger.info(f"Timer completed: {timer_id}")
                            break  # success
                        except asyncio.TimeoutError:
                            logger.warning(f"Timer callback timed out: {timer_id}")
                            exc = "timeout"
                        except asyncio.CancelledError:
                            logger.info(f"Timer cancelled during callback: {timer_id}")
                            raise
                        except Exception as es:
                            logger.error(f"Error in timer callback {timer_id}: {es}", exc_info=True)
                            exc = es

                        attempt += 1
                        if attempt > meta.max_retries:
                            logger.error(f"Timer {timer_id} exhausted retries ({meta.max_retries}); giving up.")
                            break

                        backoff_delay = meta.backoff * (2 ** (attempt - 1))
                        # Optional jitter on retries: reuse jitter parameter to randomize the backoff slightly
                        if meta.jitter > 0:
                            backoff_delay += random.uniform(0, min(1.0, meta.jitter))
                        logger.info(f"Retrying timer callback {timer_id} in {backoff_delay:.2f}s (attempt {attempt}/{meta.max_retries})")
                        await asyncio.sleep(backoff_delay)

                except asyncio.CancelledError:
                    logger.info(f"Timer cancelled: {timer_id}")
                    raise
                except Exception as es:
                    logger.error(f"Unhandled error in timer {timer_id}: {es}", exc_info=True)
                finally:
                    # Cleanup
                    async with self._lock:
                        self.active_timers.pop(timer_id, None)
                        self.timer_ends.pop(timer_id, None)
                        self.timer_meta.pop(timer_id, None)

            task = asyncio.create_task(timer_task(), name=f"timer:{timer_id}")
            self.active_timers[timer_id] = task

            logger.info(f"Scheduled new timer: {timer_id}")
            return timer_id

    def get_remaining_time(self, timer_id: str) -> Optional[float]:
        """
        Get the remaining time for a timer in seconds.
        Returns None if timer is not found or already finished.
        """
        task = self.active_timers.get(timer_id)
        if task and not task.done():
            end_time = self.timer_ends.get(timer_id)
            if end_time is not None:
                remaining = end_time - time.monotonic()
                return max(0.0, float(remaining))
        return None

    def cancel_timer(self, timer_id: str) -> bool:
        """
        Cancel a running timer by its ID.
        Returns True if the timer was canceled, False if it wasn't found.
        """
        task = self.active_timers.get(timer_id)
        if task:
            task.cancel()
            # Cleanup happens in task.finally; also pre-clean here just in case
            self.active_timers.pop(timer_id, None)
            self.timer_ends.pop(timer_id, None)
            self.timer_meta.pop(timer_id, None)
            logger.info(f"Cancelled timer: {timer_id}")
            return True
        return False

    def cancel_by_scope(
        self,
        *,
        guild_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        timer_type: Optional[str] = None
    ) -> int:
        """
        Cancel timers filtered by scope. Returns number of cancelled timers.
        """
        to_cancel: List[str] = []
        for tid, meta in list(self.timer_meta.items()):
            if guild_id is not None and meta.guild_id != guild_id:
                continue
            if channel_id is not None and meta.channel_id != channel_id:
                continue
            if timer_type is not None and meta.timer_type != timer_type:
                continue
            to_cancel.append(tid)

        count = 0
        for tid in to_cancel:
            if self.cancel_timer(tid):
                count += 1
        if count:
            logger.info(f"Cancelled {count} timer(s) by scope "
                        f"(guild={guild_id}, channel={channel_id}, type={timer_type})")
        return count

    def list_timers(self) -> List[dict]:
        """
        Return a snapshot of timers with metadata and remaining seconds.
        """
        result = []
        for tid, meta in self.timer_meta.items():
            remaining = self.get_remaining_time(tid)
            payload = asdict(meta)
            payload["timer_id"] = tid
            payload["remaining"] = remaining
            result.append(payload)
        return result

    def pause_timer(self, timer_id: str) -> Optional[float]:
        """
        Pause a timer by cancelling it but returning the remaining time
        so that it can be resumed later. Returns the remaining seconds or None.
        """
        remaining = self.get_remaining_time(timer_id)
        if remaining is not None:
            self.cancel_timer(timer_id)
        return remaining

    async def resume_timer(
        self,
        timer_id: str,
        remaining_seconds: float,
        callback: Callable[..., Any],
        *,
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        max_retries: int = 0,
        backoff: float = 2.0,
        callback_timeout: Optional[float] = 15.0,
    ) -> Optional[str]:
        """
        Resume a paused timer by scheduling a new one with the same id components.
        The timer_id is re-derived from its parts; this method expects timer_id format guild:channel:type:name.
        """
        try:
            gid_str, cid_str, typ, name = timer_id.split(":", 3)
            return await self.run_timer(
                int(cid_str),
                int(gid_str),
                name,
                max(0.0, float(remaining_seconds)),
                callback,
                typ,
                args=args,
                kwargs=kwargs,
                jitter=0.0,
                max_retries=max_retries,
                backoff=backoff,
                callback_timeout=callback_timeout,
                replace_if_sooner_than=0.0
            )
        except Exception as e:
            logger.error(f"Failed to resume timer {timer_id}: {e}", exc_info=True)
            return None

    async def cancel_all(self) -> int:
        """
        Cancel all timers (for graceful shutdown). Returns count.
        """
        to_cancel = list(self.active_timers.keys())
        for tid in to_cancel:
            self.cancel_timer(tid)
        if to_cancel:
            # Give tasks a moment to observe cancellation
            await asyncio.sleep(0)
            logger.info(f"Cancelled all timers: {len(to_cancel)}")
        return len(to_cancel)