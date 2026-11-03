# 京都市営地下鉄

2026-11-03 UTCに公式HTML・JavaScriptとWaybackの保存HTMLを取得しました。
URL、UTC取得日時、原本SHA-256、fixture SHA-256は
[kyoto_subway_manifest.json](kyoto_subway_manifest.json) に記録しています。
fixtureは無加工の応答全体で、第三者コンテンツとしてGitには含めません。

## 取得範囲と判定根拠

- 人向け・実行時の取得先：https://www.city.kyoto.lg.jp/kotsu/
- 公開方法の説明：https://www.city.kyoto.lg.jp/kotsu/category/166-0-0-0-0-0-0-0-0-0.html
- 表示JavaScript：https://www.city.kyoto.lg.jp/main/css/img/onload_ku_top.js?20260729
- 利用条件：https://www.city.kyoto.lg.jp/main/site_policy/0000000005.html

地下鉄カテゴリは、ダイヤの乱れ等をトップページ最上部の緊急情報欄に掲載すると説明しています。
対象欄は `#main` 直下の `▼▼緊急情報▼▼` / `▲▲緊急情報▲▲` コメントで区切られます。
現在のHTMLには両コメントがあり、その間は空です。確認した `onload_ku_top.js` に別状態取得処理はありません。
`#main_lower` 以下の通常のお知らせ・臨時便・設備工事等は取得対象外です。
HTTP応答の記録にはそれらも含まれますが、解析・状態判定には利用しません。

| fixture | 原本の保存時刻（UTC） | 確認内容 |
| --- | --- | --- |
| `kyoto_subway_normal.html` | 2026-11-03T15:57:53.749704Z（ライブ取得） | 緊急情報のマーカー間が空 |
| `kyoto_subway_notice_20230815040858.html` | 2023-08-15T04:08:58Z | `#imp.imp_kinkyu` に直通運転・市バス・災害の複数案内 |
| `kyoto_subway_cleared_20230816075536.html` | 2023-08-16T07:55:36Z | `#imp .imp_lower` の明示的な案内なし表示 |

保存URL：

- https://web.archive.org/web/20230815040858id_/https://www.city.kyoto.lg.jp/kotsu/
- https://web.archive.org/web/20230816075536id_/https://www.city.kyoto.lg.jp/kotsu/
- https://web.archive.org/web/20240827141354id_/https://www.city.kyoto.lg.jp/kotsu/
- https://web.archive.org/web/20250802110421id_/https://www.city.kyoto.lg.jp/kotsu/
- https://web.archive.org/web/20251031085732id_/https://www.city.kyoto.lg.jp/kotsu/

最後の3保存もマーカー間が空で、現在の空欄と同じ構造です。
翌日の保存は同じ欄から案内が消える例であり、個別路線の障害・復旧時刻を証明するものではありません。
検索で見つかった直通中止記事 `/kotsu/page/0000342820.html` は直接取得では404で、fixtureに採用していません。

## 共通モデルへの対応と限界

- マーカー間が空、または保存HTMLで確認した完全な案内なし文に一致する場合だけ `NORMAL`。
  これは緊急情報欄に掲載がないという意味で、全線の平常運転や別枠の案内の不存在を保証しません。
- 緊急情報ありは `UNKNOWN`。地下鉄以外の案内も同じ欄に混在し、路線・影響の専用項目がありません。
  本文の路線名や運休等の語句から対象・状態を推測せず、`affected_line_ids=()` を保持します。
- 欄内の本文とリンク先URLを一つの案内として両路線に保持し、Provider/Trackerでは共通alert IDで一件に集約。
  リンク先の記事本文、市バス接近情報、別のお知らせ一覧、長期案内、時刻表、遅延証明書は取得しません。
- 年のない日付見出しから日時を作りません。`updated_at=None`、`timing=UNKNOWN`、
  `active_from=None`、`active_until=None`。個別路線の遅延・運休・適用期間は未確認です。
- 京都市交通局と烏丸線・東西線の共通IDはYahoo登録済みのものを再利用し、スナップショットは独立。
- コメントの欠損・重複・順序異常、本文・必須構造の欠損は `ParseError`。失敗時は前回状態を保持します。
- 私的複製・引用等の法定範囲以外の無断複製・転用を制限する市の規約から、メタデータは
  `PERMISSION_REQUIRED`。公開運行データとしての別の利用許諾は確認できませんでした。

保存した実データで掲載あり→明示的掲載なし→現在の空欄を検証します。
本文の否定・予告・復旧・バス限定案内、未知の表示、欠損・重複・不正リンク・HTTP失敗は
明示的な合成テストです。これらは実際の異常時形式や種別の根拠としては扱いません。
