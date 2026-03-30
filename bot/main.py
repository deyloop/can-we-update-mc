from __future__ import annotations

import logging
import sys
from pathlib import Path

import discord

from bot.commands import setup as setup_commands
from bot.config import Config, load_config

logger = logging.getLogger(__name__)


class CanWeUpdateMC(discord.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)

        self.config = config
        self._commands_setup = False

    async def on_ready(self) -> None:
        logger.info(f"Bot connected as {self.user}")

        if not self._commands_setup:
            setup_commands(self, self.config)
            self._commands_setup = True
            logger.info(f"Commands registered. Pending: {len(self._pending_application_commands)}")
            logger.info(
                f"Pending command names: {[c.name for c in self._pending_application_commands]}"
            )

        await self.sync_commands()
        logger.info(
            f"Sync complete. Application commands: {[c.name for c in self.application_commands]}"
        )


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def run_bot(config_path: str | Path | None = None) -> None:
    setup_logging()

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        logger.error(f"Config file error: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Config validation error: {e}")
        sys.exit(1)

    bot = CanWeUpdateMC(config)
    bot.run(config.discord.token)


def main() -> None:
    run_bot()


if __name__ == "__main__":
    main()
