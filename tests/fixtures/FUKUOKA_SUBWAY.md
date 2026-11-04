# 福岡市交通局：公式運行情報

2026-11-04 UTCに公開HTML・JavaScriptとWayback保存HTMLを調査しました。
HTTP取得にはライブラリのUser-Agentを使用しています。
原本のSHA-256、UTC取得時刻、保存URL、ローカルfixture名は
[fukuoka_subway_manifest.json](fukuoka_subway_manifest.json) に記録しています。
fixtureは応答bytesを無加工でコピーし、第三者コンテンツをGit・配布物には含めません。

## 対応の根拠

- [運行情報](https://subway.city.fukuoka.lg.jp/status/) の `section#status .box02 dl > dt`
  に本文 `.statusNews` と専用の更新欄 `div[align="right"]` が直接存在します。
- 現行と20230711012832・20241224075857・20250501031503・20260527005254の保存HTMLで
  同じ平常定型文全体を確認しました。この完全一致だけを `NORMAL` とします。
- [20240829161647の保存HTML](https://web.archive.org/web/20240829161647id_/https://subway.city.fukuoka.lg.jp/status/)
  は台風接近時の運転見合わせ予告です。平常時と同じ `span.status.st02` を使用しているため、
  アイコンを運休コードと解釈できません。定型平常文以外は運行案内の掲載として `ALERT` とし、
  遅延・運休・復旧・予告を本文から分類しません。
- 本文のリンク先は文字列として保持し、追加取得はしません。
- 路線別の専用対象フィールドはありません。全体の運行案内を3路線に共有しますが、
  `affected_line_ids=()` を維持します。各路線に障害が発生していることを意味しません。
  Yahooの空港線・箱崎線・七隈線と既存の共通IDを使い、取得結果は独立です。
- 保存HTMLの専用「更新」欄は年・月・日・時・分を明示しています。
  日本の現地時刻として `Asia/Tokyo` を付け、空欄は `updated_at=None`。
  `.data` の「現在」はページ生成時刻なので更新日時として代用しません。
- 適用時期を確定する専用状態は確認できず `timing=UNKNOWN`、適用期間は `None`。
  公開されている予定が現在の運行欄に混在する場合も保持します。

## 取得範囲と未確認事項

ヘッダーの `running.json` は要約表示で、実行時は取得しません。
[suspension_header.js](https://subway.city.fukuoka.lg.jp/js/suspension_header.js) は
別の `suspension.json` を「計画運休等の予定」欄に表示します。この構造的に独立した欄は対象外です。
現在の運行欄内にある長期案内の専用分類は確認できていません。
運行履歴・遅延証明書・列車位置・ニュース・乗り入れ先JR線の情報も取得しません。
生応答記録には別欄のリンクやヘッダー用スクリプトが含まれます。

実際の保存応答で平常と運転見合わせ予告を検証します。現在有効な遅延・運休を細分する専用コード、
路線ごとの対象指定、同一障害の発生から掲載削除までの連続応答は未確認です。
任意本文の否定・遅延・予告・復旧、リンク、破損・HTTP失敗・掲載削除の連続更新は合成テストです。
空欄・必須構造の欠損・重複・不正な更新日時は `ParseError` とし、直前の結果を保持します。

## 利用条件

[当サイトについて](https://subway.city.fukuoka.lg.jp/utility/) の利用制限に基づき
`usage_permission=PRIVATE_USE_ONLY` とします。公開利用・商用利用への許諾は確認していません。
