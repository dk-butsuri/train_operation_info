"""Live official normal XML; all abnormal/unknown mutations below are synthetic."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError, RefreshError
from train_operation_info.models import LINE_CATALOG, AlertEffect, LineId, LineStatus, UsagePermission
from train_operation_info.providers.seibu import SeibuProvider

_FIXTURES = Path(__file__).parent / "fixtures"
_URL = "https://www.seiburailway.jp/api/v1/travelinfo/raw/IDS2Web.xml"


def _normal_text() -> str:
    return (_FIXTURES / "seibu_normal.xml").read_text("utf-8-sig")


def _response(request: httpx.Request, xml: str | None = None) -> httpx.Response:
    assert str(request.url) == _URL
    assert request.method == "GET"
    return httpx.Response(200, content=(xml or _normal_text()).encode("utf-8"))


def test_official_normal_and_canonical_ids() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_response)) as client:
            provider = SeibuProvider(client=client)
            tracker = Tracker(enabled_providers=("seibu",), overrides=(provider,))
            assert tracker.providers == (provider,)
            assert len(tracker.unknown_lines) == 11
            await tracker.refresh()
            assert len(tracker.lines) == 11
            assert len({line.line_id for line in provider.lines}) == 11
            assert all(line.status is LineStatus.NORMAL for line in tracker.lines)
            assert not tracker.alerts and not tracker.affected_lines
            assert provider.lines == (
                provider.shinjuku, provider.toshima, provider.ikebukuro_chichibu,
                provider.seibuen, provider.kokubunji, provider.tamako, provider.yamaguchi,
                provider.tamagawa, provider.haijima, provider.sayama, provider.yurakucho,
            )
            for line in provider.lines:
                assert line.operator is LINE_CATALOG[line.line_id].operator
                assert line.operator.name == "西武鉄道"
                assert line.updated_at is not None
                assert line.updated_at.isoformat() == "2026-11-01T14:53:23+09:00"
                assert line.fetched_at is not None
                assert line.fetched_at.utcoffset() == timedelta(0)
                assert line.source_line_names
            assert provider.ikebukuro_chichibu.source_line_names == ("池袋線", "西武秩父線")
            assert provider.metadata.usage_permission is UsagePermission.PERMISSION_REQUIRED
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize(("label", "status", "effect"), [
    ("運転見合わせ", LineStatus.SUSPENDED, AlertEffect.NO_SERVICE),
    ("運転再開見込", LineStatus.SUSPENDED, AlertEffect.NO_SERVICE),
    ("運休", LineStatus.SUSPENDED, AlertEffect.NO_SERVICE),
    ("遅延", LineStatus.ALERT, AlertEffect.OTHER),
    ("一部運休", LineStatus.ALERT, AlertEffect.OTHER),
])
def test_synthetic_incident_labels_and_recovery(label: str, status: LineStatus, effect: AlertEffect) -> None:
    incident = _normal_text().replace(
        '<dif all="0" />',
        f'<dif all="1"><lif><lin><nm>新宿線</nm></lin><sts><nm>{label}</nm></sts></lif></dif>',
    )
    recovered = False

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, None if recovered else incident)

    async def scenario() -> None:
        nonlocal recovered
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            tracker = Tracker(enabled_providers=("seibu",), client=client)
            await tracker.refresh()
            line = tracker.seibu.shinjuku
            assert line.status is status
            assert line.alerts[0].effect is effect
            assert line.alerts[0].affected_line_ids == (line.line_id,)
            assert label in (line.source_status or "")
            assert line.updated_at is not None
            assert all(other.status is LineStatus.NORMAL for other in tracker.lines if other.line_id != line.line_id)
            recovered = True
            await tracker.refresh()
            assert not tracker.alerts and not tracker.affected_lines
            assert all(other.status is LineStatus.NORMAL for other in tracker.lines)
            assert line.status is status  # the previous snapshot stays immutable

    asyncio.run(scenario())


def test_synthetic_all_lines_marker_applies_to_every_line() -> None:
    incident = _normal_text().replace(
        '<dif all="0" />',
        '<dif all="1"><lif><lin><nm>西武線全線</nm></lin><sts><nm>運休</nm></sts></lif></dif>',
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, incident),
        )) as client:
            provider = SeibuProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.SUSPENDED for line in provider.lines)
            assert len(provider.alerts) == 1
            assert set(provider.alerts[0].affected_line_ids) == {line.line_id for line in provider.lines}

    asyncio.run(scenario())


def test_synthetic_unscoped_notice_marks_otherwise_normal_lines_unknown() -> None:
    incident = _normal_text().replace("<txt />", "<txt>対象路線未特定のお知らせ</txt>")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, incident),
        )) as client:
            provider = SeibuProvider(client=client)
            await provider.refresh()
            assert all(line.status is LineStatus.UNKNOWN for line in provider.lines)
            assert len(provider.alerts) == 1
            assert provider.alerts[0].affected_line_ids == ()

    asyncio.run(scenario())


def test_synthetic_overall_text_is_folded_into_a_matched_incident() -> None:
    incident = _normal_text().replace("<txt />", "<txt>信号機故障のため</txt>", 1).replace(
        '<dif all="0" />',
        '<dif all="1"><lif><lin><nm>新宿線</nm></lin><sts><nm>遅延</nm></sts></lif></dif>',
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, incident),
        )) as client:
            provider = SeibuProvider(client=client)
            await provider.refresh()
            assert provider.shinjuku.status is LineStatus.ALERT
            assert "信号機故障のため" in provider.shinjuku.alerts[0].description
            assert all(line.status is LineStatus.NORMAL for line in provider.lines if line.line_id != provider.shinjuku.line_id)

    asyncio.run(scenario())


@pytest.mark.parametrize("fault", [
    "bad_root", "missing_time", "malformed_time", "missing_chk", "missing_info",
    "missing_dif", "missing_dif_all", "count_mismatch_zero", "count_mismatch_nonzero",
    "missing_name", "missing_status", "unknown_name", "ambiguous_name",
    "invalid_xml", "http_error", "transport_error",
])
def test_synthetic_malformed_source_preserves_previous_snapshot(fault: str) -> None:
    text = _normal_text()
    if fault == "bad_root":
        broken = text.replace("<IDS2Web", "<IDS2WebX").replace("</IDS2Web>", "</IDS2WebX>")
    elif fault == "missing_time":
        broken = text.replace("<time>20261101145323</time>", "")
    elif fault == "malformed_time":
        broken = text.replace("20261101145323", "not-a-time")
    elif fault == "missing_chk":
        broken = text.replace("<chk>0</chk>", "")
    elif fault == "missing_info":
        broken = text.replace("<info>", "<renamed>").replace("</info>", "</renamed>")
    elif fault == "missing_dif":
        broken = text.replace('<dif all="0" />', "")
    elif fault == "missing_dif_all":
        broken = text.replace('<dif all="0" />', "<dif />")
    elif fault == "count_mismatch_zero":
        broken = text.replace(
            '<dif all="0" />',
            '<dif all="0"><lif><lin><nm>新宿線</nm></lin><sts><nm>遅延</nm></sts></lif></dif>',
        )
    elif fault == "count_mismatch_nonzero":
        broken = text.replace('<dif all="0" />', '<dif all="1" />')
    elif fault == "missing_name":
        broken = text.replace(
            '<dif all="0" />',
            '<dif all="1"><lif><lin><nm></nm></lin><sts><nm>遅延</nm></sts></lif></dif>',
        )
    elif fault == "missing_status":
        broken = text.replace(
            '<dif all="0" />',
            '<dif all="1"><lif><lin><nm>新宿線</nm></lin><sts><nm></nm></sts></lif></dif>',
        )
    elif fault == "unknown_name":
        broken = text.replace(
            '<dif all="0" />',
            '<dif all="1"><lif><lin><nm>謎の路線</nm></lin><sts><nm>遅延</nm></sts></lif></dif>',
        )
    elif fault == "ambiguous_name":
        # Contrived: two distinct catalog lines' fragments both present in one name.
        broken = text.replace(
            '<dif all="0" />',
            '<dif all="1"><lif><lin><nm>新宿線豊島線</nm></lin><sts><nm>遅延</nm></sts></lif></dif>',
        )
    else:
        broken = text

    is_broken = False

    def handler(request: httpx.Request) -> httpx.Response:
        if not is_broken:
            return _response(request)
        if fault == "http_error":
            return httpx.Response(503)
        if fault == "transport_error":
            raise httpx.ConnectError("synthetic", request=request)
        if fault == "invalid_xml":
            return httpx.Response(200, content=b"<html>maintenance</html>")
        return httpx.Response(200, content=broken.encode("utf-8"))

    async def scenario() -> None:
        nonlocal is_broken
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SeibuProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            is_broken = True
            expected = FetchError if fault in ("http_error", "transport_error") else ParseError
            with pytest.raises(expected):
                await provider.refresh()
            assert provider.lines is previous
            assert not client.is_closed

    asyncio.run(scenario())


def test_tracker_selection_default_and_failure_isolation() -> None:
    requests: list[str] = []
    fail = False

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(503) if fail else _response(request)

    async def scenario() -> None:
        nonlocal fail
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = SeibuProvider(client=client)
            assert "seibu" in {p.provider_id for p in Tracker().providers}
            disabled = Tracker(enabled_providers=(), overrides=(provider,))
            await disabled.refresh()
            assert requests == []
            tracker = Tracker(enabled_providers=("seibu",), overrides=(provider,))
            await tracker.refresh()
            previous = provider.lines
            fail = True
            with pytest.raises(RefreshError) as captured:
                await tracker.refresh()
            assert set(captured.value.errors) == {provider.provider_id}
            assert provider.lines is previous
            assert len(requests) == 2

    asyncio.run(scenario())


def test_ikebukuro_chichibu_combines_both_official_segments() -> None:
    incident = _normal_text().replace(
        '<dif all="0" />',
        '<dif all="2">'
        '<lif><lin><nm>池袋線</nm></lin><sts><nm>遅延</nm></sts></lif>'
        '<lif><lin><nm>西武秩父線</nm></lin><sts><nm>運転見合わせ</nm></sts></lif>'
        '</dif>',
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _response(request, incident),
        )) as client:
            provider = SeibuProvider(client=client)
            await provider.refresh()
            line = provider.ikebukuro_chichibu
            assert line.status is LineStatus.SUSPENDED  # SUSPENDED outranks ALERT
            assert len(line.alerts) == 2
            assert line.line_id == LineId("jp:seibu:line_45cb36b285e9")

    asyncio.run(scenario())
