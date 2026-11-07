# Provider別の詳細

各Providerの属性名、取得元、状態の対応付け、対象外の情報、検証に使ったデータの範囲をまとめています。共通の使い方は [README](../README.md)、判定方針は [CONTRIBUTING.md](../CONTRIBUTING.md) を参照してください。

コード例は `async` 関数の中で実行する前提で、`from train_operation_info import Tracker` を省略しています。

## 高雄MRT/LRT

```python
tracker = Tracker(enabled_providers=("kaohsiung_metro",))
await tracker.refresh()
print(tracker.kaohsiung_metro.metro.status)
print(tracker.kaohsiung_metro.light_rail.status)
```

直接使う場合は
`from train_operation_info.providers.kaohsiung_metro import KaohsiungMetroProvider`。
サンプルは `python -m examples.kaohsiung_metro`。既定の取得対象にも含まれます。

[公式トップ](https://www.krtc.com.tw/)のPC・モバイル向け専用状態欄を1回のGETで取得します。
`metro` は紅線・橘線まとめて `GROUP`（`tw:krtc:metro`）、`light_rail` は
環状輕軌の `LINE`（`tw:krtc:light_rail`）。会社は高雄捷運股份有限公司です。
紅線・橘線別の障害状態や影響区間は取得できません。

確認済みの緑色マーカーと完全一致の正常文のみ `NORMAL` とします。
他の文言・色の組み合わせや追加の参照リンクは `UNKNOWN` として原文・マーカー・リンクを保持し、
遅延・運休・現在有効を推測しません。`affected_line_ids=()`、`timing=UNKNOWN`、
`updated_at`・適用開始終了は `None` です。必須構造の欠損・重複やPC／モバイルの不一致では
更新全体を失敗させ、前回値を保持します。

別枠のニュース・重要公告・将来計画・リンク先本文・時刻表・列車位置は対象外です。
生応答の記録にはこれらの対象外部分も含まれます。`NORMAL` は専用状態欄の範囲だけを表します。
正常表示はライブHTMLと2026-10-17の保存HTMLで確認し、異常時の状態欄は未取得です。
未知状態・破損・復旧遷移は合成テストです。公式のプライバシー／情報セキュリティ方針と
著作権表示を確認しましたが再利用許諾は見つからず、メタデータは `UNSPECIFIED` です。
出典と未確認範囲は [KAOHSIUNG_METRO.md](../tests/fixtures/KAOHSIUNG_METRO.md)、
取得日時・原本／抽出後ハッシュは
[kaohsiung_metro_manifest.json](../tests/fixtures/kaohsiung_metro_manifest.json) に記録しています。

## 埼玉高速鉄道（埼玉スタジアム線）

```python
tracker = Tracker(enabled_providers=("saitama_railway",))
await tracker.refresh()
print(tracker.saitama_railway.main.status)
print(tracker.saitama_railway.main.alerts)
```

直接使う場合は `from train_operation_info.providers.saitama_railway import SaitamaRailwayProvider`。
サンプルは `python -m examples.saitama_railway`。既定の取得対象に含まれ、
公式公開JSONへ1回のGETを行います。赤羽岩淵～浦和美園の1路線で、Yahooに登録済みの
共通ID `jp:operator_6792d0f7efc4:line_1b9213f482b7` を使います。

公式運行情報ページと同じ `latest=true` の現在項目だけを解析します。
`stdtxt` の平常アイコンと `message` の専用状態欄を根拠に平常・遅延・見合わせ／運休・
一部運休を対応付けます。直通中止・再開・振替輸送等は `ALERT`、未知ラベル・typeは
原文付き `UNKNOWN`。空配列・履歴のみも `UNKNOWN` です。複数現在項目の本文は
すべて保持し、状態は共通の優先順位で集約します。

発信日時を日本現地時刻として `updated_at` に採用し、外側の生成日時は使いません。
`latest` は障害の適用時期を保証しないため `timing=UNKNOWN`、適用期間は未設定です。
現在項目の長期案内を本文で除外しません。履歴、別枠のニュース・臨時ダイヤ、遅延証明書、
振替輸送の詳細、他社線の状態は対象外ですが、生応答記録には履歴も含まれます。
`NORMAL` は公式の掲載基準（15分以上の遅れ・見込み）とこの取得範囲内の状態です。

平常JSONと公開JSを確認し、異常時・復旧は合成テストです。根拠・未確認範囲は
[SAITAMA_RAILWAY.md](../tests/fixtures/SAITAMA_RAILWAY.md)、出典・ハッシュは
[saitama_railway_manifest.json](../tests/fixtures/saitama_railway_manifest.json) に記録しています。
[サイトポリシー](https://www.s-rail.co.jp/sitepolicy/) が情報の印刷・引用・転用に承諾を
求めるため、利用許諾区分は `PERMISSION_REQUIRED` です。

## TfL（Transport for London）

```python
tracker = Tracker(enabled_providers=("tfl",))
await tracker.refresh()
print(tracker.tfl.bakerloo.status)
print(tracker.tfl.elizabeth.alerts)
```

直接使う場合は `from train_operation_info.providers.tfl import TflProvider`。
サンプルは `python -m examples.tfl`。既定の取得対象に含まれ、APIキーなしで
公式Unified APIへ1回のGETを行います。通常の30秒間隔制限が適用されます。

| 系統 | 属性 | 共通ID / 運行会社 |
| --- | --- | --- |
| Tube 11路線 | `bakerloo`, `central`, `circle`, `district`, `hammersmith_city`, `jubilee`, `metropolitan`, `northern`, `piccadilly`, `victoria`, `waterloo_city` | `gb:london_underground:<属性>` / London Underground Limited |
| Overground 6路線 | `liberty`, `lioness`, `mildmay`, `suffragette`, `weaver`, `windrush` | `gb:london_overground:<属性>` / First Rail London Limited |
| Elizabeth line | `elizabeth` | `gb:elizabeth_line:main` / GTS Rail Operations Limited |
| DLR | `dlr` | `gb:dlr:network` / KeolisAmey Docklands Limited |
| Tram | `tram` | `gb:london_trams:network` / Tram Operations Limited |

DLRとTramはネットワーク全体の `GROUP`、他は `LINE` です。取得元TfLと実際の
運行会社を区別します。Overgroundは旧来の全体1項目に統合しません。

公式の状態コードとラベルの組を検証し、10/18を `NORMAL`、6/9を `DELAYED`、
1/2/16を `SUSPENDED`、3/5/7/11を `PARTIAL_SUSPENSION` とします。その他の
確認済みコードは詳細な影響を補わず `ALERT`、未知または不一致の組は原文付きの
`UNKNOWN` です。Planned Closureは現在の全面停止を断定せず `ALERT`、Service Closedも
営業時間外と障害を区別できないため `ALERT` です。複数状態は既存の共通優先順位で
集約し、各状態のアラートと本文はすべて保持します。本文中の代替輸送先を影響路線に
追加しません。

日付指定なしの現在状態 `lineStatuses` を取得します。`PlannedWork` は期間の長短を
分類する項目ではなく、この一覧に長期専用の分離欄はないため混在する工事案内も保持します。
`isNow=false` は将来予告を意味せず、日付や本文から除外しません。既知の非平常状態の
専用 `isNow=true` のみ `timing=ACTIVE`、その他は `UNKNOWN`。明示された各有効期間を
別アラートにし、離れた期間を一続きにしません。更新日時は確認できず `updated_at=None`。
別の日付指定・将来一覧、駅・設備情報、バス、船、ケーブルカー、National Rail、到着予測は
対象外です。平常はこの取得範囲内の意味です。

商用・非商用再利用の条件と `Powered by TfL Open Data` の帰属表示、規約の登録条項、
匿名アクセス枠の違いを `metadata` に記録しています。匿名通信が成功することだけで
利用条件を満たすとは扱いません。再利用時は公式規約全文を確認してください。
実データで平常・遅延・運休・一部運休・工事案内・複数状態を確認し、その他のコードと復旧・
失敗ケースは合成テストです。出典と未確認範囲は [TFL.md](../tests/fixtures/TFL.md)、
取得日時とハッシュは [tfl_manifest.json](../tests/fixtures/tfl_manifest.json) を参照。

## 桃園MRT（桃園捷運）

```python
tracker = Tracker(enabled_providers=("taoyuan_metro",))
await tracker.refresh()
print(tracker.taoyuan_metro.airport.status)
print(tracker.taoyuan_metro.airport.alerts)
```

`Tracker()` の既定の取得対象です。直接使う場合は
`from train_operation_info.providers.taoyuan_metro import TaoyuanMetroProvider`。
サンプルは `python -m examples.taoyuan_metro` です。
[公式トップページ](https://www.tymetro.com.tw/tymetro-new/tw/)の専用運行表示から、
桃園機場捷運を1路線として取得します。共通IDは `tw:tymetro:airport`、
運行会社は `桃園大眾捷運股份有限公司` です。普通車と直達車は分割しません。

保存HTMLで確認したラベルとCSSの組を根拠に、`green` + `正常營運` は `NORMAL`、
`red` + `全線停駛` は `SUSPENDED`、`yellow` + `減速營運` は `ALERT` とします。
減速運転から実際の遅延・減便を推測せず、影響は `OTHER` です。
未知・矛盾するラベルとCSSの組は原文・CSSを保持して `UNKNOWN`、
モバイル／デスクトップ表示の不一致・欠損は `ParseError` として前回値を保持します。

取得範囲は専用運行表示のみです。別枠のニュース・将来の運転計画・工事予告・
リンク先の詳細・列車位置・時刻表は対象外ですが、生HTTP記録には別枠の本文も含まれます。
`NORMAL` はこの表示の範囲内の状態です。専用表示内の未知の案内を本文から除外しません。
公式の更新時刻・適用期間は確認できず、`updated_at` と適用期間は `None`、
適用時期は `UNKNOWN` とします。トップの時計を更新時刻には使いません。

平常・全線停止・減速運転は公式の保存HTMLで検証しました。
停止後の平常保存ページも確認しましたが、正確な再開時刻・同一事象への明示的な復旧案内は未確認です。
遅延・一部運休の表示も未確認です。破損・未知表示・通信失敗のテストは合成です。
出典とハッシュは [TAOYUAN_METRO.md](../tests/fixtures/TAOYUAN_METRO.md) と
[taoyuan_metro_manifest.json](../tests/fixtures/taoyuan_metro_manifest.json) に記録しています。
[公式利用条件](https://www.tymetro.com.tw/tymetro-new/tw/_pages/note/intellect.html)は
合理的使用等を除く著作物の利用に同意・許諾を求めており、`PERMISSION_REQUIRED` としています。

## Renfe Cercanías / Rodalies

```python
tracker = Tracker(enabled_providers=("renfe",))
await tracker.refresh()
print(tracker.renfe.cercanias.status)
print(tracker.renfe.cercanias.updated_at)
print(tracker.renfe.cercanias.alerts)
```

[公式障害データセット](https://data.renfe.com/es/dataset/incidencias-avisos)の
GTFS-realtime JSONを取得します。`python -m examples.renfe` でも確認できます。
共通IDは `es:renfe:cercanias`、運行会社は `Renfe Operadora`、掲載範囲は
`GROUP` です。既定の取得対象に含まれます。

フィードと現行static GTFSの対象IDに不整合があるため、個別路線への対応は未提供です。
案内の `affected_line_ids=()`、ネットワーク状態は案内があれば `UNKNOWN`。
検証済みの空FULL_DATASETだけが掲載範囲内の `NORMAL` になります。
明示effectはアラートの影響へ直接対応しますが、本文や地域番号から状態を推定しません。
工事・長期案内・復旧文・駅設備情報は同じ一覧に混在するため保持します。
AVE・長距離列車・列車別の遅延・リンク先詳細は対象外です。

元のentity IDが異なる対象一覧で重複する応答にも対応し、IDとselector集合のハッシュで
両方を保持します。esラベルが重複する翻訳は非空の本文を原順序で空行連結し、
言語を推測し直しません。見出しがない案内のtitleには元のentity IDを使います。
`activePeriod`は掲載期間のため、障害期間や `ACTIVE` 判定に使いません。

2026-11-04の実応答には69件があり、全件effectが未指定でした。フィードの更新時刻は
2026-10-07T07:32:52Zと古いままです。`updated_at` と `fetched_at` を併せて確認してください。
空一覧・復旧・明示effectの検証は合成データによるもので、実際の復旧応答は未確認です。
出典と検証範囲は [RENFE.md](../tests/fixtures/RENFE.md) に記録しています。

データセットはCC BY 4.0、[公式条件](https://data.renfe.com/es/legal)は商用・非商用の
再利用を認めています。帰属表示 `Origen de los datos: Renfe Operadora`、原本の更新日・
条件の保持、ライセンスへのリンク、変更の表示等の条件をメタデータに記録しています。

## 香港MTR

```python
tracker = Tracker(enabled_providers=("mtr",))
await tracker.refresh()
print(tracker.mtr.tsuen_wan.status)
print(tracker.mtr.airport_express.alerts)
```

`Tracker()`の既定の取得対象です。`python -m examples.mtr`でも実行できます。[MTR公式サイト](https://www.mtr.com.hk/en/customer/main/index.html)の公開状態XMLから、10路線を取得します。属性は`tsuen_wan`（荃湾線）、`kwun_tong`（観塘線）、`island`（港島線）、`south_island`（南港島線）、`tseung_kwan_o`（将軍澳線）、`tung_chung`（東涌線）、`disneyland_resort`（迪士尼線）、`airport_express`（機場快線）、`east_rail`（東鉄線）、`tuen_ma`（屯馬線）です。共通IDは`hk:mtr:...`、運行会社はMTR Corporation Limitedです。

公式凡例の`green`は`NORMAL`、`yellow`（遅延または段階的復旧）は`DELAYED`、`red`・`pink`・`typhoon`は`ALERT`です。`red`は全線・一部の運休を確定しません。`grey`は非サービス時間で、運行アラート上は`NORMAL`とし、原コードを`source_status`に残します。未知コードは`UNKNOWN`、路線・必須項目の欠落や通信失敗時は前回の結果を保持します。同じ路線のメッセージ見出しとリンクを保持し、本文から障害種別・対象路線・適用期間を推測しません。平常色にもメッセージがあれば`ALERT`です。

軽鉄・高速鉄道、別のTraffic Newsバナー、詳細ページ、別配信の特別・長期案内は取得しません。公式の掲載基準は継続的な追加行車時間20分超等で、`NORMAL`はこの範囲内の平常表示です。`lastBuildDate`のタイムゾーン等を確定する仕様は未確認のため`updated_at=None`、適用時期は`timing=UNKNOWN`です。

実取得した平常XMLで確認し、異常・復旧は公開凡例に基づく合成テストで検証しています。出典と未確認範囲は[MTR.md](../tests/fixtures/MTR.md)に記録しています。利用条件のメタデータは[公式規約](https://www.mtr.com.hk/en/customer/main/terms_of_use.html)の個人・非商用利用制限に基づく`PRIVATE_USE_ONLY`です。

## 日本：JR

### JR北海道

```python
tracker = Tracker(enabled_providers=("jrhokkaido",))
await tracker.refresh()
print(tracker.jrhokkaido.soya.status)
print(tracker.jrhokkaido.hakodate_line.alerts)
```

`Tracker()` の既定の取得対象です。`python -m examples.jrhokkaido` で取得例を実行できます。[公式運行情報](https://www3.jrhokkaido.co.jp/webunkou/index.html) が参照する道央・道南・道北・道東の4エリアJSON（`json/area/area_02.json`〜`area_05.json`）を取得します。属性は `gakuen_toshi`（学園都市線）、`hidaka`（日高線）、`soya`（宗谷線）、`sekihoku`（石北線）、`furano`（富良野線）、`sekisho`（石勝線）、`hanasaki`（根室線（花咲線））、`senmo`（釧網線）の既存共通ID8件と、`airport`（エアポート）、`hakodate_chitose`（函館・千歳線）、`muroran`（室蘭線）、`hakodate_liner`（はこだてライナー）、`hakodate_line`（函館線）、`nemuro`（根室線）の新規`GROUP`6件です。

公式JSONの`senkuStatus`は線区（掲載単位）別のコード値を持ち、`0`は`NORMAL`、`1`は運休・３０分以上の遅延・運転見合わせを区別しない`ALERT`、それ以外（提供時間5:00～24:00外を示す`2`）は`UNKNOWN`です。本文からの状態推測はしません。学園都市線・日高線・宗谷線・石北線・富良野線・石勝線・花咲線・釧網線は公式の掲載単位名が既存カタログの単一路線と一致するため既存IDを再利用します。エアポート・函館・千歳線・室蘭線・はこだてライナー・函館線・根室線は、既存カタログが分割する千歳線・函館本線・室蘭本線・根室本線の区間より広い範囲、または対応区間を確認できない掲載単位のため、JR九州のエリア掲載単位と同様に新規`GROUP`とし、既存の分割区間へのエイリアスにはしません。特急列車（エリアごとの列車種別単位で物理路線に対応しない）と北海道新幹線（`area_06.json`が存在せず共通カタログにも路線がない）は対象外です。

状態コードが`1`で、同じ応答の`gaikyo`配列にその線区の所属エリアで有効な案内（`eikyo`フラグが立ち、見出しが空でない項目）があれば、その本文・見出し・掲載時刻を`updated_at`に採用します。一致する案内がない場合は固定文言のアラートのみを保持し`updated_at=None`です。トップレベルの`time`はJR東日本の地域ページと同様「現在」で終わる表示用の値のため採用しません。長期案内が構造的に分離されている根拠はなく、`NORMAL`は読んでいる欄に案内がないことだけを示します。`timing`は常に`UNKNOWN`です。

2026年11月の調査時には道北エリアで宗谷線（音威子府～稚内）の実際の運転見合わせ（列車とクマの衝突）を確認しており、他の13掲載単位の障害・復旧・未知コードの検証は合成データです。調査根拠・出典・ハッシュは [JRHOKKAIDO.md](../tests/fixtures/JRHOKKAIDO.md) を参照してください。公式の無断転載・複写等を禁じる記載に基づき、利用条件のメタデータは `PERMISSION_REQUIRED` です。

### JR東日本

JR東日本だけを取得する例です。`python -m examples.jreast` でも確認できます。

```python
tracker = Tracker(enabled_providers=("jreast",))
await tracker.refresh()
print(tracker.jreast.yamanote.status)
print(tracker.jreast.joban.alerts)
print(tracker.jreast.tohoku_shinkansen.status)
```

[公式運行情報](https://traininfo.jreast.co.jp/train_info/)の関東・東北・信越・新幹線の4ページから、86路線・系統の状態ラベルと本文を取得します。`yamanote`、`keihin_tohoku`、`chuo_rapid`、`chuo_sobu_local`、`saikyo`、`kawagoe`、`joban`、`joban_rapid`、`joban_local`、`koumi`、`tohoku_shinkansen` などを型付きプロパティで参照できます。全属性は `providers/jreast/provider.py` に静的に定義されています。東京モノレールは `tokyo_monorail`、BRTは `ofunato_brt`・`kesennuma_brt` です。運行会社は共通カタログの `Line.operator` を参照します。

掲載基準は4時～翌2時の30分以上の遅れ・見込みで、BRTは長時間の運転見合わせが対象です。`NORMAL` はその基準による平常表示です。複数地域や同一路線の複数項目は統合し、平常の項目で別の障害を消しません。「一部運休」は `PARTIAL_SUSPENSION`、運転見合わせ中の「運転再開見込」は `SUSPENDED`、原文が運休に言及していても「お知らせ」は `ALERT` とします。取得元の区間別IDと範囲が異なる広域の項目は、既存のYahoo区間へ割り当てず別IDです。

地域ページの「現在」は配信日時ではないため `updated_at=None` とし、取得時刻は `fetched_at` に保持します。特急列車、路線一覧とは別の新幹線の列車別運休情報、別配信のお知らせ欄・PDF、詳細ページの更新履歴・配信時刻、遅延証明書は取得しません。未知の状態は原文付きの `UNKNOWN`、路線・必須項目の欠落は `ParseError` とし、失敗時は前回の結果を保持します。

平常・遅延・見合わせ・一部運休・再開見込・お知らせは公式の実データで検証しています。復旧への更新、未知状態、欠損は合成テストです。出典と対応範囲は [tests/fixtures/JREAST.md](../tests/fixtures/JREAST.md) に記録しています。[サイト利用条件](https://www.jreast.co.jp/site/rules.html/)を確認したメタデータの許諾区分は `PERMISSION_REQUIRED` です。

### JR東海

```python
tracker = Tracker(enabled_providers=("jrcentral",))
await tracker.refresh()
print(tracker.jrcentral.tokaido_atami_toyohashi.status)
print(tracker.jrcentral.chuo.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.jrcentral` で取得例を実行できます。
[公式在来線運行情報](https://traininfo.jr-central.co.jp/zairaisen/index.html) の13路線・区間を扱います。
属性は `tokaido_atami_toyohashi`、`tokaido_toyohashi_maibara`、`chuo`、`kansai`、`kisei`、`takayama`、`taketoyo`、`iida`、`taita`、`gotemba`、`minobu`、`sangu`、`meisho` です。
中央線は名古屋～塩尻の一括掲載のため、Yahooの区間別IDとは別の共通IDを使います。他の12路線・区間は既存IDを再利用し、取得結果を独立して保持します。

専用の詳細状態コードに基づき、運転見合わせは `SUSPENDED`、遅れありは `DELAYED`、平常は `NORMAL` とします。「遅れ・運休あり」「運休あり」は範囲・影響が一意でないため `ALERT` で原文を保持し、未知のコードは `UNKNOWN` です。本文から運行状態を推測しません。メンテナンス・必須項目の欠損・未知の路線・通信失敗時は直前の結果を保持します。

更新日時と適用時期を確認できる専用項目がないため、`updated_at=None`、`timing=UNKNOWN` です。提供基準は概ね10分以上の遅れとその見込みで、平常表示はこの取得範囲の状態を意味します。別枠のお知らせ、特急・ホームライナー等、振替輸送、画像・PDF、列車位置、遅延証明書は取得しません。

**新幹線は未対応です。** 調査時には詳細JSONが公式トップページへリダイレクトされ、トップページ用サマリーも空で、運行状態を検証できませんでした。
在来線の実際の遅延JSON・公式履歴、その後の平常JSONと公開表示コードで確認しています。平常への切り替えで古い案内が消えることも検証しています。運転見合わせ・運休は実応答を未確認で、対応するテストは合成です。出典・ハッシュ・判定根拠は [tests/fixtures/JRCENTRAL.md](../tests/fixtures/JRCENTRAL.md) を参照してください。利用条件メタデータは公式の無断転載等の制限に基づき `PERMISSION_REQUIRED` です。

### JR西日本

JR西日本は `dailyData` の当日分だけを解析します。分離された地域案内 `areaAnnouncements`（長期運休・工事予告など）、過去の履歴・翌日以降の日別データ・列車名単位の特急情報・フェリーは対象外です。APIの同じ応答に含まれる地域案内は、通信・生応答の記録からは除去しません。`NORMAL` は日次障害欄に掲載がないことを示し、地域案内に掲載された長期運休がないことを保証しません。

### JR四国

```python
tracker = Tracker(enabled_providers=("jrshikoku",))
await tracker.refresh()
print(tracker.jrshikoku.seto_ohashi.status)
print(tracker.jrshikoku.yodo.alerts)
```

`Tracker()` の既定の取得対象にも含まれます。路線属性は `seto_ohashi`、`yosan_takamatsu_matsuyama`、`yosan_matsuyama_uwajima`、`dosan_tadotsu_kochi`、`dosan_kochi_kubokawa`、`kotoku`、`mugi`、`tokushima`、`naruto`、`yodo` です。Yahooの同一区間と共通の路線IDを使います。

[公式運行情報](https://www.jr-shikoku.co.jp/info/index.html) は概ね30分以上の遅れ・運休とその見込みを掲載します。公式の概要・地図は遅延と運転見合わせを区別しないため、案内のある路線は `ALERT` とし、具体的な影響はアラート本文に保持します。`delay_lines` ではなく `affected_lines`・`alerts` で案内を参照してください。見出しが路線を特定しない案内は `affected_line_ids=()` とし全路線に添付します。予讃線・土讃線の区間を地図から特定できない場合は両区間を対象にします。

未知の表示は `UNKNOWN`、構造欠損・矛盾は `ParseError` となり、取得・解析失敗時は前回の結果を保持します。平常表示に更新日時はなく `updated_at=None` です。注意事項欄の固定案内、リンク先PDF、列車走行位置、遅延証明書は取得しません。調査根拠と未確認範囲は [tests/fixtures/JRSHIKOKU.md](../tests/fixtures/JRSHIKOKU.md) に記録しています。

### JR九州

```python
tracker = Tracker(enabled_providers=("jrkyushu",))
await tracker.refresh()
print(tracker.jrkyushu.fukuoka_kitakyushu.status)
print(tracker.jrkyushu.kumamoto.alerts)
print(tracker.jrkyushu.kyushu_shinkansen.updated_at)
```

`Tracker()` の既定の取得対象にも含まれます。`python -m examples.jrkyushu` で取得例を実行できます。
[公式運行情報](https://www.jrkyushu.co.jp/trains/info/) のXMLを取得します。構造的に分離された8個の長期見合わせフラグ（別テキストファイル）は対象外で、取得・検証しません。
公開属性は `fukuoka_kitakyushu`、`oita`、`saga_nagasaki`、`kumamoto`、`miyazaki`、`kagoshima`、
`kyushu_shinkansen`、`nishi_kyushu_shinkansen` です。

在来線6エリアは `GROUP`、新幹線2路線は `LINE` です。
エリアをYahoo登録済みの個別路線へ展開せず、エリア案内の `affected_line_ids` は空にします。
XMLの案内ありなら `ALERT` とします。
本文から遅延・運休範囲・現在有効かを推測せず、`timing=UNKNOWN` とします。
未知の状態は原文付き `UNKNOWN`、構造欠損・日時不正・通信失敗時は全8掲載単位の前回値を保持します。

`updated_at` はXML案内が持つ更新日時の最大値で、日本時間・分精度です。
平常時は `None` です。端末時刻とXML全体の時刻は代用しません。
長期見合わせフラグ、別枠の工事・災害案内、リンク先PDF、路線図画像、列車位置、遅延証明書は取得範囲外です。
`NORMAL` はXMLに案内がないことだけを示し、長期の運転見合わせ区間がないことを保証しません。

ライブXMLの案内なしを確認済みです。実障害XMLと同一障害の復旧は未確認で、
案内本文・更新日時・消去・未知状態・故障は公式JavaScriptを根拠にした合成テストで検証しています。
取得範囲、出典・ハッシュ、利用条件の確認範囲は [JRKYUSHU.md](../tests/fixtures/JRKYUSHU.md) を参照してください。
再利用条件は未確認のため `UNSPECIFIED` としています。

## 日本：関東（横浜市営地下鉄）

```python
tracker = Tracker(enabled_providers=("yokohama_subway",))
await tracker.refresh()
print(tracker.yokohama_subway.blue.status)
print(tracker.yokohama_subway.green.alerts)
```

`YokohamaSubwayProvider` は既定の取得対象です。`python -m examples.yokohama_subway` で
単独取得できます。両路線はYahooと既存の共通路線ID・会社情報を共有し、状態は独立しています。
[公式運行情報](https://status.hamabus.city.yokohama.lg.jp/operation/list) が参照する
日本語の地下鉄現在一覧JSONを取得し、公式画面と同じく路線ごとの項目が0件なら `NORMAL`。
公式履歴と公開表示コードで確認した状態ID `2`・状態名「遅延」の組だけを `DELAYED`、
他は `UNKNOWN` とし、各一覧レコードをJSONとして `alerts` に保持します。
未知路線・路線名不一致・重複・必須構造破損は解析失敗として前回の2路線を保持します。

`timing=UNKNOWN`、`active_from/active_until=None`、`updated_at=None`。
一覧のサーバー時刻・案内期間・画面に表示されない状態更新時刻を代用しません。
履歴・詳細画面だけの追加情報や振替路線・市バス・証明書・位置情報・別のニュースは取得範囲外。
一覧に混在する案内は保持し、`NORMAL` はこの一覧の掲載範囲だけを表します。
現在の異常時応答・運休コード・グリーンライン異常時・同一障害の復旧は未確認です。
一般サイトポリシーのサブサイト/APIへの適用は未確認のため、利用条件は `UNSPECIFIED`。
出典と合成テストの区別は [YOKOHAMA_SUBWAY.md](../tests/fixtures/YOKOHAMA_SUBWAY.md) を参照。

## 日本：北海道（地下鉄）

### 仙台市交通局

```python
tracker = Tracker(enabled_providers=("sendai_subway",))
await tracker.refresh()
print(tracker.sendai_subway.namboku.status)
print(tracker.sendai_subway.tozai.alerts)
```

取得元IDは `sendai_subway`、クラスは `SendaiSubwayProvider` です。
`Tracker()` の既定の取得対象に含み、`python -m examples.sendai_subway` で単独取得できます。
南北線・東西線は既存のYahooと同じ共通路線ID・運行会社を使用し、取得状態は独立しています。

公式の南北線 `/unkou/nanbokusen/`、東西線 `/unkou/touzaisen/` のHTMLを取得します。
専用状態欄の `ope_normal` と、証明書ボタンを除いた内容全体が確認済みの平常表示に
完全一致するときだけ `NORMAL` です。他の表示・未知クラス・追加本文は `UNKNOWN` とし、
案内本文とリンク先URLを保持します。本文やCSSクラス名から遅延・運休種別を推測しません。
路線ごとのページから対象路線を特定し、本文の他路線名に影響を広げません。

[公式の掲載基準](https://www.kotsu.city.sendai.jp/unkou/)は30分以上の遅れの発生・見込みです。
`NORMAL` はこの取得範囲の平常表示であり、短時間の遅れも含めて全運行が平常という意味ではありません。
`updated_at=None`、`timing=UNKNOWN`、`active_from/active_until=None` です。
WordPressのページ更新日時を運行状態の更新時刻に転用しません。
市バス、別のお知らせ、遅延証明書、X、リンク先本文は取得しません。
路線ページ内に混在する長期案内を本文から除外せず、追加の詳細欄も保持します。
2路線のどちらかの通信・解析が失敗した場合は、両路線の前回スナップショットを保持します。

実際の平常HTMLと2026年4月の東西線の平常保存ページを検証に使用しています。
異常時の現行形式は未確認で、未知表示・復旧・破損の検証は合成データです。
調査根拠・出典・ハッシュは [SENDAI_SUBWAY.md](../tests/fixtures/SENDAI_SUBWAY.md) に記録しています。
無断複製・転用を制限する公式方針に基づき、利用条件メタデータは `PERMISSION_REQUIRED` です。

### 札幌市営地下鉄

```python
tracker = Tracker(enabled_providers=("sapporo_subway",))
await tracker.refresh()
print(tracker.sapporo_subway.namboku.status)
print(tracker.sapporo_subway.tozai.alerts)
print(tracker.sapporo_subway.toho.status)
```

`Tracker()` の既定の取得対象です。`python -m examples.sapporo_subway` で取得例を実行できます。
[公式運行情報](https://operationstatus.city.sapporo.jp/unkojoho/) の南北線・東西線・東豊線の路線別案内を取得し、Yahooと既存の共通路線IDを共有します。取得結果は独立しています。

確認済みの平常文「現在、10分以上の遅れは発生していません。」との完全一致だけを `NORMAL` とします。それ以外は路線別の案内原文を保持した `UNKNOWN` です。公式履歴では遅れ・復旧を確認しましたが、現在ページの異常時の状態語彙は未確認で、本文や履歴ラベルから遅延・運休を推測しません。追加本文がある場合も平常扱いせず保持します。`updated_at=None`、`timing=UNKNOWN` です。欠損・重複等の解析失敗や通信失敗時は前回値を保持します。

掲載基準は10分以上の遅れとその見込みです。履歴・遅延証明書・市電・翻訳・別枠のお知らせは取得しません。路線欄で構造的に分離できない案内は原文のまま保持します。平常は実応答、異常・復旧・構造破損は合成テストです。調査根拠・未確認範囲・ハッシュは [SAPPORO_SUBWAY.md](../tests/fixtures/SAPPORO_SUBWAY.md) を参照してください。利用条件メタデータは `PERMISSION_REQUIRED` です。

## 日本：関東

### 東武鉄道

```python
tracker = Tracker(enabled_providers=("tobu",))
await tracker.refresh()
print(tracker.tobu.skytree.status)
print(tracker.tobu.tojo.alerts)
```

`Tracker()` の既定の取得対象にも含まれます。路線属性は `nikko_express`、`isesaki_express`、`sl_dl`、`th_liner`、`skytree`、`isesaki_north`、`nikko_north`、`kameido_daishi`、`urban_park`、`tj_liner`、`tojo`、`ogose` です。`python -m examples.tobu` で取得例を実行できます。

[公式運行情報](https://www.tobu.co.jp/service_status/) が読み込むXMLの12掲載単位を扱います。久喜以北エリアは伊勢崎線の久喜～伊勢崎・佐野線・桐生線・小泉線、南栗橋以北エリアは日光線の南栗橋～東武日光・宇都宮線・鬼怒川線の合計です。これらと亀戸線・大師線、特急・ライナーは `GROUP` として個別路線から区別します。スカイツリーライン・アーバンパークライン・東上線・越生線は既存の共通路線IDを再利用します。

XMLは状態コードを持たず、各掲載単位の案内本文を返します。平常の定型文は `NORMAL`、それ以外は `ALERT` とし、本文から遅延・運休を推測しません。`delay_lines` ではなく `affected_lines` と `alerts` で案内を参照してください。掲載基準は30分以上の遅れやその見込みです。本文中の発生時刻と画面の現在時刻は更新日時として扱わず、`updated_at=None` を返します。構造欠損・未登録路線・通信失敗時は前回の結果を保持します。

台風の減便案内・実際の遅延を含む保存XMLで検証しています。同一障害の復旧データは未確認です。地図画像・列車位置・遅延証明書・リンク先PDFは取得しません。調査根拠と合成テストの範囲は [tests/fixtures/TOBU.md](../tests/fixtures/TOBU.md) を参照してください。

### 西武鉄道

```python
tracker = Tracker(enabled_providers=("seibu",))
await tracker.refresh()
print(tracker.seibu.shinjuku.status)
print(tracker.seibu.ikebukuro_chichibu.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.seibu` でも確認できます。属性は `shinjuku`（新宿線）、`toshima`（豊島線）、`ikebukuro_chichibu`（池袋線・西武秩父線）、`seibuen`（西武園線）、`kokubunji`（国分寺線）、`tamako`（多摩湖線）、`yamaguchi`（山口線）、`tamagawa`（多摩川線）、`haijima`（拝島線）、`sayama`（狭山線）、`yurakucho`（西武有楽町線）の既存共通ID11件です。公式トップページの路線名ウィジェットは池袋線・西武秩父線を別項目として掲載しますが、Yahooの既存共通IDと同じく1路線に統合しています。

[公式運行情報](https://www.seiburailway.jp/railway/railwayinfo/) が参照する公開XML（`https://www.seiburailway.jp/api/v1/travelinfo/raw/IDS2Web.xml`）の `info/dif`（路線別 `lin/nm`・`sts/nm`）と `info/txt`（全体の案内文）を取得します。公開JavaScriptで確認した対応により、状態ラベルが「運転見合わせ」「運転再開見込」「運休」のいずれかに一致する場合だけ `SUSPENDED`、それ以外の空でないラベルは `ALERT` とします。遅延と一部運休は公式コード自身も区別しないため、どちらにも振り分けません。路線名が「西武線全線」の場合は11路線全てに適用し、それ以外は公式トップページで確認した12個の路線名表記との部分一致で対応付けます。未知の路線表記は `ParseError` とし前回値を保持します。`info/txt` が対象路線なしで案内文のみを持つ場合は `affected_line_ids=()` の `ALERT` を保持し、他の路線が本来平常でも `UNKNOWN` にします。掲載基準は15分以上の遅れです。

同じXMLが公開する `info/tif`（地図パターン）と `info/plf`（`plf`/`pld`）は取得しません。別エンドポイント `/api/v1/servicestatus.jsonp` がライブ確認で `dif`/`tif` を含まず `plf.pld` だけをバナー表示に使うことから、`plf`/`pld` は構造的に分離された長期・重要案内の欄と判断し、このProviderは対象外としています。`timing` はこのProviderでは設定せず常に `UNKNOWN` です。

ライブ正常XMLは実データで確認済みです。Wayback Machineに本エンドポイントの保存はなく、異常時の実データは未確認のため、運転見合わせ・ALERT・路線全体案内・対象未特定案内・未知路線名・構造破損のテストは公開JavaScriptの分岐を根拠にした合成データです。出典・ハッシュ・判定根拠は [tests/fixtures/SEIBU.md](../tests/fixtures/SEIBU.md) を参照してください。公式運行情報ページに無断転載・複写等を制限する記載があるため、利用条件のメタデータは `PERMISSION_REQUIRED` です。

### 京成電鉄

```python
tracker = Tracker(enabled_providers=("keisei",))
await tracker.refresh()
print(tracker.keisei.main.status)
print(tracker.keisei.narita_sky_access.alerts)
print(tracker.keisei.chiba_chihara.scope)
```

`python -m examples.keisei` でも確認できます。属性は `main`、`narita_sky_access`、`oshiage`、`kanamachi`、`chiba_chihara`、`matsudo` です。[公式運行情報](https://www.keisei.co.jp/traininfo/index.php)の日本語の路線別状態・原因・区間と、対応する詳細本文を取得します。千葉線・千原線は公式の合算項目で、既存のYahoo共通IDを再利用し `LineScope.GROUP` としています。東成田線の独立した掲載単位は未確認のため、このProviderの属性には含みません。

平常・遅れ・一部運休・運転見合わせは公式の実HTMLで検証しています。障害一覧にない対象路線は掲載基準上の平常として扱い、未知の路線別状態は原文付き `UNKNOWN`、必須構造の欠損は `ParseError` として直前の結果を保持します。掲載基準はおおむね15分以上の遅れの発生・見込みです。ページの「現在」時刻は情報の更新時刻と確認できないため `updated_at=None` です。

公開JavaScriptの追加告知も日本語の有効フラグと日本時間の掲載期間を確認して取得します。対象路線を断定できない告知は `affected_line_ids=()` とし、平常の路線に `ALERT` を付けます。履歴・路線図画像・列車位置・遅延証明書は取得しません。アーカイブと合成テストの区別・取得元・ハッシュは [tests/fixtures/KEISEI.md](../tests/fixtures/KEISEI.md) に記録しています。公式ページには無断転載・複写等を制限する記載があるため、利用条件のメタデータは `PERMISSION_REQUIRED` です。

### 京王電鉄

```python
tracker = Tracker(enabled_providers=("keio",))
await tracker.refresh()
print(tracker.keio.main.status)
print(tracker.keio.inokashira.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.keio` でも確認できます。属性は `main`（京王線）、`shinsen`（京王新線）、`sagamihara`（京王相模原線）、`takao`（京王高尾線）、`keibajo`（京王競馬場線）、`doubutsuen`（京王動物園線）、`inokashira`（京王井の頭線）の7路線です。Yahooと共通の路線IDを使い、取得結果は独立しています。

[公式運行情報ページ](https://www.keio.co.jp/unkou/unkou_pc.html)が参照する唯一の公式XML（[unkouInformation.xml](https://www.keio.co.jp/_system/_unkou/unkouInformation.xml)）を取得します。このXMLは7路線を区別せず、`emergency`（真偽値）・`unkouInformation`（案内本文）・`time`（日本時間の更新時刻）を公開します。`emergency=false` かつ本文が定型の平常文と完全一致するときだけ7路線すべてを `NORMAL` とし、それ以外（`true` や未知の値、`false` でも別の本文）は本文を本文のまま保持した単一のお知らせとして `affected_line_ids=()` を付け、7路線すべてを `UNKNOWN` にします。

平常時の案内文は「京王線・井の頭線は平常通り運転しています。」のように両方のグループ名を挙げますが、2019年の実際の障害アーカイブでは「井の頭線　運転を見合せています」のように一方のみを挙げており、単一の実例からは路線別の対応を一般化できません。このため自由記述からの路線別判定は行いません。

`imgTime`・`lang_time` は時刻の別表記で未使用です。ページが読み込む公開JavaScript（`unkou_time.js`・`unkou_cookie_manager.js`）は上記XMLの取得と更新時刻表示・自動更新間隔のCookie管理だけを行い、別の判定材料は確認できません。公式サイトの著作権条項は複製・転載・二次的使用等を私的利用の留保なく一律に禁じているため、利用条件のメタデータは `PERMISSION_REQUIRED` です。

平常表示はライブ取得と2011～2024年のWayback保存で確認しています。唯一見つかった異常時アーカイブ（2019年、Shift_JISで保存）は、CPython標準の `xml.etree` がXML宣言の多バイト符号化（Shift_JIS）を解釈できないため、そのままでは `ParseError` になります。この実データの内容をUTF-8へ再符号化した合成fixtureで `emergency=true` の判定を検証しています。出典・ハッシュ・この制限の詳細は [tests/fixtures/KEIO.md](../tests/fixtures/KEIO.md) に記録しています。

### 小田急電鉄

```python
from train_operation_info import Tracker

tracker = Tracker(enabled_providers=("odakyu",))
await tracker.refresh()
print(tracker.odakyu.odawara.status)
print(tracker.odakyu.enoshima.alerts)
print(tracker.odakyu.tama.updated_at)
```

小田急線は `Tracker()` の既定の取得対象です。`python -m examples.odakyu` でも実行できます。[公式運行情報](https://traininfo.odakyu-rt.jp/train_status)の区間別状態を取得し、Yahooとは同じ共通IDで独立した結果を保持します。遅延・全区間の運休・一部区間の運休を専用コードで区別します。本文だけから運休や適用時期を推測せず、`timing` は `UNKNOWN` です。特急・直通運転など対象路線を確定できない案内は `affected_line_ids=()` で保持します。

更新日時は運行案内の `update_time` がある場合だけ設定します。お知らせタブ・列車位置・深夜のサービス対象時間判定は取得対象外です。取得範囲の平常表示は列車の運転時間を保証しません。取得元の利用条件は `tracker.odakyu.metadata`、調査根拠と保存応答は [ODAKYU.md](../tests/fixtures/ODAKYU.md) を参照してください。

### 東急電鉄

```python
tracker = Tracker(enabled_providers=("tokyu",))
await tracker.refresh()
print(tracker.tokyu.toyoko.status)
print(tracker.tokyu.den_en_toshi.alerts)
```

`Tracker()` の既定の取得対象に含まれます。属性は `toyoko`、`meguro`、
`shin_yokohama`、`den_en_toshi`、`oimachi`、`ikegami`、`tamagawa`、
`setagaya`、`kodomonokuni` です。Yahooと共通の路線IDを使い、取得結果は独立しています。

[公式運行情報](https://www.tokyu.co.jp/unten2/unten.html)が参照する公開JSONを取得します。
掲載基準は15分以上の遅れ・運転見合わせが発生または見込まれる場合です。
丸は `NORMAL`、バツは `SUSPENDED`、三角は遅延・運休・直通運転中止などを含む
`ALERT` です。三角だけから `DELAYED` や `PARTIAL_SUSPENSION` は推測しません。
案内文は改行を含むテキストで保持し、対象路線を特定できないお知らせは
`affected_line_ids=()` として、平常表示の路線を `UNKNOWN` にします。
未知コードは原文付きの `UNKNOWN`、必須項目の欠損や矛盾は `ParseError` です。
取得・解析失敗時は直前のスナップショットを保持します。

画面の現在時刻はブラウザが生成するため更新日時には使いません。
JSONの `kousin_jikoku` は平常時に `null` で、非null時の形式・意味は未確認です。
そのため `updated_at=None` とし、障害案内に非空の値があれば原文を残します。
東急の取得元では、みなとみらい線の独立した状態・路線図画像・振替輸送先一覧は取得対象外です。みなとみらい線は専用の `minatomirai` Providerで取得できます。
平常時は公式の実データで、異常時と復旧は公開JavaScriptに基づく合成データで検証しています。
調査根拠と保存データの出典は [tests/fixtures/TOKYU.md](../tests/fixtures/TOKYU.md) を参照してください。

### 京浜急行電鉄（京急）

```python
tracker = Tracker(enabled_providers=("keikyu",))
await tracker.refresh()
print(tracker.keikyu.main.status)
print(tracker.keikyu.airport.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.keikyu` でも確認できます。属性は `main`（本線）、`airport`（空港線）、`daishi`（大師線）、`kurihama`（久里浜線）、`zushi`（逗子線）です。既存の共通IDをそのまま再利用しています。

[公式運行情報ページ](https://unkou.keikyu.co.jp/)はサーバーレンダリングで、5路線を区別しない全線一括の案内を1件だけ掲載します。専用の状態コードや路線別欄はなく、自由記述の案内文と明示的な更新日時（`YYYY/MM/DD HH:MM更新`、日本時間）だけが構造化されています。確認できた唯一の固定文言「京急線は平常通り運転しています。」のときだけ `NORMAL` とし、それ以外は5路線すべてを `UNKNOWN` とし、案内本文をそのまま保持した単一のアラートを付けます。実データには特定区間だけの運転見合わせ（津波警報による堀ノ内～浦賀間等）や、路線名を挙げない遅延案内が含まれており、本文中の路線名・「遅れ」「見合わせ」等の語から対象路線や遅延・運休の種別を判定することはしません（`affected_line_ids=()`）。阪神電鉄の全体サマリーと同様、どの路線の案内か特定できないため、影響のない路線まで `ALERT` にすることはしません。

未知の表示は原文付きの `UNKNOWN`、見出し・更新日時・案内欄の構造欠損は `ParseError` とし、取得・解析失敗時は前回の結果を保持します。適用時期を判別する専用項目はないため `timing=UNKNOWN` です。公式ページの掲載基準はおおむね10分以上の遅れ・運転見合わせです。平常・遅延・運転見合わせは公式ページとWayback Machineに保存された実データで検証し、固定文言に文言が混在する未確認のケースのみ合成データで検証しています。出典・ハッシュ・判定根拠は [tests/fixtures/KEIKYU.md](../tests/fixtures/KEIKYU.md) に記録しています。利用条件は一般のサイト利用規約が私的利用の範囲を留保し、運行情報ページ自体はさらに無断転載・複写を禁じる記載があるため、メタデータの許諾区分は `PERMISSION_REQUIRED` です。ODPTの京急データはチャレンジ限定ライセンスのため使用していません。

### みなとみらい線

```python
tracker = Tracker(enabled_providers=("minatomirai",))
await tracker.refresh()
print(tracker.minatomirai.main.status)
print(tracker.minatomirai.main.alerts)
```

`Tracker()` の既定の取得対象にも含まれます。`python -m examples.minatomirai` で実行できます。[公式運行情報ページ](https://www.mm21railway.co.jp/service/)から横浜～元町・中華街の案内を取得します。Yahooと同じ共通路線IDを使い、取得結果は独立して保持します。

定型の平常文全体が一致する場合は `NORMAL`、公式の遅延時間欄が「大幅な遅れ」の場合は `DELAYED` です。それ以外の案内は原文付きの `ALERT` とし、本文から運転見合わせ・一部運休を推測しません。運休・計画運休の案内も `affected_lines` / `alerts` で参照してください。平常文の後に注意書きが続く場合も案内を保持します。

発生時刻・原因・遅延時間の詳細表はアラート本文にラベル付きで保持します。発生時刻を更新日時として使わず、`updated_at=None` を返します。未知の表示クラスや矛盾する平常表示は `UNKNOWN`、構造欠損・重複・通信失敗時は直前の結果を保持します。掲載基準は10分以上の遅れ・運転見合わせとその見込みです。列車位置・遅延証明書・リンク先の振替輸送一覧は取得しません。

平常・遅延・台風の注意／運休案内を実際の公式HTMLで検証しています。同一障害の復旧と現在の異常時HTMLは未確認で、平常への切り替えは別時点の平常HTMLで検証しています。出典・ハッシュ・合成テストの範囲は [tests/fixtures/MINATOMIRAI.md](../tests/fixtures/MINATOMIRAI.md) に記録しています。公式の無断転載禁止の記載に基づき、利用条件メタデータは `PERMISSION_REQUIRED` です。

### 箱根登山鉄道

```python
tracker = Tracker(enabled_providers=("hakone_tozan",))
await tracker.refresh()
print(tracker.hakone_tozan.main.status)
print(tracker.hakone_tozan.main.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.hakone_tozan` でも実行できます。
[箱根ナビの公式運行情報](https://www.hakonenavi.jp/transportation/)から、箱根登山電車（小田原～強羅）の状態欄と区間別案内・注記を取得します。Yahooと既存の共通路線IDを使い、取得結果は独立して保持します。

確認済みの平常表示だけを `NORMAL`、共通の警告表示を `ALERT` とします。本文や「運休、運転見合わせあり」という見出しだけから全線運休・一部運休・遅延を区別しません。未知の状態、営業終了、運行予定、平常表示と追加案内の混在は原文付きの `UNKNOWN` です。案内は `alerts` で参照してください。必須構造の欠損・重複・通信失敗時は直前の結果を保持します。

更新日時・適用時期の専用項目を確認できていないため、`updated_at=None`、`timing=UNKNOWN` です。ページ生成時刻の `data-debug` は更新日時に使いません。ケーブルカー・ロープウェイ・船・バス・混雑情報・別枠のニュースや全体案内・リンク先記事は解析対象外です。生応答の保存にはこれらも含まれます。`NORMAL` は取得範囲内の表示で、別記事の計画変更等の不存在を保証しません。

平常表示と他交通機関の警告を実際の保存HTMLで確認しました。現在の形式での登山電車の異常時応答・遅延・同一障害の復旧は未確認で、登山電車の警告テストは合成です。調査根拠・保存応答・ハッシュは [HAKONE_TOZAN.md](../tests/fixtures/HAKONE_TOZAN.md) を参照してください。公式ポリシーの無断転載等の制限を反映し、利用条件メタデータは `PERMISSION_REQUIRED` です。

### 東京メトロ

```python
tracker = Tracker(enabled_providers=("tokyo_metro",))
await tracker.refresh()
print(tracker.tokyo_metro.ginza.status)
print(tracker.tokyo_metro.tozai.alerts)
```

`Tracker()` の既定の取得対象にも含まれます。路線属性は `ginza`、`marunouchi`、`hibiya`、`tozai`、`chiyoda`、`yurakucho`、`hanzomon`、`namboku`、`fukutoshin` です。`python -m examples.tokyo_metro` で取得例を実行できます。

[公式運行情報](https://www.tokyometro.jp/unkou/history/ginza.html) が参照するJSONから、9路線の状態・本文・影響区間・原因を取得します。Yahooの同一路線と共通IDを使い、取得結果は独立して保持します。公式の掲載基準は5分以上の遅れとその見込みです。状態ラベルから遅延・運転見合わせ・折返し運転を判定し、ダイヤ乱れ・運転再開後のダイヤ乱れは `ALERT` として本文を残します。これらの案内は `affected_lines` と `alerts` でも参照してください。

未知の状態・運転終了・矛盾する平常表示は `UNKNOWN`、構造欠損・路線不整合・通信失敗時は前回の結果を保持します。JSONに更新日時がないため `updated_at=None` です。画面の現在時刻や履歴の日時を代用しません。平常時に残る過去の原因欄からアラートを生成しません。丸ノ内線・千代田線の支線は各路線に含め、支線別・駅別・方面別の状態、地図、列車位置、遅延証明書、過去履歴は取得しません。

平常時JSONと公式履歴の異常・復旧文言を確認しています。異常時の現在情報JSONはアーカイブ取得がHTTP 429となり未確認で、同形式での異常・復旧テストは合成データです。調査根拠と出典は [tests/fixtures/TOKYO_METRO.md](../tests/fixtures/TOKYO_METRO.md) に記録しています。

### 都営地下鉄

```python
tracker = Tracker(enabled_providers=("toei",))
await tracker.refresh()
print(tracker.toei.asakusa.status)
print(tracker.toei.mita.alerts)
```

`Tracker()` の既定の取得対象に含まれます。属性は `asakusa`（浅草線）、
`mita`（三田線）、`shinjuku`（新宿線）、`oedo`（大江戸線）です。
`python -m examples.toei` で取得例を実行できます。

[公式運行情報](https://www.kotsu.metro.tokyo.jp/subway/schedule/index.html) の
4路線の要約と案内本文を取得します。掲載基準は15分以上の遅れまたはその見込みで、
`NORMAL` はこの基準による平常表示です。「ダイヤ乱れ」は `ALERT` として
本文を保持します。`affected_lines` と `alerts` で案内を参照してください。
独立した遅延・全線運休・一部運休のラベルは未確認のため推測せず、未知ラベルや
要約と本文の矛盾は `UNKNOWN`、構造欠損・通信失敗では直前の結果を保持します。
画面の現在時刻は配信時刻ではないため `updated_at=None` です。

Yahooと共通の路線IDを使い、取得結果は独立しています。都電荒川線・
日暮里・舎人ライナー・列車位置・遅延証明書は対象外です。
異常時と復旧は公式履歴で確認しましたが、現在ページの異常時HTMLは未取得で、
そのパーサーテストは合成です。調査根拠と制限は
[tests/fixtures/TOEI.md](../tests/fixtures/TOEI.md) に記録しています。
利用条件は一般ポリシーと運行情報固有の転載制限を反映した `PERMISSION_REQUIRED` です。

### ゆりかもめ

```python
tracker = Tracker(enabled_providers=("yurikamome",))
await tracker.refresh()
print(tracker.yurikamome.main.status)
print(tracker.yurikamome.main.updated_at)
print(tracker.yurikamome.main.alerts)
```

`Tracker()` の既定の取得対象にも含まれます。[公式運行情報ページ](https://www.yurikamome.co.jp/ride-guidance/operation.html) が読み込むHTMLから、新橋～豊洲のゆりかもめ線の状態・案内本文・配信日時（日本時間）を取得します。Yahooの同一路線と共通IDを使い、取得結果は独立して保持します。

遅延・運転見合わせ・一部運休・折返し運転のラベルを共通状態に対応付けます。運転再開などの案内は `ALERT` として保持します。未知のラベル、平常運転の見出しに情報提供時間外の案内だけがある場合は `UNKNOWN` です。構造欠損・不正日時・通信失敗では前回の結果を保持します。

公式の掲載基準は概ね15分以上の遅れとその見込みです。区間・原因は本文に掲載された範囲で保持し、駅別状態・遅延証明書は取得しません。平常時と情報提供時間外は実データで確認し、異常時と復旧は公式JavaScriptのラベルに基づく合成テストで検証しています。出典・未確認範囲は [tests/fixtures/YURIKAMOME.md](../tests/fixtures/YURIKAMOME.md) に記録しています。

### 相模鉄道

```python
tracker = Tracker(enabled_providers=("sotetsu",))
await tracker.refresh()
print(tracker.sotetsu.main.status)
print(tracker.sotetsu.main.alerts)
```

`Tracker()` の既定の取得対象です。`python -m examples.sotetsu` でも確認できます。[公式運行情報](https://www.sotetsu.co.jp/train/status/)が参照する公開JSON `https://cdn.sotetsu.co.jp/unkou/dat/train_status1_v2.json` を取得します。属性 `main` は相鉄線全体の1掲載単位で、Yahooの相鉄線と既存共通ID `jp:sotetsu:line_bcfb80c3830e` を再利用し、取得結果は独立して保持します。本線・いずみ野線・新横浜線への分割は行いません。

公式の公開JavaScriptが `IRREGULAR=false` を「相鉄線平常運転」、`true` を「相鉄線運行情報あり」と表示することを根拠に、`NORMAL`／`ALERT` に対応付けます。`MSG`（運行情報）と、空でない `MSG2`（振替輸送）を原文のまま保持します。遅延・運転見合わせ・一部運休を本文や英語の `E_STATUS` から推測しません。掲載基準は10分以上の遅れ・運転見合わせとその見込みです。`timing=UNKNOWN`、適用期間は未設定です。

`DATE` の更新日時としての意味は未確認で、画面の「現在の情報です」はブラウザの時計なので、`updated_at=None` とします。必須項目の欠損・型不一致、空の本文、掲載項目の欠損・重複は `ParseError` とし前回値を保持します。`MSG2` の省略は公式の空文字へのフォールバックに合わせて許容します。別取得の `owabi.json`（お詫び）とmicroCMSの `train-alerts`（電車のお知らせ）は構造的に分離された別欄のため対象外です。遅延証明書・列車位置・他社線情報も取得しません。`NORMAL` はこの取得範囲内の状態です。

ライブの平常JSONと、2023年7月17日の東横線方面との直通中止（目黒線方面は継続）、別時点の平常JSONを確認しました。同一障害の復旧・現在の異常JSON・実際の振替輸送欄の内容は未確認で、これらの動作検証は合成データです。出典とハッシュは [SOTETSU.md](../tests/fixtures/SOTETSU.md) を参照してください。公式の運行情報固有の転載・複写禁止に基づき、メタデータは `PERMISSION_REQUIRED` です。一般規約が留保する法令上の私的利用等も `usage_note` に記録しています。

### りんかい線

```python
tracker = Tracker(enabled_providers=("rinkai",))
await tracker.refresh()
print(tracker.rinkai.main.status)
print(tracker.rinkai.main.updated_at)
print(tracker.rinkai.main.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.rinkai` で取得例を実行できます。[公式運行情報](https://service.twr.co.jp/rinkai/public/information?lang=ja)の大崎～新木場の案内を取得し、Yahooの同一路線と共通IDを使って独立した結果を保持します。

確認済みの平常文全体が一致すれば `NORMAL`、それ以外の案内は原文付きの `ALERT` です。独立した状態コードがないため、本文の単語から遅延・運休・一部運休を推測しません。`affected_lines` / `alerts` で案内を参照してください。平常文と追加案内が混在する場合は原文付きの `UNKNOWN`、構造欠損・不正な更新日時・通信失敗時は直前の結果を保持します。

本文に明示された「更新」日時だけを日本時間の `updated_at` とします。ページ上部の現在時刻は使用せず、平常時など更新日時がない場合は `None` です。継続期間・適用時期は専用項目がなく、条件付きの将来案内も混在するため、両方 `UNKNOWN` のまま保持します。

掲載対象は30分以上の遅れやその見込み・JRとの直通運転中止・運転中止などです。別枠のニュース・リンク先の計画変更・列車位置・遅延証明書・公式Xは取得しません。平常表示は小さな遅延や別記事の案内がないことを保証しません。

実際の雪・台風・遅延・直通運転中止の保存HTMLと、遅延後の平常HTMLで検証しています。現行の異常時HTML・長期運休・独立した一部運休は未確認です。出典・ハッシュ・合成テストの範囲は [tests/fixtures/RINKAI.md](../tests/fixtures/RINKAI.md) に記録しています。HTMLの再利用条件を明記した一般規約は確認できず `UNSPECIFIED` とし、リンクされたSNS規約の転載制限は適用範囲を区別してメタデータに記録しています。

## 日本：中部

### 名古屋鉄道（名鉄）

```python
tracker = Tracker(enabled_providers=("meitetsu",))
await tracker.refresh()
print(tracker.meitetsu.nagoya_main.status)
print(tracker.meitetsu.inuyama.alerts)
print(tracker.meitetsu.tokoname_airport.source_line_names)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.meitetsu` でも確認できます。
属性は `nagoya_main`、`toyokawa`、`nishio`、`gamagori`、`mikawa`、`toyota`、
`tokoname_airport`、`chikko`、`kowa_chita`、`tsushima_bisai`、`takehana_hashima`、
`inuyama`、`hiromi`、`komaki`、`kakamigahara`、`seto` です。
常滑線・空港線、河和線・知多新線、津島線・尾西線は、それぞれ既存の共通IDの単位で統合します。
同じ路線のYahooの取得結果とは独立しています。

[公式運行情報](https://top.meitetsu.co.jp/em/)の専用の「路線／区間」欄を解析します。
「運転見合せ」は `SUSPENDED` で、路線の一部区間の見合わせも含みます。
「遅延・一部運休」は両者を区別できないため `ALERT` とし、区間・理由・備考を原文で保持します。
自由記述の再開・予告から専用欄の状態を上書きしません。対象未特定の案内は
`affected_line_ids=()` で保持し、専用欄で状態が確認できない路線を `UNKNOWN` にします。

平常表示は概ね15分以上の遅れ等の掲載基準によるものです。平常ページが提供時間外
（日本時間00:31～04:59）の場合は、公式JavaScriptの表示に合わせて `UNKNOWN` にします。
画面の時計や作成時刻を更新日時とみなさず、`updated_at=None`、`timing=UNKNOWN` です。
別枠の重要告知、振替・バス代行輸送の案内、地図、走行位置、遅延証明書、リンク先は取得対象外です。
未知の表示は原文付きの `UNKNOWN`、必須構造の欠損は `ParseError` とし、取得失敗時は前回値を保持します。
平常・見合わせ・混合状態・予告は公式の保存HTMLで検証しています。現在の異常時ライブ取得と
異常時のリダイレクトは未確認で、復旧への更新・提供時間・未知表示・欠損のテストは合成です。
出典と加工内容は [tests/fixtures/MEITETSU.md](../tests/fixtures/MEITETSU.md) に記録しています。

## 日本：関西

### 近鉄

近鉄だけを取得する例です。`python -m examples.kintetsu` でも確認できます。

```python
tracker = Tracker(enabled_providers=("kintetsu",))
await tracker.refresh()
print(tracker.kintetsu.osaka.status)
print(tracker.kintetsu.kyoto.alerts)
```

近鉄の属性は `namba`、`nara`、`kyoto`、`kashihara`、`keihanna`、`osaka`、`nagoya`、`minami_osaka`、`yoshino`、`ikoma`、`tenri`、`tawaramoto`、`shigi`、`yunoyama`、`suzuka`、`yamada`、`toba`、`shima`、`domyoji`、`nagano`、`gose`、`ikoma_cable`、`nishi_shigi_cable` です。

近鉄公式の[運行情報ページ](https://www.kintetsu.jp/unkou/unkou.html)は15分以上の遅れを掲載対象とします。`NORMAL` はこの掲載基準による表示です。障害一覧を検証できた場合は、掲載されていない路線を `NORMAL` にします。対象路線を特定できない全体のお知らせは原文と `affected_line_ids=()` を保持し、状態を `UNKNOWN` にします。

路線別アラートの `description` は、一覧の詳細リンク先にある案内本文です。本文セルの改行を整え、掲載されている区間・時刻・振替輸送の案内も文章のまま保持します。`ServiceAlert.source_url` は詳細ページ、`Line.source_url` は一覧ページです。同じ詳細URLは1回の更新につき一度だけ取得します。詳細の取得・解析に失敗した場合も更新全体を失敗とし、前回の結果を保持します。従来の「路線名: 状態／原因: …／詳細: URL」という合成文は生成しません。

状態は一覧の状況欄だけから判定し、詳細本文から推測しません。本文の時刻・区間は構造化せず、`updated_at=None`、`timing=UNKNOWN` を維持します。平常・運転見合わせ・一部運休・お知らせ・「遅延」と詳細本文は公式ページの実データで、別表記の「遅れ」と未知表示・詳細欠損等は合成データで検証しています。

### 南海電鉄

南海電鉄だけを取得する例です。

```python
tracker = Tracker(enabled_providers=("nankai",))
await tracker.refresh()
print(tracker.nankai.main.status)
print(tracker.nankai.airport.alerts)
print(tracker.nankai.semboku.updated_at)
```

南海の属性は `main`（南海本線）、`airport`、`wakayama_port`、`takashinohama`、`kada`、`tanagawa`、`koya`（なんば～極楽橋）、`cable`、`shiomibashi`（汐見橋～岸里玉出）、`semboku` です。公式の[運行情報ページ](https://www.traffic.nankai.co.jp/railinfo/01.html)にある路線別の記号と対象欄を解析します。掲載基準は20分以上の遅れが発生・見込まれる場合で、`NORMAL` はその基準による平常表示です。高野線の2区間は取得元が分けて表示するため別の共通IDです。

特急・観光列車だけのお知らせは原文を保持し、`affected_line_ids=()` とします。掲載された系統内の平常路線には `ALERT` を付けます。路線全体の遅延・運休には置き換えません。未知の路線記号は `UNKNOWN`、路線・本文・更新日時の欠損は `ParseError` とします。独立した一部運休の記号は未確認です。遅延・運転見合わせは公式アーカイブでも検証していますが、運転見合わせの保存ページは泉北線の掲載前のため該当系統ごとのテストです。出典と加工内容は [tests/fixtures/SOURCES.md](../tests/fixtures/SOURCES.md) に記録しています。

### 阪神・大阪モノレール

阪神・大阪モノレールのサマリーが影響路線を特定しない場合は、原文を持つアラートを残し、路線状態は `UNKNOWN` にします。未特定の影響対象は `affected_line_ids=()` です。

### 大阪メトロ

大阪メトロの属性は `midosuji`、`tanimachi`、`yotsubashi`、`chuo`、`sennichimae`、`sakaisuji`、`nagahori_tsurumi_ryokuchi`、`imazatosuji`、`new_tram` です。各Providerの属性は `provider.py` に静的に定義されています。

[公式運行情報ページ](https://subway.osakametro.co.jp/guide/subway_information.php) 本体の路線別ステータス欄を解析します。地下鉄8路線とニュートラムの計9路線が対象です。
埋め込みの詳細アプリは調査環境でHTTP 403となったため取得しません。この試作のアラートは公式の状態表示を正規化したサマリーで、障害の詳細本文・区間・原因は含みません。
通常表示は実ページ、遅延・運休表示はWayback Machineに保存された公式ページのHTMLで確認しています。2023年8月15日、2024年8月30日（日本時間）、2026年1月11日の実表示をテストに使用し、運休から遅延、平常への更新も検証しています。
保存ページの出典と抽出方法は [tests/fixtures/README.md](../tests/fixtures/README.md) に記録しています。未知の表示やHTML欠落は合成HTMLでも検証しています。
他のProviderの実データとアーカイブの出典は [tests/fixtures/SOURCES.md](../tests/fixtures/SOURCES.md) を参照してください。MRTと大阪モノレールの異常時は、公開コードの解析と合成データでの検証までです。
公式の掲載基準外の小さな遅延まで検出するものではありません。公式ページに掲載された利用条件は利用者側で確認してください。

## 日本：四国・九州・沖縄

### 福岡市交通局

```python
tracker = Tracker(enabled_providers=("fukuoka_subway",))
await tracker.refresh()
print(tracker.fukuoka_subway.kuko.status)
print(tracker.fukuoka_subway.hakozaki.status)
print(tracker.fukuoka_subway.nanakuma.status)
```

`FukuokaSubwayProvider` は `Tracker()` の既定の取得対象です。
`python -m examples.fukuoka_subway` で単独取得できます。
[公式運行情報](https://subway.city.fukuoka.lg.jp/status/) の現在の運行案内欄を取得し、
空港線・箱崎線・七隈線の既存共通IDを再利用します。

平常定型文全体の一致だけを `NORMAL`、その他の掲載を `ALERT` として原文・リンクを保持します。
実際の運転見合わせ予告でも平常時と同じアイコンが使われているため、アイコン・本文から
遅延・運休や適用時期を推測しません。全体の案内を3路線に共有し、`affected_line_ids=()`、
`timing=UNKNOWN`、適用期間は未設定です。各路線の障害を確認したという意味ではありません。

専用の「更新」欄だけを `Asia/Tokyo` 付き `updated_at` に使い、空欄は `None`。
ページ生成時の「現在」時刻は使いません。欠損・重複・空欄本文・不正な更新日時は `ParseError`。
別欄の計画運休、履歴、遅延証明書、列車位置、乗り入れ先JR線、リンク先記事は対象外です。
現在の運行欄に混在する予告は保持します。生応答記録には対象外のヘッダーやリンクも含まれます。

平常・運転見合わせ予告の実保存HTMLと合成の破損・復旧ケースで検証します。
出典と未確認範囲は [FUKUOKA_SUBWAY.md](../tests/fixtures/FUKUOKA_SUBWAY.md) を参照。
公式の利用制限に基づく許諾区分は `PRIVATE_USE_ONLY` です。

### 西日本鉄道

```python
tracker = Tracker(enabled_providers=("nishitetsu",))
await tracker.refresh()
print(tracker.nishitetsu.tenjin_omuta.status)
print(tracker.nishitetsu.dazaifu.alerts)
print(tracker.nishitetsu.amagi.status)
print(tracker.nishitetsu.kaizuka.status)
```

`Tracker()` の既定の取得対象です。`python -m examples.nishitetsu` で取得例を実行できます。
[公式電車ページ](https://www.nishitetsu.jp/train/)が参照する
[運行状況](https://jik.nishitetsu.jp/traffic/default.htm)の `div.traffic` を取得します。
4路線ともYahooと既存の共通IDを再利用し、取得結果は独立して保持します。

専用見出し「天神大牟田線（太宰府線・甘木線含む）」の案内を `tenjin_omuta`・`dazaifu`・`amagi`、
「貝塚線」の案内を `kaizuka` に `ALERT` として保持します。グループ掲載は個別の影響対象を
確定しないため `affected_line_ids=()` です。復旧案内も同じ欄に残る実例があり、
遅延・見合わせ・一部運休や現在有効かどうかを本文から推測しません。
年のない「現在」の表示から更新日時を作らず、`updated_at=None`、`timing=UNKNOWN`、適用期間も未設定です。

案内なしの定型段落、または既知のバス見出しだけなら `NORMAL`。
この状態は緊急案内欄に鉄道の掲載がないことに限定し、通常運行や小規模な遅延がないことを保証しません。
`高速バス`・`一般路線バス` は構造的に除外します。未知の見出しはバスと断定せず、
全4路線を `UNKNOWN` にして原文と対象不明のアラートを保持します。
空欄・重複・欠損・不正な見出し本文の組は `ParseError` とし、直前のスナップショットを保持します。

別枠のニュース・X・リンク先記事・遅延証明書・列車位置は取得しません。
鉄道欄内に長期案内が構造的に分離される根拠はなく、その欄の案内は保持します。
HTTP応答の記録には対象外のバス本文やリンク一覧が含まれます。
平常、鉄道案内、復旧、バスのみの実HTMLで解析を検証し、未知見出し・破損・掲載削除の連続更新は合成テストです。
出典・ハッシュ・未確認範囲は [NISHITETSU.md](../tests/fixtures/NISHITETSU.md) を参照してください。
公式サイト利用規定に基づくメタデータの許諾区分は `PERMISSION_REQUIRED` です。

### とさでん交通

```python
tracker = Tracker(enabled_providers=("tosaden",))
await tracker.refresh()
print(tracker.tosaden.main.status)
print(tracker.tosaden.main.alerts)
```

`Tracker()` の既定の取得対象にも含まれます。`python -m examples.tosaden` で取得例を実行できます。
[公式の電車運行状況](https://www.tosaden.co.jp/info/service.php?ID=1)の主本文を取得し、
路面電車全体を `main` の1掲載単位として扱います。Yahooの「とさでん交通線」と共通IDを使い、
取得結果は独立して保持します。

確認した平常の見出し・本文全体が一致すれば `NORMAL`、それ以外の案内は原文付き `ALERT` です。
状態コードがないため、文章から現在の遅延・全線運休・一部運休を推測しません。
運休予告等は `delay_lines` ではなく `affected_lines` / `alerts` で参照してください。
平常文と別の案内が混在する場合は `UNKNOWN`、構造欠損・重複・通信失敗時は前回の結果を保持します。
主本文に更新日時や適用期間の独立した項目がないため、`updated_at=None`、
アラートの適用時期（`timing`）は `UNKNOWN` です。

公式の掲載基準は30分以上の遅れ、またはその見込みです。
`NORMAL` は主本文のこの基準の表示であり、別枠の「運行についてのお知らせ」とリンク先に載る
長期案内・ダイヤ変更・車両単位の運休の有無までは保証しません。別枠の記事、バス、時刻表、車両位置は取得対象外です。
平常と台風の運休予告は実際の公式HTMLで検証しました。同一障害の復旧・現在の異常時HTMLは未確認です。
出典・ハッシュ・合成テストの範囲は [tests/fixtures/TOSADEN.md](../tests/fixtures/TOSADEN.md) に記録しています。
公式運行状況ページの無断転記・複写等を禁じる記載に基づき、利用条件メタデータは `PERMISSION_REQUIRED` です。

### ゆいレール

```python
tracker = Tracker(enabled_providers=("yuirail",))
await tracker.refresh()
print(tracker.yuirail.main.status)
print(tracker.yuirail.main.updated_at)
print(tracker.yuirail.main.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.yuirail` で取得例を実行できます。[公式トップページ](https://www.yui-rail.co.jp/)の運行情報欄が読み込むJSONから、那覇空港～てだこ浦西の日本語テキストを取得します。Yahooの同一路線と共通IDを使い、取得結果は独立して保持します。

取得元は状態コード・路線別の欄・配信日時を持たないため、確認済みの平常文と完全一致した場合だけ `NORMAL` とし、それ以外は原文付きの `ALERT` とします。本文の語句から遅延・終日運休・一部運休を推測しません。`affected_lines` / `alerts` で案内を参照してください。2026-08-25の保存応答のように、平常運行と翌日の注意喚起が同じ文に含まれる場合も `ALERT` です。

`updated_at` は取得元に配信日時がないため `None` です。適用時期・継続期間・区間・原因は `UNKNOWN` のまま保持します。リンク先の詳細、遅延証明書、多言語欄、駅別・方向別の状態は取得しません。

平常文と台風による終日運休は公式のライブ応答・保存応答で確認し、未知の文言・構造欠損は合成テストで検証しています。出典・ハッシュは [tests/fixtures/YUIRAIL.md](../tests/fixtures/YUIRAIL.md) に記録しています。サイトの著作権・転載制限の記載に基づき、利用条件メタデータは `PERMISSION_REQUIRED` です。

## 海外

### 台湾鉄路（TRA）

```python
tracker = Tracker(enabled_providers=("tra",))
await tracker.refresh()
print(tracker.tra.eastern.status)
print(tracker.tra.jiji.alerts)
```

`Tracker()` の既定の取得対象です。`python -m examples.tra` でも実行できます。直接使用する場合は `from train_operation_info.providers.tra import TraProvider` です。路線属性は `western`、`western_coast`、`eastern`、`south_link`、`chengzhui`、`pingxi`、`shenao`、`liujia`、`neiwan`、`jiji`、`shalun`、`suaoxin_suao` です。

[公式の路線運行狀態](https://www.railway.gov.tw/tra-tip-web/tip/tip007/tip711/blockList)の12掲載単位を取得します。共通IDは `tw:tra:...`、会社は國營臺灣鐵路股份有限公司です。西部・東部幹線と南迴線の掲載範囲は個別の物理路線と区別して `GROUP` にします。保存応答では南迴線欄に屏東～潮州も掲載されています。海線と各支線・蘇澳新～蘇澳は別の掲載単位として保持します。

行ごとの公式凡例で「列車延誤」は `DELAYED`、災害等級・台風案内は `ALERT`、未知の表示は `UNKNOWN` とします。「部份受阻」は復旧行も含む一覧サマリーのため、それだけから一部運休と判定しません。「恢復正常」の行は情報アラートとして残し、他に障害行がなければ `NORMAL` にします。長期工事・将来の運転案内も原文のまま保持し、本文から運休や適用時期を推測しません。`timing=UNKNOWN`、`active_from=None`、`active_until=None` です。

`updated_at` はページに明示された更新時刻（`Asia/Taipei`）で、事故の発生・更新時刻を保証しません。各行の日付と復旧見込みはアラート本文に残します。ニュース・地図・列車別のリアルタイム遅延・リンク先資料は取得対象外です。`NORMAL` はこの一覧の取得範囲内の表示です。未知の路線や構造欠損・通信失敗時は前回結果を保持します。

実際の遅延・地震・台風・長期工事・復旧案内と、その後の平常一覧を保存HTMLで検証しています。同一障害を追跡した復旧ペアは未確認です。出典・ハッシュ・合成テストの範囲は [TRA.md](../tests/fixtures/TRA.md) を参照してください。利用条件メタデータは、出典表示等を条件とする公式のサイト資料開放宣告に基づき `COMMERCIAL_ALLOWED` としています。

### 台湾高鉄（THSR）

台湾高鉄だけを取得する例です。`python -m examples.thsr` でも確認できます。

```python
tracker = Tracker(enabled_providers=("thsr",))
await tracker.refresh()
print(tracker.thsr.main.status)
print(tracker.thsr.main.alerts)
print(tracker.thsr.main.updated_at)
```

台湾高鉄の[列車運行状況](https://www.thsrc.com.tw/ArticleContent/3ec1c04f-d3de-45b1-becc-cba412d55123)にある現在のカードを取得します。共通路線IDは `tw:thsr:main`、運行会社は台灣高速鐵路股份有限公司です。`全線正常營運` は `NORMAL`、`部份列車延誤` は `DELAYED`、`營運班表調整` は `ALERT` に対応します。ダイヤ変更だけから全線の遅延・運休を推測しません。折りたたまれた更新履歴は現在の状態に含めません。

障害の原因・影響区間・本文・詳細リンクをアラートに保持し、更新日時は `Asia/Taipei` を付けます。正常表示に有効な更新日時がない場合は `updated_at=None` です。未知の表示は原文を持つ `UNKNOWN`、必須項目の欠損は `ParseError` とし、取得・解析失敗時は直前の結果を保持します。駅別・方向別の状態、独立した全線運休・一部運休ラベル、障害の有効期間は未確認です。遅延・ダイヤ変更・正常は公式の保存HTMLで検証し、復旧への更新と未知表示・欠損は合成テストで検証しています。出典は [tests/fixtures/SOURCES.md](../tests/fixtures/SOURCES.md) に記録しています。利用条件のメタデータは `PERMISSION_REQUIRED` です。

### 台北MRT

台北MRTだけを取得する例です。`python -m examples.taipei_metro` でも確認できます。

```python
tracker = Tracker(enabled_providers=("taipei_metro",))
await tracker.refresh()
print(tracker.taipei_metro.bannan.status)
print(tracker.taipei_metro.bannan.alerts)
print(tracker.taipei_metro.circular.operator.name)
```

属性は `wenhu`（文湖線）、`tamsui_xinyi`（淡水信義線）、`songshan_xindian`（松山新店線）、`zhonghe_xinlu`（中和新蘆線）、`bannan`（板南線）、`circular`（環状線）です。シンガポールの `tracker.singapore_mrt` とは別の取得元です。
[公式の路線運行情報](https://tpweb.metro.taipei/2026/)の灯号と運行メッセージを取得します。凡例の黄灯は `DELAYED`、赤灯「路線局部受阻」は `PARTIAL_SUSPENSION` です。全線運休と推測しません。緑灯および営業時間外の灰灯「非營運時間」は障害情報なしの `NORMAL` とし、元表示を `source_status` に残します。`NORMAL` は列車が走行中であることを意味しません。新北投・小碧潭支線の個別状態は取得しません。
未知の灯号は `UNKNOWN`、路線・必須項目の欠落は `ParseError` で、取得失敗時は直前のスナップショットを保持します。路線を特定できない独立したメッセージは原文と `affected_line_ids=()` を保持し、路線状態を `UNKNOWN` とします。掲載されたデータ更新日時は `Asia/Taipei` で保持し、障害発生時刻とは区別します。平常時はライブHTML・保存HTMLで確認済みです。遅延・一部支障・営業時間外・復旧のテストは公式凡例に基づく合成データで、異常発生中の実ページは未確認です。

### シンガポールMRT/LRT

シンガポールMRT/LRTの取得元ID・Tracker属性は `singapore_mrt` です。`enabled_providers=("singapore_mrt",)` で選択できます。Providerを直接使う場合は `from train_operation_info.providers.singapore_mrt import SingaporeMrtProvider` で読み込みます。共通路線IDの `sg:mrt:...` は国コード `sg` を含む識別子です。
公式JavaScriptで確認した `HH:MM-LINE-Major/Minor/Planned` のヘッダーから対象路線と案内の存在を取得し、状態は `ALERT` とします。本文の `no train service` 等から運休・遅延を区別せず、本文中の路線名から影響対象を推測しません。未確認の鉄道形式は対象未特定の `UNKNOWN` として原文を保持します。異常時POST応答のアーカイブは未確認です。

### 欧州（DB・SNCF Transilien・ÖBB）

欧州の3取得元だけを使う例です。SBBは公式リアルタイムAPIのトークンが必要なため、現在は未対応です。

```python
tracker = Tracker(enabled_providers=("db", "transilien", "obb"))
await tracker.refresh()
print(tracker.db.alerts)
print(tracker.transilien.rer_d.alerts)
print(tracker.transilien.metro_6.status)
print(tracker.transilien.metro_7bis.alerts)
print(tracker.obb.alerts)
```

DB・ÖBBの全国案内は、個別の影響路線を特定できません。案内があるときの掲載単位の状態は `UNKNOWN`、アラートの `affected_line_ids=()` とし、本文を保持します。障害種別や現在有効かどうかを本文から推測しません。空一覧の `NORMAL` は上記の取得範囲に案内がないことだけを示します。Transilienは公式APIの系統別リストと専用状態コードに基づいて対応します。3取得元とも `timing=UNKNOWN` です。調査根拠・実応答・合成テストの区別は [DB](../tests/fixtures/DB.md)、[Transilien](../tests/fixtures/TRANSILIEN.md)、[ÖBB](../tests/fixtures/OBB.md) に記録しています。利用条件は各Providerの `metadata` を参照してください。

TransilienはSNCFのRER C/D/E・列車H/J/K/L/N/P/R/U/Vの12系統に加え、RATPのメトロ16路線を取得します。メトロの属性は `metro_1`〜`metro_14`、`metro_3bis`、`metro_7bis`、共通IDは `fr:ratp:metro_1` などです。メトロは `scope=LINE`、運行会社は `RATP` で、既存のSNCF系統は従来のID・属性と `scope=GROUP` を維持します。Providerは取得元を表すため、メトロも `tracker.transilien` に属します。RATPサイトへの直接取得は行いません。`python -m examples.transilien` で確認できます。

取得先は共通一覧 `/api/traffic/infos` と路線別 `/api/traffic/line/{code}?lang=fr` です。メトロのコードは `METRO_1`〜`METRO_14`、`METRO_3BIS`、`METRO_7BIS`。全28路線・系統の `fetchStatus=FULL` を要求し、一覧1件と詳細28件の計29リクエストが成功した後にまとめて更新します。メトロを含む1路線でも取得・解析に失敗した場合、SNCF系統も含め直前のスナップショットを保持します。

取得範囲は `currentDisruptions` のうち `category=TRAVAUX` を除く案内です。工事分類と別リストの将来予告は対象外で、RER A/B・トラム・バス・Orlyval・CDGVAL・ケーブルカーも取得しません。専用コード `SLOWED_TRAFFIC` / `HIGHLY_SLOWED_TRAFFIC` は `DELAYED`、既知のその他の障害コードは影響範囲を確定せず `ALERT`、未知のコード・分類は原文を保持して `UNKNOWN` です。`timing=UNKNOWN`、適用期間は `None`、`updated_at` は対象案内の `modifiedDate` の最大値です。`NORMAL` はこの取得範囲内に案内がないことを表します。利用条件は従来どおり `PERMISSION_REQUIRED` です。

### MTA New York City Subway（GTFS-realtime）

```python
tracker = Tracker(enabled_providers=("mta_subway",))
await tracker.refresh()
print(tracker.mta_subway.route_f.status)
print(tracker.mta_subway.route_6x.alerts)
```

MTAのデータフィード規約はMTAのサーバーから直接他者へデータを提供するアプリを禁止しているため、`Tracker()` の既定の取得対象には含めません。`enabled_providers` に `"mta_subway"` を明示した場合だけ通信します。利用条件は `tracker.mta_subway.metadata`（`PERMISSION_REQUIRED`）と [MTA_SUBWAY.md](../tests/fixtures/MTA_SUBWAY.md) を参照してください。

GTFS-realtimeの解析は共通モジュール `providers/gtfs_rt.py` が行い、外部のprotobuf依存は追加していません。Providerはフィード固有のURL・規約・`route_id` 対応表・取得範囲だけを持ちます。
公開属性は静的GTFSの29路線（運転系統）に対応する `route_a`、`route_6x`、`route_gs`（42 St Shuttle）、`route_si`（Staten Island Railway）などです。

- 公式仕様で計画工事とされる `lmm:planned_work` のエンティティは取得範囲外です。`NORMAL` は未計画のアラートがないことだけを示します。
- MTAは `effect` を使用しないため、アラートのある路線は `UNKNOWN` です。自由記述扱いの `alert_type` から遅延・運休を判定しません。
- GTFS-rtの共通規則では、`NO_SERVICE` が路線全体（停留所・列車・方向の指定なし）を対象とするときだけ `SUSPENDED`、`SIGNIFICANT_DELAYS` なら `DELAYED`、その他の明示的な影響は `ALERT` です。
- `active_period` は表示期間のため `active_from`/`active_until` に使わず、`timing` は `UNKNOWN` です。
- 未登録の `route_id`、仕様外のエンティティID、破損したprotobufは `ParseError` として前回値を保持します。

### Metro-North Railroad（GTFS-realtime）

```python
tracker = Tracker(enabled_providers=("metro_north",))
await tracker.refresh()
print(tracker.metro_north.hudson.status)
print(tracker.metro_north.harlem.alerts)
print(tracker.metro_north.port_jervis.alerts)
```

取得元IDは `metro_north`、クラスは `MetroNorthProvider` です。公式Service Alertsフィードを使い、列車位置・発着予測は取得しません。MTA Subwayと同じ利用条件により既定無効で、明示指定時だけ通信します。利用条件は `metadata`（`PERMISSION_REQUIRED`）を参照してください。サンプルは `python -m examples.metro_north` です。

公開属性は `hudson`、`harlem`、`new_haven`、`new_canaan`、`danbury`、`waterbury`、`pascack_valley`、`port_jervis`、`wassaic` の9掲載単位です。共通IDは `us:metro_north:<属性名>`。静的GTFSの6路線に加え、公式画面の路線一覧で西岸2路線（50/51）、公開スクリプトでWassaic別掲載を確認しています。WassaicをHarlem全体へ統合せず、支線の案内を親路線へ伝播しません。西岸2路線のサービス事業者はMetro-North、運転実務はNJ Transitです。

- `lmm:planned_work` の計画工事は除外。`NORMAL` は未計画アラートがないことだけを表します。
- 取得した列車別遅延案内には `effect` がないため、本文を保持して路線状態・影響・適用時期は `UNKNOWN` とします。自由記述の `alert_type` や本文の遅延分数から状態を推測しません。
- 明示的なeffectがある場合は既存GTFS-rt規則を使います。路線全体のNO_SERVICE→SUSPENDED、SIGNIFICANT_DELAYS→DELAYED。列車・停留所等に限定される場合はALERTです。
- `active_period` は表示期間のため `active_from` / `active_until` に使用しません。未知の路線・事業者、仕様外ID、破損応答では `ParseError` として前回値を保持します。

実際の列車別案内・計画工事を保存しています。復旧・各路線の未計画案内・明示effect・異常応答は合成テストです。取得元・路線対応・ハッシュ・未確認範囲は [METRO_NORTH.md](../tests/fixtures/METRO_NORTH.md) と [metro_north_manifest.json](../tests/fixtures/metro_north_manifest.json) に記録しています。

## 集約サイト（明示指定時のみ）

### 京都市営地下鉄

```python
tracker = Tracker(enabled_providers=("kyoto_subway",))
await tracker.refresh()
print(tracker.kyoto_subway.karasuma.status)
print(tracker.kyoto_subway.tozai.status)
print(tracker.kyoto_subway.alerts)
```

取得元IDは `kyoto_subway`、クラスは `KyotoSubwayProvider` です。
`Tracker()` の既定の取得対象に含まれ、`python -m examples.kyoto_subway` で単独取得できます。
烏丸線・東西線はYahooと同じ共通路線ID・運行会社を使用し、取得状態は独立しています。

[京都市交通局トップ](https://www.city.kyoto.lg.jp/kotsu/)の緊急情報欄だけを取得します。
[公式説明](https://www.city.kyoto.lg.jp/kotsu/category/166-0-0-0-0-0-0-0-0-0.html)では、
地下鉄ダイヤの乱れ等をこの欄に掲載するとしています。欄のマーカー間が空、または確認済みの
明示的な掲載なし表示なら `NORMAL`。これはこの欄に掲載がないという意味で、全運行の平常を保証しません。

緊急情報には市バス・災害等も混在し、路線別の状態・影響を示す専用項目がないため、
掲載ありは両路線とも `UNKNOWN`、アラートの `affected_line_ids=()` とします。
本文の路線名・運休表現から対象や運休種別を推測しません。案内は本文とリンク先URLを保持し、
Provider/Trackerの `alerts` では一件に集約します。`delay_lines` / `affected_lines` ではなく
`alerts` / `unknown_lines` で参照してください。

`updated_at=None`、`timing=UNKNOWN`、`active_from=None`、`active_until=None` です。
年のない日付見出しから更新時刻を作りません。通常のお知らせ欄・長期案内・臨時便等は構造で除外し、
リンク先本文、時刻表、市バス接近情報、遅延証明書は取得しません。生HTTP記録には対象外の欄も含まれます。
必須構造の欠損・重複・順序異常や通信失敗時は前回の完全なスナップショットを保持します。

ライブの空欄、2023年8月の実際の緊急情報と翌日の掲載終了表示を保存HTMLで検証します。
個別路線の遅延・運休分類は未確認で、本文の否定・予告・復旧、未知の表示、構造破損は合成テストです。
出典・ハッシュ・検証範囲は [KYOTO_SUBWAY.md](../tests/fixtures/KYOTO_SUBWAY.md) を参照してください。
利用条件メタデータは市の著作権方針に基づく `PERMISSION_REQUIRED` です。

### Yahoo!鉄道情報

Yahooは `Tracker()` の既定の取得対象に含めません。利用条件の記録は取得前にも `tracker.yahoo.metadata` で確認でき、`enabled_providers` に `"yahoo"` を明示した場合だけTrackerから通信します。`examples.all_providers` も既定の取得元を使うためYahooには通信しません。

[リンク、二次利用について](https://support.yahoo-net.jp/PccTransit/s/article/H000007493) に二次利用を原則不可とする記載があるため、メタデータの許諾区分は `PERMISSION_REQUIRED` としています。[共通利用規約](https://www.lycorp.co.jp/ja/company/terms/) と併せて記録しており、私的利用なら一律に許諾済みという分類にはしていません。利用者が取得元を選択できます。

```python
from train_operation_info.providers.yahoo import YahooArea, YahooProvider, YahooRouteId
from train_operation_info import Tracker

yahoo = YahooProvider(areas=(YahooArea.KINKI,))
print(yahoo.metadata.usage_permission)
print(yahoo.metadata.terms_url)
print(yahoo.metadata.additional_terms_urls)

tracker = Tracker(enabled_providers=("yahoo",), overrides=(yahoo,))
await tracker.refresh()
print(tracker.yahoo.midosuji.status)
print(tracker.yahoo.get_source_line(YahooRouteId("288/0")))
print(tracker.delay_lines)
```

`python -m examples.yahoo` で近畿の例を実行できます。`YahooProvider()` は全国8地域、`areas` 指定時はその地域だけを取得します。地域は `HOKKAIDO`、`TOHOKU`、`KANTO`、`CHUBU`、`KINKI`、`KYUSHU`、`CHUGOKU`、`SHIKOKU` です。各地域の全路線一覧を検証し、異常・復旧の記載がある項目の詳細を取得します。同時接続数は既定4、`max_concurrency` で1～16を指定できます。

御堂筋線等の既存路線は公式Providerと同じ `LineId` です。`get_source_line()` はYahooの `/diainfo/288/0` のような2つの番号を両方含めたIDを受け取り、対応する共通路線のスナップショットを返します。`331/421` と `331/422` は異なる取得元区間ですが、どちらも共通の山陰本線に集約します。登録済みIDは `source_line_ids`、取得対象の路線は `lines` で参照できます。存在しないIDは `None`、選択地域外で未取得の路線は `UNKNOWN` です。

`Line.source_line_names` に実際に取得した区間名を保持します。地域選択により同一路線の一部区間が未取得の場合、路線全体を平常とはせず `UNKNOWN` を残します。京阪本線・中之島線の合算項目、近鉄山田線・鳥羽線・志摩線の合算項目は `GROUP` とし、個別路線と区別します。阪急の各本線も、公式Providerの3系統全体とは別IDです。

掲載時刻は日本時間で、年を省略した表記は取得日時から補います。掲載時刻がない通常表示は `updated_at=None` です。本文から運休を推測せず、詳細の現在の状態ラベルを使います。実際の遅延・運転見合わせ・復旧のデータと、未確認・合成ケースの区別は [tests/fixtures/YAHOO.md](../tests/fixtures/YAHOO.md) に記録しています。

#### つくばエクスプレス

つくばエクスプレス線は既存のYahoo Providerで取得できます。関東を選択し、
Yahooの路線ID `412/0` で参照します。取得元はYahoo、運行会社は首都圏新都市鉄道です。
Yahooの利用条件と明示指定の扱いは上記のとおりです。

```python
from train_operation_info import Tracker
from train_operation_info.providers.yahoo import YahooArea, YahooProvider, YahooRouteId

yahoo = YahooProvider(areas=(YahooArea.KANTO,))
tracker = Tracker(enabled_providers=("yahoo",), overrides=(yahoo,))
await tracker.refresh()
line = tracker.yahoo.get_source_line(YahooRouteId("412/0"))
assert line is not None
print(line.name, line.status, line.alerts)
```

2026年11月4日の確認時点で、[TX公式Webの運行情報](https://www.mir.co.jp/info/)は
配信停止・メンテナンス中のため、専用の公式Providerは追加していません。
配信停止の案内を列車の平常状態として扱いません。
[ODPTのTX運行情報](https://ckan.odpt.org/dataset/r_train_status-mir)にはAPIキーが必要で、
[APIキー必須の取得元を追加しない方針](../CONTRIBUTING.md#追加を見送る取得元)により対象外です。


## Trenitalia

```python
tracker = Tracker(enabled_providers=("trenitalia",))
await tracker.refresh()
print(tracker.trenitalia.network.status)
print(tracker.trenitalia.network.alerts)
```

[公式Infomobilità](https://www.trenitalia.com/it/informazioni/Infomobilita/notizie-infomobilita.html)
の全国案内を、共通ID `it:trenitalia:network`、運行会社 `Trenitalia` の
`GROUP` として取得します。個々の路線や列車の状態ではありません。
`python -m examples.trenitalia` でも確認できます。

2024年と2026年の公式保存ページで確認した、全国平常の見出し・分類・本文全体が
定型形式に一致する場合だけ `NORMAL` とします。それ以外は `UNKNOWN` です。
高速網だけの平常告知を全国平常へ拡張しません。他の案内は原文と分類・掲載日を
保持し、影響は `OTHER`、対象路線は空、適用時期は `UNKNOWN` とします。
赤の注意分類には復旧案内もあるため、色・本文中の単語から遅延・運休を推測しません。
全国平常が明示されていても、併記された案内は消しません。

`Programmazione` の予定分類は構造的に除外し、その本文は検証しません。
他の分類に混在する工事情報は保持します。生HTTP記録には除外した案内も含まれます。
掲載日は更新時刻や適用期間ではないため、`updated_at` と適用期間は `None` です。
列車検索、リンク先の詳細・PDFは対象外です。ViaggiaTrenoは識別User-Agentに403を
返したため取得しません。実際の平常・異常応答と合成テストの区別は
[TRENITALIA.md](../tests/fixtures/TRENITALIA.md) に記録しています。

[公式利用条件](https://www.trenitalia.com/it/informazioni/termini-e-condizioni-di-utilizzo-sito-trenitalia.html)
は個人の非商用保存と再配布等を区別し、後者には事前同意を求めています。
メタデータは `PERMISSION_REQUIRED`、取得は明示指定時のみです。

## 名古屋市営地下鉄

```python
tracker = Tracker(enabled_providers=("nagoya_subway",))
await tracker.refresh()
print(tracker.nagoya_subway.higashiyama.status)
print(tracker.nagoya_subway.meijo_meiko.alerts)
```

`Tracker()` の既定の取得対象に含まれます。`python -m examples.nagoya_subway` でも確認できます。
属性は `higashiyama`、`meijo_meiko`、`tsurumai`、`sakuradori`、`kamiiida` です。
[公式運行情報](https://www.kotsu.city.nagoya.jp/rp/emergency/)のJSONを取得します。
6路線を5系統で掲載し、名城線・名港線は一つの `M_LINE` です。
Yahooの既存共通IDを再利用し、個別路線へ分割しません。

公開JavaScriptの専用コードを根拠に、`N_T_ICO` と完全一致の `平常運行` は `NORMAL`、
`W_T_ICO` は `DELAYED`、`E_T_ICO` は `SUSPENDED`、`C_T_ICO` は `ALERT` とします。
`N_T_ICO` でもタイトルが異なれば `ALERT`、未知コードは `UNKNOWN` です。
全スロットの非平常案内を保持し、平常項目で別の障害を消しません。
タイトル・本文・区間・理由を保持し、自由記述から状態を推定しません。

市バスは対象外ですが、HTTP生応答記録には含まれます。長期案内を分離する専用項目は
確認できず、本文で除外しません。公式の情報提供は10分以上の遅延が見込まれる場合等で、
`NORMAL` はその範囲内です。適用時期は `UNKNOWN`、適用期間はNoneです。
`create_datetime` の路線更新時刻としての意味が未確認なので `updated_at=None` とします。

ライブ取得は平常JSONのみで、異常時・複数案内・復旧のテストは合成です。
出典・ハッシュ・未確認範囲は [NAGOYA_SUBWAY.md](../tests/fixtures/NAGOYA_SUBWAY.md) を参照。
無断転載・複製を禁止する公式規約に基づき、メタデータは `PERMISSION_REQUIRED` です。


## Metro Trains Melbourne

```python
tracker = Tracker(enabled_providers=("metro_trains_melbourne",))
await tracker.refresh()
print(tracker.metro_trains_melbourne.sunbury.status)
print(tracker.metro_trains_melbourne.werribee.alerts)
```

`Tracker()`の既定の取得対象です。直接使う場合は
`from train_operation_info.providers.metro_trains_melbourne import MetroTrainsMelbourneProvider`。
サンプルは `python -m examples.metro_trains_melbourne` です。
[公式ホームページ](https://www.metrotrains.com.au/)のHealthboard APIとネットワーク定義を取得します。
属性は `alamein`、`belgrave`、`craigieburn`、`cranbourne`、`mernda`、`frankston`、
`glen_waverley`、`hurstbridge`、`lilydale`、`pakenham`、`sandringham`、`stony_point`、
`sunbury`、`upfield`、`werribee`、`williamstown`、`racecourse` の17路線です。
共通IDは `au:metro_trains_melbourne:<属性名>`、会社はMetro Trains Melbourneです。

固定の平常文字列／空通知配列と `good` / `good-service` は `NORMAL`、
`minor` / `major` は `DELAYED`、`suspended` は `PARTIAL_SUSPENSION`。
公式凡例のSuspendedは区間の見合わせを意味するため、全線の `SUSPENDED` は導出しません。
工事・旅行案内・列車単位の運休／変更は `ALERT`、未知コード・文字列は `UNKNOWN`です。
No Servicesは運転予定がない表示で、障害扱いにせず `NORMAL` として原文を保持します。
複数通知を保持し、平常通知で別の障害を消しません。

対象は路線の `alerts` と構造化された `disruptions` のみです。別枠の計画工事一覧・
増発案内・昇降設備・全体バナーは対象外ですが、路線状態欄のworks通知は保持します。
対象路線は公式ID・disruptionsのlinesから決定し、本文の別路線名・駅名から広げません。
通知のUnix秒を `active_from` / `active_until` に保存し、適用時期は `UNKNOWN`、
更新時刻は意味が未確認なので `updated_at=None`。工事予告を本文からACTIVEにしません。
ネットワークは調査時の既定設定 `Aug26` を使い、路線ID・件数・名称の変更を検知します。

ライブ取得で平常文字列・works通知・No Services条件を確認しました。
遅延・見合わせ・非空disruptions・復旧は公開JavaScript／凡例に基づく合成テストです。
出典と未確認範囲は [METRO_TRAINS_MELBOURNE.md](../tests/fixtures/METRO_TRAINS_MELBOURNE.md)。
一般利用規約・再利用許諾は発見できず、メタデータは `UNSPECIFIED` / `terms_url=None` です。

## 土佐くろしお鉄道

```python
tracker = Tracker(enabled_providers=("tosakuro",))
await tracker.refresh()
print(tracker.tosakuro.gomen_nahari.status)
print(tracker.tosakuro.nakamura_sukumo.alerts)
```

`Tracker()` の既定の取得対象です。直接使う場合は
`from train_operation_info.providers.tosakuro import TosaKuroshioProvider`。
サンプルは `python -m examples.tosakuro` です。
[公式トップページ](https://www.tosakuro.com/)の路線別運行情報欄から、
ごめん・なはり線と中村・宿毛線の2記事を取得します。
Yahooの同じ掲載単位の共通路線ID・会社情報を再利用し、取得結果は独立です。

完全一致する平常見出し「平常運行」「平常運転」だけを `NORMAL`、
未確認の見出しは `UNKNOWN` にします。遅延・見合わせ・一部運休は分類しません。
`NORMAL` は公式記事の見出しの状態です。個別列車の運休案内が本文に併記される
場合もあるため、平常時も全記事本文を `effect=OTHER` の情報アラートに保持します。
そのため `NORMAL` でも `alerts` は空になりません。
対象路線の掲載枠は影響区間の確定情報ではなく、`affected_line_ids=()` です。
本文の日時・原因・運休表現から状態や適用時期を推定しません。
`timing=UNKNOWN`、適用期間・`updated_at=None` を維持します。

トップページの別のお知らせ／トピックス欄、時刻表、列車位置、SNS、
記事中のリンク先PDF／画像の解析は対象外です。運行記事内に混在する長期・将来・
復旧案内はそのまま保持します。本文のリンク・画像URLも残します。
生HTTP記録には対象外のお知らせ欄が含まれます。

平常表示はライブHTMLと2026年の保存HTMLで検証しました。
異常時の安定した状態対応・同一事象の復旧データは未確認で、異常・破損・復旧は合成テストです。
出典・取得日時・ハッシュ・未確認範囲は [TOSAKURO.md](../tests/fixtures/TOSAKURO.md) を参照。
確認した公式トップページ・企業情報から適用可能な再利用規約は見つからず、
メタデータは `UNSPECIFIED` / `terms_url=None` です。

## SNCF TGV (`tgv`)

```python
tracker = Tracker(enabled_providers=("tgv",), rate_limit=120)
await tracker.refresh()
print(tracker.tgv.network.status)
print(tracker.tgv.network.alerts)
```

[SNCFの公式Open Data](https://transport.data.gouv.fr/datasets/horaires-sncf)
のNeTEx時刻表とSIRI SX Service Alertsを照合します。共通IDは
`fr:sncf:tgv`、運行会社はSNCF Voyageurs、範囲は`GROUP`です。
Transilienの近郊系統とは別の範囲です。`python -m examples.tgv`でも取得できます。

NeTExの列車ブランド`OUI`・`TGVOUIGO`・`LYR`と`highSpeedRail`を用い、
INOUI・OUIGO高速列車・Lyriaの案内を取り込みます。列車番号と運行主体で
照合し、路線名・番号の桁数・本文の単語から列車種別を推測しません。
TER・Intercités・OUIGO Train Classique・DBブランドと確定できた案内は
対象外です。未登録列車、未知ブランド、対象駅だけの案内、曖昧な照合は
未特定の案内として保持します。

列車別の案内では系統全体の遅延・運休は断定できないため、案内ありは
`UNKNOWN`、対象内および未特定の案内がなければ`NORMAL`です。
`NORMAL`はこのフィードの公表範囲内での案内なしを意味し、全列車の定時運転を
保証しません。本文・詳細HTML・列車番号・Progress・Severityを保持し、
`effect=OTHER`、`timing=UNKNOWN`、`affected_line_ids=()`とします。
Severityから運休・遅延を推測しません。ValidityPeriodは掲載期間として扱い、
影響の開始・終了へ転用しません。`updated_at`はフィードのResponseTimestampです。
工事・長期案内は同じ欄に混在するため、本文や日付で除外しません。

毎回、全国NeTEx ZIPとSIRI SXを取得します。調査時のZIPは約32 MB、展開後XMLは
約654 MBです。XMLは逐次解析し、解析はワーカースレッドで行います。
取得負荷が大きいため既定では無効です。明示指定し、長めの更新間隔を設定してください。
保存・再生に必要な両応答を毎回記録します。通信・構造の破損時は直前の状態を保持します。

公式データセットのライセンスはODbL 1.0です。メタデータは
`COMMERCIAL_ALLOWED`とし、帰属表示・ライセンス表示・該当する継承条件を記録しています。
旅客向けページは識別User-Agentに403を返したため実行時には使用しません。
Open Dataの独立した公開先を利用し、拒否の回避は行いません。
調査根拠・未確認範囲は[fixture出典](../tests/fixtures/TGV.md)を参照してください。
