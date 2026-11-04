# Provider追加の手順

このライブラリはService Alertsだけを扱います。Providerは運行会社ではなく取得元です。会社は `Line.operator`、路線の共通定義は `models.LINE_CATALOG` にあります。

ライブラリのソースは `src/train_operation_info/` に置きます。以下の `models.py`・`tracker.py`・`providers/` は、このパッケージ内の相対パスです。開発環境はプロジェクト直下で `python -m pip install -e ".[dev]"` により準備します。公開APIの型情報を配布するため、パッケージ直下の `py.typed` を維持してください。

## 全Provider共通の判定方針

**このライブラリでは、アドホックで不確実な推論を禁止します。** 型が一致するだけでなく、取得した値から公開APIの値への対応を、取得元の仕様・公開ソースコード・保存応答で説明できることを必須とします。状態、影響、対象路線、継続期間、適用時期、日時のすべてに適用します。

- 専用フィールド、状態コード、明示された分類、構造化された対象路線を優先します。自由記述中の原因・単語・日付の存在だけから、運休、一時的、長期、現在有効、将来予告、影響対象を導出しません。
- 文言判定・正規表現は、取得元のコードやアーカイブ等を調査し、固定部分・可変部分・対象範囲と意味が安定した定型形式だと確認できる場合に限ります。形式全体を検証し、本文の引用・否定・取り消し・別対象への言及を、定型形式の値として扱わないでください。単一の本文サンプルに含まれた語句だけでは、一般化の根拠になりません。
- 採用する対応ごとに、出典、取得元のフィールドまたは定型形式、共通モデルへの対応、未確認の範囲を記録します。合成テストは実装の検証であり、取得元の意味や形式の安定性を証明する資料ではありません。
- 対応が確認できなければ `UNKNOWN`、対象路線が特定できなければ `affected_line_ids=()`、日時が確認できなければ `None` を維持し、原文を保持します。取得元が単に「案内あり」と示す場合は、その根拠の範囲で `ALERT` とし、障害の種類を付け足しません。必須構造の破損は `ParseError` として直前のスナップショットを保持します。
- 特定の路線名・事故・掲載本文への特別分岐で分類を補完しません。判定条件を追加するときは、根拠と適用範囲を先に確認し、公開APIの意味・互換性への影響と検証方法を示します。

## 追加を見送る取得元

調査の結果、次に当たる取得元はProviderとして追加しません。

- **APIキー・アカウント登録が必要な取得元**：当面は実装せず、候補として調査結果を `reports/` に記録します（例：ODPT運行情報。`reports/` はローカル専用でリポジトリには含めません）。登録と規約への同意は利用者自身が行う必要があるため、方針を見直すまで保留します。
- **自動取得にライセンス契約を求める取得元**：利用規約がスクレイピング・自動抽出にライセンス契約（書面の契約）を求めている場合です（例：National Rail Enquiries、Eurostar）。契約の仕組みがある以上、それを通さずに取得するライブラリは配布しません。事前の許可・同意を求めるだけの取得元は対象外とし、規約の内容を `usage_note` に記録して、必要に応じて明示指定時のみ取得します。
- **名乗った通信を拒否する取得元**：ブラウザを装う、CAPTCHA・ログイン・アクセス制限を回避する、取得元を分散させて再試行する、といった手段でしか取得できない場合です。拒否は取得元の意思として扱います。User-Agentは `providers/base.py` の `USER_AGENT` を使い、Providerで上書きしないでください。
- **平常を判定する根拠がない取得元**：状態コード・専用フィールドがなく、安定した定型の平常文も確認できない場合です。どの応答も `UNKNOWN` にしかならず、取得元として役に立ちません。

## 1. 取得元と異常時の挙動を調査する

人が閲覧する運行情報ページを確認し、公開HTML・JavaScriptが参照するJSON、XML、埋め込みページを調べます。画面の表示とデータの対応を確認してください。現在の平常表示だけから障害時のラベルやコードを推測しないでください。

**各Providerの `provider.py` 先頭のdocstringには、異常時の調査方法を必ず記録してください。**

- 調査方法が「アーカイブ」「公開HTML・JavaScript等の逆解析」「両方」のどれに当たるか。
- 参照したページ・スクリプト・エンドポイントのURL。
- アーカイブを使用した場合は取得日時付きの保存URLと、確認した状態。
- 状態コード・ラベルと共通モデルの対応を判断した根拠。
- 未確認の状態、取得できない詳細、推測に基づく合成テストの範囲。
- 適用時期（`timing`）を判定できる専用状態の根拠、対象の公式項目、判別できない範囲。長期案内の構造的な分離と取得範囲。

例えば `providers/keihan/provider.py` はXMLの状態コードを公式JavaScriptと保存XMLの両方で確認しています。`providers/singapore_mrt/provider.py` は公開JavaScriptと平常時のJSONを確認していますが、異常時の保存POST応答は未確認です。この違いを明示してください。

WaybackではCDX索引から保存時刻を探し、`https://web.archive.org/web/<timestamp>id_/<元URL>` で保存本体を取得できます。JavaScriptが別途読み込むデータはHTMLと同時刻に保存されているとは限りません。HTMLだけで異常時のデータまで確認できたことにしないでください。

保存データは必要な部分だけを `tests/fixtures/` に置き、出典URL、UTCの保存時刻、取得・抽出方法、原本のSHA-256を `tests/fixtures/SOURCES.md` に追記します。DOMのシリアライズやJSONの投影などの加工も記録します。合成データは実データと区別します。

## 2. 既存の路線IDを照合する

**同じ路線が登録済みなら、Providerが違っても既存の `LineId` を再利用してください。取得元の都合だけで新しい路線IDを作らないでください。**

1. `models.LINE_CATALOG` で既存の共通路線を探します。
2. 表記だけでなく運行会社・路線・区間・系統の範囲（`LineDefinition.scope`）を照合します。同名の別路線や、系統全体と個別路線を統合しません。
3. 取得元の路線ID・名称を共通IDに対応付け、その対応表をProvider内に静的に定義します。
4. 未登録の路線だけ、`models.py` の共通定義に追加します。
5. 別Providerが生成する `Line` は別インスタンスにし、同じ共通IDと会社情報を参照させます。取得結果を共有・上書きしないでください。

```python
from train_operation_info.models import LINE_CATALOG, LineId, ProviderId

definition = LINE_CATALOG[LineId("jp:osaka_metro:midosuji")]
line = definition.create_line(
    ProviderId("another_source"), "https://example.com/service-status",
)
```

共通IDは取得元IDとは別です。`initial_lines()` は登録済みIDと会社の一致を検証します。Provider側の別表記は対応表で吸収します。

JR西日本のように地区ごとに同じ路線が複数回掲載される場合も、共通路線ごとに情報を統合します。一部区間の正常表示で、別区間の障害を消さないでください。対象が系統全体の場合や影響路線が特定できない場合は、範囲を明示して取り込みます。

## 3. Providerのフォルダを追加する

```text
providers/
└── sample/
    ├── __init__.py
    └── provider.py
```

`__init__.py` は公開するクラスだけをエクスポートします。

```python
from .provider import SampleProvider

__all__ = ["SampleProvider"]
```

共通の `SnapshotProvider` を継承すると、HTTPクライアントの所有権、取得失敗の変換、スナップショットの一括差し替えを共通化できます。`_fetch_lines(client)` は完全に検証した `tuple[Line, ...]` を返してください。途中で `self._lines` を書き換えないでください。

コンストラクターは `snapshot_dir: str | Path | None = None` を受け取り、基底クラスにも渡します。HTTP取得には `await self._get(client, url)` または `await self._post(client, url, data=...)` を使ってください。これにより正常・解析失敗・HTTPエラーの応答が保存されます。`client.get()` / `client.post()` を直接呼ぶと記録を通らないため、使用しません。日時は `self._now()` で取得し、オフライン再生時にも記録時刻を使えるようにします。

既存のIDを使う例は次の形です。実際の取得元に合わせて専用の入力モデルを定義してください。

```python
from typing import ClassVar, Literal
from pathlib import Path

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict

from train_operation_info.models import LINE_CATALOG, Line, LineId, LineStatus, ProviderId, ProviderMetadata
from train_operation_info.providers.base import SnapshotProvider, make_alert, snapshot


class _SourceStatus(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    status: Literal["normal", "delay", "suspended"]
    updatedAt: AwareDatetime
    description: str


class SampleProvider(SnapshotProvider):
    _provider_id = ProviderId("sample")
    _source_url = "https://example.com/service-status"
    _metadata: ClassVar[ProviderMetadata]  # 次節の必須メタデータを実際に設定する

    def __init__(
        self, *, client: httpx.AsyncClient | None = None, snapshot_dir: str | Path | None = None,
    ) -> None:
        line = LINE_CATALOG[LineId("jp:osaka_metro:midosuji")].create_line(
            self._provider_id, self._source_url,
        )
        super().__init__((line,), client=client, snapshot_dir=snapshot_dir)

    async def _fetch_lines(self, client: httpx.AsyncClient) -> tuple[Line, ...]:
        response = await self._get(client, "https://example.com/status.json")
        response.raise_for_status()
        data = _SourceStatus.model_validate_json(response.content)
        state = {
            "normal": LineStatus.NORMAL,
            "delay": LineStatus.DELAYED,
            "suspended": LineStatus.SUSPENDED,
        }[data.status]
        line = self.midosuji
        alerts = () if state is LineStatus.NORMAL else (
            make_alert(line, state, data.status, data.description),
        )
        return (snapshot(
            line, state, data.status, self._now(),
            updated_at=data.updatedAt, alerts=alerts,
        ),)

    @property
    def midosuji(self) -> Line:
        return self._line("midosuji")
```

上の例は構成説明用です。公開前には先頭の調査コメントと `_metadata` の値を実データに基づいて埋めます。

JSONを `response.json()` の無検証の辞書で処理せず、Pydanticの専用入力モデルで検証します。使用する必須項目と型はstrictにします。未使用の追加フィールドを許容する場合の `extra="ignore"` は明示し、既知フィールドの欠損や型不一致は許容しません。HTML/XMLでも構造・路線ID・状態コードを検証します。

日時はすべてタイムゾーン付きにします。JSONの日時には `AwareDatetime` を使い、時刻だけの入力にタイムゾーンを付ける場合は、取得元の仕様から現地時刻を確定します。日本なら `Asia/Tokyo`、シンガポールなら `Asia/Singapore` です。取得時刻は `datetime.now(timezone.utc)` とし、更新時刻がなければ `None` を返します。ブラウザの現在時刻や取得時刻を、取得元の更新時刻として代用しません。

属性は明示的な `@property` として型定義します。`__getattr__`、`setattr`、`Any`、型エラーの抑制で路線アクセスを実装しません。路線が多い場合は静的なPythonコードを生成して構いません。実行時の動的属性生成にはしません。

## 4. メタデータを記録する

### 運行への影響と適用時期

`ServiceAlert.effect` は遅延・運休などの影響、`timing: AlertTiming` は適用時期です。`timing` は `ACTIVE`（専用状態から現在有効と確認）と `UNKNOWN`（未確認）だけを持ちます。長期／一時的の判別と将来予告の自動判別は提供しません。期間分類のフィールド・列挙型・一覧プロパティも設けません。

JR西日本・JR東日本・Yahooでは、専用状態欄から確認した現在の遅延・見合わせ・一部運休に限り `ACTIVE` を設定します。`ALERT` や `UNKNOWN` から適用時期を推測しません。JR四国など、専用状態から適用時期を確定していないProviderは `UNKNOWN` です。

新規Provider・既存Providerの修正とも、次のルールを守ってください。

1. **取得元の専用項目・状態表示、または全Provider共通の判定方針を満たす定型形式を根拠にします。** 自由記述中の原因・期間・日付だけから運行状態や適用時期を導出しません。
2. 判別できない状態・適用時期には `UNKNOWN` を使います。不明は平常や一時的な障害がないことの証拠ではありません。
3. **現在の障害と将来予告を混ぜません。** 専用状態欄が現在の障害を示す場合、本文の再開見込み日でその状態を上書きしません。本文の運休表現・実施日・現在形・見込みから適用時期を付与しません。
4. 共通の `providers/classification.py` は、検証済みの専用状態から適用時期への対応だけを扱います。自由記述は入力に取りません。Provider固有の文言判定を追加する場合も、安定した定型形式である根拠を記録し、調査コメント・出典・否定文／予告／復旧のテストを併せて更新します。
5. `active_from` / `active_until` は**実際に案内が適用される期間**が明示される場合だけ設定します。更新日時、掲載開始・終了日時、取得時刻から代用しません。日付だけの情報から架空の開始時刻を作りません。繰り返しの運休を、一つの連続した運休期間に変換しません。
6. 長期案内が取得元で構造的に分離されている（別の欄・別ファイル・専用フラグ等）場合は、その欄を取得範囲から除外します。同じ欄に混在していて構造で分けられない場合は除外をあきらめ、原文のまま保持します。本文による長期判別や除外を追加しません。復旧・掲載終了・削除で古いアラートが消えることも確認します。
7. **`NORMAL` は宣言した取得範囲内の状態です。長期運休も含む全情報の平常を意味しません。** JR西日本は `dailyData` の当日分だけを解析し、構造的に分離された `areaAnnouncements` は対象外として検証・取り込みを行いません。JR九州も別テキストファイルの長期見合わせフラグを取得しません。対象欄の必須構造の型・欠損検証は維持します。対象外の欄が同じHTTP応答や生応答記録に含まれる場合は、その点も文書化します。
8. 対象路線は共通IDと照合します。地域全体の案内を、その地域の全路線が運休しているという意味に変換しません。特定できない対象は `affected_line_ids=()` とし、原文と不明な範囲を保持します。

`make_alert()` の `timing=` は既定値が `UNKNOWN` です。案内全体は `alerts` に保持し、`Line`・Provider・`Tracker` で次の一覧を参照できます。

| プロパティ | 対象 |
| --- | --- |
| `active_alerts` | `timing=ACTIVE`。一時的な障害に限定しない |
| `unclassified_alerts` | `timing=UNKNOWN`。適用時期を判別していない案内 |

Provider間の比較では共通路線ID、取得範囲、専用状態、実際の本文を確認します。一方の未分類や取得範囲外を「一致」や「案内なし」と判定しないでください。状態ラベルが異なっても同じ運休を指す場合、将来予告を片方だけが掲載している場合、取得・掲載時刻が違う場合を区別します。

### 取得元メタデータ

各Providerの `_METADATA` を `ProviderMetadata` として定義します。

| フィールド | 内容 |
| --- | --- |
| `provider_id` / `name` | 取得元のIDと表示名 |
| `source_page_url` | 人が閲覧できる運行情報ページ。内部APIだけを指定しない |
| `endpoints` | 実行時に取得するURL・HTTPメソッド・データ形式を列挙した、空でない `tuple[SourceEndpoint, ...]` |
| `terms_url` | 公式のサイト利用規約。見つからなければ `None` |
| `additional_terms_urls` | 運行情報固有の条件など、追加で確認した公式URL |
| `usage_permission` | `PRIVATE_USE_ONLY` / `UNSPECIFIED` / `COMMERCIAL_ALLOWED` / `PERMISSION_REQUIRED` |
| `usage_note` | 分類の根拠、留保される範囲、帰属表示などの条件 |
| `statuses` | `_fetch_lines()` が返し得る `LineStatus` の `frozenset`。`UNKNOWN` は含めず、`NORMAL` は必ず含める |
| `reviewed_at` | 実際に条件を確認した日時。タイムゾーン付きの固定値 |

`SourceEndpoint` には `url`、`method: Literal["GET", "POST"]`、`format: DataFormat`、`is_template`、`description` を設定します。`DataFormat` は `HTML`・`XML`・`JSON`・`JAVASCRIPT`・`TEXT`（プレーンテキスト）・`PROTOBUF`（GTFS-realtime等）です。GTFS-realtimeのフィードは共通の `providers/gtfs_rt.py` で解析し、フィードごとのProviderにURL・規約・`route_id` 対応表・取得範囲を定義します。人向けページとHTTP取得先を分け、`_fetch_lines()` が実際に使う取得先を全て宣言してください。調査で閲覧しただけのURLを含めません。固定URLには完全なURLを、実行時に決まるURLには `{filename}` 等を含むURLと `is_template=True` を指定し、決定方法・条件・POSTデータ等を `description` に記録します。

```python
from train_operation_info.models import DataFormat, SourceEndpoint

endpoints = (
    SourceEndpoint(
        url="https://example.com/status.json", method="GET", format=DataFormat.JSON,
        description="Current service status",
    ),
)
```

`tests/test_metadata.py` に形式の期待値、`tests/test_snapshots.py` に全取得先を通るfixtureを追加します。保存した実リクエストとメタデータの宣言が一致することも確認対象です。

`statuses` には、取得元の専用状態からコード上で導出できる状態を全て宣言します。`japanese_status()` のような共通のラベル対応表を通す場合は、その対応表が返し得る状態をすべて含めます。`combined_status()` は空の入力に `NORMAL` を返すので注意してください。`UNKNOWN` は取得前・未知の表示として全Providerで返り得るため宣言しません。宣言にない状態を解析した場合、`refresh()` は `ParseError` を送出して直前の結果を保持します。そのため、状態ごとのテストを書けば宣言の漏れは検出されます。一方、宣言が多すぎても検出されないため、実際に返さない状態は含めないでください。宣言はREADME（英語版・日本語版）の状態の分類能力の表と一致させます。食い違うと `tests/test_metadata.py` が失敗します。

```python
from train_operation_info.models import LineStatus

statuses = frozenset({LineStatus.NORMAL, LineStatus.ALERT})  # 遅延・運休を区別しない取得元
```

`PRIVATE_USE_ONLY` は私的使用等の法定範囲を留保する記載、`UNSPECIFIED` は再利用条件の明記を確認できない場合です。無断再利用を制限する記載がある場合は `PERMISSION_REQUIRED` として、無記載と区別します。商用可は明示的な根拠がある場合だけ記録します。

取得できることと利用許諾があることを混同しないでください。一般規約と運行情報固有の条件は両方を確認し、異なる記載があれば `usage_note` に残します。確認日時をモジュール読み込み時の `now()` にすると毎回確認したように見えるため、レビュー時点の日時を固定して記録します。

## 5. Trackerに登録する

`tracker.py` の次の箇所を更新します。

1. 具体的なProviderクラスのimport。
2. `ProviderName` の `Literal` に取得元IDを追加。
3. `Tracker` クラスに `sample = _Slot(SampleProvider)` の1行を追加。属性名は `provider_id` と同じにします。

`_Slot` は読み取り専用の型付き属性で、`tracker.sample` の型は `SampleProvider` になります。構築・`rate_limit` の適用・`overrides` による差し替えは `Tracker.__init__` が全取得元に共通で行います。Providerは `client` と `snapshot_dir` のキーワード引数だけで構築できるようにしてください。`ProviderName` と `_Slot` の過不足や、属性名と `provider_id` の不一致はimport時に `RuntimeError` になります。`tests/test_tracker.py` は `ProviderName` から全取得元を検証するため、テストの一覧を更新する必要はありません。

選択可能な取得元は `ProviderName` の全要素、既定の取得元は `_DEFAULT_PROVIDERS` です。Yahoo・MTA・小田急電鉄・DBは利用者が明示的に選択する方式のため、`_OPT_IN_PROVIDERS` として既定から除外しています。登録・`overrides` に渡しただけでは有効化せず、`enabled_providers` で選ばれたProviderだけを更新します。

これで `tracker.sample.midosuji` の属性補完・誤記検出と、`enabled_providers` による選択を両立できます。路線の集約では運行会社を階層キーにしません。

## 6. テストデータを追加する

Providerの追加・修正と一緒に、その挙動を再現するテストデータを追加します。

1. 取得した公式HTML・XML・JSONの必要部分を `tests/fixtures/` に保存します。平常時だけでなく、入手できる遅延・運休・復旧のデータも対象です。
   取得元の著作物を再配布しないため、これらのファイルはGitに含めません（`.gitignore` で `*.md` と `*_manifest.json` 以外を除外）。出典・保存日時・ハッシュ・加工内容を次の手順で必ず記録し、ファイルがなくても取得元を追跡できるようにします。
2. `tests/fixtures/SOURCES.md` に元URL、Wayback等の保存URLとUTCの保存日時、取得方法、原本のSHA-256を記録します。ライブ取得なら取得日、DOM抽出・JSON投影なら加工内容も記録します。
   Provider専用の出典ファイルに分ける場合は `SOURCES.md` からリンクします。Yahooの例は `YAHOO.md` と、取得日時・原本／抽出後のハッシュを記録した `yahoo_manifest.json` です。
3. 実データの状態ラベルや対象路線を書き換えて、別の実際の障害があったように見せないでください。故障・未知状態を作った合成データは、その旨をファイル名、コメント、テスト名等で区別します。
4. 追加したfixtureを読み込むテストを追加し、期待する共通路線ID、状態、アラート本文、タイムゾーンを確認します。実サイトへ通信せず `httpx.MockTransport` で再現します。
5. 再開・復旧のfixtureがあれば、更新後に古い遅延・運休が残らないことも確認します。確認できなかった状態はProviderの調査コメントに残します。

`tests/test_snapshots.py` にもProviderのfixture応答を追加し、保存したHTTP応答を `SnapshotReplayTransport` で再生したとき、路線状態・アラート・日時が一致することを確認します。既存fixtureをモック経由で記録したデータは、新たに実サイトから取得した証拠にはなりません。

参考になる実装は `tests/test_osaka_metro.py` のアーカイブによる復旧テストと、`tests/test_providers.py` の公式fixture・合成MRTケースです。

## 7. 確認する

保存した実データで正常・遅延・運休・復旧を確認します。未確認の状態は合成テストであることを明示します。欠損・未知の表示・通信失敗時に、正常運転へ変わらず直前の結果を保持することを確認してください。

同じ路線の共通IDの再利用、会社情報の一致、別Provider間の状態の独立、日時のタイムゾーンも確認対象です。複数Providerでは1社の失敗が他社の更新を妨げないことを確認します。

```powershell
python -m mypy
python -m pytest
```

`tests/fixtures/` に保存データがない環境（リポジトリをcloneした直後など）では、そのデータを読むテストは失敗せずスキップされます。スキップ理由は `python -m pytest -rs` で確認できます。Providerを変更したときは、保存データがそろった環境で全テストを実行してください。

実際の公式サイトへの取得は、オフラインテストとは分けてサンプルから確認します。最後にREADMEの対応Provider表・状態の分類能力の表（英語版・日本語版）と [docs/PROVIDERS.md](docs/PROVIDERS.md) へ対応範囲・アクセス例・取得できない情報を追記してください。

## 貢献のライセンスと署名

貢献されたコードは、このリポジトリの [MIT License](https://github.com/dk-butsuri/train_operation_info/blob/main/LICENSE) で公開します。著作権は各貢献者に残ります。

コミットには `git commit -s` で `Signed-off-by:` 行を付けてください。これは [Developer Certificate of Origin](https://developercertificate.org/) への同意を表し、そのコードを自分が書いた、またはMIT Licenseで提供する権利があることの確認になります。

- 個人のメールアドレスを公開しないよう、GitHubの `noreply` アドレス（`ID+ユーザー名@users.noreply.github.com`）でのコミットを推奨します。
- Issue・Pull Request・ドキュメント・デモ画面に、実際の運行情報の案内本文やスクリーンショットを載せないでください。説明には合成データを使います。
