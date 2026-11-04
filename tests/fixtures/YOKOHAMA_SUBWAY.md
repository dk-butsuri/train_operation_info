# 横浜市営地下鉄（ブルーライン・グリーンライン）

2026-11-04 UTCに公式HTML・公開JavaScript・公開APIを共通User-Agentで調査しました。
正確なURL、UTC取得日時、HTTP結果、原本SHA-256は
[yokohama_subway_manifest.json](yokohama_subway_manifest.json) に記録しています。
第三者の応答原本・スクリプトは `reports/yokohama/`、テスト用コピーは
Git対象外の `tests/fixtures/` に保存し、配布しません。

## 取得元・共通路線

- 表示ページ：https://status.hamabus.city.yokohama.lg.jp/operation/list
- 現在一覧：https://cms.yokohama-operation.cld.navitime.jp/api/web/railroad/operations?lang=ja
- 調査用履歴：https://cms.yokohama-operation.cld.navitime.jp/api/web/railroad/operations/history?lang=ja

| 公式 `line.id` | 公式名 | 共通路線ID | 公開属性 |
| --- | --- | --- | --- |
| `1` | ブルーライン | `jp:operator_702b41c21dfa:line_103dce814f8a` | `blue` |
| `2` | グリーンライン | `jp:operator_702b41c21dfa:line_7332f720bd3d` | `green` |

既存のYahooと路線全体の範囲・会社（横浜市交通局）が一致するため、その定義を再利用します。
Providerごとの状態は独立しています。新規の会社・共通路線IDは追加しません。

## 公開スクリプトと対応根拠

スクリプトはすべて `https://status.hamabus.city.yokohama.lg.jp/_nuxt/` 配下です。

- HTMLの `window.__NUXT__.config.public.apiBaseUrl` は上記CMSを指定。
- `CoffiUX-.js`：`fetchOperationInfoList()` が地下鉄の現在一覧、
  `fetchOperationInfoHistoryList()` が別の履歴を取得。日本語は `lang=ja`。
- `Bjix2mz5.js`：`BLUELINE="1"`、`GREENLINE="2"`。
- `CqGW2eWD.js`：`resRail.items` を `line.id` ごとに抽出し、0件なら
  `OperationInfoCardRailNormal` を表示。非空なら `operationStatus.name` と
  `sections`、`cause`、`maxDelayTime`、`period` を表示。
- `CpZcISDq.js`：日本語の `common.normal-service` は平常表示。
  `now` をクライアント側で更新日時に変換する処理ではありません。
- `CUgBru-4.js`：別の詳細APIから `additionalInfo`、`additionalUrl`、
  `replacementTrains` を取得する構造。今回のProviderはこの詳細を取得しません。
- `Br3FGq2Z.js`：詳細リンクのID検証は英数字・ハイフン、1～64文字。

ライブの現在一覧は `now` と空の `items` を返しました。
必須エンベロープと全項目を検証した後、路線ごとの0件を `NORMAL` に対応させます。
欠損した `items` や未知の路線IDを「当該路線の情報なし」とは扱いません。

公式履歴の7項目はブルーラインの過去の遅延で、すべて専用状態が
`operationStatus.id="2"`、`operationStatus.name="遅延"` でした。
表示コードが専用状態名をそのまま使うため、この組だけを `DELAYED` に対応させます。
他のID・名前の組は `UNKNOWN`。本文・アイコン・`hasDelayStatus` から分類しません。
各一覧レコードの使用フィールドをJSONとして `alert.description` に保持します。
使用しない追加フィールドは入力モデルの `extra="ignore"` で無視します。
欠損・型不一致・同一路線内の重複group ID・既知IDに異なる路線名・逆転した期間は `ParseError`。
画面のリストkeyに合わせて路線とgroup IDの組を識別子とし、路線間の同一group IDは許容します。
複数項目を統合するときも未知状態とすべての案内を保持します。

`timing=UNKNOWN`、`active_from/active_until=None`、`updated_at=None` です。
現在一覧に載っていることと「現在有効」の確定を区別します。
`now` はサーバー時刻、`period` は表示する案内期間で、`updateTime` は
今回の一覧画面では表示されないため、共通モデルの更新日時へ代用しません。

## 異常時の調査・未確認範囲

調査方法は**公開HTML・JavaScriptの逆解析と公式のライブ履歴API**です。
現在一覧の異常時応答、運休・見合わせコード、グリーンライン異常時、同一障害の
復旧応答は未確認です。履歴項目を現在一覧のエンベロープに入れたテストは、
**履歴の内容を改変しない合成エンベロープ**であり、実際の現在応答の証拠ではありません。
未知状態・否定・将来予告・復旧・複数路線・長期案内・故障はすべて合成テストです。

Wayback CDXのAPI応答索引照会はタイムアウトしました。
ページの索引は2021年、2023年、2026年の保存を返しましたが、保存本体は取得していません。
SPAのHTML索引だけではAPIの異常時データの証拠になりません。
履歴の最初のgroup IDを詳細APIへ指定した調査応答は `{}` で、
過去の詳細本文は確認できませんでした。詳細取得による補完は行いません。

## 取得範囲・保存方法

実行時は日本語の地下鉄**現在一覧だけを1回GET**します。履歴、別の詳細画面、
遅延証明書、市バス、列車位置、外部リンク本文、お知らせは取得しません。
一覧内部に長期案内を区別する専用項目は未確認です。混在案内は本文から除外しません。
`NORMAL` は取得対象の一覧に掲載がないことを示し、全情報・短時間の遅れまで保証しません。
通信・解析失敗時には2路線の前回スナップショットをまとめて保持します。

`operations.json` と `history.json` を無加工で
`yokohama_subway_normal.json`、`yokohama_subway_history.json` にコピーしました。
fixtureのSHA-256は原本と同じです。記録・再生テストのMockTransportは新たな取得証拠ではありません。

## 利用条件

フッターのリンク先は https://www.city.yokohama.lg.jp/aboutweb/sitepolicy.html です。
この方針は `https://www.city.yokohama.lg.jp/` を「当サイト」と定義し、
その他の公式ドメインのサイトをサブサイトとして区別しています。
当サイトでは法定の範囲を除く無断複製・転用を制限し、数値・簡単な表等や
別途ライセンスが明示されたデータを区別しています。
運行情報サブサイトとCMSへの明示的な適用・個別の再利用許諾は確認できていません。
メタデータは `UNSPECIFIED` とし、一般規約のリンクと適用範囲の不確実性を記録します。
