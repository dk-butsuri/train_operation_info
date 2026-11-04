# 香港MTR

2026-11-04に公式HTML・公開JavaScript・平常時XMLを調査。原本の取得URL・UTC取得日時・SHA-256は [mtr_manifest.json](mtr_manifest.json) に記録。取得はライブラリ標準User-AgentによるGETで、ブラウザの偽装・別ホストへのフォールバックは行っていない。平常XMLは `mtr_normal.xml`、調査用のHTML・JavaScript・凡例はローカルの `reports/mtr/` に保存し、原本はGitに含めない。

- [公式トップページ](https://www.mtr.com.hk/en/customer/main/index.html) が [RYGfunc.js](https://www.mtr.com.hk/share/customer/js/RYGfunc.js?v=0.2) を読み込む。
- `createRYGLineStatus` は `/alert/ryg_line_status_lite.xml` の `line_code`・`line_name`・`line_name_tc`・`status` を参照し、`messages/message` の `title_en`・`url_en` と繁体字版を表示する。Providerは英語の全メッセージの見出しとリンクを保持し、詳細ページは取得しない。HTMLを含む見出しはテキスト化する。
- [common_rpyg.js](https://www.mtr.com.hk/share/customer/js/common_rpyg.js) の `AlertHandler` は `/alert/getDomain.php` の値の末尾 `/` を削除してXML取得先を構成する。今回の値は `/` なので取得先は同一オリジン。Providerは確認済みの `https://www.mtr.com.hk/alert/ryg_line_status_lite.xml` を直接読む。配信先設定が将来変わった場合の追従・他ホストへの切替は実装していない。
- [公式凡例ページ](https://www.mtr.com.hk/en/customer/main/service_status.html) の `createRYGLegendAndRemark` は [legend_remarks_v2.xml](https://www.mtr.com.hk/alert/legend_remarks_v2.xml) の色と説明を使用する。この凡例は追加行車時間20分超の継続的遅延、台風、祝祭日の特別運行を案内対象として説明している。平常は配信範囲内の表示であり、あらゆる遅延の不存在を意味しない。

| status | 共通状態 | 根拠・制限 |
| --- | --- | --- |
| green | NORMAL | 平常 |
| grey | NORMAL | 非サービス時間。運行アラート上の平常であり、列車運転中を意味しない |
| yellow | DELAYED | 追加待ち時間・行車時間、または段階的復旧。復旧完了とは扱わない |
| red | ALERT | 運行への支障。全線運休・一部運休を断定する情報ではない |
| pink | ALERT | 遅延または支障で、種別を一意に決められない |
| typhoon | ALERT | 台風警報。運休とは判定しない |
| その他 | UNKNOWN | 未知コードを保持 |

`green`・`grey`でも同じ路線の`messages`に案内がある場合は本文を捨てず`ALERT`にする。本文の運休・復旧・日付・他路線名から分類や対象を推測しない。対象はメッセージが所属する構造化された`line`だけ。`timing=UNKNOWN`、有効期間は`None`。`lastBuildDate`はタイムゾーン・時刻の意味を確定する仕様を確認できないため、`updated_at=None`とする。

確認した平常XMLはTWL・KTL・ISL・SIL・TKL・TCL・DRL・AEL・EAL・TMLの10路線、すべて`green`。共通IDは`hk:mtr:...`、会社は`hk:mtr`。軽鉄（LR）、高速鉄道、別のTraffic Newsバナー、詳細ページ、構造的に別配信の特別・長期案内は取得範囲外。同じ`messages`内に将来予告等があればそのまま保持する。

Wayback CDXの `www.mtr.com.hk/alert/ryg_line_status_lite.xml`・HTTP 200・`text/xml`の検索は空だった。他のホスト・MIME型・旧形式の保存応答まで不存在を確認したわけではない。異常時の実応答は未確認。色コード・複数メッセージ・未知コード・欠損・復旧のテストは、取得したXML構造と公開JavaScript・凡例に基づく合成データであり、実際の障害の証拠ではない。保存応答の再生テストも新規のライブ取得ではない。

[利用規約](https://www.mtr.com.hk/en/customer/main/terms_of_use.html)の第5項は個人・非商用利用に限定し、第5・10項は複製・再配布・改変・商用利用を制限している。メタデータは`PRIVATE_USE_ONLY`とし、別途の許諾・適用法による留保を`usage_note`に残す。オープンデータAPIの利用許諾をウェブサイトXMLに適用しない。
