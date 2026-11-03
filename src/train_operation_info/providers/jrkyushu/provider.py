"""JR Kyushu: public HTML/JavaScript reverse engineering (no incident archive).

Sources: https://www.jrkyushu.co.jp/trains/info/ and its js/script.js,
data/IDS2Web.xml. script.js viewData maps aif/nm to eight panels; sts=1
displays eif/txt and eif/time, sts=0 without a long-term flag displays
NO_INFO_WORD. The long-term closure flags are structurally separate text files
(data/{fukhok,oita,sagnag,kuma,miya,kago,shin,nishi}.txt) and are neither
fetched nor validated, like JR West areaAnnouncements. The XML notice does not
determine individual affected routes or the extent of suspension: it becomes
ALERT, never DELAYED/SUSPENDED.
Six conventional panels are GROUPs, not aliases of Yahoo's individual routes.
Their alerts have affected_line_ids=(); the two Shinkansen panels identify a
single line. No prose is classified. Unknown codes remain UNKNOWN with raw text.
NORMAL means no XML notice only; it does not exclude long-term closures.
Separate inc/info_top.html, inc/info_mid.html, linked disaster/construction PDFs,
map images/IDS2IMG.xml, train positions and certificates are outside this scope.
cnvtDateStr displays eif/time as YYYYMMDDHHMM (trailing digits are not displayed);
Japan-local notice times alone supply updated_at. The root XML time and browser
clock are not notice updates. timing remains UNKNOWN and validity dates None,
including future prose. Live XML with sts=0 in all eight areas was verified.
No incident XML or same-incident recovery was found in the queried CDX index;
notice/date parsing, recovery, unknown codes and failures are synthetic tests.
See tests/fixtures/JRKYUSHU.md and jrkyushu_manifest.json for evidence and limits.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Final
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineScope, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.jrkyushu.co.jp/trains/info/"
_XML: Final = _URL + "data/IDS2Web.xml"
_ID: Final = ProviderId("jrkyushu")
# XML name -> public property, canonical identity, HTML/text-file basename.
_ROUTES: Final = {
    "Fukuoka-Kitakyushu": ("fukuoka_kitakyushu", LineId("jp:jr_kyushu:fukuoka_kitakyushu_group"), "fukhok"),
    "Oita": ("oita", LineId("jp:jr_kyushu:oita_group"), "oita"),
    "Saga-Nagasaki": ("saga_nagasaki", LineId("jp:jr_kyushu:saga_nagasaki_group"), "sagnag"),
    "Kumamoto": ("kumamoto", LineId("jp:jr_kyushu:kumamoto_group"), "kuma"),
    "Miyazaki": ("miyazaki", LineId("jp:jr_kyushu:miyazaki_group"), "miya"),
    "Kagoshima": ("kagoshima", LineId("jp:jr_kyushu:kagoshima_group"), "kago"),
    "Kyushu-Shinkansen": ("kyushu_shinkansen", LineId("jp:jr_kyushu:kyushu_shinkansen"), "shin"),
    "Nishi-Kyushu-Shinkansen": ("nishi_kyushu_shinkansen", LineId("jp:jr_kyushu:nishi_kyushu_shinkansen"), "nishi"),
}
_NORMAL: Final = "遅れの情報はありません。"
_NOTICE: Final = "遅れ等が発生しています。"
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="JR Kyushu official", source_page_url=HttpUrl(_URL),
    endpoints=(
        SourceEndpoint(url=_XML, method="GET", format=DataFormat.XML,
                       description="Eight area/panel statuses and notice text/update times"),
    ),
    terms_url=None,
    additional_terms_urls=(HttpUrl(_URL + "inc/info_mid.html"),),
    usage_permission=UsagePermission.UNSPECIFIED,
    usage_note="No general reuse licence or restriction applicable to this public feed was found in the reviewed official pages. The notice page states a disclaimer and a publication threshold of anticipated delays over 15 minutes affecting multiple trains. Train Navi, Web membership, JQ CARD and social media rules concern separate services and are not treated as feed terms. Coverage is limited to the XML; the structurally separate long-term closure flags, disaster/construction notices and PDFs are excluded. UNSPECIFIED is not a grant of reuse permission.",
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T15:55:00+00:00"),
)


@dataclass(frozen=True)
class _Notice:
    body: str
    updated_at: datetime


@dataclass(frozen=True)
class _Area:
    status: str
    notices: tuple[_Notice, ...]


def _one(root: ET.Element, name: str) -> ET.Element:
    matches = root.findall(name)
    if len(matches) != 1:
        raise ParseError(f"Missing or ambiguous JR Kyushu element: {name}")
    return matches[0]


def _text(root: ET.Element, name: str) -> str:
    node = _one(root, name)
    if len(node) or node.text is None or not node.text.strip():
        raise ParseError(f"Invalid JR Kyushu text field: {name}")
    return node.text.strip()


def _notice_time(value: str) -> datetime:
    # Preserve the official display's minute precision. Trailing two digits in
    # a 14-digit form have no verified meaning and do not supply extra precision.
    if not re.fullmatch(r"[0-9]{12}(?:[0-9]{2})?", value):
        raise ParseError("Invalid JR Kyushu notice update time")
    return datetime.strptime(value[:12], "%Y%m%d%H%M").replace(tzinfo=ZoneInfo("Asia/Tokyo"))


def _parse_xml(content: bytes) -> dict[str, _Area]:
    root = ET.fromstring(content)
    if root.tag != "IDS2Web":
        raise ParseError("Unexpected JR Kyushu XML root")
    info = _one(root, "info")
    areas: dict[str, _Area] = {}
    for element in info:
        if element.tag != "aif":
            raise ParseError("Unexpected JR Kyushu area element")
        name, status = _text(element, "nm"), _text(element, "sts")
        if name not in _ROUTES or name in areas:
            raise ParseError(f"Unknown or duplicate JR Kyushu area: {name}")
        notices = tuple(_Notice(_text(e, "txt"), _notice_time(_text(e, "time")))
                        for e in element.findall("eif"))
        if (status == "1" and not notices) or (status == "0" and notices):
            raise ParseError("JR Kyushu status conflicts with notice presence")
        areas[name] = _Area(status, notices)
    if set(areas) != set(_ROUTES):
        raise ParseError("Incomplete JR Kyushu area list")
    return areas


class JrKyushuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _URL + page + ".html")
            for _, identifier, page in _ROUTES.values()
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _XML)
        response.raise_for_status()
        areas = _parse_xml(response.content)
        fetched_at = self._now()
        result: list[Line] = []
        for source, (_, identifier, _) in _ROUTES.items():
            line = next(line for line in self.lines if line.line_id == identifier)
            area = areas[source]
            known = area.status in ("0", "1")
            status = (LineStatus.UNKNOWN if not known else
                      LineStatus.ALERT if area.status == "1" else LineStatus.NORMAL)
            # GROUP only describes the publication panel. Its incident does not
            # identify which individual routes or sections are affected.
            affected = () if line.scope is LineScope.GROUP else (line.line_id,)
            alerts: list[ServiceAlert] = [
                make_alert(line, LineStatus.ALERT if area.status == "1" else LineStatus.UNKNOWN,
                           line.name, notice.body, affected_line_ids=affected)
                for notice in area.notices
            ]
            if not known:
                alerts.append(make_alert(line, LineStatus.UNKNOWN, line.name,
                                         f"sts={area.status}", affected_line_ids=affected))
            summary = (f"sts={area.status}" if not known else
                       _NOTICE if area.status == "1" else _NORMAL)
            result.append(snapshot(
                line, status, summary, fetched_at, alerts=tuple(alerts),
                updated_at=max((n.updated_at for n in area.notices), default=None),
                source_line_names=(line.name.removeprefix("JR九州 "),),
            ))
        return tuple(result)

    def _route(self, key: str) -> Line:
        identifier = next(identifier for prop, identifier, _ in _ROUTES.values() if prop == key)
        return next(line for line in self.lines if line.line_id == identifier)

    @property
    def fukuoka_kitakyushu(self) -> Line:
        return self._route("fukuoka_kitakyushu")

    @property
    def oita(self) -> Line:
        return self._route("oita")

    @property
    def saga_nagasaki(self) -> Line:
        return self._route("saga_nagasaki")

    @property
    def kumamoto(self) -> Line:
        return self._route("kumamoto")

    @property
    def miyazaki(self) -> Line:
        return self._route("miyazaki")

    @property
    def kagoshima(self) -> Line:
        return self._route("kagoshima")

    @property
    def kyushu_shinkansen(self) -> Line:
        return self._route("kyushu_shinkansen")

    @property
    def nishi_kyushu_shinkansen(self) -> Line:
        return self._route("nishi_kyushu_shinkansen")
