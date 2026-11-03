# Taiwan Railway Corporation (TRA)

公式取得先は <https://www.railway.gov.tw/tra-tip-web/tip/tip007/tip711/blockList>。
調査方法は公開HTMLの逆解析とWayback保存HTMLの両方。取得日は2026-11-02 UTC。
[tra_manifest.json](tra_manifest.json) に原URL、保存URL、UTC保存日時、原本と抽出後のSHA-256を記録。
原本からBeautifulSoupの `html.parser` で `#content` 直下の `p` と完全な
`.operation-list` をシリアライズし、`div#content` に格納。路線・状態・本文の変更なし。
HTTP再生テストの記録は新たな実サイトの証拠ではない。

## 保存応答

保存URLは `https://web.archive.org/web/<保存時刻>id_/` に原URLを連結。
正確なURLとUTC日時はmanifest参照。

| 保存時刻 (UTC) | 確認した表示 |
| --- | --- |
| 20240213061449 | 平溪線の緑 Resume 行、集集線の Moderate 行。サマリーは両方「部份受阻」 |
| 20240403013943 | 東部幹線の地震、赤 Extreme。集集線の長期案内 |
| 20240804153201 | 東部幹線の黄 Delay。深澳線・集集線の Moderate |
| 20241004110527 | 台風 Typhoon と長期工事 Moderate の複数行 |
| 20241117082659 | 東部幹線の Severe。本文は単線双方向運転であり全線運休を意味しない |
| 20250310054809 | 東部幹線の脱線影響、黄 Delay。復旧見込みは「評估中」 |
| 20250707021531 | Typhoon と Moderate。西部4行、南迴線2行、集集線2行など計12行 |
| 20250813015801 | Typhoon、長期工事。復旧予定日時なしの行 |
| 20260702152705 | 12掲載単位すべて「全線正常運行」、空の通阻表 |
| ライブ 2026-11-02 | 全12掲載単位が平常。明示更新時刻2026/11/02 23:56 |

CDXの2024～2026年月別索引も確認した。同一障害に対する発生・復旧ペアは未確認。

## 状態・日時・取得範囲

`.operation-list` 直下の `dl.now_status` と直後の `table` が一対。
表の各行は日付・区間・本文・復旧見込みの4欄。
「部份受阻」は復旧行でも残るため運休や適用時期を示すコードではない。

| 行の公式凡例／色 | 公開値 |
| --- | --- |
| 恢復正常 (Resume) / #009900 | NORMAL、情報アラート OTHER は保持 |
| 列車延誤 (Delay) / #FFCC00 | DELAYED / DELAYS |
| 列車丙級災害規模 (Moderate) / #EE9200 | ALERT / OTHER |
| 列車乙級災害規模 (Severe) / #FF0099 | ALERT / OTHER |
| 列車甲級災害規模 (Extreme) / #CC0000 | ALERT / OTHER |
| 颱風期間列車運行資訊 (Typhoon) / #3300FF | ALERT / OTHER |

凡例のラベル・色と行のマーカーを併せて照合。未知色・ラベル変更・未知マーカーは
UNKNOWN、原文と色を保持。既知の平常サマリー（circle-o、#5bb900）かつ空表ならNORMAL。
既知の「部份受阻」（warning、#ff8400）で行がある場合に限り行状態を集約。
平常サマリーと非空表などの矛盾はUNKNOWN。欠損・空欄・重複・未知路線・不正日時・
孤立表・受阻なのに空表はParseErrorで一括更新を取り消す。

自由記述から運休・影響路線・適用時期を導出しない。路線IDは表の所属が根拠。
本文に他路線が登場しても影響IDを増やさない。区間名・4欄原文・行内リンクを保持。
長期工事・台風・復旧見込みは同じ表に混在し、構造上分離されていないため全行を保持。
`timing=UNKNOWN`。行日付は意味を事故発生時刻と断定できず、復旧予定も実際の有効期限
ではないため、`active_from/active_until` はNone。ページの「更新時間」だけをAsia/Taipei
として `Line.updated_at` に設定。個々の事故の更新を保証しない。

## 共通ID

既存カタログにTRA路線は未登録だったため、運行会社 `tw:tra` と12定義を追加。

| 公式掲載単位 | tw:tra: の接尾辞 | scope |
| --- | --- | --- |
| 西部幹線 | western_group | GROUP |
| 西部幹線 (海線) | western_coast | LINE |
| 東部幹線 | eastern_group | GROUP |
| 南迴線 | south_link_group | GROUP |
| 成追線 | chengzhui | LINE |
| 平溪線 | pingxi | LINE |
| 深澳線 | shenao | LINE |
| 六家線 | liujia | LINE |
| 內灣線 | neiwan | LINE |
| 集集線 | jiji | LINE |
| 沙崙線 | shalun | LINE |
| 蘇澳新-蘇澳 | suaoxin_suao | LINE |

西部・東部は複数の物理路線をまとめる掲載単位。南迴線欄には保存応答で屏東～潮州が
含まれ、物理的な南迴線単独のIDを割り当てない。蘇澳新～蘇澳はこの区間のみ。
海線は保存応答で竹南～彰化を確認。支線を複合幹線IDへ統合しない。

## 利用条件

確認日時2026-11-02T15:56:56Z。

- サイト資料開放宣告: <https://www.railway.gov.tw/tra-tip-web/adr/about-public-info-7>
  原本SHA-256 `e277b072b0f25f6d3460756ec9ab807e20b136fcc2666364eaa278941bc8d3db`。
  ウェブサイト全体の公開資料について無料・非独占・再許諾可能の利用、製品・サービスの
  開発を明示。出典表示が必要。商標等の別権利・個人情報・特記された著作物は除外。
  英語欄はOGDL-Taiwan-1.0に言及。推薦・公認を意味しない。
- 著作権声明: <https://www.railway.gov.tw/tra-tip-web/tip/tip00F/tipF14/view>
  原本SHA-256 `8a60c173b73e5bf8c6c25da63ed90f53e045a2af6f1fe658ec662a8fadc254d0`。
  保護対象には許諾または合理的使用を要求。上記サイト全体への明示許諾と併記する。
- 運行一覧に別の再利用制限は確認されなかった。メタデータは明示的なサイト資料開放宣告を
  根拠にCOMMERCIAL_ALLOWED。表示上の出典は國營臺灣鐵路股份有限公司。

## 検証と未確認

`test_tra.py` は10保存応答、12属性と共通ID・会社、遅延・復旧表示・原文保持、複数行と
長期工事、案内削除、選択と依存注入を検証。未知色・凡例変更・矛盾・欠損・HTTP失敗は
合成テスト。SnapshotReplayTransportで保存・再生と宣言取得先を照合する。
SUSPENDED/PARTIAL_SUSPENSIONへの専用コード対応、適用時期判別、同一障害の復旧ペア、
地図・別ニュース・列車単位の速報は未確認／対象外。
