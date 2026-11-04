# 相模鉄道

調査方法は公開HTML・JavaScriptの逆解析と公式JSONのアーカイブ確認。
2026-11-04 UTCにライブラリの `USER_AGENT` を名乗ってHTTP GETし、200応答を確認した。
出典URL・Wayback保存URL・UTC取得日時・原本SHA-256は
[sotetsu_manifest.json](sotetsu_manifest.json) に記録。原本・fixtureとも無加工のバイト列。
第三者のHTML・JS・JSONはローカルだけに保存し、Gitには出典とmanifestだけを含める。

- [公式運行情報](https://www.sotetsu.co.jp/train/status/) のNuxt設定は
  `trainStatusAPIURL=https://cdn.sotetsu.co.jp/unkou/dat` を指定している。
- `https://www.sotetsu.co.jp/_nuxt/Cq7Xtqw3.js` は `train_status1_v2.json` の
  先頭項目を表示。`MSG` は「運行情報」、`MSG2` は「振替輸送」で、後者は空なら非表示。
- `https://www.sotetsu.co.jp/_nuxt/BG3P_7p2.js` は `IRREGULAR` をそのまま渡し、
  `MSG2 || ""` を採用。`DATE` は日付に変換するが、運行情報ページでは表示しない。
- `https://www.sotetsu.co.jp/_nuxt/BB6XB0j6.js` は `irregular` がtrueなら
  「相鉄線運行情報あり」、falseなら「相鉄線平常運転」と表示する。
  この対応だけを `ALERT`／`NORMAL` に採用する。英語の `E_STATUS` は採用しない。
- 運行情報ページの「現在」は `new Date(Date.now())` で生成される。
  これを更新日時として使わず、`DATE` も更新日時との明示的な対応が未確認なので
  `updated_at=None` とする。`timing=UNKNOWN`、適用期間は未設定。
- `owabi.json` とmicroCMS `train-alerts` は、運行情報表とは別のお知らせ欄。
  長期案内を含み得るこの別欄、遅延証明書・列車位置・他社線運行情報は取得対象外。
  対象フィード内の本文を期間・キーワードで除外することはしない。
- 相鉄線全体の掲載単位はYahoo 125/0と同じ共通ID
  `jp:sotetsu:line_bcfb80c3830e` を再利用する。個別路線別の状態は導出しない。

| ローカルfixture | 出典・確認内容 |
| --- | --- |
| `sotetsu_normal.json` | ライブJSON。IRREGULAR=false、平常表示 |
| `sotetsu_20230717075741.json` | [2023-07-17 07:57:41 UTC](https://web.archive.org/web/20230717075741id_/https://cdn.sotetsu.co.jp/unkou/dat/train_status1_v2.json)。東横線方面との直通中止、目黒線方面は継続。IRREGULAR=true。相鉄線全線の運転見合わせには変換しない |
| `sotetsu_20230729083512.json` | [2023-07-29 08:35:12 UTC](https://web.archive.org/web/20230729083512id_/https://cdn.sotetsu.co.jp/unkou/dat/train_status1_v2.json)。平常、false |
| `sotetsu_20260519070818.json` | [2026-05-19 07:08:18 UTC](https://web.archive.org/web/20260519070818id_/https://cdn.sotetsu.co.jp/unkou/dat/train_status1_v2.json)。平常、false |

後日の平常データは同一障害の復旧の証拠とはしない。現在の異常時、独立した全線運転見合わせ、
空でないMSG2、多項目の実データは未確認。これらと将来予告・復旧・欠損・型不一致・HTTP失敗の
テストは明示的な合成データであり、取得元の未確認状態の根拠ではない。
JSONは必須MSG・IRREGULARと、公式で空文字にフォールバックする任意MSG2をstrictに検証し、
空配列・複数項目・空本文はParseErrorで前回値を保持する。

[一般利用規約](https://www.sotetsu.co.jp/terms/) は著作権法上の私的利用と事前承諾を留保し、
それ以外の無断利用を禁じる。運行情報ページの表示JSは情報固有の無断転載・複写禁止も表示する。
メタデータは `PERMISSION_REQUIRED` とし、一般規約の留保も記録する。
