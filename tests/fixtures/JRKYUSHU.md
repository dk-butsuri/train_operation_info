# JR九州 調査・取得範囲

2026-11-03 JSTに公開HTML・JavaScriptとライブ応答を調査。
個々の取得日時（UTC）、URL、取得方法、原本とfixtureのSHA-256は
[jrkyushu_manifest.json](jrkyushu_manifest.json)に記録した。
fixtureはHTTP応答本文のバイト列を無加工で保存している。

## 公式ソースと判定

- 人向けページ: https://www.jrkyushu.co.jp/trains/info/
- 表示ロジック: https://www.jrkyushu.co.jp/trains/info/js/script.js
- XML: https://www.jrkyushu.co.jp/trains/info/data/IDS2Web.xml
- 長期見合わせフラグ: 同じdata/配下の
  fukhok.txt / oita.txt / sagnag.txt / kuma.txt / miya.txt / kago.txt / shin.txt / nishi.txt
- 別枠の注意事項: https://www.jrkyushu.co.jp/trains/info/inc/info_mid.html

script.jsの`viewData()`は`aif/nm`を8エリアに対応付け、`sts=1`なら
「遅れ等が発生しています。」と`eif/time`・`eif/txt`を表示する。
専用の路線ID、遅延／運休の内訳や適用時期はないため`ALERT`とし、
自由記述から`DELAYED`・`SUSPENDED`・`ACTIVE`を導出しない。

`readLongtermFlgFile()`は各テキストの先頭1文字を読み、空ファイルは`0`とする。
`1`の意味は「長期の運転見合わせ区間があります。」で、地域全体の運休ではない。
フラグはXMLと別ファイルに構造的に分離された長期案内であるため、
全Provider共通の方針（構造的に分離された長期案内は対象外）に従い、
実行時には取得・検証しない。`sts=0`を取得範囲内の`NORMAL`とし、
長期の運転見合わせ区間がないことは保証しない。
調査時の実XMLは全8エリア`sts=0`、熊本・鹿児島の実フラグは`1`だった
（フラグのfixtureは調査記録として保存している）。

未知の状態は原文付き`UNKNOWN`。
必須構造の欠損・重複、未知／欠損エリア、壊れた日時、状態と案内有無の矛盾、
XML取得失敗は8掲載単位全体の前回値を保持する。
`all`属性、`map`、XMLルートの`time`は状態・案内更新時刻の根拠には使わない。

## 共通IDと対象

以下はいずれも既存カタログに同じ範囲の定義がなく、新規追加した。
接頭辞はすべて`jp:jr_kyushu:`。Yahoo登録済みの個別在来線と範囲が異なるため、
そのIDをエリアの別名として再利用しない。運行会社は同じ既存Operatorを参照する。

| XML nm | 公開プロパティ | 共通IDの末尾 | scope |
| --- | --- | --- | --- |
| Fukuoka-Kitakyushu | fukuoka_kitakyushu | fukuoka_kitakyushu_group | GROUP |
| Oita | oita | oita_group | GROUP |
| Saga-Nagasaki | saga_nagasaki | saga_nagasaki_group | GROUP |
| Kumamoto | kumamoto | kumamoto_group | GROUP |
| Miyazaki | miyazaki | miyazaki_group | GROUP |
| Kagoshima | kagoshima | kagoshima_group | GROUP |
| Kyushu-Shinkansen | kyushu_shinkansen | kyushu_shinkansen | LINE |
| Nishi-Kyushu-Shinkansen | nishi_kyushu_shinkansen | nishi_kyushu_shinkansen | LINE |

在来線エリアは掲載単位であり、所属路線の障害を意味しない。
本文の路線名を照合して対象を推測せず、`affected_line_ids=()`とする。
新幹線2パネルは単一路線を特定しているため、その共通IDを設定する。
新幹線についても運休範囲や列車の区別は行わない。

## 日時・対象外

`cnvtDateStr()`は`eif/time`の先頭12桁を年月日時分として表示する。
12桁／14桁のコンパクト形式を検証し、表示と同じ分精度・日本時間として扱う。
14桁の末尾2桁の意味は未確認のため、秒の精度を付加しない。
`updated_at`はそのパネルのXML案内の最大更新日時のみ。
ルートXML時刻、端末の現在時刻では代用しない。
`timing=UNKNOWN`、`active_from=active_until=None`。

別枠の`inc/info_top.html`・`inc/info_mid.html`、工事／災害のリンク先やPDF、
画像地図・`IDS2IMG.xml`、列車位置、遅延証明書は取得対象外。
`NORMAL`はそれらを含む全情報で運休がないことを保証しない。
実行時の取得先はXMLの1件のみ。
保存応答の取得時、User-Agentなしのurllib取得は403、`Mozilla/5.0`では200だった。
Providerはブラウザを装わず、共通の`USER_AGENT`で名乗る。拒否された場合は`FetchError`とし、回避しない。

## 利用条件の確認範囲

運行情報ページと`inc/info_mid.html`には免責と、複数列車に15分を超える
遅れが見込まれる場合等の掲載基準がある。一般の再利用条件は確認できなかった。
公式トップ・鉄道トップのフッター、以下の公式ページと検索結果も確認した。

- https://www.jrkyushu.co.jp/privacy/rule/index.html : 個人情報の取扱い
- https://www.jrkyushu.co.jp/social/ : リンク・ソーシャルメディア一覧
- https://www.jrkyushu.co.jp/jq/privacy/ : JQ CARDホームページの条件
- https://www.jrkyushu.co.jp/point/rules/webmemberkiyaku_iframe.html : Web会員サービスの条件
- https://www.jrkyushu.co.jp/trainnavi/policy/japanese.pdf : 別サービスのトレインナビ規約へのリンク

他サービスの規約をこのXMLへ拡張して適用しない。
一般の利用規約は`terms_url=None`、運行情報注意事項を`additional_terms_urls`に記録し、
`usage_permission=UNSPECIFIED`とする。これは利用許諾を確認したという意味ではない。

## 実証範囲と合成テスト

CDXで`www.jrkyushu.co.jp/trains/info/data/IDS2Web.xml`のHTTP 200保存を照会したが、
応答は空だった。ライブXMLに`eif`はなく、実障害／同一障害の復旧は未確認。
異常時の`eif/txt`・`eif/time`は公式JavaScriptから読み方を確認した。
日時の入力形式、複数案内、予告・否定・復旧文言、未知コード、破損、通信失敗、
案内消去のテストは、実XMLを変更した**合成データ**であり、
実際の障害を再現した証拠ではない。
記録・再生テストも新たな実サイト取得の証拠ではない。
