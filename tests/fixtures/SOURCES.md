# Additional provider evidence

## 高雄MRT/LRT

[KAOHSIUNG_METRO.md](KAOHSIUNG_METRO.md) に公式HTML・JavaScriptと保存HTMLの
調査範囲、紅橘線GROUP／輕軌LINE、確認済み正常表示、未確認状態、利用条件を記録。
[kaohsiung_metro_manifest.json](kaohsiung_metro_manifest.json) に原URL・最終URL・
UTC取得日時・原本と抽出後のSHA-256・DOM抽出方法を記録しています。
実応答は正常表示のみで、未知状態・破損・復旧遷移は合成テストです。

## TfL

[TfL Unified API](TFL.md): current rail/tram statuses, official severity metadata,
Swagger schema, operator evidence and licence/access conditions;
[capture manifest](tfl_manifest.json). Real and synthetic cases are distinguished.

## European service notices

- [DB Verkehrslage / DB Fernverkehr](DB.md): public HTML/JavaScript and abnormal live JSON, source scope and expiry rules; [manifest](db_manifest.json).
- [Transilien](TRANSILIEN.md): 12 SNCF-operated route groups and 16 RATP Paris Métro lines, public JavaScript and complete live JSON; [SNCF manifest](transilien_manifest.json), [Métro manifest](transilien_metro_manifest.json).
- [ÖBB editorial incident notices](OBB.md): official JavaScript, archived incident HTML and the live incident-free listing; [manifest](obb_manifest.json).

These providers preserve unknown effects, timing and affected lines rather than deriving them from incident prose. Their dedicated documents distinguish real captures from synthetic cases and explain structurally excluded construction/future notices.

## 台湾鉄路（TRA）

公式通阻一覧のライブHTMLと遅延・災害・台風・長期工事・復旧表示の保存HTML、
状態対応、路線範囲、利用条件、未確認事項は [TRA.md](TRA.md) を参照。
原URL・UTC保存日時・原本と抽出後のSHA-256・DOM抽出方法は
[tra_manifest.json](tra_manifest.json) に記録。

## 箱根登山鉄道（箱根ナビ公式）

[HAKONE_TOZAN.md](HAKONE_TOZAN.md) に調査範囲・状態対応・未確認事項を記録しています。
公式HTMLの取得元・Wayback保存日時（UTC）・取得日時・原本と抽出後のSHA-256・加工方法は
[hakone_tozan_manifest.json](hakone_tozan_manifest.json) を参照してください。
平常表示と他交通機関の警告は実応答、登山電車の警告・未知表示・破損・復旧遷移のテストは合成です。

## MyTransportのメッセージ形式

[mrt_message_script.js](mrt_message_script.js) は公式JavaScriptの424–574行を改変せず抽出したものです。[mrt_message_manifest.json](mrt_message_manifest.json) に出典URL、UTC取得日時、原本と抽出後のSHA-256を記録しています。公式コードは `HH:MM-LINE-Major/Minor/Planned` を解析し、Major/MinorをそれぞれModerate/Minorの表示へ対応付けます。自由記述の `no train service` で運休を判別する処理や `Normal` ヘッダーの解析はありません。

Providerはこのヘッダーから対象路線と案内の存在だけを取得し、`ALERT` とします。本文の路線コードによる対象推測、本文からの遅延・運休・復旧判別は行いません。未確認の鉄道形式は原文を保持した対象未特定の `UNKNOWN` です。異常時POST応答は保存データ未確認であり、異常・未知形式・復旧のテストは合成データです。実際の正常応答は既存の `mrt_normal.json` にあります。

専用状態による適用時期、混在する長期案内の保持、JR西日本の地域案内の除外については [ALERT_CLASSIFICATION.md](ALERT_CLASSIFICATION.md) を参照してください。除外の検証に使う未加工応答の取得記録は [alert_classification_manifest.json](alert_classification_manifest.json) に残しています。

JR四国の通常・運休・事前案内の実データ、保存URL、抽出方法とハッシュは [JRSHIKOKU.md](JRSHIKOKU.md) と [jrshikoku_manifest.json](jrshikoku_manifest.json) を参照してください。

Yahoo!鉄道情報のライブ取得データ、地域・詳細の抽出方法、取得日時とハッシュは [YAHOO.md](YAHOO.md) と [yahoo_manifest.json](yahoo_manifest.json) を参照してください。

## Taiwan High Speed Rail (THSR)

Public HTML and archived responses were inspected on 2026-11-01 UTC. The
[human-facing status page](https://www.thsrc.com.tw/ArticleContent/3ec1c04f-d3de-45b1-becc-cba412d55123)
renders current `.ts-tag` cards under `.trafficstatus-container`; collapsed
update-history records are separate siblings and must not determine status.
The [home page](https://www.thsrc.com.tw/) embeds a
[summary iframe](https://www.thsrc.com.tw/ArticleContent/f7f05113-cd27-4dd9-8edc-014f4e920212/index.html).
The provider fetches the full status page for incident details.

CDX was queried for the status-page URL, successful responses, years 2024–2026,
collapsed by month. A daily query for 2024-04-03 through 2024-04-10 found only
the earthquake delay capture, so same-incident recovery remains unverified.
All archive replay timestamps below are UTC; source incident times use
`Asia/Taipei` (UTC+08:00).

Fixtures are BeautifulSoup serializations of the status section plus its
preceding update-time paragraph when present. `.rail-area` diagrams, scripts,
navigation, styles and unrelated page content were omitted. Current labels,
CSS markers, incident text, causes, sections, times and collapsed histories
were not changed. SHA-256 values refer to complete downloaded response bytes,
before extraction.

| Fixture | Source / capture time (UTC) | SHA-256 of downloaded original |
| --- | --- | --- |
| [thsr_normal.html](thsr_normal.html) | [live source](https://www.thsrc.com.tw/ArticleContent/3ec1c04f-d3de-45b1-becc-cba412d55123), fetched 2026-11-01 | `7f6da8bb6ae971a8fcae0d2156de942b6cdf55238bc81f399f7caa81081bdfb6` |
| [thsr_20240403005339.html](thsr_20240403005339.html) | [source](https://web.archive.org/web/20240403005339id_/https://www.thsrc.com.tw/ArticleContent/3EC1C04F-D3DE-45B1-BECC-CBA412D55123), 2024-04-03 00:53:39 | `e58430e8acc982ee7673c3b0bf5ede42ec0d8821a87bb4f0d0d5c391320baa7e` |
| [thsr_20241003073858.html](thsr_20241003073858.html) | [source](https://web.archive.org/web/20241003073858id_/https://www.thsrc.com.tw/ArticleContent/3EC1C04F-D3DE-45B1-BECC-CBA412D55123), 2024-10-03 07:38:58 | `e778f4bf08ec08cbf9932273bff926b6405b976254026279a54f33c7708cf601` |
| [thsr_20250227055330.html](thsr_20250227055330.html) | [source](https://web.archive.org/web/20250227055330id_/https://www.thsrc.com.tw/ArticleContent/3EC1C04F-D3DE-45B1-BECC-CBA412D55123), 2025-02-27 05:53:30 | `7bf13794cf17b955328ca27ff2bd247e75289d3ff8b258ea48b38200bb2c3cc2` |
| [thsr_20260711043641.html](thsr_20260711043641.html) | [source](https://web.archive.org/web/20260711043641id_/https://www.thsrc.com.tw/ArticleContent/3EC1C04F-D3DE-45B1-BECC-CBA412D55123), 2026-07-11 04:36:41 | `08264dda16e994fab3a8b51ff43c94f7dc450b9bfbc9a6930fe44afbca5be0c1` |
| [thsr_20260830041403.html](thsr_20260830041403.html) | [source](https://web.archive.org/web/20260830041403id_/https://www.thsrc.com.tw/ArticleContent/3EC1C04F-D3DE-45B1-BECC-CBA412D55123), 2026-08-30 04:14:03 | `a49b7dcb9c07bc2a8663d972e772ed1be1798adddd6399bafa5726144b8cbeb6` |

Both delay archives verify `caution` / `部份列車延誤` = `DELAYED`, including
the narrower 彰化–南港 affected section. Both timetable archives verify
`caution` / `營運班表調整` = `ALERT`: the label does not specify delay or
suspension, and the body may describe different service at different times.
Normal responses verify `全線正常營運`, with and without the `normal` class.
Hidden `0001/01/01` placeholder times and website deployment dates are ignored.
Unknown markers/labels, malformed structure, combining multiple incident cards
and refreshing from a delay to normal are explicitly synthetic test scenarios.
Full/partial suspension labels, station/direction statuses and incident validity
periods have not been verified.

The [official intellectual-property declaration](https://www.thsrc.com.tw/ArticleContent/b9dcb8ea-02ab-4726-b71d-335904dbd86b)
was reviewed on 2026-11-01 UTC (original SHA-256
`4b6607ff43a069317d4357c478cc8530bf78a6bad9b5cce6985dd2d3d77ea600`).
It reserves rights and requires prior written consent for quotation or
republication. No separate reuse grant was found on the service page;
metadata records `PERMISSION_REQUIRED`.

## Metro Taipei (MRT)

Public HTML was inspected on 2026-11-01 UTC. The provider reads the human-facing
[route operating-information page](https://tpweb.metro.taipei/2026/).
The main site's [operating-information section](https://www.metro.taipei/cp.aspx?n=73C64BE06624284F)
also embeds `https://web.metro.taipei/pages2026/WebAbnormal`; that related page
was inspected but is not fetched by the provider. No membership API is used.

The `tpweb` page includes six route codes/names, image alt text, operating
messages, a displayed `資料更新時間`, and an explicit four-light legend. The
legend establishes `lightgreen.png` (normal), `lightyellow.gif` (route delay),
`lightred.gif` (route locally obstructed), and `lightgray.png` (outside operating
hours). The common service-alert statuses are NORMAL, DELAYED,
PARTIAL_SUSPENSION and NORMAL respectively. Closed hours are preserved in
`source_status`; NORMAL denotes no disruption, not that trains are running.
The red legend does not establish full suspension. Separate branch statuses,
incident start/end times and a full-suspension marker have not been verified.
The displayed data timestamp is interpreted as Asia/Taipei (UTC+08), not UTC,
and is not used as an incident start time. It is the page's data-refresh time,
not evidence that the incident itself changed at that time.

Fixtures are BeautifulSoup serializations of `#UpdatePanelRealStatusDetail`.
Outer wrappers, scripts and ASP.NET form state were omitted. Whitespace,
attribute order and HTML void-tag spelling can differ; route/status/message
text, image references, the legend and displayed timestamps are unchanged.

| Fixture | Source / time (UTC) | SHA-256 of downloaded original |
| --- | --- | --- |
| [taipei_metro_normal.html](taipei_metro_normal.html) | [live source](https://tpweb.metro.taipei/2026/), fetched 2026-11-01T15:02:02.484283+00:00; displayed 2026/11/01 23:02:03 local | `a6008bb70c5e25a6e543d8fd7ee37ef55cd9ca5bfff855724aba1e176137e65c` |
| [taipei_metro_20261024103101.html](taipei_metro_20261024103101.html) | [archive](https://web.archive.org/web/20261024103101id_/https://tpweb.metro.taipei/2026/), captured 2026-10-24 10:31:01; displayed 2026/10/24 18:31:02 local | `fd3ec71eb521fb7dfdf97e4a37e16bb6a74d994814f6833aa80701dd87f87ee1` |

Both captures are normal. CDX query for `tpweb.metro.taipei/2026/*`, successful
HTML responses collapsed by digest, returned the above normal capture only.
Queries for `web.metro.taipei/pages2026/WebAbnormal` and
`web.metro.taipei/pages/WebAbnormal.aspx` returned no captures. No abnormal
archived response was verified. Tests explicitly labelled synthetic mutate the
route light based on the real legend and add invented messages. Recovery tests
replace synthetic disruption HTML with the normal fixture; they are not a
recording of recovery from an actual incident. Unknown lights/labels, unscoped
messages, broken markup and transport failures are synthetic too.

The source lists the Circular Line, but its operator is New Taipei Metro.
[Metro Taipei's station information](https://web.metro.taipei/pages/tw/station/202)
states that operation transferred on 2023-05-23. Its canonical ID is
`tw:ntmetro:circular`; the other five lines use `tw:trtc:*`. These lines were
absent from LINE_CATALOG before this provider was added.

Terms reviewed 2026-11-01 UTC: the official
[government website open-data declaration](https://www.metro.taipei/News_Content.aspx?n=BD13B1ACE1C92D02&s=791780E919AB130C&sms=397D9220FC82B394)
grants free, non-exclusive reuse, adaptation and distribution for products and
services, without additional written permission, with attribution to Metro
Taipei (臺北捷運公司). Metadata records COMMERCIAL_ALLOWED and the attribution
condition. The grant excludes trademarks/logos, personal data and expressly
excluded third-party materials, and conveys no endorsement. This public HTML
provider does not use the [separate membership API](https://www.metro.taipei/cp.aspx?n=BDEB860F2BE3E249).

## Kintetsu

The following fixtures are excerpts of the Japanese official summary. Original
Shift_JIS bytes were decoded as CP932 and parsed with BeautifulSoup. The title,
status area, normal statement or notice tables, and following caption boundary
were serialized back to CP932. Outer page wrappers, scripts, service disclaimers
and other-railway links were omitted; route/status/cause text and detail onclick
links were not changed. Tests serve these CP932 bytes through MockTransport.
The original HTML's server-clock JavaScript reads the HTTP Date header; it does
not identify the last incident update. Historical summary tests use explicitly
synthetic detail prose; no matching historical detail capture is available.

Live summary, [route list](https://www.kintetsu.co.jp/station/) and
[general terms](https://www.kintetsu.co.jp/toppage/annai.html) were inspected on
2026-11-01 JST. The operation page also publishes its own reuse conditions.
Archive timestamps below are UTC. The alternative delay label `遅れ`, malformed
HTML and unknown statuses in tests are explicitly synthetic, not observed incidents.

| Fixture | Source | SHA-256 of downloaded original |
| --- | --- | --- |
| [kintetsu_20261101.html](kintetsu_20261101.html) | [live official summary](https://www.kintetsu.jp/unkou/unkou.html), fetched 2026-11-01 JST; Kyoto suspension | `54cdfa531d253ed7497577d4a99c2090557104411e6810b6060ecd63e7e03a41` |
| [kintetsu_20260111081515.html](kintetsu_20260111081515.html) | [2026-01-11 08:15:15 UTC](https://web.archive.org/web/20260111081515id_/https://www.kintetsu.jp/unkou/unkou.html); Kashihara/Kyoto partial cancellation | `15bdc4117bf82db129ff424e158b66c79b0f48fc31ebbffbe095150665f2a82d` |
| [kintetsu_20260213065943.html](kintetsu_20260213065943.html) | [2026-02-13 06:59:43 UTC](https://web.archive.org/web/20260213065943id_/https://www.kintetsu.jp/unkou/unkou.html); no delay of 15 minutes or more | `67ee04c5eb7a08d19a7d228853fdb6aaa289415b269ec01792b05a84a6332f7a` |
| [kintetsu_20260305143142.html](kintetsu_20260305143142.html) | [2026-03-05 14:31:42 UTC](https://web.archive.org/web/20260305143142id_/https://www.kintetsu.jp/unkou/unkou.html); Kyoto notice | `e17451105d1994c4bd3ed0b03552e122ea66443063822de613f41bc53dcb237d` |
| [kintetsu_20260504000342.html](kintetsu_20260504000342.html) | [2026-05-04 00:03:42 UTC](https://web.archive.org/web/20260504000342id_/https://www.kintetsu.jp/unkou/unkou.html); Toba suspension, Shima/Yamada partial cancellation | `22b8754a3dcfc0853c750d50e4dd094348f37063f70da4ecb122f6e58c6fd2c7` |
| [kintetsu_20260601231132.html](kintetsu_20260601231132.html) | [2026-06-01 23:11:32 UTC](https://web.archive.org/web/20260601231132id_/https://www.kintetsu.jp/unkou/unkou.html); typhoon notice | `f6f82134b026df9f9a047aa955f69e304b0023d1cce89556528215aa34f74280` |
| [kintetsu_20250820134746.html](kintetsu_20250820134746.html) | [2025-08-20 13:47:46 UTC](https://web.archive.org/web/20250820134746id_/https://www.kintetsu.jp/unkou/unkou.html); extra limited-express service notice | `3490767495aac1e8434025968bc75f60b4bef0529d23660d227184de8535d1d2` |
| [kintetsu_20261107.html](kintetsu_20261107.html) | [live official summary](https://www.kintetsu.jp/unkou/unkou.html), fetched 2026-11-07 14:58:00 UTC; Nagoya `遅延` | `3ce6c73be337958326bfd8a83163757a8b112db71d4b8ba71dbc43efb5b164a1` |
| [kintetsu_detail_940571_20261107.html](kintetsu_detail_940571_20261107.html) | [live official detail](https://www.kintetsu.jp/unkou/files/940571.html), fetched 2026-11-07 14:58:00 UTC; Nagoya detail prose | `ebcf9a4ff4d2384b8ca3283374a640b536dafa10a6c6a82a89d524b796d7ed4f` |

The 2026-11-07 pair is saved as unmodified HTTP response bytes, fetched with
the library's User-Agent. Both pages declare Shift_JIS and are decoded as CP932.
The detail page has one `#tran` marker inside its narrative table cell, after
the navigation and map and before the disclaimer/service/other-railway tables.
The provider takes that cell's text, converts `<br>` to newlines and removes
formatting whitespace, scripts and styles. It retains the displayed timestamp,
prose, affected-section and alternative-transport sections without interpreting
them as structured dates, affected lines or state. The live summary explicitly
labels this incident `遅延`; the detail describes earlier suspension and service
resumption. The summary remains authoritative for status. These captures are
local only and are not redistributed; synthetic tests cover body extraction,
shared detail URLs, malformed/empty bodies and atomic failure/recovery.

Recovery tests switch the actual partial-cancellation fixture to the actual
no-delay fixture; this tests snapshot replacement and is not an archived
timeline of the same incident. The raw detail page inspected during the initial
2026-11-01 research was not used as a fixture; the 2026-11-07 detail is used above.

## Other providers

HTML fixtures are excerpts of the original status DOM (serialized by BeautifulSoup); labels and status values are unchanged. XML fixtures retain original bytes. The older JR West JSON fixtures are projected to createdAt, maintenance flags, the route master, and daily data; unrelated history is omitted. Future days and incident version histories remain where present. The newer `jrw_announcements_20261102.json` retains the complete response, including area announcements.
MRT abnormal cases in tests are synthetic. No abnormal archived POST response or abnormal Osaka Monorail snapshot has been verified.
Live responses were obtained on 2026-11-01 (Asia/Tokyo). Archive timestamps in filenames and source URLs are UTC; `monorail_normal.html` is also an archived response, as its source URL shows.

| Fixture | Source | SHA-256 of downloaded original |
| --- | --- | --- |
| [hankyu_20250722023635.html](hankyu_20250722023635.html) | [source](https://web.archive.org/web/20250722023635id_/https://www.hankyu.co.jp/railinfo/include/page_railinfo.html) | `94e0940f51ada12237321f004bb807b47c97cc6b4ad6ff0e468de8ef519ce3ef` |
| [hankyu_20230815061839.html](hankyu_20230815061839.html) | [source](https://web.archive.org/web/20230815061839id_/https://www.hankyu.co.jp/railinfo/include/page_railinfo.html) | `f616c37a3aca6ef86892b2cf9ec4caea4940ea94875acdc6eaa8269067e7b8e6` |
| [hankyu_normal.html](hankyu_normal.html) | [source](https://www.hankyu.co.jp/railinfo/include/page_railinfo.html) | `f145f56a67d3094020efc021927a400e7cc8fba87e6c0b286e40d20721763559` |
| [hanshin_20240830120316.html](hanshin_20240830120316.html) | [source](https://web.archive.org/web/20240830120316id_/https://www.hanshin.co.jp/) | `a6592c0ae55d43582b2a2eeede493cf77e7ad99acedfaba4ec3f8f9c657a5c18` |
| [hanshin_20250730092425.html](hanshin_20250730092425.html) | [source](https://web.archive.org/web/20250730092425id_/https://www.hanshin.co.jp/) | `98b7be75f916fdfb41e711521308b1933aeace38dc0fcadfaef08c116cfadc45` |
| [hanshin_normal.html](hanshin_normal.html) | [source](https://www.hanshin.co.jp/) | `4ed080762f317599358980f9e93b02fd31bc1e6163b6ab15c2146da6a47e3f2d` |
| [monorail_normal.html](monorail_normal.html) | [source](https://web.archive.org/web/20250811060448id_/https://www.osaka-monorail.co.jp/) | `707acb5e061e521c4c4b009a2c6c09803d2367c11696fd2cfaebc8e680ef3875` |
| [keihan_xml_20230911234517.xml](keihan_xml_20230911234517.xml) | [source](https://web.archive.org/web/20230911234517id_/https://www.keihan.co.jp/tinfo/01-traininfo/traininfo20230912081718.xml) | `1958eb3e0d0be70d590642b8ddaf79f2d01279f4cf9cf357ee6e9d6f2ad66700` |
| [keihan_xml_20251101104408.xml](keihan_xml_20251101104408.xml) | [source](https://web.archive.org/web/20251101104408id_/https://www.keihan.co.jp/tinfo/01-traininfo/traininfo20251101194244.xml) | `07cdea571f6733ba4804d3e57bdeab6af74521a091bf4266d7685f02ffba7039` |
| [keihan_xml_20261013060555.xml](keihan_xml_20261013060555.xml) | [source](https://web.archive.org/web/20261013060555id_/https://www.keihan.co.jp/tinfo/01-traininfo/traininfo20261013135400.xml) | `a44e9d1a09157ed72e601e4d0cb89ac61e4874832be1c893f4198e3451c8f400` |
| [keihan_normal.xml](keihan_normal.xml) | [source](https://www.keihan.co.jp/tinfo/01-traininfo/traininfo20261031014631.xml) | `45794ef6505d79579e0060ae8a7edaa4cb2c14f4b1f8d4ece5b900eb275c95b9` |
| [keihan_filelist.xml](keihan_filelist.xml) | [source](https://www.keihan.co.jp/tinfo/05-flist/FileList.xml) | `f15394f45c71f0f6bb265f53b769fb5021c38c5ac9171bf40ca5bec939cf4558` |
| [keihan_normal.json](keihan_normal.json) | [source](https://www.keihan.co.jp/tinfo/06-app/info.json) | `7ad3a421c8a8363b8eff76e8add6c9a78194ac31fb74f2583e3779fb2539bc37` |
| [mrt_normal.json](mrt_normal.json) | [source](https://www.mytransport.sg/trainstatus) | `57e31474361f31604185b3e963626b423d7b0834306fbae55171f54ebe564ead` |
| [mrt_page.html](mrt_page.html) | [source](https://www.mytransport.sg/trainstatus) | `ee9d8163219b54b7f6c2a3ffc1e8b12302a9e2b3d0c09b43ca069c7c8fa8b119` |
| [jrw_status.json](jrw_status.json) | [source](https://trafficinfo.westjr.co.jp/api/v1/trafficinfo.json) | `a950fd7c2d9613120a7082863513385b1ada05ccaabe37204367c818e4ed4f18` |
| [jrw_api_20261001234249.json](jrw_api_20261001234249.json) | [source](https://web.archive.org/web/20261001234249id_/https://trafficinfo.westjr.co.jp/api/v1/trafficinfo.json) | `ec9e92fb07a5ef709eaf414ec5a6ef778ce3462cc2e3816679a986e3c05ed88b` |
| [jrw_api_20261021235454.json](jrw_api_20261021235454.json) | [source](https://web.archive.org/web/20261021235454id_/https://trafficinfo.westjr.co.jp/api/v1/trafficinfo.json) | `08f30253aaafde7897b0b4c01c021822a99607ac1387f7741ac1369c075e1e09` |

## Singapore MRT mixed-message regression

Captured at `2026-11-02T15:15:25.430700+00:00` (UTC). Exact URLs, request
methods/form fields, original SHA-256 hashes and extraction details are in
[mrt_manifest.json](mrt_manifest.json).

- [mrt_normal_with_unscoped_message.json](mrt_normal_with_unscoped_message.json)
  is the unmodified public `LTAGOVTrainServiceAlerts` POST response. It reports
  `Status=1`, no `AffectedSegments`, and a bus 170/170X diversion in `Message`.
  It is evidence of a normal rail feed carrying an unrelated message, not an
  abnormal rail response.
- [mrt_message_filter.js](mrt_message_filter.js) contains lines 424-459 and
  535-538 of the [official map script](https://www.mytransport.sg/etc/designs/ltagov/custom/map/script.js).
  The UI matches the full `HH:MM-LINE-Major/Minor/Planned` format after trimming,
  ignores other message formats, and initializes rail lines as normal.

The provider excludes non-rail-format messages from line state only when
`Status=1`. Supported rail messages and structured affected segments remain
authoritative. Unsupported `HH:MM-LINE-...` headers remain unscoped `UNKNOWN`;
this prefix is a conservative retention guard, not a scope/severity classifier.
With `Status=2`, unscoped messages remain `UNKNOWN` with their original text.
No bus keywords, route numbers, or incident-specific exclusions are used.
The mixed-feed boundary tests modify the captured JSON and are synthetic.

## Tokyu

See [TOKYU.md](TOKYU.md) for the official normal JSON, public JavaScript and
HTML legend excerpts, original SHA-256 hashes, acquisition method, and the
explicitly synthetic scope of abnormal/recovery tests.

## Keisei

See [KEISEI.md](KEISEI.md) for official live and archived HTML, public notice
scripts, capture times, extraction, original hashes and synthetic-test limits.

## Keio

See [KEIO.md](KEIO.md) for the official normal XML, the one archived abnormal
capture found (and why its original Shift_JIS bytes are not parseable by
`xml.etree`, with a documented UTF-8 transcoding used instead), the public
JavaScript that reads this XML, capture times, original hashes and the
rationale for not decomposing `emergency=true` by line.

## Nankai

Retrieved on 2026-11-01 UTC using httpx GET with redirects enabled. Each HTML
fixture is a BeautifulSoup serialization of `.rosenzu-update-time`,
`#nankai-line`, `#koya-line`, `#nankai-line-wrap`, `#koya-line-wrap`, and
`#semboku-line-wrap` where present, in that order. `#koya-line` contains the
nested Semboku legend on newer pages. No state markers, route labels, source
times or incident text were edited. Scripts, maps and unrelated page content
were omitted. Hashes below are of the complete downloaded response bytes before
extraction. Capture timestamps and the timestamps in filenames are UTC.

| Fixture | Source / capture time (UTC) | SHA-256 of downloaded original |
| --- | --- | --- |
| [nankai_normal.html](nankai_normal.html) | [live source](https://www.traffic.nankai.co.jp/railinfo/01.html), fetched 2026-11-01; displayed update 2026/10/28 22:01 JST | `a3e4a340e612a9b22b24d971b8f4f748013e997f17b708b39c0789b13cf93a44` |
| [nankai_20230814234144.html](nankai_20230814234144.html) | [source](https://web.archive.org/web/20230814234144id_/https://www.traffic.nankai.co.jp/railinfo/01.html), 2023-08-14 23:41:44 | `272e584b50ce22ff279ed64de850a5717e3deef98c18639af4a584724acfd023` |
| [nankai_20250806220111.html](nankai_20250806220111.html) | [source](https://web.archive.org/web/20250806220111id_/https://www.traffic.nankai.co.jp/railinfo/01.html), 2025-08-06 22:01:11 | `fbd242e31d88bccf4acf20e2ab7bf62e534e29a9e7d90c8c44caf2a9e64c202a` |
| [nankai_20250920072018.html](nankai_20250920072018.html) | [source](https://web.archive.org/web/20250920072018id_/https://www.traffic.nankai.co.jp/railinfo/01.html), 2025-09-20 07:20:18 | `c8dd98c2defb9d31300d99dc124c9e6c96385c61d14a12f165537a298822dcee` |
| [nankai_20261004112434.html](nankai_20261004112434.html) | [source](https://web.archive.org/web/20261004112434id_/https://www.traffic.nankai.co.jp/railinfo/01.html), 2026-10-04 11:24:34 | `0d8f992eb9850ba1261959f8f634500912ebcb91adc82b41efc7835508cfded3` |

CDX was queried for `www.traffic.nankai.co.jp/railinfo/01.html`, years
2023–2026, successful responses, collapsed by month. The replay originally
requested at `20261003100124` redirected to `20261004112434`; the fixture uses
the final capture timestamp and its displayed source update is 2026/10/4 20:15
JST. The source's separate current-time field is never used as the update time.

The 2023 capture verifies `times` markers and current suspension statements in
the Nankai and Koya sections. It has no Semboku section and is tested only at
section level. Its Takashinohama label explicitly says replacement bus
(`高師浜線(バス)`); this is historical source evidence, not a claim that trains
ran on that date. The 2025-08 capture verifies `triangle` for Semboku and a
separate limited-express-only notice for Semboku Liner. The 2026-10 capture
verifies `triangle` for Koya and Semboku while cable and Shiomibashi retain
`circle`. Live and 2025-09 captures verify normal `circle` markers. These
establish the marker mapping without classifying current service from narrative
keywords. No distinct partial-suspension marker or same-incident recovery
capture was verified; clearing old snapshots is tested against normal HTML.
Malformed markup and unknown markers in tests are explicitly synthetic.

Terms reviewed on 2026-11-01 UTC: the [general site terms](https://www.nankai.co.jp/terms.html)
and the service page's own usage conditions. Both restrict unapproved reuse;
metadata records `PERMISSION_REQUIRED` and both URLs.
# JR Central

Official conventional-line JSON and history, public rendering scripts, route
master, dedicated status-code mappings, UTC retrieval times, unmodified-body
hashes, excluded Shinkansen/express scopes and synthetic-test limits are
documented in [JRCENTRAL.md](JRCENTRAL.md) and
[jrcentral_manifest.json](jrcentral_manifest.json).

# JR East

Official live route HTML, source URLs, UTC fetch times, original/extracted
hashes, scope decisions and synthetic-test boundaries are documented in
[JREAST.md](JREAST.md) and [jreast_manifest.json](jreast_manifest.json).

# Yurikamome

Official operation HTML, published JavaScript labels, the out-of-hours archive,
source URLs, UTC retrieval times, original/fixture hashes and synthetic-test
boundaries are documented in [YURIKAMOME.md](YURIKAMOME.md) and
[yurikamome_manifest.json](yurikamome_manifest.json).


# Tobu

Official XML, public JavaScript, archive URLs, UTC timestamps, hashes and
publication scopes are documented in [TOBU.md](TOBU.md) and
[tobu_manifest.json](tobu_manifest.json).

# Tokyo Metro

Official current JSON, public rendering scripts, official history evidence,
UTC retrieval timestamps, hashes and synthetic-test boundaries are documented
in [TOKYO_METRO.md](TOKYO_METRO.md) and
[tokyo_metro_manifest.json](tokyo_metro_manifest.json).

# Minatomirai

Official HTML/CSS/JavaScript, archived disruption and normal HTML, UTC retrieval
times, original/extracted hashes, classification limits and synthetic cases are
documented in [MINATOMIRAI.md](MINATOMIRAI.md) and
[minatomirai_manifest.json](minatomirai_manifest.json).

# Toei Subway

Official normal HTML, public script inspection, rendered official history evidence,
UTC retrieval times, hashes and synthetic-test limitations are documented in
[TOEI.md](TOEI.md) and [toei_manifest.json](toei_manifest.json).

# Rinkai Line

Official normal/disruption HTML, a chronological delay-to-normal pair, source
and archive URLs, UTC timestamps, original/extracted hashes, terms scope and
synthetic-test limits are documented in [RINKAI.md](RINKAI.md) and
[rinkai_manifest.json](rinkai_manifest.json).

# Tosaden

Official streetcar main-panel HTML, archived typhoon announcement and normal HTML,
public script inspection, original/extracted hashes, UTC retrieval/capture times and
coverage limits are documented in [TOSADEN.md](TOSADEN.md) and
[tosaden_manifest.json](tosaden_manifest.json).

# Meitetsu

Official normal/disruption HTML, public CSS and inline JavaScript, source and
archive URLs, UTC retrieval/capture times, original/extracted hashes, canonical
route mapping and synthetic-test boundaries are documented in
[MEITETSU.md](MEITETSU.md) and [meitetsu_manifest.json](meitetsu_manifest.json).

# Yui Rail

Official top-page JSON, public script inspection, live and archived normal texts,
archived typhoon suspension and caution notices, UTC retrieval/capture times,
original/fixture hashes and synthetic-test limits are documented in
[YUIRAIL.md](YUIRAIL.md) and [yuirail_manifest.json](yuirail_manifest.json).
# 小田急線

出典・保存時刻・ハッシュ・抽出方法・状態判定の根拠は [ODAKYU.md](ODAKYU.md) と `odakyu_manifest.json` を参照。

# JR九州

公式XML・8エリアの長期見合わせフラグ・表示JavaScript・注意事項HTMLをライブ取得。長期見合わせフラグは構造的に分離された欄として実行時の取得対象外とし、調査記録として保存している。
出典、UTC取得日時、無加工の原本／fixtureハッシュ、判定根拠、取得範囲と
未確認／合成テストの区別は [JRKYUSHU.md](JRKYUSHU.md) と
[jrkyushu_manifest.json](jrkyushu_manifest.json)を参照。

# 京浜急行電鉄

公式運行情報ページのライブ取得と、Wayback Machineに保存された平常・遅延・運転見合わせの
実データ。出典URL、UTC取得日時、原本とfixtureのSHA-256、専用状態欄がなく自由記述のみである
根拠、未確認範囲は [KEIKYU.md](KEIKYU.md) と [keikyu_manifest.json](keikyu_manifest.json) を参照。


# Metro-North Railroad（GTFS-realtime）

2026-11-04 UTCに公式Service Alerts、静的GTFS、画面用路線一覧と公開JavaScriptを取得。
取得元URL・UTC取得時刻・加工方法・原本／fixtureのSHA-256・実応答と合成テストの区別は
[METRO_NORTH.md](METRO_NORTH.md) と [metro_north_manifest.json](metro_north_manifest.json) を参照。

# MTA New York City Subway（GTFS-realtime）

公式GTFS-realtimeアラートフィード（APIキー不要）を2回ライブ取得した無加工のprotobuf応答。
公式仕様書・GTFS-rt proto・静的GTFS `routes.txt` の出典とハッシュ、計画工事の構造的除外の根拠、
実データ／合成テストの区別は [MTA_SUBWAY.md](MTA_SUBWAY.md) と
[mta_subway_manifest.json](mta_subway_manifest.json) を参照。

# 西武鉄道

公式XML（IDS2Web.xml）のライブ正常応答、公開JavaScript（script.js・seiburailways.core.js）、
ホームページの路線名ウィジェットHTML、別エンドポイント（servicestatus.jsonp）がdif/tifを
含まないことの確認をライブ取得。Wayback Machineに本エンドポイントの保存は無く、異常時データは
未確認。出典URL、UTC取得日時、原本とfixtureのSHA-256、状態ラベル・「西武線全線」の判定根拠、
構造的に分離されたplf/pld（重要なお知らせ）の除外根拠、実データ／合成テストの区別は
[SEIBU.md](SEIBU.md) と [seibu_manifest.json](seibu_manifest.json) を参照。

# 京都市営地下鉄

公式トップのライブHTML・公開JavaScript・公開方法の説明・利用条件と、Wayback保存HTMLを調査。
2023-08-15の実際の緊急情報、翌日の掲載終了、ライブの空欄を無加工のローカルfixtureで検証します。
路線・影響・日時を本文から推測しない範囲、保存URL・UTC取得日時・SHA-256、合成テストの区別は
[KYOTO_SUBWAY.md](KYOTO_SUBWAY.md) と [kyoto_subway_manifest.json](kyoto_subway_manifest.json) を参照。

# JR北海道

公式エリア別JSON（道央・道南・道北・道東）をライブ取得した無加工の応答（UTF-8 BOM付き）。
道北エリアでは宗谷線（音威子府～稚内）の実際の運転見合わせ（2026-10-30発生のクマとの衝突）を
取得できた。表示JavaScript・掲載単位名称一覧・利用上の注意ページも確認済み。出典URL、UTC取得
日時、原本とfixtureのSHA-256、線区IDと共通路線IDの対応根拠、未確認／合成テストの区別は
[JRHOKKAIDO.md](JRHOKKAIDO.md) と [jrhokkaido_manifest.json](jrhokkaido_manifest.json) を参照。

# 札幌市営地下鉄

公式の現在ページ（3路線の平常表示）をライブ取得し、`#tmp_contents` を抽出しました。
公式履歴・公開JavaScript・CSSも調査し、異常時の現在ページの形式は未確認です。
取得元・UTC取得日時・原本とfixtureのSHA-256・実データと合成テストの区別は
[SAPPORO_SUBWAY.md](SAPPORO_SUBWAY.md) と
[sapporo_subway_manifest.json](sapporo_subway_manifest.json) を参照。


# 西日本鉄道

公式電車ページ・運行状況HTML・公開JavaScript・利用条件とWayback保存HTMLを調査。
4路線の共通ID再利用、掲載単位と影響対象の区別、平常・鉄道案内・復旧・バスのみの実応答、
未知見出しと合成テストの範囲は [NISHITETSU.md](NISHITETSU.md) を参照。
保存URL・UTC取得日時・原本と無加工fixtureのSHA-256は
[nishitetsu_manifest.json](nishitetsu_manifest.json) に記録しています。

# 名古屋市営地下鉄

公式JSONの平常応答、公開HTML・JavaScript、利用条件、Wayback CDXの空の結果を取得。
URL・UTC取得日時・SHA-256・状態コードの根拠・共通IDの再利用・未確認範囲は
[NAGOYA_SUBWAY.md](NAGOYA_SUBWAY.md) と
[nagoya_subway_manifest.json](nagoya_subway_manifest.json) を参照。

# 相模鉄道

公式の公開運行情報JSON・HTML・表示JavaScript・利用規約と、Waybackの直通中止／平常JSONを調査。
原本は無加工でローカルに保存し、第三者の案内本文はGitに含めません。
URL・UTC取得日時・SHA-256・状態フラグの根拠・未確認範囲・合成テストとの区別は
[SOTETSU.md](SOTETSU.md) と [sotetsu_manifest.json](sotetsu_manifest.json) を参照。

# 香港MTR

公式状態XML・凡例・公開JavaScript・利用規約の調査は [MTR.md](MTR.md)、取得日時・原本ハッシュは [mtr_manifest.json](mtr_manifest.json) を参照。


# Renfe

Renfeの出典・取得範囲・未確認範囲は [RENFE.md](RENFE.md)、原本のUTC取得日時・
SHA-256は [renfe_manifest.json](renfe_manifest.json) を参照。

# Metro Trains Melbourne

公式HTML・公開JavaScriptの逆解析とライブの路線定義／Healthboard JSONを調査。
標準User-Agentで取得し、第三者本文はローカルだけに保存しています。
出典・対応根拠・未確認範囲・合成テストとの区別は
[METRO_TRAINS_MELBOURNE.md](METRO_TRAINS_MELBOURNE.md)、UTC取得日時・原本ハッシュは
[metro_trains_melbourne_manifest.json](metro_trains_melbourne_manifest.json) を参照。

## Trenitalia

Official live HTML, archived national normal bulletins, public JavaScript and terms: [TRENITALIA.md](TRENITALIA.md). Exact UTC retrieval times, URLs, original hashes and local capture names: [trenitalia_manifest.json](trenitalia_manifest.json). Third-party responses remain local; synthetic cases are identified in the evidence note.

# 桃園MRT（桃園捷運）

公式トップの専用運行表示・公開JavaScriptと、平常・全線停止・減速運転の保存HTMLを調査。
出典・分類根拠・未確認範囲は [TAOYUAN_METRO.md](TAOYUAN_METRO.md)、
UTC取得日時・保存URL・原本／抽出後のSHA-256は
[taoyuan_metro_manifest.json](taoyuan_metro_manifest.json) を参照。
第三者HTML・JavaScriptはローカルだけに保存し、Git・配布物には含めません。

# 福岡市交通局

公式運行情報HTML・公開JavaScriptと平常／運転見合わせ予告の保存HTMLを調査。
出典・対応根拠・未確認範囲は [FUKUOKA_SUBWAY.md](FUKUOKA_SUBWAY.md)、
取得日時・保存URL・原本SHA-256は [fukuoka_subway_manifest.json](fukuoka_subway_manifest.json) を参照。



# Sendai City Subway

Official route HTML, public CSS/JavaScript and normal Wayback captures: [SENDAI_SUBWAY.md](SENDAI_SUBWAY.md). Exact request URLs, UTC retrieval times, original and extracted SHA-256 values: [sendai_subway_manifest.json](sendai_subway_manifest.json). Third-party HTML stays local; incident/recovery/corruption tests are synthetic.

## 横浜市営地下鉄

公式の現在一覧・履歴APIと公開JavaScriptを調査しました。根拠・未確認範囲は
[YOKOHAMA_SUBWAY.md](YOKOHAMA_SUBWAY.md)、元URL・UTC取得日時・原本SHA-256・
無加工のfixtureコピーは [yokohama_subway_manifest.json](yokohama_subway_manifest.json) を参照。
履歴を使う現在一覧のテストは合成エンベロープです。第三者応答はGitに含めません。

## 土佐くろしお鉄道

公式トップページ・運行記事・企業情報とWayback保存HTMLを調査しました。
出典・構造・分類根拠・未確認範囲は [TOSAKURO.md](TOSAKURO.md)、
元URL・UTC保存日時・原本と抽出後のSHA-256は
[tosakuro_manifest.json](tosakuro_manifest.json) に記録しています。
HTML・記事本文はローカルだけに保存し、Gitや配布物へ含めません。

# SNCF TGV

公式NeTEx・SIRI SXのライブ応答とOpen Dataメタデータを調査しました。
照合根拠・状態の意味・未確認範囲は[TGV.md](TGV.md)、
元URL・UTC取得日時・HTTP状態・原本SHA-256は
[tgv_manifest.json](tgv_manifest.json)に記録しています。応答原本はローカルにのみ保存します。

## 埼玉高速鉄道

公式公開JSONと表示JavaScriptを調査しました。分類根拠・取得範囲・未確認状態は
[SAITAMA_RAILWAY.md](SAITAMA_RAILWAY.md)、元URL・UTC取得日時・原本SHA-256は
[saitama_railway_manifest.json](saitama_railway_manifest.json) を参照。応答原本はローカルのみ保存します。
