# 土佐くろしお鉄道

調査日: 2026-11-04 UTC。方法: 公式公開HTMLの解析とWayback保存HTML。
標準の `train_operation_info` User-Agent で取得しています。
原本・抽出後のSHA-256、出典URL、保存日時は
[tosakuro_manifest.json](tosakuro_manifest.json) に記録しました。
`saved_at_utc` は応答直後に保存したローカルファイルの時刻です。
第三者のHTML・記事本文はローカルだけに保存し、Git・配布物に含めません。

## 取得元と構造

- [公式トップページ](https://www.tosakuro.com/) の `#comp-m9tlcfob` 内の
  ごめん・なはり線／中村・宿毛線の個別見出しと記事リスト。
  余分な共通リストは重複表示として取り込みません。
- [ごめん・なはり線の記事](https://www.tosakuro.com/post/ごめん・なはり線-通常運転中) と
  [中村・宿毛線の記事](https://www.tosakuro.com/post/_平常運行) の
  `h1[data-hook="post-title"]` と `section[data-hook="post-description"]`。
  実行時はトップページが示す記事URLを使用し、URLの語句で分類しません。
- [企業情報](https://www.tosakuro.com/company-profile) とトップページの公開リンクから
  適用可能な再利用規約は見つかりませんでした。`UNSPECIFIED` とし、許諾を推定しません。

## 確認した対応と限界

2026-11-04のライブ記事および下記保存ページで平常の見出しを確認しました。

- [2026-02-03 07:03:43 UTC](https://web.archive.org/web/20260203070343id_/https://www.tosakuro.com/)
- [2026-06-09 20:39:18 UTC](https://web.archive.org/web/20260609203918id_/https://www.tosakuro.com/)
- [2026-07-09 05:19:32 UTC](https://web.archive.org/web/20260709051932id_/https://www.tosakuro.com/)
- [2026-08-25 06:30:25 UTC](https://web.archive.org/web/20260825063025id_/https://www.tosakuro.com/)

完全一致する「平常運行」「平常運転」だけを `NORMAL` に対応させます。
異常時の保存見出し・安定した分類コード・同一事象の復旧過程は未確認です。
それ以外の見出しは `UNKNOWN`。遅延、運休、適用時期を本文から推定しません。

公式記事は平常の見出しでも個別列車の運休等を併記できます。
検索時に取得した[公式ごめん・なはり線記事](https://www.tosakuro.com/post/ごめん・なはり線-通常運転中)
の2026-11-03掲載内容に併記がありましたが、その応答本体は保存していません。
これは状態分類の根拠には使わず、本文を捨てない設計上の制限として記録します。
全記事本文を `effect=OTHER` の情報アラートとして常に保持します。
`NORMAL` でも `alerts` は空になりません。`affected_line_ids=()`、
`timing=UNKNOWN`、適用期間・`updated_at=None`。
掲載路線は記事の分類範囲であり、全列車・全区間の影響を確定しません。
年なし日時や記事の `dateModified` を運行状態の更新時刻へ変換しません。

トップページの別のお知らせ／トピックス欄とリンク先は構造で除外します。
運行記事内に混在する長期・将来・復旧案内はそのまま残します。
時刻表・列車位置・SNS・リンク先PDF／画像の内容解析は対象外です。
生HTTP記録には対象外のお知らせ欄も含まれます。

2025年の保存HTMLも調査しましたが、当時のリスト構造は現在と異なるため
現在のパーサーの対応対象にしていません。
原本から必要なDOMのみ抽出し、class/style属性のみ削除しています。
保存記事は実在の平常記事です。異常・否定・将来予告・復旧・構造破損・
通信失敗・同一Provider内の更新のテストは明示的な合成データです。
