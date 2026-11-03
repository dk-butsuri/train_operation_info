# 小田急公式の運行情報

調査日は2026-11-03 JST（2026-11-02 UTC）。公開HTML・JavaScriptの逆解析と、Waybackの公式API保存応答の両方を使用した。

- 人向けページ: https://traininfo.odakyu-rt.jp/train_status
- 公開アプリ: https://traininfo.odakyu-rt.jp/assets/index-yuMM9dEt.js
- API: https://d6oynijiy33tb.cloudfront.net/service/status_detail
- サイト利用条件: https://www.odakyu.jp/policy/

`odakyu_manifest.json` に原本URL、取得時刻、原本SHA-256、fixture名、加工方法を記録した。API応答は無加工。`odakyu_app_excerpt.js` はAxios設定から1箇所と、`JP`から`Ef`までの連続した公開コードをそのまま抽出したもの。全文の原本ハッシュもmanifestに記録した。公開ブラウザー用のAPIヘッダーはこの設定から取得する。個人の認証情報は使わない。

## 状態・対象の根拠

公式の `JP` コンポーネントは `influence_block_state` を次の範囲で分ける。

| 区間番号 | 路線 | 既存の共通ID |
| --- | --- | --- |
| 1–17 | 小田原線 | `jp:odakyu:line_fbb4645c43db` |
| 18–23 | 江ノ島線 | `jp:odakyu:line_5f3c44bd632d` |
| 24–26 | 多摩線 | `jp:odakyu:line_cf199b49d179` |

27–28は3路線カードの対象外。上下いずれかが2なら「運休」、該当する区間数が路線内の全区間数未満なら「一部運休」。1なら「遅延」。0なら平常運転。空の区間配列もカード上は平常表示である。未知の値を平常に丸める公式表示は踏襲せずUNKNOWNとして原値を残す。非空配列の区間欠損・重複はParseError。

| 保存時刻（UTC） | 保存URL | 確認した内容 |
| --- | --- | --- |
| 2025-07-10 07:14:11 | https://web.archive.org/web/20250710071411id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 案内なし、空配列 |
| 2025-07-30 09:07:50 | https://web.archive.org/web/20250730090750id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 江ノ島線の区間23が2、津波警報による一部運休 |
| 2025-10-22 12:16:02 | https://web.archive.org/web/20251022121602id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 案内なし |
| 2025-11-24 01:20:21 | https://web.archive.org/web/20251124012021id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 小田原線の一部運休、他区間・他路線の遅延 |
| 2025-11-26 03:31:18 | https://web.archive.org/web/20251126033118id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 江ノ島線の一部運休、他2路線の平常カード |
| 2026-01-28 23:46:09 | https://web.archive.org/web/20260128234609id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 小田原線の遅延、特急・直通運転案内 |
| 2026-07-28 13:40:22 | https://web.archive.org/web/20260728134022id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 小田原・江ノ島線の下り方向の遅延、多摩線の平常 |
| 2026-10-14 20:00:25 | https://web.archive.org/web/20261014200025id_/https://d6oynijiy33tb.cloudfront.net/service/status_detail | 案内なし、復旧後の差し替え検証に使用 |

区間状態による路線状態のほか、`hp_influence_status_odawara/enoshima/tama` が空でなければ当該路線の案内として保存する。専用状態で分類できない本文はALERT。自由記述の単語による運休・遅延分類はしない。`hp_status`・原因・振替・備考を原文で保存する。特急本文・`hp_influence_status_whole`・千代田線直通フラグは対象路線を確定せず `affected_line_ids=()` の案内にする。路線の障害が特定できない全体案内も同様。対象未特定の案内がある平常カードはUNKNOWN。

## 日時・適用範囲・未確認事項

`train_service_status_detail.update_time` は運行案内の更新時刻で、保存応答のISO 8601 UTC値を使用する。案内なしの場合はNone。`Ef`が画面冒頭に表示する時計はブラウザーの`new Date()`であり更新時刻ではない。発生時刻を適用開始時刻に変換しない。`timing`はUNKNOWNを維持する。全区間の停止、メンテナンス状態21/22、未知コード、予告・否定文のテストは合成であり、実保存障害の証拠ではない。掲載終了時にアラートが消えることを異なる時刻の保存応答による差し替えで検証するが、同一障害の連続記録ではない。

取得範囲は3路線の運行カードと関連する運行案内。`news_latest`は別のお知らせタブなので取り込まない。同じHTTP応答には含まれうる。本文から長期案内を除外しない。深夜のサービス対象時間外表示や列車位置は取得対象外であり、NORMALは運転時間・列車の存在を保証しない。

サイト規約1項は事前許諾のないコンテンツ利用を制限するため `PERMISSION_REQUIRED`。規約本文はodakyu.jpを対象としており、別ドメインAPIの再利用許諾は確認できていない。この記録は利用許諾ではない。
