"""JR West official service alerts.

Investigation: Both archive and public-source inspection. The official Next.js client
identifies /api/v1/trafficinfo.json. Current live data and Wayback captures 20261001234249
and 20261021235454 were obtained. Only current-day active entries are used; history and
future-day arrays are not current incidents. Regional source IDs are mapped to shared
canonical line IDs. Evidence: tests/fixtures/SOURCES.md.
areaAnnouncements is outside the provider's scope and is ignored, including
long-term closures and other regional notices. NORMAL means no incident in the
current-day dailyData, not absence of long-term closures. The raw API response
may still contain excluded announcements. Duration/future applicability are not
inferred from prose; verified current status labels alone establish ACTIVE.
Scope evidence: tests/fixtures/ALERT_CLASSIFICATION.md.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl,
)

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    Line, LineId, LineStatus, Operator, OperatorId,
    ProviderId, ProviderMetadata, ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, initial_lines, japanese_status, make_alert, snapshot
from ..classification import timing_from_status

_URL: Final = "https://trafficinfo.westjr.co.jp/"
_API: Final = "https://trafficinfo.westjr.co.jp/api/v1/trafficinfo.json"
_ID: Final = ProviderId("jrw")
_OPERATOR: Final = Operator(operator_id=OperatorId("jp:jr_west"), name="JR西日本")

# Static route properties and catalog are generated below from the observed
# official master data. No dynamic attributes or untyped JSON dictionaries.
_CATALOG: Final[tuple[tuple[int, str, str], ...]] = (
    (1, "hokuriku", "北陸線"),
    (2, "biwako", "琵琶湖線"),
    (3, "kyoto", "ＪＲ京都線"),
    (4, "kobe", "ＪＲ神戸線"),
    (5, "sanyo", "山陽線"),
    (6, "ako", "赤穂線"),
    (7, "wadamisaki", "和田岬線"),
    (8, "kosei", "湖西線"),
    (9, "kusatsu", "草津線"),
    (10, "nara", "奈良線"),
    (11, "sagano", "嵯峨野線"),
    (12, "osaka_higashi", "おおさか東線"),
    (13, "takarazuka", "ＪＲ宝塚線"),
    (14, "tozai", "ＪＲ東西線"),
    (15, "gakkentoshi", "学研都市線"),
    (16, "kakogawa", "加古川線"),
    (17, "kishin", "姫新線"),
    (18, "osaka_loop", "大阪環状線"),
    (19, "yumesaki", "ＪＲゆめ咲線"),
    (20, "yamatoji", "大和路線"),
    (21, "hanwa", "阪和線"),
    (22, "kansai_airport", "関西空港線"),
    (23, "hagoromo", "羽衣線"),
    (24, "wakayama", "和歌山線"),
    (25, "manyomahoroba", "万葉まほろば線"),
    (26, "kansai", "関西線"),
    (27, "hokuriku", "北陸線"),
    (28, "oito", "大糸線"),
    (29, "takayama", "高山線"),
    (30, "himi", "氷見線"),
    (31, "johana", "城端線"),
    (32, "nanao", "七尾線"),
    (33, "etsumi_hoku", "越美北線（九頭竜線）"),
    (34, "obama", "小浜線"),
    (35, "wakayama", "和歌山線"),
    (36, "kinokuni", "きのくに線"),
    (37, "kisei", "紀勢線（和歌山市方面）"),
    (38, "sanin", "山陰線"),
    (39, "takarazuka", "ＪＲ宝塚線"),
    (40, "fukuchiyama", "福知山線"),
    (41, "bantan", "播但線"),
    (42, "maizuru", "舞鶴線"),
    (43, "inbi", "因美線"),
    (44, "kishin", "姫新線"),
    (45, "uno_minato", "宇野みなと線"),
    (46, "seto_ohashi", "瀬戸大橋線"),
    (47, "ako", "赤穂線"),
    (48, "geibi", "芸備線"),
    (49, "sanyo", "山陽線"),
    (50, "tsuyama", "津山線"),
    (51, "momotaro", "桃太郎線"),
    (52, "hakubi", "伯備線"),
    (53, "fukuen", "福塩線"),
    (54, "sanin", "山陰線"),
    (55, "inbi", "因美線"),
    (56, "sakai", "境線"),
    (57, "kisuki", "木次線"),
    (58, "hakubi", "伯備線"),
    (59, "kabe", "可部線"),
    (60, "sanyo", "山陽線"),
    (61, "geibi", "芸備線"),
    (62, "kure", "呉線"),
    (63, "fukuen", "福塩線"),
    (64, "sanin", "山陰線"),
    (65, "sanin_senzaki", "山陰線（仙崎方面）"),
    (66, "gantoku", "岩徳線"),
    (67, "yamaguchi", "山口線"),
    (68, "ube", "宇部線"),
    (69, "onoda", "小野田線"),
    (70, "onoda_nagato_motoyama", "小野田線（長門本山方面）"),
    (71, "mine", "美祢線"),
    (101, "sanyo_shinkansen", "山陽新幹線"),
    (102, "hakata_minami", "博多南線"),
    (103, "hokuriku_shinkansen", "北陸新幹線"),
)


_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_API, method="GET", format=DataFormat.JSON,
            description='Current-day dailyData only; areaAnnouncements excluded',
        ),
    ),
    provider_id=ProviderId('jrw'), name='JR West official',
    source_page_url=HttpUrl('https://trafficinfo.westjr.co.jp/'),
    terms_url=HttpUrl('https://trafficinfo.westjr.co.jp/static-pages/usage.html'),
    additional_terms_urls=(HttpUrl('https://trafficinfo.westjr.co.jp/static-pages/readme.html'), HttpUrl('https://www.westjr.co.jp/guide/'), ),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note='The service overview prohibits unapproved republication, copying and processing into electronic media. The environment/links page is not a commercial data licence.',
    reviewed_at=datetime.fromisoformat('2026-11-01T14:36:42.593050+00:00'),
)

class _SourceModel(BaseModel):
    # Validate every consumed field strictly; unrelated history/extension fields
    # are ignored so additions by the publisher do not break a current feed.
    model_config = ConfigDict(strict=True, extra="ignore")


class _MasterLine(_SourceModel):
    id: int
    name: str


class _MasterPlace(_SourceModel):
    id: int
    lines: list[_MasterLine]


class _MasterArea(_SourceModel):
    id: int
    places: list[_MasterPlace]


class _MasterData(_SourceModel):
    areas: list[_MasterArea]


class _Version(_SourceModel):
    id: int
    title: str
    body: str
    updatedAt: AwareDatetime


class _Detail(_SourceModel):
    trafficId: int
    conditionName: str
    publicationDate: AwareDatetime
    versionDetail: list[_Version] = Field(min_length=1)


class _Traffic(_SourceModel):
    id: int
    lineName: str
    conventionalLineTrafficInfoDetails: list[_Detail] | None = None
    shinkansenTrafficInfoDetails: list[_Detail] | None = None


class _Place(_SourceModel):
    id: int
    conventionalLineTrafficInfos: list[_Traffic] | None = None
    shinkansenTrafficInfos: list[_Traffic] | None = None


class _Day(_SourceModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    placeTrafficInfos: list[_Place]


class _Area(_SourceModel):
    id: int
    dailyData: list[_Day]


class _Maintenance(_SourceModel):
    id: int
    isMaintaining: bool


class _Payload(_SourceModel):
    createdAt: AwareDatetime
    masterData: _MasterData
    areaTrafficInfos: list[_Area]
    maintenances: list[_Maintenance]


@dataclass(frozen=True)
class _CurrentIncident:
    status: LineStatus
    label: str
    version: _Version


def _parse(data: _Payload, lines: tuple[Line, ...], fetched_at: datetime) -> tuple[Line, ...]:
    if any(item.isMaintaining for item in data.maintenances):
        raise ParseError("JR West is announcing source maintenance")
    catalog_ids = {identifier for identifier, _, _ in _CATALOG}
    master_places: dict[int, set[int]] = {}
    master_areas: dict[int, set[int]] = {}
    for area in data.masterData.areas:
        if area.id == 0:  # Named express trains are services, not physical lines.
            continue
        if area.id not in (1, 2, 3, 4, 5) or area.id in master_areas:
            raise ParseError("Unknown or duplicate JR West master area")
        master_areas[area.id] = set()
        for master_place in area.places:
            if master_place.id in master_places:
                raise ParseError("Duplicate JR West master place")
            master_areas[area.id].add(master_place.id)
            master_places[master_place.id] = {line.id for line in master_place.lines}
    observed_ids = set().union(*master_places.values())
    # 72 is the Miyajima ferry, deliberately excluded from this railway library.
    if observed_ids - {72} != catalog_ids or set(master_areas) != {1, 2, 3, 4, 5}:
        raise ParseError("JR West official route catalog changed or is incomplete")
    by_key = {line.line_id.rsplit(":", 1)[-1]: line for line in lines}
    by_id = {identifier: by_key[key] for identifier, key, _ in _CATALOG}
    events: dict[LineId, dict[int, _CurrentIncident]] = {line.line_id: {} for line in lines}
    current_date = data.createdAt.astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat()
    seen_areas: set[int] = set()
    for traffic_area in data.areaTrafficInfos:
        if traffic_area.id == 0:
            continue
        if traffic_area.id not in master_areas or traffic_area.id in seen_areas:
            raise ParseError("Unknown or duplicate JR West traffic area")
        seen_areas.add(traffic_area.id)
        days = [day for day in traffic_area.dailyData if day.date == current_date]
        if len(days) != 1:
            raise ParseError("JR West current-day data is missing or ambiguous")
        places = days[0].placeTrafficInfos
        if {place.id for place in places} != master_areas[traffic_area.id] or len(places) != len(master_areas[traffic_area.id]):
            raise ParseError("JR West place coverage is incomplete")
        for place in places:
            is_shinkansen = traffic_area.id in (4, 5)
            traffics = place.shinkansenTrafficInfos if is_shinkansen else place.conventionalLineTrafficInfos
            if traffics is None:
                raise ParseError("JR West current traffic list is missing")
            seen_lines: set[int] = set()
            for traffic in traffics:
                if traffic.id == 72:
                    continue
                if traffic.id not in master_places[place.id] or traffic.id not in by_id or traffic.id in seen_lines:
                    raise ParseError(f"Unexpected JR West active line: {traffic.id}")
                seen_lines.add(traffic.id)
                details = traffic.shinkansenTrafficInfoDetails if is_shinkansen else traffic.conventionalLineTrafficInfoDetails
                if not details:
                    raise ParseError("JR West active line lacks incident details")
                line = by_id[traffic.id]
                for detail in details:
                    version = max(detail.versionDetail, key=lambda item: item.updatedAt)
                    previous = events[line.line_id].get(detail.trafficId)
                    state = japanese_status(detail.conditionName)
                    label = detail.conditionName
                    if previous is not None:
                        if previous.version.updatedAt > version.updatedAt:
                            continue
                        if previous.version.updatedAt == version.updatedAt:
                            state = combined_status((previous.status, state))
                            label = " / ".join(dict.fromkeys((previous.label, label)))
                    events[line.line_id][detail.trafficId] = _CurrentIncident(state, label, version)
    if seen_areas != set(master_areas):
        raise ParseError("JR West area coverage is incomplete")
    result: list[Line] = []
    for line in lines:
        incidents = events[line.line_id]
        daily_alerts: list[ServiceAlert] = []
        for identifier, incident in incidents.items():
            if incident.status is LineStatus.NORMAL:
                continue
            daily_alerts.append(make_alert(
                line, incident.status, incident.version.title, incident.version.body,
                alert_id=f"jrw:{identifier}:{line.line_id}", timing=timing_from_status(incident.status),
            ))
        alerts = tuple(daily_alerts)
        status = combined_status(tuple(incident.status for incident in incidents.values()))
        label = " / ".join(dict.fromkeys(
            incident.label for incident in incidents.values()
        ))
        updated_at = max(
            (incident.version.updatedAt for incident in incidents.values()), default=data.createdAt,
        )
        result.append(snapshot(
            line, status, label or "通常運転（日次障害欄の掲載なし）", fetched_at,
            updated_at=updated_at, alerts=alerts,
        ))
    return tuple(result)


class JrWestProvider(SnapshotProvider):
    _metadata = _METADATA
    _provider_id = _ID
    _source_url = _URL

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        definitions = tuple(dict.fromkeys((key, name) for _, key, name in _CATALOG))
        super().__init__(initial_lines("jp:jr_west", _ID, _URL, _OPERATOR, definitions), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, _API)
        response.raise_for_status()
        payload = _Payload.model_validate_json(response.content)
        return _parse(payload, self.lines, self._now())

    @property
    def hokuriku_kinki(self) -> Line:
        return self._line("hokuriku")

    @property
    def biwako(self) -> Line:
        return self._line("biwako")

    @property
    def kyoto(self) -> Line:
        return self._line("kyoto")

    @property
    def kobe(self) -> Line:
        return self._line("kobe")

    @property
    def sanyo_kinki(self) -> Line:
        return self._line("sanyo")

    @property
    def ako_kinki(self) -> Line:
        return self._line("ako")

    @property
    def wadamisaki(self) -> Line:
        return self._line("wadamisaki")

    @property
    def kosei(self) -> Line:
        return self._line("kosei")

    @property
    def kusatsu(self) -> Line:
        return self._line("kusatsu")

    @property
    def nara(self) -> Line:
        return self._line("nara")

    @property
    def sagano(self) -> Line:
        return self._line("sagano")

    @property
    def osaka_higashi(self) -> Line:
        return self._line("osaka_higashi")

    @property
    def takarazuka(self) -> Line:
        return self._line("takarazuka")

    @property
    def tozai(self) -> Line:
        return self._line("tozai")

    @property
    def gakkentoshi(self) -> Line:
        return self._line("gakkentoshi")

    @property
    def kakogawa(self) -> Line:
        return self._line("kakogawa")

    @property
    def kishin_kinki(self) -> Line:
        return self._line("kishin")

    @property
    def osaka_loop(self) -> Line:
        return self._line("osaka_loop")

    @property
    def yumesaki(self) -> Line:
        return self._line("yumesaki")

    @property
    def yamatoji(self) -> Line:
        return self._line("yamatoji")

    @property
    def hanwa(self) -> Line:
        return self._line("hanwa")

    @property
    def kansai_airport(self) -> Line:
        return self._line("kansai_airport")

    @property
    def hagoromo(self) -> Line:
        return self._line("hagoromo")

    @property
    def wakayama_kinki(self) -> Line:
        return self._line("wakayama")

    @property
    def manyomahoroba(self) -> Line:
        return self._line("manyomahoroba")

    @property
    def kansai(self) -> Line:
        return self._line("kansai")

    @property
    def hokuriku(self) -> Line:
        return self._line("hokuriku")

    @property
    def oito(self) -> Line:
        return self._line("oito")

    @property
    def takayama(self) -> Line:
        return self._line("takayama")

    @property
    def himi(self) -> Line:
        return self._line("himi")

    @property
    def johana(self) -> Line:
        return self._line("johana")

    @property
    def nanao(self) -> Line:
        return self._line("nanao")

    @property
    def etsumi_hoku(self) -> Line:
        return self._line("etsumi_hoku")

    @property
    def obama(self) -> Line:
        return self._line("obama")

    @property
    def wakayama(self) -> Line:
        return self._line("wakayama")

    @property
    def kinokuni(self) -> Line:
        return self._line("kinokuni")

    @property
    def kisei(self) -> Line:
        return self._line("kisei")

    @property
    def sanin_kitakinki(self) -> Line:
        return self._line("sanin")

    @property
    def takarazuka_kitakinki(self) -> Line:
        return self._line("takarazuka")

    @property
    def fukuchiyama(self) -> Line:
        return self._line("fukuchiyama")

    @property
    def bantan(self) -> Line:
        return self._line("bantan")

    @property
    def maizuru(self) -> Line:
        return self._line("maizuru")

    @property
    def inbi_okayama(self) -> Line:
        return self._line("inbi")

    @property
    def kishin_okayama(self) -> Line:
        return self._line("kishin")

    @property
    def uno_minato(self) -> Line:
        return self._line("uno_minato")

    @property
    def seto_ohashi(self) -> Line:
        return self._line("seto_ohashi")

    @property
    def ako_okayama(self) -> Line:
        return self._line("ako")

    @property
    def geibi_okayama(self) -> Line:
        return self._line("geibi")

    @property
    def sanyo_okayama(self) -> Line:
        return self._line("sanyo")

    @property
    def tsuyama(self) -> Line:
        return self._line("tsuyama")

    @property
    def momotaro(self) -> Line:
        return self._line("momotaro")

    @property
    def hakubi_okayama(self) -> Line:
        return self._line("hakubi")

    @property
    def fukuen_okayama(self) -> Line:
        return self._line("fukuen")

    @property
    def sanin(self) -> Line:
        return self._line("sanin")

    @property
    def inbi(self) -> Line:
        return self._line("inbi")

    @property
    def sakai(self) -> Line:
        return self._line("sakai")

    @property
    def kisuki(self) -> Line:
        return self._line("kisuki")

    @property
    def hakubi(self) -> Line:
        return self._line("hakubi")

    @property
    def kabe(self) -> Line:
        return self._line("kabe")

    @property
    def sanyo(self) -> Line:
        return self._line("sanyo")

    @property
    def geibi(self) -> Line:
        return self._line("geibi")

    @property
    def kure(self) -> Line:
        return self._line("kure")

    @property
    def fukuen(self) -> Line:
        return self._line("fukuen")

    @property
    def sanin_yamaguchi(self) -> Line:
        return self._line("sanin")

    @property
    def sanin_senzaki(self) -> Line:
        return self._line("sanin_senzaki")

    @property
    def gantoku(self) -> Line:
        return self._line("gantoku")

    @property
    def yamaguchi(self) -> Line:
        return self._line("yamaguchi")

    @property
    def ube(self) -> Line:
        return self._line("ube")

    @property
    def onoda(self) -> Line:
        return self._line("onoda")

    @property
    def onoda_nagato_motoyama(self) -> Line:
        return self._line("onoda_nagato_motoyama")

    @property
    def mine(self) -> Line:
        return self._line("mine")

    @property
    def sanyo_shinkansen(self) -> Line:
        return self._line("sanyo_shinkansen")

    @property
    def hakata_minami(self) -> Line:
        return self._line("hakata_minami")

    @property
    def hokuriku_shinkansen(self) -> Line:
        return self._line("hokuriku_shinkansen")

    @property
    def ako(self) -> Line:
        return self._line("ako")

    @property
    def kishin(self) -> Line:
        return self._line("kishin")
