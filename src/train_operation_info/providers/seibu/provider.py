"""Seibu Railway's official per-line status XML for eleven catalog lines.

Investigation: public HTML/JavaScript reverse engineering plus live fetches
on 2026-11-03 (no archived abnormal response exists; see below). Pages
inspected: https://www.seiburailway.jp/ (home widget, static
`.js-railwaysInfoLine > li` list of exactly twelve official line names:
"池袋線", "西武秩父線", "西武有楽町線", "豊島線", "狭山線", "山口線", "新宿線",
"拝島線", "西武園線", "国分寺線", "多摩湖線", "多摩川線") and
https://www.seiburailway.jp/railway/railwayinfo/ (detail page, same widget
logic, 15-minutes-or-more publication threshold stated in its own notice
list). Scripts inspected: https://www.seiburailway.jp/assets/js/script.js
(`railwaysInfo()` -> `getXml()`/`getLine()`/`getTxt()`) and
https://www.seiburailway.jp/assets/js/seiburailways.core.js (`operation()`).

`script.js` XHRs `/api/v1/travelinfo/raw/IDS2Web.xml` and reads
`info/dif` (`all` count plus `lif` children, each with `lin/nm` line name and
`sts/nm` status label), `info/tif` (map-pattern numbers only, used solely to
pick an illustration image) and `info/txt` (overall Japanese notice text).
`getLine()` treats a `lif` entry two ways: if its `sts/nm` is exactly
"運転見合わせ", "運転再開見込" or "運休" it adds the `stop` CSS class to the
matching mini-line item; any other non-empty label only adds `caution`. The
code never further distinguishes delay from partial suspension, so this
provider does the same: those three labels map to `SUSPENDED`, any other
non-empty label maps to `ALERT`. A `lin/nm` of exactly "西武線全線" is
checked with strict equality in the official code and applies to every line;
any other `lin/nm` is matched by substring containment against the twelve
verified official names above (mirroring `tempLine.match(item2.innerText)`),
which are mutually exclusive substrings. An unrecognized `lin/nm` raises
`ParseError` rather than guessing, since the twelve-name list was itself
confirmed live rather than inferred from prose.

`seiburailways.core.js` separately calls JSONP endpoint
`/api/v1/servicestatus.jsonp` (confirmed live) and renders only its
`IDS2Web[].plf.pld[].lang_ja` entries as a "重要なお知らせ" banner placed
*before* the status widget. That JSONP response has no `dif`/`tif` fields at
all, confirming `plf`/`pld` is a structurally separate long-term/important-
notice channel from the per-line `dif` status; this provider does not
request `/api/v1/servicestatus.jsonp` and ignores `plf`/`tif` in the XML.

Live XML fetched 2026-11-03 was the no-incident state (`dif`/`tif`/`plf`
`all="0"`, `info/txt` empty, `chk=0`); Wayback CDX has no captures of
`seiburailway.jp/api/v1/travelinfo/*` (JS-only, apparently never crawled),
and its handful of HTML captures of `/railway/railwayinfo/` only hold the
static server-rendered default icon, not the live XML state. No real
abnormal response was found. All suspended/alert/network-wide/unscoped-
notice/unknown-name/malformed-structure tests are therefore synthetic
mutations of the verified normal XML, built strictly from the branching
described above. `timing` is left `UNKNOWN`: this provider is not one of
the README's enumerated ACTIVE-timing sources. `info/txt` present without
any `dif` entry is treated as an unscoped notice (`affected_line_ids=()`),
downgrading otherwise-normal lines to `UNKNOWN`, mirroring the Tokyu
provider's established handling of the same ambiguity.

Evidence, hashes and the live JSONP excerpt are recorded in
tests/fixtures/SEIBU.md.
"""

from datetime import datetime
import re
from typing import Final
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_PAGE_URL: Final = "https://www.seiburailway.jp/railway/railwayinfo/"
_XML_URL: Final = "https://www.seiburailway.jp/api/v1/travelinfo/raw/IDS2Web.xml"
_ID: Final = ProviderId("seibu")
_ALL_LINES_MARKER: Final = "西武線全線"
_SUSPENDED_LABELS: Final = frozenset({"運転見合わせ", "運転再開見込", "運休"})

# (attribute name, verified official display-name fragments, canonical LineId)
_ROUTES: Final = (
    ("shinjuku", ("新宿線",), LineId("jp:seibu:line_02a838eb9e45")),
    ("toshima", ("豊島線",), LineId("jp:seibu:line_354248c5c7e4")),
    ("ikebukuro_chichibu", ("池袋線", "西武秩父線"), LineId("jp:seibu:line_45cb36b285e9")),
    ("seibuen", ("西武園線",), LineId("jp:seibu:line_66456985b818")),
    ("kokubunji", ("国分寺線",), LineId("jp:seibu:line_7bd734dcd18d")),
    ("tamako", ("多摩湖線",), LineId("jp:seibu:line_7e4a8b7d5033")),
    ("yamaguchi", ("山口線",), LineId("jp:seibu:line_c9258a4807a7")),
    ("tamagawa", ("多摩川線",), LineId("jp:seibu:line_e8dcfc68797a")),
    ("haijima", ("拝島線",), LineId("jp:seibu:line_f20220477394")),
    ("sayama", ("狭山線",), LineId("jp:seibu:line_f946fb99efeb")),
    ("yurakucho", ("西武有楽町線",), LineId("jp:seibu:line_fd1bf3ad13e2")),
)
_FRAGMENTS: Final = {identifier: fragments for _, fragments, identifier in _ROUTES}

_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Seibu Railway official",
    source_page_url=HttpUrl(_PAGE_URL),
    endpoints=(
        SourceEndpoint(
            url=_XML_URL, method="GET", format=DataFormat.XML,
            description=(
                "Current per-line status: info/dif (lif/lin/nm, lif/sts/nm) and "
                "info/txt. info/tif (map image pattern) and info/plf (separate "
                "important-notice feed) are present but not parsed."
            ),
        ),
    ),
    terms_url=HttpUrl("https://www.seiburailway.jp/policy/"),
    additional_terms_urls=(HttpUrl(_PAGE_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The operation-information page states that unauthorized reproduction "
        "or republishing of its notices, including with altered formatting on "
        "other websites, is strictly prohibited ('この情報を無断で転載・複写す"
        "ること...固く禁じます'). The site-wide copyright notice separately "
        "reserves statutory private use and requires the rightsholder's "
        "permission for reuse beyond that. No service-specific commercial "
        "reuse grant was found. The page states a publication threshold of "
        "15 minutes or more of delay."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-03T03:46:31+00:00"),
)


def _match_targets(lines: tuple[Line, ...], name: str) -> tuple[LineId, ...]:
    if name == _ALL_LINES_MARKER:
        return tuple(line.line_id for line in lines)
    matched = [identifier for identifier, fragments in _FRAGMENTS.items() if any(fragment in name for fragment in fragments)]
    if not matched:
        raise ParseError(f"Unknown Seibu line name in dif/lif: {name!r}")
    if len(matched) > 1:
        raise ParseError(f"Ambiguous Seibu line name in dif/lif: {name!r}")
    return (matched[0],)


def _parse(xml: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    root = ET.fromstring(xml)
    if root.tag != "IDS2Web":
        raise ParseError("Invalid Seibu IDS2Web root")
    time_text = root.findtext("time")
    if time_text is None or re.fullmatch(r"\d{14}", time_text) is None:
        raise ParseError("Missing or malformed Seibu source timestamp")
    updated_at = datetime.strptime(time_text, "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    if root.findtext("chk") is None:
        raise ParseError("Missing Seibu chk flag")
    info = root.find("info")
    if info is None:
        raise ParseError("Missing Seibu info block")
    overall_text = (info.findtext("txt") or "").strip()
    dif = info.find("dif")
    if dif is None or dif.get("all") is None:
        raise ParseError("Missing Seibu dif block")
    entries = dif.findall("lif")
    if dif.get("all") == "0" and entries:
        raise ParseError("Seibu dif reports zero incidents but lists line entries")
    if not entries and dif.get("all") != "0":
        raise ParseError("Seibu dif reports an incident without any line entry")

    by_id = {line.line_id: line for line in lines}
    statuses: dict[LineId, list[LineStatus]] = {identifier: [] for identifier in by_id}
    labels: dict[LineId, list[str]] = {identifier: [] for identifier in by_id}
    per_line_alerts: dict[LineId, list[ServiceAlert]] = {identifier: [] for identifier in by_id}

    for entry in entries:
        name = entry.findtext("lin/nm")
        label = entry.findtext("sts/nm")
        if not name or not label:
            raise ParseError("Seibu line entry is missing its line name or status label")
        status = LineStatus.SUSPENDED if label in _SUSPENDED_LABELS else LineStatus.ALERT
        targets = _match_targets(lines, name)
        alert = make_alert(
            by_id[targets[0]], status, label, overall_text or label,
            affected_line_ids=targets,
        )
        for identifier in targets:
            statuses[identifier].append(status)
            labels[identifier].append(label)
            per_line_alerts[identifier].append(alert)

    shared: tuple[ServiceAlert, ...] = ()
    if overall_text and not entries:
        shared = (make_alert(
            lines[0], LineStatus.ALERT, "西武鉄道: お知らせ（対象路線未特定）", overall_text,
            affected_line_ids=(),
        ),)

    result: list[Line] = []
    for line in lines:
        identifier = line.line_id
        status = combined_status(tuple(statuses[identifier])) if statuses[identifier] else LineStatus.NORMAL
        alerts = tuple(per_line_alerts[identifier]) + shared
        if status is LineStatus.NORMAL and shared:
            status = LineStatus.UNKNOWN
        label = " / ".join(labels[identifier]) or "平常運行（15分以上の遅れ等の掲載なし）"
        result.append(snapshot(
            line, status, label, fetched_at, updated_at=updated_at, alerts=alerts,
            source_line_names=_FRAGMENTS[identifier],
        ))
    return tuple(result)


class SeibuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _PAGE_URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _PAGE_URL) for _, _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _XML_URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    @property
    def shinjuku(self) -> Line:
        return self._line("line_02a838eb9e45")

    @property
    def toshima(self) -> Line:
        return self._line("line_354248c5c7e4")

    @property
    def ikebukuro_chichibu(self) -> Line:
        return self._line("line_45cb36b285e9")

    @property
    def seibuen(self) -> Line:
        return self._line("line_66456985b818")

    @property
    def kokubunji(self) -> Line:
        return self._line("line_7bd734dcd18d")

    @property
    def tamako(self) -> Line:
        return self._line("line_7e4a8b7d5033")

    @property
    def yamaguchi(self) -> Line:
        return self._line("line_c9258a4807a7")

    @property
    def tamagawa(self) -> Line:
        return self._line("line_e8dcfc68797a")

    @property
    def haijima(self) -> Line:
        return self._line("line_f20220477394")

    @property
    def sayama(self) -> Line:
        return self._line("line_f946fb99efeb")

    @property
    def yurakucho(self) -> Line:
        return self._line("line_fd1bf3ad13e2")
