"""Nankai official service alerts.

Investigation: Both archive and public HTML inspection of
https://www.traffic.nankai.co.jp/railinfo/01.html. The route legend's circle,
triangle and times markers correspond to normal, delayed and suspended service:
Wayback 20230814234144 verifies times with current suspension statements;
20250806220111 and 20261004112434 verify triangle
with current delay statements. Exact replay URLs, hashes and extraction are in
tests/fixtures/SOURCES.md. The live HTML verifies circle and the 20-minute
publication threshold. State comes from these markers, never narrative keywords.

Each named detail is scoped by its heading, not routes mentioned in the prose.
Limited-express/tourist-train notices retain an empty affected-line scope and
are attached as ALERT to otherwise normal lines in their source section.
Unknown markers retain UNKNOWN; missing/changed structure raises ParseError.
No distinct partial-suspension marker has been verified. Historical suspension
evidence predates the Semboku section; it is tested per section, without making
a missing section acceptable in current responses. Synthetic tests cover unknown
markers, inconsistent HTML and transport failure; archived/live normal pages
verify clearing old alerts, not a replay of the same incident's actual recovery.
"""

from datetime import datetime
import re
from typing import Final
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
from pathlib import Path

import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    Line, LineStatus, Operator, OperatorId, ProviderId, ProviderMetadata,
    ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, initial_lines, make_alert, snapshot

_URL: Final = "https://www.traffic.nankai.co.jp/railinfo/01.html"
_ID: Final = ProviderId("nankai")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:nankai"), name="南海電気鉄道")
_DEFINITIONS: Final = (
    ("main", "南海本線"), ("airport", "空港線"), ("wakayama_port", "和歌山港線"),
    ("takashinohama", "高師浜線"), ("kada", "加太線"), ("tanagawa", "多奈川線"),
    ("koya", "高野線（なんば～極楽橋）"), ("cable", "高野山ケーブル"),
    ("shiomibashi", "高野線（汐見橋～岸里玉出）"), ("semboku", "泉北線"),
)
_GROUPS: Final = {
    "nankai": ("main", "airport", "wakayama_port", "takashinohama", "kada", "tanagawa"),
    "koya": ("koya", "cable", "shiomibashi"),
    "semboku": ("semboku",),
}
_ROUTES: Final = {
    "南海線": "main", "空港線": "airport", "和歌山港線": "wakayama_port",
    "高師浜線": "takashinohama", "高師浜線(バス)": "takashinohama",
    "加太線": "kada", "多奈川線": "tanagawa", "高野線": "koya",
    "高野山ケーブル": "cable", "高野線汐見橋方面": "shiomibashi", "泉北線": "semboku",
}
_SERVICES: Final = {
    "nankai": ("ラピート", "サザン"),
    "koya": ("こうや", "りんかん", "泉北ライナー", "天空", "GRAN 天空"),
    "semboku": (),
}
_MARKERS: Final = {
    "circle": LineStatus.NORMAL, "triangle": LineStatus.DELAYED,
    "times": LineStatus.SUSPENDED,
}
_NORMAL: Final = "只今、20分以上の列車の遅れはございません。"
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Route markers and incident details',
        ),
    ),
    provider_id=_ID, name="Nankai official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.nankai.co.jp/terms.html"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note="The service page prohibits unapproved republication, copying and processing into electronic media. General site terms also prohibit unapproved secondary use. No reuse licence was found.",
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-01T14:53:09+00:00"),
)


def _one(soup: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = soup.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Missing or ambiguous Nankai element: {selector}")
    return matches[0]


def _parse_group(
    soup: BeautifulSoup, group: str, lines: tuple[Line, ...],
    fetched_at: datetime, updated_at: datetime,
) -> tuple[Line, ...]:
    legend = _one(soup, f"#{group}-line")
    listing = _one(legend, ":scope > ul")
    states: dict[str, LineStatus] = {}
    markers: dict[str, str] = {}
    service_markers: list[str] = []
    for item in listing.select(":scope > li"):
        label = item.get_text(" ", strip=True)
        marker = item.find("span", recursive=False)
        if not isinstance(marker, Tag):
            raise ParseError(f"Missing Nankai route marker: {label}")
        code = " ".join(marker.get_attribute_list("class"))
        if label.startswith(("特急列車", "観光列車")):
            service_markers.append(code)
            continue
        key = _ROUTES.get(label)
        if key not in _GROUPS[group] or key in states:
            raise ParseError(f"Unknown or duplicate Nankai route: {label}")
        states[key] = _MARKERS.get(code, LineStatus.UNKNOWN)
        markers[key] = code
    if set(states) != set(_GROUPS[group]):
        raise ParseError(f"Incomplete Nankai route legend: {group}")

    details = _one(soup, f"#{group}-line-wrap").select(":scope > .alert")
    if not details:
        raise ParseError(f"Missing Nankai official statement: {group}")
    by_key = {line.line_id.rsplit(":", 1)[1]: line for line in lines}
    alerts: dict[str, list[ServiceAlert]] = {key: [] for key in states}
    descriptions: dict[str, str] = {}
    service_notices = 0
    normal = len(details) == 1 and details[0].get_text(" ", strip=True) == _NORMAL
    if normal:
        if any(state is not LineStatus.NORMAL for state in states.values()) or any(
            code != "circle" for code in service_markers
        ):
            raise ParseError(f"Nankai normal statement conflicts with route markers: {group}")
    else:
        for detail in details:
            label = _one(detail, ".col-10.col-md-2").get_text(" ", strip=True)
            message = _one(detail, ".col-12.col-md-9").get_text(" ", strip=True)
            if not label or not message:
                raise ParseError("Empty Nankai incident heading or description")
            key = _ROUTES.get(label)
            if key in states:
                if key in descriptions:
                    raise ParseError(f"Duplicate Nankai incident: {label}")
                descriptions[key] = message
                # A notice with a normal marker does not prove delay/suspension.
                if states[key] is LineStatus.NORMAL:
                    states[key] = LineStatus.ALERT
                alerts[key].append(make_alert(by_key[key], states[key], label, message))
            elif label in _SERVICES[group]:
                service_notices += 1
                notice = make_alert(
                    lines[0], LineStatus.ALERT, label, message, affected_line_ids=(),
                )
                for route in states:
                    alerts[route].append(notice)
                    if states[route] is LineStatus.NORMAL:
                        states[route] = LineStatus.ALERT
            else:
                raise ParseError(f"Unknown Nankai incident heading: {label}")
        for key, code in markers.items():
            if code != "circle" and key not in descriptions:
                raise ParseError(f"Missing Nankai incident details: {key}")
        if any(code != "circle" for code in service_markers) and not service_notices:
            raise ParseError(f"Missing Nankai special-train notice: {group}")
    return tuple(snapshot(
        line, states[key],
        (f"{markers[key]}: {descriptions[key]}" if states[key] is LineStatus.UNKNOWN else
         descriptions.get(key, _NORMAL if states[key] is LineStatus.NORMAL else "特急・観光列車のお知らせ")),
        fetched_at, updated_at=updated_at, alerts=tuple(alerts[key]),
    ) for key, line in by_key.items())


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    # Current time is a separate text node; only this span is the source update.
    time_text = _one(soup, ".rosenzu-update-time > span").get_text(" ", strip=True)
    match = re.fullmatch(r"更新時刻\s*:\s*(\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2})", time_text)
    if match is None:
        raise ParseError("Invalid Nankai source update time")
    updated_at = datetime.strptime(match[1], "%Y/%m/%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    result: list[Line] = []
    for group, keys in _GROUPS.items():
        group_lines = tuple(line for line in lines if line.line_id.rsplit(":", 1)[1] in keys)
        result.extend(_parse_group(soup, group, group_lines, fetched_at, updated_at))
    return tuple(result)


class NankaiProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(initial_lines("jp:nankai", _ID, _URL, _OPERATOR, _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.lines, self._now())

    @property
    def main(self) -> Line:
        return self._line("main")

    @property
    def airport(self) -> Line:
        return self._line("airport")

    @property
    def wakayama_port(self) -> Line:
        return self._line("wakayama_port")

    @property
    def takashinohama(self) -> Line:
        return self._line("takashinohama")

    @property
    def kada(self) -> Line:
        return self._line("kada")

    @property
    def tanagawa(self) -> Line:
        return self._line("tanagawa")

    @property
    def koya(self) -> Line:
        return self._line("koya")

    @property
    def cable(self) -> Line:
        return self._line("cable")

    @property
    def shiomibashi(self) -> Line:
        return self._line("shiomibashi")

    @property
    def semboku(self) -> Line:
        return self._line("semboku")
