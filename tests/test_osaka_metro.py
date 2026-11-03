"""Archived official summaries and synthetic cases for defensive parsing."""

import asyncio
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import (
    AlertEffect, Line, LineId, LineStatus, ProviderId,
)
from train_operation_info.providers.osaka_metro import OsakaMetroProvider
from train_operation_info import Tracker

_NAMES = (
    "御堂筋線", "谷町線", "四つ橋線", "中央線", "千日前線", "堺筋線",
    "長堀鶴見緑地線", "今里筋線", "ニュートラム",
)


def _html(
    labels: dict[str, str] | None = None,
    *,
    names: tuple[str, ...] = _NAMES,
    timestamp: str = "2026/11/01 22:26現在",
) -> str:
    overrides = {} if labels is None else labels
    rows = "".join(
        '<dd class="headerMenuOperationArea_subway"><a><ul>'
        '<li class="subwayArea_Status">'
        f'<img alt="{escape(overrides.get(name, "アイコン通常運転"))}"></li>'
        f'<li class="subwayArea_LineName"><img alt="{escape(name)}"></li>'
        '</ul></a></dd>'
        for name in names
    )
    return (
        '<dl class="headerMenuOperationArea">'
        f'<dt><p class="cs-currentTimeSP">{escape(timestamp)}</p></dt>'
        f'{rows}</dl>'
    )


def test_initial_state_is_unknown_and_properties_do_not_fetch() -> None:
    tracker = Tracker(enabled_providers=("osaka_metro",))
    assert len(tracker.lines) == 9
    assert len(tracker.unknown_lines) == 9
    assert tracker.delay_lines == ()
    assert tracker.affected_lines == ()
    assert tracker.osaka_metro.midosuji.operator.name == "Osaka Metro"
    assert tracker.osaka_metro.new_tram.name == "ニュートラム"
    assert tracker.osaka_metro.midosuji.fetched_at is None


@pytest.mark.parametrize(
    ("label", "expected_status", "expected_effect"),
    [
        ("アイコン通常運転", LineStatus.NORMAL, None),
        ("アイコン遅延など", LineStatus.DELAYED, AlertEffect.DELAYS),
        ("アイコン運転見合わせ", LineStatus.SUSPENDED, AlertEffect.NO_SERVICE),
        ("未知の新しい表示", LineStatus.UNKNOWN, AlertEffect.UNKNOWN),
    ],
)
def test_status_alerts_and_lists(
    label: str,
    expected_status: LineStatus,
    expected_effect: AlertEffect | None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "subway.osakametro.co.jp"
        return httpx.Response(200, text=_html({"御堂筋線": label}))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("osaka_metro",), overrides=(OsakaMetroProvider(client=client),))
            before = tracker.osaka_metro.midosuji
            await tracker.refresh()
            line = tracker.osaka_metro.midosuji
            assert line.status is expected_status
            assert line.source_status == label
            assert line.line_id == LineId("jp:osaka_metro:midosuji")
            assert line.provider_id == ProviderId("osaka_metro")
            assert line.updated_at is not None
            assert line.updated_at.isoformat() == "2026-11-01T22:26:00+09:00"
            assert line.fetched_at is not None
            assert line.fetched_at.utcoffset() == timedelta(0)
            assert before.status is LineStatus.UNKNOWN
            assert before is not line
            assert not client.is_closed
            if expected_effect is None:
                assert line.alerts == ()
            else:
                assert len(line.alerts) == 1
                assert line.alerts[0].effect is expected_effect
                assert line.alerts[0].affected_line_ids == (line.line_id,)
                assert line.alerts[0].active_from is None
            assert (line in tracker.delay_lines) == (expected_status is LineStatus.DELAYED)
            assert (line in tracker.affected_lines) == (
                expected_status in (LineStatus.DELAYED, LineStatus.SUSPENDED)
            )
            assert (line in tracker.unknown_lines) == (expected_status is LineStatus.UNKNOWN)
            assert tracker.osaka_metro.get_line(line.line_id) is line
            assert tracker.osaka_metro.get_line(LineId("missing")) is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "bad_html",
    [
        "<html><h1>Maintenance</h1></html>",
        _html(names=_NAMES[:-1]),
        _html(names=(*_NAMES, _NAMES[0])),
        _html(names=(*_NAMES[:-1], "新路線")),
        _html(timestamp="not a timestamp"),
        _html().replace('class="cs-currentTimeSP"', 'class="changed"'),
        _html().replace('class="subwayArea_Status"', 'class="changed"', 1),
        _html().replace('alt="アイコン通常運転"', 'alt=""', 1),
    ],
)
def test_parse_failure_keeps_complete_previous_snapshot(bad_html: str) -> None:
    responses = iter([_html({"御堂筋線": "アイコン遅延など"}), bad_html])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=next(responses))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OsakaMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.midosuji.status is LineStatus.DELAYED

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "timeout"])
def test_fetch_failure_keeps_previous_snapshot(failure: str) -> None:
    count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(200, text=_html())
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(503)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OsakaMetroProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_models_are_frozen_strict_and_require_aware_timestamps() -> None:
    line = Tracker(enabled_providers=("osaka_metro",)).osaka_metro.midosuji
    with pytest.raises(ValidationError):
        # setattr exercises runtime immutability without a static assignment error.
        setattr(line, "name", "changed")
    with pytest.raises(ValidationError):
        Line(
            line_id=line.line_id, name=line.name, operator=line.operator,
            provider_id=line.provider_id, source_url=line.source_url,
            fetched_at=datetime(2026, 11, 1),
        )
    with pytest.raises(ValidationError):
        Line.model_validate({
            "line_id": str(line.line_id), "name": line.name,
            "operator": line.operator, "provider_id": str(line.provider_id),
            "source_url": line.source_url, "status": "normal",
            "fetched_at": datetime.now(timezone.utc),
        })


@pytest.mark.parametrize(
    ("capture", "expected_delayed", "expected_suspended"),
    [
        ("20230815015922", ("御堂筋線", "中央線"), ("ニュートラム",)),
        ("20240829220436", (), ("御堂筋線", "四つ橋線")),
        ("20240830010545", ("御堂筋線", "四つ橋線"), ()),
        ("20240830045314", (), ()),
        ("20260111081515", ("ニュートラム",), ()),
    ],
)
def test_archived_official_status_summary(
    capture: str,
    expected_delayed: tuple[str, ...],
    expected_suspended: tuple[str, ...],
) -> None:
    html = (Path(__file__).parent / "fixtures" / f"{capture}.html").read_text(
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("osaka_metro",), overrides=(OsakaMetroProvider(client=client),))
            await tracker.refresh()
            assert len(tracker.lines) == 9
            assert tuple(line.name for line in tracker.delay_lines) == expected_delayed
            assert tuple(
                line.name for line in tracker.lines
                if line.status is LineStatus.SUSPENDED
            ) == expected_suspended
            assert tracker.unknown_lines == ()
            assert len(tracker.affected_lines) == len(expected_delayed) + len(expected_suspended)
            for line in tracker.affected_lines:
                expected_effect = (
                    AlertEffect.NO_SERVICE if line.status is LineStatus.SUSPENDED
                    else AlertEffect.DELAYS
                )
                assert line.alerts[0].effect is expected_effect

    asyncio.run(scenario())


def test_archived_suspension_delay_and_recovery_sequence() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    captures = iter(("20240829220436", "20240830010545", "20240830045314"))

    def handler(request: httpx.Request) -> httpx.Response:
        html = (fixture_dir / f"{next(captures)}.html").read_text(encoding="utf-8")
        return httpx.Response(200, text=html)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("osaka_metro",), overrides=(OsakaMetroProvider(client=client),))
            await tracker.refresh()
            suspended = tracker.osaka_metro.midosuji
            assert suspended.status is LineStatus.SUSPENDED
            await tracker.refresh()
            delayed = tracker.osaka_metro.midosuji
            assert delayed.status is LineStatus.DELAYED
            await tracker.refresh()
            recovered = tracker.osaka_metro.midosuji
            assert recovered.status is LineStatus.NORMAL
            assert recovered.alerts == ()
            assert tracker.affected_lines == ()
            assert suspended.status is LineStatus.SUSPENDED

    asyncio.run(scenario())
