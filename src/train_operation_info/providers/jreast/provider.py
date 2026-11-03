"""JR East official service alerts.

Investigation: reverse engineering of public HTML/JavaScript (no archive).
Reviewed live on 2026-11-02: https://traininfo.jreast.co.jp/train_info/
and kanto.aspx, tohoku.aspx, shinetsu.aspx, shinkansen.aspx under that path.
The server-rendered traininfo-routes__table contains current route labels,
status classes and prose. Real saved responses verify normal, delay,
adjust/suspension (including a timed reopening estimate), partial cancellation,
and info/notices. Class delay also accompanies 一部運休: labels must be checked.
getinformation-jp-kanto.js and getinformation-jp-shinkansen.js under
/train_info/js/ fetch www.jreast.co.jp/traininfojp/{area}.json solely for
the separate editorial notice panel; they do not supply the current route rows.
That panel, PDFs, limited-express services, individual Shinkansen cancellation
lists, detail-page update history and delay certificates are outside coverage.
The region header says 現在 (page clock), not 配信: updated_at remains None.
Status is never inferred from prose, including planned works in notices.
Repeated rows and regions are combined without overwriting active alerts.
Unknown labels/classes remain UNKNOWN; route/field loss aborts the snapshot.
Recovery, unknown labels/classes and damaged HTML are synthetic tests.
Evidence, hashes and canonical scope decisions: tests/fixtures/JREAST.md.
Duration and future applicability are not inferred from prose. Current source
status labels alone establish ACTIVE; mixed long-term notices remain in alerts.
See fixtures/ALERT_CLASSIFICATION.md.
"""

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Final
from unicodedata import normalize
from urllib.parse import parse_qs, urljoin, urlsplit

from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata, ServiceAlert, DataFormat, SourceEndpoint
from train_operation_info.models import UsagePermission
from ..base import SnapshotProvider, combined_status, make_alert, snapshot
from ..classification import timing_from_status

_URL: Final = "https://traininfo.jreast.co.jp/train_info/"
_ID: Final = ProviderId("jreast")
_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL + "kanto.aspx", method="GET", format=DataFormat.HTML,
            description='Current kanto route table',
        ),
        SourceEndpoint(
            url=_URL + "tohoku.aspx", method="GET", format=DataFormat.HTML,
            description='Current tohoku route table',
        ),
        SourceEndpoint(
            url=_URL + "shinetsu.aspx", method="GET", format=DataFormat.HTML,
            description='Current shinetsu route table',
        ),
        SourceEndpoint(
            url=_URL + "shinkansen.aspx", method="GET", format=DataFormat.HTML,
            description='Current shinkansen route table',
        ),
    ),
    provider_id=_ID, name="JR East official", source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.jreast.co.jp/site/rules.html/"),
    additional_terms_urls=(HttpUrl(_URL),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note="The general site terms restrict copying, processing, transmission "
    "and secondary use. The service page describes the publication threshold "
    "and accuracy limitations. Public availability is not a reuse licence.",
    statuses=frozenset({LineStatus.NORMAL, LineStatus.DELAYED, LineStatus.SUSPENDED, LineStatus.PARTIAL_SUSPENSION, LineStatus.ALERT}),
    reviewed_at=datetime.fromisoformat("2026-11-02T02:15:00+00:00"),
)

# Static bindings and explicit properties are generated during development.
_BINDINGS: Final[dict[str, tuple[str, str, LineId]]] = {
    'yamanoteline': ('yamanote', '山手線', LineId('jp:jr_east:yamanote')),
    'ueno-tokyoline': ('ueno_tokyo', '上野東京ライン', LineId('jp:jr_east:line_24943fa818c8')),
    'shonan-shinjukuline': ('shonan_shinjuku', '湘南新宿ライン', LineId('jp:jr_east:line_1a18def17ec6')),
    'sotetsuline': ('sotetsu_through', '相鉄線直通列車', LineId('jp:jr_east:sotetsu_through')),
    'tokaidoline': ('tokaido', '東海道線', LineId('jp:jr_east:line_68861e6bc9d4')),
    'keihin-tohokuline': ('keihin_tohoku', '京浜東北線', LineId('jp:jr_east:line_5cba7d480417')),
    'yokosukaline': ('yokosuka', '横須賀線', LineId('jp:jr_east:line_b40f72600869')),
    'nambuline': ('nambu', '南武線', LineId('jp:jr_east:nambu')),
    'yokohamaline': ('yokohama', '横浜線', LineId('jp:jr_east:line_a6253f08e0a1')),
    'itoline': ('ito', '伊東線', LineId('jp:jr_east:line_0c20ece36b83')),
    'sagamiline': ('sagami', '相模線', LineId('jp:jr_east:line_cf1daefaaa33')),
    'tsurumiline': ('tsurumi', '鶴見線', LineId('jp:jr_east:line_aac6494a6de6')),
    'utsunomiyaline': ('utsunomiya', '宇都宮線', LineId('jp:jr_east:utsunomiya')),
    'takasakiline': ('takasaki', '高崎線', LineId('jp:jr_east:line_2e8809991508')),
    'saikyoline': ('saikyo', '埼京線', LineId('jp:jr_east:saikyo')),
    'kawagoeline': ('kawagoe', '川越線', LineId('jp:jr_east:kawagoe')),
    'musashinoline': ('musashino', '武蔵野線', LineId('jp:jr_east:line_70e87c9f6bdf')),
    'joetsuline': ('joetsu', '上越線', LineId('jp:jr_east:joetsu')),
    'shin-etsuline_kanto': ('shinetsu_takasaki', '信越本線', LineId('jp:jr_east:line_5056ef82ff2c')),
    'agatsumaline': ('agatsuma', '吾妻線', LineId('jp:jr_east:line_d4b0ab9769dc')),
    'karasuyamaline': ('karasuyama', '烏山線', LineId('jp:jr_east:line_3397da3861a6')),
    'hachikoline': ('hachiko', '八高線', LineId('jp:jr_east:hachiko')),
    'nikkoline': ('nikko', '日光線', LineId('jp:jr_east:line_8e4a4c3c8e00')),
    'ryomoline': ('ryomo', '両毛線', LineId('jp:jr_east:line_e69fd4909061')),
    'chuoline_rapidservice': ('chuo_rapid', '中央線快速電車', LineId('jp:jr_east:line_0c82b749d285')),
    'chuo_sobuline_local': ('chuo_sobu_local', '中央・総武各駅停車', LineId('jp:jr_east:line_0a0443880f32')),
    'chuoline': ('chuo', '中央本線', LineId('jp:jr_east:chuo')),
    'itsukaichiline': ('itsukaichi', '五日市線', LineId('jp:jr_east:line_62f43f386d81')),
    'omeline': ('ome', '青梅線', LineId('jp:jr_east:ome')),
    'koumiline': ('koumi', '小海線', LineId('jp:jr_east:line_e8d90dcc0a91')),
    'jobanline': ('joban', '常磐線', LineId('jp:jr_east:joban')),
    'jobanline_rapidservice': ('joban_rapid', '常磐線快速電車', LineId('jp:jr_east:line_70fc0a306ef0')),
    'jobanline_local': ('joban_local', '常磐線各駅停車', LineId('jp:jr_east:line_213c6468afe9')),
    'suigunline': ('suigun', '水郡線', LineId('jp:jr_east:line_9f42712495ae')),
    'mitoline': ('mito', '水戸線', LineId('jp:jr_east:line_0cead7e02b77')),
    'sobuline_rapidservice': ('sobu_rapid', '総武快速線', LineId('jp:jr_east:line_4425bef3a42e')),
    'sobuline': ('sobu', '総武本線', LineId('jp:jr_east:line_91317b39aef5')),
    'keiyoline': ('keiyo', '京葉線', LineId('jp:jr_east:line_945231301f34')),
    'uchiboline': ('uchibo', '内房線', LineId('jp:jr_east:line_6122365b2987')),
    'kashimaline': ('kashima', '鹿島線', LineId('jp:jr_east:line_1fa0b2704985')),
    'kururiline': ('kururi', '久留里線', LineId('jp:jr_east:line_12af095e0fad')),
    'sotoboline': ('sotobo', '外房線', LineId('jp:jr_east:line_8ebaa257ac63')),
    'toganeline': ('togane', '東金線', LineId('jp:jr_east:line_f5b0c4a3be2c')),
    'naritaline': ('narita', '成田線', LineId('jp:jr_east:narita')),
    'monorail': ('tokyo_monorail', '東京モノレール線', LineId('jp:operator_4e61cd883b63:line_8798b239dcc2')),
    'uetsuline': ('uetsu', '羽越本線', LineId('jp:jr_east:uetsu')),
    'ouline': ('ou', '奥羽本線', LineId('jp:jr_east:ou')),
    'ouline_yamagataline': ('yamagata', '奥羽本線（山形線）', LineId('jp:jr_east:line_d80046cd016f')),
    'senzanline': ('senzan', '仙山線', LineId('jp:jr_east:line_e7979ea095d4')),
    'sensekiline': ('senseki', '仙石線', LineId('jp:jr_east:line_3b534d63d808')),
    'senseki-tohokuline': ('senseki_tohoku', '仙石東北ライン', LineId('jp:jr_east:senseki_tohoku')),
    'tohokuline': ('tohoku', '東北本線', LineId('jp:jr_east:tohoku')),
    'ban-etsu-westline': ('banetsu_west', '磐越西線', LineId('jp:jr_east:line_01df1690dc1f')),
    'aterazawaline': ('aterazawa', '左沢線', LineId('jp:jr_east:line_e2382bc8a1d0')),
    'ishinomakiline': ('ishinomaki', '石巻線', LineId('jp:jr_east:line_feffec40264a')),
    'ofunatoline': ('ofunato', '大船渡線', LineId('jp:jr_east:line_d2cafc29c210')),
    'ofunatoline_brt': ('ofunato_brt', '大船渡線ＢＲＴ', LineId('jp:jr_east:ofunato_brt')),
    'ominatoline': ('ominato', '大湊線', LineId('jp:jr_east:line_1850c06bd3e2')),
    'ogaline': ('oga', '男鹿線', LineId('jp:jr_east:line_cd047b11ddf9')),
    'kamaishiline': ('kamaishi', '釜石線', LineId('jp:jr_east:line_7318438435c1')),
    'kitakamiline': ('kitakami', '北上線', LineId('jp:jr_east:line_1134007cbbc2')),
    'kesennumaline': ('kesennuma', '気仙沼線', LineId('jp:jr_east:line_7388a39f1b28')),
    'kesennumaline_brt': ('kesennuma_brt', '気仙沼線ＢＲＴ', LineId('jp:jr_east:kesennuma_brt')),
    'gonoline': ('gono', '五能線', LineId('jp:jr_east:line_1e1df3919bf1')),
    'tazawakoline': ('tazawako', '田沢湖線', LineId('jp:jr_east:line_7442b107c7b5')),
    'tadamiline': ('tadami', '只見線', LineId('jp:jr_east:line_69a3d48ab6bd')),
    'tsugaruline': ('tsugaru', '津軽線', LineId('jp:jr_east:line_12c5fb07b099')),
    'hachinoheline': ('hachinohe', '八戸線', LineId('jp:jr_east:line_ec4ddaa3da53')),
    'hanawaline': ('hanawa', '花輪線', LineId('jp:jr_east:line_295aa8d32036')),
    'ban-etsu-eastline': ('banetsu_east', '磐越東線', LineId('jp:jr_east:line_d19d97fd53c3')),
    'yamadaline': ('yamada', '山田線', LineId('jp:jr_east:line_276831b19018')),
    'yonesakaline': ('yonesaka', '米坂線', LineId('jp:jr_east:line_42587e436867')),
    'riku-westline': ('rikuu_west', '陸羽西線', LineId('jp:jr_east:line_4f0c53cac8b3')),
    'riku-eastline': ('rikuu_east', '陸羽東線', LineId('jp:jr_east:line_170b89280b60')),
    'shin-etsuline_shin-etsu': ('shinetsu_niigata', '信越本線', LineId('jp:jr_east:line_ac3a24dc269f')),
    'shinonoiline': ('shinonoi', '篠ノ井線', LineId('jp:jr_east:line_9d86c0fb4662')),
    'hakushinline': ('hakushin', '白新線', LineId('jp:jr_east:line_127dec402b73')),
    'iiyamaline': ('iiyama', '飯山線', LineId('jp:jr_east:line_a1eae8f6261d')),
    'echigoline': ('echigo', '越後線', LineId('jp:jr_east:line_5fa34fe030ff')),
    'oitoline': ('oito', '大糸線', LineId('jp:jr_east:line_26a1c72a8a77')),
    'yahikoline': ('yahiko', '弥彦線', LineId('jp:jr_east:line_682562788971')),
    'tohokushinkansen': ('tohoku_shinkansen', '東北新幹線', LineId('jp:jr_east:tohoku_shinkansen')),
    'yamagatashinkansen': ('yamagata_shinkansen', '山形新幹線', LineId('jp:jr_east:yamagata_shinkansen')),
    'akitashinkansen': ('akita_shinkansen', '秋田新幹線', LineId('jp:jr_east:akita_shinkansen')),
    'hokurikushinkansen': ('hokuriku_shinkansen', '北陸新幹線', LineId('jp:jr_west:hokuriku_shinkansen')),
    'joetsushinkansen': ('joetsu_shinkansen', '上越新幹線', LineId('jp:jr_east:joetsu_shinkansen')),
}

_AREA_GIDS: Final = {"kanto": "1", "tohoku": "4", "shinetsu": "5"}
_AREA_ROUTES: Final[dict[str, tuple[str, ...]]] = {
    'kanto': (
        'yamanoteline',
        'ueno-tokyoline',
        'shonan-shinjukuline',
        'sotetsuline',
        'tokaidoline',
        'keihin-tohokuline',
        'yokosukaline',
        'nambuline',
        'yokohamaline',
        'itoline',
        'sagamiline',
        'tsurumiline',
        'utsunomiyaline',
        'takasakiline',
        'saikyoline',
        'kawagoeline',
        'musashinoline',
        'joetsuline',
        'shin-etsuline_kanto',
        'agatsumaline',
        'karasuyamaline',
        'hachikoline',
        'nikkoline',
        'ryomoline',
        'chuoline_rapidservice',
        'chuo_sobuline_local',
        'chuoline',
        'itsukaichiline',
        'omeline',
        'koumiline',
        'jobanline',
        'jobanline_rapidservice',
        'jobanline_local',
        'suigunline',
        'mitoline',
        'sobuline_rapidservice',
        'sobuline',
        'keiyoline',
        'uchiboline',
        'kashimaline',
        'kururiline',
        'sotoboline',
        'toganeline',
        'naritaline',
        'monorail',
    ),
    'tohoku': (
        'uetsuline',
        'ouline',
        'ouline_yamagataline',
        'jobanline',
        'senzanline',
        'sensekiline',
        'senseki-tohokuline',
        'tohokuline',
        'ban-etsu-westline',
        'aterazawaline',
        'ishinomakiline',
        'ofunatoline',
        'ofunatoline_brt',
        'ominatoline',
        'ogaline',
        'kamaishiline',
        'kitakamiline',
        'kesennumaline',
        'kesennumaline_brt',
        'gonoline',
        'suigunline',
        'tazawakoline',
        'tadamiline',
        'tsugaruline',
        'hachinoheline',
        'hanawaline',
        'ban-etsu-eastline',
        'yamadaline',
        'yonesakaline',
        'riku-westline',
        'riku-eastline',
    ),
    'shinetsu': (
        'uetsuline',
        'shin-etsuline_shin-etsu',
        'joetsuline',
        'shinonoiline',
        'chuoline',
        'hakushinline',
        'ban-etsu-westline',
        'iiyamaline',
        'echigoline',
        'oitoline',
        'koumiline',
        'tadamiline',
        'yahikoline',
        'yonesakaline',
    ),
    'shinkansen': (
        'tohokushinkansen',
        'yamagatashinkansen',
        'akitashinkansen',
        'hokurikushinkansen',
        'joetsushinkansen',
    ),
}


@dataclass(frozen=True)
class _Report:
    source_id: str
    name: str
    label: str
    status: LineStatus
    description: str
    url: str


def _status(label: str, markers: tuple[str, ...]) -> LineStatus:
    text = re.sub(r"\s+", "", normalize("NFKC", label))
    if markers == ("normal",) and text == "平常運転":
        return LineStatus.NORMAL
    if markers == ("delay",):
        if text == "遅延":
            return LineStatus.DELAYED
        if text == "一部運休":
            return LineStatus.PARTIAL_SUSPENSION
    if markers == ("adjust",) and re.fullmatch(
        r"(?:\d{1,2}時(?:\d{1,2}分)?頃?)?(?:運転見合わせ|運転再開見込)", text,
    ):
        return LineStatus.SUSPENDED
    if markers == ("info",) and text == "お知らせ":
        return LineStatus.ALERT
    return LineStatus.UNKNOWN


def _parse_area(html: str, area: str) -> tuple[_Report, ...]:
    soup = BeautifulSoup(html, "html.parser")
    expected = _AREA_ROUTES[area]
    seen: set[str] = set()
    reports: list[_Report] = []
    for item in soup.select(".traininfo-routes__table__item"):
        names = item.select(".traininfo-routes__name")
        statuses = item.select(".traininfo-routes__status")
        infos = item.select(".traininfo-routes__info")
        if len(names) != 1 or len(statuses) != 1 or len(infos) != 1:
            raise ParseError("JR East route name, status or info is missing/duplicated")
        name = names[0].get_text(strip=True)
        label = statuses[0].get_text(" ", strip=True)
        href = infos[0].get("href")
        if area == "shinkansen":
            icons = item.select(".traininfo-routes__line")
            classes = icons[0].get_attribute_list("class") if len(icons) == 1 else []
            keys = [key for key in classes if key != "traininfo-routes__line"]
            if len(keys) != 1:
                raise ParseError("JR East Shinkansen route identity is missing")
            source_id = keys[0]
            detail_url = urljoin(_URL, "shinkansen.aspx")
        else:
            if not isinstance(href, str):
                raise ParseError("JR East route link is missing")
            detail_url = urljoin(_URL, href)
            parsed = urlsplit(detail_url)
            query = parse_qs(parsed.query)
            keys = query.get("lineid", [])
            if (parsed.scheme != "https" or parsed.netloc != "traininfo.jreast.co.jp"
                    or parsed.path != "/train_info/line.aspx" or len(keys) != 1
                    or query.get("gid") != [_AREA_GIDS[area]]
                    or set(query) != {"gid", "lineid"}):
                raise ParseError("JR East route link changed")
            source_id = keys[0]
        if source_id not in expected or name != _BINDINGS[source_id][1] or not label:
            raise ParseError("JR East route identity or status changed")
        markers = tuple(c for c in statuses[0].get_attribute_list("class") if c != "traininfo-routes__status")
        if not markers:
            raise ParseError("JR East status marker is missing")
        state = _status(label, markers)
        description = "\n".join(node.get_text(" ", strip=True) for node in item.select(".traininfo-routes__note"))
        if state not in (LineStatus.NORMAL, LineStatus.UNKNOWN) and not description:
            raise ParseError("JR East incident description is missing")
        if state is LineStatus.UNKNOWN and not description:
            description = f"{name}: {label}\n表示クラス: {' '.join(markers)}"
        reports.append(_Report(source_id, name, label, state, description, detail_url))
        seen.add(source_id)
    if seen != set(expected):
        raise ParseError(f"JR East {area} route inventory is incomplete")
    return tuple(reports)


class JrEastProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        super().__init__(tuple(
            LINE_CATALOG[binding[2]].create_line(_ID, _URL)
            for binding in _BINDINGS.values()
        ), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        reports: list[_Report] = []
        for area in _AREA_ROUTES:
            response = await self._get(client, urljoin(_URL, f"{area}.aspx"))
            response.raise_for_status()
            reports.extend(_parse_area(response.text, area))
        fetched_at = self._now()
        by_id: dict[LineId, list[_Report]] = {line.line_id: [] for line in self.lines}
        for report in reports:
            by_id[_BINDINGS[report.source_id][2]].append(report)
        result: list[Line] = []
        for line in self.lines:
            entries = by_id[line.line_id]
            by_alert_id: dict[str, ServiceAlert] = {}
            for report in entries:
                if report.status is LineStatus.NORMAL:
                    continue
                alert = make_alert(
                    line, report.status, f"{report.name}: {report.label}", report.description,
                    timing=timing_from_status(report.status),
                ).model_copy(update={"source_url": report.url})
                by_alert_id[alert.alert_id] = alert
            alerts = tuple(by_alert_id.values())
            result.append(snapshot(
                line, combined_status(tuple(report.status for report in entries)),
                " / ".join(dict.fromkeys(report.label for report in entries)), fetched_at,
                alerts=alerts, source_line_names=tuple(dict.fromkeys(report.name for report in entries)),
            ))
        return tuple(result)

    def _route(self, source_id: str) -> Line:
        identifier = _BINDINGS[source_id][2]
        return next(line for line in self.lines if line.line_id == identifier)

    @property
    def yamanote(self) -> Line:
        return self._route('yamanoteline')


    @property
    def ueno_tokyo(self) -> Line:
        return self._route('ueno-tokyoline')


    @property
    def shonan_shinjuku(self) -> Line:
        return self._route('shonan-shinjukuline')


    @property
    def sotetsu_through(self) -> Line:
        return self._route('sotetsuline')


    @property
    def tokaido(self) -> Line:
        return self._route('tokaidoline')


    @property
    def keihin_tohoku(self) -> Line:
        return self._route('keihin-tohokuline')


    @property
    def yokosuka(self) -> Line:
        return self._route('yokosukaline')


    @property
    def nambu(self) -> Line:
        return self._route('nambuline')


    @property
    def yokohama(self) -> Line:
        return self._route('yokohamaline')


    @property
    def ito(self) -> Line:
        return self._route('itoline')


    @property
    def sagami(self) -> Line:
        return self._route('sagamiline')


    @property
    def tsurumi(self) -> Line:
        return self._route('tsurumiline')


    @property
    def utsunomiya(self) -> Line:
        return self._route('utsunomiyaline')


    @property
    def takasaki(self) -> Line:
        return self._route('takasakiline')


    @property
    def saikyo(self) -> Line:
        return self._route('saikyoline')


    @property
    def kawagoe(self) -> Line:
        return self._route('kawagoeline')


    @property
    def musashino(self) -> Line:
        return self._route('musashinoline')


    @property
    def joetsu(self) -> Line:
        return self._route('joetsuline')


    @property
    def shinetsu_takasaki(self) -> Line:
        return self._route('shin-etsuline_kanto')


    @property
    def agatsuma(self) -> Line:
        return self._route('agatsumaline')


    @property
    def karasuyama(self) -> Line:
        return self._route('karasuyamaline')


    @property
    def hachiko(self) -> Line:
        return self._route('hachikoline')


    @property
    def nikko(self) -> Line:
        return self._route('nikkoline')


    @property
    def ryomo(self) -> Line:
        return self._route('ryomoline')


    @property
    def chuo_rapid(self) -> Line:
        return self._route('chuoline_rapidservice')


    @property
    def chuo_sobu_local(self) -> Line:
        return self._route('chuo_sobuline_local')


    @property
    def chuo(self) -> Line:
        return self._route('chuoline')


    @property
    def itsukaichi(self) -> Line:
        return self._route('itsukaichiline')


    @property
    def ome(self) -> Line:
        return self._route('omeline')


    @property
    def koumi(self) -> Line:
        return self._route('koumiline')


    @property
    def joban(self) -> Line:
        return self._route('jobanline')


    @property
    def joban_rapid(self) -> Line:
        return self._route('jobanline_rapidservice')


    @property
    def joban_local(self) -> Line:
        return self._route('jobanline_local')


    @property
    def suigun(self) -> Line:
        return self._route('suigunline')


    @property
    def mito(self) -> Line:
        return self._route('mitoline')


    @property
    def sobu_rapid(self) -> Line:
        return self._route('sobuline_rapidservice')


    @property
    def sobu(self) -> Line:
        return self._route('sobuline')


    @property
    def keiyo(self) -> Line:
        return self._route('keiyoline')


    @property
    def uchibo(self) -> Line:
        return self._route('uchiboline')


    @property
    def kashima(self) -> Line:
        return self._route('kashimaline')


    @property
    def kururi(self) -> Line:
        return self._route('kururiline')


    @property
    def sotobo(self) -> Line:
        return self._route('sotoboline')


    @property
    def togane(self) -> Line:
        return self._route('toganeline')


    @property
    def narita(self) -> Line:
        return self._route('naritaline')


    @property
    def tokyo_monorail(self) -> Line:
        return self._route('monorail')


    @property
    def uetsu(self) -> Line:
        return self._route('uetsuline')


    @property
    def ou(self) -> Line:
        return self._route('ouline')


    @property
    def yamagata(self) -> Line:
        return self._route('ouline_yamagataline')


    @property
    def senzan(self) -> Line:
        return self._route('senzanline')


    @property
    def senseki(self) -> Line:
        return self._route('sensekiline')


    @property
    def senseki_tohoku(self) -> Line:
        return self._route('senseki-tohokuline')


    @property
    def tohoku(self) -> Line:
        return self._route('tohokuline')


    @property
    def banetsu_west(self) -> Line:
        return self._route('ban-etsu-westline')


    @property
    def aterazawa(self) -> Line:
        return self._route('aterazawaline')


    @property
    def ishinomaki(self) -> Line:
        return self._route('ishinomakiline')


    @property
    def ofunato(self) -> Line:
        return self._route('ofunatoline')


    @property
    def ofunato_brt(self) -> Line:
        return self._route('ofunatoline_brt')


    @property
    def ominato(self) -> Line:
        return self._route('ominatoline')


    @property
    def oga(self) -> Line:
        return self._route('ogaline')


    @property
    def kamaishi(self) -> Line:
        return self._route('kamaishiline')


    @property
    def kitakami(self) -> Line:
        return self._route('kitakamiline')


    @property
    def kesennuma(self) -> Line:
        return self._route('kesennumaline')


    @property
    def kesennuma_brt(self) -> Line:
        return self._route('kesennumaline_brt')


    @property
    def gono(self) -> Line:
        return self._route('gonoline')


    @property
    def tazawako(self) -> Line:
        return self._route('tazawakoline')


    @property
    def tadami(self) -> Line:
        return self._route('tadamiline')


    @property
    def tsugaru(self) -> Line:
        return self._route('tsugaruline')


    @property
    def hachinohe(self) -> Line:
        return self._route('hachinoheline')


    @property
    def hanawa(self) -> Line:
        return self._route('hanawaline')


    @property
    def banetsu_east(self) -> Line:
        return self._route('ban-etsu-eastline')


    @property
    def yamada(self) -> Line:
        return self._route('yamadaline')


    @property
    def yonesaka(self) -> Line:
        return self._route('yonesakaline')


    @property
    def rikuu_west(self) -> Line:
        return self._route('riku-westline')


    @property
    def rikuu_east(self) -> Line:
        return self._route('riku-eastline')


    @property
    def shinetsu_niigata(self) -> Line:
        return self._route('shin-etsuline_shin-etsu')


    @property
    def shinonoi(self) -> Line:
        return self._route('shinonoiline')


    @property
    def hakushin(self) -> Line:
        return self._route('hakushinline')


    @property
    def iiyama(self) -> Line:
        return self._route('iiyamaline')


    @property
    def echigo(self) -> Line:
        return self._route('echigoline')


    @property
    def oito(self) -> Line:
        return self._route('oitoline')


    @property
    def yahiko(self) -> Line:
        return self._route('yahikoline')


    @property
    def tohoku_shinkansen(self) -> Line:
        return self._route('tohokushinkansen')


    @property
    def yamagata_shinkansen(self) -> Line:
        return self._route('yamagatashinkansen')


    @property
    def akita_shinkansen(self) -> Line:
        return self._route('akitashinkansen')


    @property
    def hokuriku_shinkansen(self) -> Line:
        return self._route('hokurikushinkansen')


    @property
    def joetsu_shinkansen(self) -> Line:
        return self._route('joetsushinkansen')

