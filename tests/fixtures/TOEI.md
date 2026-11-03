# 都営地下鉄

2026-11-02に公式の公開HTML・JavaScriptと、公式ページのテキスト表示を調査。
取得できた原本のURL・UTC取得日時・SHA-256・抽出内容は
[toei_manifest.json](toei_manifest.json) に記録しています。

## 現在の運行情報

- https://www.kotsu.metro.tokyo.jp/subway/schedule/index.html
- https://www.kotsu.metro.tokyo.jp/common/scripts/main.js?v=2026101901

`toei_normal.html` はライブ取得HTMLの `#js-operationInfo` と `#main-body`
をBeautifulSoupでシリアライズして最小HTMLに入れた実データです。
広告・ナビゲーション等は除外し、運行情報・ご留意事項を保持しています。
4路線の本文は「現在、１５分以上の遅延はありません。」、要約は「平常運行」。
路線名・クラス・履歴リンクを照合し、Yahooと既存の共通路線IDを共有します。
取得対象は地下鉄4路線のみです。

スクリプトの `co()` は現在ページのHEAD応答の `Date`、`lo()` はその時刻を
`Asia/Tokyo` に変換して `js-currentTime` に表示します。障害の更新時刻では
ないため、HTTP Date・表示時計・取得時刻を `updated_at` には使用しません。
別の運行情報JSONを取得する処理は確認できませんでした。

## 異常時の根拠と限界

公式履歴のテキスト表示をWebツールで確認しました。以下は確認内容の要約で、
履歴HTMLの保存fixtureではありません。直接HTTP取得では履歴ページに
IncapsulaのHTMLが返ったため、原本HTMLのハッシュは取得できていません。

| URL | 確認した配信時刻（日本時間）と状態 |
| --- | --- |
| https://www.kotsu.metro.tokyo.jp/subway/schedule/mita_log.html | 2026-10-29 08:43「ダイヤ乱れ」（目黒駅のホームドア点検）、09:21「平常運行」 |
| https://www.kotsu.metro.tokyo.jp/subway/schedule/asakusa_log.html | 2026-10-28 22:39「ダイヤ乱れ」（京急線内の混雑・振替輸送）、翌01:06「平常運行」 |
| https://www.kotsu.metro.tokyo.jp/subway/schedule/oedo_log.html | 2026-10-29 08:17「ダイヤ乱れ」（青山一丁目駅のドア点検）、10:40「平常運行」 |
| https://www.kotsu.metro.tokyo.jp/subway/schedule/shinjuku_log.html | 過去7日間に履歴なし |

「ダイヤ乱れ」は `ALERT` とし、本文中の過去の運転見合わせ・直通中止等から
全線の遅延・運休を推測しません。未確認ラベルは本文を保持した `UNKNOWN`。
平常要約と本文の不一致も `UNKNOWN`。欠損・重複・想定外の路線は
`ParseError` とし、直前の完全なスナップショットを保持します。

Wayback CDXで保存時刻を調べましたが、次の保存URLはHTTP 429でした。
保存本体は確認できていません。

- https://web.archive.org/web/20260520185019id_/https://www.kotsu.metro.tokyo.jp/subway/schedule/index.html
- https://web.archive.org/web/20260304132314id_/https://www.kotsu.metro.tokyo.jp/subway/schedule/index.html

現在ページの異常時HTML・独立した運転見合わせ/一部運休のラベル・配信日時の
マークアップは未確認です。異常時・復旧・未知状態・構造欠損のパーサーテストは
実際の正常HTMLを書き換えた**合成テスト**です。公式履歴の同一事象の復旧を
確認したことと、その時点の現在ページを保存・再現したことを区別しています。
テスト中の「運転見合わせ」は未知ラベルの合成例で、確認済みコードではありません。
履歴・遅延証明書・列車位置・リンク先・都電・ライナーは実行時に取得しません。

## 利用条件

https://www.kotsu.metro.tokyo.jp/riyo/ をWebツールで確認しました。
一般ポリシーは私的使用・引用等の法定利用を留保し、無断複製・転用を制限します。
さらに運行情報ページ固有のご留意事項は、無断転載・複写・体裁を変更した
ホームページ公開を禁止しています。両方をメタデータに記録し、
`PERMISSION_REQUIRED` としています。公開サイネージ利用の許諾ではありません。
掲載基準は15分以上の遅れまたはその見込みで、`NORMAL` はこの基準の平常表示です。
