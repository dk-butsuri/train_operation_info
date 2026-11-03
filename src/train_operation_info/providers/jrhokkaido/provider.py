"""JR Hokkaido official 列車運行情報: public JSON + JavaScript reverse engineering
(no incident archive).

Source: https://www3.jrhokkaido.co.jp/webunkou/index.html, its include
call_goriyo.html (service usage notes loaded into the top page) and
call_common_header.html, and the per-area status JSON at
json/area/area_{02,03,04,05}.json. The JSON shape and the senku(line-segment)
id -> senkuStatus field mapping were confirmed from the loader scripts
js/top.js, js/common_area_operation.js, js/area.js, js/common_area_senku.js,
js/senku.js and js/senku_information_display.js, and from
json/master/senku_name_master.json (the official per-senku display name used
below as source_line_names).

Status codes come directly from getIconImgElement()/OPERATION_STATUS_*_REMARKS
in common_area_operation.js: 0 = no 30+ minute delay/suspension notice
(NORMAL); 1 = cancellation, 30+ minute delay, or operation suspension,
undistinguishable from the code alone (ALERT); any other value (the live
service used 2, meaning "サービス時間外", outside the 5:00-24:00 service
window stated in call_goriyo.html) is UNKNOWN. No status is ever derived from
free text.

Each area_XX.json independently reports ITS OWN area's senku ids using one
fixed 16-key senkuStatus schema (express/airport/hakochise/hakodateLiner/
hakodate/gakuen/sekisho/muroran/nemuro/hidaka/soya/sekihoku/furano/rumoi/
senmo/hanasaki); keys that are not one of that area's own senku ids hold
unrelated placeholder values and are never read for that area. This was
verified live by fetching all five area_0{1..5}.json endpoints on 2026-11-03:
area_01 (Sapporo suburbs, senku 01-04) and area_02 (Central Hokkaido,
senku 05-10) always reported identical values for the four field names they
publish in common (express/airport/hakochise/gakuen -- per
common_area_senku.js these are the SAME physical service cross-listed on both
area pages), while area_04's own soya/express differed from every other
area's, confirming the data is genuinely per area rather than one shared
object. Only area_02/03/04/05 are fetched here; area_01 contributes nothing
not already present in area_02.

json/master/senku_name_master.json confirms that 学園都市線(senku 04/08,
field gakuen)/日高線(10, hidaka)/宗谷線(15, soya)/石北線(16, sekihoku)/富良野線
(17, furano)/石勝線(20, sekisho)/釧網線(23, senmo)/根室線（花咲線）(22,
hanasaki) each name exactly one physical line already in the common catalog,
so those eight reuse their existing LineId (LineScope.LINE). エアポート
(02/06, airport)/函館・千歳線(03/07, hakochise)/室蘭線(09, muroran)/はこだて
ライナー(12, hakodateLiner)/函館線(13, hakodate)/根室線(21, nemuro) are each
one official reporting unit that, per the loader scripts and the official
area-to-senku map, covers more physical mileage than one catalog segment, or
whose exact catalog boundary could not be confirmed from the published data
(JR Hokkaido does not publish a status per split 千歳線/函館本線/室蘭本線/
根室本線 segment the way the common catalog splits them). Like
providers/jrkyushu's area panels, these six become new GROUP LineIds
(jp:jr_hokkaido:*_group) and are never aliased to, or treated as equivalent
to, any one of those catalog segments; their alerts keep affected_line_ids=().

特急列車 (senku 01/05/11/14/19, field "express") is a per-area limited-express
status with no corresponding physical line in the catalog; it is out of
scope, matching JR East's exclusion of 特急列車. 北海道新幹線 (senku 24,
areaStatus.shin) has no area_06.json of its own (confirmed live: the URL
returns the site's own "ページが存在しません" page) and has no LineId in the
common catalog; it is out of scope. rumoi is a schema field with no current
senku id (the former 留萌本線 section was discontinued) and is validated but
never read. 道南いさりび鉄道との直通列車はcall_goriyo.htmlにより対象外と明記
されている.

Only data.today is read; data.tomorrow (the forecast for the next calendar
day) is validated for structure but never surfaced, since this library models
current status only. The top-level "time" field ends in 現在 the same way as
JR East's region pages and is treated the same way: not a notice update time,
so updated_at stays None unless a specific notice supplies one. Each gaikyo
entry's own "time" (for example "2026年11月02日 15時39分現在", captured live
during a real 宗谷線 bear-collision suspension) is a per-notice timestamp,
distinct from the always-empty placeholder entry that is published whenever
there is nothing to report
({"time": "", "title": "", "honbun": "現在、遅れに関する情報はありません。"})
and that is never surfaced as an alert. A real notice (non-empty title)
supplies updated_at and alert text only for the lines whose official area has
eikyo[area] == 1 on that notice, and only while that same line's own senku
status is 1; status 1 without a matching notice falls back to the fixed
OPERATION_STATUS_1_REMARKS text, and keeps updated_at=None. areaComments
items are validated only for the "comment" field actually used elsewhere on
the site (extra fields ignored) because every captured response, including
the live incident below, had an empty areaComments array; a populated example
was not found. Long-term closures are not structurally separated anywhere in
this feed (no separate flag file or section was found, unlike JR Kyushu/
JR West), so NORMAL does not guarantee the absence of a long-running
suspension that is reported only outside the fields read here. timing stays
UNKNOWN and active_from/active_until stay None; no validity-period field was
found.

Live area_02/03/04/05 JSON was fetched on 2026-11-02/03 JST: area_02 (道央),
area_03 (道南) and area_05 (道東) were NORMAL throughout. area_04 (道北)
genuinely showed soya=1 for both "today" and the forecast "tomorrow", a real
suspension on 宗谷線 (音威子府～稚内) caused by a train/bear collision on
2026-10-30, with the notice text captured verbatim. No other live incident
(学園都市線/日高線/エアポート/函館・千歳線/室蘭線/はこだてライナー/函館線/
石北線/富良野線/石勝線/根室線/花咲線/釧網線) was observed; their ALERT /
UNKNOWN(status 2) / recovery / malformed-schema paths are synthetic mutations
of the real captures. See tests/fixtures/JRHOKKAIDO.md and
jrhokkaido_manifest.json for evidence, hashes and the usage-terms review.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Final, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    LINE_CATALOG, DataFormat, Line, LineId, LineScope, LineStatus, ProviderId,
    ProviderMetadata, ServiceAlert, SourceEndpoint, UsagePermission,
)
from ..base import SnapshotProvider, make_alert, snapshot

_BASE: Final = "https://www3.jrhokkaido.co.jp/webunkou/"
_ID: Final = ProviderId("jrhokkaido")
_HEADERS: Final = {"Accept-Language": "ja,en;q=0.8"}

_AreaKey = Literal["doo", "donan", "dohoku", "doto"]

_AREA_URLS: Final[tuple[tuple[_AreaKey, str], ...]] = (
    ("doo", _BASE + "json/area/area_02.json"),
    ("donan", _BASE + "json/area/area_03.json"),
    ("dohoku", _BASE + "json/area/area_04.json"),
    ("doto", _BASE + "json/area/area_05.json"),
)

_REMARK_1: Final = "運休・３０分以上の遅延・運転見合わせが発生"
_REMARK_2: Final = "サービス時間外"


class _Eikyo(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    spo: int
    doo: int
    donan: int
    dohoku: int
    doto: int


class _Gaikyo(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    time: str
    title: str
    honbun: str
    eikyo: _Eikyo


class _AreaComment(BaseModel):
    # Every captured response has an empty areaComments array; only the field
    # used elsewhere on the site (comment) is validated. See module docstring.
    model_config = ConfigDict(strict=True, extra="ignore")
    comment: str


class _AreaStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    spo: int
    doo: int
    donan: int
    dohoku: int
    doto: int
    shin: int


class _SenkuStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    express: int
    airport: int
    hakochise: int
    hakodateLiner: int
    hakodate: int
    gakuen: int
    sekisho: int
    muroran: int
    nemuro: int
    hidaka: int
    soya: int
    sekihoku: int
    furano: int
    rumoi: int
    senmo: int
    hanasaki: int


class _Day(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    dateText: str
    areaStatus: _AreaStatus
    gaikyo: tuple[_Gaikyo, ...]
    areaComments: tuple[_AreaComment, ...]
    senkuStatus: _SenkuStatus


class _AreaPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    time: str
    today: _Day
    tomorrow: _Day


class _FieldGetter:
    def __init__(self, name: str) -> None:
        self._name = name

    def __call__(self, status: _SenkuStatus) -> int:
        if self._name == "airport":
            return status.airport
        if self._name == "hakochise":
            return status.hakochise
        if self._name == "hakodateLiner":
            return status.hakodateLiner
        if self._name == "hakodate":
            return status.hakodate
        if self._name == "gakuen":
            return status.gakuen
        if self._name == "sekisho":
            return status.sekisho
        if self._name == "muroran":
            return status.muroran
        if self._name == "nemuro":
            return status.nemuro
        if self._name == "hidaka":
            return status.hidaka
        if self._name == "soya":
            return status.soya
        if self._name == "sekihoku":
            return status.sekihoku
        if self._name == "furano":
            return status.furano
        if self._name == "senmo":
            return status.senmo
        if self._name == "hanasaki":
            return status.hanasaki
        raise ParseError(f"Unknown JR Hokkaido senku field: {self._name}")


def _eikyo_flag(eikyo: _Eikyo, area: _AreaKey) -> int:
    if area == "doo":
        return eikyo.doo
    if area == "donan":
        return eikyo.donan
    if area == "dohoku":
        return eikyo.dohoku
    return eikyo.doto


_NOTICE_TIME: Final = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})時(\d{1,2})分現在")


def _parse_notice_time(value: str) -> datetime:
    match = _NOTICE_TIME.fullmatch(value)
    if match is None:
        raise ParseError(f"Invalid JR Hokkaido notice time: {value!r}")
    year, month, day, hour, minute = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Tokyo"))
    except ValueError as exc:
        raise ParseError(f"Invalid JR Hokkaido notice date: {value!r}") from exc


@dataclass(frozen=True)
class _Senku:
    attribute: str
    line_id: LineId
    senku_id: str
    area: _AreaKey
    field: str
    official_name: str


_SENKU: Final[tuple[_Senku, ...]] = (
    _Senku("gakuen_toshi", LineId("jp:jr_hokkaido:line_1b3f7157a97f"), "08", "doo", "gakuen", "学園都市線"),
    _Senku("hidaka", LineId("jp:jr_hokkaido:line_d2d4151ea5a8"), "10", "doo", "hidaka", "日高線"),
    _Senku("airport", LineId("jp:jr_hokkaido:airport_group"), "06", "doo", "airport", "エアポート"),
    _Senku("hakodate_chitose", LineId("jp:jr_hokkaido:hakodate_chitose_group"), "07", "doo", "hakochise", "函館・千歳線"),
    _Senku("muroran", LineId("jp:jr_hokkaido:muroran_group"), "09", "doo", "muroran", "室蘭線"),
    _Senku("hakodate_liner", LineId("jp:jr_hokkaido:hakodate_liner_group"), "12", "donan", "hakodateLiner", "はこだてライナー"),
    _Senku("hakodate_line", LineId("jp:jr_hokkaido:hakodate_line_group"), "13", "donan", "hakodate", "函館線"),
    _Senku("soya", LineId("jp:jr_hokkaido:line_d3463a409618"), "15", "dohoku", "soya", "宗谷線"),
    _Senku("sekihoku", LineId("jp:jr_hokkaido:line_903b6ae2bcf1"), "16", "dohoku", "sekihoku", "石北線"),
    _Senku("furano", LineId("jp:jr_hokkaido:line_ea3437497425"), "17", "dohoku", "furano", "富良野線"),
    _Senku("sekisho", LineId("jp:jr_hokkaido:line_6664f6717ccf"), "20", "doto", "sekisho", "石勝線"),
    _Senku("nemuro", LineId("jp:jr_hokkaido:nemuro_group"), "21", "doto", "nemuro", "根室線"),
    _Senku("hanasaki", LineId("jp:jr_hokkaido:line_0ec04639e5c5"), "22", "doto", "hanasaki", "根室線（花咲線）"),
    _Senku("senmo", LineId("jp:jr_hokkaido:line_e15dbba9f742"), "23", "doto", "senmo", "釧網線"),
)

_METADATA: Final = ProviderMetadata(
    provider_id=_ID, name="JR Hokkaido official",
    source_page_url=HttpUrl(_BASE + "index.html"),
    endpoints=tuple(
        SourceEndpoint(
            url=url, method="GET", format=DataFormat.JSON,
            description=f"{area} area: today/tomorrow senku status and area-wide notices",
        )
        for area, url in _AREA_URLS
    ),
    terms_url=HttpUrl("https://www.jrhokkaido.co.jp/other/goriyou.html"),
    additional_terms_urls=(HttpUrl(_BASE + "call_goriyo.html"),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "General site terms (other/goriyou.html) reserve copyright and prohibit "
        "unauthorized reproduction or modification "
        "(\"無断で複製・改変等を行う事が禁止されております\"). The train-info "
        "service's own usage notes (call_goriyo.html) separately state a "
        "publication threshold of roughly 30-minute delays/suspensions, a "
        "5:00-24:00 service window, that 道南いさりび鉄道 through-trains are "
        "out of scope, and explicitly prohibit unauthorized reproduction, "
        "copying, or reprocessing into electronic media "
        "(\"この情報を無断転載、複写または電磁媒体等に加工することを禁じます\")."
    ),
    statuses=frozenset({LineStatus.NORMAL, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-03T02:30:00+00:00"),
)


class JrHokkaidoProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _BASE + "index.html"
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[entry.line_id].create_line(_ID, _BASE + f"senku.html?id={entry.senku_id}")
            for entry in _SENKU
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        days: dict[_AreaKey, _Day] = {}
        for area, url in _AREA_URLS:
            response = await self._get(client, url, headers=_HEADERS)
            response.raise_for_status()
            payload = _AreaPayload.model_validate_json(response.content.decode("utf-8-sig"))
            days[area] = payload.today
        fetched_at = self._now()
        result: list[Line] = []
        for entry in _SENKU:
            line = next(line for line in self.lines if line.line_id == entry.line_id)
            day = days[entry.area]
            code = _FieldGetter(entry.field)(day.senkuStatus)
            default_affected = () if line.scope is LineScope.GROUP else (line.line_id,)
            notices = tuple(
                (item.title, item.honbun, _parse_notice_time(item.time))
                for item in day.gaikyo
                if item.title.strip() and _eikyo_flag(item.eikyo, entry.area) == 1
            )
            alerts: tuple[ServiceAlert, ...]
            updated_at: datetime | None
            if code == 0:
                status = LineStatus.NORMAL
                alerts, updated_at = (), None
            elif code == 1:
                status = LineStatus.ALERT
                if notices:
                    alerts = tuple(
                        make_alert(line, LineStatus.ALERT, title, honbun, affected_line_ids=())
                        for title, honbun, _ in notices
                    )
                    updated_at = max(notice_time for _, _, notice_time in notices)
                else:
                    alerts = (make_alert(
                        line, LineStatus.ALERT, entry.official_name, _REMARK_1,
                        affected_line_ids=default_affected,
                    ),)
                    updated_at = None
            else:
                status = LineStatus.UNKNOWN
                alerts = (make_alert(
                    line, LineStatus.UNKNOWN, entry.official_name, f"status={code} ({_REMARK_2})",
                    affected_line_ids=default_affected,
                ),)
                updated_at = None
            result.append(snapshot(
                line, status, str(code), fetched_at,
                updated_at=updated_at, alerts=alerts,
                source_line_names=(entry.official_name,),
            ))
        return tuple(result)

    def _route(self, key: str) -> Line:
        identifier = next(e.line_id for e in _SENKU if e.attribute == key)
        return next(line for line in self.lines if line.line_id == identifier)

    @property
    def gakuen_toshi(self) -> Line:
        return self._route("gakuen_toshi")

    @property
    def hidaka(self) -> Line:
        return self._route("hidaka")

    @property
    def airport(self) -> Line:
        return self._route("airport")

    @property
    def hakodate_chitose(self) -> Line:
        return self._route("hakodate_chitose")

    @property
    def muroran(self) -> Line:
        return self._route("muroran")

    @property
    def hakodate_liner(self) -> Line:
        return self._route("hakodate_liner")

    @property
    def hakodate_line(self) -> Line:
        return self._route("hakodate_line")

    @property
    def soya(self) -> Line:
        return self._route("soya")

    @property
    def sekihoku(self) -> Line:
        return self._route("sekihoku")

    @property
    def furano(self) -> Line:
        return self._route("furano")

    @property
    def sekisho(self) -> Line:
        return self._route("sekisho")

    @property
    def nemuro(self) -> Line:
        return self._route("nemuro")

    @property
    def hanasaki(self) -> Line:
        return self._route("hanasaki")

    @property
    def senmo(self) -> Line:
        return self._route("senmo")
