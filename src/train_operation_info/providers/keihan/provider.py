"""Keihan official service alerts.

Investigation: Both archive and public-source inspection. /app-
files/js/custom/traffic_information_index.js documents FileList.xml, traininfo XML,
emergency JSON, route-ID groups, and icon codes. Archived XML captures 20230911234517,
20251101104408 and 20261013060555 verify suspension, shuttle operation and delay. Use
direct eif/lin and eif/sts only: route names in replacement-transport prose are not
affected-line IDs. Evidence: tests/fixtures/SOURCES.md.
"""

from datetime import datetime
import re
from typing import Final
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from pydantic import (
    BaseModel, ConfigDict, Field, HttpUrl,
)

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    Line, LineStatus, Operator, OperatorId, ProviderId, ProviderMetadata, ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, initial_lines, make_alert, snapshot

_URL: Final = "https://www.keihan.co.jp/traffic/information/"
_JSON_URL: Final = "https://www.keihan.co.jp/tinfo/06-app/info.json"
_LIST_URL: Final = "https://www.keihan.co.jp/tinfo/05-flist/FileList.xml"
_XML_ROOT: Final = "https://www.keihan.co.jp/tinfo/01-traininfo/"
_ID: Final = ProviderId("keihan")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:keihan"), name="京阪電気鉄道")
_DEFINITIONS: Final = (
    ("main", "京阪本線"), ("oto", "鴨東線"), ("nakanoshima", "中之島線"),
    ("katano", "交野線"), ("uji", "宇治線"), ("keishin", "京津線"),
    ("ishiyama_sakamoto", "石山坂本線"), ("cable", "石清水八幡宮参道ケーブル"),
)
_ROUTES: Final = {
    "050010": (0,), "050020": (1,), "050030": (2,), "050040": (3,),
    "050050": (4,), "050090": (5,), "050080": (6,), "050060": (7,),
    "050100": (0, 1), "050110": (0,), "050999": (0, 1, 2, 3, 4),
}


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_JSON_URL, method="GET", format=DataFormat.JSON,
            description='Emergency notice',
        ),
        SourceEndpoint(
            url=_LIST_URL, method="GET", format=DataFormat.XML,
            description='Current traininfo filename',
        ),
        SourceEndpoint(
            url=_XML_ROOT + "{filename}", method="GET", format=DataFormat.XML,
            is_template=True,
            description='Filename from FileList.xml',
        ),
    ),
    provider_id=ProviderId('keihan'), name='Keihan official',
    source_page_url=HttpUrl('https://www.keihan.co.jp/traffic/information/'),
    terms_url=HttpUrl('https://www.keihan.co.jp/terms.html'),
    additional_terms_urls=(HttpUrl('https://www.keihan.co.jp/traffic/information/'), ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note='The service page prohibits unapproved duplication, republication and sale. General terms separately discuss statutory private use and prohibit business use without approval; a service-specific reuse grant was not found.',
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)

class _Emergency(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    title: str
    body: str
    emergency: int = Field(ge=0, le=1)


def _parse(xml: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    root = ET.fromstring(xml)
    if root.tag != "TrainInfo":
        raise ParseError("Invalid Keihan TrainInfo root")
    time_text = root.findtext("time")
    if time_text is None or re.fullmatch(r"\d{14}", time_text) is None:
        raise ParseError("Missing Keihan source timestamp")
    updated_at = datetime.strptime(time_text, "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    difference = root.find("./info/dif")
    title = root.findtext("./info/HPDelivery/title")
    message = root.findtext("./info/HPDelivery/msg")
    if difference is None or not title or not message:
        raise ParseError("Incomplete Keihan official statement")
    events = difference.findall("eif")
    if not events and difference.get("all") != "0":
        raise ParseError("Keihan reports an incident without route information")
    statuses: dict[int, list[LineStatus]] = {index: [] for index in range(len(lines))}
    labels: dict[int, list[str]] = {index: [] for index in range(len(lines))}
    alerts: dict[int, list[ServiceAlert]] = {index: [] for index in range(len(lines))}
    for event in events:
        route = event.find("lin")
        state = event.find("sts")
        if route is None or state is None:
            raise ParseError("Keihan incident lacks direct line/status fields")
        route_id = route.get("pid", "")
        if route_id not in _ROUTES:
            raise ParseError(f"Unknown Keihan route ID: {route_id}")
        icon = state.get("icn", "").strip()
        status = {
            "1": LineStatus.SUSPENDED, "2": LineStatus.DELAYED,
            "3": LineStatus.PARTIAL_SUSPENSION, "4": LineStatus.NORMAL,
        }.get(icon, LineStatus.UNKNOWN)
        label = state.findtext("nm[@lng='ja']") or f"Unknown icon {icon}"
        indices = _ROUTES[route_id]
        affected_ids = tuple(lines[index].line_id for index in indices)
        alert = make_alert(
            lines[indices[0]], status, title, message,
            alert_id=f"keihan:{difference.get('ono', updated_at.isoformat())}:{route_id}",
            affected_line_ids=affected_ids,
        )
        for index in indices:
            statuses[index].append(status)
            labels[index].append(label)
            if status is not LineStatus.NORMAL:
                alerts[index].append(alert)
    return tuple(snapshot(
        line, combined_status(tuple(statuses[index])),
        " / ".join(labels[index]) or "平常運転（30分以上の遅れの掲載なし）",
        fetched_at, updated_at=updated_at, alerts=tuple(alerts[index]),
    ) for index, line in enumerate(lines))


class KeihanProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(initial_lines("jp:keihan", _ID, _URL, _OPERATOR, _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _JSON_URL)
        response.raise_for_status()
        emergency = _Emergency.model_validate_json(response.content)
        if emergency.emergency:
            description = "\n".join(filter(None, (emergency.title, emergency.body)))
            if not description:
                raise ParseError("Empty Keihan emergency statement")
            alert = make_alert(
                self.lines[0], LineStatus.UNKNOWN, emergency.title or "京阪電車 運行情報",
                description, affected_line_ids=(),
            )
            return tuple(snapshot(
                line, LineStatus.UNKNOWN, description, self._now(), alerts=(alert,),
            ) for line in self.lines)
        listing = await self._get(client, _LIST_URL)
        listing.raise_for_status()
        root = ET.fromstring(listing.content)
        filename = root.findtext("traininfo")
        if root.tag != "FileList" or filename is None or re.fullmatch(r"traininfo\d{14}\.xml", filename) is None:
            raise ParseError("Invalid Keihan traininfo filename")
        response = await self._get(client, _XML_ROOT + filename)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    @property
    def main(self) -> Line:
        return self._line("main")

    @property
    def oto(self) -> Line:
        return self._line("oto")

    @property
    def nakanoshima(self) -> Line:
        return self._line("nakanoshima")

    @property
    def katano(self) -> Line:
        return self._line("katano")

    @property
    def uji(self) -> Line:
        return self._line("uji")

    @property
    def keishin(self) -> Line:
        return self._line("keishin")

    @property
    def ishiyama_sakamoto(self) -> Line:
        return self._line("ishiyama_sakamoto")

    @property
    def cable(self) -> Line:
        return self._line("cable")
