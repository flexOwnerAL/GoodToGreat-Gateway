"""Unit tests for ProviderRegistry and BaseProvider."""
import pytest
from typing import Any, AsyncIterator
from app.providers.base import BaseProvider
from app.providers.registry import ProviderRegistry


class _FakeProvider(BaseProvider):
    name = "fake"

    async def list_models(self) -> list[dict[str, Any]]:
        return [{"id": "fake:model1", "object": "model", "owned_by": "fake"}]

    async def generate(self, model: str, messages, **options) -> dict[str, Any]:
        return {"choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}


class _AnotherProvider(BaseProvider):
    name = "another"

    async def list_models(self) -> list[dict[str, Any]]:
        return [{"id": "another:m", "object": "model", "owned_by": "another"}]

    async def generate(self, model: str, messages, **options) -> dict[str, Any]:
        return {"choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}]}


def test_register_and_get():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    p = reg.get("fake")
    assert p.name == "fake"


def test_duplicate_registration_raises():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_FakeProvider())


def test_unknown_provider_raises():
    reg = ProviderRegistry()
    with pytest.raises(LookupError):
        reg.get("nonexistent")


def test_priority_order():
    reg = ProviderRegistry()
    reg.register(_FakeProvider(), priority=20)
    reg.register(_AnotherProvider(), priority=10)
    order = reg.priority_order()
    assert order[0] == "another"
    assert order[1] == "fake"


@pytest.mark.asyncio
async def test_list_all_models():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    reg.register(_AnotherProvider())
    models = await reg.list_all_models()
    ids = {m["id"] for m in models}
    assert "fake:model1" in ids
    assert "another:m" in ids


def test_resolve_provider_by_prefix():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    p = reg.resolve_provider("fake:model1")
    assert p is not None
    assert p.name == "fake"


def test_resolve_provider_unknown_returns_none():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    assert reg.resolve_provider("nonexistent:thing") is None


@pytest.mark.asyncio
async def test_base_provider_default_stream():
    """Default stream() implementation yields the full generate() response."""
    p = _FakeProvider()
    chunks = [c async for c in p.stream("fake:model1", [{"role": "user", "content": "hi"}])]
    assert "".join(chunks) == "ok"
