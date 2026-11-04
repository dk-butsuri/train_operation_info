"""Hong Kong MTR's public heavy-rail service-status lights.

Investigation: public HTML/JavaScript and live normal XML, 2026-11-04.
https://www.mtr.com.hk/en/customer/main/index.html loads
https://www.mtr.com.hk/share/customer/js/RYGfunc.js?v=0.2, whose
createRYGLineStatus reads /alert/ryg_line_status_lite.xml. Its official legend,
/alert/legend_remarks_v2.xml, defines green=normal, grey=non-service hours,
yellow=delay or gradual resumption, red=disruption, pink=delay or disruption,
typhoon=cyclone warning. Yellow maps to DELAYED, red/pink/typhoon to ALERT:
none establishes full/partial suspension. Grey maps to NORMAL (no disruption
asserted, not a claim that trains run). Unknown codes remain UNKNOWN.
common_rpyg.js resolves /alert/getDomain.php; the reviewed response is '/',
which that script strips to the same origin. This provider uses that origin's
public XML directly, without alternate hosts or fallbacks.

Only the ten heavy-rail routes present in the reviewed feed are supported.
Light Rail, High Speed Rail, separate Traffic News banners/detail pages and
special/long-term arrangements outside the line-status feed are not fetched.
Messages within a line are retained, including multiple messages; their prose
does not determine status, scope, timing or validity periods. timing stays
UNKNOWN. lastBuildDate has no timezone or verified timestamp specification,
so updated_at stays None. Browser refresh time is not a source update time.
No abnormal archived response was found in the queried Wayback CDX index;
abnormal/recovery tests are synthetic and based on the published legend and
message fields consumed by the official JavaScript, not recorded incidents.
Evidence, hashes, limitations and terms: tests/fixtures/MTR.md.
"""

from datetime import datetime
from pathlib import Path
from typing import Final
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_PAGE: Final = "https://www.mtr.com.hk/en/customer/main/index.html"
_URL: Final = "https://www.mtr.com.hk/alert/ryg_line_status_lite.xml"
_ID: Final = ProviderId("mtr")
_CODES: Final = {
    "TWL": LineId("hk:mtr:tsuen_wan"),
    "KTL": LineId("hk:mtr:kwun_tong"),
    "ISL": LineId("hk:mtr:island"),
    "SIL": LineId("hk:mtr:south_island"),
    "TKL": LineId("hk:mtr:tseung_kwan_o"),
    "TCL": LineId("hk:mtr:tung_chung"),
    "DRL": LineId("hk:mtr:disneyland_resort"),
    "AEL": LineId("hk:mtr:airport_express"),
    "EAL": LineId("hk:mtr:east_rail"),
    "TML": LineId("hk:mtr:tuen_ma"),
}
# Labels transcribed from the official legend; never derived from message prose.
_STATES: Final = {
    "green": (LineStatus.NORMAL, "Normal Service"),
    "grey": (LineStatus.NORMAL, "Non-service hours"),
    "yellow": (LineStatus.DELAYED, "Service Delay – Additional waiting and travelling time*; or Service gradually resuming*"),
    "red": (LineStatus.ALERT, "Service Disruption – consider using other transport*"),
    "pink": (LineStatus.ALERT, "Service delay or disruption"),
    "typhoon": (LineStatus.ALERT, "Tropical Cyclone Warning Signals issued"),
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Hong Kong MTR", source_page_url=HttpUrl(_PAGE),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.XML,
        description="Heavy-rail line-status lights and embedded message titles/links; no detail-page requests",
    ),),
    terms_url=HttpUrl("https://www.mtr.com.hk/en/customer/main/terms_of_use.html"),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note=(
        "MTR website Terms of Use section 5 limits website use to personal, "
        "non-commercial use. Sections 5 and 10 restrict copying, redistribution, "
        "derivative works and commercial exploitation without permission, subject "
        "to applicable law. Public availability is not an open-data licence."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-04T07:57:26+00:00"),
)


def _field(element: ET.Element, name: str, *, allow_empty: bool = False) -> str:
    matches = element.findall(name)
    if len(matches) != 1 or len(matches[0]):
        raise ParseError(f"MTR field is missing, duplicated or not text: {name}")
    value = (matches[0].text or "").strip()
    if not value and not allow_empty:
        raise ParseError(f"MTR field is empty: {name}")
    return value


def _text(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)


def _parse(xml: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ParseError("Invalid MTR status XML") from exc
    if root.tag != "ryg_status":
        raise ParseError("MTR status XML root changed")
    _field(root, "lastBuildDate")  # Unzoned source build time is not an incident timestamp.
    by_id = {line.line_id: line for line in lines}
    parsed: dict[LineId, Line] = {}
    for item in root.findall("line"):
        code = _field(item, "line_code")
        identifier = _CODES.get(code)
        if identifier is None or identifier in parsed:
            raise ParseError(f"Unknown or duplicate MTR line: {code}")
        line = by_id[identifier]
        if _field(item, "line_name") != line.name:
            raise ParseError(f"MTR line code/name mismatch: {code}")
        _field(item, "line_name_tc")
        raw = _field(item, "status")
        status, label = _STATES.get(raw, (LineStatus.UNKNOWN, raw))
        containers = item.findall("messages")
        if (
            len(containers) != 1 or (containers[0].text or "").strip()
            or any(child.tag != "message" or (child.tail or "").strip() for child in containers[0])
        ):
            raise ParseError(f"MTR messages structure changed: {code}")
        alerts: list[ServiceAlert] = []
        for message in containers[0]:
            title = _text(_field(message, "title_en"))
            link = _field(message, "url_en", allow_empty=True)
            if link:
                link = str(HttpUrl(urljoin(_URL, link)))
            if not title:
                raise ParseError(f"MTR message title is empty: {code}")
            # A green/grey light does not erase a separately supplied message.
            if status is LineStatus.NORMAL:
                status = LineStatus.ALERT
            alerts.append(make_alert(
                line, status, title, "\n".join(part for part in (label, title, link) if part),
                language="en",
            ))
        if status is not LineStatus.NORMAL and not alerts:
            alerts.append(make_alert(line, status, label, label, language="en"))
        parsed[identifier] = snapshot(
            line, status, raw, fetched_at, alerts=tuple(alerts),
        )
    if parsed.keys() != by_id.keys():
        raise ParseError("MTR line list is incomplete")
    return tuple(parsed[line.line_id] for line in lines)


class MtrProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _PAGE
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        lines = tuple(LINE_CATALOG[identifier].create_line(_ID, _PAGE) for identifier in _CODES.values())
        super().__init__(lines, client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    @property
    def tsuen_wan(self) -> Line:
        return self._line("tsuen_wan")

    @property
    def kwun_tong(self) -> Line:
        return self._line("kwun_tong")

    @property
    def island(self) -> Line:
        return self._line("island")

    @property
    def south_island(self) -> Line:
        return self._line("south_island")

    @property
    def tseung_kwan_o(self) -> Line:
        return self._line("tseung_kwan_o")

    @property
    def tung_chung(self) -> Line:
        return self._line("tung_chung")

    @property
    def disneyland_resort(self) -> Line:
        return self._line("disneyland_resort")

    @property
    def airport_express(self) -> Line:
        return self._line("airport_express")

    @property
    def east_rail(self) -> Line:
        return self._line("east_rail")

    @property
    def tuen_ma(self) -> Line:
        return self._line("tuen_ma")
