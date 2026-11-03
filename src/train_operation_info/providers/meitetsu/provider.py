"""Meitetsu official service notices, using existing canonical route scopes.

Investigation: public HTML/CSS/JavaScript and archived HTML, 2026-11-02 UTC.
https://top.meitetsu.co.jp/em/ supplies the normal page; disrupted pages are
published at /em/ryokaku/format3.html. Follow HTTP redirects from /em/.
/em/css/basic.css defines emLv01 as suspension, emLv02 as delays OR partial
cancellation, emLv03/04 as alternative/bus transport, emLv05 as other notices.
The emInfoTitle heading must agree with the known class for a precise status.
The mixed emLv02 category yields ALERT, never an inferred DELAYED/reduced service.
SUSPENDED denotes an explicitly suspended section, not necessarily a whole line.

Wayback /web/20260208081057id_/https://top.meitetsu.co.jp/em/ryokaku/format3.html
contains Hiromi suspension, mixed disruption and alternative transport.
20260908095207 at that URL contains multiple suspended sections and mixed
disruption, with restart prose that must not override dedicated current fields.
20240831065722 contains multiple suspension blocks plus unscoped future prose;
20230815094730 contains all 19 source route names and restart/next-day prose.
Only the dedicated 路線 list / 区間 list supplies affected routes. Several source
names map to one existing Yahoo canonical group; their original names and section
text are retained. Unknown route names retain an unscoped alert, making otherwise
normal routes UNKNOWN. Reasons/prose never determine affected routes or status.

Runtime scope: main .layEm service blocks and .wrapFree prose. Alternative/bus
transport blocks, map SVG/positions, delay certificates, linked articles and
separate /tokudashi/tokudashi.html announcements are outside scope. The latter
is injected by /em/js/tokudashi.js. NORMAL excludes none of those separate notices.
The normal sentence means no reported delays >=15 minutes (also anticipated).
The normal page's inline loadDateTimeDisp replaces it outside 05:00--00:30 JST;
that exact normal page yields UNKNOWN outside the published service window.
Both normal/disrupted display clocks use Date.now(); abnormal createDate is not
documented as an update timestamp. updated_at remains None. No dedicated incident
validity/applicability fields were verified: timing UNKNOWN, no active periods.
Normal archives and live HTML verify clearing, but not same-event recovery.
Current abnormal live retrieval, a modern redirect during disruption and separate
delay-only/partial-only categories remain unverified. Unknown/malformed, redirect,
time-window and transition tests are synthetic. Evidence: fixtures/MEITETSU.md.
"""

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag
import httpx
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_URL: Final = "https://top.meitetsu.co.jp/em/"
_ID: Final = ProviderId("meitetsu")
_NORMAL: Final = "15分以上の列車の遅れはございません。"
_OUT_OF_HOURS: Final = "運行情報サービスの提供時間は、AM5:00～AM0:30です。"
# Preserve existing canonical scopes/IDs rather than splitting Yahoo's groups.
_ROUTES: Final = (
    ("nagoya_main", "line_4a34e1bd4cf5", ("名古屋本線",)),
    ("toyokawa", "line_1d5b5befe473", ("豊川線",)),
    ("nishio", "line_432cd30abf37", ("西尾線",)),
    ("gamagori", "line_6a4362997350", ("蒲郡線",)),
    ("mikawa", "line_7d2e158abcf2", ("三河線",)),
    ("toyota", "line_7666a844336e", ("豊田線",)),
    ("tokoname_airport", "line_6096e0a53bec", ("常滑線", "空港線")),
    ("chikko", "line_21bd01e99894", ("築港線",)),
    ("kowa_chita", "line_a75b30817184", ("河和線", "知多新線")),
    ("tsushima_bisai", "line_3bd54d7ebaec", ("津島線", "尾西線")),
    ("takehana_hashima", "line_12b330a48d24", ("竹鼻・羽島線",)),
    ("inuyama", "line_316bf1c335dc", ("犬山線",)),
    ("hiromi", "line_67eaaa1a3dd4", ("広見線",)),
    ("komaki", "line_8c96a5064f5a", ("小牧線",)),
    ("kakamigahara", "line_e3a6d0b3a7a9", ("各務原線",)),
    ("seto", "line_fa5360b12447", ("瀬戸線",)),
)
_SOURCE_IDS: Final = {
    name: LineId(f"jp:meitetsu:{suffix}")
    for _, suffix, names in _ROUTES for name in names
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Meitetsu official", source_page_url=HttpUrl(_URL),
    endpoints=(SourceEndpoint(
        url=_URL, method="GET", format=DataFormat.HTML,
        description="Japanese main service page, following HTTP redirects when supplied",
    ),),
    terms_url=HttpUrl("https://www.meitetsu.co.jp/site_policy/index.html"),
    additional_terms_urls=(HttpUrl("https://top.meitetsu.co.jp/em/train_notice.html"),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "General site terms section 2 restrict reproduction, processing, transmission "
        "and secondary use; no reuse grant was found. The service notice publishes "
        "delays of roughly 15 minutes or more affecting multiple trains, including "
        "anticipated disruption. Separate important announcements, transport "
        "arrangements, maps and linked articles are outside this provider's scope."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.SUSPENDED, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T15:38:31.538184+00:00"),
)


def _one(parent: BeautifulSoup | Tag, selector: str) -> Tag:
    matches = parent.select(selector)
    if len(matches) != 1:
        raise ParseError(f"Meitetsu element missing or duplicated: {selector}")
    return matches[0]


def _text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())


def _alert(
    line: Line, status: LineStatus, title: str, description: str, affected: tuple[LineId, ...],
) -> ServiceAlert:
    # A partially recognized list produces distinct scoped and unscoped alerts.
    identity = f"{_ID}:{status.value}:{title}:{description}:{affected}"
    return make_alert(
        line, status, title, description, affected_line_ids=affected,
        alert_id=sha256(identity.encode("utf-8")).hexdigest()[:24],
    )


def _parse(html: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    soup = BeautifulSoup(html, "html.parser")
    for hidden in soup.select("script, style, template, noscript"):
        hidden.decompose()
    if _text(_one(soup, "#wrapHeader h1.EM")) != "列車運行情報":
        raise ParseError("Not a Meitetsu service page")
    panel = _one(soup, "#wrapContents main .layEm")
    normal = panel.select("#descriptionText")
    if len(normal) > 1:
        raise ParseError("Duplicated Meitetsu normal notice")
    blocks = panel.select(".emInfo")
    free = panel.select(".wrapFree")
    if not normal and not blocks and not free:
        raise ParseError("Empty Meitetsu service panel")
    base = LineStatus.NORMAL
    source = "掲載なし"
    notices: list[tuple[LineStatus, ServiceAlert]] = []
    if normal:
        source = _text(normal[0])
        if not source:
            raise ParseError("Empty Meitetsu normal notice")
        if source == _NORMAL and "emLv00" in normal[0].get_attribute_list("class"):
            local = fetched_at.astimezone(ZoneInfo("Asia/Tokyo"))
            if 0 < local.hour < 5 or (local.hour == 0 and local.minute > 30):
                base, source = LineStatus.UNKNOWN, _OUT_OF_HOURS
        else:
            base = LineStatus.UNKNOWN
            notices.append((base, _alert(lines[0], base, source, source, ())))
    for block in blocks:
        title = _text(_one(block, ".emInfoTitle h2"))
        detail = _one(block, ".emInfoDetail")
        description = detail.get_text("\n", strip=True)
        if not title or not description:
            raise ParseError("Empty Meitetsu service block")
        levels = [c for c in block.get_attribute_list("class") if c.startswith("emLv")]
        if len(levels) != 1:
            raise ParseError("Missing or conflicting Meitetsu block class")
        level = levels[0]
        # These describe transport on other operators, not Meitetsu route state.
        if (level, title) in (("emLv03", "振替輸送"), ("emLv04", "バス代行輸送")):
            continue
        state = LineStatus.UNKNOWN
        field: str | None = None
        if (level, title) == ("emLv01", "運転見合せ"):
            state, field = LineStatus.SUSPENDED, "区間"
        elif (level, title) == ("emLv02", "遅延・一部運休"):
            state, field = LineStatus.ALERT, "路線"
        elif level == "emLv05":
            state = LineStatus.ALERT
        affected: list[LineId] = []
        unresolved = field is None
        if field is not None:
            rows = [row for row in detail.select("table.emTbl01 tr")
                    if len(row.select("th")) == 1 and _text(row.select("th")[0]) == field]
            if len(rows) != 1:
                raise ParseError(f"Missing or duplicated Meitetsu {field} field")
            cell = _one(rows[0], "td")
            items = cell.select("ul.emListLine > li" if field == "路線" else "ul.emListCmn > li")
            if not items:
                raise ParseError("Empty Meitetsu affected route list")
            for item in items:
                value = _text(item)
                if not value:
                    raise ParseError("Empty Meitetsu affected route")
                # A section item is route-name + whitespace + station interval.
                name, separator, section = value.partition(" ")
                if field == "区間" and (not separator or not section):
                    raise ParseError("Meitetsu section is missing its interval")
                identifier = _SOURCE_IDS.get(value if field == "路線" else name)
                if identifier is None:
                    unresolved = True
                elif identifier not in affected:
                    affected.append(identifier)
        if affected:
            notices.append((state, _alert(
                lines[0], state, title, description, tuple(affected),
            )))
        if unresolved:
            notices.append((LineStatus.UNKNOWN, _alert(
                lines[0], state, title, description, (),
            )))
    for notice in free:
        description = notice.get_text("\n", strip=True)
        if not description:
            raise ParseError("Empty Meitetsu supplemental notice")
        notices.append((LineStatus.UNKNOWN, _alert(
            lines[0], LineStatus.ALERT, "運行案内", description, (),
        )))
    if not normal and not notices:
        raise ParseError("No Meitetsu service state or notice")
    if normal and notices:
        base = LineStatus.UNKNOWN
    results: list[Line] = []
    for line in lines:
        relevant = [(state, alert) for state, alert in notices
                    if not alert.affected_line_ids or line.line_id in alert.affected_line_ids]
        targeted = [state for state, alert in relevant if alert.affected_line_ids]
        # Unscoped prose cannot erase a verified route-specific classification.
        states = targeted if targeted else [state for state, _ in relevant]
        state = combined_status(tuple(states) + (base,))
        results.append(snapshot(
            line, state, " / ".join(dict.fromkeys(a.title for _, a in relevant)) or source,
            fetched_at, alerts=tuple(a for _, a in relevant),
        ))
    return tuple(results)


class MeitetsuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        lines: list[Line] = []
        for _, suffix, names in _ROUTES:
            definition = LINE_CATALOG[LineId(f"jp:meitetsu:{suffix}")]
            lines.append(Line(
                line_id=definition.line_id, name=definition.name, operator=definition.operator,
                scope=definition.scope, provider_id=_ID, source_url=_URL, source_line_names=names,
            ))
        super().__init__(tuple(lines), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    def _route(self, key: str) -> Line:
        suffix = next(suffix for name, suffix, _ in _ROUTES if name == key)
        return self._line(suffix)

    @property
    def nagoya_main(self) -> Line:
        return self._route("nagoya_main")

    @property
    def toyokawa(self) -> Line:
        return self._route("toyokawa")

    @property
    def nishio(self) -> Line:
        return self._route("nishio")

    @property
    def gamagori(self) -> Line:
        return self._route("gamagori")

    @property
    def mikawa(self) -> Line:
        return self._route("mikawa")

    @property
    def toyota(self) -> Line:
        return self._route("toyota")

    @property
    def tokoname_airport(self) -> Line:
        return self._route("tokoname_airport")

    @property
    def chikko(self) -> Line:
        return self._route("chikko")

    @property
    def kowa_chita(self) -> Line:
        return self._route("kowa_chita")

    @property
    def tsushima_bisai(self) -> Line:
        return self._route("tsushima_bisai")

    @property
    def takehana_hashima(self) -> Line:
        return self._route("takehana_hashima")

    @property
    def inuyama(self) -> Line:
        return self._route("inuyama")

    @property
    def hiromi(self) -> Line:
        return self._route("hiromi")

    @property
    def komaki(self) -> Line:
        return self._route("komaki")

    @property
    def kakamigahara(self) -> Line:
        return self._route("kakamigahara")

    @property
    def seto(self) -> Line:
        return self._route("seto")
