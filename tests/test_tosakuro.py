"""Real normal captures; abnormal, recovery and damage cases are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import AlertEffect, AlertTiming, LineStatus, ProviderId
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.tosakuro import TosaKuroshioProvider
from train_operation_info.providers.tosakuro.provider import _posts

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.tosakuro.com/"


def _home(first: str = "平常運行", second: str = "平常運行") -> bytes:
    return (
        '<html><body><div id="comp-m9tlcfob">'
        '<div id="comp-m9tlcfoj"><h1>ごめん・なはり線</h1></div>'
        '<div id="comp-mf4wtprw"><a href="https://www.tosakuro.com/post/synthetic-gomen">'
        f'<div data-hook="post-title"><h2>{first}</h2></div></a></div>'
        '<div id="comp-m9tlcfop"><h1>中村・宿毛線</h1></div>'
        '<div id="comp-mf4wv5z1"><a href="https://www.tosakuro.com/post/synthetic-nakamura">'
        f'<div data-hook="post-title"><h2>{second}</h2></div></a></div>'
        '</div><div data-hook="post-title">合成：別のお知らせ欄に運休案内</div></body></html>'
    ).encode()


def _article(title: str = "平常運行", body: str = "合成：運行案内本文") -> bytes:
    return (f'<html><h1 data-hook="post-title">{title}</h1>'
            f'<section data-hook="post-description"><p>{body}</p></section></html>').encode()


async def _refresh(home: bytes, first: bytes, second: bytes) -> TosaKuroshioProvider:
    pages = iter((home, first, second))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"] == USER_AGENT
        return httpx.Response(200, content=next(pages))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TosaKuroshioProvider(client=client)
        await provider.refresh()
        assert not client.is_closed
        return provider


def test_real_normal_articles_preserve_complete_information() -> None:
    provider = asyncio.run(_refresh(*(
        (_FIXTURES / name).read_bytes() for name in (
            "tosakuro_home.html", "tosakuro_gomen.html", "tosakuro_nakamura.html",
        )
    )))
    assert len(provider.lines) == 2 and len(provider.alerts) == 2
    assert all(line.status is LineStatus.NORMAL for line in provider.lines)
    for line in provider.lines:
        assert line.source_status == "平常運行" and line.updated_at is None
        assert line.fetched_at is not None and line.fetched_at.utcoffset() == timedelta(0)
        alert, = line.alerts
        assert alert.description and alert.effect is AlertEffect.OTHER
        assert alert.timing is AlertTiming.UNKNOWN and alert.affected_line_ids == ()
        assert alert.active_from is None and alert.active_until is None
        assert str(alert.source_url).startswith(_URL + "post/")
    assert provider.active_alerts == () and provider.affected_lines == ()


@pytest.mark.parametrize("timestamp, titles", [
    ("20260203070343", ("平常運行", "平常運行")),
    ("20260609203918", ("平常運転", "平常運行")),
    ("20260709051932", ("平常運行", "平常運行")),
    ("20260825063025", ("平常運行", "平常運行")),
])
def test_real_archived_route_headlines(timestamp: str, titles: tuple[str, str]) -> None:
    posts = _posts((_FIXTURES / f"tosakuro_home_{timestamp}.html").read_bytes())
    assert tuple(title for title, _ in posts) == titles


@pytest.mark.parametrize("title", [
    "合成：遅延", "合成：運転見合わせ", "合成：明日は運休予定", "合成：運転再開",
    "平常運行との案内を取り消します", "平常運行（合成：追加案内）",
])
def test_synthetic_unknown_headline_never_guesses_impact(title: str) -> None:
    provider = asyncio.run(_refresh(_home(title), _article(title), _article()))
    assert provider.gomen_nahari.status is LineStatus.UNKNOWN
    assert provider.nakamura_sukumo.status is LineStatus.NORMAL
    assert provider.gomen_nahari.alerts[0].title == title
    assert provider.gomen_nahari.alerts[0].effect is AlertEffect.OTHER
    assert not provider.delay_lines and not provider.active_alerts


@pytest.mark.parametrize("body", [
    "合成：運休は発生していません。", "合成：明日は一部列車を運休します。",
    "合成：運転を再開しました。", "合成：本日、以下の列車は運休となります。",
])
def test_synthetic_normal_headline_keeps_mixed_body_without_classification(body: str) -> None:
    provider = asyncio.run(_refresh(_home(), _article(body=body), _article()))
    line = provider.gomen_nahari
    assert line.status is LineStatus.NORMAL
    assert line.alerts[0].description == body
    assert line.alerts[0].effect is AlertEffect.OTHER
    assert line.alerts[0].timing is AlertTiming.UNKNOWN
    assert line.alerts[0].affected_line_ids == ()


def test_synthetic_article_links_and_media_are_retained_without_fetching() -> None:
    body = ('合成：案内<a href="https://example.com/advice.pdf">詳細</a>'
            '<img alt="合成画像" src="https://example.com/advice.png">')
    provider = asyncio.run(_refresh(_home(), _article(body=body), _article()))
    text = provider.gomen_nahari.alerts[0].description
    assert "https://example.com/advice.pdf" in text and "https://example.com/advice.png" in text


def test_synthetic_article_source_urls_match_public_string_type() -> None:
    provider = asyncio.run(_refresh(_home(), _article(), _article()))
    for alert, slug in zip(provider.alerts, ("synthetic-gomen", "synthetic-nakamura"), strict=True):
        assert isinstance(alert.source_url, str)
        assert alert.source_url == _URL + "post/" + slug
        assert alert.model_dump(mode="json", warnings="error")["source_url"] == alert.source_url
        assert alert.source_url in alert.model_dump_json(warnings="error")


@pytest.mark.parametrize("mutation", [
    "missing_panel", "duplicate_panel", "wrong_heading", "missing_title", "duplicate_title",
    "blank_title", "missing_link", "external_link", "invalid_path", "duplicated_post",
])
def test_synthetic_home_damage_is_not_normal(mutation: str) -> None:
    home = _home().decode()
    if mutation == "missing_panel":
        home = home.replace('id="comp-m9tlcfob"', 'id="missing"')
    elif mutation == "duplicate_panel":
        home += '<div id="comp-m9tlcfob"></div>'
    elif mutation == "wrong_heading":
        home = home.replace('ごめん・なはり線', '合成：別路線')
    elif mutation == "missing_title":
        home = home.replace('data-hook="post-title"', 'data-hook="removed"', 1)
    elif mutation == "duplicate_title":
        home = home.replace('</h2>', '</h2><span data-hook="post-title">重複</span>', 1)
    elif mutation == "blank_title":
        home = home.replace('平常運行', '', 1)
    elif mutation == "missing_link":
        home = home.replace('href=', 'removed=', 1)
    elif mutation == "external_link":
        home = home.replace('https://www.tosakuro.com/post/synthetic-gomen', 'https://example.com/post/notice')
    elif mutation == "invalid_path":
        home = home.replace('post/synthetic-gomen', 'post/%2Fother')
    else:
        home = home.replace('synthetic-nakamura', 'synthetic-gomen')
    with pytest.raises(ParseError):
        asyncio.run(_refresh(home.encode(), _article(), _article()))


@pytest.mark.parametrize("article", [
    b'', _article("合成：変更済み"), _article(body=""),
    _article(body='<script>1</script>合成'), _article(body='<a>合成</a>'),
    _article() + '<h1 data-hook="post-title">重複</h1>'.encode(),
])
def test_synthetic_second_article_failure_preserves_complete_snapshot(article: bytes) -> None:
    async def scenario() -> None:
        second = _article()
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=(
                _home() if r.url.path == '/' else
                _article() if r.url.path.endswith('gomen') else second
            )),
        )) as client:
            provider = TosaKuroshioProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            second = article
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_synthetic_clearing_refusal_and_tracker_failure_isolation() -> None:
    async def scenario() -> None:
        title, code = "合成：運行案内", 200

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(code, content=_home(title) if request.url.path == '/' else
                                  _article(title) if request.url.path.endswith('gomen') else _article())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TosaKuroshioProvider(client=client)
            tracker = Tracker(enabled_providers=("tosakuro", "kyoto_subway"), client=client,
                              overrides=(provider,))
            with pytest.raises(RefreshError) as caught:
                await tracker.refresh()
            assert set(caught.value.errors) == {ProviderId("kyoto_subway")}
            assert provider.gomen_nahari.status is LineStatus.UNKNOWN
            old_alert = provider.gomen_nahari.alerts[0]
            title = "平常運行"
            await provider.refresh()
            assert provider.lines[0].status is LineStatus.NORMAL
            assert old_alert not in provider.alerts
            previous = provider.lines
            code = 403
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


def test_registration_shared_ids_and_independent_snapshots() -> None:
    tracker = Tracker()
    provider = tracker.tosakuro
    assert provider in tracker.providers
    assert provider.lines == (provider.gomen_nahari, provider.nakamura_sukumo)
    for line in provider.lines:
        shared = tracker.yahoo.get_line(line.line_id)
        assert shared is not None and shared.operator == line.operator and shared is not line
        assert shared.status is LineStatus.UNKNOWN
    assert provider.metadata.statuses == frozenset({LineStatus.NORMAL})
