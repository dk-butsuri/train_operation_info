"""Osaka Monorail official service alerts.

Investigation: live abnormal HTML and public CSS/JavaScript inspection (2026-11-14),
plus normal Wayback capture 20250811060448. Sources: https://www.osaka-monorail.co.jp/,
/common/css/common.css?v=1788157719 and /common/js/common.js on the same host.
The station map's explicit normal/delay/stop segment classes share the colors of
the normal/delayed/suspended legend. Complete route topology determines full versus
partial suspension; current segment states establish ACTIVE timing. The live sample
contains partial main-line suspension and Saito delays. Full suspension, normal map
segments, unknown classes, malformed maps and recovery transitions use synthetic tests.
Without a map, preserve abnormal summaries as unscoped UNKNOWN. Exclude publication
policy, English duplicate and dispTime (JavaScript's reader clock, not an update time).
Separate news, planned services and transfer-acceptance notices are outside this scope;
validity periods and source update times are not published in the consumed fields.
Evidence and capture hashes: tests/fixtures/OSAKA_MONORAIL.md and its manifest.
"""

from datetime import datetime
from typing import Final

from pathlib import Path

import httpx
from pydantic import HttpUrl
from bs4 import BeautifulSoup, Tag

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    Line, LineStatus, Operator, OperatorId, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, initial_lines, make_alert, snapshot
from ..classification import timing_from_status

_URL: Final = "https://www.osaka-monorail.co.jp/"
_ID: Final = ProviderId("osaka_monorail")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:osaka_monorail"), name="大阪モノレール")
_DEFINITIONS: Final = (("main", "大阪モノレール線"), ("saito", "彩都線"))
_ROUTES: Final = (
    ("stationMap__botRail", tuple(range(11, 25))),
    ("stationMap__topRail", (17, 51, 52, 53, 54)),
)
_SEGMENT_STATES: Final = {
    "normal": LineStatus.NORMAL, "delay": LineStatus.DELAYED,
    "stop": LineStatus.SUSPENDED,
}


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Network status summary and current station-to-station status map',
        ),
    ),
    provider_id=ProviderId('osaka_monorail'), name='Osaka Monorail official',
    source_page_url=HttpUrl('https://www.osaka-monorail.co.jp/'),
    terms_url=HttpUrl('https://www.osaka-monorail.co.jp/siteguide/'),
    additional_terms_urls=(),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note='The copyright section prohibits copying or republication in other media without permission. No separate private or commercial data reuse grant was found.',
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED,
                        LineStatus.PARTIAL_SUSPENSION}),
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)


def _map_statuses(station_map: Tag, label: str, lines: tuple[Line, ...],
                  fetched_at: datetime) -> tuple[Line, ...]:
    names: dict[int, str] = {}
    for station in station_map.select("p[id^=station_]"):
        identifier = str(station.get("id"))
        name = station.select_one("a .-station")
        if name is None or not name.get_text(strip=True):
            raise ParseError("Osaka Monorail station name is missing")
        number = identifier.removeprefix("station_")
        if not number.isdecimal() or int(number) in names:
            raise ParseError("Osaka Monorail station ID is invalid or duplicated")
        names[int(number)] = name.get_text(strip=True)
    if set(names) != set(range(11, 25)) | {51, 52, 53, 54}:
        raise ParseError("Osaka Monorail station topology changed")
    if len(station_map.select("[id^=line]")) != 17:
        raise ParseError("Osaka Monorail segment count changed")

    result: list[Line] = []
    for line, (rail_class, stations) in zip(lines, _ROUTES):
        rails = station_map.select(f".{rail_class}")
        if len(rails) != 1:
            raise ParseError("Osaka Monorail route map is missing or duplicated")
        rail = rails[0]
        # Station 17 is shared by the branch, but its node belongs to the main rail.
        route_stations = stations if stations[0] == 11 else stations[1:]
        if tuple(str(node.get("id")) for node in rail.select("p[id^=station_]")) != tuple(
            f"station_{number}" for number in route_stations
        ):
            raise ParseError("Osaka Monorail route station topology changed")
        expected = tuple(f"line{a}-{b}" for a, b in zip(stations, stations[1:]))
        segments = rail.select("p > span[id^=line]")
        if tuple(str(segment.get("id")) for segment in segments) != expected:
            raise ParseError("Osaka Monorail segment topology changed")
        states: list[LineStatus] = []
        details: list[str] = []
        for segment, a, b in zip(segments, stations, stations[1:]):
            if not isinstance(segment.parent, Tag) or segment.parent.get("id") != f"station_{b}":
                raise ParseError("Osaka Monorail segment is attached to the wrong station")
            raw_classes = segment.get("class")
            classes = tuple(raw_classes) if isinstance(raw_classes, list) else ()
            state = (_SEGMENT_STATES.get(classes[0], LineStatus.UNKNOWN)
                     if len(classes) == 1 else LineStatus.UNKNOWN)
            states.append(state)
            details.append(f"{names[a]}～{names[b]}: {' '.join(classes)}")
        if LineStatus.UNKNOWN in states:
            status = LineStatus.UNKNOWN
        elif all(state is LineStatus.SUSPENDED for state in states):
            status = LineStatus.SUSPENDED
        elif LineStatus.SUSPENDED in states:
            status = LineStatus.PARTIAL_SUSPENSION
        elif LineStatus.DELAYED in states:
            status = LineStatus.DELAYED
        else:
            status = LineStatus.NORMAL
        description = "\n".join((label, *details))
        alerts = () if status is LineStatus.NORMAL else (make_alert(
            line, status, f"{line.name} 運行情報", description,
            timing=timing_from_status(status),
        ),)
        result.append(snapshot(line, status, description, fetched_at, alerts=alerts))
    return tuple(result)


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.select_one(".operationStatus .operationStatus__status")
    if tag is None:
        raise ParseError("Osaka Monorail official status is missing")
    # Exclude the standing publication policy, English duplicate, and reader clock.
    for extra in tag.select(".-read, .-small, #dispTime"):
        extra.decompose()
    label = tag.get_text("\n", strip=True)
    if not label:
        raise ParseError("Osaka Monorail official status is empty")
    maps = soup.select(".operationStatus .stationMap__wrap")
    if len(maps) > 1:
        raise ParseError("Osaka Monorail station map is duplicated")
    if maps:
        return _map_statuses(maps[0], label, lines, fetched_at)
    if soup.select_one(".operationStatus__detail__mapWrap") is not None:
        raise ParseError("Osaka Monorail station map is missing")
    normal = label == "現在、平常通り運行しております。"
    status = LineStatus.NORMAL if normal else LineStatus.UNKNOWN
    alerts = () if normal else (make_alert(
        lines[0], status, "大阪モノレール 運行情報", label, affected_line_ids=(),
    ),)
    return tuple(snapshot(line, status, label, fetched_at, alerts=alerts) for line in lines)


class OsakaMonorailProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(initial_lines("jp:osaka_monorail", _ID, _URL, _OPERATOR, _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.lines, self._now())

    @property
    def main(self) -> Line:
        return self._line("main")

    @property
    def saito(self) -> Line:
        return self._line("saito")
