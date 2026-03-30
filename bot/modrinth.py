from __future__ import annotations

import asyncio
import re
import time
from asyncio import Semaphore
from dataclasses import dataclass
from typing import Literal, Self

import httpx

MODRINTH_API_BASE = "https://api.modrinth.com/v2"

VALID_LOADERS = {"fabric", "forge", "quilt", "neoforge", "paper", "bukkit", "spigot"}
VALID_PREFIXES = VALID_LOADERS | {"datapack"}
VALID_RELEASE_TYPES = {"release", "beta", "alpha"}
HTTP_NOT_FOUND = 404
MOD_ENTRY_MAX_PARTS = 3

MAX_VERSIONS_SHOWN = 5
MAX_RETRIES = 3
RATE_LIMIT_PER_MINUTE = 50
RATE_LIMIT_WINDOW_SECONDS = 60
CACHE_TTL_SECONDS = 300

COMPATIBLE_COLOR = 0x00FF00
INCOMPATIBLE_COLOR = 0xFF0000
PARTIAL_COLOR = 0xFFAA00


@dataclass
class ParsedModEntry:
    prefix: str | None
    project: str
    version_spec: str | None

    @classmethod
    def parse(cls, entry: str) -> ParsedModEntry:
        parts = entry.split(":", 2)
        if len(parts) == 1:
            return cls(prefix=None, project=parts[0], version_spec=None)
        if parts[0] in VALID_PREFIXES:
            prefix = parts[0]
            if len(parts) == MOD_ENTRY_MAX_PARTS:
                version_index = 2
                return cls(prefix=prefix, project=parts[1], version_spec=parts[version_index])
            return cls(prefix=prefix, project=parts[1], version_spec=None)
        return cls(prefix=None, project=parts[0], version_spec=parts[1])

    def effective_loader(self, default_loader: str) -> str:
        if self.prefix in VALID_LOADERS:
            return self.prefix
        return default_loader

    def effective_channel(self) -> str | None:
        if self.version_spec in VALID_RELEASE_TYPES:
            return self.version_spec
        return None

    def is_hash_specified(self) -> bool:
        return self.version_spec is not None and self.version_spec not in VALID_RELEASE_TYPES


@dataclass
class ModVersion:
    name: str
    version_number: str
    game_versions: list[str]
    version_type: Literal["release", "beta", "alpha"]
    loaders: list[str]
    date_published: str
    version_id: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> ModVersion:
        return cls(
            name=data["name"],
            version_number=data["version_number"],
            game_versions=data["game_versions"],
            version_type=data["version_type"],
            loaders=data["loaders"],
            date_published=data["date_published"],
            version_id=data.get("id"),
        )


@dataclass
class ModInfo:
    slug: str
    title: str | None
    compatible: bool
    compatible_version: ModVersion | None
    latest_version: ModVersion | None
    all_versions: list[ModVersion]
    error: str | None = None
    hash_version: ModVersion | None = None
    specified_hash: str | None = None
    specified_channel: str | None = None

    @property
    def latest_version_str(self) -> str | None:
        if self.latest_version:
            return f"{self.latest_version.version_number}"
        return None


@dataclass
class ProjectInfo:
    slug: str
    title: str
    description: str | None
    categories: list[str]
    client_side: str | None
    server_side: str | None

    @classmethod
    def from_json(cls, data: dict) -> ProjectInfo:
        return cls(
            slug=data.get("slug", ""),
            title=data.get("title", ""),
            description=data.get("description"),
            categories=data.get("categories", []),
            client_side=data.get("client_side"),
            server_side=data.get("server_side"),
        )


@dataclass
class CompatibilityResult:
    minecraft_version: str
    loader: str
    mods: list[ModInfo]

    @property
    def all_compatible(self) -> bool:
        return all(mod.compatible for mod in self.mods)

    @property
    def compatible_mods(self) -> list[ModInfo]:
        return [mod for mod in self.mods if mod.compatible]

    @property
    def incompatible_mods(self) -> list[ModInfo]:
        return [mod for mod in self.mods if not mod.compatible]


@dataclass
class CachedVersionList:
    versions: list[ModVersion]
    cached_at: float


class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max_per_minute
        self.semaphore = Semaphore(max_per_minute)
        self.tokens: list[float] = []

    async def acquire(self) -> None:
        now = time.monotonic()
        self.tokens = [t for t in self.tokens if now - t < RATE_LIMIT_WINDOW_SECONDS]

        if len(self.tokens) >= self.max_per_minute:
            wait_time = 60 - (now - self.tokens[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                self.tokens = []

        await self.semaphore.acquire()
        self.tokens.append(time.monotonic())


class ModrinthClient:
    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=MODRINTH_API_BASE,
            timeout=timeout,
            headers={
                "User-Agent": "can-we-update-mc/0.1.0 (https://github.com/deyloop/can-we-update-mc)"
            },
        )
        self._max_retries = max_retries
        self._version_cache: dict[str, CachedVersionList] = {}
        self._rate_limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _is_cache_valid(self, cached: CachedVersionList) -> bool:
        return time.monotonic() - cached.cached_at < CACHE_TTL_SECONDS

    async def _get_with_retry(self, path: str, **kwargs: object) -> dict | list:
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                await self._rate_limiter.acquire()
                response = await self._client.get(path, **kwargs)
                response.raise_for_status()
                return response.json()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2**attempt)
        if last_error:
            raise last_error
        msg = "Unexpected error in _get_with_retry"
        raise RuntimeError(msg)

    async def get_project_versions(
        self,
        project_id: str,
        game_versions: list[str] | None = None,
        loaders: list[str] | None = None,
        version_type: str | None = None,
    ) -> list[ModVersion]:
        cached = self._version_cache.get(project_id)
        if cached and self._is_cache_valid(cached):
            all_versions = cached.versions
        else:
            data = await self._get_with_retry(
                f"/project/{project_id}/version", params={"include_changelog": "false"}
            )
            all_versions = [ModVersion.from_json(v) for v in data] if isinstance(data, list) else []
            self._version_cache[project_id] = CachedVersionList(
                versions=all_versions, cached_at=time.monotonic()
            )

        versions = list(all_versions)

        if game_versions:
            versions = [v for v in versions if any(gv in v.game_versions for gv in game_versions)]
        if loaders:
            versions = [v for v in versions if any(loader in v.loaders for loader in loaders)]
        if version_type:
            versions = [v for v in versions if v.version_type == version_type]

        return versions

    def clear_cache(self) -> None:
        self._version_cache.clear()

    async def find_version_by_id(self, project_id: str, id_or_hash: str) -> ModVersion | None:
        versions = await self.get_project_versions(project_id)
        search_lower = id_or_hash.lower()

        for version in versions:
            if version.version_id and version.version_id.lower() == search_lower:
                return version

        for version in versions:
            for f in version.files or []:
                sha1 = f.get("hashes", {}).get("sha1", "").lower()
                if sha1.startswith(search_lower):
                    return version

        return None

    async def _check_hash_version(
        self,
        parsed: ParsedModEntry,
        minecraft_version: str,
    ) -> ModInfo:
        hash_spec = parsed.version_spec
        if hash_spec is None:
            msg = "version_spec should not be None when is_hash_specified is True"
            raise ValueError(msg)

        version = await self.find_version_by_id(parsed.project, hash_spec)

        if version is None:
            return ModInfo(
                slug=parsed.project,
                title=None,
                compatible=False,
                compatible_version=None,
                latest_version=None,
                all_versions=[],
                error=f"Hash '{hash_spec}' not found in any version",
                specified_hash=hash_spec,
            )

        all_project_versions = await self.get_project_versions(parsed.project)

        supported_mc_versions = version.game_versions
        compatible = minecraft_version in supported_mc_versions

        if compatible:
            return ModInfo(
                slug=parsed.project,
                title=None,
                compatible=True,
                compatible_version=version,
                latest_version=version,
                all_versions=all_project_versions,
                hash_version=version,
                specified_hash=hash_spec,
            )

        return ModInfo(
            slug=parsed.project,
            title=None,
            compatible=False,
            compatible_version=None,
            latest_version=version,
            all_versions=all_project_versions,
            error=(
                f"Hash '{hash_spec}' targets MC {supported_mc_versions[0]}, not {minecraft_version}"
            ),
            hash_version=version,
            specified_hash=hash_spec,
        )

    async def search_project(self, query: str) -> dict | None:
        data = await self._get_with_retry(
            "/search",
            params={"query": query, "limit": 5},
        )
        if not isinstance(data, dict):
            return None
        hits = data.get("hits")
        if not isinstance(hits, list):
            return None
        for hit in hits:
            if isinstance(hit, dict) and hit.get("slug", "").lower() == query.lower():
                return hit
        if hits:
            first_hit = hits[0]
            if isinstance(first_hit, dict):
                return first_hit
        return None

    async def get_project_info(self, project_id: str) -> ProjectInfo:
        data = await self._get_with_retry(f"/project/{project_id}")
        if isinstance(data, dict):
            return ProjectInfo.from_json(data)
        msg = f"Unexpected response type: {type(data)}"
        raise TypeError(msg)

    async def get_game_versions(self) -> list[dict]:
        data = await self._get_with_retry("/tag/game_version")
        if not isinstance(data, list):
            return []
        return data

    async def get_latest_minecraft_version(self) -> str | None:
        versions = await self.get_game_versions()
        stable_versions = [
            v["version"]
            for v in versions
            if v.get("version_type") == "release" and self._is_stable_mc_version(v["version"])
        ]
        return stable_versions[0] if stable_versions else None

    @staticmethod
    def _is_stable_mc_version(version: str) -> bool:
        return bool(re.match(r"^\d+\.\d+(\.\d+)?$", version))

    @staticmethod
    def _build_incompatible_error(
        requested_channel: str,
        minecraft_version: str,
        loader_text: str,
        available_channels: dict[str, list[ModVersion]],
        higher_channels: dict[str, list[str]],
    ) -> str:
        for higher in higher_channels.get(requested_channel, []):
            if higher in available_channels:
                version = available_channels[higher][0]
                return (
                    f"No {requested_channel} version for Minecraft "
                    f"{minecraft_version}{loader_text}. "
                    f"Found {higher}: {version.version_number}"
                )
        if available_channels:
            channels_text = ", ".join(available_channels.keys())
            return (
                f"No {requested_channel} version for Minecraft {minecraft_version}"
                f"{loader_text}. Available: {channels_text}"
            )
        return f"No {requested_channel} version for Minecraft {minecraft_version}{loader_text}."

    async def check_mod_compatibility(
        self,
        project: str,
        minecraft_version: str,
        loader: str,
    ) -> ModInfo:
        parsed = ParsedModEntry.parse(project)

        if parsed.is_hash_specified():
            return await self._check_hash_version(parsed, minecraft_version)

        is_datapack = parsed.prefix == "datapack"
        effective_loader = parsed.effective_loader(loader)
        effective_loaders: list[str] = [] if is_datapack else [effective_loader]
        specified_channel = parsed.effective_channel()
        requested_channel = specified_channel or "release"

        loader_text = f" with {effective_loader}" if effective_loaders else ""

        try:
            available_channels = await self._get_available_versions(
                parsed.project, minecraft_version, effective_loaders
            )

            all_versions = await self.get_project_versions(
                parsed.project,
                loaders=effective_loaders if effective_loaders else None,
            )
            latest = all_versions[0] if all_versions else None

            if requested_channel in available_channels:
                compatible_version = available_channels[requested_channel][0]

                if requested_channel != "release" and "release" in available_channels:
                    release_version = available_channels["release"][0]
                    note = (
                        f" Note: release {release_version.version_number} is available. "
                        f"Consider removing :{requested_channel} from your mods list."
                    )
                else:
                    note = None

                return ModInfo(
                    slug=parsed.project,
                    title=None,
                    compatible=True,
                    compatible_version=compatible_version,
                    latest_version=compatible_version,
                    all_versions=available_channels.get(requested_channel, []),
                    specified_channel=specified_channel,
                    error=note,
                )

            higher_channels: dict[str, list[str]] = {
                "release": [],
                "beta": ["release"],
                "alpha": ["release", "beta"],
            }
            error = self._build_incompatible_error(
                requested_channel,
                minecraft_version,
                loader_text,
                available_channels,
                higher_channels,
            )

            return ModInfo(
                slug=parsed.project,
                title=None,
                compatible=False,
                compatible_version=None,
                latest_version=latest,
                all_versions=all_versions,
                error=error,
                specified_channel=specified_channel,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == HTTP_NOT_FOUND:
                return ModInfo(
                    slug=parsed.project,
                    title=None,
                    compatible=False,
                    compatible_version=None,
                    latest_version=None,
                    all_versions=[],
                    error=f"Project not found: {parsed.project}",
                    specified_channel=specified_channel,
                )
            return ModInfo(
                slug=parsed.project,
                title=None,
                compatible=False,
                compatible_version=None,
                latest_version=None,
                all_versions=[],
                error=f"HTTP error: {e.response.status_code}",
                specified_channel=specified_channel,
            )
        except Exception as e:
            return ModInfo(
                slug=parsed.project,
                title=None,
                compatible=False,
                compatible_version=None,
                latest_version=None,
                all_versions=[],
                error=str(e),
                specified_channel=specified_channel,
            )

    async def _get_available_versions(
        self,
        project_id: str,
        minecraft_version: str,
        loaders: list[str],
    ) -> dict[str, list[ModVersion]]:
        available_channels: dict[str, list[ModVersion]] = {}
        for channel in VALID_RELEASE_TYPES:
            channel_versions = await self.get_project_versions(
                project_id,
                game_versions=[minecraft_version],
                loaders=loaders if loaders else None,
                version_type=channel,
            )
            if channel_versions:
                available_channels[channel] = channel_versions
        return available_channels

    async def check_mods_compatibility(
        self,
        mods: list[str],
        minecraft_version: str,
        loader: str = "fabric",
    ) -> CompatibilityResult:
        results: list[ModInfo] = []
        for mod in mods:
            mod_info = await self.check_mod_compatibility(mod, minecraft_version, loader)
            results.append(mod_info)

        return CompatibilityResult(
            minecraft_version=minecraft_version,
            loader=loader,
            mods=results,
        )
