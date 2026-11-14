"""Record/replay existing fixtures; these recordings are not new live evidence."""

import asyncio
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import logging
from pathlib import Path
import re
from string import Formatter
from typing import get_args

import httpx
import pytest

from train_operation_info import ProviderName, Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LineStatus, SourceEndpoint
from train_operation_info.providers.keisei import KeiseiProvider
from train_operation_info.providers.nankai import NankaiProvider
from train_operation_info.snapshots import SnapshotCapture, SnapshotReplayTransport, _REPLAY_TIME

_FIXTURES = Path(__file__).parent / "fixtures"
_FILES = {
    "kaohsiung_metro": "kaohsiung_metro_normal_20261104.html",
    "tfl": "tfl_live_20261104.json",
    "yokohama_subway": "yokohama_subway_normal.json",
    "taoyuan_metro": "taoyuan_metro_suspended_20240403012130.html",
    "fukuoka_subway": "fukuoka_subway_20240829161647.html",
    "renfe": "renfe_alerts_20261104.json",
    "trenitalia": "trenitalia_live_20261104.html",
    "mtr": "mtr_normal.xml",
    "nishitetsu": "nishitetsu_20260728135357.html",
    "kyoto_subway": "kyoto_subway_notice_20230815040858.html",
    "obb": "obb_20260717055055.html",
    "tra": "tra_20250707021531.html",
    "hakone_tozan": "hakone_tozan_20260208142500.html",
    "meitetsu": "meitetsu_20260908095207.html",
    "nagoya_subway": "nagoya_subway_normal.json",
    "osaka_metro": "20240829220436.html", "jrw": "jrw_api_20261001234249.json",
    "jrshikoku": "jrshikoku_20260712052626.html", "hankyu": "hankyu_20250722023635.html",
    "hanshin": "hanshin_20240830120316.html", "nankai": "nankai_20250806220111.html",
    "kintetsu": "kintetsu_20260504000342.html", "osaka_monorail": "osaka_monorail_partial_20261114.html",
    "taipei_metro": "taipei_metro_normal.html", "thsr": "thsr_20240403005339.html",
    "yurikamome": "yurikamome_normal.html",
    "yuirail": "yuirail_normal.json",
    "tobu": "tobu_normal.xml",
    "tokyo_metro": "tokyo_metro_normal.json",
    "minatomirai": "minatomirai_20180122144419.html",
    "toei": "toei_normal.html",
    "sapporo_subway": "sapporo_subway_normal.html",
    "tosaden": "tosaden_20220918071853.html",
    "rinkai": "rinkai_20220825002322.html",
    "keikyu": "keikyu_20220713030847.html",
    "keio": "keio_normal.xml",
    "mta_subway": "mta_subway_alerts_20261103033316.pb",
    "metro_north": "metro_north_alerts_20261104115626.pb",
    "seibu": "seibu_normal.xml",
    "sotetsu": "sotetsu_20230717075741.json",
    "saitama_railway": "saitama_railway_normal.json",
}


def _matches_endpoint(endpoint: SourceEndpoint, method: str, url: str) -> bool:
    if endpoint.method != method:
        return False
    if not endpoint.is_template:
        return endpoint.url == url
    pattern = "".join(
        re.escape(literal) + (r"[^?#]+" if field is not None else "")
        for literal, field, _, _ in Formatter().parse(endpoint.url)
    )
    return re.fullmatch(pattern, url) is not None


def _fixture_response(provider: ProviderName, request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if provider == "tosakuro":
        name = ("tosakuro_home.html" if path == "/" else "tosakuro_gomen.html"
                if "ごめん" in path else "tosakuro_nakamura.html")
        return httpx.Response(200, content=(_FIXTURES / name).read_bytes())
    if provider == "kintetsu" and path.startswith("/unkou/files/"):
        # Synthetic prose for the summary-only archive, not captured detail text.
        return httpx.Response(200, content=(
            '<div class="title">近鉄列車運行情報</div>'
            '<table><tr><td><p id="tran">テストの詳細本文<br>テストの追加案内</td></tr></table>'
        ).encode("cp932"))
    if provider == "sendai_subway":
        name = ("sendai_subway_namboku_normal.html" if path.endswith("nanbokusen/")
                else "sendai_subway_tozai_normal.html")
    elif provider == "db":
        if path == "/api/views/disruptions":
            name = "db_listing.json"
        elif path == "/api/views/message":
            name = {
                "493b1167-9762-49df-a8f3-35b7dabe487e": "db_message_berlin.json",
                "89ae83a0-740d-3e50-92d6-184c6d472c71": "db_message_berlin.json",
                "c1d91fe2-8cac-4287-bf5c-2d391039b910": "db_message_wuppertal.json",
                "15bee9d8-282e-370b-8a97-682ab0f3f37a": "db_message_wuppertal.json",
            }[request.url.params["id"]]
        else:
            assert path == "/de/region/DB_Fernverkehr"
            name = "db_page.html"
        # Interpret the real, time-limited fixture at its capture date even
        # when this offline test is run after the notices have expired.
        return httpx.Response(
            200, content=(_FIXTURES / name).read_bytes(),
            extensions={_REPLAY_TIME: datetime(2026, 11, 3, 3, 38, tzinfo=timezone.utc)},
        )
    elif provider == "metro_trains_melbourne":
        name = ("metro_trains_melbourne_network.json" if request.url.params["op"] == "get_network"
                else "metro_trains_melbourne_healthboard.json")
    elif provider == "tgv":
        name = "tgv_netex_20261104.zip" if path.endswith(".zip") else "tgv_alerts_20261104.xml"
    elif provider == "transilien":
        code = path.rsplit("/", 1)[-1].lower()
        name = "transilien_metro_summary.json" if code == "infos" else f"transilien_{code}.json"
    elif provider == "odakyu":
        name = ("odakyu_normal.json" if path == "/service/status_detail" else
                "odakyu_app_excerpt.js" if path.endswith(".js") else "odakyu_page.html")
    elif provider == "keihan":
        name = ("keihan_normal.json" if path.endswith("info.json") else
                "keihan_filelist.xml" if path.endswith("FileList.xml") else
                "keihan_xml_20230911234517.xml")
    elif provider == "singapore_mrt":
        if request.method == "POST":
            assert b"serviceName=LTAGOVTrainServiceAlerts" in request.content
            name = "mrt_normal.json"
        else:
            name = "mrt_page.html"
    elif provider == "tokyu":
        name = {
            "unten2.json": "tokyu_normal.json",
            "unten_additional.json": "tokyu_additional_normal.json",
            "information.json": "tokyu_information_normal.json",
        }[path.rsplit("/", 1)[-1]]
    elif provider == "keisei":
        name = "keisei_notice.js" if path.endswith(".js") else "keisei_20260415104003.html"
    elif provider == "jrcentral":
        name = "jrcentral_service.json" if path.endswith("hp_service_jotai_kanri.json") else "jrcentral_operation.json"
    elif provider == "jrhokkaido":
        name = "jrhokkaido_" + path.rsplit("/", 1)[-1]
    elif provider == "jrkyushu":
        name = "jrkyushu_" + path.rsplit("/", 1)[-1]
    elif provider == "jreast":
        area = path.rsplit("/", 1)[-1].removesuffix(".aspx")
        name = f"jreast_{area}_20261102.html"
    elif provider == "yahoo":
        name = "yahoo_" + path.removeprefix("/diainfo/").replace("/", "_") + ".html"
    else:
        name = _FILES[provider]
    return httpx.Response(200, content=(_FIXTURES / name).read_bytes())


@pytest.mark.parametrize("provider_name", get_args(ProviderName))
def test_every_provider_roundtrips_http_bodies_and_parsed_state(
    provider_name: ProviderName, tmp_path: Path,
) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _fixture_response(provider_name, request),
        )) as client:
            tracker = Tracker(enabled_providers=(provider_name,), client=client, snapshot_dir=tmp_path)
            await tracker.refresh()
            original = tracker.lines
            endpoints = tracker.providers[0].metadata.endpoints
            assert not client.is_closed
        capture_path, = (tmp_path / provider_name).glob("[0-9]*/*.json")
        transport = SnapshotReplayTransport(capture_path)
        assert transport.capture.provider_id == provider_name
        assert transport.capture.responses
        assert transport.capture.error is None
        if provider_name == "transilien":
            assert len(original) == 28
            assert len(transport.capture.responses) == 29
            assert {entry.url.rsplit("/", 1)[-1] for entry in transport.capture.responses
                    if "/METRO_" in entry.url} == {
                f"METRO_{code}?lang=fr" for code in (
                    "1", "2", "3", "3BIS", "4", "5", "6", "7", "7BIS",
                    "8", "9", "10", "11", "12", "13", "14",
                )
            }
        matched_endpoints: set[int] = set()
        for response in transport.capture.responses:
            matches = {
                index for index, endpoint in enumerate(endpoints)
                if _matches_endpoint(endpoint, response.method, response.url)
            }
            assert matches, f"Undeclared request: {response.method} {response.url}"
            matched_endpoints.update(matches)
            body = gzip.decompress((tmp_path / provider_name / "bodies" / f"{response.body_sha256}.gz").read_bytes())
            assert sha256(body).hexdigest() == response.body_sha256
        assert matched_endpoints == set(range(len(endpoints)))
        async with httpx.AsyncClient(transport=transport) as client:
            replay = Tracker(enabled_providers=(provider_name,), client=client)
            await replay.refresh()
            assert replay.lines == original

    asyncio.run(scenario())


def test_disabled_by_default_and_unchanged_captures_are_skipped(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _fixture_response("nankai", request),
        )) as client:
            provider = NankaiProvider(client=client)
            await provider.refresh()
            assert list(tmp_path.iterdir()) == []
            provider = NankaiProvider(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            await provider.refresh()
            assert len(list(tmp_path.glob("nankai/[0-9]*/*.json"))) == 1
            assert len(list(tmp_path.glob("nankai/bodies/*.gz"))) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [200, 503])
def test_bad_response_is_preserved_before_parsing_and_replays_failure(tmp_path: Path, status: int) -> None:
    broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if broken:
            return httpx.Response(status, content=b"broken source\x00")
        return _fixture_response("nankai", request)

    async def scenario() -> None:
        nonlocal broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = NankaiProvider(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            original = provider.lines
            broken = True
            with pytest.raises(ParseError if status == 200 else FetchError):
                await provider.refresh()
            assert provider.lines is original
        paths = list(tmp_path.glob("nankai/[0-9]*/*.json"))
        failed = next(p for p in paths if SnapshotCapture.model_validate_json(p.read_bytes()).error)
        transport = SnapshotReplayTransport(failed)
        assert transport.capture.responses[0].status_code == status
        digest = transport.capture.responses[0].body_sha256
        assert gzip.decompress((tmp_path / "nankai/bodies" / f"{digest}.gz").read_bytes()) == b"broken source\x00"
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ParseError if status == 200 else FetchError):
                await NankaiProvider(client=client).refresh()

    asyncio.run(scenario())


def test_storage_failure_does_not_stop_refresh_and_is_retried(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("file", encoding="utf-8")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _fixture_response("nankai", request),
        )) as client:
            provider = NankaiProvider(client=client, snapshot_dir=blocker)
            with caplog.at_level(logging.WARNING):
                await provider.refresh()
            assert provider.delay_lines
            assert "Could not save nankai snapshot" in caplog.text
            blocker.unlink()
            await provider.refresh()
            assert len(list(blocker.glob("nankai/[0-9]*/*.json"))) == 1

    asyncio.run(scenario())


def test_replay_checks_post_identity_and_never_falls_back_to_network(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _fixture_response("singapore_mrt", request),
        )) as client:
            tracker = Tracker(enabled_providers=("singapore_mrt",), client=client, snapshot_dir=tmp_path)
            await tracker.refresh()
        capture_path, = tmp_path.glob("singapore_mrt/[0-9]*/*.json")
        transport = SnapshotReplayTransport(capture_path)
        post = next(entry for entry in transport.capture.responses if entry.method == "POST")
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.ConnectError, match="No recorded response"):
                await client.post(post.url, data={"serviceName": "wrong"})
            with pytest.raises(httpx.ConnectError, match="No recorded response"):
                await client.get("https://unrecorded.invalid/")

    asyncio.run(scenario())


@pytest.mark.parametrize("corruption", ["hash", "gzip"])
def test_replay_detects_corrupt_body(tmp_path: Path, corruption: str) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _fixture_response("nankai", request),
        )) as client:
            await NankaiProvider(client=client, snapshot_dir=tmp_path).refresh()
        capture_path, = tmp_path.glob("nankai/[0-9]*/*.json")
        transport = SnapshotReplayTransport(capture_path)
        digest = transport.capture.responses[0].body_sha256
        body = gzip.compress(b"tampered") if corruption == "hash" else b"invalid gzip"
        (tmp_path / "nankai/bodies" / f"{digest}.gz").write_bytes(body)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(FetchError, match="Could not fetch"):
                await NankaiProvider(client=client).refresh()

    asyncio.run(scenario())


def test_concurrent_refreshes_do_not_mix_multi_endpoint_captures(tmp_path: Path) -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        await asyncio.sleep(0)
        return _fixture_response("keisei", request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = KeiseiProvider(client=client, snapshot_dir=tmp_path)
            await asyncio.gather(provider.refresh(), provider.refresh())
        assert requests == ["/traininfo/index.php", "/traininfo/data/notice.js"] * 2
        capture_path, = tmp_path.glob("keisei/[0-9]*/*.json")
        capture = SnapshotCapture.model_validate_json(capture_path.read_bytes())
        assert len(capture.responses) == 2

    asyncio.run(scenario())


def test_replay_restores_recorded_clock_for_time_limited_notice(tmp_path: Path) -> None:
    class RecordedKeisei(KeiseiProvider):
        @staticmethod
        def _now() -> datetime:
            return datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".js"):
            # Synthetic activation of the real disabled notice, not live evidence.
            text = (_FIXTURES / "keisei_notice.js").read_text(encoding="utf-8")
            return httpx.Response(200, text=text.replace("ja_flg = 0", "ja_flg = 1"))
        return httpx.Response(200, content=(_FIXTURES / "keisei_normal.html").read_bytes())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = RecordedKeisei(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            assert provider.alerts
            original = provider.lines
        capture_path, = tmp_path.glob("keisei/[0-9]*/*.json")
        async with httpx.AsyncClient(transport=SnapshotReplayTransport(capture_path)) as client:
            replay = KeiseiProvider(client=client)
            await replay.refresh()
            assert replay.lines == original

    asyncio.run(scenario())
