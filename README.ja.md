# train_operation_info

[English](README.md) | **日本語**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/dk-butsuri/train_operation_info/blob/main/LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Typed](https://img.shields.io/badge/typing-mypy%20strict-informational.svg)

世界各地の鉄道運行情報（Service Alerts）を、取得元ごとのProviderで取得する型付きPythonライブラリです。主な利用先として私用サイネージを想定しています。

> **非公式ライブラリです。** 各鉄道事業者・情報提供元とは関係がなく、承認も受けていません。運行情報の権利は各取得元に帰属します。利用前に [免責事項](#免責事項) と [責任ある利用](#責任ある利用) を確認してください。

- 国内外41の取得元に対応し、国・地域を限定せずProviderを追加できます。
- 共通モデルはPydanticのstrict・frozenなモデルで、公開APIはmypy strictで検証しています。`py.typed` を同梱しています。
- アドホックで不確実な推論をしません。取得元の仕様・公開コード・保存応答で裏付けた対応だけを採用し、未確認の値は `UNKNOWN` として原文ごと保持します。詳細は [判定方針](https://github.com/dk-butsuri/train_operation_info/blob/main/CONTRIBUTING.md#全provider共通の判定方針) を参照してください。
- 取得元ごとのレート制限、HTTP応答の保存とオフライン再生、ローカルの監視画面を備えています。

## 免責事項

本ライブラリは非公式のもので、各鉄道事業者・情報提供元とは関係ありません。

- 取得する運行情報の権利は各取得元に帰属します。多くの取得元は、運行情報の無断転載・再利用を制限しています。利用前に各Providerの `metadata`（後述の「Providerのメタデータ」）に記録した利用規約と許諾区分、および取得元の最新の規約を確認してください。
- 取得結果の正確性・即時性は保証しません。安全や業務に関わる判断には、必ず各事業者の公式情報を確認してください。
- 取得元のページ構成やAPIが変わると、取得・解析できなくなる場合があります。
- 取得元サーバーの負荷を考慮し、レート制限を無効にしたり、短い間隔で取得したりしないでください。

## 責任ある利用

このライブラリは、取得元に負担や不利益をかけないことを機能より優先します。

- **名乗って取得します。** すべての通信は `train_operation_info (+https://github.com/dk-butsuri/train_operation_info)` というUser-Agentで送信し、ブラウザを装いません。呼び出し側の `httpx.AsyncClient` に独自のUser-Agentを設定した場合はそれを使います。
- **制限を回避しません。** 取得元に拒否された場合は `FetchError` として扱います。ブラウザの偽装、CAPTCHA・ログイン・アクセス制限の回避、取得元を分散させての再試行は実装しません。
- **間隔を守ります。** 取得元ごとに30秒（最短10秒）のレート制限があり、無効にはできません。
- **データを配布しません。** 取得元のページ・応答の保存データはリポジトリにもパッケージにも含めません。ドキュメントやデモの画面には、実際の案内本文ではなく合成データを使います。
- **規約を記録します。** 各Providerの `metadata` に利用規約と許諾区分を記録しています。区分は適法性の判定ではありません。公開の場（店舗・施設のサイネージ、Webサイト、SNS等）に表示・転載する場合は、取得元の規約を確認し、必要な許諾を得てください。

## 取得元の方へ

本ライブラリによる取得の停止や変更をご希望の場合は、[停止・変更の依頼](https://github.com/dk-butsuri/train_operation_info/issues/new?template=removal_request.yml) からご連絡ください。原則として7日以内に該当Providerを既定の取得対象から外し、次のリリースで削除または修正します。

## インストール

Python 3.10以上が必要です。

```bash
pip install train_operation_info
```

GitHubの最新版をインストールする場合は次のとおりです。

```bash
pip install git+https://github.com/dk-butsuri/train_operation_info.git
```

## クイックスタート

```python
import asyncio
from train_operation_info import Tracker

async def main() -> None:
    tracker = Tracker()
    await tracker.refresh()

    line = tracker.osaka_metro.midosuji
    print(line.name, line.operator.name, line.status)
    print(line.alerts)
    print(tracker.delay_lines)

asyncio.run(main())
```

`Tracker()` は既定の取得元（Yahoo!鉄道情報・MTA・小田急電鉄・DBを除く全取得元）を更新します。対象を絞る場合は `Tracker(enabled_providers=("jrw", "keihan", "nankai"))` のように指定します。属性の型は選択にかかわらず明示され、未更新のProviderは `UNKNOWN` のままです。集約一覧は選択したProviderのみを対象にします。

公開APIは `train_operation_info` パッケージから読み込みます。共通モデルは `train_operation_info.models`、例外は `train_operation_info.exceptions`、各Providerは `train_operation_info.providers` にあります。
以降のコード例は `async` 関数の中で実行する前提で、`import` を一部省略しています。

## 対応Provider

`Tracker()` はYahoo!鉄道情報・MTA・小田急電鉄・DBを除く全取得元を更新します。この4つは利用条件を確認したうえで、`enabled_providers` に明示した場合だけ通信します。
各Providerの属性一覧・状態の対応付け・対象外の情報・検証範囲は [docs/PROVIDERS.md](https://github.com/dk-butsuri/train_operation_info/blob/main/docs/PROVIDERS.md) にまとめています。

### 日本

| Provider | 路線アクセス例 | 取得範囲 |
| --- | --- | --- |
| JR北海道 | `tracker.jrhokkaido.soya`、`tracker.jrhokkaido.hakodate_line` | 公式JSONの14掲載単位。単一路線に対応する8線区と、複数区間をまとめた新規6グループ。特急列車・北海道新幹線は対象外 |
| JR東日本 | `tracker.jreast.yamanote`、`tracker.jreast.tohoku_shinkansen` | 関東・東北・信越・新幹線の86路線・系統。BRT・東京モノレールを含む公式の路線別一覧 |
| JR東海 | `tracker.jrcentral.tokaido_atami_toyohashi`、`tracker.jrcentral.chuo` | 公式JSONの在来線13路線・区間。専用状態コードと案内本文。新幹線・特急等・別枠のお知らせは対象外 |
| JR西日本 | `tracker.jrw.osaka_loop`、`tracker.jrw.ako` | 北陸・近畿・中国・新幹線の61路線。地区別74項目を共通路線に統合 |
| JR四国 | `tracker.jrshikoku.seto_ohashi`、`tracker.jrshikoku.yodo` | 公式掲載の10路線・区間。運行案内の本文・対象区間・更新日時 |
| JR九州 | `tracker.jrkyushu.fukuoka_kitakyushu`〜`tracker.jrkyushu.nishi_kyushu_shinkansen` | 公式XMLの8掲載単位。在来線6エリアと新幹線2路線。案内本文・XML案内の更新日時。分離された長期見合わせフラグは対象外 |
| 東武鉄道 | `tracker.tobu.skytree`、`tracker.tobu.tojo` | 特急・ライナー・支線を含む公式の12掲載単位。運行案内の原文 |
| 西武鉄道 | `tracker.seibu.shinjuku`、`tracker.seibu.ikebukuro_chichibu` | 公式XMLの11掲載単位（池袋線・西武秩父線は既存の共通IDに統合）。路線別の運転見合わせ・案内 |
| 京成電鉄 | `tracker.keisei.main`、`tracker.keisei.matsudo` | 本線・スカイアクセス・押上・金町・千葉線／千原線・松戸の6掲載単位。原因・区間・詳細本文・期間限定告知 |
| 京王電鉄 | `tracker.keio.main`、`tracker.keio.inokashira` | 京王線・新線・相模原線・高尾線・競馬場線・動物園線・井の頭線の7路線。公式XMLの全線一括の運行情報 |
| 小田急電鉄（明示指定時のみ） | `tracker.odakyu.odawara`、`tracker.odakyu.enoshima`、`tracker.odakyu.tama` | 小田原線・江ノ島線・多摩線。公式の区間別運行状態・案内本文・更新日時 |
| 東急電鉄 | `tracker.tokyu.toyoko`、`tracker.tokyu.den_en_toshi` | 東急9路線。公式JSONの路線別状態・案内文・対象未特定のお知らせ |
| 京浜急行電鉄（京急） | `tracker.keikyu.main`、`tracker.keikyu.airport` | 本線・空港線・大師線・久里浜線・逗子線の5路線。公式の全線一括の案内本文・更新日時 |
| みなとみらい線 | `tracker.minatomirai.main` | 横浜～元町・中華街の1路線。公式の運行案内・発生時刻・原因・遅延時間 |
| 箱根登山鉄道 | `tracker.hakone_tozan.main` | 小田原～強羅の1路線。箱根ナビ公式HTMLの路線別状態と案内原文 |
| 東京メトロ | `tracker.tokyo_metro.ginza`、`tracker.tokyo_metro.tozai` | 公式JSONの9路線。路線別の状態・本文・影響区間・原因 |
| 都営地下鉄 | `tracker.toei.asakusa`、`tracker.toei.oedo` | 公式HTMLの地下鉄4路線。状態・案内本文 |
| 札幌市営地下鉄 | `tracker.sapporo_subway.namboku`、`tracker.sapporo_subway.tozai`、`tracker.sapporo_subway.toho` | 公式HTMLの3路線。10分以上の遅れなしの平常表示と未分類の案内原文 |
| ゆりかもめ | `tracker.yurikamome.main` | 新橋～豊洲の1路線。公式運行情報の状態・本文・配信日時 |
| りんかい線 | `tracker.rinkai.main` | 大崎～新木場の1路線。公式運行情報の案内本文・明示された更新日時 |
| 名古屋市営地下鉄 | `tracker.nagoya_subway.higashiyama`、`tracker.nagoya_subway.meijo_meiko` | 公式JSONの5系統（名城線・名港線は合算）。状態コード・全案内の本文・区間・理由。市バスは対象外 |
| 名古屋鉄道（名鉄） | `tracker.meitetsu.nagoya_main`、`tracker.meitetsu.inuyama` | 公式HTMLの路線・区間別の見合わせ、遅延・一部運休、案内本文。既存共通IDの16掲載単位 |
| 近鉄 | `tracker.kintetsu.osaka`、`tracker.kintetsu.nara`、`tracker.kintetsu.kyoto` | 本線・支線・ケーブルの23路線。公式運行情報の状況・原因・詳細リンク |
| 南海電鉄 | `tracker.nankai.main`、`tracker.nankai.koya`、`tracker.nankai.semboku` | 本線・支線・高野山ケーブル・泉北線の10路線・区間 |
| 阪神 | `tracker.hanshin.main`、`tracker.hanshin.namba` | 3路線。公式トップの全体サマリー |
| 京阪 | `tracker.keihan.main`、`tracker.keihan.uji` | 本線・支線・大津線・ケーブルの8路線 |
| 阪急 | `tracker.hankyu.kobe`、`tracker.hankyu.kyoto` | 公式発表の神戸線・宝塚線・京都線の3系統 |
| 大阪モノレール | `tracker.osaka_monorail.main`、`tracker.osaka_monorail.saito` | 2路線。公式トップの全体サマリー |
| 大阪メトロ | `tracker.osaka_metro.midosuji` | 地下鉄8路線・ニュートラム |
| 京都市営地下鉄 | `tracker.kyoto_subway.karasuma`、`tracker.kyoto_subway.tozai` | 公式トップの緊急情報欄。掲載なし／対象・影響未特定の案内。Yahooと共通路線IDを使用 |
| とさでん交通 | `tracker.tosaden.main` | 路面電車全体の1掲載単位。公式の運行状況本文・台風等の案内 |
| ゆいレール（沖縄都市モノレール） | `tracker.yuirail.main` | 那覇空港～てだこ浦西の1路線。公式トップの運行情報テキスト |

### 海外

| Provider | 路線アクセス例 | 取得範囲 |
| --- | --- | --- |
| 台湾鉄路（TRA） | `tracker.tra.eastern`、`tracker.tra.pingxi` | 公式の12路線・区間。通阻一覧の状態凡例・対象区間・本文・復旧見込み |
| Taiwan High Speed Rail（台湾高鉄） | `tracker.thsr.main` | 南港～左営の1路線。公式の現在の運行状態・原因・影響区間・本文 |
| 台北MRT（Metro Taipei） | `tracker.taipei_metro.bannan`、`tracker.taipei_metro.tamsui_xinyi` | 公式掲載の6路線。環状線の運行会社は新北捷運 |
| シンガポールMRT/LRT | `tracker.singapore_mrt.east_west`、`tracker.singapore_mrt.downtown` | MRT6路線・LRT3路線。運行会社は各Lineのプロパティ |
| DB Verkehrslage（DB Fernverkehr、明示指定時のみ） | `tracker.db.fernverkehr` | 長距離列車部門の当日運行案内1掲載単位。工事分類を除外。DB Regio・S-Bahn・列車別遅延は対象外 |
| SNCF Transilien | `tracker.transilien.rer_c`、`tracker.transilien.ligne_h` | SNCF運行のRER C/D/E・列車H/J/K/L/N/P/R/U/Vの12系統。現在の案内から工事分類を除外。全国のTGV・TER・Intercités、RER A/Bは対象外 |
| ÖBB公式運行案内 | `tracker.obb.network` | 全国の編集型障害一覧1掲載単位。工事欄を除外。個別路線・列車別遅延は対象外 |
| MTA New York City Subway（明示指定時のみ） | `tracker.mta_subway.route_f`、`tracker.mta_subway.route_6x` | GTFS-realtimeの29路線（運転系統）。計画工事は対象外 |

SBBは公式リアルタイムAPIのトークンが必要なため、現在は未対応です。

### 集約サイト

| Provider | 路線アクセス例 | 取得範囲 |
| --- | --- | --- |
| Yahoo!鉄道情報（明示指定時のみ） | `tracker.yahoo.midosuji`、`tracker.yahoo.yamanote` | 全国8地域の在来線一覧536項目・共通路線532件。地域を選択可能。新幹線の別一覧は対象外 |

## 更新と表示

通信は `await tracker.refresh()` でのみ行います。属性や一覧の参照は通信しません。
`Line` は変更不可のスナップショットです。更新後はProviderから取り直してください。以前の `line` 変数は以前の状態を保持します。

`tracker.nankai` などのProvider属性は読み取り専用です。独自のHTTPクライアントや設定を持つProviderは、構築時に `Tracker(enabled_providers=("nankai",), overrides=(provider,))` のように渡します。どの属性を置き換えるかは `provider.provider_id` で決まります。型が属性と合わないProviderは `TypeError`、未知の取得元や同じ取得元の重複は `ValueError` です。`overrides` に渡しただけでは取得対象にならないため、更新するには `enabled_providers` にも指定してください。構築後の属性への代入は `AttributeError` になり、型チェッカーでも検出されます。

- 取得前は全路線が `LineStatus.UNKNOWN` です。
- `delay_lines` は `DELAYED`、`affected_lines` は遅延・運転見合わせ・一部運休・お知らせの路線、`unknown_lines` は状態不明の路線です。`ALERT` は詳細な影響を断定しないお知らせ、`PARTIAL_SUSPENSION` は一部運休・折返し運転を表します。
- `tracker.alerts` / `provider.alerts` はアラートの一覧です。影響対象を特定できない全体のお知らせは `unknown_lines` と併せて参照してください。
- 平常時の `alerts` は空ですが、空の一覧だけで平常とは判定せず `status` を参照してください。
- 未知の表示は `UNKNOWN` として原文を保持します。
- Provider単体の通信失敗は `FetchError`、HTML変更や型・必須項目の不一致は `ParseError` を送出します。どちらも `ProviderError` の派生です。失敗時は直前のスナップショットを保持します。
- `tracker.refresh()` は選択した取得元を並行更新します。全取得元の処理後に、失敗があれば `RefreshError` を送出します。成功した取得元は更新され、失敗した取得元は以前の状態を保持します。失敗内訳は `exception.errors` と `tracker.refresh_errors` で参照できます。
- サイネージ側では例外を処理し、`fetched_at` と現在時刻から古い情報であることを表示してください。取得失敗を平常扱いにしないでください。
- datetimeはすべてタイムゾーン付きです。`fetched_at` はUTC、取得元の日時は掲載されたオフセット、または明確な現地時刻として日本は `Asia/Tokyo`、シンガポールMRTは `Asia/Singapore`、台北MRTは `Asia/Taipei` を付けます。更新時刻が不明なら `updated_at=None` です。ブラウザの時計を取得元の更新時刻として採用しません。
- JSONはProvider内のPydantic専用モデルで `model_validate_json()` により検証します。共通モデルはstrict・frozenで、naiveな日時は受け付けません。
- 長時間使う場合は、呼び出し側で所有する `httpx.AsyncClient` を `Tracker(client=client)` や各Providerに渡して接続を再利用できます。自動ポーリングは行いません。
- 取得元サーバーの負荷を考慮し、[keihan_tracker](https://github.com/dk-butsuri/keihan_tracker) と同じく取得元ごとに30秒のレート制限を内蔵しています。前回の取得開始から30秒以内の `refresh()` は通信せず、直前のスナップショットをそのまま保持します。失敗した取得も間隔に数えるため、失敗した取得元をすぐに取り直すことはありません。この間は前回の `ProviderError` を再び送出するため、失敗した取得元が成功扱いになることはありません。
- 間隔は `Tracker(rate_limit=60)` のように秒数で変更できます。取得元への配慮から10秒未満（`0` を含む）は `ValueError` です。`Tracker` に渡したProviderには適用されないため、その場合は `provider.rate_limit = 60` で設定してください。

```python
from train_operation_info.exceptions import RefreshError

try:
    await tracker.refresh()
except RefreshError as exc:
    for source, error in exc.errors.items():
        print(source, error)
```

複数Providerを選んだ場合の `tracker.lines`・`delay_lines` 等は、各取得元の結果を連結します。同じ `LineId` の結果でも `provider_id` と状態は独立しており、自動的な優先順位付けやYahooへの切り替えは行いません。

## 状態の分類能力

取得元の専用状態欄から区別できる `LineStatus` はProviderごとに異なります。✓ のない状態はそのProviderからは返りません。たとえば東武鉄道の遅延は `DELAYED` ではなく `ALERT`、京王電鉄の平常以外の表示は `UNKNOWN` になります。`DELAYED` を返さないProviderでは `delay_lines` が常に空になるため、`affected_lines`・`unknown_lines` と `alerts` を参照してください。

`UNKNOWN`（取得前・未知の表示）はすべてのProviderで返り得るため省略しています。同じ内容は実行時に `provider.metadata.statuses` で参照できます。宣言にない状態を解析した場合は `ParseError` とし、直前の結果を保持します。

| `provider_id` | `NORMAL` | `DELAYED` | `SUSPENDED` | `PARTIAL_SUSPENSION` | `ALERT` |
| --- | :-: | :-: | :-: | :-: | :-: |
| `jrhokkaido` | ✓ |  |  |  | ✓ |
| `jreast` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `jrcentral` | ✓ | ✓ | ✓ |  | ✓ |
| `jrw` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `jrshikoku` | ✓ |  |  |  | ✓ |
| `jrkyushu` | ✓ |  |  |  | ✓ |
| `sapporo_subway` | ✓ |  |  |  |  |
| `tokyo_metro` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `toei` | ✓ |  |  |  | ✓ |
| `tobu` | ✓ |  |  |  | ✓ |
| `seibu` | ✓ |  | ✓ |  | ✓ |
| `keisei` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `keio` | ✓ |  |  |  |  |
| `odakyu` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `tokyu` | ✓ |  | ✓ |  | ✓ |
| `keikyu` | ✓ |  |  |  |  |
| `minatomirai` | ✓ | ✓ |  |  | ✓ |
| `hakone_tozan` | ✓ |  |  |  | ✓ |
| `yurikamome` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `rinkai` | ✓ |  |  |  | ✓ |
| `nagoya_subway` | ✓ | ✓ | ✓ |  | ✓ |
| `meitetsu` | ✓ |  | ✓ |  | ✓ |
| `kintetsu` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `nankai` | ✓ | ✓ | ✓ |  | ✓ |
| `hanshin` | ✓ |  |  |  |  |
| `keihan` | ✓ | ✓ | ✓ | ✓ |  |
| `hankyu` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `osaka_monorail` | ✓ |  |  |  |  |
| `osaka_metro` | ✓ | ✓ | ✓ |  |  |
| `kyoto_subway` | ✓ |  |  |  |  |
| `tosaden` | ✓ |  |  |  | ✓ |
| `yuirail` | ✓ |  |  |  | ✓ |
| `tra` | ✓ | ✓ |  |  | ✓ |
| `thsr` | ✓ | ✓ |  |  | ✓ |
| `taipei_metro` | ✓ | ✓ |  | ✓ |  |
| `singapore_mrt` | ✓ |  |  |  | ✓ |
| `db` | ✓ |  |  |  | ✓ |
| `transilien` | ✓ | ✓ |  |  | ✓ |
| `obb` | ✓ |  |  |  | ✓ |
| `mta_subway` | ✓ | ✓ | ✓ |  | ✓ |
| `yahoo` | ✓ | ✓ | ✓ | ✓ | ✓ |

## 案内の取得範囲と適用時期

本文の単語・原因・日付から、一時的／長期、現在有効／将来予告を判別しません。長期案内が取得元で構造的に分離されている場合（JR西日本の地域案内、JR九州の長期見合わせフラグ）はその欄を対象外とし、同じ欄に混在していて構造的に分けられない場合は除外をあきらめて保持します。JR東日本・JR四国・Yahooなどの取得欄に混在する長期案内や工事予告は原文のまま保持します。取得結果に長期案内が含まれないことは保証しません。

JR西日本・JR東日本・Yahooは、専用状態欄から確認した遅延・運転見合わせ・一部運休のアラートだけに `timing=ACTIVE` を設定します。`お知らせ`・`その他` などは本文が現在の障害を述べていても `UNKNOWN` です。JR四国など専用状態から適用時期を確定していないProviderも `UNKNOWN` です。

```python
tracker = Tracker(enabled_providers=("jrw", "jreast", "yahoo"))
await tracker.refresh()

print(tracker.alerts)                    # 取得範囲内の全案内。混在する長期案内も保持
print(tracker.active_alerts)             # 専用状態から現在有効と確認した案内
print(tracker.unclassified_alerts)       # 適用時期を判別していない案内
```

長期／一時的の分類フィールドや専用フィルターはありません。`timing: AlertTiming` は `ACTIVE` / `UNKNOWN` のみです。各一覧は `Line`・Provider・`Tracker` で参照できます。`active_alerts` は一時的な障害だけの一覧ではありません。`Line.status` は取得範囲内の総合表示であり、対象外の欄に掲載された運休がないことを保証しません。

取得範囲と専用状態の根拠は [ALERT_CLASSIFICATION.md](https://github.com/dk-butsuri/train_operation_info/blob/main/tests/fixtures/ALERT_CLASSIFICATION.md)、判定方針は [CONTRIBUTING.md](https://github.com/dk-butsuri/train_operation_info/blob/main/CONTRIBUTING.md) を参照してください。

## Providerのメタデータ

```python
metadata = tracker.singapore_mrt.metadata
print(metadata.source_page_url)       # 人が閲覧する取得元ページ
for endpoint in metadata.endpoints:   # Providerが実際に取得するデータ
    print(endpoint.url, endpoint.method, endpoint.format.value)
    print(endpoint.is_template, endpoint.description)
print(metadata.terms_url)             # 利用規約
print(metadata.additional_terms_urls) # 運行情報固有の条件など
print(metadata.usage_permission)      # UsagePermission
print(metadata.usage_note)            # 分類の根拠・限定事項
print(metadata.reviewed_at)           # 規約確認日時（タイムゾーン付き）
```

`source_page_url` は人向けの案内ページ、`endpoints` はHTTP取得先の一覧です。同じURLを使う取得元もあります。各要素は `SourceEndpoint` で、`method` は `Literal["GET", "POST"]`、`format` は `DataFormat.HTML` / `XML` / `JSON` / `JAVASCRIPT` / `TEXT` です。HTMLはページや断片のスクレイピング、XML・JSONは構造化データの解析、JavaScriptは告知データの抽出、TEXTはプレーンテキストのフラグ等を表します。JavaScript自体を実行するものではありません。

京阪はJSON＋XML、京成はHTML＋JavaScript、シンガポールMRTはHTML＋JSON（POST）を記録しています。調査の根拠として参照しただけのスクリプト・履歴・規約URLは、実行時の取得先には含めません。

動的な取得先は `is_template=True` とし、`url` の `{filename}`・`{area}`・`{resource_path}` 等と `description` に決定方法を記録します。例えば京阪のXMLファイル名は一覧XML、シンガポールMRTのPOST先はページ内の `resourcePath` から決まります。これらのURLはテンプレートのままHTTPリクエストするものではありません。実際に解決された取得URLはsnapshotの記録で確認できます。メタデータの参照は通信を行いません。

| `UsagePermission` | 記録する意味 |
| --- | --- |
| `PRIVATE_USE_ONLY` | 私的使用等、法令に認められる範囲を留保する記載。それを超える利用には許諾が必要 |
| `UNSPECIFIED` | 該当する再利用条件を確認できない。要問い合わせ |
| `COMMERCIAL_ALLOWED` | 商用を含む再利用が明示されている。帰属表示等の条件は `usage_note` に記載 |
| `PERMISSION_REQUIRED` | 無断再利用を制限する明示的な記載がある |

区分は公開された条件の記録で、個々のサイネージ用途の適法性を判定するものではありません。無記載を私的利用可・商用可とみなしません。一般規約と運行情報固有の記載が異なる場合は両方を残します。
現時点の確認では阪急・阪神・ゆりかもめは法令上の利用範囲を留保し、台北MRTは公式の政府網站資料開放宣告に基づく出典表示付き再利用を `COMMERCIAL_ALLOWED` として記録しています。それ以外の取得元は運行情報またはサイト規約に無断再利用を制限する記載があります。参照した規約URLと根拠は各Providerのメタデータに記録しています。

## 構成

- 共通モデルは `models.py` ひとつにまとめています。
- 共通ファイルは `src/train_operation_info/`、各取得元はその配下の `providers/<取得元ID>/` に置きます。Providerごとに `__init__.py` と `provider.py` の2ファイルです。
- `tracker.osaka_metro` は大阪メトロ公式サイトという取得元の名前空間です。運行会社別の階層ではありません。
- `Line.operator` が運行会社、`Line.provider_id` が取得元です。
- `Line.scope` は個別路線か系統全体かを区別します。阪急の3項目は `LineScope.GROUP` で、個別の本線・支線を表すIDとは区別します。
- `Line.line_id` は `models.LINE_CATALOG` で管理する取得元共通の路線IDです。別Providerに同じ路線があっても、取得結果の `Line` は別インスタンスになります。新Providerは既存IDを再利用し、取得元固有のIDはProvider内で対応付けます。
- JR西日本の地区別項目が同じ路線を指す場合も統合します。例えば `jrw.ako_kinki` と `jrw.ako_okayama` は `jrw.ako` と同じスナップショットです。
- 路線名は明示的な型付きプロパティです。動的な属性生成や `Any` による属性解決は使いません。

```text
src/train_operation_info/
├── __init__.py       # Tracker などの公開API
├── py.typed
├── models.py         # 共通モデルと共通路線ID（LINE_CATALOG）
├── exceptions.py
├── snapshots.py      # HTTP応答の保存・再生
├── tracker.py
└── providers/
    ├── base.py
    ├── gtfs_rt.py    # GTFS-realtimeの共通解析
    └── <取得元ID>/    # 各取得元。__init__.py と provider.py
```

Providerを直接使う場合は `from train_operation_info.providers.osaka_metro import OsakaMetroProvider` のように読み込みます。

## HTTP応答の保存とオフライン再生

`snapshot_dir` を指定すると、取得した本文を解析前のバイト列で保存できます。全Providerで利用でき、通常時・異常時のほか、解析できなかった本文やHTTPエラー応答も残します。既定では保存しません。

```python
from train_operation_info import Tracker

tracker = Tracker(enabled_providers=("osaka_metro",), snapshot_dir="snapshots")
await tracker.refresh()
```

Providerを直接作る場合も `OsakaMetroProvider(snapshot_dir="snapshots")` のように指定できます。Trackerに独自Providerを渡す場合は、そのProvider自身にも `snapshot_dir` を指定してください。呼び出し側が渡したHTTPクライアントは、そのまま利用し、閉じたり設定を書き換えたりしません。

保存先は `snapshots/<provider_id>/YYYYMMDD/HHMMSS.ffffff_<識別子>.json` です。JSONには取得時刻（UTC）、リクエストのメソッド・URL・本文のSHA-256、HTTPステータス、文字コードを含むContent-Type、解析エラーを記録します。レスポンス本文は `snapshots/<provider_id>/bodies/<SHA-256>.gz` にgzip保存し、同じ本文を共有します。同じProviderで前回の応答一式・エラーが変わらなければ、新しい記録を作りません。この前回比較はプロセス内のProviderインスタンス単位です。1回の更新で複数のURLやPOSTを使う場合も、再生に必要な応答をまとめて記録します。

「本文」はhttpxがHTTP圧縮を展開した後、文字コード変換やHTML/JSON解析をする前のデータです。保存失敗はログに記録し、通常の更新は続行します。古いファイルの自動削除は行いません。`snapshots/` はGitの管理対象から除外しています。

収集・再生用のコマンドはリポジトリの `examples/` にあります（配布パッケージには含まれません）。リポジトリを取得し、プロジェクト直下で `pip install -e .` を実行してから使います。`record` は通常1回だけ取得し、`--interval 60` を付けると60秒間隔でCtrl+Cまで収集します。

```bash
python -m examples.snapshots record --provider osaka_metro --directory snapshots
python -m examples.snapshots record --provider osaka_metro --directory snapshots --interval 60
python -m examples.snapshots replay snapshots/osaka_metro
```

`replay` にProviderの保存フォルダーを渡すと最新の記録、JSONファイルを渡すとその記録を再生します。再生は外部通信せず、未記録のURL・POST本文はエラーにします。記録時刻を使うため、年の省略された掲載日時や期間限定のお知らせも当時の条件で解析できます。再生1回ごとに新しいTransportを作ります。

```python
import httpx
from train_operation_info import Tracker
from train_operation_info.snapshots import SnapshotReplayTransport

transport = SnapshotReplayTransport("snapshots/osaka_metro/20261102/<記録ファイル>.json")
async with httpx.AsyncClient(transport=transport) as client:
    tracker = Tracker(enabled_providers=("osaka_metro",), client=client)
    await tracker.refresh()
    print(tracker.affected_lines)
```

同じ設定（Yahooの地域選択など）のProviderで再生してください。JSONとそのProviderの `bodies/` は一緒に保管します。異常→復旧はそれぞれの記録を順に再生して確認できます。記録機能はHTTPクライアントが返した応答を保存するため、MockTransportや加工データを使った記録を、実際の異常時データとは扱いません。テストfixtureとして採用するときは取得元・日時・実データか合成かを `tests/fixtures/SOURCES.md` 等に記録してください。まだ未取得の実障害データは、実際にその表示が出た時の収集で補う必要があります。

## 運行監視ビジュアライザ

MAGIをモチーフにしたローカルのデバッグ画面です。追加のWebフレームワークやNode.jsは不要です。リポジトリを取得し、プロジェクト直下で `pip install -e .` を実行してから起動します。

```bash
python -m examples.visualizer --demo
```

ブラウザーで <http://127.0.0.1:8765> を開きます。`--demo` は架空の遅延・運休・通信失敗を表示し、「実データ」に切り替えるまで外部通信しません。終了はターミナルで `Ctrl+C` です。

実際の取得元を監視する場合は `--demo` を外します。最初に画面を開いたときに取得し、以降は「情報更新」または任意の60秒自動更新で再取得します。取得元やポートも指定できます。

```bash
python -m examples.visualizer --providers tokyo_metro osaka_metro jreast --port 8765
```

- 上のBALTHASARで平常路線、左下のCASPERで要確認路線、右下のMELCHIORで取得元の応答を表示します。各パネルを押すと対応する路線へ絞り込めます。路線数は取得元別で、共通IDが同じ路線の重複を含みます。
- 最初は「要確認」を表示します。「全路線」「通信エラー」の切り替えができ、路線ごとに状態・案内・取得時刻を一行で確認できます。見出しはHG明朝Eなどのローカル明朝体を使用し、フォントのダウンロードは行いません。
- 路線名・会社・共通IDで検索し、取得元と状態で絞り込めます。
- 路線を選ぶとアラート原文と公式ページを確認できます。共通ID、取得元が公表した更新日時、生JSON、エンドポイント情報は「デバッグ情報」にまとめています。更新日時が公表されていない場合は「公開なし」です。
- 取得失敗は運休とは別に表示します。失敗した取得元の前回値は保持し、エラーの原因と併せて確認できます。初回失敗は「不明・未取得」です。
- JSONのコピー・全監視データの保存ができます。同じ共通IDを持つ別取得元が選択対象に含まれる場合は、その状態も個別照会に表示します。

HTTP応答の記録も必要なら `--snapshot-dir snapshots/visualizer` を追加します。保存データの再生方法は「HTTP応答の保存とオフライン再生」を参照してください。Yahooは他のサンプルと同様、`--providers` に `yahoo` を指定した場合だけ取得します。このサーバーはローカル開発用で、`127.0.0.1` のみで待ち受けます。

すべての取得元で `ConnectError: All connection attempts failed` になる場合は、サーバーを起動した環境の外部通信制限を確認し、通常のPowerShellなど外部接続可能な環境で起動してください。ブラウザーが通信可能でも、サーバー側のPythonが通信できない場合があります。

`CERTIFICATE_VERIFY_FAILED: Missing Subject Key Identifier` など、Pythonの証明書検証と取得先の証明書チェーンの互換性で失敗する場合は、OSの証明書ストアで検証するオプションを利用できます。証明書の信頼性・ホスト名の検証は有効なままです。

```bash
python -m pip install -e ".[visualizer]"
python -m examples.visualizer --system-certificates
```

## サンプル

Provider別の取得例はリポジトリの `examples/` にあります。プロジェクト直下から実行します。

```bash
python -m examples.hakone_tozan
python -m examples.jrcentral
python -m examples.jreast
python -m examples.jrhokkaido
python -m examples.jrkyushu
python -m examples.jrshikoku
python -m examples.keikyu
python -m examples.keio
python -m examples.keisei
python -m examples.kintetsu
python -m examples.meitetsu
python -m examples.nagoya_subway
python -m examples.minatomirai
python -m examples.nankai
python -m examples.odakyu
python -m examples.osaka_metro
python -m examples.rinkai
python -m examples.seibu
python -m examples.taipei_metro
python -m examples.thsr
python -m examples.tobu
python -m examples.sapporo_subway
python -m examples.toei
python -m examples.tokyo_metro
python -m examples.tokyu
python -m examples.tosaden
python -m examples.tra
python -m examples.yuirail
python -m examples.yurikamome
python -m examples.all_providers
```

`examples.all_providers` は既定の取得元を使うため、Yahoo・MTA・小田急電鉄・DBには通信しません。Yahooの例は `python -m examples.yahoo` で実行できます。

## 開発

```bash
git clone https://github.com/dk-butsuri/train_operation_info.git
cd train_operation_info
python -m pip install -e ".[dev]"
python -m mypy
python -m pytest
```

取得元のページやAPI応答を保存したテストデータは、取得元の著作物を再配布しないためリポジトリに含めていません。出典・保存日時・ハッシュは `tests/fixtures/` の記録ファイルに残しています。データがないテストはスキップされます（`python -m pytest -rs` で確認できます）。

Providerの追加手順、共通路線IDの照合方法、Pydantic・日時の扱い、調査根拠の記録方法は [CONTRIBUTING.md](https://github.com/dk-butsuri/train_operation_info/blob/main/CONTRIBUTING.md) にまとめています。

## ライセンス

[MIT License](https://github.com/dk-butsuri/train_operation_info/blob/main/LICENSE)

MIT Licenseが適用されるのはこのライブラリのソースコードのみです。本ライブラリで取得した運行情報には適用されず、各取得元の規約に従います。
