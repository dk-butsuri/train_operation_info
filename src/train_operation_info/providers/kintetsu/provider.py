"""Kintetsu official service-alert summary.

Investigation: Both archive and public-source inspection of
https://www.kintetsu.jp/unkou/unkou.html and the route list at
https://www.kintetsu.co.jp/station/. Wayback captures 20260111081515,
20260213065943, 20260305143142 and 20260504000342 verify partial cancellation,
normal service, notices and suspension. Captures 20260601231132 and
20250820134746 verify notices without identified affected routes. A live
response on 2026-11-01 also verified Kyoto suspension. Only summary route,
status, cause and detail link are imported; detail prose/times are not fetched.
#servertime is the HTTP server's current clock, not an update timestamp.
Unlisted routes are normal only with a validated incident table or explicit
no-delay statement. The current publication threshold is 15 minutes; smaller
delays are outside this source's coverage. Delay labels have synthetic tests
only. Evidence and hashes: tests/fixtures/SOURCES.md.
"""

import re
from datetime import datetime
from typing import Final
from unicodedata import normalize
from urllib.parse import urljoin

from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import Line, LineStatus, Operator, OperatorId, ProviderId, ProviderMetadata, UsagePermission, DataFormat, SourceEndpoint
from ..base import SnapshotProvider, initial_lines, make_alert, snapshot

_URL: Final = "https://www.kintetsu.jp/unkou/unkou.html"
_ID: Final = ProviderId("kintetsu")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:kintetsu"), name="近畿日本鉄道")
_DEFINITIONS: Final = (
    ("namba", "難波線"), ("nara", "奈良線"),
    ("kyoto", "京都線"), ("kashihara", "橿原線"),
    ("keihanna", "けいはんな線"), ("osaka", "大阪線"),
    ("nagoya", "名古屋線"), ("minami_osaka", "南大阪線"),
    ("yoshino", "吉野線"), ("ikoma", "生駒線"),
    ("tenri", "天理線"), ("tawaramoto", "田原本線"),
    ("shigi", "信貴線"), ("yunoyama", "湯の山線"),
    ("suzuka", "鈴鹿線"), ("yamada", "山田線"),
    ("toba", "鳥羽線"), ("shima", "志摩線"),
    ("domyoji", "道明寺線"), ("nagano", "長野線"),
    ("gose", "御所線"), ("ikoma_cable", "生駒ケーブル"),
    ("nishi_shigi_cable", "西信貴ケーブル"),
)
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL, method="GET", format=DataFormat.HTML,
            description='Route status summary',
        ),
    ),
    provider_id=_ID, name="Kintetsu official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.kintetsu.co.jp/toppage/annai.html"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PRIVATE_USE_ONLY,
    usage_note="Both general site terms and the operation page require permission "
    "for uses beyond statutory personal private use. This records the reserved "
    "private-use exception, not a licence for public signage or automated reuse.",
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-01T14:57:00+00:00"),
)


def _summary(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".title")
    if title is None or title.get_text(strip=True) != "近鉄列車運行情報":
        raise ParseError("Kintetsu summary title is missing")
    parts: list[str] = []
    for node in title.next_siblings:
        if isinstance(node, Tag) and node.select_one(".caption") is not None:
            return BeautifulSoup("".join(parts), "html.parser")
        parts.append(str(node))
    raise ParseError("Kintetsu summary boundary is missing")


def _parse(html: str, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    summary = _summary(html)
    for script in summary.select("script, style"):
        script.decompose()
    normal_tag = next((tag for tag in summary.select("font") if normalize(
        "NFKC", tag.get_text(strip=True),
    ) == "現在は15分以上の列車の遅れはございません。"), None)
    headers = summary.select("thead")
    if len(headers) > 1:
        raise ParseError("Duplicate Kintetsu status header")
    statuses: dict[str, tuple[str, str]] = {}
    if headers:
        if normal_tag is not None:
            raise ParseError("Conflicting Kintetsu normal and incident summaries")
        header = headers[0]
        if [tag.get_text(strip=True) for tag in header.select("th")] != [
            "路線名", "状況", "原因", "詳細",
        ]:
            raise ParseError("Kintetsu status columns changed")
        table = header.find_next("table")
        if not isinstance(table, Tag):
            raise ParseError("Kintetsu incident table is missing")
        for row in table.select("tr"):
            cells = row.select(":scope > td")
            if len(cells) != 4:
                raise ParseError("Incomplete Kintetsu incident row")
            name, label, cause = (cell.get_text(strip=True) for cell in cells[:3])
            if name not in {line.name for line in lines} or name in statuses or not label:
                raise ParseError("Unknown or duplicate Kintetsu route, or missing status")
            button = cells[3].select_one("input[onclick]")
            onclick = button.get("onclick") if button is not None else None
            match = re.fullmatch(r"window\.open\('(?P<path>\./files/\d+\.html)'\);?", onclick) if isinstance(onclick, str) else None
            if match is None:
                raise ParseError("Kintetsu detail link is missing or changed")
            statuses[name] = label, f"{name}: {label}\n原因: {cause}\n詳細: {urljoin(_URL, match['path'])}"
        if not statuses:
            raise ParseError("Empty Kintetsu incident table")
        header_table = header.find_parent("table")
        table.decompose()
        if header_table is not None:
            header_table.decompose()
    if normal_tag is not None:
        normal_label = normal_tag.get_text(strip=True)
        normal_tag.decompose()
    else:
        normal_label = "掲載対象の運行情報なし"
    notices: list[str] = []
    for table in summary.select("table"):
        heading = table.select_one("b")
        if heading is None or not heading.get_text(strip=True).startswith("【"):
            raise ParseError("Unrecognized Kintetsu summary table")
        notices.append(table.get_text("\n", strip=True))
    if not statuses and normal_tag is None and not notices:
        raise ParseError("Kintetsu summary contains no recognized status or notice")
    shared = tuple(make_alert(
        lines[0], LineStatus.UNKNOWN, "近鉄: お知らせ", text, affected_line_ids=(),
    ) for text in notices if text)
    result: list[Line] = []
    for line in lines:
        label, description = statuses.get(line.name, (normal_label, ""))
        status = {
            "運転見合わせ": LineStatus.SUSPENDED,
            "一部運休": LineStatus.PARTIAL_SUSPENSION,
            "遅れ": LineStatus.DELAYED,
            "遅延": LineStatus.DELAYED,
            "お知らせ": LineStatus.ALERT,
        }.get(label, LineStatus.UNKNOWN) if description else (
            LineStatus.UNKNOWN if shared else LineStatus.NORMAL
        )
        alerts = shared + (() if not description else (
            make_alert(line, status, f"{line.name}: {label}", description),
        ))
        if shared and not description:
            label = "お知らせ（対象路線未特定）"
        result.append(snapshot(line, status, label, fetched_at, alerts=alerts))
    return tuple(result)


class KintetsuProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(initial_lines("jp:kintetsu", _ID, _URL, _OPERATOR, _DEFINITIONS), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _URL)
        response.raise_for_status()
        return _parse(response.content.decode("cp932"), self.lines, self._now())

    @property
    def namba(self) -> Line:
        return self._line("namba")

    @property
    def nara(self) -> Line:
        return self._line("nara")

    @property
    def kyoto(self) -> Line:
        return self._line("kyoto")

    @property
    def kashihara(self) -> Line:
        return self._line("kashihara")

    @property
    def keihanna(self) -> Line:
        return self._line("keihanna")

    @property
    def osaka(self) -> Line:
        return self._line("osaka")

    @property
    def nagoya(self) -> Line:
        return self._line("nagoya")

    @property
    def minami_osaka(self) -> Line:
        return self._line("minami_osaka")

    @property
    def yoshino(self) -> Line:
        return self._line("yoshino")

    @property
    def ikoma(self) -> Line:
        return self._line("ikoma")

    @property
    def tenri(self) -> Line:
        return self._line("tenri")

    @property
    def tawaramoto(self) -> Line:
        return self._line("tawaramoto")

    @property
    def shigi(self) -> Line:
        return self._line("shigi")

    @property
    def yunoyama(self) -> Line:
        return self._line("yunoyama")

    @property
    def suzuka(self) -> Line:
        return self._line("suzuka")

    @property
    def yamada(self) -> Line:
        return self._line("yamada")

    @property
    def toba(self) -> Line:
        return self._line("toba")

    @property
    def shima(self) -> Line:
        return self._line("shima")

    @property
    def domyoji(self) -> Line:
        return self._line("domyoji")

    @property
    def nagano(self) -> Line:
        return self._line("nagano")

    @property
    def gose(self) -> Line:
        return self._line("gose")

    @property
    def ikoma_cable(self) -> Line:
        return self._line("ikoma_cable")

    @property
    def nishi_shigi_cable(self) -> Line:
        return self._line("nishi_shigi_cable")
