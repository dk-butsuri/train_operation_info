# JR四国の取得根拠

公式の [列車運行情報](https://www.jr-shikoku.co.jp/info/index.html)、[CSS](https://www.jr-shikoku.co.jp/info/css/style.css)、[JavaScript](https://www.jr-shikoku.co.jp/info/js/jquery.plugins.js) を確認しました。データはHTML内にあり、JavaScriptはスクロール・画面表示の調整のみです。

取得日時、原本・抽出後のSHA-256、保存URLとUTC保存時刻は [jrshikoku_manifest.json](jrshikoku_manifest.json) に記録しています。fixtureはBeautifulSoupの`html.parser`で `.delay_status`、`.mapbase`、`.delay_info` を抽出・再シリアライズしたUTF-8のHTMLです。見出し、状態、日時、本文の書き換えはありません。

| fixture | 確認した表示 |
| --- | --- |
| `jrshikoku_normal.html` | 2026-11-02のライブ取得。現在、遅れ等の情報はありません。 |
| `jrshikoku_20250216210138.html` | 瀬戸大橋線の列車運休。地図は瀬戸大橋線が点灯。 |
| `jrshikoku_20260712052626.html` | 予土線の一部区間運休・代行輸送。地図は予土線が点灯。 |
| `jrshikoku_20240621132151.html` | 翌日の強風に関する事前案内。路線名のない見出し、地図点灯なし。 |
| `jrshikoku_20260116145742.html` | 予讃線の日中集中工事の事前案内。地図点灯なし。 |

地図の点灯は対象区間を表し、遅延・運転見合わせ・一部運休を区別しません。概要の「遅れまたは運転を見合わせている区間があります」も複数状態を含むため、`ALERT` と原文を返します。本文中の語句から運休を推定しません。見出しが路線名を持つ場合はその路線に紐付け、同一路線内に点灯区間があればその区間に絞ります。予讃線・土讃線の見出しだけで区間が特定できない場合は両区間に紐付けます。路線名のない見出しは影響対象不明の `affected_line_ids=()` として保持します。

通常表示には更新日時がありません。各案内の更新時刻には日本時間を付けます。取得時刻を更新日時として代用しません。掲載基準は概ね30分以上の遅れ・運休（見込みを含む）です。注意事項欄の固定案内やリンク先PDFは対象外です。

純粋な遅延だけの保存ページ、同じ障害の実際の復旧ページは未確認です。後日の通常表示への更新で古いアラートの消去を検証しています。未知の表示・構造破損・通信障害・複数案内のテストは実fixtureを加工した合成データとして明記しています。

利用条件は2026-11-02に [公式規約ページ](https://www.jr-shikoku.co.jp/site_policy/index.shtm) とリンク先の [利用規約PDF](https://www.jr-shikoku.co.jp/site_policy/jrshikoku_sitepolicy.pdf) 第1項を確認し、無断の複製・転記・配布等を制限する記載から `PERMISSION_REQUIRED` と記録しています。
