# 名古屋市営地下鉄

調査方法は公開HTML・JavaScriptの逆解析と平常時JSONのライブ取得。
2026-11-03 UTC（日本時間11月4日）にライブラリのUser-Agentを名乗り、
httpxで取得した。各URL、UTC取得完了時刻、無加工の原本／fixtureのSHA-256は
[nagoya_subway_manifest.json](nagoya_subway_manifest.json)に記録している。
原本の著作物はGitに含めない。JSONのUTF-8 BOMも保存したままである。

## 根拠と適用範囲

- [公式ページ](https://www.kotsu.city.nagoya.jp/rp/emergency/)が読み込む
  [traffic_info_for_top.js](https://www.kotsu.city.nagoya.jp/rp/Jassets/js/common/traffic_info_for_top.js)
  の `LatestTrafficStore` は
  [latest_traffic.json](https://www.kotsu.city.nagoya.jp/datas/latest_traffic.json) を取得する。
- `JSITE.colors` は `N_T_ICO` / `W_T_ICO` / `C_T_ICO` / `E_T_ICO` を
  normal / delay / caution / suspended のCSSクラスに対応させる。
  この専用コードから `NORMAL` / `DELAYED` / `ALERT` / `SUSPENDED` とする。
  `C_T_ICO` の具体的影響や部分運休は確認できないため補完しない。
- `UpdateTrafficInfoForTopSp` は `N_T_ICO` でも `traffic_title` が
  `平常運行` 以外なら「お知らせあり」とする。この場合は `ALERT`。
  未知コードは `UNKNOWN`、空コード・空タイトルは構造不備とする。
  本文・原因・区間・日付による推定はしない。
- `UpdateTrafficInfoForDetail` は `rosen_id` ごとに全スロットを列挙し、
  `traffic_title`、`traffic_message`、`traffic_section`、`traffic_cause` を表示する。
  空文字・JSON null・文字列 `null` は表示しない。非平常の全スロットをアラートに保持し、
  同じ路線の平常項目で障害を消さない。共通の `combined_status` で集約する。
- [emergency.js](https://www.kotsu.city.nagoya.jp/rp/Jassets/js/emergency/emergency.js)
  の `ConvRosenName` は `H`=東山線、`M`=名城線・名港線、`T`=鶴舞線、
  `S`=桜通線、`K`=上飯田線。名城線・名港線の見た目は分離されていてもJSONは
  一つの `M_LINE`。Yahooで既存の5共通IDと同じ範囲であり、既存ID・会社情報を再利用する。
  部分区間の案内を各路線全体の個別運休へ展開しない。
- `B_LINE`（市バス）の内容は対象外。HTTP保存には同じ応答中の市バスも含まれる。
  長期案内を分ける専用フィールドは確認できず、同じ路線の案内を本文で除外しない。
- `create_datetime` はオフセットのない掲載時刻。路線の更新日時としての意味は
  未確認のため `updated_at=None`。[common.js](https://www.kotsu.city.nagoya.jp/rp/Jassets/js/common/common.js)
  の `GetDateStringYMDHM` は文字列を分割して表示するだけである。
  ページの画面表示日時はブラウザの現在時刻で、更新時刻として使わない。
  現在有効を確定する専用フラグや適用期間も未確認なので `timing=UNKNOWN`、適用期間はNone。
- 公式ページは10分以上の遅延が見込まれる場合等に情報提供すると記載する。
  `NORMAL` はこの公開範囲内での平常である。

## 未確認・合成テスト

このJSON URLのWayback CDX照会（manifestに完全URLあり）はHTTP 200、空配列だった。
ライブJSONは5系統すべて平常であり、実際の異常・復旧JSONは未取得。
公開コードで状態対応と複数スロットの表示方法は確認したが、異常時の文章は一般化していない。
遅延・停止・注意・復旧・未来／否定文・未知コード・複数案内・破損応答のテストは合成である。
`test_live_normal_fixture_with_utf8_bom` と全ProviderのHTTP保存再生テストはライブ原本を使う。

## 利用条件

[ご利用にあたって](https://www.kotsu.city.nagoya.jp/rp/WEBSITE/trp0000834.htm) は
許可のない転載・複製を禁止し、運行情報ページのフッターにも無断使用・転載の禁止がある。
JSONの再利用を許す個別条件は見つからず、メタデータは `PERMISSION_REQUIRED` とする。
通信できたことを利用許諾とは扱わない。
