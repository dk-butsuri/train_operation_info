"""Tokyo Metro official status: public JavaScript and official history inspection.

Reviewed 2026-11-02. /library/common/js/common.js fetches
https://www.tokyometro.jp/library/common/operation/status.json; the Japanese
lines supply status_info, contents, section and cause. The detail renderer at
https://www.tokyometro.jp/library/unkou/js/common.js displays those fields.
The numeric status has no verified abnormal mapping and is not used to infer
severity. Exact labels are used instead; narrative keywords never set status.
The live normal feed still contains old causes, so normal lines have no alerts.

Official /library/common/operation/history/ginza.json and /history/touzai.json
verify delay, partial-train delay, timetable disruption, suspension, turnbacks,
restart with disruption and normal recovery text. Disruption/restart remain
ALERT because they do not specify delay versus reduced service. The seven
distinct successful CDX captures (2018-2023) were located, but replay returned
HTTP 429. No archived abnormal status.json or same-incident live recovery is
claimed. Abnormal current-feed tests are explicitly synthetic, combining the
real feed structure with labels verified in official history. Unknown labels,
ended service, contradictions and faults are synthetic and remain UNKNOWN or
raise ParseError without replacing the previous snapshot.

status.json has no update timestamp. The screen's getNow clock is not a source
update, and history dates are not assigned to current status: updated_at=None.
Only nine current line snapshots are fetched; history, maps, positions, delay
certificates, and independent branch/direction status are excluded. Existing
Yahoo canonical IDs are reused. Evidence: tests/fixtures/TOKYO_METRO.md.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup
import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://www.tokyometro.jp/unkou/history/ginza.html"
_FEED_URL: Final = "https://www.tokyometro.jp/library/common/operation/status.json"
_ID: Final = ProviderId("tokyo_metro")
_NORMAL: Final = "現在、平常どおり運転しています。"
# Feed spelling, database spelling, source name, canonical ID (shared with Yahoo).
_ROUTES: Final = (
    (1, "ginza", "ginza", "銀座線", LineId("jp:tokyo_metro:line_be3b26a30ba3")),
    (2, "marunouchi", "marunouchi", "丸ノ内線", LineId("jp:tokyo_metro:line_fdee53402844")),
    (4, "hibiya", "hibiya", "日比谷線", LineId("jp:tokyo_metro:line_2e7158add59d")),
    (5, "touzai", "tozai", "東西線", LineId("jp:tokyo_metro:line_7e014bf48341")),
    (6, "chiyoda", "chiyoda", "千代田線", LineId("jp:tokyo_metro:line_6257bfc9d174")),
    (7, "yurakucho", "yurakucho", "有楽町線", LineId("jp:tokyo_metro:line_0c44b7d30049")),
    (9, "hanzoumon", "hanzomon", "半蔵門線", LineId("jp:tokyo_metro:line_23324b895d5a")),
    (10, "nanboku", "namboku", "南北線", LineId("jp:tokyo_metro:line_0e87c680e869")),
    (25, "fukutoshin", "fukutoshin", "副都心線", LineId("jp:tokyo_metro:line_5a2b7458bcb0")),
)
_STATES: Final = {
    "平常運転": LineStatus.NORMAL,
    "遅延": LineStatus.DELAYED,
    "一部列車遅延": LineStatus.DELAYED,
    "運転見合わせ": LineStatus.SUSPENDED,
    "折返し運転": LineStatus.PARTIAL_SUSPENSION,
    "ダイヤ乱れ": LineStatus.ALERT,
    "運転再開・ダイヤ乱れ": LineStatus.ALERT,
}
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_FEED_URL, method="GET", format=DataFormat.JSON,
            description='Current Japanese route status records',
        ),
    ),
    provider_id=_ID, name="Tokyo Metro official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.tokyometro.jp/terms/index.html"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note="The site terms require copyright-holder permission for reuse. "
    "The operation page separately prohibits unauthorized reproduction, copying "
    "and republication with altered formatting. No commercial reuse grant was "
    "found. The current page publishes actual or expected delays of five minutes "
    "or more and warns that its information may differ from actual operation.",
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T05:32:16+00:00"),
)


class _SourceLine(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    line_id: int
    name_alpha: str
    name_alpha_db: str
    line_name: str
    status: int
    status_info: str
    status_icon: str
    contents: str
    section: str
    cause: str


class _JapaneseStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    lines: list[_SourceLine]


class _SourceStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    jp: _JapaneseStatus


def _text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script, style"):
        node.decompose()
    return soup.get_text("\n", strip=True)


def _parse(content: bytes, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    source = _SourceStatus.model_validate_json(content)
    by_id = {item.line_id: item for item in source.jp.lines}
    if len(by_id) != len(source.jp.lines) or set(by_id) != {r[0] for r in _ROUTES}:
        raise ParseError("Missing, duplicate or unknown Tokyo Metro routes")
    result: list[Line] = []
    for line, (identifier, alpha, database, name, _) in zip(lines, _ROUTES):
        item = by_id[identifier]
        if (item.name_alpha, item.name_alpha_db, item.line_name) != (alpha, database, name):
            raise ParseError("Tokyo Metro route identity mismatch")
        label, body = item.status_info.strip(), _text(item.contents)
        if not label or not body or not item.status_icon.strip():
            raise ParseError("Empty Tokyo Metro status or description")
        status = _STATES.get(label, LineStatus.UNKNOWN)
        if status is LineStatus.NORMAL:
            if item.status_icon != "heijou" or item.status != 0 or body != _NORMAL:
                status = LineStatus.UNKNOWN
        elif item.status_icon == "heijou":
            status = LineStatus.UNKNOWN
        details = [body]
        if status is not LineStatus.NORMAL:
            for title, value in (("影響区間", item.section), ("原因", item.cause)):
                text = _text(value)
                if text:
                    details.append(f"{title}：{text}")
        alerts = () if status is LineStatus.NORMAL else (
            make_alert(line, status, f"{name} {label}", "\n".join(details)),
        )
        result.append(snapshot(line, status, label, fetched_at, alerts=alerts,
                               source_line_names=(name,)))
    return tuple(result)


class TokyoMetroProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None,
        snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[identifier].create_line(
                _ID, f"https://www.tokyometro.jp/unkou/history/{alpha}.html",
            ) for _, alpha, _, _, identifier in _ROUTES
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _FEED_URL)
        response.raise_for_status()
        return _parse(response.content, self.lines, self._now())

    @property
    def ginza(self) -> Line:
        return self._line("line_be3b26a30ba3")

    @property
    def marunouchi(self) -> Line:
        return self._line("line_fdee53402844")

    @property
    def hibiya(self) -> Line:
        return self._line("line_2e7158add59d")

    @property
    def tozai(self) -> Line:
        return self._line("line_7e014bf48341")

    @property
    def chiyoda(self) -> Line:
        return self._line("line_6257bfc9d174")

    @property
    def yurakucho(self) -> Line:
        return self._line("line_0c44b7d30049")

    @property
    def hanzomon(self) -> Line:
        return self._line("line_23324b895d5a")

    @property
    def namboku(self) -> Line:
        return self._line("line_0e87c680e869")

    @property
    def fukutoshin(self) -> Line:
        return self._line("line_5a2b7458bcb0")
