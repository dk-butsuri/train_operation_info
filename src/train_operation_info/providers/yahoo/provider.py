"""Yahoo! Transit service alerts from the eight regional conventional-line pages.

Investigation: public HTML inspection and live abnormal responses, with the
area-list/detail approach and year-rollover logic referenced from
../keihan_tracker/keihan_tracker/delay_tracker.py (MIT, dk-butsuri, 2026).
Live pages /diainfo/336/0 and /diainfo/288/0 verify delay and suspension;
/diainfo/547/0 verifies recovery. No archived abnormal response was needed.
The two numeric path components together identify a source route: 331/421 and
331/422 are different sections. Navigation and truncated area previews are not
incident details. Keihan's combined route and Hankyu's individual main lines
must not be equated with different-scope canonical definitions.
Evidence and fixture extraction: tests/fixtures/YAHOO.md.
"Other" is not assumed to mean long-term or currently active. Duration and
future applicability are not inferred from prose. Only explicit current status
labels establish ACTIVE. See ALERT_CLASSIFICATION.md.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
import re
from typing import Final, NewType
import unicodedata
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

from train_operation_info.exceptions import ParseError
from train_operation_info.models import (
    DataFormat, SourceEndpoint,
    LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata,
    ServiceAlert, UsagePermission,
)
from ..base import SnapshotProvider, combined_status, make_alert, snapshot
from ..classification import timing_from_status

YahooRouteId = NewType("YahooRouteId", str)


class YahooArea(IntEnum):
    HOKKAIDO = 2
    TOHOKU = 3
    KANTO = 4
    CHUBU = 5
    KINKI = 6
    KYUSHU = 7
    CHUGOKU = 8
    SHIKOKU = 9


_URL: Final = "https://transit.yahoo.co.jp/diainfo"
_ID: Final = ProviderId("yahoo")
_JST: Final = ZoneInfo("Asia/Tokyo")
_ALL_AREAS: Final = tuple(YahooArea)
_ROUTE_PATH: Final = re.compile(r"/diainfo/(\d+/\d+)/?")
_POSTED: Final = re.compile(r"[（(](\d{1,2})月(\d{1,2})日\s*(\d{1,2})時(\d{1,2})分掲載[）)]")

_METADATA: Final = ProviderMetadata(
    endpoints=(
        SourceEndpoint(
            url=_URL + "/area/{area}", method="GET", format=DataFormat.HTML,
            is_template=True,
            description='Selected area IDs, 2 through 9',
        ),
        SourceEndpoint(
            url=_URL + "/{route}/{section}", method="GET", format=DataFormat.HTML,
            is_template=True,
            description='Registered route details when a notice or recovery is listed',
        ),
    ),
    provider_id=_ID, name="Yahoo!路線情報",
    source_page_url=HttpUrl(_URL),
    terms_url=HttpUrl("https://www.lycorp.co.jp/ja/company/terms/"),
    additional_terms_urls=(HttpUrl("https://support.yahoo-net.jp/PccTransit/s/article/H000007493"),),
    usage_permission=UsagePermission.PERMISSION_REQUIRED,
    usage_note=(
        "Yahoo! Transit's service-specific help says secondary use is generally not permitted "
        "because the information is supplied under partner agreements; some cases require an "
        "inquiry. It also restricts saving and reusing the information. No blanket private-use "
        "or commercial data licence is claimed by this provider."
    ),
    reviewed_at=datetime.fromisoformat("2026-11-01T15:18:41+00:00"),
)


@dataclass(frozen=True)
class _Binding:
    source_id: YahooRouteId
    line_id: LineId
    source_name: str
    operator_name: str
    areas: tuple[YahooArea, ...]


# Static reviewed bindings. New source IDs must be registered and matched to the
# canonical catalog, never silently assigned during a refresh.
_BINDINGS: Final[tuple[_Binding, ...]] = (
    _Binding(YahooRouteId('9/9'), LineId('jp:jr_hokkaido:line_f5a9641bce93'), '函館本線[小樽～札幌]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('9/10'), LineId('jp:jr_hokkaido:line_df4ca9ee7c7a'), '函館本線[札幌～岩見沢]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('9/434'), LineId('jp:jr_hokkaido:line_1cdf7c6b7099'), '函館本線[函館～長万部]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('9/435'), LineId('jp:jr_hokkaido:line_725912f9c9d0'), '函館本線[長万部～小樽]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('9/436'), LineId('jp:jr_hokkaido:line_9f6f4fc8b301'), '函館本線[岩見沢～旭川]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('11/0'), LineId('jp:jr_hokkaido:line_1f2f2527218b'), '千歳線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('12/0'), LineId('jp:jr_hokkaido:line_1b3f7157a97f'), '学園都市線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('13/0'), LineId('jp:operator_8161169f094c:line_efe2ab637efc'), '札幌市営東西線', '札幌市交通局', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('14/0'), LineId('jp:operator_8161169f094c:line_b55a3152dc18'), '札幌市営南北線', '札幌市交通局', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('15/0'), LineId('jp:operator_8161169f094c:line_cddc2da78846'), '札幌市営東豊線', '札幌市交通局', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('16/16'), LineId('jp:jr_east:line_e3d21b09cbbb'), '東北本線[福島～仙台]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('16/17'), LineId('jp:jr_east:line_ceee6d61c2cd'), '東北本線[仙台～一ノ関]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('16/440'), LineId('jp:jr_east:line_29088d74cb3a'), '東北本線[黒磯～福島]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('16/441'), LineId('jp:jr_east:line_80254a19923c'), '東北本線[一ノ関～盛岡]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('18/0'), LineId('jp:jr_east:line_e7979ea095d4'), '仙山線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('19/0'), LineId('jp:jr_east:line_3b534d63d808'), '仙石線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('20/0'), LineId('jp:operator_31739cacf719:line_cc1ac570adb3'), '仙台市営南北線', '仙台市交通局', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('21/0'), LineId('jp:jr_east:yamanote'), '山手線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('22/0'), LineId('jp:jr_east:line_5cba7d480417'), '京浜東北根岸線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('25/0'), LineId('jp:jr_east:line_1a18def17ec6'), '湘南新宿ライン', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('27/0'), LineId('jp:jr_east:line_68861e6bc9d4'), '東海道本線[東京～熱海]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('29/0'), LineId('jp:jr_east:line_b40f72600869'), '横須賀線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('31/0'), LineId('jp:jr_east:line_a6253f08e0a1'), '横浜線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('33/0'), LineId('jp:jr_east:line_cf1daefaaa33'), '相模線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('34/0'), LineId('jp:jr_east:line_172efbbe9d16'), '南武線[川崎～立川]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('36/0'), LineId('jp:jr_east:line_aac6494a6de6'), '鶴見線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('37/0'), LineId('jp:jr_east:line_747d13b41788'), '南武線[浜川崎～尻手]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('38/0'), LineId('jp:jr_east:line_0c82b749d285'), '中央線(快速)[東京～高尾]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('40/0'), LineId('jp:jr_east:line_0a0443880f32'), '中央総武線(各停)', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('42/0'), LineId('jp:jr_east:line_b100d0d169c8'), '中央本線[高尾～大月]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('43/43'), LineId('jp:jr_east:line_b8efdc7ffe9a'), '青梅線[立川～青梅]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('43/44'), LineId('jp:jr_east:line_10385e063777'), '青梅線[青梅～奥多摩]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('45/0'), LineId('jp:jr_east:line_62f43f386d81'), '五日市線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('46/46'), LineId('jp:jr_east:line_a2a00f18f5ad'), '宇都宮線[東京～宇都宮]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('46/47'), LineId('jp:jr_east:line_0b12ce3449a3'), '宇都宮線[宇都宮～黒磯]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('48/0'), LineId('jp:jr_east:line_2e8809991508'), '高崎線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('50/0'), LineId('jp:jr_east:line_0015538babb1'), '埼京川越線[羽沢横浜国大～川越]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('52/0'), LineId('jp:jr_east:line_0e382591a9ef'), '八高川越線[八王子～川越]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('54/0'), LineId('jp:jr_east:line_fd41f7ede880'), '八高線[高麗川～高崎]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('55/0'), LineId('jp:jr_east:line_8e4a4c3c8e00'), '日光線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('56/0'), LineId('jp:jr_east:line_3397da3861a6'), '烏山線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('57/0'), LineId('jp:jr_east:line_70fc0a306ef0'), '常磐線(快速)[品川～取手]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('58/0'), LineId('jp:jr_east:line_213c6468afe9'), '常磐線(各停)', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('59/59'), LineId('jp:jr_east:line_e60a0d8e4256'), '常磐線[品川～水戸]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('59/60'), LineId('jp:jr_east:line_c41ccbf7eb97'), '常磐線[水戸～いわき]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('61/0'), LineId('jp:jr_east:line_4425bef3a42e'), '総武線(快速)[東京～千葉]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('62/0'), LineId('jp:jr_east:line_91317b39aef5'), '総武本線[千葉～銚子]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('63/0'), LineId('jp:jr_east:line_6122365b2987'), '内房線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('65/0'), LineId('jp:jr_east:line_8ebaa257ac63'), '外房線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('67/0'), LineId('jp:jr_east:line_00acb78b9e7b'), '成田線[我孫子～成田]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('68/0'), LineId('jp:jr_east:line_e673e389bd51'), '成田線[千葉～成田空港・銚子]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('69/0'), LineId('jp:jr_east:line_945231301f34'), '京葉線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('71/0'), LineId('jp:jr_east:line_70e87c9f6bdf'), '武蔵野線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('74/0'), LineId('jp:jr_east:line_f5b0c4a3be2c'), '東金線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('75/0'), LineId('jp:jr_east:line_12af095e0fad'), '久留里線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('76/0'), LineId('jp:jr_east:line_1fa0b2704985'), '鹿島線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('77/0'), LineId('jp:tobu:line_2ad5f9ac6422'), '東武スカイツリーライン', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('78/0'), LineId('jp:tobu:line_844b252f4684'), '東武亀戸線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('79/0'), LineId('jp:tobu:line_0ffd7f6bc756'), '東武大師線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('80/0'), LineId('jp:tobu:line_52f36a4f53d3'), '東武日光線[南栗橋～東武日光]', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('81/0'), LineId('jp:tobu:line_2e8a7494d811'), '東武アーバンパークライン', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('82/0'), LineId('jp:tobu:line_94b33b082d4f'), '東武東上線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('83/0'), LineId('jp:tobu:line_161291460e55'), '東武越生線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('84/0'), LineId('jp:seibu:line_45cb36b285e9'), '西武池袋線・秩父線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('86/0'), LineId('jp:seibu:line_02a838eb9e45'), '西武新宿線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('87/0'), LineId('jp:seibu:line_66456985b818'), '西武西武園線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('88/0'), LineId('jp:seibu:line_7bd734dcd18d'), '西武国分寺線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('89/0'), LineId('jp:seibu:line_7e4a8b7d5033'), '西武多摩湖線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('90/0'), LineId('jp:seibu:line_fd1bf3ad13e2'), '西武有楽町線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('91/0'), LineId('jp:seibu:line_354248c5c7e4'), '西武豊島線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('92/0'), LineId('jp:seibu:line_f946fb99efeb'), '西武狭山線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('93/0'), LineId('jp:seibu:line_f20220477394'), '西武拝島線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('94/0'), LineId('jp:seibu:line_e8dcfc68797a'), '西武多摩川線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('95/0'), LineId('jp:seibu:line_c9258a4807a7'), '西武山口線', '西武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('96/0'), LineId('jp:keisei:line_e96ffc09d83a'), '京成本線', '京成電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('97/0'), LineId('jp:keisei:line_e05fc743741a'), '京成東成田線', '京成電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('98/0'), LineId('jp:keisei:line_4c0010d67413'), '京成押上線', '京成電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('99/0'), LineId('jp:keisei:line_9c8d3cb5f81a'), '京成千葉線・千原線', '京成電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('101/0'), LineId('jp:keisei:line_3e3f536f0c12'), '京成金町線', '京成電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('102/0'), LineId('jp:keio:line_0cb7d2efef5d'), '京王線', '京王電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('103/0'), LineId('jp:keio:line_3c2563f11b2a'), '京王新線', '京王電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('104/0'), LineId('jp:keio:line_25cd0e31969a'), '京王相模原線', '京王電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('105/0'), LineId('jp:keio:line_5e6de121e906'), '京王高尾線', '京王電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('106/0'), LineId('jp:keio:line_d155e8d8cfa8'), '京王競馬場線', '京王電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('107/0'), LineId('jp:keio:line_da0cc13de9db'), '京王動物園線', '京王電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('108/0'), LineId('jp:keio:line_1690db7527c8'), '京王井の頭線', '京王電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('109/0'), LineId('jp:odakyu:line_fbb4645c43db'), '小田急小田原線', '小田急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('110/0'), LineId('jp:odakyu:line_5f3c44bd632d'), '小田急江ノ島線', '小田急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('111/0'), LineId('jp:odakyu:line_cf199b49d179'), '小田急多摩線', '小田急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('112/0'), LineId('jp:tokyu:line_965f1b018f36'), '東急東横線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('113/0'), LineId('jp:tokyu:line_03de25366237'), '東急目黒線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('114/0'), LineId('jp:tokyu:line_65171aeb7d8c'), '東急田園都市線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('115/0'), LineId('jp:tokyu:line_e9ca4aaa4764'), '東急大井町線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('116/0'), LineId('jp:tokyu:line_4268fea72783'), '東急多摩川線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('117/0'), LineId('jp:tokyu:line_a3e6707bf08d'), '東急池上線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('119/0'), LineId('jp:tokyu:line_4a77de8e8446'), '東急世田谷線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('120/0'), LineId('jp:keikyu:line_78db092fdebd'), '京急本線', '京浜急行電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('121/0'), LineId('jp:keikyu:line_f7fdfd13f776'), '京急空港線', '京浜急行電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('122/0'), LineId('jp:keikyu:line_f45aa080b06c'), '京急大師線', '京浜急行電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('123/0'), LineId('jp:keikyu:line_298c2fc57ddd'), '京急逗子線', '京浜急行電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('124/0'), LineId('jp:keikyu:line_1baf033c4c82'), '京急久里浜線', '京浜急行電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('125/0'), LineId('jp:sotetsu:line_bcfb80c3830e'), '相鉄線', '相模鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('127/0'), LineId('jp:keisei:line_780859fc9d46'), '京成松戸線', '京成電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('128/0'), LineId('jp:toei:line_a8db0e428af5'), '都営浅草線', '東京都交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('129/0'), LineId('jp:toei:line_ea9aaf413955'), '都営三田線', '東京都交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('130/0'), LineId('jp:toei:line_1dee09a8acc9'), '都営新宿線', '東京都交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('131/0'), LineId('jp:toei:line_e0cd13888da5'), '都営大江戸線', '東京都交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('132/0'), LineId('jp:tokyo_metro:line_be3b26a30ba3'), '東京メトロ銀座線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('133/0'), LineId('jp:tokyo_metro:line_fdee53402844'), '東京メトロ丸ノ内線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('134/0'), LineId('jp:tokyo_metro:line_2e7158add59d'), '東京メトロ日比谷線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('135/0'), LineId('jp:tokyo_metro:line_7e014bf48341'), '東京メトロ東西線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('136/0'), LineId('jp:tokyo_metro:line_6257bfc9d174'), '東京メトロ千代田線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('137/0'), LineId('jp:tokyo_metro:line_0c44b7d30049'), '東京メトロ有楽町線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('138/0'), LineId('jp:tokyo_metro:line_23324b895d5a'), '東京メトロ半蔵門線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('139/0'), LineId('jp:tokyo_metro:line_0e87c680e869'), '東京メトロ南北線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('140/0'), LineId('jp:operator_702b41c21dfa:line_103dce814f8a'), 'ブルーライン', '横浜市交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('141/0'), LineId('jp:operator_6a342006a568:line_af9b12dc5c52'), '北総線', '北総鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('142/0'), LineId('jp:operator_447d26ca72bf:line_3910e5befe9f'), '東葉高速線', '東葉高速鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('143/0'), LineId('jp:operator_6792d0f7efc4:line_1b9213f482b7'), '埼玉高速鉄道線', '埼玉高速鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('144/0'), LineId('jp:operator_a76aef032695:line_68e848012d4b'), 'りんかい線', '東京臨海高速鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('145/0'), LineId('jp:operator_cd31dbc1a16a:line_d75228fec192'), '流鉄流山線', '流鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('146/0'), LineId('jp:operator_6081aa5cd8cc:line_9e2a695b9807'), '秩父鉄道線', '秩父鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('147/0'), LineId('jp:operator_5dbad158fdda:line_a0694844624f'), '箱根登山鉄道線', '小田急箱根', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('148/0'), LineId('jp:operator_a55ec17bd0d8:line_794f44d2ebb9'), '江ノ島電鉄線', '江ノ島電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('149/0'), LineId('jp:operator_5d7fcdd1adb0:line_dda9ee333198'), '小湊鉄道線', '小湊鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('150/0'), LineId('jp:operator_dc464cdb574f:line_ad2db773b7e9'), 'いすみ鉄道線', 'いすみ鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('151/0'), LineId('jp:operator_11f4188b9203:line_a01e06a52e81'), '富士急行線', '富士山麓電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('153/0'), LineId('jp:operator_32276b8fdb14:line_c676b89db19c'), '伊豆箱根鉄道大雄山線', '伊豆箱根鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('154/0'), LineId('jp:operator_4e61cd883b63:line_8798b239dcc2'), '東京モノレール線', '東京モノレール', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('155/0'), LineId('jp:operator_f8d6fa63c406:line_1491b697c0f6'), '湘南モノレール線', '湘南モノレール', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('156/0'), LineId('jp:operator_9c0aa569e1ea:line_d475b8504cee'), '多摩都市モノレール線', '多摩都市モノレール', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('157/0'), LineId('jp:operator_ba7af007bad1:line_0160516ebf3d'), '千葉都市モノレール線', '千葉都市モノレール', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('159/0'), LineId('jp:operator_1e72c4980229:line_9c1d2f492121'), 'シーサイドライン', '横浜シーサイドライン', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('160/0'), LineId('jp:operator_c0a210bf19c5:line_cbfd3a81aaf1'), 'ゆりかもめ線', 'ゆりかもめ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('161/0'), LineId('jp:operator_71599a1871e0:line_04e2c2ef0ab8'), 'ニューシャトル', '埼玉新都市交通', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('162/0'), LineId('jp:jr_east:line_d4b0ab9769dc'), '吾妻線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('163/0'), LineId('jp:jr_east:line_0c20ece36b83'), '伊東線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('164/0'), LineId('jp:jr_east:line_04f701c8a04a'), '上越線[高崎～水上]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('165/0'), LineId('jp:jr_east:line_5056ef82ff2c'), '信越本線[高崎～横川]', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('166/0'), LineId('jp:jr_east:line_9f42712495ae'), '水郡線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('167/0'), LineId('jp:jr_east:line_0cead7e02b77'), '水戸線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('168/0'), LineId('jp:jr_east:line_e69fd4909061'), '両毛線', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('169/0'), LineId('jp:tobu:line_fe50875b7747'), '東武宇都宮線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('170/0'), LineId('jp:tobu:line_cc08364ffb5c'), '東武鬼怒川線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('171/0'), LineId('jp:tobu:line_9ad5856fe549'), '東武小泉線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('172/0'), LineId('jp:tobu:line_9f8e325ba38c'), '東武佐野線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('173/0'), LineId('jp:tobu:line_df6ce7d234f5'), '東武桐生線', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('175/0'), LineId('jp:operator_f3e91418d4f4:line_4c486a2fc190'), '関東鉄道常総線', '関東鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('176/0'), LineId('jp:operator_f3e91418d4f4:line_e323c07b223c'), '関東鉄道竜ケ崎線', '関東鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('177/0'), LineId('jp:operator_4eb45e1671e5:line_20949a3245a4'), 'ひたちなか海浜鉄道湊線', 'ひたちなか海浜鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('179/0'), LineId('jp:operator_9151c159eadd:line_d489665c878e'), '上信電鉄線', '上信電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('180/0'), LineId('jp:operator_738ce5251950:line_deaaad1a6442'), '上毛電鉄線', '上毛電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('181/0'), LineId('jp:operator_2438e8238cc0:line_5c0f8347a337'), '銚子電鉄線', '銚子電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('182/0'), LineId('jp:operator_f9e2538152f1:line_53c022f0687c'), '伊豆急行線', '伊豆急行', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('183/0'), LineId('jp:operator_bcd8d52912a3:line_3f19906dde12'), '会津鉄道線', '会津鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('184/0'), LineId('jp:operator_bfae1a68b891:line_18bc59e91067'), '野岩鉄道会津鬼怒川線', '野岩鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('185/0'), LineId('jp:operator_8b14dd78fe16:line_6398540c9086'), 'わたらせ渓谷鐵道線', 'わたらせ渓谷鐵道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('186/0'), LineId('jp:operator_a19dd34f5197:line_24bfd6b50b14'), '鹿島臨海鉄道大洗鹿島線', '鹿島臨海鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('187/0'), LineId('jp:operator_d5b304d28ccf:line_449f28b2e10c'), '真岡鐵道線', '真岡鐵道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('188/0'), LineId('jp:operator_7b52ec133164:line_64fd6d30cc4c'), 'ディズニーリゾートライン', '舞浜リゾートライン', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('189/0'), LineId('jp:operator_dc6243ab938e:line_052b6be69554'), '山万ユーカリが丘線', '山万', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('190/0'), LineId('jp:toei:line_deca9144c6f9'), '都電荒川線', '東京都交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('192/192'), LineId('jp:jr_central:line_6fc336cf9ff1'), '東海道本線[熱海～豊橋]', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('192/193'), LineId('jp:jr_central:line_f8d0edf56619'), '東海道本線[豊橋～米原]', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('195/0'), LineId('jp:jr_central:line_d7896ac10524'), '御殿場線', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('196/0'), LineId('jp:jr_central:line_38a7c5d61048'), '身延線', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('197/0'), LineId('jp:jr_central:line_fe938e24f4f9'), '飯田線', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('199/0'), LineId('jp:jr_central:line_d1cf7125827b'), '武豊線', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('200/0'), LineId('jp:jr_central:line_c41689a43fa0'), '高山本線[岐阜～猪谷]', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('201/201'), LineId('jp:jr_central:line_5f4d2a9ef7e9'), '中央本線[名古屋～中津川]', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('201/202'), LineId('jp:jr_central:line_5cc20b8e5648'), '中央本線[中津川～塩尻]', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('203/0'), LineId('jp:jr_central:line_1b813d15693b'), '太多線', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('204/0'), LineId('jp:jr_central:line_e7dbe9beead2'), '関西本線[名古屋～亀山]', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('205/0'), LineId('jp:jr_central:line_bbddf7bbb005'), '紀勢本線[亀山～新宮]', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('206/0'), LineId('jp:jr_central:line_110504ba73d0'), '参宮線', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('207/0'), LineId('jp:jr_central:line_856f2cc50a8c'), '名松線', 'JR東海', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('208/0'), LineId('jp:meitetsu:line_4a34e1bd4cf5'), '名鉄名古屋本線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('209/0'), LineId('jp:meitetsu:line_432cd30abf37'), '名鉄西尾線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('210/0'), LineId('jp:meitetsu:line_7d2e158abcf2'), '名鉄三河線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('211/0'), LineId('jp:meitetsu:line_7666a844336e'), '名鉄豊田線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('212/0'), LineId('jp:meitetsu:line_6a4362997350'), '名鉄蒲郡線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('213/0'), LineId('jp:meitetsu:line_6096e0a53bec'), '名鉄常滑線・空港線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('214/0'), LineId('jp:meitetsu:line_21bd01e99894'), '名鉄築港線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('215/0'), LineId('jp:meitetsu:line_a75b30817184'), '名鉄河和線・知多新線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('217/0'), LineId('jp:meitetsu:line_fa5360b12447'), '名鉄瀬戸線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('218/0'), LineId('jp:meitetsu:line_8c96a5064f5a'), '名鉄小牧線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('219/0'), LineId('jp:meitetsu:line_e3a6d0b3a7a9'), '名鉄各務原線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('220/0'), LineId('jp:meitetsu:line_316bf1c335dc'), '名鉄犬山線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('221/0'), LineId('jp:meitetsu:line_67eaaa1a3dd4'), '名鉄広見線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('222/0'), LineId('jp:meitetsu:line_3bd54d7ebaec'), '名鉄津島線・尾西線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('224/0'), LineId('jp:meitetsu:line_12b330a48d24'), '名鉄竹鼻・羽島線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('226/0'), LineId('jp:meitetsu:line_1d5b5befe473'), '名鉄豊川線', '名古屋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('230/0'), LineId('jp:kintetsu:nagoya'), '近鉄名古屋線', '近畿日本鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('231/0'), LineId('jp:kintetsu:suzuka'), '近鉄鈴鹿線', '近畿日本鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('233/0'), LineId('jp:kintetsu:yunoyama'), '近鉄湯の山線', '近畿日本鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('237/0'), LineId('jp:kintetsu:yamada_toba_shima_group'), '近鉄山田線・鳥羽線・志摩線', '近畿日本鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('240/0'), LineId('jp:operator_f28d789a1fa7:line_f2d919c931ae'), '名古屋市営東山線', '名古屋市交通局', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('241/0'), LineId('jp:operator_f28d789a1fa7:line_205e60be39e6'), '名古屋市営名城線・名港線', '名古屋市交通局', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('242/0'), LineId('jp:operator_f28d789a1fa7:line_ce492247f6f9'), '名古屋市営鶴舞線', '名古屋市交通局', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('243/0'), LineId('jp:operator_f28d789a1fa7:line_0330f591536d'), '名古屋市営桜通線', '名古屋市交通局', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('244/0'), LineId('jp:operator_32276b8fdb14:line_78861461a9b8'), '伊豆箱根鉄道駿豆線', '伊豆箱根鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('245/0'), LineId('jp:operator_0b87f3e58a9e:line_93bde51b0821'), '岳南鉄道線', '岳南電車', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('246/0'), LineId('jp:operator_08f80879f813:line_d5d929b55715'), '静岡鉄道線', '静岡鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('247/0'), LineId('jp:operator_f1ebb68c248c:line_57cd8e93c4ab'), '大井川鉄道大井川本線', '大井川鐵道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('249/0'), LineId('jp:operator_a50e13d9e5cf:line_2dcea38866e6'), '遠州鉄道線', '遠州鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('250/0'), LineId('jp:operator_b2e2e0b91c2a:line_b37bc16f9102'), '豊橋鉄道渥美線', '豊橋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('251/0'), LineId('jp:operator_b2e2e0b91c2a:line_71d741f3b3c5'), '豊橋鉄道市内線', '豊橋鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('252/0'), LineId('jp:operator_3294a89d1d31:line_0545ed2d44d9'), '三岐鉄道三岐線', '三岐鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('253/0'), LineId('jp:operator_a81d100fc27c:line_4f8a47643927'), '城北線', 'JR東海交通事業', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('254/0'), LineId('jp:operator_267896e04f84:line_6a1f5de5d7c5'), '天竜浜名湖鉄道線', '天竜浜名湖鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('256/0'), LineId('jp:operator_d1044d8ab9a2:line_7a475ba7711d'), '樽見鉄道線', '樽見鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('257/0'), LineId('jp:operator_4b679c20c842:line_c3796b93c397'), '明知鉄道線', '明知鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('258/0'), LineId('jp:operator_598a47b46589:line_90475f6f77e5'), '長良川鉄道越美南線', '長良川鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('259/0'), LineId('jp:operator_b7bdfca47747:line_56225b4792b8'), '愛知環状鉄道線', '愛知環状鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('260/0'), LineId('jp:operator_52ec598970c8:line_31bf04c6272b'), '伊勢鉄道線', '伊勢鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('262/0'), LineId('jp:operator_8b75f280912e:line_bf7dbb16e16e'), 'ゆとりーとライン', '名古屋ガイドウェイバス', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('263/0'), LineId('jp:jr_west:osaka_loop'), '大阪環状線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('264/0'), LineId('jp:jr_west:yumesaki'), 'JRゆめ咲線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('265/0'), LineId('jp:jr_west:takarazuka'), 'JR宝塚線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('266/0'), LineId('jp:jr_west:biwako'), '琵琶湖線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('267/0'), LineId('jp:jr_west:kyoto'), 'JR京都線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('268/0'), LineId('jp:jr_west:kosei'), '湖西線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('269/0'), LineId('jp:jr_west:kusatsu'), '草津線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('270/0'), LineId('jp:jr_west:sagano'), '嵯峨野線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('271/0'), LineId('jp:jr_west:gakkentoshi'), '学研都市線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('272/0'), LineId('jp:jr_west:tozai'), 'JR東西線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('273/0'), LineId('jp:jr_west:kobe'), 'JR神戸線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('274/0'), LineId('jp:jr_west:hanwa'), '阪和線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('275/0'), LineId('jp:jr_west:kisei'), '紀勢本線[和歌山～和歌山市]', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('276/0'), LineId('jp:jr_west:hagoromo'), '羽衣線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('277/0'), LineId('jp:jr_west:yamatoji'), '大和路線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('278/0'), LineId('jp:jr_west:kansai'), '関西本線[亀山～加茂]', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('279/0'), LineId('jp:jr_west:nara'), '奈良線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('280/0'), LineId('jp:jr_west:manyomahoroba'), '桜井線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('281/0'), LineId('jp:jr_west:wakayama'), '和歌山線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('282/0'), LineId('jp:jr_west:kansai_airport'), '関西空港線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('283/0'), LineId('jp:jr_west:wadamisaki'), '和田岬線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('284/0'), LineId('jp:kintetsu:osaka'), '近鉄大阪線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('285/0'), LineId('jp:kintetsu:nara'), '近鉄奈良線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('287/0'), LineId('jp:kintetsu:keihanna'), '近鉄けいはんな線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('288/0'), LineId('jp:kintetsu:kyoto'), '近鉄京都線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('289/0'), LineId('jp:kintetsu:kashihara'), '近鉄橿原線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('290/0'), LineId('jp:kintetsu:tenri'), '近鉄天理線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('291/0'), LineId('jp:kintetsu:shigi'), '近鉄信貴線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('292/0'), LineId('jp:kintetsu:ikoma'), '近鉄生駒線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('293/0'), LineId('jp:kintetsu:tawaramoto'), '近鉄田原本線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('295/0'), LineId('jp:kintetsu:minami_osaka'), '近鉄南大阪線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('296/0'), LineId('jp:kintetsu:domyoji'), '近鉄道明寺線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('297/0'), LineId('jp:kintetsu:gose'), '近鉄御所線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('298/0'), LineId('jp:kintetsu:yoshino'), '近鉄吉野線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('299/0'), LineId('jp:kintetsu:nagano'), '近鉄長野線', '近畿日本鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('300/0'), LineId('jp:keihan:main_nakanoshima_group'), '京阪本線・中之島線', '京阪電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('301/0'), LineId('jp:keihan:katano'), '京阪交野線', '京阪電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('302/0'), LineId('jp:keihan:uji'), '京阪宇治線', '京阪電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('303/0'), LineId('jp:keihan:keishin'), '京阪京津線', '京阪電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('304/0'), LineId('jp:keihan:ishiyama_sakamoto'), '京阪石山坂本線', '京阪電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('306/0'), LineId('jp:hankyu:kyoto_main'), '阪急京都本線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('307/0'), LineId('jp:hankyu:itami'), '阪急伊丹線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('308/0'), LineId('jp:hankyu:imazu'), '阪急今津線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('309/0'), LineId('jp:hankyu:koyo'), '阪急甲陽線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('310/0'), LineId('jp:hankyu:kobe_main'), '阪急神戸本線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('311/0'), LineId('jp:hankyu:takarazuka_main'), '阪急宝塚本線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('312/0'), LineId('jp:hankyu:mino'), '阪急箕面線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('313/0'), LineId('jp:hankyu:senri'), '阪急千里線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('314/0'), LineId('jp:hankyu:arashiyama'), '阪急嵐山線', '阪急電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('315/0'), LineId('jp:hanshin:main'), '阪神本線', '阪神電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('316/0'), LineId('jp:hanshin:namba'), '阪神なんば線', '阪神電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('317/0'), LineId('jp:hanshin:mukogawa'), '阪神武庫川線', '阪神電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('318/0'), LineId('jp:operator_9e7399db41b2:line_a4f8893160fb'), '京都市営烏丸線', '京都市交通局', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('319/0'), LineId('jp:operator_9e7399db41b2:line_bc4a5426cc32'), '京都市営東西線', '京都市交通局', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('320/0'), LineId('jp:osaka_metro:new_tram'), 'ニュートラム', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('321/0'), LineId('jp:osaka_metro:midosuji'), '大阪メトロ御堂筋線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('322/0'), LineId('jp:osaka_metro:tanimachi'), '大阪メトロ谷町線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('323/0'), LineId('jp:osaka_metro:yotsubashi'), '大阪メトロ四つ橋線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('324/0'), LineId('jp:osaka_metro:chuo'), '大阪メトロ中央線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('325/0'), LineId('jp:osaka_metro:sennichimae'), '大阪メトロ千日前線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('326/0'), LineId('jp:osaka_metro:sakaisuji'), '大阪メトロ堺筋線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('327/0'), LineId('jp:osaka_metro:nagahori_tsurumi_ryokuchi'), '大阪メトロ長堀鶴見緑地線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('328/0'), LineId('jp:operator_9d32346c47f5:line_7869e8fca274'), '神戸市営西神・山手線・北神線', '神戸市交通局', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('329/0'), LineId('jp:operator_9d32346c47f5:line_5131f68f3aa9'), '神戸市営海岸線', '神戸市交通局', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('330/0'), LineId('jp:jr_west:ako'), '赤穂線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('331/421'), LineId('jp:jr_west:sanin'), '山陰本線[鳥取～益田]', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('331/422'), LineId('jp:jr_west:sanin'), '山陰本線[益田～下関]', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('332/417'), LineId('jp:jr_west:sanyo'), '山陽本線[姫路～三原]', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('332/418'), LineId('jp:jr_west:sanyo'), '山陽本線[三原～岩国]', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('332/419'), LineId('jp:jr_west:sanyo'), '山陽本線[岩国～下関]', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('333/0'), LineId('jp:jr_west:kinokuni'), 'きのくに線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('334/0'), LineId('jp:jr_west:kakogawa'), '加古川線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('335/0'), LineId('jp:jr_west:kishin'), '姫新線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('336/0'), LineId('jp:jr_west:bantan'), '播但線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('338/0'), LineId('jp:jr_west:maizuru'), '舞鶴線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('339/0'), LineId('jp:nankai:main'), '南海本線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('340/0'), LineId('jp:nankai:airport'), '南海空港線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('341/0'), LineId('jp:nankai:takashinohama'), '南海高師浜線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('342/0'), LineId('jp:nankai:tanagawa'), '南海多奈川線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('343/0'), LineId('jp:nankai:kada'), '南海加太線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('344/0'), LineId('jp:nankai:wakayama_port'), '南海和歌山港線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('346/0'), LineId('jp:nankai:koya'), '南海高野線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('347/0'), LineId('jp:nankai:shiomibashi'), '南海汐見橋線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('348/0'), LineId('jp:nankai:semboku'), '南海泉北線', '南海電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('349/0'), LineId('jp:operator_16326efea874:line_cd647bd950b9'), '北大阪急行線', '北大阪急行電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('350/0'), LineId('jp:operator_7d79832a58e4:line_673275e6dd87'), '神戸電鉄有馬・三田線', '神戸電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('352/0'), LineId('jp:operator_7d79832a58e4:line_f2c2f7b76cd0'), '神戸電鉄公園都市線', '神戸電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('353/0'), LineId('jp:operator_7d79832a58e4:line_009fcecad4c7'), '神戸電鉄粟生線', '神戸電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('354/0'), LineId('jp:operator_c448fb6c1aa7:line_442fef333528'), '山陽電鉄本線', '山陽電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('355/0'), LineId('jp:operator_c448fb6c1aa7:line_3a51a3c6adea'), '山陽電鉄網干線', '山陽電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('358/0'), LineId('jp:operator_ea4f15e9fc2b:line_84134807c83d'), '嵐電', '京福電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('360/0'), LineId('jp:operator_a5cfdf86be97:line_5083f9018a22'), '叡山電鉄線', '叡山電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('362/0'), LineId('jp:operator_06d5e1a11988:line_14d2f5ee38c7'), '阪堺電気軌道線', '阪堺電気軌道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('364/0'), LineId('jp:operator_c2126eea4516:line_16a6cf6d1a8d'), '近江鉄道線', '近江鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('367/0'), LineId('jp:operator_f38f8a1d2a93:line_abb36bb5d69f'), '水間鉄道線', '水間鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('369/0'), LineId('jp:operator_9f67cbafaf9f:line_7c170927a11b'), '紀州鉄道線', '紀州鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('370/0'), LineId('jp:operator_852320543083:line_ec855d17b8b4'), '能勢電鉄線', '能勢電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('374/0'), LineId('jp:operator_f479946567b2:line_4ba7d5317b42'), '京都丹後鉄道宮福線', 'ウィラートレインズ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('375/0'), LineId('jp:operator_f479946567b2:line_86e6bbf18eb0'), '京都丹後鉄道宮舞線・宮豊線', 'ウィラートレインズ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('376/0'), LineId('jp:operator_e69260e6511d:line_04a01442862e'), '信楽高原鐵道線', '信楽高原鐵道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('377/0'), LineId('jp:operator_fd5861b1f11d:line_c5178837f450'), '北条鉄道線', '北条鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('379/0'), LineId('jp:operator_c14d6df360ed:line_4e2155c2696a'), '智頭急行線', '智頭急行', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('380/0'), LineId('jp:osaka_monorail:main'), '大阪モノレール線', '大阪モノレール', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('384/0'), LineId('jp:operator_61d8b48a9755:line_6cb3584b7e04'), 'ポートライナー', '神戸新交通', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('385/0'), LineId('jp:operator_61d8b48a9755:line_bdaff5a95cfb'), '六甲ライナー', '神戸新交通', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('386/386'), LineId('jp:jr_kyushu:line_f3140c055eca'), '鹿児島本線[門司港～大牟田]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('386/387'), LineId('jp:jr_kyushu:line_415945c3fe6f'), '鹿児島本線[大牟田～八代]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('388/519'), LineId('jp:jr_kyushu:line_5f0c9b5800c7'), '日豊本線[小倉～大分]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('388/520'), LineId('jp:jr_kyushu:line_d66786899d94'), '日豊本線[大分～宮崎]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('388/633'), LineId('jp:jr_kyushu:line_d3b4dff1ea2b'), '日豊本線[宮崎～鹿児島中央]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('389/0'), LineId('jp:jr_kyushu:line_a91543b41400'), '福北ゆたか線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('390/0'), LineId('jp:jr_kyushu:line_76073dfb1f8f'), '原田線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('391/0'), LineId('jp:jr_kyushu:line_b65cfb71db0a'), '若松線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('392/0'), LineId('jp:jr_kyushu:line_99c1d26b82c1'), '香椎線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('394/0'), LineId('jp:jr_kyushu:line_1991513e4903'), '日田彦山線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('395/0'), LineId('jp:jr_kyushu:line_477de81cb392'), '後藤寺線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('396/0'), LineId('jp:jr_west:hakata_minami'), '博多南線', 'JR西日本', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('397/0'), LineId('jp:operator_afa22347b935:line_10f28d664b10'), '福岡市営空港線', '福岡市交通局', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('398/0'), LineId('jp:operator_afa22347b935:line_11ed84bd24c5'), '福岡市営箱崎線', '福岡市交通局', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('400/0'), LineId('jp:operator_f28d789a1fa7:line_f3aba768460b'), '名古屋市営上飯田線', '名古屋市交通局', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('401/0'), LineId('jp:operator_d2d012d773b3:line_3b169884afee'), 'みなとみらい線', '横浜高速鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('402/0'), LineId('jp:tokyu:line_ad0499ddb335'), '東急こどもの国線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('408/0'), LineId('jp:operator_72ff2153b0a4:line_04e0461153f9'), 'リニモ', '愛知高速交通', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('409/0'), LineId('jp:operator_afa22347b935:line_927daf7c388e'), '福岡市営七隈線', '福岡市交通局', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('412/0'), LineId('jp:operator_aeb5d1451041:line_6925d35402ec'), 'つくばエクスプレス線', '首都圏新都市鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('413/0'), LineId('jp:operator_7b911b6ce6c0:line_4e3d73d92dac'), '西鉄天神大牟田線', '西日本鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('414/0'), LineId('jp:operator_7b911b6ce6c0:line_ab3438d1ea2b'), '西鉄太宰府線', '西日本鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('415/0'), LineId('jp:operator_7b911b6ce6c0:line_18c851797e51'), '西鉄甘木線', '西日本鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('416/0'), LineId('jp:operator_7b911b6ce6c0:line_872659be7aa0'), '西鉄貝塚線', '西日本鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('423/0'), LineId('jp:jr_hokkaido:line_d3463a409618'), '宗谷本線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('424/0'), LineId('jp:jr_hokkaido:line_903b6ae2bcf1'), '石北本線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('425/0'), LineId('jp:jr_hokkaido:line_e15dbba9f742'), '釧網本線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('427/0'), LineId('jp:jr_hokkaido:line_8d3c07c9b705'), '根室本線[滝川～富良野]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('428/0'), LineId('jp:jr_hokkaido:line_f2e7bd75baa6'), '根室本線[新得～釧路]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('429/0'), LineId('jp:jr_hokkaido:line_ea3437497425'), '富良野線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('430/0'), LineId('jp:jr_hokkaido:line_6664f6717ccf'), '石勝線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('431/0'), LineId('jp:jr_hokkaido:line_d2d4151ea5a8'), '日高本線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('432/432'), LineId('jp:jr_hokkaido:line_a60d2835b018'), '室蘭本線[長万部～苫小牧]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('432/433'), LineId('jp:jr_hokkaido:line_20bf90818f12'), '室蘭本線[苫小牧～岩見沢]', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('439/0'), LineId('jp:jr_hokkaido:line_0ec04639e5c5'), '花咲線', 'JR北海道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('443/0'), LineId('jp:jr_east:line_0185e17df1a8'), '常磐線[いわき～仙台]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('444/0'), LineId('jp:jr_east:line_d19d97fd53c3'), '磐越東線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('445/0'), LineId('jp:jr_east:line_01df1690dc1f'), '磐越西線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('446/0'), LineId('jp:jr_east:line_69a3d48ab6bd'), '只見線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('447/0'), LineId('jp:jr_east:line_feffec40264a'), '石巻線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('448/0'), LineId('jp:jr_east:line_7388a39f1b28'), '気仙沼線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('449/0'), LineId('jp:jr_east:line_d2cafc29c210'), '大船渡線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('450/0'), LineId('jp:jr_east:line_7318438435c1'), '釜石線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('451/0'), LineId('jp:jr_east:line_276831b19018'), '山田線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('453/0'), LineId('jp:jr_east:line_ec4ddaa3da53'), '八戸線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('454/0'), LineId('jp:jr_east:line_1850c06bd3e2'), '大湊線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('455/0'), LineId('jp:jr_east:line_d80046cd016f'), '山形線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('456/456'), LineId('jp:jr_east:line_4bf16efc14a2'), '奥羽本線[新庄～秋田]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('456/457'), LineId('jp:jr_east:line_9612b874038e'), '奥羽本線[秋田～青森]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('458/0'), LineId('jp:jr_east:line_42587e436867'), '米坂線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('459/0'), LineId('jp:jr_east:line_e2382bc8a1d0'), '左沢線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('460/0'), LineId('jp:jr_east:line_170b89280b60'), '陸羽東線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('461/0'), LineId('jp:jr_east:line_4f0c53cac8b3'), '陸羽西線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('462/0'), LineId('jp:jr_east:line_1134007cbbc2'), '北上線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('463/0'), LineId('jp:jr_east:line_7442b107c7b5'), '田沢湖線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('464/0'), LineId('jp:jr_east:line_295aa8d32036'), '花輪線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('465/0'), LineId('jp:jr_east:line_cd047b11ddf9'), '男鹿線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('466/0'), LineId('jp:jr_east:line_1e1df3919bf1'), '五能線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('467/0'), LineId('jp:jr_east:line_12c5fb07b099'), '津軽線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('468/625'), LineId('jp:jr_east:line_433ab0a40607'), '羽越本線[新津～酒田]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('468/626'), LineId('jp:jr_east:line_bf6dc999b218'), '羽越本線[酒田～秋田]', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('469/0'), LineId('jp:jr_east:line_127dec402b73'), '白新線', 'JR東日本', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('470/0'), LineId('jp:jr_east:line_925481eec928'), '中央本線[大月～塩尻]', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('471/0'), LineId('jp:jr_east:line_e8d90dcc0a91'), '小海線', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('472/0'), LineId('jp:jr_east:line_9d86c0fb4662'), '篠ノ井線', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('473/0'), LineId('jp:jr_east:line_26a1c72a8a77'), '大糸線[松本～南小谷]', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('474/0'), LineId('jp:jr_east:line_ac3a24dc269f'), '信越本線[直江津～新潟]', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('476/0'), LineId('jp:jr_east:line_a1eae8f6261d'), '飯山線', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('477/0'), LineId('jp:jr_east:line_5fa34fe030ff'), '越後線', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('478/0'), LineId('jp:jr_east:line_682562788971'), '弥彦線', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('479/0'), LineId('jp:jr_east:line_4f1048c540e3'), '上越線[水上～長岡]', 'JR東日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('481/0'), LineId('jp:jr_west:hokuriku'), '北陸本線', 'JR西日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('483/0'), LineId('jp:jr_west:etsumi_hoku'), '九頭竜線', 'JR西日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('484/0'), LineId('jp:jr_west:nanao'), '七尾線', 'JR西日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('485/0'), LineId('jp:jr_west:himi'), '氷見線', 'JR西日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('486/0'), LineId('jp:jr_west:johana'), '城端線', 'JR西日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('487/0'), LineId('jp:jr_west:takayama'), '高山本線[猪谷～富山]', 'JR西日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('488/0'), LineId('jp:jr_west:oito'), '大糸線[南小谷～糸魚川]', 'JR西日本', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('489/0'), LineId('jp:jr_west:obama'), '小浜線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('490/0'), LineId('jp:jr_west:fukuchiyama'), '福知山線[篠山口～福知山]', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('491/0'), LineId('jp:jr_west:seto_ohashi'), '瀬戸大橋線[岡山～児島]', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('492/0'), LineId('jp:jr_west:uno_minato'), '宇野線[茶屋町～宇野]', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('493/0'), LineId('jp:jr_west:tsuyama'), '津山線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('494/0'), LineId('jp:jr_west:inbi'), '因美線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('495/0'), LineId('jp:jr_west:momotaro'), '吉備線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('496/0'), LineId('jp:jr_west:hakubi'), '伯備線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('497/0'), LineId('jp:jr_west:sakai'), '境線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('498/0'), LineId('jp:jr_west:geibi'), '芸備線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('499/0'), LineId('jp:jr_west:fukuen'), '福塩線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('500/0'), LineId('jp:jr_west:kisuki'), '木次線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('502/0'), LineId('jp:jr_west:kure'), '呉線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('503/0'), LineId('jp:jr_west:kabe'), '可部線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('504/0'), LineId('jp:jr_west:gantoku'), '岩徳線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('505/0'), LineId('jp:jr_west:ube'), '宇部線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('506/0'), LineId('jp:jr_west:onoda'), '小野田線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('507/0'), LineId('jp:jr_west:yamaguchi'), '山口線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('508/0'), LineId('jp:jr_west:mine'), '美祢線', 'JR西日本', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('509/0'), LineId('jp:jr_shikoku:line_e0e7a7ecebce'), '瀬戸大橋線[児島～高松]', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('510/510'), LineId('jp:jr_shikoku:line_5c01e50604fa'), '予讃線[高松～松山]', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('510/511'), LineId('jp:jr_shikoku:line_33d69f3cb472'), '予讃線[松山～宇和島]', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('512/512'), LineId('jp:jr_shikoku:line_53f79739e96a'), '土讃線[多度津～高知]', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('512/513'), LineId('jp:jr_shikoku:line_55f63f4ebffa'), '土讃線[高知～窪川]', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('514/0'), LineId('jp:jr_shikoku:line_d43dbbda1b8c'), '予土線', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('515/0'), LineId('jp:jr_shikoku:line_71d4292395b3'), '高徳線', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('516/0'), LineId('jp:jr_shikoku:line_06ed0930edd2'), '鳴門線', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('517/0'), LineId('jp:jr_shikoku:line_85cc278aea6c'), '徳島線', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('518/0'), LineId('jp:jr_shikoku:line_d5da40ac8c32'), '牟岐線', 'JR四国', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('521/0'), LineId('jp:jr_kyushu:line_962b6c53fbee'), '鹿児島本線[川内～鹿児島中央]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('522/0'), LineId('jp:jr_kyushu:line_fc641594100c'), '筑肥線[姪浜～西唐津]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('523/0'), LineId('jp:jr_kyushu:line_2ec221867bd9'), '筑肥線[西唐津～伊万里]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('524/0'), LineId('jp:jr_kyushu:line_1376bbc3fd88'), '唐津線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('525/0'), LineId('jp:jr_kyushu:line_089629e14f6f'), '長崎本線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('526/0'), LineId('jp:jr_kyushu:line_d5bf915c9134'), '佐世保線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('527/0'), LineId('jp:jr_kyushu:line_ad5d509e5a94'), '大村線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('528/0'), LineId('jp:jr_kyushu:line_9be42162b08d'), '久大本線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('529/0'), LineId('jp:jr_kyushu:line_f75f85031f44'), '豊肥本線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('530/0'), LineId('jp:jr_kyushu:line_525bbea82cdf'), '三角線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('531/0'), LineId('jp:jr_kyushu:line_40d04aff0de2'), '肥薩線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('532/0'), LineId('jp:jr_kyushu:line_b9aa383de1a4'), '吉都線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('533/0'), LineId('jp:jr_kyushu:line_9a594a332514'), '宮崎空港線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('534/0'), LineId('jp:jr_kyushu:line_51bea35832cc'), '日南線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('535/0'), LineId('jp:jr_kyushu:line_41495645cc53'), '指宿枕崎線', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('537/0'), LineId('jp:osaka_metro:imazatosuji'), '大阪メトロ今里筋線', '大阪メトロ', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('539/0'), LineId('jp:operator_702b41c21dfa:line_7332f720bd3d'), 'グリーンライン', '横浜市交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('540/0'), LineId('jp:tokyo_metro:line_5a2b7458bcb0'), '東京メトロ副都心線', '東京メトロ', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('541/0'), LineId('jp:toei:line_86045934bbac'), '日暮里・舎人ライナー', '東京都交通局', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('542/0'), LineId('jp:operator_6270420e8524:line_ce6dcc191adb'), '仙台空港アクセス線', '仙台空港鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('543/0'), LineId('jp:operator_3f08e3327220:line_f3ed2cf0c3d5'), '土佐くろしお鉄道中村・宿毛線', '土佐くろしお鉄道', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('544/0'), LineId('jp:operator_3f08e3327220:line_ae624e7552d0'), '土佐くろしお鉄道ごめん・なはり線', '土佐くろしお鉄道', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('545/0'), LineId('jp:operator_b0180e591641:line_2c44151b7903'), '札幌市電', '札幌市交通事業振興公社', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('546/0'), LineId('jp:operator_626645833cf9:line_e91f23700b85'), '函館市電', '函館市企業局', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('547/0'), LineId('jp:jr_west:sanin'), '山陰本線[園部～鳥取]', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('548/0'), LineId('jp:operator_a0cb53a6ff8b:line_456cd2730424'), 'あおなみ線', '名古屋臨海高速鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('549/0'), LineId('jp:operator_3749c81128a8:line_9436963e10b6'), '阿武隈急行線', '阿武隈急行', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('550/0'), LineId('jp:operator_3563f48da25d:line_2cbf6b3d44a4'), '福島交通飯坂線', '福島交通', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('551/0'), LineId('jp:operator_a18cfea7a802:line_faffbafa96c0'), '山形鉄道フラワー長井線', '山形鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('552/0'), LineId('jp:operator_32dfba745434:line_8275dff6811d'), '三陸鉄道リアス線', '三陸鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('554/0'), LineId('jp:operator_3a763fc5766d:line_0a25442be26b'), 'いわて銀河鉄道線', 'IGRいわて銀河鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('555/0'), LineId('jp:operator_7f978ea6b673:line_cbf2e0f7d7c6'), '由利高原鉄道線', '由利高原鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('556/0'), LineId('jp:operator_2750fc45c4a8:line_638ba02cde34'), '秋田内陸線', '秋田内陸縦貫鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('557/0'), LineId('jp:operator_d8e2590c967c:line_f7d785c1454f'), '青い森鉄道線', '青い森鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('558/0'), LineId('jp:operator_8779cd25763a:line_1047b15f4f25'), '弘南鉄道弘南線', '弘南鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('559/0'), LineId('jp:operator_8779cd25763a:line_18f6f232f426'), '弘南鉄道大鰐線', '弘南鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('560/0'), LineId('jp:operator_2648e0bd4c0c:line_a0693e179e6a'), '津軽鉄道線', '津軽鉄道', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('562/0'), LineId('jp:operator_51157fdc3ba6:line_f83817037abb'), '芝山鉄道線', '芝山鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('563/0'), LineId('jp:operator_b9db3e1e1b06:line_a5b9987dca5e'), '養老鉄道線', '養老鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('564/0'), LineId('jp:operator_3294a89d1d31:line_99e1a36826d6'), '三岐鉄道北勢線', '三岐鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('565/0'), LineId('jp:operator_b355b490ded4:line_3af8cbc278e4'), '福井鉄道線', '福井鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('566/0'), LineId('jp:operator_f568a3419ccb:line_51b9af47ad8b'), 'えちぜん鉄道勝山永平寺線', 'えちぜん鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('567/0'), LineId('jp:operator_f568a3419ccb:line_26488b5b871f'), 'えちぜん鉄道三国芦原線', 'えちぜん鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('568/0'), LineId('jp:operator_d60d27691f54:line_4ed3af9ebdb1'), '北陸鉄道石川線', '北陸鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('569/0'), LineId('jp:operator_d60d27691f54:line_dd7060890680'), '北陸鉄道浅野川線', '北陸鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('570/0'), LineId('jp:operator_755ae30d00c7:line_1d5c13b5a9d6'), 'のと鉄道線', 'のと鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('571/0'), LineId('jp:operator_8f12fec9b74b:line_5c624b55c865'), '富山地方鉄道本線', '富山地方鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('572/0'), LineId('jp:operator_8f12fec9b74b:line_cffdf84d7815'), '富山地方鉄道立山線', '富山地方鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('573/0'), LineId('jp:operator_8f12fec9b74b:line_8fd87657df15'), '富山地方鉄道不二越・上滝線', '富山地方鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('574/0'), LineId('jp:operator_8f12fec9b74b:line_a682c47be28a'), '富山地方鉄道富山市内軌道線', '富山地方鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('576/0'), LineId('jp:operator_877b6021e659:line_175aa3c5b356'), '万葉線', '万葉線', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('577/0'), LineId('jp:operator_82d611a1ab2f:line_8b7ed4db87b8'), '北越急行ほくほく線', '北越急行', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('578/0'), LineId('jp:operator_4d0917a9e4d1:line_238e9f3386e3'), '長野電鉄線', '長野電鉄', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('580/0'), LineId('jp:operator_e970a4fbc150:line_30f4c5d8f27e'), 'しなの鉄道線', 'しなの鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('581/0'), LineId('jp:operator_bc275cff14c0:line_1edc6a21b79e'), '上田電鉄別所線', '上田電鉄', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('582/0'), LineId('jp:operator_ebb87ca0294c:line_5b06ac48bf3d'), 'アルピコ交通上高地線', 'アルピコ交通', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('583/0'), LineId('jp:operator_6d6f0c56a54c:line_348b8beef5f7'), '和歌山電鐵貴志川線', '和歌山電鐵', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('584/0'), LineId('jp:jr_west:osaka_higashi'), 'おおさか東線', 'JR西日本', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('585/0'), LineId('jp:operator_eb8a6af20615:line_1fab903a287f'), '岡山電気軌道線', '岡山電気軌道', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('586/0'), LineId('jp:operator_9f2f425b4fc9:line_c77a62698f46'), '水島臨海鉄道線', '水島臨海鉄道', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('587/0'), LineId('jp:operator_837a3b59afcf:line_e67249a2f31c'), '井原鉄道線', '井原鉄道', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('588/0'), LineId('jp:operator_ebcb3324c3d8:line_331689c76e19'), '広島電鉄宮島線', '広島電鉄', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('589/0'), LineId('jp:operator_ebcb3324c3d8:line_5621f0746a1e'), '広島電鉄市内線', '広島電鉄', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('590/0'), LineId('jp:operator_61a0c15c3a37:line_5df39c3815e2'), 'アストラムライン', '広島高速交通', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('591/0'), LineId('jp:operator_2fa54821493a:line_fb44098c1f54'), '錦川鉄道線', '錦川鉄道', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('592/0'), LineId('jp:operator_b908cfada105:line_0d9e87196642'), '若桜鉄道線', '若桜鉄道', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('593/0'), LineId('jp:operator_0e9437345847:line_c9b8a6c17f5e'), '一畑電車線', '一畑電車', (YahooArea.CHUGOKU, )),
    _Binding(YahooRouteId('595/0'), LineId('jp:operator_414b7330652e:line_87405df4228a'), '高松琴平電鉄琴平線', '高松琴平電鉄', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('596/0'), LineId('jp:operator_414b7330652e:line_169941a2f3bd'), '高松琴平電鉄志度線', '高松琴平電鉄', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('597/0'), LineId('jp:operator_414b7330652e:line_0ecd7b7089c6'), '高松琴平電鉄長尾線', '高松琴平電鉄', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('598/0'), LineId('jp:operator_74ae511377a2:line_d1d5a8a2e706'), 'とさでん交通線', 'とさでん交通', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('599/0'), LineId('jp:operator_38073936bac7:line_340d4e1bb3e5'), '阿佐海岸鉄道阿佐東線', '阿佐海岸鉄道', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('600/0'), LineId('jp:operator_70a4f41a12fa:line_65749ab8c41f'), '伊予鉄高浜線・横河原線', '伊予鉄道', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('602/0'), LineId('jp:operator_70a4f41a12fa:line_72dcc2ec819f'), '伊予鉄郡中線', '伊予鉄道', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('603/0'), LineId('jp:operator_70a4f41a12fa:line_14c13d76ddbb'), '伊予鉄松山市内線', '伊予鉄道', (YahooArea.SHIKOKU, )),
    _Binding(YahooRouteId('604/0'), LineId('jp:operator_3d1e3ac9302f:line_eb89fff2601f'), '北九州モノレール線', '北九州高速鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('605/0'), LineId('jp:operator_9473f70fdc75:line_006e4b1e8a81'), '筑豊電鉄線', '筑豊電鉄', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('606/0'), LineId('jp:operator_0eca8363a745:line_4e886f95e26d'), '甘木鉄道線', '甘木鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('607/0'), LineId('jp:operator_101dd8d9c8cf:line_18928fb21159'), '平成筑豊鉄道伊田線', '平成筑豊鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('608/0'), LineId('jp:operator_101dd8d9c8cf:line_f2acbcf0e0ff'), '平成筑豊鉄道田川線', '平成筑豊鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('609/0'), LineId('jp:operator_101dd8d9c8cf:line_1c776706f0f0'), '平成筑豊鉄道糸田線', '平成筑豊鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('610/0'), LineId('jp:operator_fcd86a4e62c5:line_c11f2b551d02'), '松浦鉄道線', '松浦鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('611/0'), LineId('jp:operator_f78cdff132aa:line_42a79626d6c0'), '島原鉄道線', '島原鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('612/0'), LineId('jp:operator_9a9a643083cd:line_bc89cb0f6361'), '長崎電気軌道線', '長崎電気軌道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('613/0'), LineId('jp:operator_399bef4fd588:line_3a15f1c87839'), '肥薩おれんじ鉄道線', '肥薩おれんじ鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('614/0'), LineId('jp:operator_caf6247dee13:line_c5136805919a'), '南阿蘇鉄道線', '南阿蘇鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('615/0'), LineId('jp:operator_55001634bd48:line_cebca27fe426'), 'くま川鉄道線', 'くま川鉄道', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('616/0'), LineId('jp:operator_2ecca208810f:line_7c7655581f90'), '熊本市電', '熊本市交通局', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('617/0'), LineId('jp:operator_f694a9028992:line_9de397ed1c12'), '熊本電鉄線', '熊本電鉄', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('619/0'), LineId('jp:operator_3ecf100c4a78:line_e429c9010b53'), '鹿児島市電', '鹿児島市交通局', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('620/0'), LineId('jp:operator_95b01abb482d:line_b8a42de95ac6'), 'ゆいレール', '沖縄都市モノレール', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('621/0'), LineId('jp:operator_cde7e3c56715:line_4b4da2eb5c60'), '伊賀鉄道線', '伊賀鉄道', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('622/0'), LineId('jp:keisei:line_5e3c730ed219'), '成田スカイアクセス線', '京成電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('623/0'), LineId('jp:hanshin:kobe_kosoku'), '神戸高速線', '阪神電鉄', (YahooArea.KINKI, )),
    _Binding(YahooRouteId('627/0'), LineId('jp:jr_east:line_24943fa818c8'), '上野東京ライン', 'JR東日本', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('628/0'), LineId('jp:operator_e970a4fbc150:line_48f9dd0578db'), 'しなの鉄道北しなの線', 'しなの鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('629/0'), LineId('jp:operator_b84830658c79:line_639259ac791e'), '妙高はねうまライン', 'えちごトキめき鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('630/0'), LineId('jp:operator_b84830658c79:line_41edfbc3db41'), '日本海ひすいライン', 'えちごトキめき鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('631/0'), LineId('jp:operator_1db543e5ee0e:line_1f4253308e1d'), 'あいの風とやま鉄道線', 'あいの風とやま鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('632/0'), LineId('jp:operator_e2b7cf9462e6:line_f039218cc1fa'), 'IRいしかわ鉄道線', 'IRいしかわ鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('634/0'), LineId('jp:jr_kyushu:line_8b8e0374cc9f'), '山陽本線[下関～門司]', 'JR九州', (YahooArea.KYUSHU, )),
    _Binding(YahooRouteId('635/0'), LineId('jp:operator_28ea73eb1891:line_b36021187552'), '四日市あすなろう鉄道線', '四日市あすなろう鉄道', (YahooArea.CHUBU, )),
    _Binding(YahooRouteId('636/0'), LineId('jp:operator_31739cacf719:line_3cb65ac614ea'), '仙台市営東西線', '仙台市交通局', (YahooArea.TOHOKU, )),
    _Binding(YahooRouteId('638/0'), LineId('jp:operator_ef8339b3bd86:line_51ce63e87fe2'), '道南いさりび鉄道線', '道南いさりび鉄道', (YahooArea.HOKKAIDO, )),
    _Binding(YahooRouteId('639/0'), LineId('jp:tobu:line_12175b4f81b5'), '東武伊勢崎線[久喜～伊勢崎]', '東武鉄道', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('641/0'), LineId('jp:tokyu:line_80065b958e40'), '東急新横浜線', '東急電鉄', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('642/0'), LineId('jp:operator_4fa22b75d3eb:line_17ca74f78b4d'), '宇都宮ライトレール線', '宇都宮ライトレール', (YahooArea.KANTO, )),
    _Binding(YahooRouteId('643/0'), LineId('jp:operator_b0505014db71:line_a47f820cdfc7'), 'ハピラインふくい線', 'ハピラインふくい', (YahooArea.CHUBU, )),
)


class _Row(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    source_id: YahooRouteId
    name: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    status: str = Field(min_length=1)
    preview: str = Field(min_length=1)


class _Detail(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    status: str = Field(min_length=1)
    description: str = Field(min_length=1)
    updated_at: AwareDatetime | None


def _normalise(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _attribute(tag: Tag, name: str) -> str:
    value = tag.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ParseError(f"Yahoo route is missing {name}")
    return value.strip()


def _status(value: str) -> LineStatus:
    return {
        "平常運転": LineStatus.NORMAL,
        "列車遅延": LineStatus.DELAYED,
        "遅延": LineStatus.DELAYED,
        "運転見合わせ": LineStatus.SUSPENDED,
        "運休": LineStatus.SUSPENDED,
        "一部運休": LineStatus.PARTIAL_SUSPENSION,
        "運転状況": LineStatus.ALERT,
        "運転再開": LineStatus.ALERT,
        "運転計画": LineStatus.ALERT,
        "直通運転中止": LineStatus.ALERT,
        "その他": LineStatus.ALERT,
        "お知らせ": LineStatus.ALERT,
    }.get(_normalise(value), LineStatus.UNKNOWN)


def _announced_at(month: int, day: int, hour: int, minute: int, now: datetime) -> datetime:
    if now.utcoffset() is None:
        raise ValueError("Yahoo timestamp reference must have a timezone")
    local_now = now.astimezone(_JST)
    # The publisher omits the year. Allow small clock skew, not tomorrow's date.
    # Four years also handles a retained February 29 announcement.
    for year in range(local_now.year, local_now.year - 5, -1):
        try:
            value = datetime(year, month, day, hour, minute, tzinfo=_JST)
        except ValueError:
            continue
        if value <= local_now + timedelta(minutes=5):
            return value
    raise ParseError("Invalid Yahoo publication timestamp")


def _parse_area(html: str, area: YahooArea) -> tuple[_Row, ...]:
    soup = BeautifulSoup(html, "html.parser")
    expected = {binding.source_id: binding for binding in _BINDINGS if area in binding.areas}
    found: dict[YahooRouteId, _Row] = {}
    for table in soup.select("div.elmTblLstLine:not(.trouble)"):
        heading = table.find_previous("h3")
        if heading is None:
            raise ParseError("Yahoo carrier heading is missing")
        operator = heading.get_text(" ", strip=True)
        for row in table.select("tr"):
            cells = tuple(tag for tag in row.find_all("td", recursive=False) if isinstance(tag, Tag))
            if not cells:
                continue
            if len(cells) != 3:
                raise ParseError("Yahoo status table columns changed")
            link = cells[0].find("a", href=True)
            if not isinstance(link, Tag):
                raise ParseError("Yahoo line link is missing")
            url = urlsplit(urljoin(_URL, _attribute(link, "href")))
            match = _ROUTE_PATH.fullmatch(url.path)
            if url.scheme != "https" or url.netloc != "transit.yahoo.co.jp" or match is None:
                raise ParseError("Unexpected Yahoo line URL")
            identifier = YahooRouteId(match.group(1))
            binding = expected.get(identifier)
            if binding is None or identifier in found:
                raise ParseError(f"Unknown or duplicate Yahoo route: {identifier}")
            name = link.get_text(" ", strip=True)
            if _normalise(name) != _normalise(binding.source_name) or _normalise(operator) != _normalise(binding.operator_name):
                raise ParseError(f"Yahoo route identity changed: {identifier}")
            found[identifier] = _Row(
                source_id=identifier, name=name, operator=operator,
                status=cells[1].get_text(" ", strip=True),
                preview=cells[2].get_text(" ", strip=True),
            )
    if not expected or set(found) != set(expected):
        raise ParseError(f"Yahoo area {area.value} route coverage is incomplete")
    return tuple(found.values())


def _parse_detail(html: str, binding: _Binding, now: datetime) -> _Detail:
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one("#mdServiceStatus")
    title = soup.select_one("h1.title")
    if title is not None and _normalise(title.get_text(" ", strip=True)) != _normalise(binding.source_name):
        raise ParseError(f"Yahoo detail route identity changed: {binding.source_id}")
    label = info.select_one("dl > dt") if info is not None else None
    body = info.select_one("dl > dd > p") if info is not None else None
    if label is None or body is None:
        raise ParseError("Yahoo service status or detail body is missing")
    status = label.get_text(" ", strip=True)
    description = body.get_text(" ", strip=True)
    match = _POSTED.search(description)
    updated_at = None
    if match is not None:
        updated_at = _announced_at(
            int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4)), now,
        )
    elif _status(status) is not LineStatus.NORMAL:
        raise ParseError("Yahoo abnormal detail is missing its publication timestamp")
    return _Detail(status=status, description=description, updated_at=updated_at)


class YahooProvider(SnapshotProvider):
    _provider_id = _ID
    _source_url = _URL
    _metadata = _METADATA

    def __init__(
        self, *, areas: tuple[YahooArea, ...] = _ALL_AREAS,
        max_concurrency: int = 4, client: httpx.AsyncClient | None = None,
        snapshot_dir: str | Path | None = None,
    ) -> None:
        if not areas or len(set(areas)) != len(areas) or any(not isinstance(area, YahooArea) for area in areas):
            raise ValueError("Yahoo areas must be a non-empty tuple of distinct YahooArea values")
        if isinstance(max_concurrency, bool) or not 1 <= max_concurrency <= 16:
            raise ValueError("Yahoo max_concurrency must be between 1 and 16")
        self._areas = areas
        self._max_concurrency = max_concurrency
        self._bindings = tuple(binding for binding in _BINDINGS if set(areas).intersection(binding.areas))
        unique = dict.fromkeys(binding.line_id for binding in self._bindings)
        lines = tuple(LINE_CATALOG[identifier].create_line(_ID, _URL) for identifier in unique)
        super().__init__(lines, client=client, snapshot_dir=snapshot_dir)

    @property
    def areas(self) -> tuple[YahooArea, ...]:
        return self._areas

    @property
    def source_line_ids(self) -> tuple[YahooRouteId, ...]:
        return tuple(binding.source_id for binding in _BINDINGS)

    def get_source_line(self, identifier: YahooRouteId) -> Line | None:
        binding = next((item for item in _BINDINGS if item.source_id == identifier), None)
        if binding is None:
            return None
        return self.get_line(binding.line_id) or LINE_CATALOG[binding.line_id].create_line(_ID, _URL)

    def _source_line(self, identifier: str) -> Line:
        line = self.get_source_line(YahooRouteId(identifier))
        if line is None:
            raise KeyError(identifier)
        return line

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def fetch_area(area: YahooArea) -> tuple[_Row, ...]:
            async with semaphore:
                response = await self._get(client, f"{_URL}/area/{area.value}")
                response.raise_for_status()
                return _parse_area(response.text, area)

        area_results = await asyncio.gather(*(fetch_area(area) for area in self._areas), return_exceptions=True)
        rows: dict[YahooRouteId, _Row] = {}
        detail_ids: set[YahooRouteId] = set()
        for area_result in area_results:
            if isinstance(area_result, BaseException):
                raise area_result
            for row in area_result:
                rows[row.source_id] = row
                if _status(row.status) is not LineStatus.NORMAL or _normalise(row.preview) != "事故・遅延情報はありません":
                    detail_ids.add(row.source_id)

        async def fetch_detail(binding: _Binding) -> tuple[YahooRouteId, _Detail]:
            async with semaphore:
                response = await self._get(client, f"{_URL}/{binding.source_id}")
                response.raise_for_status()
                return binding.source_id, _parse_detail(response.text, binding, self._now())

        detail_results = await asyncio.gather(*(
            fetch_detail(binding) for binding in self._bindings if binding.source_id in detail_ids
        ), return_exceptions=True)
        details: dict[YahooRouteId, _Detail] = {}
        for detail_result in detail_results:
            if isinstance(detail_result, BaseException):
                raise detail_result
            identifier, detail = detail_result
            details[identifier] = detail
        fetched_at = self._now()
        result: list[Line] = []
        for line in self.lines:
            bindings = tuple(binding for binding in self._bindings if binding.line_id == line.line_id)
            states: list[LineStatus] = []
            labels: list[str] = []
            alerts: list[ServiceAlert] = []
            timestamps: list[datetime] = []
            for binding in bindings:
                row = rows[binding.source_id]
                route_detail = details.get(binding.source_id)
                label = route_detail.status if route_detail is not None else row.status
                description = route_detail.description if route_detail is not None else row.preview
                status = _status(label)
                states.append(status)
                labels.append(label)
                if route_detail is not None and route_detail.updated_at is not None:
                    timestamps.append(route_detail.updated_at)
                if status is not LineStatus.NORMAL:
                    source_line = LINE_CATALOG[line.line_id].create_line(_ID, f"{_URL}/{binding.source_id}")
                    alerts.append(make_alert(
                        source_line, status, f"{binding.source_name}: {label}", description,
                        alert_id=f"yahoo:{binding.source_id}",
                        timing=timing_from_status(status),
                    ))
            all_source_ids = {binding.source_id for binding in _BINDINGS if binding.line_id == line.line_id}
            if not all_source_ids.issubset(rows):
                states.append(LineStatus.UNKNOWN)
                labels.append("未取得の区間あり")
            result.append(snapshot(
                line, combined_status(tuple(states)), " / ".join(dict.fromkeys(labels)), fetched_at,
                updated_at=max(timestamps) if timestamps else None, alerts=tuple(alerts),
                source_line_names=tuple(binding.source_name for binding in bindings),
            ))
        return tuple(result)

    @property
    def ako(self) -> Line:
        return self._source_line('330/0')

    @property
    def bantan(self) -> Line:
        return self._source_line('336/0')

    @property
    def biwako(self) -> Line:
        return self._source_line('266/0')

    @property
    def chuo(self) -> Line:
        return self._source_line('324/0')

    @property
    def etsumi_hoku(self) -> Line:
        return self._source_line('483/0')

    @property
    def fukuchiyama(self) -> Line:
        return self._source_line('490/0')

    @property
    def fukuen(self) -> Line:
        return self._source_line('499/0')

    @property
    def gakkentoshi(self) -> Line:
        return self._source_line('271/0')

    @property
    def gantoku(self) -> Line:
        return self._source_line('504/0')

    @property
    def geibi(self) -> Line:
        return self._source_line('498/0')

    @property
    def hagoromo(self) -> Line:
        return self._source_line('276/0')

    @property
    def hakata_minami(self) -> Line:
        return self._source_line('396/0')

    @property
    def hakubi(self) -> Line:
        return self._source_line('496/0')

    @property
    def hankyu_arashiyama(self) -> Line:
        return self._source_line('314/0')

    @property
    def hankyu_imazu(self) -> Line:
        return self._source_line('308/0')

    @property
    def hankyu_itami(self) -> Line:
        return self._source_line('307/0')

    @property
    def hankyu_kobe(self) -> Line:
        return self._source_line('310/0')

    @property
    def hankyu_koyo(self) -> Line:
        return self._source_line('309/0')

    @property
    def hankyu_kyoto(self) -> Line:
        return self._source_line('306/0')

    @property
    def hankyu_mino(self) -> Line:
        return self._source_line('312/0')

    @property
    def hankyu_senri(self) -> Line:
        return self._source_line('313/0')

    @property
    def hankyu_takarazuka(self) -> Line:
        return self._source_line('311/0')

    @property
    def hanshin_kobe_kosoku(self) -> Line:
        return self._source_line('623/0')

    @property
    def hanshin_main(self) -> Line:
        return self._source_line('315/0')

    @property
    def hanshin_mukogawa(self) -> Line:
        return self._source_line('317/0')

    @property
    def hanshin_namba(self) -> Line:
        return self._source_line('316/0')

    @property
    def hanwa(self) -> Line:
        return self._source_line('274/0')

    @property
    def himi(self) -> Line:
        return self._source_line('485/0')

    @property
    def hokuriku(self) -> Line:
        return self._source_line('481/0')

    @property
    def imazatosuji(self) -> Line:
        return self._source_line('537/0')

    @property
    def inbi(self) -> Line:
        return self._source_line('494/0')

    @property
    def johana(self) -> Line:
        return self._source_line('486/0')

    @property
    def kabe(self) -> Line:
        return self._source_line('503/0')

    @property
    def kakogawa(self) -> Line:
        return self._source_line('334/0')

    @property
    def kansai(self) -> Line:
        return self._source_line('278/0')

    @property
    def kansai_airport(self) -> Line:
        return self._source_line('282/0')

    @property
    def keihan_ishiyama_sakamoto(self) -> Line:
        return self._source_line('304/0')

    @property
    def keihan_katano(self) -> Line:
        return self._source_line('301/0')

    @property
    def keihan_keishin(self) -> Line:
        return self._source_line('303/0')

    @property
    def keihan_main_nakanoshima(self) -> Line:
        return self._source_line('300/0')

    @property
    def keihan_uji(self) -> Line:
        return self._source_line('302/0')

    @property
    def kinokuni(self) -> Line:
        return self._source_line('333/0')

    @property
    def kisei(self) -> Line:
        return self._source_line('275/0')

    @property
    def kishin(self) -> Line:
        return self._source_line('335/0')

    @property
    def kisuki(self) -> Line:
        return self._source_line('500/0')

    @property
    def kobe(self) -> Line:
        return self._source_line('273/0')

    @property
    def kosei(self) -> Line:
        return self._source_line('268/0')

    @property
    def kure(self) -> Line:
        return self._source_line('502/0')

    @property
    def kusatsu(self) -> Line:
        return self._source_line('269/0')

    @property
    def kyoto(self) -> Line:
        return self._source_line('267/0')

    @property
    def maizuru(self) -> Line:
        return self._source_line('338/0')

    @property
    def manyomahoroba(self) -> Line:
        return self._source_line('280/0')

    @property
    def midosuji(self) -> Line:
        return self._source_line('321/0')

    @property
    def mine(self) -> Line:
        return self._source_line('508/0')

    @property
    def momotaro(self) -> Line:
        return self._source_line('495/0')

    @property
    def nagahori_tsurumi_ryokuchi(self) -> Line:
        return self._source_line('327/0')

    @property
    def nanao(self) -> Line:
        return self._source_line('484/0')

    @property
    def nara(self) -> Line:
        return self._source_line('279/0')

    @property
    def new_tram(self) -> Line:
        return self._source_line('320/0')

    @property
    def obama(self) -> Line:
        return self._source_line('489/0')

    @property
    def oito(self) -> Line:
        return self._source_line('488/0')

    @property
    def onoda(self) -> Line:
        return self._source_line('506/0')

    @property
    def osaka_higashi(self) -> Line:
        return self._source_line('584/0')

    @property
    def osaka_loop(self) -> Line:
        return self._source_line('263/0')

    @property
    def osaka_monorail_main(self) -> Line:
        return self._source_line('380/0')

    @property
    def sagano(self) -> Line:
        return self._source_line('270/0')

    @property
    def sakai(self) -> Line:
        return self._source_line('497/0')

    @property
    def sakaisuji(self) -> Line:
        return self._source_line('326/0')

    @property
    def sanin(self) -> Line:
        return self._source_line('331/422')

    @property
    def sanyo(self) -> Line:
        return self._source_line('332/419')

    @property
    def sennichimae(self) -> Line:
        return self._source_line('325/0')

    @property
    def seto_ohashi(self) -> Line:
        return self._source_line('491/0')

    @property
    def takarazuka(self) -> Line:
        return self._source_line('265/0')

    @property
    def takayama(self) -> Line:
        return self._source_line('487/0')

    @property
    def tanimachi(self) -> Line:
        return self._source_line('322/0')

    @property
    def tozai(self) -> Line:
        return self._source_line('272/0')

    @property
    def tsuyama(self) -> Line:
        return self._source_line('493/0')

    @property
    def ube(self) -> Line:
        return self._source_line('505/0')

    @property
    def uno_minato(self) -> Line:
        return self._source_line('492/0')

    @property
    def wadamisaki(self) -> Line:
        return self._source_line('283/0')

    @property
    def wakayama(self) -> Line:
        return self._source_line('281/0')

    @property
    def yamaguchi(self) -> Line:
        return self._source_line('507/0')

    @property
    def yamanote(self) -> Line:
        return self._source_line('21/0')

    @property
    def yamatoji(self) -> Line:
        return self._source_line('277/0')

    @property
    def yotsubashi(self) -> Line:
        return self._source_line('323/0')

    @property
    def yumesaki(self) -> Line:
        return self._source_line('264/0')
