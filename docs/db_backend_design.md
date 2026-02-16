# DB バックエンド設計メモ（BIRD / BigQuery など）

## 前提

- **ツール** (`DatabaseTools`) は汎用にしたい（BIRD 専用にしない）
- **BIRD** は評価用。DuckDB + dev_databases 内の SQLite を attach して実行
- **BigQuery** は次回以降。別の接続方式（プロジェクト・認証）
- 連載サンプルなので、複雑にしすぎない

## 方針の候補

### 1. DB_TYPE + バックエンドごとの環境変数（推奨）

- **DB_TYPE** で「今どれを使うか」だけ決める。`bird` / `bigquery` など。
- 各バックエンド用の設定は **別々の環境変数** に分ける。

| DB_TYPE   | 使う環境変数（例） |
|-----------|---------------------|
| bird      | `SQL_AGENT_BIRD_PATH`（dev_databases のルート）, `SQL_AGENT_DUCKDB_PATH` |
| bigquery  | `BIGQUERY_PROJECT`, 認証（ADC や `GOOGLE_APPLICATION_CREDENTIALS`） |

- メリット: 何が有効か明確。BIRD 用パスと BigQuery 用プロジェクトが共存できる。
- デフォルト: `DB_TYPE=bird`, `SQL_AGENT_BIRD_PATH=data/bird/minidev/MINIDEV` のままにすれば、現状の評価がそのまま動く。

### 2. DB_TYPE をやめて「どれが設定されているか」で判定

- `SQL_AGENT_BIRD_PATH` が set → BIRD（DuckDB）
- `BIGQUERY_PROJECT` が set → BigQuery
- 両方 set のときの優先順位を決める必要あり（例: BIRD 優先、または明示的にエラー）。

- メリット: 環境変数が 1 つ減る。
- デメリット: 暗黙的。「意図せず両方設定されていた」時の挙動が分かりにくい。

### 3. DB_TYPE は残すが、値は「接続先の種類」だけ

- `DB_TYPE=bird` → BIRD 用のパス系の変数だけ参照
- `DB_TYPE=bigquery` → BigQuery 用の変数だけ参照
- ツール側は `config.DB_TYPE` を見て、使う設定と実装を切り替える。

→ 実質は **案 1** と同じで、DB_TYPE を「どのバックエンドか」のスイッチとして使う形。

---

## 推奨: 案 1（DB_TYPE + バックエンド別の環境変数）

- **DB_TYPE**: `bird` | `bigquery`（将来 `postgres` なども可）
- **BIRD 用**: `SQL_AGENT_BIRD_PATH`（従来の MINIDEV のルート）。`SQL_AGENT_DUCKDB_PATH` は DuckDB ワークスペース。
- **BigQuery 用**: `BIGQUERY_PROJECT` など、必要になったら追加。

こうすると:

1. BIRD は「評価用のパス」を BIRD 専用の名前で持てる（`DB_DATA_PATH` のような汎用名と混同しない）
2. BigQuery は別の変数で追加できる
3. ツールは `if config.DB_TYPE == "bird": ... elif config.DB_TYPE == "bigquery": ...` のように分岐するか、あるいは「接続オブジェクトを返すファクトリ」を小さく作るだけで済む

## config のイメージ（案 1）

```python
# どのバックエンドを使うか
DB_TYPE = os.getenv("SQL_AGENT_DB_TYPE", "bird")

# BIRD 用（DB_TYPE=bird のときのみ参照）
BIRD_PATH = _resolve_path(
    os.getenv("SQL_AGENT_BIRD_PATH"),
    Path("data") / "bird" / "minidev" / "MINIDEV",
)
DUCKDB_PATH = ...

# BigQuery 用（DB_TYPE=bigquery のときのみ参照）
# BIGQUERY_PROJECT = os.getenv("BIGQUERY_PROJECT")
```

- ツール側: `DB_TYPE` に応じて `BIRD_PATH` か BigQuery 用の設定を読む。`DatabaseTools` は「接続の取得」を `DB_TYPE` で分岐し、`run_query` / `list_tables` / `describe_tables` のインターフェースは共通に保つ。

## まとめ

- **DB_TYPE** は「接続先の種類」のスイッチとして残すのが分かりやすい。
- **BIRD 用パス** は `SQL_AGENT_BIRD_PATH`（あるいは `BIRD_MINIDEV_PATH` のまま）のように **BIRD 用の名前の環境変数** にすると、BigQuery 用の変数と分離できてよい。
- 実装は「config に BIRD 用と BigQuery 用を並べ、DatabaseTools が DB_TYPE で切り替え」という最小構成にすると、連載の複雑さを抑えられる。

---

## 現在の構成（シンプルに 1 ファイルに集約）

- **config**: `DB_TYPE`, `BIRD_PATH`, `DUCKDB_PATH` を定義。
- **tools/database_tools.py**: `connect(db_id)` で `DB_TYPE==bird` のとき `_attach_bird_databases(db_id)` を呼び、BIRD_PATH の dev_databases を DuckDB に attach。BigQuery 等を足すときはここに `elif config.DB_TYPE == "bigquery"` を追加する想定。
- **eval/eval_bird.py**: 評価用に `config.BIRD_PATH` を参照（問題 JSON や gold SQLite のパス）。
