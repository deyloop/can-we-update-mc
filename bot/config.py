from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass
class DiscordConfig:
    token: str
    guild_id: int | None = None


@dataclass
class ModsConfig:
    file: str = "mods.txt"
    loader: str = "fabric"


@dataclass
class Config:
    discord: DiscordConfig
    mods: ModsConfig

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        discord_data = data.get("discord", {})
        discord = DiscordConfig(
            token=discord_data.get("token", ""),
            guild_id=discord_data.get("guild_id") or None,
        )

        mods_data = data.get("mods", {})
        mods = ModsConfig(
            file=mods_data.get("file", "mods.txt"),
            loader=mods_data.get("loader", "fabric"),
        )

        return cls(discord=discord, mods=mods)

    def get_mods_file_path(self) -> Path:
        return Path(self.mods.file).expanduser().resolve()

    def load_mods_list(self) -> list[str]:
        mods_file = self.get_mods_file_path()
        if not mods_file.exists():
            return []
        return self._parse_mods_file(mods_file)

    def _parse_mods_file(self, path: Path) -> list[str]:
        mods: list[str] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    mods.append(stripped)
        return mods


def load_config(config_path: str | Path | None = None) -> Config:
    load_dotenv()

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.toml"

    config_path = Path(config_path).expanduser().resolve()

    if not config_path.exists():
        msg = f"Config file not found: {config_path}"
        raise FileNotFoundError(msg)

    with config_path.open("rb") as f:
        data = tomllib.load(f)

    config = Config.from_dict(data)

    token_from_env = os.environ.get("DISCORD_TOKEN", "").strip()
    if token_from_env:
        config.discord.token = token_from_env

    if not config.discord.token:
        msg = (
            "Discord token not configured. "
            "Set DISCORD_TOKEN in .env or discord.token in config.toml"
        )
        raise ValueError(msg)

    return config
