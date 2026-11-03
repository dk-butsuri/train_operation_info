"""Official Toei Subway information for the four underground lines.

Investigation: public HTML/JavaScript inspection on 2026-11-02.
https://www.kotsu.metro.tokyo.jp/subway/schedule/index.html embeds the
current four .operation__item records and #js-operationInfo summary labels.
https://www.kotsu.metro.tokyo.jp/common/scripts/main.js?v=2026101901
does not fetch a separate status feed. Its js-currentTime uses an HTTP Date
header to display the current time, NOT an incident update: updated_at=None.
The official /subway/schedule/{asakusa,mita,oedo}_log.html pages show
平常運行 and ダイヤ乱れ, including same-event recovery on 2026-10-29.
ダイヤ乱れ is ALERT; it does not establish a specific delay/suspension.
Unknown labels or contradictory normal/body combinations are UNKNOWN and
retain the notice. Missing/duplicate records raise ParseError atomically.

Wayback CDX was inspected, but replay returned HTTP 429. Raw current
abnormal HTML, suspension labels, incident timestamp markup and partial
suspension remain unverified. Incident/recovery parser tests are synthetic
mutations of live normal HTML, informed by the rendered official history;
they are not saved real incident responses. No history, delay certificates,
train positions, linked pages or non-subway services are fetched at runtime.
Evidence, hashes and limitations: tests/fixtures/TOEI.md and manifest.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.kotsu.metro.tokyo.jp/subway/schedule/index.html"
_ID: Final = ProviderId("toei")
_ROUTES: Final = (
    ("Asakusa", "asakusa", "浅草線", LineId("jp:toei:line_a8db0e428af5")),
    ("Mita", "mita", "三田線", LineId("jp:toei:line_ea9aaf413955")),
    ("Shinjuku", "shinjuku", "新宿線", LineId("jp:toei:line_1dee09a8acc9")),
    ("Oedo", "oedo", "大江戸線", LineId("jp:toei:line_e0cd13888da5")),
)
_NORMAL: Final = "現在、１５分以上の遅延はありません。"
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Four subway route summaries',
        ),
    ),
    provider_id=_ID, name="Toei Subway official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.kotsu.metro.tokyo.jp/riyo/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The site policy reserves private copying, quotation and other uses allowed "
        "by copyright law. The operation page separately prohibits unauthorized "
        "copying, republication and publication on websites after reformatting. "
        "This is not a public-signage licence. Information is published for delays "
        "of 15 minutes or more, including anticipated delays."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T05:40:02+00:00"),
)


def _one(parent: Tag | BeautifulSoup, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Toei element missing or duplicated: {selector}")
    return matches[0]


def _text(tag: Tag) -> str:
    # Preserve paragraph/line breaks while removing executable/non-display text.
    clean = BeautifulSoup(str(tag), "html.parser")
    for hidden in clean.select("script, style, template, noscript"):
        hidden.decompose()
    for br in clean.select("br"):
        br.replace_with(NavigableString("\n"))
    return clean.get_text("\n", strip=True)


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    main = _one(soup, "#main-body")
    panel = _one(main, ".operation")
    summary = _one(soup, "#js-operationInfo")
    records = panel.select("dl.operation__item")
    if len(records) != len(_ROUTES):
        raise ParseError("Toei must contain exactly four subway records")
    result: list[Line] = []
    used: list[Tag] = []
    for (route_class, key, name, identifier), line in zip(_ROUTES, lines):
        route = _one(panel, f"dt.route{route_class}")
        record = route.parent
        if not isinstance(record, Tag) or record not in records or record in used:
            raise ParseError(f"Invalid Toei route record: {key}")
        used.append(record)
        if _text(route) != name or line.line_id != identifier:
            raise ParseError(f"Unexpected Toei route identity: {key}")
        body = _text(_one(record, "dd.operation__info"))
        link = _one(record, "dd.operation__link a")
        if link.get("href") != f"/subway/schedule/{key}_log.html":
            raise ParseError(f"Unexpected Toei history route: {key}")
        entry = _one(summary, f"dl.info{route_class}")
        if _text(_one(entry, "dt")) != name:
            raise ParseError(f"Unexpected Toei summary route: {key}")
        label = _text(_one(entry, "dd"))
        if not body or not label:
            raise ParseError(f"Empty Toei status: {key}")
        status = LineStatus.UNKNOWN
        if label == "平常運行" and body == _NORMAL:
            status = LineStatus.NORMAL
        elif label == "ダイヤ乱れ" and _NORMAL not in body:
            status = LineStatus.ALERT
        alerts = () if status is LineStatus.NORMAL else (
            make_alert(line, status, f"{name}：{label}", body),
        )
        result.append(snapshot(
            line, status, label, fetched_at, alerts=alerts, source_line_names=(name,),
        ))
    return tuple(result)


class ToeiProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(_ID, _URL)
            for _, _, _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content.decode("utf-8-sig"), self.lines, self._now())

    @property
    def asakusa(self) -> Line:
        return self._line("line_a8db0e428af5")

    @property
    def mita(self) -> Line:
        return self._line("line_ea9aaf413955")

    @property
    def shinjuku(self) -> Line:
        return self._line("line_1dee09a8acc9")

    @property
    def oedo(self) -> Line:
        return self._line("line_e0cd13888da5")
