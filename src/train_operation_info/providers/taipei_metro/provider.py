"""Metro Taipei's public, server-rendered operating lights.

Investigation: public HTML inspection plus a normal archived HTML response.
https://tpweb.metro.taipei/2026/ publishes six route cards, a source timestamp,
operating messages and an explicit legend: lightgreen.png = normal,
lightyellow.gif = route delay, lightred.gif = route partially obstructed,
lightgray.png = outside operating hours. The last is NORMAL in this service-alert
model (no disruption), with the original label retained; it does not mean trains
are running. Red does not establish a full-line suspension.
The current official site also embeds the related WebAbnormal page at
https://www.metro.taipei/cp.aspx?n=73C64BE06624284F.
https://web.archive.org/web/20261024103101id_/https://tpweb.metro.taipei/2026/
confirms normal cards and the same legend. CDX returned no abnormal capture;
delay, partial obstruction, closed hours and recovery scenarios are synthetic
mutations based on that published legend, not recorded incidents. Full suspension,
separate branch statuses and incident validity times are unverified. Unknown
lights are retained as UNKNOWN; missing/duplicate/unknown routes fail atomically.
The Circular Line is operated by New Taipei Metro, although listed by this
source. Evidence, original hashes and terms: tests/fixtures/SOURCES.md.
"""

from datetime import datetime
from typing import Final
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://tpweb.metro.taipei/2026/"
_ID: Final = ProviderId("taipei_metro")
_CODES: Final = {
    "BR": LineId("tw:trtc:wenhu"),
    "R": LineId("tw:trtc:tamsui_xinyi"),
    "G": LineId("tw:trtc:songshan_xindian"),
    "O": LineId("tw:trtc:zhonghe_xinlu"),
    "BL": LineId("tw:trtc:bannan"),
    "Y": LineId("tw:ntmetro:circular"),
}
_LIGHTS: Final = {
    "lightgreen.png": LineStatus.NORMAL,
    "lightyellow.gif": LineStatus.DELAYED,
    "lightred.gif": LineStatus.PARTIAL_SUSPENSION,
    "lightgray.png": LineStatus.NORMAL,
}
_NORMAL_MESSAGES: Final = frozenset(("目前正常營運", "全線正常營運", "非營運時間"))
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Route lights and operating message',
        ),
    ),
    provider_id=_ID, name="Metro Taipei (MRT)",
    source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl(
        "https://www.metro.taipei/News_Content.aspx?n=BD13B1ACE1C92D02"
        "&s=791780E919AB130C&sms=397D9220FC82B394",
    ),
    additional_terms_urls=(),
    usage_permission=UsagePermission.COMMERCIAL_ALLOWED,
    usage_note=(
        "Metro Taipei's government website open-data declaration grants free, "
        "non-exclusive reuse, adaptation and distribution to develop products or "
        "services, with source attribution (臺北捷運公司). The grant excludes "
        "trademarks, logos, personal data and specifically excluded third-party "
        "materials; it does not imply endorsement. This provider reads public "
        "website HTML, not the separate membership API."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.PARTIAL_SUSPENSION}),
    reviewed_at=datetime.fromisoformat("2026-11-01T15:02:02+00:00"),
)


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    panels = soup.select("#UpdatePanelRealStatusDetail")
    if len(panels) != 1:
        raise ParseError("Metro Taipei operating-information panel changed or is missing")
    panel = panels[0]
    timestamps = panel.select("#LabelUpdatetime")
    if len(timestamps) != 1:
        raise ParseError("Metro Taipei data update timestamp is missing or duplicated")
    raw_time = timestamps[0].get_text(strip=True)
    prefix = "資料更新時間："
    if not raw_time.startswith(prefix):
        raise ParseError("Metro Taipei data update timestamp label changed")
    updated_at = datetime.strptime(raw_time.removeprefix(prefix).strip(), "%Y/%m/%d %H:%M:%S").replace(
        tzinfo=ZoneInfo("Asia/Taipei"),
    )
    descriptions = panel.select(".realstatus__desc .realstatus__text")
    if len(descriptions) != 1 or not descriptions[0].get_text(strip=True):
        raise ParseError("Metro Taipei operating message is missing")
    description = descriptions[0].get_text("\n", strip=True)
    # Keep source links/diagrams available without guessing their incident details.
    references = tuple(dict.fromkeys(
        urljoin(_URL, raw)
        for element in panel.select(".realstatus__desc a[href], .abnormalpic img[src]")
        if isinstance(raw := element.get("href") or element.get("src"), str) and raw.strip()
    ))
    details = "\n".join((description, *references))
    by_id = {line.line_id: line for line in lines}
    states: dict[LineId, tuple[LineStatus, str]] = {}
    for item in panel.select(".realstatus__abnormalwrap .realstatusdetail__item"):
        codes = item.select(".linecode")
        names = item.select(".linetitletw")
        images = item.select(".realstatus__img img")
        if len(codes) != 1 or len(names) != 1 or len(images) != 1:
            raise ParseError("Metro Taipei route card changed or is incomplete")
        code = codes[0].get_text(strip=True)
        identifier = _CODES.get(code)
        if identifier is None or identifier in states:
            raise ParseError(f"Unknown or duplicate Metro Taipei route: {code}")
        line = by_id[identifier]
        if names[0].get_text(strip=True) != line.name:
            raise ParseError(f"Metro Taipei route name does not match code: {code}")
        image = images[0]
        src, label = image.get("src"), image.get("alt")
        if not isinstance(src, str) or not src.strip() or not isinstance(label, str) or not label.strip():
            raise ParseError(f"Metro Taipei route light or label is missing: {code}")
        marker = urlsplit(src).path.rsplit("/", 1)[-1]
        status = _LIGHTS.get(marker, LineStatus.UNKNOWN)
        label = label.strip()
        if marker not in _LIGHTS:
            label = f"{label} [{src}]"
        # Do not let a stale green/gray image silently hide a new source label.
        if status is LineStatus.NORMAL and label.removeprefix(line.name).strip() not in _NORMAL_MESSAGES:
            status = LineStatus.UNKNOWN
        states[identifier] = (status, label)
    if states.keys() != by_id.keys():
        raise ParseError("Metro Taipei route list is incomplete")

    result: list[Line] = []
    # When all lights are normal but a separate notice is present, the source
    # has not identified affected lines. Retain it once with an empty scope.
    unscoped: ServiceAlert | None = None
    if all(status is LineStatus.NORMAL for status, _ in states.values()) and (
        description not in _NORMAL_MESSAGES or references
    ):
        unscoped = make_alert(
            lines[0], LineStatus.UNKNOWN, "臺北捷運營運訊息", details,
            affected_line_ids=(), language="zh-Hant",
        )
    for line in lines:
        status, label = states[line.line_id]
        alerts: tuple[ServiceAlert, ...] = ()
        if unscoped is not None:
            status, alerts = LineStatus.UNKNOWN, (unscoped,)
        elif status is not LineStatus.NORMAL:
            alerts = (make_alert(
                line, status, label, f"{label}\n{details}", language="zh-Hant",
            ),)
        result.append(snapshot(
            line, status, label, fetched_at, updated_at=updated_at, alerts=alerts,
        ))
    return tuple(result)


class TaipeiMetroProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        lines = tuple(LINE_CATALOG[identifier].create_line(_ID, _URL) for identifier in _CODES.values())
        super().__init__(lines, client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.text, self.lines, self._now())

    @property
    def wenhu(self) -> Line:
        return self._line("wenhu")

    @property
    def tamsui_xinyi(self) -> Line:
        return self._line("tamsui_xinyi")

    @property
    def songshan_xindian(self) -> Line:
        return self._line("songshan_xindian")

    @property
    def zhonghe_xinlu(self) -> Line:
        return self._line("zhonghe_xinlu")

    @property
    def bannan(self) -> Line:
        return self._line("bannan")

    @property
    def circular(self) -> Line:
        return self._line("circular")
