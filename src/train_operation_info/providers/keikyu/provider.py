"""Keikyu (京浜急行電鉄) official service notice for all five lines.

Investigation: public HTML inspection of the live page plus Wayback Machine
archives (public-source inspection and archive, both). The human-facing page
https://unkou.keikyu.co.jp/ is server-rendered: a single
``dl.index_unit`` block holds one ``dt`` update timestamp ("YYYY/MM/DD
HH:MM更新", Asia/Tokyo) and one or more ``dd`` elements containing the current
notice as free-form Japanese prose. There is no separate status code, icon or
field: the only verified fixed string is the exact normal message
"京急線は平常通り運転しています。" The page explains its own publication
threshold ("全線にわたり10分以上の遅れ・運転見合わせが発生または見込まれる場合")
and never structurally names which of the five lines are affected, even when
the prose does (see below). This mirrors ``providers/hanshin``, whose single
site-wide notice is likewise replicated across all of the operator's existing
per-line canonical IDs rather than invented into a new combined ID.

``reports/keikyu_cdx.json`` / ``reports/keikyu_cdx_scan.py`` (left by a prior
investigation) list every Wayback capture of ``unkou.keikyu.co.jp``. Sampling
across 2015-2026 and re-fetching several captures confirmed:
- Normal, current template, e.g.
  https://web.archive.org/web/20231102112722id_/https://unkou.keikyu.co.jp/
  and the current live page (2026-11-03T00:29 JST): exactly the fixed string
  above, with a trailing empty ``<dd><br /></dd>``.
- Delay prose, current template, e.g.
  https://web.archive.org/web/20220713030847id_/https://unkou.keikyu.co.jp/
  ("...の一部電車に遅れ。" plus a following 【遅延】 detail paragraph) and
  https://web.archive.org/web/20240927133743id_/https://unkou.keikyu.co.jp/
  (signal-equipment inspection delay).
- Suspension prose naming specific sections, current template:
  https://web.archive.org/web/20250730013943id_/https://unkou.keikyu.co.jp/
  ("...の上下線の運転を見合わせ" for the 久里浜線/逗子線 sections only, due to a
  tsunami warning; 本線 and 空港線/大師線 are not mentioned).
- A second, real non-empty ``dd`` can carry supplementary prose alongside an
  incident (e.g. https://web.archive.org/web/20220207231354id_/...: a delay
  notice plus a same-day snow forecast advisory).
- Pre-2019 captures use an older ``div.unko-panel`` template with the same
  free-text convention but no ``dl.index_unit``/``dt`` markup (e.g.
  20160614005000, 20180827141025); that legacy layout is out of scope.

Because the only stable, verified field is the single fixed normal string,
and the source never structurally (as opposed to in prose) names which lines
are affected, any non-normal notice keeps every line ``UNKNOWN`` with one
shared alert carrying the full prose and ``affected_line_ids=()``, like
``providers/hanshin``: marking all five lines ALERT would attribute e.g. the
2025-07-30 Kurihama/Zushi suspension to the Main Line. We do not parse "遅れ"/"見合わせ"
keywords, station names or line names out of the prose to infer DELAYED,
SUSPENDED, PARTIAL_SUSPENSION or which of the five lines are affected: the
2025-07-30 capture shows a suspension confined to two sections while the
first dd of several delay captures only says "...に遅れ。" without a stable
severity vocabulary, so no narrative mapping was verified as stable. Text
that starts with, but is not exactly equal to, the fixed normal message is
likewise ``UNKNOWN`` (unverified mixed case; no real capture of it was found).

The source publishes no explicit applicability window: ``timing`` stays
``UNKNOWN`` and ``active_from``/``active_until`` are never set. The explicit
``dt`` update timestamp is kept as ``updated_at`` (Asia/Tokyo); it is a real
publication time, not a page-load clock. Only the single status page is
fetched: the homepage's duplicate summary link, social-media feeds, the delay
certificate issuance page and the bad-weather/earthquake PDF are out of
scope. Evidence, captured-at UTC times and SHA-256 hashes are recorded in
tests/fixtures/KEIKYU.md.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Final
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://unkou.keikyu.co.jp/"
_ID: Final = ProviderId("keikyu")
_TITLE: Final = "京急線 運行情報"
_HEADER_TEXT: Final = "鉄道運行情報"
_NORMAL: Final = "京急線は平常通り運転しています。"
_UPDATE_PATTERN: Final = re.compile(
    r"(\d{4})/(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})更新",
)
# key -> canonical LineId. All five share one page-wide notice; the official
# publication unit never distinguishes among them structurally.
_ROUTES: Final[tuple[tuple[str, LineId], ...]] = (
    ("main", LineId("jp:keikyu:line_78db092fdebd")),
    ("airport", LineId("jp:keikyu:line_f7fdfd13f776")),
    ("daishi", LineId("jp:keikyu:line_f45aa080b06c")),
    ("kurihama", LineId("jp:keikyu:line_1baf033c4c82")),
    ("zushi", LineId("jp:keikyu:line_298c2fc57ddd")),
)
_ROUTE_IDS: Final = dict(_ROUTES)

_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Keikyu official", source_page_url=HttpUrl(_URL),
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description="Server-rendered network-wide service notice",
        ),
    ),
    terms_url=HttpUrl("https://www.keikyu.co.jp/website-guide.html"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "General site terms (website-guide.html section 1) reserve copying to "
        "private/home use and require prior consent for other reuse. The "
        "service notice page itself carries a stronger, specific notice "
        "('本内容に関する編集著作権を含む一切の権利は、京浜急行電鉄株式会社に帰属します。"
        "この運行情報を無断で転載・複写すること、また体裁を変更するなどしてホームページ"
        "等で公開することを固く禁じます。') with no private-use carve-out, so this is "
        "recorded as PERMISSION_REQUIRED rather than PRIVATE_USE_ONLY. The page states its "
        "own publication threshold: roughly 10-minute delays/suspensions, network-wide, "
        "that are occurring or anticipated."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-03T03:45:36.656796+00:00"),
)


def _normalize(text: str) -> str:
    return "".join(text.split())


def _parse(html: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    headers = soup.select("h1.heading_title")
    if len(headers) != 1 or headers[0].get_text(strip=True) != _HEADER_TEXT:
        raise ParseError("Keikyu page identity changed")
    units = soup.select("dl.index_unit")
    if len(units) != 1:
        raise ParseError("Keikyu status block missing or duplicated")
    unit = units[0]
    dts = unit.select("dt")
    dds = unit.select("dd")
    if len(dts) != 1 or not dds:
        raise ParseError("Keikyu status block structure changed")
    match = _UPDATE_PATTERN.fullmatch(dts[0].get_text(strip=True))
    if match is None:
        raise ParseError("Keikyu update timestamp format changed")
    year, month, day, hour, minute = (int(value) for value in match.groups())
    try:
        updated_at = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Tokyo"))
    except ValueError as exc:
        raise ParseError("Keikyu update timestamp is not a valid date") from exc
    body = "\n".join(dd.get_text("\n", strip=True) for dd in dds).strip()
    if not body:
        raise ParseError("Keikyu status text is empty")
    # A network-wide notice does not identify which of the five lines it
    # concerns, so no line is marked ALERT on its behalf (as in hanshin).
    status = LineStatus.NORMAL if _normalize(body) == _NORMAL else LineStatus.UNKNOWN
    alerts = () if status is LineStatus.NORMAL else (
        make_alert(lines[0], status, _TITLE, body, affected_line_ids=()),
    )
    return tuple(
        snapshot(line, status, body, fetched_at, updated_at=updated_at, alerts=alerts)
        for line in lines
    )


class KeikyuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(
            tuple(LINE_CATALOG[identifier].create_line(_ID, _URL) for _, identifier in _ROUTES),
            client=client, snapshot_dir=snapshot_dir,
        )

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    def _route(self, key: str) -> Line:
        identifier = _ROUTE_IDS[key]
        return next(line for line in self.lines if line.line_id == identifier)

    @property
    def main(self) -> Line:
        return self._route("main")

    @property
    def airport(self) -> Line:
        return self._route("airport")

    @property
    def daishi(self) -> Line:
        return self._route("daishi")

    @property
    def kurihama(self) -> Line:
        return self._route("kurihama")

    @property
    def zushi(self) -> Line:
        return self._route("zushi")
