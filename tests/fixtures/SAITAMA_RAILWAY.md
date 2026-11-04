# 埼玉高速鉄道（埼玉スタジアム線）

調査方法は公式HTML内の公開JavaScriptの逆解析。2026-11-04 UTCに
ライブラリの `USER_AGENT` を名乗ったGETで200応答を確認した。
元URL・UTC取得日時・原本SHA-256・加工内容は
[saitama_railway_manifest.json](saitama_railway_manifest.json) を参照。
公式の応答原本はローカルのみ保存し、Git・配布物には含めない。

- [公式電車運行情報](https://www.s-rail.co.jp/ticket/train/) のインラインJSは
  `/service_status/status.json?t=<現在時刻>` を取得する。`t` はキャッシュ回避だけで、
  時刻を指定しないJSONも200で同じ構造を返した。Providerは固定URLを使う。
- `createTrainNote()` へ渡すのは `latest` がtrueの項目のみ。
  過去7日分は別の `createTable()` に渡す。`latest` がない項目もJSの条件では
  現在表示から外れるため、Providerでもfalseと同様に除外する。
  過去項目の本文・日時は解析せず、必須の配列構造・項目オブジェクト・flag型は検証する。
  空配列または現在項目なしは `UNKNOWN`。掲載なしを平常と扱わない。
- [トップページ](https://www.s-rail.co.jp/) は先頭項目だけを使うが、
  Providerは専用運行情報ページと同じく全 `latest=true` を保持する。
- `stdtxt` は `createTrainNote()` とトップの `setMessage()` で平常の `o` アイコンを
  固定表示するため `NORMAL`。任意の本文の単語から状態は導出しない。
- `message` は `langs.ja.status` が専用状態欄、`langs.ja.text` が案内本文。
  `STATUS_TYPES` に明記されたラベルだけを照合する。

| 専用状態欄 | 共通状態 |
| --- | --- |
| 平常運転 | NORMAL |
| 遅延 | DELAYED |
| 運転見合わせ、運休 | SUSPENDED |
| 一部運休 | PARTIAL_SUSPENSION |
| 運転再開見込、お知らせ、運転再開、直通運転中止、折返し運転、経路変更、直通運転再開、バス代行、振替輸送、リフレッシュ工事、一部運転再開 | ALERT |
| 未知ラベル、未知type、overtime | UNKNOWN（原文保持） |

共用アイコン `^` / `x` だけでは遅延・運休を区別できないため、アイコンから分類しない。
直通中止や振替先への言及を埼玉高速鉄道全線の運休へ変換しない。
複数の現在項目は共通の優先順位で集約し、各非平常項目の本文を保持する。

履歴表は `msg.time` を「発信日時」としてYYYYMMDDHHmm形式で表示し、ライブの値は
秒を含む14桁。現在項目のこの発信日時を日本現地時刻 `Asia/Tokyo` として
`updated_at` に採用する。複数現在項目なら最新の発信日時を使う。
外側の `time` / `created` は毎日の生成日時と区別できるため採用しない。
`latest` は表示対象の指定であり障害の適用時期の証拠ではない。
全案内の `timing=UNKNOWN`、適用開始・終了は未設定。

取得範囲は赤羽岩淵～浦和美園の現在項目。Yahooの既存共通ID
`jp:operator_6792d0f7efc4:line_1b9213f482b7` を再利用し、状態は取得元ごとに独立する。
専用JSに長期案内の分離欄はなく、現在欄に掲載された案内を本文の期間で除外しない。
別のニュース、臨時ダイヤ、遅延証明書、振替輸送詳細、他社線は対象外。
生応答記録には過去項目も含まれる。公式の掲載基準は15分以上の遅れ・その見込みであり、
`NORMAL` はこの取得範囲の状態を示す。

ローカルfixture `saitama_railway_normal.json` はライブの `stdtxt/latest=true` の
無加工応答。発信日時は2026-10-29 04:00:03 JST、生成日時は2026-11-04。
完全一致URLのWayback CDX照会は `[]`、クエリ付きURLを含むワイルドカード照会は
タイムアウトした。異常時JSON、復旧の実データ、複数現在項目、overtimeは未確認。
これらのテストと欠損・未知値・HTTP失敗・記録再生は明示的な合成データであり、
実際の異常時応答の証拠とは扱わない。

[サイトポリシー](https://www.s-rail.co.jp/sitepolicy/) は情報（文字・データ・画像）の
印刷・引用・転用に承諾を求めるため `PERMISSION_REQUIRED`。
フッターの同ポリシーへのリンクも確認した。匿名で取得できることを利用許諾とみなさない。
