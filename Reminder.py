import asyncio
import os
import signal
from typing import Optional

from dotenv import load_dotenv
from shared_bot import bot  # bot instance only; no secrets imported
from utils.logger import get_logger

logger = get_logger("Leveling")

def _load_env() -> tuple[str, int]:
    load_dotenv()
    token = os.getenv("TOKEN")
    app_id = os.getenv("DISCORD_CLIENT_ID")  # needed by the bot (validated by shared_bot)

    if not token:
        logger.critical("Missing TOKEN environment variable.")
        raise SystemExit(2)

    if not app_id:
        logger.critical("Missing DISCORD_CLIENT_ID environment variable.")
        raise SystemExit(2)

    try:
        return token, int(app_id)
    except ValueError:
        logger.critical("DISCORD_CLIENT_ID must be an integer.")
        raise SystemExit(2)


async def shutdown_handler(bot_instance, reason: str = "shutdown"):
    logger.info(f"Initiating graceful shutdown due to {reason}...")
    try:
        if hasattr(bot_instance, "rotate_status") and bot_instance.rotate_status:
            bot_instance.rotate_status.cancel()
            logger.info("Status rotation stopped")
    except Exception as e:
        logger.error(f"Error stopping status rotation: {e}")

    try:
        # Stop OAuth server
        if hasattr(bot_instance, "oauth_server") and bot_instance.oauth_server:
            await bot_instance.oauth_server.stop()
            logger.info("OAuth server stopped")
    except Exception as e:
        logger.error(f"Error stopping OAuth server: {e}")

    try:
        if not bot_instance.is_closed():
            await bot_instance.close()
            logger.info("Discord bot shutdown completed")
    except Exception as shutdown_error:
        logger.error(f"Error during bot shutdown: {shutdown_error}")


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event):
    def _trigger(sig_name: str):
        logger.info(f"Received {sig_name}, signaling shutdown...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _trigger, sig.name)
        except NotImplementedError:
            # Fallback for platforms where add_signal_handler is not implemented (e.g., Windows)
            signal.signal(sig, lambda *_: _trigger(sig.name))


async def start_services():
    token, _ = _load_env()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, stop_event)

    bot_task: Optional[asyncio.Task] = None
    try:
        bot_task = asyncio.create_task(bot.start(token), name="discord-bot")
        logger.info("Discord bot task started")
        # Wait until either bot stops or we receive a stop signal
        done, pending = await asyncio.wait(
            {bot_task, asyncio.create_task(stop_event.wait(), name="shutdown-waiter")},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if stop_event.is_set():
            await shutdown_handler(bot, reason="signal")
        else:
            # Bot task finished first; check for exceptions
            if bot_task in done:
                exc = bot_task.exception()
                if exc:
                    logger.error("Bot task failed", exc_info=exc)
                    raise exc
                logger.info("Bot exited cleanly")

    except asyncio.CancelledError:
        logger.info("Services received shutdown cancellation")
        await shutdown_handler(bot, reason="cancelled")
    except Exception as e:
        logger.error(f"Error in services: {e}", exc_info=True)
        await shutdown_handler(bot, reason="error")
        raise
    finally:
        # Ensure the bot task is cleaned up
        if bot_task and not bot_task.done():
            bot_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bot_task


if __name__ == "__main__":
    import contextlib
    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        logger.info("Shutdown initiated by KeyboardInterrupt")
    except SystemExit as e:
        # Propagate non-zero exit for CI/Orchestration visibility
        raise
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise SystemExit(1)