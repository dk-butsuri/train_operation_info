# MTA New York City Subway (GTFS-realtime Service Alerts)

調査日: 2026-11-03 (UTC)。共通デコーダは `providers/gtfs_rt.py`、Providerは `providers/mta_subway/provider.py`。

## 取得元

| 種別 | URL | 確認内容 |
| --- | --- | --- |
| フィード | `https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts` | APIキー不要、`application/x-protobuf`。2回取得のみ |
| 公式仕様 | https://www.mta.info/document/90881 (MTA GTFS Alerts Feed Documentation, December 2021) | PDF（取得時SHA-256 `0d734dde5f97cdd38372b8fb13a815ebe3db96b3fec73e10ce9955bd220cbd5b`）。リポジトリには保存しない |
| GTFS-rt標準 | https://github.com/google/transit/blob/master/gtfs-realtime/proto/gtfs-realtime.proto | フィールド番号の根拠。SHA-256 `8feff2c5499e0ff08777e203e49ef702e07be0a8376b8bb2126add311a709299` |
| 静的GTFS | https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip | `routes.txt` 29路線と名称。2026-11-03T03:38:53Z取得、SHA-256 `acb122715bd90aeacf61f4559722ccf0b7de9c63317200a6dd7480246488f1e6` |
| 規約 | https://www.mta.info/developers/terms-and-conditions | "Updated Mar 13, 2024" |
| 人向けページ | https://www.mta.info/ | 路線別の運行状況。`/alerts` は計画運休の一覧 |
| 状態ラベル解説 | https://www.mta.info/guides/service-status | Delays/Part Suspended/Suspended等の説明（分類には未使用） |

## 公式仕様から採用した対応

- `FeedEntity.id`: "`lmm:planned_work` indicates a planned service interruption ... and `lmm:alert` indicates an unplanned disruption of service"。計画工事はIDで構造的に分離されているため除外。`lmm:` で始まらないIDは仕様外として `ParseError`。
- Mercury拡張の `alert_type` は "data consumers should treat this as a free text field" とされるため、状態・除外の判定に使わない。実データでも計画工事に `Planned - ` 接頭辞のない種別（Reduced Service, Boarding Change, Extra Service, Station Notice, Expect Delays）があり、接頭辞では分離できない。
- `cause`・`effect`・`url` は "Not currently used"。実データの全180/181件で `effect` 欠落。共通規則によりアラートのある路線は `UNKNOWN`、`ServiceAlert.effect` も `UNKNOWN`。
- `active_period` は "times when the alert should be shown to the user"。未計画アラートの開始はMercuryの `created_at` と一致し、2回目の取得では表示終了時刻が付いた。障害期間ではないため `active_from`/`active_until` は `None`、`timing` は `UNKNOWN`。
- `EntitySelector`: `agency_id` は `MTASBWY`（静的GTFSの `MTA NYCT` とは異なるが仕様書の値）。`route_id` は静的GTFSの `route_id` と一致することを確認し、29路線すべてを共通ID `us:nyct_subway:<route_id小文字>` に対応付けた。GTFSの路線は運転系統（A、6X、GSなど）であり、物理的な線路名ではない。
- 文字列は `en`（平文）を使用し、`en-html` は使用しない。本文は改変しない。

## 保存データ（実データ）

| Fixture | 取得時刻 (UTC) | 内容 |
| --- | --- | --- |
| [mta_subway_alerts_20261103033316.pb](mta_subway_alerts_20261103033316.pb) | 2026-11-03 03:33:16 | 180件中178件が計画工事。未計画: F/G遅延 (`lmm:alert:274643:26`)、B/Q通過 (`lmm:alert:274645:29`)。すべて路線のみのセレクター |
| [mta_subway_alerts_20261103045354.pb](mta_subway_alerts_20261103045354.pb) | 2026-11-03 04:53:54 | 181件中178件が計画工事。F/G/Bのアラートは消滅（実際の復旧）。Q・3・Eの遅延3件 |

取得方法・ハッシュは [mta_subway_manifest.json](mta_subway_manifest.json)。応答本体は無加工。フィードヘッダの `timestamp` は取得時刻より7〜31分古い値だったが、そのまま `updated_at` とする。

デコーダの検証として、1件目を公式 `gtfs-realtime-bindings` 3.0.0 で解析した結果（ID、見出し・本文の全翻訳、active_period、セレクター、effectの有無）と全180件で一致することを調査時に確認した（ライブラリの依存には含めない）。

## 合成データ

`tests/test_gtfs_rt.py` はすべてテスト内のエンコーダで生成した合成フィード。`tests/test_mta_subway.py` の `_synthetic_entity` は実データの末尾に合成エンティティを追加したもの。次の項目は実データで未確認:

- `effect` を伴うアラート（NO_SERVICE→SUSPENDED、SIGNIFICANT_DELAYS→DELAYEDなど）。MTAは現在使用していない。
- 停留所のみのセレクター（全路線 `UNKNOWN`・`affected_line_ids=()`）、未登録route_id、仕様外ID、破損データ。
- `impact_period`（MTA未使用）による `active_from`/`active_until`。

## 未確認・保留

- `alert_type` と Mercury `sort_order` の優先度（`PRIORITY_DELAYS` 等）は公式に記述があるが自由記述扱いのため未使用。採用するとF/G等を `DELAYED` にできるが、方針判断が必要。
- 規約は「MTAのサーバーから直接他者へデータを提供するアプリ」を禁止し、データの改変・削除も禁止している。本Providerは既定で無効（opt-in）。計画工事の除外・英語表示の選択が "modify or delete" に当たらないことはMTAに確認していない。
