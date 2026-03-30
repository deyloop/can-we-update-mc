from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from bot.commands import format_result, validate_minecraft_version
from bot.modrinth import ModrinthClient, ModInfo, ModVersion, CompatibilityResult


def _make_mod_version(
    version_number: str,
    game_versions: list[str],
    loaders: list[str],
    version_type: str = "release",
    version_id: str = "test-id",
) -> dict:
    return {
        "name": f"Mod v{version_number}",
        "version_number": version_number,
        "game_versions": game_versions,
        "loaders": loaders,
        "version_type": version_type,
        "date_published": "2024-01-01T00:00:00Z",
        "files": [],
        "id": version_id,
    }


def _mock_response(json_data: dict | list) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = json_data
    response.raise_for_status.return_value = None
    return response


class TestCheckLatest:
    TEST_MODS: tuple[str, ...] = (
        "sodium",
        "lithium",
        "fabric-api",
        "armor-poser:beta",
    )
    TEST_MC_VERSION = "1.21.5"
    TEST_LOADER = "fabric"
    TEST_MOD_COUNT = 4

    @pytest.fixture
    def mock_httpx_client(self) -> MagicMock:
        with patch.object(httpx.AsyncClient, "get") as mock_get:
            yield mock_get

    def _setup_mock_responses(
        self,
        mock_get: MagicMock,
        mc_versions: list[str] | None = None,
        sodium_release: str | None = "0.3.0",
        lithium_release: str | None = "0.2.0",
        fabric_api_release: str | None = "0.100.0",
        armor_poser_release: str | None = "1.5.0",
        armor_poser_beta: str | None = "1.6.0-beta",
    ) -> None:
        if mc_versions is None:
            mc_versions = ["1.21.5", "1.21.4", "1.21.3"]

        sodium_versions = []
        if sodium_release:
            sodium_versions.append(
                _make_mod_version(sodium_release, mc_versions, ["fabric", "forge"])
            )

        lithium_versions = []
        if lithium_release:
            lithium_versions.append(
                _make_mod_version(lithium_release, mc_versions, ["fabric", "forge"])
            )

        fabric_api_versions = []
        if fabric_api_release:
            fabric_api_versions.append(
                _make_mod_version(fabric_api_release, mc_versions, ["fabric"])
            )

        armor_poser_versions = []
        if armor_poser_release:
            armor_poser_versions.append(
                _make_mod_version(armor_poser_release, mc_versions, ["fabric", "quilt"])
            )
        if armor_poser_beta:
            armor_poser_versions.append(
                _make_mod_version(
                    armor_poser_beta,
                    mc_versions,
                    ["fabric", "quilt"],
                    "beta",
                    "beta-id",
                )
            )

        def get_side_effect(path: str, **kwargs: object) -> MagicMock:
            if path == "/tag/game_version":
                return _mock_response([{"version": v} for v in mc_versions])
            if path.startswith("/project/sodium/version"):
                return _mock_response(sodium_versions)
            if path.startswith("/project/lithium/version"):
                return _mock_response(lithium_versions)
            if path.startswith("/project/fabric-api/version"):
                return _mock_response(fabric_api_versions)
            if path.startswith("/project/armor-poser/version"):
                return _mock_response(armor_poser_versions)
            return _mock_response([])

        mock_get.side_effect = get_side_effect

    @pytest.mark.asyncio
    async def test_all_mods_compatible_with_release(self, mock_httpx_client: MagicMock) -> None:
        self._setup_mock_responses(mock_httpx_client)

        async with ModrinthClient() as client:
            result = await client.check_mods_compatibility(
                self.TEST_MODS, self.TEST_MC_VERSION, self.TEST_LOADER
            )

        assert len(result.mods) == self.TEST_MOD_COUNT
        assert result.all_compatible is True

        sodium = next(m for m in result.mods if m.slug == "sodium")
        assert sodium.compatible is True
        assert sodium.latest_version_str == "0.3.0"

        armor_poser = next(m for m in result.mods if m.slug == "armor-poser")
        assert armor_poser.compatible is True
        assert armor_poser.specified_channel == "beta"
        assert armor_poser.error is not None
        assert "release 1.5.0 is available" in armor_poser.error
        assert "Consider removing :beta" in armor_poser.error

    @pytest.mark.asyncio
    async def test_beta_mod_compatible_when_beta_exists(self, mock_httpx_client: MagicMock) -> None:
        self._setup_mock_responses(
            mock_httpx_client,
            armor_poser_release=None,
            armor_poser_beta="1.6.0-beta",
        )

        async with ModrinthClient() as client:
            result = await client.check_mods_compatibility(
                ["armor-poser:beta"], self.TEST_MC_VERSION, self.TEST_LOADER
            )

        assert len(result.mods) == 1
        armor_poser = result.mods[0]
        assert armor_poser.compatible is True
        assert armor_poser.specified_channel == "beta"
        assert armor_poser.error is None

    @pytest.mark.asyncio
    async def test_beta_mod_incompatible_when_beta_missing_but_release_exists(
        self, mock_httpx_client: MagicMock
    ) -> None:
        self._setup_mock_responses(
            mock_httpx_client,
            armor_poser_release="1.5.0",
            armor_poser_beta=None,
        )

        async with ModrinthClient() as client:
            result = await client.check_mods_compatibility(
                ["armor-poser:beta"], self.TEST_MC_VERSION, self.TEST_LOADER
            )

        assert len(result.mods) == 1
        armor_poser = result.mods[0]
        assert armor_poser.compatible is False
        assert armor_poser.specified_channel == "beta"
        assert armor_poser.error is not None
        assert "No beta version" in armor_poser.error
        assert "Found release: 1.5.0" in armor_poser.error

    @pytest.mark.asyncio
    async def test_mod_incompatible_for_unsupported_mc_version(
        self, mock_httpx_client: MagicMock
    ) -> None:
        self._setup_mock_responses(
            mock_httpx_client,
            mc_versions=["1.20.4", "1.20.1"],
            sodium_release="0.2.0",
            lithium_release=None,
            fabric_api_release=None,
            armor_poser_release=None,
            armor_poser_beta=None,
        )

        async with ModrinthClient() as client:
            result = await client.check_mods_compatibility(["sodium"], "1.21.5", self.TEST_LOADER)

        assert len(result.mods) == 1
        sodium = result.mods[0]
        assert sodium.compatible is False
        assert sodium.error is not None
        assert "No release version" in sodium.error


class TestFormatResult:
    @pytest.fixture
    def mock_httpx_client(self) -> MagicMock:
        with patch.object(httpx.AsyncClient, "get") as mock_get:
            yield mock_get

    @pytest.mark.asyncio
    async def test_format_result_with_all_compatible(self, mock_httpx_client: MagicMock) -> None:
        mc_versions = ["1.21.5", "1.21.4", "1.21.3"]

        sodium_versions = [
            _make_mod_version("1.0.0", mc_versions, ["fabric"], version_id="sodium-id")
        ]
        lithium_versions = [
            _make_mod_version("1.0.0", mc_versions, ["fabric"], version_id="lithium-id")
        ]
        fabric_api_versions = [
            _make_mod_version("1.0.0", mc_versions, ["fabric"], version_id="fabric-api-id")
        ]
        armor_poser_versions = [
            _make_mod_version("1.0.0", mc_versions, ["fabric"], version_id="armor-poser-id"),
            _make_mod_version(
                "1.0.0-beta",
                mc_versions,
                ["fabric"],
                "beta",
                "armor-poser-beta-id",
            ),
        ]

        def get_side_effect(path: str, **kwargs: object) -> MagicMock:
            if path == "/tag/game_version":
                return _mock_response([{"version": v} for v in mc_versions])
            if path.startswith("/project/sodium/version"):
                return _mock_response(sodium_versions)
            if path.startswith("/project/lithium/version"):
                return _mock_response(lithium_versions)
            if path.startswith("/project/fabric-api/version"):
                return _mock_response(fabric_api_versions)
            if path.startswith("/project/armor-poser/version"):
                return _mock_response(armor_poser_versions)
            return _mock_response([])

        mock_httpx_client.side_effect = get_side_effect

        async with ModrinthClient() as client:
            result = await client.check_mods_compatibility(
                ["sodium", "lithium", "fabric-api", "armor-poser:beta"],
                "1.21.5",
                "fabric",
            )

        embed = format_result(result)

        assert embed.title is not None
        assert "✅" in embed.title
        assert "1.21.5" in embed.title


class TestValidateMinecraftVersion:
    def test_valid_version_with_patch(self) -> None:
        is_valid, error = validate_minecraft_version("1.21.5")
        assert is_valid is True
        assert error is None

    def test_valid_version_without_patch(self) -> None:
        is_valid, error = validate_minecraft_version("1.21")
        assert is_valid is True
        assert error is None

    def test_invalid_version_with_letters(self) -> None:
        is_valid, error = validate_minecraft_version("1.21.5snapshot")
        assert is_valid is False
        assert error is not None

    def test_invalid_version_empty(self) -> None:
        is_valid, error = validate_minecraft_version("")
        assert is_valid is False
        assert error is not None

    def test_invalid_version_none(self) -> None:
        is_valid, error = validate_minecraft_version(None)  # type: ignore[arg-type]
        assert is_valid is False
        assert error is not None

    def test_invalid_version_special_chars(self) -> None:
        is_valid, error = validate_minecraft_version("1.21-pre1")
        assert is_valid is False
        assert error is not None
