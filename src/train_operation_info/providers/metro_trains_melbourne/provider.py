"""Metro Trains Melbourne's public healthboard.

Investigation: reverse engineering of official HTML/JavaScript and live JSON,
2026-11-04. https://www.metrotrains.com.au/ loads mtm-app.min.js (m3.2.4)
from /wp-content/themes/metrotrains/library/js/ on ds12k1658w1f2.cloudfront.net.
MTMAPIService reads /api?op=get_healthboard_alerts and get_network with the
current default config Aug26. MTMHealthboardLine and mtmDefinitions define
the alerts array, normal string, no-services display and alert categories.
The homepage legend defines minor/major as delays and suspended as a section
of a line suspended: PARTIAL_SUSPENSION, never full-line SUSPENDED. Other
notice categories are ALERT; cancellation refers to a train, not the line.
Unknown categories/strings stay UNKNOWN. All notices are retained, rather
than allowing one notice or a recovery message to erase another disruption.

The 17 network IDs are checked against the static canonical roster. Separate
planned_works_list, extra services, lift/escalator outages and general banners
are excluded; works notices in alerts and structured disruptions are included.
Disruption scope comes only from lines, never station names or prose.
from_date/to_date are Unix seconds as shown by mtmAlertTimestampToString;
zero/empty/null mean unspecified. timing stays UNKNOWN: works may announce
future changes and no universal current-validity contract was verified.
modified is not a verified line update time, so updated_at remains None.
Only normal strings and a works notice were captured live. Delay, suspension,
structured disruptions, recovery and malformed data tests are synthetic,
based on the public source, not recorded incidents. No archive was used.
Evidence, terms review and hashes: tests/fixtures/METRO_TRAINS_MELBOURNE.md.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, RootModel

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_PAGE: Final = "https://www.metrotrains.com.au/"
_URL: Final = _PAGE + "api?op=get_healthboard_alerts"
_NETWORK: Final = _PAGE + "api?op=get_network&config=Aug26"
_ID: Final = ProviderId("metro_trains_melbourne")
_ROUTES: Final = {
    "82": ("alamein", "Alamein"), "84": ("belgrave", "Belgrave"),
    "85": ("craigieburn", "Craigieburn"), "86": ("cranbourne", "Cranbourne"),
    "87": ("mernda", "Mernda"), "88": ("frankston", "Frankston"),
    "89": ("glen_waverley", "Glen Waverley"), "90": ("hurstbridge", "Hurstbridge"),
    "91": ("lilydale", "Lilydale"), "92": ("pakenham", "Pakenham"),
    "93": ("sandringham", "Sandringham"), "94": ("stony_point", "Stony Point"),
    "95": ("sunbury", "Sunbury"), "96": ("upfield", "Upfield"),
    "97": ("werribee", "Werribee"), "98": ("williamstown", "Williamstown"),
    "168307": ("racecourse", "Racecourse"),
}
_NORMAL: Final = "Good service - trains are running on time"
_STATES: Final = {
    "good": (LineStatus.NORMAL, "Good Service"),
    "good-service": (LineStatus.NORMAL, "Good Service"),
    "no-services": (LineStatus.NORMAL, "No Services"),
    "minor": (LineStatus.DELAYED, "Minor Delays"),
    "major": (LineStatus.DELAYED, "Major Delays"),
    "suspended": (LineStatus.PARTIAL_SUSPENSION, "Suspended"),
    "works": (LineStatus.ALERT, "Works Alert"),
    "travel": (LineStatus.ALERT, "Travel Alert"),
    "trip": (LineStatus.ALERT, "Trip Alert"),
    "service": (LineStatus.ALERT, "Service Change"),
    "cancellation": (LineStatus.ALERT, "Cancellation"),
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Metro Trains Melbourne", source_page_url=HttpUrl(_PAGE),
    endpoints=(
        SourceEndpoint(url=_NETWORK, method="GET", format=DataFormat.JSON,
                       description="Current Aug26 network: validates the 17 routes and active flags"),
        SourceEndpoint(url=_URL, method="GET", format=DataFormat.JSON,
                       description="Line healthboard alerts and structured disruptions"),
    ),
    terms_url=None,
    usage_permission=UsagePermission.UNSPECIFIED,
    usage_note=(
        "Reviewed the official homepage/footer, public application and linked privacy policy. "
        "The footer asserts Metro Trains Melbourne copyright; no website/service-data reuse "
        "licence or general website terms were located. Privacy policy is not a reuse licence. "
        "UNSPECIFIED does not grant permission; Transport Victoria open-data terms are not "
        "applied to this separate website feed."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED,
                        LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-04T11:57:50.560095+00:00"),
)


class _SourceModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _NetworkLine(_SourceModel):
    id: str
    name: str
    active: bool


class _Group(_SourceModel):
    lines: list[_NetworkLine]


class _NetworkData(_SourceModel):
    network: list[_Group]


class _Alert(_SourceModel):
    alert_type: str = Field(min_length=1)
    alert_text: str = Field(min_length=1)
    line_id: str | None = None
    from_date: str | None
    to_date: str | None
    altered_services_text: str | None = None


class _LineData(_SourceModel):
    line_name: str | None = None
    alerts: str | list[_Alert]
    no_services: str | None = None


class _Disruption(_SourceModel):
    lines: list[str | int] = Field(min_length=1)
    alert_type: str = Field(min_length=1)
    notice: str = Field(min_length=1)
    from_date: str | None
    to_date: str | None


class _JsonObject(RootModel[dict[str, JsonValue]]):
    model_config = ConfigDict(strict=True)


class _Disruptions(RootModel[list[_Disruption] | dict[str, _Disruption]]):
    model_config = ConfigDict(strict=True)


def _text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)


def _epoch(raw: str | None) -> datetime | None:
    if raw in (None, "", "0"):
        return None
    if raw is None or not raw.isascii() or not raw.isdecimal():
        raise ParseError("Invalid Metro healthboard Unix timestamp")
    try:
        return datetime.fromtimestamp(int(raw), timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ParseError("Out-of-range Metro healthboard Unix timestamp") from exc


def _notice(
    line: Line, code: str, html: str, start: str | None, end: str | None,
    *, affected: tuple[LineId, ...] | None = None,
) -> ServiceAlert:
    status, label = _STATES.get(code, (LineStatus.UNKNOWN, code))
    description = _text(html)
    if not description:
        raise ParseError("Empty Metro healthboard notice")
    active_from, active_until = _epoch(start), _epoch(end)
    if active_from is not None and active_until is not None and active_until < active_from:
        raise ParseError("Reversed Metro healthboard validity period")
    alert = make_alert(line, status, label, description,
                       affected_line_ids=affected, language="en")
    return alert.model_copy(update={"active_from": active_from, "active_until": active_until})


def _parse(
    body: bytes, network: _NetworkData, lines: tuple[Line, ...], fetched_at: datetime,
) -> tuple[Line, ...]:
    network_lines = [item for group in network.network for item in group.lines]
    if len(network_lines) != len(_ROUTES) or {item.id for item in network_lines} != set(_ROUTES):
        raise ParseError("Metro network route roster changed")
    for route in network_lines:
        if route.name != _ROUTES[route.id][1]:
            raise ParseError(f"Metro network route name changed: {route.id}")
    active = {item.id: item.active for item in network_lines}
    data = _JsonObject.model_validate_json(body).root
    # Separate source collections, not additional lines. Never infer their scope
    # or use their prose to change a line's current healthboard classification.
    for key in ("metadata", "general", "lift_escalator_outages"):
        data.pop(key, None)
    raw_disruptions = data.pop("disruptions", [])
    disruptions = _Disruptions.model_validate(raw_disruptions).root
    if set(data) != set(_ROUTES):
        raise ParseError("Metro healthboard route roster changed")
    by_code = dict(zip(_ROUTES, lines, strict=True))
    statuses: dict[str, list[LineStatus]] = {code: [] for code in _ROUTES}
    labels: dict[str, list[str]] = {code: [] for code in _ROUTES}
    alerts: dict[str, list[ServiceAlert]] = {code: [] for code in _ROUTES}
    for code, line in by_code.items():
        entry = _LineData.model_validate(data[code])
        if entry.line_name is not None and entry.line_name != _ROUTES[code][1]:
            raise ParseError(f"Metro healthboard route name changed: {code}")
        if isinstance(entry.alerts, str):
            state = LineStatus.NORMAL if entry.alerts == _NORMAL else LineStatus.UNKNOWN
            statuses[code].append(state)
            labels[code].append(entry.alerts)
            if state is LineStatus.UNKNOWN:
                description = _text(entry.alerts)
                if not description:
                    raise ParseError("Empty Metro healthboard status string")
                alerts[code].append(make_alert(
                    line, LineStatus.UNKNOWN, "Unrecognised line status", description, language="en",
                ))
        else:
            for item in entry.alerts:
                if item.line_id is not None and item.line_id != code:
                    raise ParseError(f"Conflicting Metro alert line_id: {item.line_id}")
                statuses[code].append(_STATES.get(item.alert_type, (LineStatus.UNKNOWN, ""))[0])
                labels[code].append(item.alert_type)
                alerts[code].append(_notice(
                    line, item.alert_type,
                    item.alert_text + (item.altered_services_text or ""), item.from_date, item.to_date,
                ))
            if not entry.alerts:
                labels[code].append("good")
        if (entry.alerts == _NORMAL or entry.alerts == []) and not active[code] and entry.no_services:
            labels[code] = ["no-services"]
            alerts[code].append(_notice(line, "no-services", entry.no_services, None, None))
    for disruption in disruptions.values() if isinstance(disruptions, dict) else disruptions:
        codes = tuple(str(code) for code in disruption.lines)
        if len(set(codes)) != len(codes) or any(code not in by_code for code in codes):
            raise ParseError("Unknown or duplicated Metro disruption route")
        affected = tuple(by_code[code].line_id for code in codes)
        alert = _notice(by_code[codes[0]], disruption.alert_type, disruption.notice,
                        disruption.from_date, disruption.to_date, affected=affected)
        for code in codes:
            statuses[code].append(_STATES.get(disruption.alert_type, (LineStatus.UNKNOWN, ""))[0])
            labels[code].append(disruption.alert_type)
            alerts[code].append(alert)
    return tuple(snapshot(
        line, combined_status(tuple(statuses[code])), "\n".join(labels[code]), fetched_at,
        alerts=tuple(alerts[code]),
    ) for code, line in by_code.items())


class MetroTrainsMelbourneProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _PAGE
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        lines = tuple(LINE_CATALOG[LineId(f"au:metro_trains_melbourne:{key}")].create_line(
            _ID, _PAGE,
        ) for key, _ in _ROUTES.values())
        super().__init__(lines, client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        network = await self._get(client, _NETWORK)
        network.raise_for_status()
        data = _NetworkData.model_validate_json(network.content)
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, data, self.lines, self._now())

    @property
    def alamein(self) -> Line:
        return self._line("alamein")

    @property
    def belgrave(self) -> Line:
        return self._line("belgrave")

    @property
    def craigieburn(self) -> Line:
        return self._line("craigieburn")

    @property
    def cranbourne(self) -> Line:
        return self._line("cranbourne")

    @property
    def mernda(self) -> Line:
        return self._line("mernda")

    @property
    def frankston(self) -> Line:
        return self._line("frankston")

    @property
    def glen_waverley(self) -> Line:
        return self._line("glen_waverley")

    @property
    def hurstbridge(self) -> Line:
        return self._line("hurstbridge")

    @property
    def lilydale(self) -> Line:
        return self._line("lilydale")

    @property
    def pakenham(self) -> Line:
        return self._line("pakenham")

    @property
    def sandringham(self) -> Line:
        return self._line("sandringham")

    @property
    def stony_point(self) -> Line:
        return self._line("stony_point")

    @property
    def sunbury(self) -> Line:
        return self._line("sunbury")

    @property
    def upfield(self) -> Line:
        return self._line("upfield")

    @property
    def werribee(self) -> Line:
        return self._line("werribee")

    @property
    def williamstown(self) -> Line:
        return self._line("williamstown")

    @property
    def racecourse(self) -> Line:
        return self._line("racecourse")
