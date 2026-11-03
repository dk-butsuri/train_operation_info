"""Taiwan Railway's server-rendered route obstruction list.

Investigation: public HTML reverse engineering and archived official HTML at
https://www.railway.gov.tw/tra-tip-web/tip/tip007/tip711/blockList .
The page pairs each .now_status with a four-column obstruction table. Its
published legend identifies row colors: Resume=normal, Delay=delayed;
Moderate/Severe/Extreme/Typhoon identify notices, not suspension extents.
https://web.archive.org/web/<timestamp>id_/ plus the URL above verifies:
20240213061449 Resume; 20240403013943 Extreme; 20240804153201 Delay;
20241117082659 Severe; 20250310054809 Delay; 20250707021531 Typhoon;
20241004110527 Moderate and Typhoon; 20260702152705 all-clear.
The summary 部份受阻 also contains recovered records, so it is not a suspension
code. Row classifications drive the aggregate only under that known summary.
Recovered rows remain informational alerts; removal clears them. Unknown colors,
changed legends and contradictory summaries remain UNKNOWN with source text.
Missing routes, row fields or table pairings fail atomically.

Timing remains UNKNOWN: neither disaster grades nor row dates prove validity.
Long-term construction and typhoon notices share the table and are all retained.
The page's displayed update time uses Asia/Taipei; it is not an incident time.
Row dates and estimated recovery times stay in the original text, never validity
bounds. No news, map, train-specific live delays or linked documents are fetched.
Full/partial suspension codes are unverified. Malformed/unknown states and
contradictions are synthetic tests. Evidence, terms and hashes: fixtures/TRA.md.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Final
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_URL: Final = "https://www.railway.gov.tw/tra-tip-web/tip/tip007/tip711/blockList"
_ID: Final = ProviderId("tra")
_ROUTES: Final = {
    "西部幹線": LineId("tw:tra:western_group"),
    "西部幹線 (海線)": LineId("tw:tra:western_coast"),
    "東部幹線": LineId("tw:tra:eastern_group"),
    "南迴線": LineId("tw:tra:south_link_group"),
    "成追線": LineId("tw:tra:chengzhui"),
    "平溪線": LineId("tw:tra:pingxi"),
    "深澳線": LineId("tw:tra:shenao"),
    "六家線": LineId("tw:tra:liujia"),
    "內灣線": LineId("tw:tra:neiwan"),
    "集集線": LineId("tw:tra:jiji"),
    "沙崙線": LineId("tw:tra:shalun"),
    "蘇澳新-蘇澳": LineId("tw:tra:suaoxin_suao"),
}
_LEGEND: Final = {
    "#009900": ("恢復正常 (Resume)", LineStatus.NORMAL),
    "#ffcc00": ("列車延誤 (Delay)", LineStatus.DELAYED),
    "#ee9200": ("列車丙級災害規模 (Moderate)", LineStatus.ALERT),
    "#ff0099": ("列車乙級災害規模 (Severe)", LineStatus.ALERT),
    "#cc0000": ("列車甲級災害規模 (Extreme)", LineStatus.ALERT),
    "#3300ff": ("颱風期間列車運行資訊 (Typhoon)", LineStatus.ALERT),
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Taiwan Railway Corporation (TRA)",
    source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Twelve route summaries, obstruction rows and status legend",
    ),),
    terms_url=HttpUrl("https://www.railway.gov.tw/tra-tip-web/adr/about-public-info-7"),
    additional_terms_urls=(HttpUrl("https://www.railway.gov.tw/tra-tip-web/tip/tip00F/tipF14/view"),),
    usage_permission=UsagePermission.COMMERCIAL_ALLOWED,
    usage_note=(
        "The website open-data statement grants free, non-exclusive, sublicensable "
        "reuse to develop products or services, with attribution to 國營臺灣鐵路股份有限公司. "
        "It excludes other intellectual-property rights, personal data and specially "
        "restricted works and does not imply endorsement. The separate copyright "
        "notice requires authorization or fair use for protected content; the "
        "website-wide open-data statement supplies the express reuse grant."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T15:56:56+00:00"),
)


def _one(parent: Tag, selector: str) -> Tag:
    elements = parent.select(selector)
    if len(elements) != 1:
        raise ParseError(f"TRA required field missing or duplicated: {selector}")
    return elements[0]


def _text(element: Tag) -> str:
    text = element.get_text(" ", strip=True)
    if not text:
        raise ParseError("TRA required text is empty")
    return text


def _color(element: Tag) -> str:
    style = element.get("style")
    if not isinstance(style, str) or not style.strip():
        raise ParseError("TRA status color is missing")
    # Only the source's single color declaration is interpreted. Other CSS is
    # retained as an unknown marker, rather than guessed from arbitrary styles.
    match = re.fullmatch(r"\s*color\s*:\s*(#[0-9a-fA-F]{6})\s*;?\s*", style)
    return match[1].lower() if match else style


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    content = _one(soup, "#content")
    panel = _one(content, ":scope > .operation-list")
    timestamps = [p for p in content.select(":scope > p") if p.get_text().startswith("更新時間：")]
    if len(timestamps) != 1:
        raise ParseError("TRA page update timestamp missing or duplicated")
    raw_time = "".join(str(t) for t in timestamps[0].find_all(string=True, recursive=False)).strip()
    updated_at = datetime.strptime(raw_time, "更新時間：%Y/%m/%d %H:%M").replace(
        tzinfo=ZoneInfo("Asia/Taipei"),
    )
    legend = _one(panel, ":scope > .info dl")
    labels: dict[str, str] = {}
    for marker in legend.select(":scope > dd"):
        legend_element = marker.find_next_sibling()
        if not isinstance(legend_element, Tag) or legend_element.name != "label":
            raise ParseError("TRA legend label missing")
        color = _color(marker)
        if color in labels:
            raise ParseError("TRA duplicate legend color")
        labels[color] = _text(legend_element)
    if not labels:
        raise ParseError("TRA legend missing")

    by_id = {line.line_id: line for line in lines}
    parsed: dict[LineId, Line] = {}
    children = panel.select(":scope > dl.now_status, :scope > table")
    if len(children) != 2 * len(lines) or len(panel.select(".now_status")) != len(lines):
        raise ParseError("TRA route/table list changed or is incomplete")
    for index in range(0, len(children), 2):
        summary, table = children[index:index + 2]
        if summary.name != "dl" or table.name != "table" or summary.find_next_sibling() is not table:
            raise ParseError("TRA route/table pairing changed")
        name = _text(_one(summary, ":scope > dt"))
        identifier = _ROUTES.get(name)
        if identifier is None or identifier in parsed:
            raise ParseError(f"TRA unknown or duplicate route: {name}")
        line = by_id[identifier]
        label = _text(_one(summary, ":scope > label"))
        marker = _one(summary, ":scope > dd")
        color = _color(marker)
        classes = set(marker.get_attribute_list("class"))
        normal = label == "全線正常運行" and color == "#5bb900" and classes == {"icon-fa", "circle-o"}
        obstructed = label == "部份受阻" and color == "#ff8400" and classes == {"icon-fa", "warning"}
        rows = table.select("tr")
        if obstructed and not rows:
            raise ParseError("TRA obstruction summary has no records")
        statuses: list[LineStatus] = []
        alerts: list[ServiceAlert] = []
        source_labels = [label]
        for row in rows:
            cells = row.select(":scope > td")
            if len(cells) != 4:
                raise ParseError("TRA obstruction row must contain four cells")
            values = tuple(_text(cell) for cell in cells)
            section = _text(_one(cells[1], ":scope > label"))
            row_marker = _one(cells[1], ":scope > span")
            row_color = _color(row_marker)
            legend_label = labels.get(row_color)
            known = _LEGEND.get(row_color)
            status = LineStatus.UNKNOWN
            if known is not None and known[0] == legend_label and set(row_marker.get_attribute_list("class")) == {"icon-fa", "fullcircle"}:
                status = known[1]
            state_label = f"{legend_label or 'Unknown'} [{row_color}]"
            references = tuple(dict.fromkeys(
                urljoin(_URL, href) for anchor in row.select("a[href]")
                if isinstance(href := anchor.get("href"), str) and href.strip() and not href.startswith("#")
            ))
            description = "\n".join((state_label, *values, *references))
            alerts.append(make_alert(line, status, f"{name} {section}: {state_label}", description, language="zh-Hant"))
            statuses.append(status)
            source_labels.append(state_label)
        if normal and not rows:
            status = LineStatus.NORMAL
        elif obstructed:
            status = combined_status(tuple(statuses))
        else:
            status = LineStatus.UNKNOWN
            alerts.append(make_alert(
                line, status, f"{name}: {label}", f"{_text(summary)} [{color}]", language="zh-Hant",
            ))
        parsed[identifier] = snapshot(
            line, status, "\n".join(source_labels), fetched_at,
            updated_at=updated_at, alerts=tuple(alerts),
        )
    if parsed.keys() != by_id.keys():
        raise ParseError("TRA route list is incomplete")
    return tuple(parsed[line.line_id] for line in lines)


class TraProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(LINE_CATALOG[i].create_line(_ID, _URL) for i in _ROUTES.values()), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.lines, self._now())

    @property
    def western(self) -> Line:
        return self._line("western_group")

    @property
    def western_coast(self) -> Line:
        return self._line("western_coast")

    @property
    def eastern(self) -> Line:
        return self._line("eastern_group")

    @property
    def south_link(self) -> Line:
        return self._line("south_link_group")

    @property
    def chengzhui(self) -> Line:
        return self._line("chengzhui")

    @property
    def pingxi(self) -> Line:
        return self._line("pingxi")

    @property
    def shenao(self) -> Line:
        return self._line("shenao")

    @property
    def liujia(self) -> Line:
        return self._line("liujia")

    @property
    def neiwan(self) -> Line:
        return self._line("neiwan")

    @property
    def jiji(self) -> Line:
        return self._line("jiji")

    @property
    def shalun(self) -> Line:
        return self._line("shalun")

    @property
    def suaoxin_suao(self) -> Line:
        return self._line("suaoxin_suao")
