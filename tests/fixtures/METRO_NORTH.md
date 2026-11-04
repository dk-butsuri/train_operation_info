# Metro-North Railroad（GTFS-realtime Service Alerts）

調査日: 2026-11-04 UTC。公式仕様、公開JavaScript、静的GTFS、ライブ応答を確認。アーカイブは使用していない。
取得には `providers/base.py` の `USER_AGENT` を使用し、キー・認証なしでアクセスした。
取得時刻・原本／抽出後SHA-256・加工方法は [metro_north_manifest.json](metro_north_manifest.json)。
第三者の応答本体は `.gitignore` に従ってローカルのみ保存する。

## 取得元と路線照合

| 出典 | 確認事項 |
| --- | --- |
| [MTA Developer Resources](https://api.mta.info/) の `static/js/main.bc5d42b5.js` | `camsys%2Fmnr-alerts` がMetro-North Railroad Alerts。列車位置用の `mnr%2Fgtfs-mnr` は対象外 |
| [公式フィード](https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fmnr-alerts) | キー不要、`application/x-protobuf`、FULL_DATASET 2.0 |
| [MTA GTFS Alerts Feed Documentation](https://www.mta.info/document/90881)（December 2021） | `agency_id=MNR`、計画工事ID、effect未使用、active_periodの意味 |
| [公式静的GTFS](https://rrgtfsfeeds.s3.amazonaws.com/gtfsmnr.zip) | `routes.txt` の1〜6と名称、`agency.txt` のMetro-North RailroadとAmerica/New_York。両CSVは無加工抽出 |
| [公式トップページ共通スクリプト](https://consist.mta.info/vuejs/apps/common/index.min.js) | 路線一覧APIの参照、Wassaic別掲載、大小文字を無視したroute_id照合。関係する3文だけ `metro_north_route_excerpt.js` に抽出 |
| [画面用路線一覧](https://otp-mta-prod.camsys-apps.com/otp/routers/default/index/routes) | キーなしGETに成功。`MNR:` レコード8件を `metro_north_status_routes.json` に投影。50=Pascack Valley、51=Port Jervis |
| [公式Developer resources](https://www.mta.info/developers) | 西岸2路線の時刻表はNJ Transit GTFSに収録すると明記 |
| [MTAデータ規約](https://www.mta.info/developers/terms-and-conditions) | Updated Mar 13, 2024。非MTAサーバーでの保存・配信等の条件 |
| [ライセンス条件](https://www.mta.info/doing-business-with-us/licensing-program) | フィードの利用条件とは別に確認が必要 |

既存 `LINE_CATALOG` に重複路線はない。共通IDの接頭辞は `us:metro_north:`。
西岸の運転実務はNJ Transitとの契約だが、公式路線一覧のサービス事業者はMetro-North Railroad。
ここでの `Line.operator` はこのサービス事業者を表す。

| alert route_id | 属性・共通ID末尾 | 根拠 |
| --- | --- | --- |
| 1 | `hudson` | 静的GTFS・画面用路線一覧 |
| 2 | `harlem` | 同上 |
| 3 | `new_haven` | 同上 |
| 4 | `new_canaan` | 同上 |
| 5 | `danbury` | 同上 |
| 6 | `waterbury` | 同上 |
| 50 | `pascack_valley` | 画面用路線一覧 |
| 51 | `port_jervis` | 画面用路線一覧 |
| wassaic / Wassaic | `wassaic` | 実フィードは小文字。共通スクリプトは `MNR:Wassaic` を追加し、照合時に両側を小文字化 |

WassaicはHarlem全体と統合しない。本支線間や親子の掲載単位にアラートを伝播しない。
9掲載単位をそれぞれ保持し、公式に確認した上記2表記以外の未知IDは推測せず拒否する。
路線一覧・スクリプトは調査時だけ取得し、Providerの実行時通信はアラートフィード1件だけ。

## 状態・適用時期

- `lmm:planned_work` は公式仕様で計画工事と定義されるため、対象外。路線IDの検証前に除外する。対象外欄は生応答の保存には含まれる。
- その他の `lmm:` エンティティを保持。`lmm:` 接頭辞のないIDは `ParseError`。`alert_type` は自由記述扱いのため、状態・計画工事除外・適用時期に使用しない。
- 実応答の `effect` は全件欠落。アラートのある路線と `ServiceAlert.effect` は `UNKNOWN`。遅延分数や本文の現在形は分類根拠にしない。
- 明示的な `effect` がある場合は共通GTFS-rt規則を使う。路線全体のNO_SERVICE→SUSPENDED、SIGNIFICANT_DELAYS→DELAYED。停留所・列車・方向に限定される場合やその他の既知effectはALERT、未知effectはUNKNOWN。
- `active_period` は表示期間。`active_from` / `active_until` に転用しない。実応答に `impact_period` はなく、`timing=UNKNOWN`。ヘッダのtimestampを `updated_at` に使い、取得時刻は別に保持。
- `en` の見出し・本文を使用し、`en-html` を選ばない。路線指定のない案内は `affected_line_ids=()`、全掲載単位の状態をUNKNOWNとする。
- `NORMAL` は取得範囲に未計画アラートがないことだけを表す。計画工事を含めた平常、全列車の定時運転を意味しない。

## 実応答と合成テスト

`metro_north_alerts_20261104115626.pb` は2026-11-04T11:56:26.341339Z取得の無加工応答。
ヘッダtimestampは11:38:39Z。10件中9件が計画工事、1件がHarlemの列車別遅延案内
（`lmm:alert:274816:24`）。後者は `agency_id=MNR, route_id=2` と列車セレクターの
`trip.route_id=2` を持つ。同じ共通路線・アラートを二重に生成しない。
計画工事には1/2/3/6/50/51/wassaicの路線・停留所セレクターと複数表示期間がある。

`tests/test_metro_north.py` の合成フィードはすべてテスト内で生成する。
空フィードへの復旧、各路線への未計画案内、Wassaicの大小文字、明示effect、列車・停留所の
狭い対象、路線不明、未知ID・事業者、重複・破損・通信失敗、対象外工事の未知route_idを検証する。
実際の復旧、平常時の空フィード、各支線・西岸・Wassaicの未計画障害、明示effectは未確認。
これらの合成テストを実障害の証拠とは扱わない。

利用条件は既存MTA Subwayと同じく `PERMISSION_REQUIRED`、既定無効。
計画工事の除外・英語選択とデータ改変禁止条項の整合性はMTAに個別確認していない。
