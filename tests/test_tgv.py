"""Official abnormal XML plus explicitly synthetic scope/recovery/failure cases."""

import asyncio
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

import httpx
import pytest

from train_operation_info import Tracker
from train_operation_info.exceptions import FetchError, ParseError
from train_operation_info.models import AlertEffect, AlertTiming, LineScope, LineStatus
from train_operation_info.providers.base import USER_AGENT
from train_operation_info.providers.tgv import TgvProvider
from train_operation_info.providers.tgv.provider import _parse, _train_scope
from train_operation_info.snapshots import SnapshotReplayTransport

_FIXTURES = Path(__file__).parent / "fixtures"
_S = 'xmlns="http://www.siri.org.uk/siri"'


def _timetable(
    *, extra: str = "", brand: str = "OUI", submode: str = "highSpeedRail",
    missing_reference: bool = False,
) -> bytes:
    rows: list[str] = []
    for number, code, mode in (("100", brand, submode), ("200", "TGVOUIGO", "highSpeedRail"),
                                ("300", "LYR", "highSpeedRail"), ("400", "TER", "regionalRail")):
        rows.append(
            f'<ServiceJourney id="journey-{number}" responsibilitySetRef="1187">'
            f'<BrandingRef ref="{code}"/><TransportSubmode><RailSubmode>{mode}</RailSubmode>'
            f'</TransportSubmode><trainNumbers><TrainNumberRef ref="number-{number}"/>'
            f'</trainNumbers></ServiceJourney>'
            f'<TrainNumber id="number-{number}" responsibilitySetRef="1187">'
            f'<ForAdvertisement>{number}</ForAdvertisement></TrainNumber>'
        )
    xml = ('<PublicationDelivery xmlns="http://www.netex.org.uk/netex">'
           + "".join(rows) + extra + '</PublicationDelivery>')
    if missing_reference:
        xml = xml.replace('ref="number-100"', 'ref="missing"')
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("synthetic.xml", xml)
    return output.getvalue()


def _notice(
    *, number: str = "100", operator: str = "1187", identifier: str = "synthetic",
    detail: str = "<p>Le train est supprimé demain ; l'ancien avis est annulé.</p>",
    journey: bool = True,
) -> str:
    target = (
        '<VehicleJourneys><AffectedVehicleJourney>'
        f'<VehicleJourneyRef>{number}</VehicleJourneyRef><Operator><OperatorRef>{operator}'
        '</OperatorRef></Operator></AffectedVehicleJourney></VehicleJourneys>'
    ) if journey else '<StopPoints><AffectedStopPoint><StopPointRef>station</StopPointRef></AffectedStopPoint></StopPoints>'
    return (
        f'<PtSituationElement><SituationNumber>{identifier}</SituationNumber><Progress>published</Progress>'
        '<ValidityPeriod><StartTime>2026-11-01T00:00:00Z</StartTime>'
        '<EndTime>2026-12-01T00:00:00Z</EndTime></ValidityPeriod><Severity>slight</Severity>'
        '<Summary xml:lang="FR">Avis synthétique</Summary>'
        f'<Detail xml:lang="FR">{escape(detail)}</Detail>'
        f'<Consequences><Consequence><Affects>{target}</Affects></Consequence></Consequences>'
        '</PtSituationElement>'
    )


def _feed(notices: str = "", *, status: str = "", timestamp: str = "2026-11-04T12:00:00Z") -> bytes:
    return (
        f'<Siri {_S} version="2.0"><ServiceDelivery><SituationExchangeDelivery>{status}'
        f'<ResponseTimestamp>{timestamp}</ResponseTimestamp><Situations>{notices}</Situations>'
        '</SituationExchangeDelivery></ServiceDelivery></Siri>'
    ).encode()


def _handler(request: httpx.Request, timetable: bytes, feed: bytes) -> httpx.Response:
    assert request.method == "GET" and request.headers["User-Agent"] == USER_AGENT
    return httpx.Response(200, content=timetable if request.url.path.endswith(".zip") else feed)


def test_synthetic_scope_filters_ter_but_never_classifies_incident_prose() -> None:
    notices = "".join(_notice(number=n, identifier=n) for n in ("100", "200", "300", "400"))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _handler(request, _timetable(), _feed(notices)),
        )) as client:
            tracker = Tracker(enabled_providers=("tgv",), client=client)
            provider = tracker.tgv
            assert provider.network.status is LineStatus.UNKNOWN
            await tracker.refresh()
            assert provider.network.scope is LineScope.GROUP
            assert str(provider.network.line_id) == "fr:sncf:tgv"
            assert provider.network.operator.name == "SNCF Voyageurs"
            assert provider.network.status is LineStatus.UNKNOWN
            assert len(provider.alerts) == 3
            assert all(alert.effect is AlertEffect.OTHER for alert in provider.alerts)
            assert all(alert.timing is AlertTiming.UNKNOWN for alert in provider.alerts)
            assert all(alert.affected_line_ids == () for alert in provider.alerts)
            assert all(alert.active_from is None and alert.active_until is None for alert in provider.alerts)
            assert "supprimé demain" in provider.alerts[0].description
            assert provider.network.updated_at == datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
            assert not provider.delay_lines and not provider.active_alerts
            assert not client.is_closed

    asyncio.run(scenario())


@pytest.mark.parametrize("notice", [
    _notice(number="999"), _notice(operator="other"), _notice(journey=False),
])
def test_synthetic_unknown_target_is_retained(notice: str) -> None:
    provider = TgvProvider()
    line, = _parse(_feed(notice), _train_scope(_timetable()), provider.network,
                   datetime.now(timezone.utc))
    assert line.status is LineStatus.UNKNOWN and len(line.alerts) == 1
    assert line.alerts[0].affected_line_ids == ()


def test_synthetic_new_brand_or_conflicting_number_is_never_treated_as_excluded() -> None:
    extra = (
        '<ServiceJourney id="new-journey" responsibilitySetRef="1187">'
        '<BrandingRef ref="NEW_BRAND"/><trainNumbers><TrainNumberRef ref="number-400"/>'
        '</trainNumbers></ServiceJourney>'
    )
    scopes = _train_scope(_timetable(extra=extra))
    assert scopes[("1187", "400")] == frozenset({False, None})
    line, = _parse(_feed(_notice(number="400")), scopes, TgvProvider().network,
                   datetime.now(timezone.utc))
    assert line.status is LineStatus.UNKNOWN and line.alerts


def test_synthetic_tgv_brand_without_high_speed_submode_stays_unclassified() -> None:
    scopes = _train_scope(_timetable(submode="newSubmode"))
    assert scopes[("1187", "100")] == frozenset({None})
    line, = _parse(_feed(_notice()), scopes, TgvProvider().network,
                   datetime.now(timezone.utc))
    assert line.status is LineStatus.UNKNOWN and line.alerts


def test_synthetic_recording_replays_both_inputs_without_cached_timetable(tmp_path: Path) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _handler(request, _timetable(), _feed(_notice())),
        )) as client:
            provider = TgvProvider(client=client, snapshot_dir=tmp_path)
            await provider.refresh()
            original = provider.lines
        capture, = (tmp_path / "tgv").glob("[0-9]*/*.json")
        transport = SnapshotReplayTransport(capture)
        assert len(transport.capture.responses) == 2
        assert {record.url for record in transport.capture.responses} == {
            endpoint.url for endpoint in provider.metadata.endpoints
        }
        async with httpx.AsyncClient(transport=transport) as client:
            replay = TgvProvider(client=client)
            await replay.refresh()
            assert replay.lines == original

    asyncio.run(scenario())


def test_synthetic_recovery_replaces_old_notices_and_rate_limit_reuses_snapshot() -> None:
    feed = _feed(_notice())
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _handler(request, _timetable(), feed)

    async def scenario() -> None:
        nonlocal feed
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TgvProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            provider.rate_limit = 120
            await provider.refresh()
            assert calls == 2 and provider.lines is previous
            provider.rate_limit = 0
            # A proven TER-only notice is outside the declared TGV scope.
            feed = _feed(_notice(number="400"))
            await provider.refresh()
            assert calls == 4
            assert provider.network.status is LineStatus.NORMAL and not provider.alerts
            feed = _feed()
            await provider.refresh()
            assert provider.network.status is LineStatus.NORMAL and not provider.alerts

    asyncio.run(scenario())


@pytest.mark.parametrize("broken", [
    b"broken XML", b"<Siri/>",
    _feed().replace(b"<Situations>", b"<Missing>").replace(b"</Situations>", b"</Missing>"),
    _feed(status="<Status>false</Status>"),
    _feed(status="<ErrorCondition><OtherError/></ErrorCondition>"),
    _feed(timestamp="2026-11-04T12:00:00"),
    _feed(_notice() + _notice()),
    _feed(_notice(detail="<p></p>")),
    _feed(_notice().replace('xml:lang="FR"', 'xml:lang="EN"')),
    _feed(_notice().replace("<OperatorRef>1187</OperatorRef>", "")),
])
def test_synthetic_bad_feed_preserves_complete_snapshot(broken: bytes) -> None:
    async def scenario() -> None:
        feed = _feed(_notice())
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: _handler(request, _timetable(), feed),
        )) as client:
            provider = TgvProvider(client=client)
            await provider.refresh()
            previous = provider.lines
            feed = broken
            with pytest.raises(ParseError):
                await provider.refresh()
            assert provider.lines is previous

    asyncio.run(scenario())


@pytest.mark.parametrize("broken", [
    b"not ZIP", _timetable(brand="NEW_BRAND"), _timetable(missing_reference=True),
])
def test_synthetic_bad_archive_is_not_normal(broken: bytes) -> None:
    with pytest.raises(ParseError):
        _train_scope(broken)


@pytest.mark.parametrize("status", [403, 429, 503])
@pytest.mark.parametrize("target", ["archive", "alerts"])
def test_http_refusal_preserves_unknown_without_retry(status: int, target: str) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith(".zip") == (target == "archive"):
            return httpx.Response(status)
        return _handler(request, _timetable(), _feed())

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TgvProvider(client=client)
            with pytest.raises(FetchError):
                await provider.refresh()
            assert provider.network.status is LineStatus.UNKNOWN
            assert len(calls) == (1 if target == "archive" else 2)

    asyncio.run(scenario())


def test_official_abnormal_capture_and_original_hashes() -> None:
    manifest = json.loads((_FIXTURES / "tgv_manifest.json").read_text(encoding="utf-8"))
    for record in manifest:
        if "fixture" in record:
            assert sha256((_FIXTURES / record["fixture"]).read_bytes()).hexdigest() == record["sha256"]
    scopes = _train_scope((_FIXTURES / "tgv_netex_20261104.zip").read_bytes())
    assert scopes[("1187", "8571")] == frozenset({True})
    provider = TgvProvider()
    line, = _parse((_FIXTURES / "tgv_alerts_20261104.xml").read_bytes(), scopes, provider.network,
                   datetime(2026, 11, 4, 12, 43, 4, tzinfo=timezone.utc))
    assert line.status is LineStatus.UNKNOWN and line.alerts
    assert any("1187:8571" in alert.description for alert in line.alerts)
    assert all(alert.timing is AlertTiming.UNKNOWN for alert in line.alerts)
