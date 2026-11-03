# 札幌市営地下鉄

2026-11-04（日本時間）に公式HTML・公開JavaScript・CSSを調査しました。
取得URL、UTC取得日時、原本・抽出後のSHA-256は
[sapporo_subway_manifest.json](sapporo_subway_manifest.json) に記録しています。
原本はローカルの `reports/sapporo/` に保存し、第三者コンテンツを配布しません。

## 現在ページと判定

- https://operationstatus.city.sapporo.jp/unkojoho/
- https://operationstatus.city.sapporo.jp/shared/site_st/js/st_jsset.js
- https://operationstatus.city.sapporo.jp/shared/site_st/style/unkojoho.css

共通User-AgentでHTTP 200を確認しました。`sapporo_subway_normal.html` は
取得したHTMLの `#tmp_contents` をBeautifulSoupの `html.parser` で
シリアライズし、最小のUTF-8 HTMLに入れた実データです。ナビゲーション等を除外し、
路線別欄と言語選択・履歴リンク・注意事項を保持しています。

`div.line` に南北線・東西線・東豊線、直後の `h2.status` に案内本文があります。
各路線から次の路線まで（最後は共通の履歴案内リストまで）を取り込みます。
確認済み平常文「現在、10分以上の遅れは発生していません。」との完全一致だけを
`NORMAL` とします。追加本文がある場合や他の表示は原文を保持した `UNKNOWN`。
路線別の構造から対象路線を特定し、既存のYahoo共通路線IDを再利用します。
路線の欠損・重複・未知名、状態欄の欠損・空欄は `ParseError` です。

公開スクリプト `st_jsset.js` はメニュー等の表示処理です。インラインの言語選択は
`index_{locale}.html` への遷移で、現在の路線案内はHTML自体に含まれています。
CSSの `.status` は平常文にも付く装飾で、異常を意味するフラグではありません。

公式の掲載基準は10分以上の遅れとその見込みです。`NORMAL` はこの基準での
平常表示であり、あらゆる運行変更がないという意味ではありません。
更新日時・適用時期を確定する専用項目は未確認のため、`updated_at=None`、
`timing=UNKNOWN`、`active_from/active_until=None` を維持します。
本文中の遅延・見合わせ・原因・時刻から分類や現在有効という判断をしません。

## 異常時の調査と限界

公式履歴 https://operationstatus.city.sapporo.jp/unkojoho/rireki_all.html を
直接HTTP取得し、南北線の2026-10-29と東西線の2026-10-07に「遅れ」と
「平常運転」の履歴があることを確認しました。ただし、履歴の「事象」欄は
現在ページの `h2.status` と同じ語彙・形式だと確認できていません。
履歴から現在ページの状態を補完したり、過去の障害を現在の障害として扱いません。

Wayback CDXの旧ドメイン `transitfare.city.sapporo.jp/unkojoho/index.html`
（2024～2025年、HTML、重複digest除外）の照会は空配列でした。
旧・現ドメインの `/unkojoho/*` に広げた照会はHTTP 503でした。
保存された異常時の現在ページ本体は確認できていません。

異常・復旧・未知文言・追加本文・構造破損のテストはすべて**合成データ**です。
実際の異常時マークアップ・日時形式・遅延／運休の状態対応を実証するものではありません。
実応答が確認済みの構造と異なる場合は取得・解析失敗として前回値を保持します。

実行時は日本語の現在ページだけを取得します。履歴、遅延証明書、翻訳、X、
市電、トップページのダイヤ改正等のお知らせは対象外です。現在ページの路線欄に
長期案内を分離する専用構造は確認できていません。路線欄に混在する案内は
本文から除外せず、そのまま保持します。

## 利用条件

- https://www.city.sapporo.jp/city/copyright/link.html
- 上記の現在ページ・履歴ページ

市の著作権方針は私的使用・引用等の法定範囲を留保し、それ以外の複製・転用は
所管課への事前相談を求めています。リンク先の履歴ページにも無許可の使用・転載・
配布・公開を認めない注意があります。確認したURLをメタデータに記録し、
`PERMISSION_REQUIRED` とします。公開表示・再配布の許諾を得たという意味ではありません。
