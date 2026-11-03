"""Tosaden official streetcar service information (not bus services).

Investigation: archived HTML and public HTML/JavaScript inspection, 2026-11-02.
https://www.tosaden.co.jp/info/service.php?ID=1 embeds #main_header and
#main_body. /ssi/js/fn.js controls navigation/sliders, not a status endpoint.
The page's 電車 heading distinguishes it from bus information. A disrupted
page can replace the entire main title/body, including the policy section.

Wayback https://web.archive.org/web/20220918071853id_/https://www.tosaden.co.jp/info/service.php?ID=1
contains a typhoon closure announcement for September 19 and conditional
September 20 reopening. It has no separate status code or update timestamp.
20230602090407id_ at the same original URL contains the normal Japanese text;
the live 2026-11-02 page also includes an English translation. Old originals
are EUC-JP, current HTML is UTF-8; fixture extraction records the conversion.
Only the complete verified normal title/body yields NORMAL. Other nonempty
notices yield ALERT with the original title/body; narrative keywords do not
establish DELAYED, SUSPENDED or PARTIAL_SUSPENSION. Contradictory normal text
yields UNKNOWN. Missing/duplicated/empty structures raise ParseError atomically.

No dedicated duration or applicability fields exist. Free prose, yearless dates
and mixed conditional reopening notices are retained with timing UNKNOWN
and no active_from/active_until. Neither retrieval time nor dates in the separate
news list are an update timestamp: updated_at=None. Standalone delay/partial
closure HTML, same-event recovery and current abnormal markup are unverified;
malformed/unknown cases are synthetic. A separate normal capture tests clearing.

Runtime scope is the main service notice only. The separate 運行についてのお知らせ
news list and its linked articles (including vehicle-specific/long-term notices),
timetables, positions and bus information are not fetched. NORMAL only means the
main panel reports no delays of 30 minutes or more; it cannot rule out service
changes in separate articles or smaller delays. Evidence/hashes and limitations:
tests/fixtures/TOSADEN.md and tosaden_manifest.json.
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

_URL: Final = "https://www.tosaden.co.jp/info/service.php?ID=1"
_ID: Final = ProviderId("tosaden")
# Same network-wide scope as Yahoo 598/0; keep provider snapshots independent.
_LINE_ID: Final = LineId("jp:operator_74ae511377a2:line_d1d5a8a2e706")
_TITLE: Final = "（電車）運行状況について"
_NORMAL: Final = "現在、30分以上の遅れは発生していません。"
_NORMAL_BODIES: Final = frozenset((
    _NORMAL + "電車輸送課088-833-7121",
    _NORMAL + "電車輸送課088-833-7121"
    "Wearenodelaysofmorethan30minutes.TOSADENTRAFFIC088-833-7121",
))
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Tram network service notice',
        ),
    ),
    provider_id=_ID, name="Tosaden official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.tosaden.co.jp/info/sitepolicy.php"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "The service page prohibits unauthorized transcription, copying and "
        "processing into magnetic media. The general site policy discusses links, "
        "not a reuse licence. Information is published for delays of 30 minutes "
        "or more, including anticipated delays. Only the main service notice is "
        "retrieved; linked news, vehicle-specific and long-term notices are outside "
        "this provider's scope. NORMAL is not evidence of their absence."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-02T05:47:07.395296+00:00"),
)


def _one(parent: Tag | BeautifulSoup, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Tosaden element missing or duplicated: {selector}")
    return matches[0]


def _compact(text: str) -> str:
    return "".join(text.split())


def _parse(html: str | bytes, line: Line, fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    if _one(soup, "h2.tit_train").get_text(strip=True) != "電車":
        raise ParseError("Tosaden page is not streetcar service information")
    main = _one(soup, "#main_a")
    title = _one(main, "#main_header h1").get_text(" ", strip=True)
    body = _one(main, "#main_body")
    # This h2 is boilerplate, not an incident. Abnormal captures can omit it.
    headings = body.select("h2")
    if len(headings) > 1 or any(h.get_text(strip=True) != "運行情報について" for h in headings):
        raise ParseError("Unexpected Tosaden service policy structure")
    for hidden in body.select("script, style, template, noscript"):
        hidden.decompose()
    parts: list[str] = []
    for node in body.descendants:
        if isinstance(node, Tag) and node.name == "h2":
            break
        if type(node) is NavigableString and node.strip():
            parts.append(str(node).strip())
    description = "\n".join(parts)
    if not title or not description or description == "-":
        raise ParseError("Tosaden service title or notice is empty")
    compact = _compact(description)
    if _compact(title) == _TITLE and compact in _NORMAL_BODIES:
        status = LineStatus.NORMAL
    elif _NORMAL in compact:
        status = LineStatus.UNKNOWN
    else:
        status = LineStatus.ALERT
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(line, status, title, description),
    )
    return (snapshot(line, status, description, fetched_at, alerts=alerts),)


class TosadenProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            (LINE_CATALOG[_LINE_ID].create_line(_ID, _URL),),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        # Inspect the declaration as old captures use EUC-JP, current pages UTF-8.
        return _parse(response.content, self.main, self._now())

    @property
    def main(self) -> Line:
        return self.lines[0]
