"""JR Central conventional lines: public HTML/JavaScript reverse engineering.

Sources: https://traininfo.jr-central.co.jp/zairaisen/index.html and js/
contents.js, index.js, status.js, train_information.js, common.js; Japanese
data/locales/ja/hp_koteimoji_master.json and data/hp_senku_master_ja.json.
Live delay then normal data (ono 60742 then 60744) and official history
0000000000060739--0000000000060741 verify delays (0006) and clearing;
status.js resolveLineInfoStatusText and Japanese locale verify
0001--0004 suspension, 0005 combined delays/cancellations, 0007 cancellations,
0009 normal. Combined/unspecified cancellations are ALERT: extent is unknown.
Unknown codes remain UNKNOWN. No classification uses incident prose.
index.js and train_information.js show no events as normal; serviceJotai
other than 0 hides the UI (maintenance), so old data must not become normal.
Only the 13 conventional panels (senkuKbn=1) are covered. Separate express
services, notice/oshirase.json, transfers, images, PDFs and train positions
are excluded. Mixed notices within message_info/events are retained.
No dedicated applicability/validity fields were verified: timing UNKNOWN,
active_from/active_until None. create_time is a date, not an update timestamp;
the page header uses HTTP/current time. updated_at remains None.
Actual suspension and cancellation captures are unverified; their tests are
synthetic. Exact sources/hashes and classification limits:
tests/fixtures/JRCENTRAL.md and jrcentral_manifest.json.
Shinkansen detail JSON currently redirects to the corporate homepage, and
the official homepage summary returns an empty object; both are excluded.
"""

from datetime import datetime
from pathlib import Path
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot

_BASE: Final = "https://traininfo.jr-central.co.jp/zairaisen/"
_URL: Final = _BASE + "index.html"
_SERVICE: Final = _BASE + "data/hp_service_jotai_kanri.json"
_OPERATION: Final = _BASE + "data/trainInfo/json/unkou.json"
_ID: Final = ProviderId("jrcentral")
# Source name -> public property, canonical identity. Central's Chuo panel
# spans both Yahoo sections, so it needs its own canonical definition.
_ROUTES: Final = {
    "東海道線(熱海～豊橋)": ("tokaido_atami_toyohashi", LineId("jp:jr_central:line_6fc336cf9ff1")),
    "東海道線(豊橋～米原)": ("tokaido_toyohashi_maibara", LineId("jp:jr_central:line_f8d0edf56619")),
    "中央線": ("chuo", LineId("jp:jr_central:chuo_nagoya_shiojiri")),
    "関西線": ("kansai", LineId("jp:jr_central:line_e7dbe9beead2")),
    "紀勢線": ("kisei", LineId("jp:jr_central:line_bbddf7bbb005")),
    "高山線": ("takayama", LineId("jp:jr_central:line_c41689a43fa0")),
    "武豊線": ("taketoyo", LineId("jp:jr_central:line_d1cf7125827b")),
    "飯田線": ("iida", LineId("jp:jr_central:line_fe938e24f4f9")),
    "太多線": ("taita", LineId("jp:jr_central:line_1b813d15693b")),
    "御殿場線": ("gotemba", LineId("jp:jr_central:line_d7896ac10524")),
    "身延線": ("minobu", LineId("jp:jr_central:line_38a7c5d61048")),
    "参宮線": ("sangu", LineId("jp:jr_central:line_110504ba73d0")),
    "名松線": ("meisho", LineId("jp:jr_central:line_856f2cc50a8c")),
}
_EXCLUDED: Final = frozenset({
    "しなの", "ひだ", "ひだ（大阪方面）", "南紀", "みえ", "しらさぎ", "伊那路",
    "ふじかわ", "ふじさん", "その他・ホームライナーなど", "美濃赤坂線", "伊勢鉄道",
})
_STATES: Final = {
    "0001": (LineStatus.SUSPENDED, "運転見合わせ"),
    "0002": (LineStatus.SUSPENDED, "運転見合わせ"),
    "0003": (LineStatus.SUSPENDED, "運転見合わせ"),
    "0004": (LineStatus.SUSPENDED, "運転見合わせ"),
    "0005": (LineStatus.ALERT, "遅れ・運休あり"),
    "0006": (LineStatus.DELAYED, "遅れあり"),
    "0007": (LineStatus.ALERT, "運休あり"),
    "0009": (LineStatus.NORMAL, "平常運転"),
}
_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="JR Central official", source_page_url=HttpUrl(_URL),
    endpoints=(
        SourceEndpoint(url=_SERVICE, method="GET", format=DataFormat.JSON,
                       description="Maintenance gate; only serviceJotai=0 exposes current information"),
        SourceEndpoint(url=_OPERATION, method="GET", format=DataFormat.JSON,
                       description="Conventional-line events and Japanese delivery messages; express entries excluded"),
    ),
    terms_url=HttpUrl("https://jr-central.co.jp/policy/"),
    additional_terms_urls=(HttpUrl(_BASE + "faq.html"),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note="The website policy prohibits unapproved reproduction, modification, reuse and public transmission except where permitted by copyright law. The service FAQ separately prohibits unauthorized reproduction/copying. No reuse licence was found. Conventional notices cover roughly 10-minute delays and anticipated delays; separate notices and express services are outside this provider's scope.",
    reviewed_at=datetime.fromisoformat("2026-11-02T15:43:07.116206+00:00"),
)


class _Input(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Service(_Input):
    serviceJotai: str


class _Name(_Input):
    lang: str
    name: str


class _Message(_Input):
    lang: str
    message: str


class _Delivery(_Input):
    trainline: list[_Name] = Field(min_length=1)
    delivery_msg: list[_Message] = Field(min_length=1)


class _Event(_Input):
    no: str = Field(min_length=1)
    imp_line: list[_Name] = Field(min_length=1)
    status_id: str = Field(min_length=1)
    status: list[_Name] = Field(min_length=1)


class _Operation(_Input):
    check: str
    events: list[_Event] | None
    message_info: list[_Delivery] | None


def _japanese(values: list[_Name]) -> str:
    names = [value.name for value in values if value.lang == "ja"]
    if len(names) != 1 or not names[0].strip():
        raise ParseError("Missing or ambiguous JR Central Japanese name")
    return names[0]


def _message(values: list[_Message]) -> str:
    messages = [value.message for value in values if value.lang == "ja"]
    if len(messages) != 1 or not messages[0].strip():
        raise ParseError("Missing or ambiguous JR Central Japanese message")
    return messages[0]


def _validate_route(name: str) -> None:
    if name not in _ROUTES and name not in _EXCLUDED:
        raise ParseError(f"Unregistered JR Central route: {name}")


def _parse(data: _Operation, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    if data.check not in ("0", "1"):
        raise ParseError("Unknown JR Central availability flag")
    if data.check == "0" and (data.events or data.message_info):
        raise ParseError("JR Central normal flag conflicts with event data")
    if data.check == "1" and (data.events is None or data.message_info is None):
        raise ParseError("JR Central incident flag requires event/message arrays")
    numbers: set[str] = set()
    events: dict[str, list[_Event]] = {}
    messages: dict[str, list[str]] = {}
    for event in data.events or []:
        if event.no in numbers:
            raise ParseError("Duplicate JR Central event number")
        numbers.add(event.no)
        name = _japanese(event.imp_line)
        _validate_route(name)
        _japanese(event.status)
        events.setdefault(name, []).append(event)
    for delivery in data.message_info or []:
        name = _japanese(delivery.trainline)
        _validate_route(name)
        messages.setdefault(name, []).append(_message(delivery.delivery_msg))
    result: list[Line] = []
    for name, line in zip(_ROUTES, lines):
        route_events = events.get(name, [])
        route_messages = messages.get(name, [])
        # The official detail page pairs messages and events per route/index.
        if len(route_events) != len(route_messages):
            raise ParseError(f"Unpaired JR Central events/messages: {name}")
        states: list[LineStatus] = []
        labels: list[str] = []
        alerts: list[ServiceAlert] = []
        for event, description in zip(route_events, route_messages):
            raw_label = _japanese(event.status)
            state, label = _STATES.get(event.status_id, (LineStatus.UNKNOWN, raw_label))
            states.append(state)
            labels.append(f"{event.status_id}: {label} ({raw_label})")
            alerts.append(make_alert(line, state, f"{name}: {label}", description))
        status = combined_status(tuple(states)) if states else LineStatus.NORMAL
        result.append(snapshot(line, status, " / ".join(labels) if labels else "平常運転",
                               fetched_at, alerts=tuple(alerts), source_line_names=(name,)))
    return tuple(result)


class JrCentralProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(self, *, client: httpx.AsyncClient | None = None,
                 snapshot_dir: str | Path | None = None) -> None:
        super().__init__(tuple(LINE_CATALOG[identifier].create_line(_ID, _URL)
                               for _, identifier in _ROUTES.values()),
                         client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        service = await self._get(client, _SERVICE)
        service.raise_for_status()
        if _Service.model_validate_json(service.content.decode("utf-8-sig")).serviceJotai != "0":
            raise ParseError("JR Central service is unavailable or under maintenance")
        response = await self._get(client, _OPERATION)
        response.raise_for_status()
        return _parse(_Operation.model_validate_json(response.content.decode("utf-8-sig")), self.lines, self._now())

    def _route(self, name: str) -> Line:
        identifier = _ROUTES[name][1]
        return next(line for line in self.lines if line.line_id == identifier)

    @property
    def tokaido_atami_toyohashi(self) -> Line:
        return self._route("東海道線(熱海～豊橋)")

    @property
    def tokaido_toyohashi_maibara(self) -> Line:
        return self._route("東海道線(豊橋～米原)")

    @property
    def chuo(self) -> Line:
        return self._route("中央線")

    @property
    def kansai(self) -> Line:
        return self._route("関西線")

    @property
    def kisei(self) -> Line:
        return self._route("紀勢線")

    @property
    def takayama(self) -> Line:
        return self._route("高山線")

    @property
    def taketoyo(self) -> Line:
        return self._route("武豊線")

    @property
    def iida(self) -> Line:
        return self._route("飯田線")

    @property
    def taita(self) -> Line:
        return self._route("太多線")

    @property
    def gotemba(self) -> Line:
        return self._route("御殿場線")

    @property
    def minobu(self) -> Line:
        return self._route("身延線")

    @property
    def sangu(self) -> Line:
        return self._route("参宮線")

    @property
    def meisho(self) -> Line:
        return self._route("名松線")
