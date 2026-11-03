"""Regional announcements are excluded; current daily data stays strict."""

import asyncio
from datetime import datetime
import json
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import ParseError
from train_operation_info.models import AlertEffect, LineStatus
from train_operation_info.providers.jrw import JrWestProvider

_FIXTURE = Path(__file__).parent / "fixtures" / "jrw_announcements_20261102.json"


class _ObservedWest(JrWestProvider):
    def _now(self) -> datetime:
        return datetime.fromisoformat("2026-11-02T05:19:40+00:00")


def test_official_regional_notices_do_not_affect_daily_snapshots() -> None:
    payload = _FIXTURE.read_bytes()
    without_notices = json.loads(payload)
    assert any(area.get("areaAnnouncements") for area in without_notices["areaTrafficInfos"])
    for area in without_notices["areaTrafficInfos"]:
        area.pop("areaAnnouncements", None)

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = _ObservedWest(client=client)
            tracker = Tracker(enabled_providers=("jrw",), overrides=(provider,))
            await tracker.refresh()
            previous = provider.lines
            # NORMAL refers only to the daily-data scope, not actual Mine service.
            assert provider.mine.status is LineStatus.NORMAL
            assert provider.mine.alerts == ()
            assert provider.sanyo.status is LineStatus.DELAYED
            assert any(a.effect is AlertEffect.DELAYS for a in provider.sanyo.active_alerts)
            assert not any(a.alert_id.startswith("jrw:announcement:") for a in provider.alerts)
            payload = json.dumps(without_notices).encode()
            await tracker.refresh()
            assert provider.lines == previous
    asyncio.run(scenario())


@pytest.mark.parametrize("excluded_value", [None, 123, "invalid", {}, [{"versions": []}]])
def test_excluded_announcement_data_is_not_parsed(excluded_value: object) -> None:
    payload = _FIXTURE.read_bytes()
    changed = json.loads(payload)
    for area in changed["areaTrafficInfos"]:
        area["areaAnnouncements"] = excluded_value

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = _ObservedWest(client=client)
            await provider.refresh()
            previous = provider.lines
            payload = json.dumps(changed).encode()
            await provider.refresh()
            assert provider.lines == previous
    asyncio.run(scenario())


def test_daily_long_term_prose_is_retained_without_classification() -> None:
    data = json.loads(_FIXTURE.read_bytes())
    body = "当分の間、運転を見合わせています。2027年1月10日、長期運転見合わせを実施します。"
    for area in data["areaTrafficInfos"]:
        for day in area["dailyData"]:
            for place in day["placeTrafficInfos"]:
                for traffic in place.get("conventionalLineTrafficInfos", []):
                    if traffic["lineName"] == "山陽線":
                        for detail in traffic["conventionalLineTrafficInfoDetails"]:
                            for version in detail["versionDetail"]:
                                version["body"] = body

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=data),
        )) as client:
            provider = JrWestProvider(client=client)
            await provider.refresh()
            assert provider.sanyo.status is LineStatus.DELAYED
            assert provider.sanyo.active_alerts
            assert all(a.description == body for a in provider.sanyo.alerts)
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["empty_versions", "wrong_body_type", "naive_time"])
def test_bad_daily_data_still_preserves_previous_snapshot(change: str) -> None:
    payload = _FIXTURE.read_bytes()
    bad = json.loads(payload)
    area = next(a for a in bad["areaTrafficInfos"] if a["id"] == 3)
    day = next(d for d in area["dailyData"] if d["date"] == "2026-11-02")
    traffic = next(t for p in day["placeTrafficInfos"] for t in p["conventionalLineTrafficInfos"]
                   if t["lineName"] == "山陽線")
    detail = traffic["conventionalLineTrafficInfoDetails"][0]
    if change == "empty_versions":
        detail["versionDetail"] = []
    elif change == "wrong_body_type":
        detail["versionDetail"][0]["body"] = 123
    else:
        detail["versionDetail"][0]["updatedAt"] = "2026-11-02T04:00:00"

    async def scenario() -> None:
        nonlocal payload
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload),
        )) as client:
            provider = JrWestProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            payload = json.dumps(bad).encode()
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous
            assert provider.sanyo.active_alerts
    asyncio.run(scenario())
