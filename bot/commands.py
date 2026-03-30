from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.modrinth import ModInfo, ModrinthClient, ParsedModEntry

if TYPE_CHECKING:
    from bot.config import Config
    from bot.modrinth import CompatibilityResult


COMPATIBLE_COLOR = 0x00FF00
INCOMPATIBLE_COLOR = 0xFF0000
PARTIAL_COLOR = 0xFFAA00
MAX_MC_VERSIONS_SHOWN = 5

_config: Config | None = None


def set_config(config: Config) -> None:
    global _config  # noqa: PLW0603
    _config = config


def get_config() -> Config:
    if _config is None:
        msg = "Config not set"
        raise RuntimeError(msg)
    return _config


def _find_suggested_version(mod: ModInfo, minecraft_version: str) -> str:
    if not mod.all_versions:
        return ""

    for version in mod.all_versions:
        if minecraft_version in version.game_versions:
            return f" | Suggested: `{version.version_number}`"

    latest = mod.all_versions[0] if mod.all_versions else None
    if latest:
        supported = ", ".join(latest.game_versions[:MAX_MC_VERSIONS_SHOWN])
        if len(latest.game_versions) > MAX_MC_VERSIONS_SHOWN:
            supported += "..."
        return f" | Latest: `{latest.version_number}` (supports {supported})"
    return ""


def _format_hash_mod(mod: ModInfo, minecraft_version: str) -> str | None:
    if not mod.hash_version:
        return None
    mc_versions = ", ".join(mod.hash_version.game_versions[:MAX_MC_VERSIONS_SHOWN])
    remaining = len(mod.hash_version.game_versions) - MAX_MC_VERSIONS_SHOWN
    if remaining > 0:
        mc_versions += f" (+{remaining} more)"
    compat_note = (
        "📌 Pinned version is compatible"
        if mod.compatible
        else f"📌 Pinned version targets older MC{_find_suggested_version(mod, minecraft_version)}"
    )
    return (
        f"**{mod.slug}** (`{mod.hash_version.version_number}`)\n"
        f"   └─ Hash `{mod.specified_hash}` → MC: {mc_versions}\n"
        f"   └─ {compat_note}"
    )


def _get_channel_suffix(mod: ModInfo) -> str:
    if mod.specified_channel:
        return f":{mod.specified_channel}"
    return ""


def format_result(result: CompatibilityResult) -> discord.Embed:
    hash_mods = [m for m in result.mods if m.specified_hash]
    hash_slugs = {m.slug for m in hash_mods}
    compatible = [m for m in result.compatible_mods if m.slug not in hash_slugs]
    incompatible = [m for m in result.incompatible_mods if m.slug not in hash_slugs]

    all_compatible_excluding_hash = len(incompatible) == 0
    has_any_compatible = bool(compatible)
    title_suffix = " ✅" if all_compatible_excluding_hash else " ❌"
    color = (
        COMPATIBLE_COLOR
        if all_compatible_excluding_hash
        else PARTIAL_COLOR
        if has_any_compatible
        else INCOMPATIBLE_COLOR
    )

    embed = discord.Embed(
        title=f"Mod Compatibility Check for Minecraft {result.minecraft_version}{title_suffix}",
        color=color,
    )

    loader_display = result.loader.upper() if result.loader != "paper" else "Paper/Plugin"
    embed.add_field(
        name="Configuration",
        value=f"Loader: `{loader_display}`\nTotal mods: {len(result.mods)}",
        inline=False,
    )

    if hash_mods:
        hash_text_parts = [_format_hash_mod(mod, result.minecraft_version) for mod in hash_mods]
        hash_text = "\n\n".join(p for p in hash_text_parts if p)
        embed.add_field(
            name=f"Hash-Pinned ({len(hash_mods)})",
            value=hash_text[:1024],
            inline=False,
        )

    if compatible:
        compatible_text_parts = []
        for mod in compatible:
            version_str = f" (`{mod.latest_version_str}`)" if mod.latest_version_str else ""
            note = f"\n   └─ {mod.error}" if mod.error else ""
            compatible_text_parts.append(
                f"✅ **{mod.slug}{_get_channel_suffix(mod)}**{version_str}{note}"
            )
        compatible_text = "\n".join(compatible_text_parts)
        embed.add_field(
            name=f"Compatible ({len(compatible)})",
            value=compatible_text[:1024],
            inline=False,
        )

    if incompatible:
        incompatible_text_parts = [
            f"❌ **{mod.slug}{_get_channel_suffix(mod)}**\n   └─ {mod.error or 'Not compatible'}"
            for mod in incompatible
        ]
        incompatible_text = "\n\n".join(incompatible_text_parts)
        embed.add_field(
            name=f"Not Compatible ({len(incompatible)})",
            value=incompatible_text[:1024],
            inline=False,
        )

    regular_mods_count = len(result.mods) - len(hash_mods)
    summary = (
        f"✅ All {len(compatible)} mods are ready for Minecraft {result.minecraft_version}!"
        if all_compatible_excluding_hash
        else (
            f"⚠️ {len(incompatible)} of {regular_mods_count} mods are NOT ready for "
            f"Minecraft {result.minecraft_version}"
        )
    )
    embed.add_field(name="Summary", value=summary, inline=False)

    embed.set_footer(text="Powered by Modrinth API")

    return embed


def setup(bot: discord.Bot, config: Config) -> None:
    set_config(config)

    @bot.slash_command(
        name="check", description="Check if your mods are ready for a Minecraft version"
    )
    async def check(ctx: discord.ApplicationContext, version: str) -> None:
        await ctx.response.defer()

        cfg = get_config()
        mods = cfg.load_mods_list()
        if not mods:
            await ctx.followup.send(
                "No mods configured. Add mods to your mods file or check the config.",
                ephemeral=True,
            )
            return

        loader = cfg.mods.loader

        with ModrinthClient() as client:
            try:
                result = client.check_mods_compatibility(mods, version, loader)
            except Exception as e:
                await ctx.followup.send(
                    f"Error checking mods: {e}",
                    ephemeral=True,
                )
                return

        embed = format_result(result)
        await ctx.followup.send(embed=embed)

    @bot.slash_command(name="test", description="Test command - debug datapacks")
    async def test(ctx: discord.ApplicationContext) -> None:
        cfg = get_config()
        mods = cfg.load_mods_list()
        msg = f"Found {len(mods)} mods:\n"
        for mod in mods:
            parsed = ParsedModEntry.parse(mod)
            msg += (
                f"- {parsed.prefix or 'mod'}: {parsed.project} ({parsed.version_spec or 'any'})\n"
            )
        await ctx.response.send_message(msg, ephemeral=True)

    @bot.slash_command(
        name="checklatest",
        description="Check if your mods are ready for the latest Minecraft version",
    )
    async def check_latest(ctx: discord.ApplicationContext) -> None:
        await ctx.response.defer()

        cfg = get_config()
        mods = cfg.load_mods_list()
        if not mods:
            await ctx.followup.send(
                "No mods configured. Add mods to your mods file or check the config.",
                ephemeral=True,
            )
            return

        loader = cfg.mods.loader

        with ModrinthClient() as client:
            try:
                latest_version = client.get_latest_minecraft_version()
                if not latest_version:
                    await ctx.followup.send(
                        "Could not determine latest Minecraft version.",
                        ephemeral=True,
                    )
                    return

                result = client.check_mods_compatibility(mods, latest_version, loader)
            except Exception as e:
                await ctx.followup.send(
                    f"Error checking mods: {e}",
                    ephemeral=True,
                )
                return

        embed = format_result(result)
        await ctx.followup.send(embed=embed)

    @bot.slash_command(name="mods", description="Show the list of mods being tracked")
    async def mods(ctx: discord.ApplicationContext) -> None:
        cfg = get_config()
        mods_list = cfg.load_mods_list()
        if not mods_list:
            await ctx.response.send_message(
                "No mods configured.",
                ephemeral=True,
            )
            return

        mods_text = "\n".join(f"- {mod}" for mod in mods_list)
        embed = discord.Embed(
            title=f"Tracked Mods ({len(mods_list)})",
            description=mods_text,
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Config",
            value=f"Loader: `{cfg.mods.loader}`\nFile: `{cfg.mods.file}`",
            inline=False,
        )
        await ctx.response.send_message(embed=embed, ephemeral=True)
