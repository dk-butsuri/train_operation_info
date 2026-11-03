"""Tobu official service notices: archives and public-source inspection, 2026-11-02.

https://www.tobu.co.jp/service_status/ and /_assets/js/bundle.js (ServiceStatus)
show twelve publication units populated from /file/trainop/trainop.xml, pairing
line/description in order. Live XML verifies the exact normal sentence. There
are no separate status codes: other descriptions are notices (ALERT), without
inferring delay/suspension or affected individual branches from narrative words.
Unknown routes, missing/duplicate pairs and unsuccessful rsp raise ParseError.
The page's area notes define the northern Isesaki/Nikko groups; express trains,
liners and Kameido/Daishi are separate groups, not individual branch snapshots.
Four matching existing canonical IDs are reused, including the Skytree service
through Kuki/Minami-Kurihashi. Source names retain the exact publication scope.

Wayback XML captures 20240816070042 (typhoon warnings, planned reduced service,
and through-service cancellations) and 20240827122946 (express cancellations
and crossing-safety-check delays) verify non-normal descriptions. Replay URLs
include their original dt query strings; dt is a cache key, not an update time.
No same-incident recovery was verified; normal XML tests clearing old notices.
Unknown text, HTML descriptions and structural faults in tests are synthetic.
The displayed current time comes from an HTTP Date header, not a source update;
updated_at is None. Linked PDFs, maps, train positions and certificates are not
fetched. Evidence, hashes and scope: tests/fixtures/TOBU.md.
"""

from datetime import datetime
from pathlib import Path
from typing import Final
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.tobu.co.jp/service_status/"
_XML_URL: Final = "https://www.tobu.co.jp/file/trainop/trainop.xml"
_ID: Final = ProviderId("tobu")
_NORMAL: Final = "平常どおり運転しています。"
_ROUTES: Final = (
    ("日光線特急", "nikko_express", LineId("jp:tobu:nikko_express_group")),
    ("伊勢崎線特急", "isesaki_express", LineId("jp:tobu:isesaki_express_group")),
    ("ＳＬ・ＤＬ", "sl_dl", LineId("jp:tobu:sl_dl_group")),
    ("ＴＨライナー", "th_liner", LineId("jp:tobu:th_liner_group")),
    ("東武スカイツリーライン〜久喜・南栗橋", "skytree", LineId("jp:tobu:line_2ad5f9ac6422")),
    ("伊勢崎線　久喜　以北エリア", "isesaki_north", LineId("jp:tobu:isesaki_north_group")),
    ("日光線　南栗橋　以北エリア", "nikko_north", LineId("jp:tobu:nikko_north_group")),
    ("亀戸線・大師線", "kameido_daishi", LineId("jp:tobu:kameido_daishi_group")),
    ("東武アーバンパークライン", "urban_park", LineId("jp:tobu:line_2e8a7494d811")),
    ("ＴＪライナー", "tj_liner", LineId("jp:tobu:tj_liner_group")),
    ("東上本線", "tojo", LineId("jp:tobu:line_94b33b082d4f")),
    ("越生線", "ogose", LineId("jp:tobu:line_161291460e55")),
)
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_XML_URL, method="GET", format=DataFormat.XML,
            description='Route and service-group descriptions',
        ),
    ),
    provider_id=_ID, name="Tobu official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.tobu.co.jp/sitepolicy/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note="Site policy article 7 reserves statutory private use and requires "
    "approval for reproduction, sale or publication beyond that scope. Article 8 "
    "requires approval for business use. The service page publishes actual or "
    "expected delays of 30 minutes or more; NORMAL refers to that threshold. "
    "No separate service-specific reuse grant was found.",
    reviewed_at=datetime.fromisoformat("2026-11-02T02:30:00+00:00"),
)


def _parse(xml: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    root = ET.fromstring(xml)
    if root.tag != "rsp" or root.get("stat") != "ok" or [n.tag for n in root] != ["info"]:
        raise ParseError("Invalid Tobu response envelope")
    children = list(root[0])
    if [node.tag for node in children] != ["line", "description"] * len(_ROUTES):
        raise ParseError("Missing, duplicate or invalid Tobu line/description pairs")
    result: list[Line] = []
    for index, (name, _, _) in enumerate(_ROUTES):
        source_line, description = children[index * 2:index * 2 + 2]
        if len(source_line) or (source_line.text or "").strip() != name:
            raise ParseError("Unknown or reordered Tobu route")
        # Preserve actual XML markup as well as CDATA/escaped HTML, without
        # executing scripts or following links. Only description content is used.
        body = (description.text or "") + "".join(
            ET.tostring(child, encoding="unicode") for child in description
        )
        soup = BeautifulSoup(body, "html.parser")
        for node in soup.select("script, style"):
            node.decompose()
        text = soup.get_text("\n", strip=True)
        if not text:
            raise ParseError("Empty Tobu service description")
        status = LineStatus.NORMAL if text == _NORMAL else LineStatus.ALERT
        line = lines[index]
        alerts = () if status is LineStatus.NORMAL else (
            make_alert(line, status, f"{name} 運行情報", text),
        )
        result.append(snapshot(line, status, text, fetched_at, alerts=alerts,
                               source_line_names=(name,)))
    return tuple(result)


class TobuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None,
        snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(LINE_CATALOG[i].create_line(_ID, _URL) for _, _, i in _ROUTES),
                         client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _XML_URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    @property
    def nikko_express(self) -> Line:
        return self._line("nikko_express_group")

    @property
    def isesaki_express(self) -> Line:
        return self._line("isesaki_express_group")

    @property
    def sl_dl(self) -> Line:
        return self._line("sl_dl_group")

    @property
    def th_liner(self) -> Line:
        return self._line("th_liner_group")

    @property
    def skytree(self) -> Line:
        return self._line("line_2ad5f9ac6422")

    @property
    def isesaki_north(self) -> Line:
        return self._line("isesaki_north_group")

    @property
    def nikko_north(self) -> Line:
        return self._line("nikko_north_group")

    @property
    def kameido_daishi(self) -> Line:
        return self._line("kameido_daishi_group")

    @property
    def urban_park(self) -> Line:
        return self._line("line_2e8a7494d811")

    @property
    def tj_liner(self) -> Line:
        return self._line("tj_liner_group")

    @property
    def tojo(self) -> Line:
        return self._line("line_94b33b082d4f")

    @property
    def ogose(self) -> Line:
        return self._line("line_161291460e55")
