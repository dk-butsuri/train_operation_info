"""Odakyu's three route status cards from its official browser application.

Investigation: public JavaScript reverse engineering AND archived API responses,
2026-11-03. Page: https://traininfo.odakyu-rt.jp/train_status ; script:
https://traininfo.odakyu-rt.jp/assets/index-yuMM9dEt.js . Axios configuration
provides the public browser API header. JP maps influence_block_state blocks
1..17 to Odawara, 18..23 to Enoshima, 24..26 to Tama; 27..28 are outside
these cards. up_state/down_state 0=normal, 1=delay, 2=no operation. A proper
subset of stopped blocks is PARTIAL_SUSPENSION; all blocks stopped is
SUSPENDED, matching JP's labels. This does not distinguish cancellations
from temporary suspension. Unknown codes are UNKNOWN, malformed structure
raises ParseError. Nonempty block arrays must cover all 26 route blocks.

Archived API https://web.archive.org/web/20250730090750id_/
https://d6oynijiy33tb.cloudfront.net/service/status_detail confirms Enoshima
partial suspension; 20251124012021 confirms Odawara suspension and Enoshima
delay; 20260728134022 confirms delays; 20261014200025 confirms empty normal
state. Full-line suspension, maintenance and unknown-state tests are synthetic.
Full URLs, UTC timestamps, hashes and unmodified fixtures: fixtures/ODAKYU.md.

Only route cards and associated service details are covered. news_latest is a
separate news tab, not imported. Special-service text and overall announcements
without an established route remain unscoped. No narrative classification or
long-term filtering. Timing remains UNKNOWN: current applicability of every
block code has not been independently established. update_time is the detail
update instant; the web page's clock uses new Date() and is never substituted.
Maintenance statuses 21/22 and unknown summary codes suppress normal results.
The route cards' feed scope does not establish overnight service availability.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Final
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_URL: Final = "https://traininfo.odakyu-rt.jp/train_status"
_API: Final = "https://d6oynijiy33tb.cloudfront.net/service/status_detail"
_ID: Final = ProviderId("odakyu")
_ROUTES: Final = (
    ("odawara", "小田原線", LineId("jp:odakyu:line_fbb4645c43db"), 1, 17),
    ("enoshima", "江ノ島線", LineId("jp:odakyu:line_5f3c44bd632d"), 18, 23),
    ("tama", "多摩線", LineId("jp:odakyu:line_cf199b49d179"), 24, 26),
)
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="Odakyu official", source_page_url=HttpUrl(_URL),
    endpoints=(
        SourceEndpoint(url=_URL, method="GET", format=DataFormat.HTML,
                       description="Discover the current browser application module"),
        SourceEndpoint(url="https://traininfo.odakyu-rt.jp/assets/{filename}",
                       method="GET", format=DataFormat.JAVASCRIPT, is_template=True,
                       description="Module script from the official page; public API configuration"),
        SourceEndpoint(url=_API, method="GET", format=DataFormat.JSON,
                       description="Route status; x-api-key is the public header in the browser module"),
    ),
    terms_url=HttpUrl("https://www.odakyu.jp/policy/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note="The official site's copyright terms prohibit reuse without prior permission. "
    "The policy names odakyu.jp; separate API reuse permission was not found. "
    "This metadata grants no reuse licence. The operation page reports delays of "
    "10 minutes or more, including expected delays, and disclaims timeliness.",
    reviewed_at=datetime.fromisoformat("2026-11-02T15:38:38+00:00"),
)


class _Source(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Summary(_Source):
    status: int
    message: str
    description: str


class _Block(_Source):
    block_state: int
    up_state: int
    down_state: int


class _Detail(_Source):
    update_time: AwareDatetime
    hp_title: str
    hp_status: str
    hp_influence_status_whole: str
    hp_influence_status_odawara: str
    hp_influence_status_enoshima: str
    hp_influence_status_tama: str
    express_service_status_description: str
    chiyoda_stop_flg: int
    hp_transfer_info: str
    hp_remarks: str

    def route_messages(self) -> tuple[str, ...]:
        return (self.hp_influence_status_odawara, self.hp_influence_status_enoshima,
                self.hp_influence_status_tama)


class _Occurrence(_Source):
    occurrence_start_station_code: str
    occurrence_end_station_code: str
    occurrence_at: AwareDatetime | None
    trouble_reason: str
    influence_block_start_station_code: str
    influence_block_end_station_code: str
    is_influence_all_line: bool


class _Payload(_Source):
    status: list[_Summary]
    influence_block_state: list[_Block]
    occurrence_location_info: list[_Occurrence]
    train_service_status_detail: _Detail | None = None


def _parse(data: _Payload, lines: tuple[Line, ...], now: datetime) -> tuple[Line, ...]:
    blocks = {block.block_state: block for block in data.influence_block_state}
    if len(blocks) != len(data.influence_block_state):
        raise ParseError("Duplicate Odakyu block")
    if blocks and not set(range(1, 27)).issubset(blocks):
        raise ParseError("Incomplete Odakyu route blocks")
    if not blocks and data.train_service_status_detail is not None:
        raise ParseError("Odakyu service detail has no route blocks")
    if blocks and data.train_service_status_detail is None:
        raise ParseError("Odakyu route blocks have no service detail")
    detail = data.train_service_status_detail
    summary = data.status[-1] if data.status else None
    summary_unknown = summary is not None and summary.status not in range(4, 15)
    unknown_blocks = any(code not in range(1, 29) for code in blocks)
    general: list[str] = []
    if summary is not None:
        general.extend((f"status={summary.status}", summary.message, summary.description))
    if detail is not None:
        general.extend((detail.hp_title, detail.hp_status, detail.hp_transfer_info, detail.hp_remarks))
    general.extend(item.model_dump_json() for item in data.occurrence_location_info)
    body = "\n".join(text for text in general if text)
    route_messages = detail.route_messages() if detail else ("", "", "")
    special = "\n".join(text for text in (
        detail.hp_influence_status_whole, detail.express_service_status_description,
        f"chiyoda_stop_flg={detail.chiyoda_stop_flg}" if detail.chiyoda_stop_flg else "",
    ) if text) if detail else ""
    result: list[Line] = []
    route_states: list[LineStatus] = []
    for _, _, _, start, end in _ROUTES:
        relevant = [blocks[code] for code in range(start, end + 1)] if blocks else []
        if summary_unknown or unknown_blocks or any(
            b.up_state not in (0, 1, 2) or b.down_state not in (0, 1, 2) for b in relevant
        ):
            state = LineStatus.UNKNOWN
        else:
            stopped = sum(b.up_state == 2 or b.down_state == 2 for b in relevant)
            if stopped:
                state = (LineStatus.SUSPENDED if stopped == len(relevant)
                         else LineStatus.PARTIAL_SUSPENSION)
            elif any(b.up_state == 1 or b.down_state == 1 for b in relevant):
                state = LineStatus.DELAYED
            else:
                state = LineStatus.NORMAL
        route_states.append(state)
    # Overall/special-service prose is not evidence that every route is affected.
    unscoped = special
    scope_unknown = summary_unknown or unknown_blocks
    if scope_unknown or (body and all(state is LineStatus.NORMAL for state in route_states)):
        unscoped = "\n".join(text for text in (body, special) if text)
    if scope_unknown:
        unscoped += "\n" + "\n".join(text for text in route_messages if text)
        unscoped += "\n" + "\n".join(b.model_dump_json() for b in data.influence_block_state
                                        if b.block_state not in range(1, 29))
    shared: tuple[ServiceAlert, ...] = () if not unscoped else (make_alert(
        lines[0], LineStatus.UNKNOWN if scope_unknown else LineStatus.ALERT,
        "小田急線: 案内（対象路線未特定）", unscoped, affected_line_ids=(),
    ),)
    for line, (_, name, _, start, end), state, route_message in zip(lines, _ROUTES, route_states, route_messages):
        alerts = shared
        if state is LineStatus.NORMAL and route_message:
            state = LineStatus.ALERT
        if state is not LineStatus.NORMAL and not scope_unknown:
            alerts += (make_alert(line, state, f"{name}: 運行情報",
                                  "\n".join(t for t in (route_message, body) if t) or "未確認の状態コード"),)
        elif shared:
            state = LineStatus.UNKNOWN
        raw_status = "\n".join(b.model_dump_json() for b in data.influence_block_state
                               if start <= b.block_state <= end or b.block_state not in range(1, 29))
        if summary:
            raw_status += "\n" + summary.model_dump_json()
        result.append(snapshot(
            line, state, raw_status or "平常運転", now, alerts=alerts,
            updated_at=detail.update_time if detail else None, source_line_names=(name,),
        ))
    return tuple(result)


class OdakyuProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(LINE_CATALOG[route[2]].create_line(_ID, _URL) for route in _ROUTES),
                         client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        page = await self._get(client, _URL)
        page.raise_for_status()
        scripts = BeautifulSoup(page.content, "html.parser").select('script[type="module"][src]')
        if len(scripts) != 1:
            raise ParseError("Odakyu browser module is missing or ambiguous")
        script_url = urljoin(_URL, str(scripts[0]["src"]))
        parts = urlsplit(script_url)
        if (parts.scheme != "https" or parts.netloc != "traininfo.odakyu-rt.jp"
                or not parts.path.startswith("/assets/") or not parts.path.endswith(".js")
                or parts.query or parts.fragment):
            raise ParseError("Unexpected Odakyu module URL")
        script = await self._get(client, script_url)
        script.raise_for_status()
        # Match the complete published Axios configuration for this fixed API.
        configs = re.findall(
            r'baseURL:"https://d6oynijiy33tb\.cloudfront\.net",headers:\{"x-api-key":"([^"\r\n]+)"\}',
            script.text,
        )
        if len(configs) != 1:
            raise ParseError("Odakyu public browser API configuration changed")
        response = await self._get(client, _API, headers={"x-api-key": configs[0]})
        response.raise_for_status()
        return _parse(_Payload.model_validate_json(response.content), self.lines, self._now())

    @property
    def odawara(self) -> Line:
        return self._line("line_fbb4645c43db")

    @property
    def enoshima(self) -> Line:
        return self._line("line_5f3c44bd632d")

    @property
    def tama(self) -> Line:
        return self._line("line_cf199b49d179")
