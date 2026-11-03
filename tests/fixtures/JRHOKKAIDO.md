# JR北海道 調査・取得範囲

2026-11-02/03 JSTに公開JSON・JavaScriptとライブ応答を調査。
個々の取得日時（UTC）、URL、取得方法、原本とfixtureのSHA-256は
[jrhokkaido_manifest.json](jrhokkaido_manifest.json)に記録した。
fixtureはHTTP応答本文のバイト列を無加工で保存している（UTF-8 BOM付き）。

## 公式ソースと判定

- 人向けページ: https://www3.jrhokkaido.co.jp/webunkou/index.html
- 利用上の注意（トップページ組込み）: https://www3.jrhokkaido.co.jp/webunkou/call_goriyo.html
- 表示ロジック: js/top.js、js/common_area_operation.js、js/area.js、
  js/common_area_senku.js、js/senku.js、js/senku_information_display.js
- 掲載単位の名称一覧: json/master/senku_name_master.json
- 実行時に取得するJSON: json/area/area_02.json（道央）、area_03.json（道南）、
  area_04.json（道北）、area_05.json（道東）

`common_area_operation.js`の`getIconImgElement()`と`OPERATION_STATUS_*_REMARKS`が
状態コードの唯一の根拠である。`0`は「運休・遅延に関する情報なし」で`NORMAL`、
`1`は「運休・３０分以上の遅延・運転見合わせが発生」で区別できないため`ALERT`、
それ以外（ライブ応答では`2`）は「サービス時間外」で`UNKNOWN`とする。
`call_goriyo.html`はサービス提供時間を5:00〜24:00と明記しており、`2`の意味と一致する。
本文からの状態推測は行わない。

## 掲載単位（線区）と共通IDの対応

`common_area_senku.js`の`load_senku_name_json()`・`getSenkuIconImgElement()`が、
線区コード（01〜24、18は欠番）を`senkuStatus`のフィールド名に対応付けている。
各`area_XX.json`は固定の16キー（express/airport/hakochise/hakodateLiner/
hakodate/gakuen/sekisho/muroran/nemuro/hidaka/soya/sekihoku/furano/rumoi/
senmo/hanasaki）を常に持つが、そのエリア自身の線区以外のキーは無関係な
既定値（観測範囲では`0`）である。2026-11-03のライブ比較で道央(area_02)・
道南(area_03)・道北(area_04)・道東(area_05)の値がエリアごとに異なること
（area_04だけが`soya`・`express`で`1`を示す）を確認し、area_01（札幌近郊）と
area_02（道央）は共有する4フィールド（express/airport/hakochise/gakuen。
線区01-04と05-08は`common_area_senku.js`上で同じ掲載＝同一の物理サービス）で
常に同値であることも確認した。このためarea_01は取得せず、area_02のみで
spo/doo共有分をカバーする。

`senku_name_master.json`の`name.ja`により、以下8線区は既存カタログの単一物理路線と
一致することを確認し、そのLineIdを再利用した（`LineScope.LINE`）。

| 線区ID | name.ja | フィールド | 既存LineId |
| --- | --- | --- | --- |
| 04/08 | 学園都市線 | gakuen | jp:jr_hokkaido:line_1b3f7157a97f |
| 10 | 日高線 | hidaka | jp:jr_hokkaido:line_d2d4151ea5a8 |
| 15 | 宗谷線 | soya | jp:jr_hokkaido:line_d3463a409618 |
| 16 | 石北線 | sekihoku | jp:jr_hokkaido:line_903b6ae2bcf1 |
| 17 | 富良野線 | furano | jp:jr_hokkaido:line_ea3437497425 |
| 20 | 石勝線 | sekisho | jp:jr_hokkaido:line_6664f6717ccf |
| 22 | 根室線（花咲線） | hanasaki | jp:jr_hokkaido:line_0ec04639e5c5 |
| 23 | 釧網線 | senmo | jp:jr_hokkaido:line_e15dbba9f742 |

以下6線区は、公式の掲載単位が既存カタログの分割区間（千歳線・函館本線の5区間・
室蘭本線の2区間・根室本線の2区間）のどれよりも広い範囲を指すか、対応する区間を
裏付ける資料（駅一覧や影響エリア地図のSVG）が確認できなかったため、
`providers/jrkyushu`のエリア掲載単位と同様に新規GROUP IDを追加し、
既存の分割区間へのエイリアスにはしていない。

| 線区ID | name.ja | フィールド | 新規LineId |
| --- | --- | --- | --- |
| 02/06 | エアポート | airport | jp:jr_hokkaido:airport_group |
| 03/07 | 函館・千歳線 | hakochise | jp:jr_hokkaido:hakodate_chitose_group |
| 09 | 室蘭線 | muroran | jp:jr_hokkaido:muroran_group |
| 12 | はこだてライナー | hakodateLiner | jp:jr_hokkaido:hakodate_liner_group |
| 13 | 函館線 | hakodate | jp:jr_hokkaido:hakodate_line_group |
| 21 | 根室線 | nemuro | jp:jr_hokkaido:nemuro_group |

対象外（取得・検証しない）:

- 線区01/05/11/14/19「特急列車」（フィールド`express`）: エリアごとに異なる値を持つ
  列車種別単位の状態で、カタログの物理路線に対応しない。JR東日本が特急列車を
  対象外とする方針に合わせる。
- 線区24「北海道新幹線」（`areaStatus.shin`）: `area_06.json`は存在せず
  （ライブ確認では公式404相当ページが返る）、共通カタログにも路線がないため対象外。
- `senkuStatus.rumoi`: 現在どの線区IDにも対応しない既定フィールド（旧留萌本線の
  名残と推測されるが未確認）で、構造検証のみ行い値は使わない。
- 道南いさりび鉄道との直通列車は`call_goriyo.html`に明記された対象外。

## 本文・更新日時・適用時期

`data.today`のみを解析する。`data.tomorrow`（翌日予報）は構造検証のみ行い、
現在状態だけを扱う本ライブラリの方針により使用しない。

トップレベルの`time`はJR東日本の地域ページと同様「現在」で終わる表示用の値で、
配信時刻の根拠にしない。各`gaikyo`項目自身の`time`
（例: `2026年11月02日 15時39分現在`、道北エリアの実際の宗谷線運休で確認）は
個別の案内に紐付く時刻であり、`updated_at`の根拠とする。案内が存在しない場合に
常に現れる既定項目（`{"time": "", "title": "", "honbun": "現在、遅れに関する
情報はありません。"}`）はアラートとして採用しない。線区の状態コードが`1`で、
かつ`gaikyo`にその線区の所属エリアで`eikyo.<area>=1`かつ`title`が空でない項目が
あれば、その本文・見出し・時刻を採用する。一致する項目がなければ
`OPERATION_STATUS_1_REMARKS`の固定文言のみを使い、`updated_at`は`None`のままとする。
`areaComments`は`comment`フィールドのみ検証する。実際に取得した全応答
（本ライブラリの合成テストを含む）で常に空配列であり、要素の全体像は未確認である。

長期案内が別ファイル・別欄に構造的に分離されている根拠は見つからなかった
（JR九州・JR西日本と異なる）。`NORMAL`はここで読んでいる欄に案内がないことだけを
示し、他欄に掲載された長期の運転見合わせがないことは保証しない。
`timing`は常に`UNKNOWN`、`active_from`・`active_until`は常に`None`。
適用期間の専用項目は確認できていない。

## 実証範囲と合成テスト

2026-11-02/03 JSTにarea_02・03・04・05を取得した。area_02（道央）・area_03（道南）・
area_05（道東）は全線区`NORMAL`だった。area_04（道北）では`soya=1`が
`today`・`tomorrow`の両方で観測され、2026-10-30に宗谷線
音威子府～稚内駅間で発生した列車とクマの衝突による実際の終日運転見合わせを
示す本文を取得できた（`jrhokkaido_area_04.json`に保存）。
これが本Providerで確認できた唯一の実障害である。

他の13掲載単位（学園都市線・日高線・エアポート・函館・千歳線・室蘭線・
はこだてライナー・函館線・石北線・富良野線・石勝線・根室線・花咲線・釧網線）の
ALERT、および全掲載単位のUNKNOWN（状態コード2）・復旧・構造欠損・通信失敗は、
実データ（area_02〜05.json）を変更した**合成データ**であり、実際の障害を
再現した証拠ではない。記録・再生テストも新たな実サイト取得の証拠ではない。

## 利用条件の確認範囲

- 一般利用規約: https://www.jrhokkaido.co.jp/other/goriyou.html
  （著作権は当社に帰属し、無断の複製・改変等を禁じる旨の記載）
- 運行情報固有の注意事項: https://www3.jrhokkaido.co.jp/webunkou/call_goriyo.html
  （概ね30分以上の遅延・運休を掲載基準とし、提供時間5:00〜24:00、
  道南いさりび鉄道の直通列車は対象外、無断転載・複写・電磁媒体等への加工を禁じる旨の記載）

両方に無断転載・複製を禁じる明示的な記載があるため、利用条件メタデータは
`PERMISSION_REQUIRED`とする。
