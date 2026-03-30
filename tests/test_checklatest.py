from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bot.commands import format_result
from bot.modrinth import ModrinthClient


@dataclass
class MockVersionConfig:
    sodium_release: str | None = "0.3.0"
    lithium_release: str | None = "0.2.0"
    fabric_api_release: str | None = "0.100.0"
    armor_poser_release: str | None = "1.5.0"
    armor_poser_beta: str | None = "1.6.0-beta"
    mc_versions: list[str] | None = None


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
    def mock_modrinth_api(self) -> Generator[MagicMock, None, None]:
        with patch.object(httpx.Client, "get") as mock_get:
            yield mock_get

    def _setup_mock_responses(
        self,
        mock_get: MagicMock,
        config: MockVersionConfig | None = None,
    ) -> None:
        if config is None:
            config = MockVersionConfig()
        if config.mc_versions is None:
            config.mc_versions = ["1.21.5", "1.21.4", "1.21.3"]

        sodium_versions = []
        if config.sodium_release:
            sodium_versions.append(
                _make_mod_version(config.sodium_release, config.mc_versions, ["fabric", "forge"])
            )

        lithium_versions = []
        if config.lithium_release:
            lithium_versions.append(
                _make_mod_version(config.lithium_release, config.mc_versions, ["fabric", "forge"])
            )

        fabric_api_versions = []
        if config.fabric_api_release:
            fabric_api_versions.append(
                _make_mod_version(config.fabric_api_release, config.mc_versions, ["fabric"])
            )

        armor_poser_versions = []
        if config.armor_poser_release:
            armor_poser_versions.append(
                _make_mod_version(
                    config.armor_poser_release, config.mc_versions, ["fabric", "quilt"]
                )
            )
        if config.armor_poser_beta:
            armor_poser_versions.append(
                _make_mod_version(
                    config.armor_poser_beta,
                    config.mc_versions,
                    ["fabric", "quilt"],
                    "beta",
                    "beta-id",
                )
            )

        mc_versions = config.mc_versions

        def get_side_effect(path: str, **_kwargs: object) -> MagicMock:
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

    def test_all_mods_compatible_with_release(self, mock_modrinth_api: MagicMock) -> None:
        self._setup_mock_responses(mock_modrinth_api)

        client = ModrinthClient()
        result = client.check_mods_compatibility(
            self.TEST_MODS, self.TEST_MC_VERSION, self.TEST_LOADER
        )
        client.close()

        assert len(result.mods) == self.TEST_MOD_COUNT  # noqa: S101
        assert result.all_compatible is True  # noqa: S101

        sodium = next(m for m in result.mods if m.slug == "sodium")
        assert sodium.compatible is True  # noqa: S101
        assert sodium.latest_version_str == "0.3.0"  # noqa: S101

        armor_poser = next(m for m in result.mods if m.slug == "armor-poser")
        assert armor_poser.compatible is True  # noqa: S101
        assert armor_poser.specified_channel == "beta"  # noqa: S101
        assert armor_poser.error is not None  # noqa: S101
        assert "release 1.5.0 is available" in armor_poser.error  # noqa: S101
        assert "Consider removing :beta" in armor_poser.error  # noqa: S101

    def test_beta_mod_compatible_when_beta_exists(self, mock_modrinth_api: MagicMock) -> None:
        self._setup_mock_responses(
            mock_modrinth_api,
            MockVersionConfig(armor_poser_release=None, armor_poser_beta="1.6.0-beta"),
        )

        client = ModrinthClient()
        result = client.check_mods_compatibility(
            ["armor-poser:beta"], self.TEST_MC_VERSION, self.TEST_LOADER
        )
        client.close()

        assert len(result.mods) == 1  # noqa: S101
        armor_poser = result.mods[0]
        assert armor_poser.compatible is True  # noqa: S101
        assert armor_poser.specified_channel == "beta"  # noqa: S101
        assert armor_poser.error is None  # noqa: S101

    def test_beta_mod_incompatible_when_beta_missing_but_release_exists(
        self, mock_modrinth_api: MagicMock
    ) -> None:
        self._setup_mock_responses(
            mock_modrinth_api,
            MockVersionConfig(armor_poser_release="1.5.0", armor_poser_beta=None),
        )

        client = ModrinthClient()
        result = client.check_mods_compatibility(
            ["armor-poser:beta"], self.TEST_MC_VERSION, self.TEST_LOADER
        )
        client.close()

        assert len(result.mods) == 1  # noqa: S101
        armor_poser = result.mods[0]
        assert armor_poser.compatible is False  # noqa: S101
        assert armor_poser.specified_channel == "beta"  # noqa: S101
        assert armor_poser.error is not None  # noqa: S101
        assert "No beta version" in armor_poser.error  # noqa: S101
        assert "Found release: 1.5.0" in armor_poser.error  # noqa: S101

    def test_mod_incompatible_for_unsupported_mc_version(
        self, mock_modrinth_api: MagicMock
    ) -> None:
        self._setup_mock_responses(
            mock_modrinth_api,
            MockVersionConfig(sodium_release="0.2.0", mc_versions=["1.20.4", "1.20.1"]),
        )

        client = ModrinthClient()
        result = client.check_mods_compatibility(["sodium"], "1.21.5", self.TEST_LOADER)
        client.close()

        assert len(result.mods) == 1  # noqa: S101
        sodium = result.mods[0]
        assert sodium.compatible is False  # noqa: S101
        assert sodium.error is not None  # noqa: S101
        assert "No release version" in sodium.error  # noqa: S101

    def test_format_result_with_all_compatible(self, mock_modrinth_api: MagicMock) -> None:
        self._setup_mock_responses(mock_modrinth_api)

        client = ModrinthClient()
        result = client.check_mods_compatibility(
            self.TEST_MODS, self.TEST_MC_VERSION, self.TEST_LOADER
        )
        client.close()

        embed = format_result(result)

        assert embed.title is not None  # noqa: S101
        assert "✅" in embed.title  # noqa: S101
        assert "1.21.5" in embed.title  # noqa: S101

    def test_format_result_shows_beta_suffix(self, mock_modrinth_api: MagicMock) -> None:
        self._setup_mock_responses(
            mock_modrinth_api,
            MockVersionConfig(armor_poser_release=None, armor_poser_beta="1.6.0-beta"),
        )

        client = ModrinthClient()
        result = client.check_mods_compatibility(
            ["armor-poser:beta"], self.TEST_MC_VERSION, self.TEST_LOADER
        )
        client.close()

        embed = format_result(result)
        fields = embed.to_dict()["fields"]

        compatible_field = next(f for f in fields if "Compatible" in f["name"])
        assert "armor-poser:beta" in compatible_field["value"]  # noqa: S101

    def test_format_result_shows_release_note_for_beta_mod(
        self, mock_modrinth_api: MagicMock
    ) -> None:
        self._setup_mock_responses(mock_modrinth_api)

        client = ModrinthClient()
        result = client.check_mods_compatibility(
            ["armor-poser:beta"], self.TEST_MC_VERSION, self.TEST_LOADER
        )
        client.close()

        embed = format_result(result)
        fields = embed.to_dict()["fields"]

        compatible_field = next(f for f in fields if "Compatible" in f["name"])
        assert "armor-poser:beta" in compatible_field["value"]  # noqa: S101
        assert "Note: release 1.5.0 is available" in compatible_field["value"]  # noqa: S101
