# とさでん交通（路面電車）

2026-11-02 UTCに公式の[電車運行状況](https://www.tosaden.co.jp/info/service.php?ID=1)、
[共通JavaScript](https://www.tosaden.co.jp/ssi/js/fn.js)、
[サイトポリシー](https://www.tosaden.co.jp/info/sitepolicy.php)を取得して確認した。
本文はHTMLの `#main_body` に直接含まれる。JavaScriptはナビゲーションと
スライダーを扱い、別の運行情報APIは参照しない。

fixtureは公式原本から `h2.tit_train` と `#main_a` をBeautifulSoupの
`html.parser` で抽出し、UTF-8の宣言と末尾改行を付けて保存した。
本文・見出し・路線名の改変はない。過去の原本はEUC-JP、現行原本はUTF-8。
原本にはXML宣言とHTMLのcharsetの食い違いがあるため、バイト列からの
文字コード判定もテストしている。抽出スクリプトは `reports/extract_tosaden.py`。
URL、UTC取得時刻、原本と加工後のSHA-256は
[tosaden_manifest.json](tosaden_manifest.json) に記録した。

| fixture | 出典・保存時刻（UTC） | 確認内容 |
| --- | --- | --- |
| `tosaden_normal.html` | ライブ取得（manifestに取得時刻） | 30分以上の遅れなし。英訳と電話番号あり |
| `tosaden_20220918071853.html` | [2022-09-18 07:18:53](https://web.archive.org/web/20220918071853id_/https://www.tosaden.co.jp/info/service.php?ID=1) | 台風14号。翌日の全線終日運休予告と翌々日の条件付き運行再開。通常の主見出し・利用条件欄も置き換わる |
| `tosaden_20230602090407.html` | [2023-06-02 09:04:07](https://web.archive.org/web/20230602090407id_/https://www.tosaden.co.jp/info/service.php?ID=1) | 日本語のみの平常定型文 |

平常の主見出しと、確認した日本語・英訳・電話番号を含む本文全体が一致する場合のみ
`NORMAL`。平常文に別の案内が混在する場合は `UNKNOWN` として本文を保持する。
それ以外の案内は原文付き `ALERT`。状態コードがないため、本文の「運休」「遅れ」だけで
`SUSPENDED`・`PARTIAL_SUSPENSION`・`DELAYED` に分類しない。
欠損・重複・空欄・別サービスのページは `ParseError`、通信失敗も前回の結果を保持する。

共通路線IDはYahoo 598/0の `jp:operator_74ae511377a2:line_d1d5a8a2e706` を再利用する。
公式の掲載単位は路面電車全体であり、後免線・伊野線・桟橋線には分割しない。
Yahooとは別のインスタンス・取得結果を持つ。

掲載基準は30分以上の遅れ、またはその見込み。`NORMAL` は主本文のこの基準の表示を意味する。
**別枠の「運行についてのお知らせ」とリンク先記事は取得対象外**。ここにはキャラクター電車、
車両単位の長期運休、ダイヤ変更等も掲載される。平常の主本文だけではそれらの有無を保証できない。
fixtureには範囲を確認できるようにこの別枠も残しているが、ニュースの日付は主本文の更新日時には使わない。
バス、時刻表、車両位置、ハートラム等の特定車両の運休日も対象外。

主本文には独立した更新日時・適用期間・継続期間の項目がないため `updated_at=None`。
日付の年を確定できず、将来予告と条件付き再開が混在する案内もある。
`timing` は `UNKNOWN`、適用期間の開始・終了は `None` とし、原文を保持する。
未確認の文章を分類するために共通の日本語推論器を適用しない。

独立した遅延・一部運休の実HTML、現在の異常時HTML、同一障害の復旧は未確認。
アラート消去は別時点の平常fixtureで検証する。未知文言・構造破損・通信失敗・
文字コードの再符号化は合成テストであり、新しい障害の実データではない。
HTTP保存・再生テストも既存fixtureを用いたもので、ライブ取得の証拠とは区別する。

一般サイトポリシーはリンク条件を記載する。一方、運行状況ページには無断の転記・複写・
磁気媒体への加工を禁じる記載があるため、メタデータを `PERMISSION_REQUIRED` とした。
