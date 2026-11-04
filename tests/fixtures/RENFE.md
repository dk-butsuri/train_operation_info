# Renfe Cercanías / Rodalies

2026-11-04 UTCに、ライブラリのUser-Agentを使って公式の公開資料・実応答を取得。
URL・取得日時・SHA-256は [renfe_manifest.json](renfe_manifest.json) に記録。
原本と無加工の `renfe_alerts_20261104.json` はローカル専用で、Gitには含めません。

## 取得範囲と対応根拠

- [公式データセット](https://data.renfe.com/es/dataset/incidencias-avisos)は
  Cercaníasの設備・代行輸送・線路障害等の案内をGTFS-realtimeで公開。
  実行時には `https://gtfsrt.renfe.com/alerts.json` だけを取得します。
- 実応答は69件。全件が `descriptionText` を持ち、`headerText` と `effect` はありません。
  本文から遅延・運休・復旧・適用時期を分類せず、`effect/timing=UNKNOWN` を維持。
  既知の明示effectはGTFSの列挙値から直接AlertEffectに対応させますが、
  ネットワーク全体の運行状態には変換しません。
- 現行の公式static GTFS（263経路）と実応答の多数の `routeId` が不一致。
  地域番号や末尾の路線名から補完しません。共通カタログに重複する登録はなく、
  データセットの掲載範囲を `es:renfe:cercanias`、`scope=GROUP` として追加。
  `affected_line_ids=()`、案内があればLineは`UNKNOWN`です。
- [GTFS仕様](https://gtfs.org/documentation/realtime/reference/)のFULL_DATASETは全掲載内容の置換。
  検証した空フィードは掲載範囲内の`NORMAL`です。全列車の平常運転を保証しません。
  [ProtoJSON仕様](https://protobuf.dev/programming-guides/json/)に従い、
  省略された反復フィールドは空、uint64 timestampは文字列として扱います。
- `AVISO_518187` が異なる `informedEntity` で2回掲載されています。
  両方を保持し、共通alert IDには元IDと検証済みselector集合のSHA-256を使います。
  同じID/selectorの重複はParseError。同じ本文であることを理由に統合しません。
- 43件が2つの翻訳を両方とも `language=es` として公開しています。
  非空のesラベル付きテキストを原順序・原文のまま空行で連結します。
  1件には空白だけの第2翻訳があり、これは表示テキストに含めません。
  実際の言語を推定してラベルを書き換えません。titleがない場合は元のentity IDを使います。
- 取得日は11月4日ですが、`header.timestamp=1791358372` は **2026-10-07T07:32:52Z**。
  古い時刻を`updated_at`に保持し、取得時刻で更新済みと見せません。
  `activePeriod`は表示期間のため、障害の`active_from/until`には流用しません。
- 工事・長期案内・復旧文・駅設備情報が同じ一覧に混在し、構造で分離できないため保持。
  AVE・長距離列車・列車別の遅延・リンク先詳細は取得対象外です。
  公式visorの公開JSは別形式のendpointを使用しており、本JSONとの同一性は未確認。

## 公開条件

データセットはCC BY 4.0を明記。[公式条件](https://data.renfe.com/es/legal)は
商用・非商用の再利用を認め、Renfe Operadoraへの帰属、原本の更新日と条件の保持、
意味の保全、Renfeの関与を示唆しないことを求めます。
CC BY 4.0のリンクと加工表示もメタデータに記録。既定の取得対象に含めます。

## 検証と未確認範囲

`test_renfe.py` の実応答テストは69件・重複ID・更新時刻・原文保持を確認。
空一覧、復旧、明示effect、壊れた構造、翻訳欠損、HTTP拒否は合成テストです。
実際の平常・復旧応答やアーカイブは確認していません。HTTP記録・再生も
無加工のJSON fixtureを使用します。原本がない環境では実応答テストだけskipします。
