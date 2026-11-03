"""Source-status applicability and regression tests against narrative inference."""

import asyncio
from datetime import datetime
import json
from pathlib import Path
from typing import Literal

import httpx
from bs4 import BeautifulSoup
from pydantic import ValidationError
import pytest

from train_operation_info import Tracker
from train_operation_info.models import (
    AlertEffect, AlertTiming, LineStatus, ServiceAlert,
)
from train_operation_info.providers.base import make_alert
from train_operation_info.providers.classification import timing_from_status
from train_operation_info.providers.jreast import JrEastProvider
from train_operation_info.providers.jrshikoku import JrShikokuProvider
from train_operation_info.providers.jrw import JrWestProvider
from train_operation_info.providers.yahoo import YahooArea, YahooProvider

_OBSERVED = datetime.fromisoformat("2026-11-02T14:19:40+09:00")
_FIXTURES = Path(__file__).parent / "fixtures"


class _ObservedYahoo(YahooProvider):
    def _now(self) -> datetime:
        return _OBSERVED


def test_alert_schema_has_no_duration_or_scheduled_placeholder() -> None:
    line = Tracker(enabled_providers=()).jrw.mine
    alert = make_alert(line, LineStatus.DELAYED, "遅延", "原文", timing=AlertTiming.ACTIVE)
    assert alert.effect is AlertEffect.DELAYS
    assert "duration" not in alert.model_dump()
    assert ServiceAlert.model_validate_json(alert.model_dump_json()) == alert
    invalid_duration = alert.model_dump(mode="json")
    invalid_duration["duration"] = "long_term"
    with pytest.raises(ValidationError):
        ServiceAlert.model_validate_json(json.dumps(invalid_duration))
    invalid_timing = alert.model_dump(mode="json")
    invalid_timing["timing"] = "scheduled"
    with pytest.raises(ValidationError):
        ServiceAlert.model_validate_json(json.dumps(invalid_timing))
    with pytest.raises(ValidationError):
        setattr(alert, "timing", AlertTiming.UNKNOWN)


@pytest.mark.parametrize(("status", "expected"), [
    (LineStatus.NORMAL, AlertTiming.UNKNOWN),
    (LineStatus.UNKNOWN, AlertTiming.UNKNOWN),
    (LineStatus.ALERT, AlertTiming.UNKNOWN),
    (LineStatus.DELAYED, AlertTiming.ACTIVE),
    (LineStatus.SUSPENDED, AlertTiming.ACTIVE),
    (LineStatus.PARTIAL_SUSPENSION, AlertTiming.ACTIVE),
])
def test_applicability_uses_only_explicit_source_status(
    status: LineStatus, expected: AlertTiming,
) -> None:
    assert timing_from_status(status) is expected


def test_real_east_mixed_long_term_and_future_notices_are_retained() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        area = request.url.path.rsplit("/", 1)[-1].removesuffix(".aspx")
        return httpx.Response(200, content=(_FIXTURES / f"jreast_{area}_20261102.html").read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = JrEastProvider(client=client)
            await provider.refresh()
            assert len(provider.alerts) == 49
            for line in (provider.aterazawa, provider.ominato, provider.oga, provider.kesennuma,
                         provider.gono, provider.hachinohe, provider.hanawa):
                assert line.alerts, line.name
                assert line.status is LineStatus.ALERT
                assert all(a.timing is AlertTiming.UNKNOWN for a in line.alerts)
            assert provider.koumi.active_alerts
            assert provider.koumi.status is LineStatus.SUSPENDED
            assert provider.kitakami.status is LineStatus.SUSPENDED
            assert any("当面運転を見合わせます" in a.description for a in provider.kitakami.alerts)
            assert provider.kitakami.active_alerts
            assert any("当分の間" in a.description for a in provider.yonesaka.alerts)
            assert provider.yokosuka.active_alerts
    asyncio.run(scenario())


def test_real_shikoku_mixed_long_term_notice_is_retained_unclassified() -> None:
    async def scenario() -> None:
        raw = (_FIXTURES / "jrshikoku_20260712052626.html").read_bytes()
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=raw),
        )) as client:
            provider = JrShikokuProvider(client=client)
            await provider.refresh()
            alert, = provider.yodo.alerts
            assert provider.yodo.status is LineStatus.ALERT
            assert "当分の間" in alert.description
            assert "運転再開の時期は未定" in alert.description
            assert alert.timing is AlertTiming.UNKNOWN
            assert provider.yodo.updated_at is not None
    asyncio.run(scenario())


def test_real_yahoo_other_preserves_notice_without_inferring_applicability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.removeprefix("/diainfo/").replace("/", "_")
        return httpx.Response(200, content=(_FIXTURES / f"yahoo_{name}.html").read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _ObservedYahoo(areas=(YahooArea.CHUGOKU,), client=client)
            await provider.refresh()
            line = provider.mine
            assert line.status is LineStatus.ALERT
            assert line.unclassified_alerts == line.alerts
            assert not line.active_alerts
            assert "運転を見合わせています" in line.alerts[0].description
    asyncio.run(scenario())


@pytest.mark.parametrize("provider_name", ["jrw", "jreast", "jrshikoku", "yahoo"])
@pytest.mark.parametrize("body", [
    "11月10日に運休しますとお知らせしていましたが、運休しません。",
    "一時的なウェブサイトの表示不具合があります。列車は運転を見合わせています。",
    "長期運転見合わせは終了しました。現在は平常運転です。",
    "運転を見合わせていますとお知らせしていましたが、現在は運転を再開しています。",
    "当分の間、運転を見合わせています。",
    "2027年1月10日、長期運転見合わせを実施します。",
    "一時的な運転見合わせです。",
    "11月10日に運休します。（11月2日 5時0分掲載）",
])
def test_notice_prose_never_sets_duration_or_applicability(
    provider_name: Literal["jrw", "jreast", "jrshikoku", "yahoo"], body: str,
) -> None:
    async def scenario() -> None:
        if provider_name == "jrw":
            data = json.loads((_FIXTURES / "jrw_announcements_20261102.json").read_bytes())
            for area in data["areaTrafficInfos"]:
                for day in area["dailyData"]:
                    for place in day["placeTrafficInfos"]:
                        for traffic in place.get("conventionalLineTrafficInfos", []):
                            if traffic["lineName"] == "山陽線":
                                for detail in traffic["conventionalLineTrafficInfoDetails"]:
                                    detail["conditionName"] = "お知らせ"
                                    for version in detail["versionDetail"]:
                                        version["title"] = "運行情報"
                                        version["body"] = body
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=data),
            )) as client:
                west = JrWestProvider(client=client)
                await west.refresh()
                line = west.sanyo
        elif provider_name == "jreast":
            def east_handler(request: httpx.Request) -> httpx.Response:
                area = request.url.path.rsplit("/", 1)[-1].removesuffix(".aspx")
                soup = BeautifulSoup((_FIXTURES / f"jreast_{area}_20261102.html").read_bytes(), "html.parser")
                for link in soup.select("a[href$='lineid=chuoline']"):
                    state = link.select_one(".traininfo-routes__status")
                    assert state is not None
                    state["class"] = "traininfo-routes__status info"
                    state.string = "お知らせ"
                    note = soup.new_tag("p", attrs={"class": "traininfo-routes__note"})
                    note.string = body
                    link.append(note)
                return httpx.Response(200, text=str(soup))
            async with httpx.AsyncClient(transport=httpx.MockTransport(east_handler)) as client:
                east = JrEastProvider(client=client)
                await east.refresh()
                line = east.chuo
        elif provider_name == "jrshikoku":
            soup = BeautifulSoup((_FIXTURES / "jrshikoku_20260712052626.html").read_bytes(), "html.parser")
            note = soup.select_one(".detail_txt")
            assert note is not None
            note.string = body
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, text=str(soup)),
            )) as client:
                shikoku = JrShikokuProvider(client=client)
                await shikoku.refresh()
                line = shikoku.yodo
        else:
            def yahoo_handler(request: httpx.Request) -> httpx.Response:
                name = request.url.path.removeprefix("/diainfo/").replace("/", "_")
                raw = (_FIXTURES / f"yahoo_{name}.html").read_bytes()
                if name == "508_0":
                    soup = BeautifulSoup(raw, "html.parser")
                    note = soup.select_one("#mdServiceStatus dl > dd > p")
                    assert note is not None
                    note.string = body + "（11月2日 5時0分掲載）"
                    return httpx.Response(200, text=str(soup))
                return httpx.Response(200, content=raw)
            async with httpx.AsyncClient(transport=httpx.MockTransport(yahoo_handler)) as client:
                yahoo = _ObservedYahoo(areas=(YahooArea.CHUGOKU,), client=client)
                await yahoo.refresh()
                line = yahoo.mine
        assert line.status is LineStatus.ALERT
        assert line.alerts
        assert all(body in alert.description for alert in line.alerts)
        assert all(alert.timing is AlertTiming.UNKNOWN for alert in line.alerts)
        assert all(alert.active_from is None and alert.active_until is None for alert in line.alerts)
        assert not line.active_alerts
    asyncio.run(scenario())


def test_applicability_views_partition_active_and_unknown_notices() -> None:
    provider = JrEastProvider()
    line = provider.yamanote
    active = make_alert(line, LineStatus.DELAYED, "遅延", "a", timing=AlertTiming.ACTIVE)
    unknown = make_alert(line, LineStatus.ALERT, "案内", "b")
    replaced = line.model_copy(update={"alerts": (active, unknown), "status": LineStatus.DELAYED})
    provider._lines = (replaced,)
    tracker = Tracker(enabled_providers=("jreast",), overrides=(provider,))
    for collection in (replaced, provider, tracker):
        assert collection.alerts == (active, unknown)
        assert collection.active_alerts == (active,)
        assert collection.unclassified_alerts == (unknown,)
    assert not Tracker(enabled_providers=(), overrides=(provider,)).active_alerts
