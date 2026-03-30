from __future__ import annotations

from bot.modrinth import ModrinthClient, ParsedModEntry


class TestParsedModEntry:
    def test_parse_simple_slug(self) -> None:
        entry = ParsedModEntry.parse("sodium")
        assert entry.prefix is None  # noqa: S101
        assert entry.project == "sodium"  # noqa: S101
        assert entry.version_spec is None  # noqa: S101

    def test_parse_with_prefix(self) -> None:
        entry = ParsedModEntry.parse("fabric:sodium")
        assert entry.prefix == "fabric"  # noqa: S101
        assert entry.project == "sodium"  # noqa: S101
        assert entry.version_spec is None  # noqa: S101

    def test_parse_with_prefix_and_version(self) -> None:
        entry = ParsedModEntry.parse("fabric:sodium:0.5.0")
        assert entry.prefix == "fabric"  # noqa: S101
        assert entry.project == "sodium"  # noqa: S101
        assert entry.version_spec == "0.5.0"  # noqa: S101

    def test_parse_version_spec_only(self) -> None:
        entry = ParsedModEntry.parse("sodium:beta")
        assert entry.prefix is None  # noqa: S101
        assert entry.project == "sodium"  # noqa: S101
        assert entry.version_spec == "beta"  # noqa: S101

    def test_effective_loader_with_prefix(self) -> None:
        entry = ParsedModEntry.parse("forge:jei")
        assert entry.effective_loader("fabric") == "forge"  # noqa: S101

    def test_effective_loader_without_prefix(self) -> None:
        entry = ParsedModEntry.parse("sodium")
        assert entry.effective_loader("fabric") == "fabric"  # noqa: S101


class TestModrinthClient:
    def test_client_initialization(self) -> None:
        client = ModrinthClient()
        assert client._client is not None  # noqa: S101,SLF001
        client.close()

    def test_client_context_manager(self) -> None:
        with ModrinthClient() as client:
            assert client._client is not None  # noqa: S101,SLF001
