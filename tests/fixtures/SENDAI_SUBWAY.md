# 仙台市交通局（南北線・東西線）

2026-11-04 UTCに、共通User-Agentで公式HTML・公開CSS/JavaScriptとWaybackの
保存ページを調査しました。URL、UTC取得日時、HTTP結果、原本・抽出後のSHA-256は
[sendai_subway_manifest.json](sendai_subway_manifest.json) に記録しています。
原本はローカルの `reports/sendai/`、抽出HTMLは `tests/fixtures/` に保存し、
第三者本文はGitに含めません。

## 取得元と対応根拠

- https://www.kotsu.city.sendai.jp/unkou/nanbokusen/
- https://www.kotsu.city.sendai.jp/unkou/touzaisen/
- https://www.kotsu.city.sendai.jp/unkou/
- https://www.kotsu.city.sendai.jp/wp-content/themes/sendai_theme/css/unkou.css
- https://www.kotsu.city.sendai.jp/wp-content/themes/sendai_theme/js/navigation.js?ver=1.0.0

路線別ページはサーバー側でHTMLを生成します。`#mainarea .page_contents .page_inner`
内の `#nanbokusen.nanbokusen_unkou_box` と `#touzaisen.touzaisen_unkou_box` に、
`dl > dt` の路線名、`dl > dd` の状態表示があります。実取得ではどちらも
`dd.clearfix.ope_normal` に `平常運行` が掲載されていました。
東西線の2026-04-12の保存ページにも同じ路線欄・クラス・平常表示があります。

`ope_normal` と完全な平常表示の両方を満たす場合のみ `NORMAL`。
証明書ボタン `.chien_btn` と路線見出しを除く `page_inner` 全体を保持し、
追加本文・リンクがある場合は平常へ分類しません。画像は代替テキストを保持し、
代替テキストがない画像や動的な実行コンテンツは解析失敗とします。
路線・状態欄の欠損、空状態、重複、異なる路線名は `ParseError` です。
他の状態は原文とリンク先を保持する `UNKNOWN`、影響・適用時期も `UNKNOWN`。
対象路線は各ページの専用路線欄から決定します。

| 公式ページ | 共通路線ID | 公開属性 |
| --- | --- | --- |
| nanbokusen | `jp:operator_31739cacf719:line_cc1ac570adb3` | `namboku` |
| touzaisen | `jp:operator_31739cacf719:line_3cb65ac614ea` | `tozai` |

Yahooの既存定義を再利用し、会社は `jp:operator_31739cacf719`（仙台市交通局）。
別Providerのスナップショットは独立しています。

公式説明の掲載基準は、地下鉄に30分以上の遅れが発生または見込まれる場合です。
`NORMAL` はこの掲載範囲の表示です。適用時期を示す専用項目は確認していないため、
`timing=UNKNOWN`、適用期間はNone。WordPressの `dateModified` はページの更新日時で、
運行状態の更新日時として確認できないため、`updated_at=None` とします。

## 異常時の調査と限界

公開CSSには `ope_down`、`ope_lag` のアイコン参照と `.unkou_detail_text` の定義が
あります。クラス名だけでは実際の異常時本文、運休範囲、現在有効かどうかを確定できません。
確認したHTMLのインラインスクリプトはスライダー・広告・解析・メニュー等、
`navigation.js` はメニュー操作です。専用の運行データ取得処理は見つかりませんでした。

Wayback CDXで `/unkou/*` の2026年のHTML保存を照会しました。
南北線の現行ページの保存はこの結果に含まれていません。東西線の現行ページと
現在と同じ形式の一覧ページを取得しましたが、いずれも平常表示でした。
検索結果に遅延証明書も含まれますが、現在の障害形式の根拠や現在状態の補完には使いません。
最初の無期間CDX照会は古い2009年以降の先頭25件だけを返すため、2026年に絞って再照会しました。

- https://web.archive.org/web/20260412141736id_/https://www.kotsu.city.sendai.jp/unkou/touzaisen/
  （東西線の平常表示）
- https://web.archive.org/web/20260712033444id_/https://www.kotsu.city.sendai.jp/unkou/
  （南北線・東西線の平常一覧・30分基準の説明）

異常時の現行形式・ラベル・日時形式は未確認です。
未知クラス、遅延・見合わせ・否定・予告・復旧の本文、長期案内混在、追加本文、
構造破損、HTTP失敗、2路線目の解析・通信失敗のテストはすべて**合成**です。
合成テストは公式の異常時仕様を実証しません。

## 保存・取得範囲

fixtureはライブ南北線・東西線と上記保存東西線の `#mainarea` をBeautifulSoupの
`html.parser` でシリアライズし、UTF-8宣言を付けたものです。
内容・状態を書き換えていません。原本ハッシュとfixtureハッシュを別々に記録しています。

実行時は路線別の2ページのみを取得し、各 `.page_inner` の案内を解析します。
遅延証明書ボタンは構造で除外し、リンク先本文、証明書、時刻表、別のお知らせ、
市バス、Xは取得しません。原本HTTP記録にはサイドメニュー・証明書へのリンク等も含まれます。
路線欄に長期案内を分離する専用項目は未確認で、混在案内は本文から除外しません。
両ページを取得後、同じ取得時刻で完全なスナップショットを作るため、
片方の失敗で他方だけが差し替わることはありません。

## 利用条件

https://www.kotsu.city.sendai.jp/menseki/ は、私的使用・引用等の法定の範囲を除く
無断複製・転用を認めていません。トップページ以外へのリンクには問い合わせを求めています。
利用条件は `PERMISSION_REQUIRED` として記録します。再利用許諾を得たという意味ではありません。
