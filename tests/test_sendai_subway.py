"""Official normal captures; incidents, recovery and corruptions are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, LineStatus, ProviderId, UsagePermission
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.sendai_subway import SendaiSubwayProvider

_ROOT = "https://www.kotsu.city.sendai.jp/unkou/"
_FIXTURES = Path(__file__).parent / "fixtures"


def _synthetic(
    key: str = "nanbokusen", status: str = "平常運行", code: str = "ope_normal", extra: str = "",
) -> str:
    name = {"nanbokusen": "南北線", "touzaisen": "東西線"}[key]
    return (
        '<div id="mainarea"><div class="page_contents"><h2>運行情報</h2>'
        '<div class="page_inner"><section>'
        f'<div id="{key}" class="{key}_unkou_box"><dl class="clearfix">'
        f'<dt>地下鉄<br>{name}</dt><dd class="clearfix {code}"><div>{status}</div></dd>'
        f'</dl></div>{extra}<div class="chien_btn"><a href="/certificate">遅延証明書</a></div>'
        '</section></div></div></div><p>対象外のニュース：東西線運休</p>'
    )


@pytest.mark.parametrize("tozai_fixture", [
    "sendai_subway_tozai_normal.html", "sendai_subway_tozai_20260412141736.html",
])
def test_official_normal_captures_and_canonical_identity(tozai_fixture: str) -> None:
    namboku = (_FIXTURES / "sendai_subway_namboku_normal.html").read_bytes()
    tozai = (_FIXTURES / tozai_fixture).read_bytes()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert request.method == "GET" and request.headers["User-Agent"] == USER_AGENT
        assert str(request.url) in (_ROOT + "nanbokusen/", _ROOT + "touzaisen/")
        return httpx.Response(200, content=namboku if request.url.path.endswith("nanbokusen/") else tozai)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("sendai_subway",), client=client)
            provider = tracker.sendai_subway
            assert len(provider.unknown_lines) == 2
            await tracker.refresh()
            assert requests == [_ROOT + "nanbokusen/", _ROOT + "touzaisen/"]
            assert provider.lines == (provider.namboku, provider.tozai)
            assert not provider.alerts
            for line, name, key in zip(provider.lines, ("南北線", "東西線"), ("nanbokusen", "touzaisen")):
                assert line.status is LineStatus.NORMAL and line.source_status == "平常運行"
                assert line.source_line_names == (name,) and str(line.source_url) == _ROOT + key + "/"
                assert line.updated_at is None and line.fetched_at is not None
                assert line.fetched_at.utcoffset() == timedelta(0)
                assert line.operator.name == "仙台市交通局"
                yahoo = tracker.yahoo.get_line(line.line_id)
                assert yahoo is not None and yahoo is not line
                assert yahoo.operator == line.operator and yahoo.status is LineStatus.UNKNOWN
            assert not client.is_closed
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            assert str(provider.metadata.terms_url) == "https://www.kotsu.city.sendai.jp/menseki/"
            assert len(provider.metadata.endpoints) == 2
        assert ProviderId("sendai_subway") in {p.provider_id for p in Tracker().providers}

    asyncio.run(scenario())


@pytest.mark.parametrize(("status", "code", "extra"), [
    ("合成：運転見合わせ", "ope_down", '<div class="unkou_detail_text">明日は運休。東西線に言及。</div>'),
    ("合成：遅れ", "ope_lag", ""),
    ("平常運行", "ope_new", ""),
    ("平常運行", "ope_normal ope_new", ""),
    ("合成：遅延は発生していません。", "ope_normal", ""),
    ("合成：運転を再開しました。", "ope_down", ""),
    ("平常運行", "ope_normal", '<p>合成：長期案内</p><a href="/notice">詳細</a>'),
    ("平常運行", "ope_normal", '<img alt="合成：追加案内" src="/notice.png">'),
])
def test_synthetic_unknown_notices_and_recovery(status: str, code: str, extra: str) -> None:
    content = _synthetic(status=status, code=code, extra=extra)

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=(
                content if request.url.path.endswith("nanbokusen/") else _synthetic("touzaisen")
            )),
        )) as client:
            provider = SendaiSubwayProvider(client=client)
            tracker = Tracker(enabled_providers=("sendai_subway",), overrides=(provider,))
            await tracker.refresh()
            assert tracker.sendai_subway is provider
            assert provider.namboku.status is LineStatus.UNKNOWN
            assert provider.tozai.status is LineStatus.NORMAL
            alert, = tracker.unclassified_alerts
            assert alert.effect is AlertEffect.UNKNOWN and alert.timing is AlertTiming.UNKNOWN
            assert alert.affected_line_ids == (provider.namboku.line_id,)
            assert status in alert.description and "遅延証明書" not in alert.description
            if '/notice"' in extra:
                assert "https://www.kotsu.city.sendai.jp/notice" in alert.description
            if "長期案内" in extra:
                assert "長期案内" in alert.description
            if "東西線に言及" in extra:
                assert "東西線に言及" in alert.description
            assert not tracker.active_alerts and not tracker.affected_lines
            assert alert.active_from is None and alert.active_until is None
            assert provider.namboku.updated_at is None
            content = _synthetic()
            await tracker.refresh()
            assert not tracker.alerts and not tracker.unknown_lines

    asyncio.run(scenario())


@pytest.mark.parametrize(("old", "new"), [
    ('id="nanbokusen"', 'id="changed"'),
    ('class="nanbokusen_unkou_box"', 'class="changed"'),
    ("地下鉄<br>南北線", "地下鉄<br>東西線"),
    ("<h2>運行情報</h2>", "<h2>運行情報履歴</h2>"),
    ('class="page_inner"', 'class="changed"'),
    ('<dd class="clearfix ope_normal"><div>平常運行</div></dd>', ""),
    ('<dd class="clearfix ope_normal"><div>平常運行</div></dd>', '<dd></dd>'),
    ('<dt>地下鉄<br>南北線</dt>', '<dt>地下鉄<br>南北線</dt><dt>地下鉄<br>南北線</dt>'),
    ('</dl>', '<dd>重複</dd></dl>'),
    ('</section>', '<div id="nanbokusen" class="nanbokusen_unkou_box"></div></section>'),
    ('</section>', '<script>dynamicNotice()</script></section>'),
    ('</section>', '<img src="/notice.png"></section>'),
    ('</section>', '<a>詳細</a></section>'),
    ('</section>', '<a href="javascript:void(0)">詳細</a></section>'),
])
def test_synthetic_structure_errors_preserve_complete_snapshot(old: str, new: str) -> None:
    content = _synthetic(status="合成：案内あり", code="ope_down")

    async def scenario() -> None:
        nonlocal content
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=(
                content if request.url.path.endswith("nanbokusen/") else _synthetic("touzaisen")
            )),
        )) as client:
            provider = SendaiSubwayProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            content = _synthetic().replace(old, new, 1)
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["http", "parse", "network"])
def test_second_route_failure_is_atomic_and_disabled_provider_does_not_fetch(failure: str) -> None:
    fail = False
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        key = "nanbokusen" if request.url.path.endswith("nanbokusen/") else "touzaisen"
        if fail and key == "touzaisen":
            if failure == "network":
                raise httpx.ConnectError("synthetic network failure", request=request)
            return httpx.Response(503 if failure == "http" else 200, text="<html>truncated</html>")
        return httpx.Response(200, text=_synthetic(key, "合成：案内あり" if fail else "平常運行"))

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SendaiSubwayProvider(client=client)
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert not requests
            tracker = Tracker(enabled_providers=("sendai_subway",), overrides=(provider,))
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            error = captured.value.errors[ProviderId("sendai_subway")]
            assert isinstance(error, ParseError if failure == "parse" else FetchError)
            assert provider.lines is previous

    asyncio.run(scenario())
