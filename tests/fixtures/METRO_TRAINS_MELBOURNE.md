# Metro Trains Melbourne healthboard

2026-11-04に公式HTML・JavaScriptを逆解析し、公式JSONをライブ取得した。アーカイブは使っていない。
取得URL・UTC取得日時・原本SHA-256は [metro_trains_melbourne_manifest.json](metro_trains_melbourne_manifest.json) に記録。
原本は `reports/metro_trains_melbourne/`、テスト用の無加工コピーは
`metro_trains_melbourne_network.json` と `metro_trains_melbourne_healthboard.json` にローカル保存する。
第三者の本文・スクリプトはGitに含めない。すべてライブラリ標準User-AgentによるGETで取得した。

## 根拠と対応

- [公式ホームページ](https://www.metrotrains.com.au/) のHealthboard Service Legendが状態の意味を説明する。
- [公開アプリ m3.2.4](https://ds12k1658w1f2.cloudfront.net/wp-content/themes/metrotrains/library/js/mtm-app.min.js?ver=m3.2.4) の `MTMAPIService.getHealthboardAlerts` は
  [get_healthboard_alerts](https://www.metrotrains.com.au/api?op=get_healthboard_alerts) を取得する。
- `getNetworkData` は `get_network` と `mtmConfig().getNetworkConfig()` を使う。調査時の `defaultNetworkConfig` は `Aug26`。
  Providerは [Aug26の路線定義](https://www.metrotrains.com.au/api?op=get_network&config=Aug26) を使用する。
  設定名の自動発見はしない。路線ID・名称・件数を照合し、変更は `ParseError` にする。
- `MTMHealthboardLine` は路線の `alerts` 配列を `MTMHealthboardAlert` として読み込む。
  ライブの平常文字列は `metadata.empty_alert_strings.good_service` と一致する固定文
  `Good service - trains are running on time`。この完全一致と空の配列を平常として扱う。
  任意の文字列を平常にするUIの寛容な挙動は採用しない。
- `mtmDefinitions.alertNames` / `alertDescriptions` と公式凡例を根拠に次の対応とする。

| ソース値 | 共通状態 | 根拠・限界 |
| --- | --- | --- |
| `good` / `good-service`、固定の平常文字列、空配列 | `NORMAL` | 配信範囲の平常表示。5分程度までの遅れを含む |
| `minor` / `major` | `DELAYED` | 凡例でそれぞれ5～15分、15分超の遅延 |
| `suspended` | `PARTIAL_SUSPENSION` | 凡例が区間の見合わせと明記。全線運休は導出しない |
| `works` / `travel` / `trip` / `service` / `cancellation` | `ALERT` | 工事・案内・列車単位の変更／運休。路線全体の運休に拡大しない |
| `no-services` | `NORMAL` | 運転予定がない表示であり、障害による運休ではない |
| その他のコード・文字列 | `UNKNOWN` | 元のコード・本文を保持 |

`NORMAL`の通知レコードも復旧等の原文を保持する。複数通知はすべて保持し、
`combined_status` で集約するため、平常通知が別の障害を消さない。
路線IDは下記の静的対応で、ネットワーク・運行情報の路線名があれば一致も検証する。
本文にある別路線名や駅名を対象路線に加えない。

| 公式ID | 共通IDの末尾 | 公式ID | 共通IDの末尾 |
| --- | --- | --- | --- |
| 82 | alamein | 84 | belgrave |
| 85 | craigieburn | 86 | cranbourne |
| 87 | mernda | 88 | frankston |
| 89 | glen_waverley | 90 | hurstbridge |
| 91 | lilydale | 92 | pakenham |
| 93 | sandringham | 94 | stony_point |
| 95 | sunbury | 96 | upfield |
| 97 | werribee | 98 | williamstown |
| 168307 | racecourse | | |

共通IDは `au:metro_trains_melbourne:<末尾>`、会社IDは `au:metro_trains_melbourne`。
既存カタログに一致する豪州路線はなかった。すべて `LineScope.LINE`。
Racecourseは公式名称を使用する。`MTMHealthboardLine` はネットワークの `active=false` と
`no_services` の存在により、通知のない路線をNo Servicesと表示する。Providerもこの条件を使い、案内本文を保持する。

`MTMHealthboardData` は別の `disruptions` コレクションの `lines` から対象路線を割り当てる。
`MTMHealthboardDisruption` が読む `alert_type` / `notice` / `from_date` / `to_date` を取り込む。
UIの「路線通知が空の場合だけnoticeを補完する」処理より情報を多く保持し、既存通知があってもnoticeを残す。
実際のdisruptionsは空配列だった。辞書形式は同クラスの `doForEachMapEntry` が消費する構造として合成テストで検証する。

`mtmAlertTimestampToString` は `from_date` / `to_date` を整数化して1000倍し、JavaScript Dateにする。
これをUnix秒としてUTCの `active_from` / `active_until` に変換する。空文字・0・nullは未指定。
`modified` の路線更新時刻としての意味は未確認で、`updated_at=None`。
全通知の `timing=UNKNOWN`。特にworksは24時間以内の予告を含み、本文や期間からACTIVEを推測しない。

## 取得範囲と検証範囲

路線の `alerts` と `disruptions` を対象とする。`planned_works_list`、`planned_works`、
`extra_services_list`、`extra_services`、`lift_escalator_outages`、ネットワークの `general` バナーは対象外。
長期工事等の別コレクションは状態へ混ぜないが、`alerts`内のworksはそのまま保持する。

ライブ応答は17路線、16路線の平常文字列とWerribeeのworks通知で、RacecourseはNo Services条件も満たした。
実際の遅延・見合わせ・復旧・複数通知・非空disruptionsは未取得。
これらのテストと未知状態・欠損・不正日時・通信失敗は公開コード／凡例に基づく合成データであり、実障害の記録ではない。
保存・再生テストは取得済み原本をMockTransport経由で記録し直すもので、新たなライブ取得の証拠ではない。

## 利用条件の確認

公式ホームページのフッターはMetro Trains Melbourneの著作権を表示し、リンク先は
[Privacy Policy](https://www.metrotrains.com.au/privacy)。確認したページ・アプリ・検索では、
サイト／運行情報の一般利用規約や再利用許諾を発見できなかった。
駅構内の活動許可条件やTransport Victoriaの別サービスのライセンスを、このAPIの条件として流用しない。
メタデータは `terms_url=None` / `UNSPECIFIED`。再利用を許可する分類ではなく、一般規約が不存在だと断定するものでもない。
