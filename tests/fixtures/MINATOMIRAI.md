# みなとみらい線

2026-11-02 UTCに公式の[運行情報](https://www.mm21railway.co.jp/service/)、
[CSS](https://www.mm21railway.co.jp/service/css/index.css)、
[共通JavaScript](https://www.mm21railway.co.jp/common/js/common.js)、
[サイトポリシー](https://www.mm21railway.co.jp/info/sitepolicy.html)を取得して確認。
HTMLに本文が直接含まれるため、運行情報ページだけを取得する。
JavaScriptの `/inc/service.html` はトップページ用の別表示。

fixtureは `.service_information` だけをBeautifulSoupの `html.parser` で
抽出・シリアライズし、UTF-8・末尾改行で保存したもの。本文やラベルの改変なし。
原本URL・UTC取得日時・原本SHA-256・加工後SHA-256は
[minatomirai_manifest.json](minatomirai_manifest.json) に記録している。
再現用スクリプトは `reports/extract_minatomirai.py`。

| fixture | 保存日時（UTC）・出典 | 確認内容 |
| --- | --- | --- |
| `minatomirai_normal.html` | ライブ取得。日時はmanifest参照 | 完全一致の平常文 |
| `minatomirai_20160920120337.html` | [2016-09-20 12:03:37](https://web.archive.org/web/20160920120337id_/http://www.mm21railway.co.jp/service/) | 平常文に台風の注意書きが続く。ALERTとして本文を保持 |
| `minatomirai_20180122144419.html` | [2018-01-22 14:44:19](https://web.archive.org/web/20180122144419id_/http://www.mm21railway.co.jp/service/) | caution、降雪によるダイヤ乱れ、遅延時間欄の「大幅な遅れ」をDELAYEDに対応 |
| `minatomirai_20191011232736.html` | [2019-10-11 23:27:36](https://web.archive.org/web/20191011232736id_/http://www.mm21railway.co.jp/service/) | cautionなしの運休・計画運休案内。ALERT |
| `minatomirai_20191012171120.html` | [2019-10-12 17:11:20](https://web.archive.org/web/20191012171120id_/http://www.mm21railway.co.jp/service/) | caution、台風による運転終了・翌日の見合わせ見込み。ALERT |
| `minatomirai_20221216085310.html` | [2022-12-16 08:53:10](https://web.archive.org/web/20221216085310id_/http://www.mm21railway.co.jp/service/) | 別表記の平常文 |

CSSの `.caution` は注意アイコン・背景色を定めるだけで、運休種別を表さない。
運休案内にも `.caution` がない実例がある。明示された遅延時間欄を除き、
本文のキーワードから遅延・運転見合わせ・一部運休を推測しない。
それ以外の案内は `ALERT` で原文を保持し、`affected_lines` / `alerts` で参照する。
未知のクラス、平常文と注意クラス・詳細欄の矛盾は `UNKNOWN`。
構造欠損・重複・空欄は `ParseError` で直前の状態を保持する。

表の発生時刻・原因・遅延時間はアラート本文にラベル付きで保持する。
「発生時刻」は更新日時ではないため、`updated_at=None`。
掲載基準は10分以上の遅れ・運転見合わせとその見込み。
平常時の定型文全体が一致する場合だけ `NORMAL` にする。

同一障害の復旧アーカイブ、独立した運転見合わせ／一部運休の状態コード、
現在の異常時HTMLは未確認。復旧テストは別時点の実際の平常HTMLへの切り替え。
未知状態・矛盾・構造欠損・通信失敗のテストは合成。
遅延証明書・列車位置・リンク先の振替輸送一覧は取得しない。

公式サイトポリシーは文章等の無断転載を禁止しているため、メタデータは
`PERMISSION_REQUIRED` とし、確認日時と公式URLを記録した。
