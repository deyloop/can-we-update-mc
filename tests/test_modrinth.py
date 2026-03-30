from __future__ import annotations

import pytest

from bot.modrinth import ModrinthClient, ParsedModEntry


class TestParsedModEntry:
    def test_parse_simple_slug(self) -> None:
        entry = ParsedModEntry.parse("sodium")
        assert entry.prefix is None
        assert entry.project == "sodium"
        assert entry.version_spec is None

    def test_parse_with_prefix(self) -> None:
        entry = ParsedModEntry.parse("fabric:sodium")
        assert entry.prefix == "fabric"
        assert entry.project == "sodium"
        assert entry.version_spec is None

    def test_parse_with_prefix_and_version(self) -> None:
        entry = ParsedModEntry.parse("fabric:sodium:0.5.0")
        assert entry.prefix == "fabric"
        assert entry.project == "sodium"
        assert entry.version_spec == "0.5.0"

    def test_parse_version_spec_only(self) -> None:
        entry = ParsedModEntry.parse("sodium:beta")
        assert entry.prefix is None
        assert entry.project == "sodium"
        assert entry.version_spec == "beta"

    def test_effective_loader_with_prefix(self) -> None:
        entry = ParsedModEntry.parse("forge:jei")
        assert entry.effective_loader("fabric") == "forge"

    def test_effective_loader_without_prefix(self) -> None:
        entry = ParsedModEntry.parse("sodium")
        assert entry.effective_loader("fabric") == "fabric"

    def test_effective_channel_with_release_type(self) -> None:
        entry = ParsedModEntry.parse("sodium:beta")
        assert entry.effective_channel() == "beta"

    def test_effective_channel_with_version_number(self) -> None:
        entry = ParsedModEntry.parse("sodium:0.5.0")
        assert entry.effective_channel() is None

    def test_is_hash_specified_with_version_number(self) -> None:
        entry = ParsedModEntry.parse("sodium:abc123")
        assert entry.is_hash_specified() is True

    def test_is_hash_specified_with_release_type(self) -> None:
        entry = ParsedModEntry.parse("sodium:beta")
        assert entry.is_hash_specified() is False


class TestModrinthClient:
    @pytest.mark.asyncio
    async def test_client_initialization(self) -> None:
        client = ModrinthClient()
        assert client._client is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_client_async_context_manager(self) -> None:
        async with ModrinthClient() as client:
            assert client._client is not None
