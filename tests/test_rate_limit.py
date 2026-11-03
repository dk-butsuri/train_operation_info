"""A refresh within rate_limit seconds of the previous attempt does not access the network."""

import asyncio
import math

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, RefreshError
from train_operation_info.models import LineStatus
from train_operation_info.providers import base
from train_operation_info.providers.osaka_monorail import OsakaMonorailProvider

_NORMAL = (
    '<div class="operationStatus"><p class="operationStatus__status">'
    "現在、平常通り運行しております。</p></div>"
).encode()


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(base, "monotonic", fake)
    return fake


def _client(requests: list[httpx.Request], status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, content=_NORMAL)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_default_is_keihan_tracker_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # Undo the conftest override to observe the shipped default.
    assert OsakaMonorailProvider().rate_limit == 30.0
    assert Tracker(enabled_providers=("osaka_monorail",)).osaka_monorail.rate_limit == 30.0


def test_refresh_within_interval_keeps_snapshot_without_request(clock: _Clock) -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []
        async with _client(requests) as client:
            provider = OsakaMonorailProvider(client=client)
            provider.rate_limit = 30.0
            await provider.refresh()
            lines = provider.lines
            assert lines[0].status is LineStatus.NORMAL

            clock.now += 29.9
            await provider.refresh()
            assert len(requests) == 1
            assert provider.lines is lines

            clock.now += 0.1
            await provider.refresh()
            assert len(requests) == 2
            assert provider.lines is not lines
    asyncio.run(run())


def test_failed_attempt_counts_and_is_reported_until_retry(clock: _Clock) -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []
        async with _client(requests, status_code=503) as client:
            provider = OsakaMonorailProvider(client=client)
            provider.rate_limit = 30.0
            with pytest.raises(FetchError) as first:
                await provider.refresh()
            clock.now += 10
            # Not retried, but the stale snapshot is not reported as a success.
            with pytest.raises(FetchError) as skipped:
                await provider.refresh()
            assert skipped.value is first.value
            assert len(requests) == 1
            assert provider.lines[0].status is LineStatus.UNKNOWN
    asyncio.run(run())


def test_cancelled_attempt_does_not_block_retry(clock: _Clock) -> None:
    async def run() -> None:
        started = asyncio.Event()
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                started.set()
                await asyncio.sleep(10)
            return httpx.Response(200, content=_NORMAL)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OsakaMonorailProvider(client=client)
            provider.rate_limit = 30.0
            task = asyncio.create_task(provider.refresh())
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await provider.refresh()
            assert len(requests) == 2
            assert provider.lines[0].status is LineStatus.NORMAL
    asyncio.run(run())


def test_concurrent_refreshes_share_one_request(clock: _Clock) -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []
        async with _client(requests) as client:
            provider = OsakaMonorailProvider(client=client)
            provider.rate_limit = 30.0
            await asyncio.gather(provider.refresh(), provider.refresh(), provider.refresh())
            assert len(requests) == 1
    asyncio.run(run())


def test_tracker_applies_rate_limit_only_to_built_providers(clock: _Clock) -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []
        async with _client(requests) as client:
            injected = OsakaMonorailProvider(client=client)
            injected.rate_limit = 5.0
            tracker = Tracker(
                enabled_providers=("osaka_monorail", "hanshin"), client=client,
                rate_limit=60.0, overrides=(injected,),
            )
            assert tracker.osaka_monorail.rate_limit == 5.0
            assert tracker.hanshin.rate_limit == 60.0

            with pytest.raises(RefreshError) as first:  # Hanshin cannot parse this page.
                await tracker.refresh()
            assert set(first.value.errors) == {"hanshin"}
            assert len(requests) == 2
            clock.now += 10
            # Only the injected provider's 5 s limit has passed; Hanshin keeps its failure.
            with pytest.raises(RefreshError) as second:
                await tracker.refresh()
            assert set(second.value.errors) == {"hanshin"}
            assert len(requests) == 3
    asyncio.run(run())


def test_interval_below_floor_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # Undo the conftest override to observe the shipped floor.
    assert base.MIN_RATE_LIMIT == 10.0
    for value in (0.0, 9.9):
        with pytest.raises(ValueError):
            Tracker(enabled_providers=("osaka_monorail",), rate_limit=value)
        provider = OsakaMonorailProvider()
        with pytest.raises(ValueError):
            provider.rate_limit = value
        assert provider.rate_limit == 30.0
    assert Tracker(enabled_providers=("osaka_monorail",), rate_limit=10).osaka_monorail.rate_limit == 10.0


@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf])
def test_invalid_rate_limit_is_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        Tracker(enabled_providers=("osaka_monorail",), rate_limit=value)
    provider = OsakaMonorailProvider()
    with pytest.raises(ValueError):
        provider.rate_limit = value
    assert provider.rate_limit == 0.0


def test_requests_identify_the_library() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []
        async with _client(requests) as client:
            await OsakaMonorailProvider(client=client).refresh()
        assert requests[0].headers["User-Agent"] == base.USER_AGENT
    asyncio.run(run())


def test_caller_user_agent_is_kept() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, content=_NORMAL)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers={"User-Agent": "my-signage/1.0"},
        ) as client:
            await OsakaMonorailProvider(client=client).refresh()
        assert requests[0].headers["User-Agent"] == "my-signage/1.0"
    asyncio.run(run())
