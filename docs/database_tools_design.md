# Database Tools 設計ドキュメント

## 概要

SQLエージェントシステムにおけるデータベース接続・ツール管理の設計方針とアーキテクチャを定義。

## 設計原則

### 1. 責務の分離 (Separation of Concerns)

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Agent Layer   │    │  Metadata Layer  │    │   SQL Layer     │
│                 │    │                  │    │                 │
│ ・推論・判断     │    │ ・BIRD CSV解析   │    │ ・DB接続        │
│ ・ツール選択     │───▶│ ・メタデータ変換 │───▶│ ・クエリ実行     │
│ ・回答生成       │    │ ・カタログ管理   │    │ ・スキーマ取得   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### 2. レイヤー別責務

#### SQL Layer (DatabaseTools) ※実装済み
- **責務**: 純粋なSQL実行とデータベース接続管理
- **設定**: `sql_agent.config` を参照（詳細は [db_backend_design.md](db_backend_design.md)）
  - `SQL_AGENT_DB_TYPE`: データベースタイプ (デフォルト: 'bird')
  - `SQL_AGENT_BIRD_PATH`: BIRD 用ルート（dev_databases の親）。デフォルト: `data/bird/minidev/MINIDEV`
  - `SQL_AGENT_DUCKDB_PATH`: DuckDB ワークスペースパス
- **提供機能**:
  - `run_query(sql)`: SQLクエリ実行
  - `list_tables(database=None)`: 生スキーマ情報でのテーブル一覧
  - `describe_tables(table_full_names)`: 生スキーマ情報でのテーブル詳細

#### Metadata Layer (MetadataManager + sync) ※未実装・将来
- **責務**: データソース特有の処理を抽象化（BIRD の description.csv 等を統合した API）
- **BIRD特有処理（予定）**:
  - `load_bird_table_descriptions()`: description.csv読み込み
  - `map_bird_format_to_standard()`: BIRD形式→標準形式変換
  - `sync_bird_metadata()`: 統一カタログへの投入
- **提供機能（予定）**:
  - `list_tables()`: メタデータ付きテーブル一覧
  - `describe_tables()`: メタデータ付きテーブル詳細

#### Agent Layer
- **責務**: 適切なツールの組み合わせと推論
- **ツール選択**:
  - **naive_agent**（実装済み）: `run_query` のみ
  - **first_agent**（実装済み）: ツールなし（動作確認用）
  - **schema_aware_agent**（未実装）: `run_query` + `list_tables` + `describe_tables`（生スキーマ）
  - **metadata_agent**（未実装）: `run_query` + Metadata Layer の `list_tables` / `describe_tables`

## アーキテクチャの利点

### 1. データソース抽象化
```python
# 現状: SQL Layer のみ実装。DatabaseTools が run_query / list_tables / describe_tables（生スキーマ）を提供。
# 将来: Metadata Layer 実装時、BIRD の description.csv 等を metadata.sync で吸収し、
#       Agent 側では統一された list_tables / describe_tables（メタデータ付き）を利用可能に。
```

### 2. 環境変数による設定
```bash
# デフォルト（BIRD）
uv run adk web agents/naive_agent/

# カスタムパス（BIRD 用）
SQL_AGENT_BIRD_PATH=/custom/bird/path uv run adk web agents/naive_agent/

# DuckDB ワークスペースを指定する場合
# SQL_AGENT_DUCKDB_PATH=duckdb/workspace.duckdb

# 将来の拡張（BigQuery / PostgreSQL 等）
# SQL_AGENT_DB_TYPE=bigquery 等、db_backend_design に従い追加
```

### 3. 状態管理の局所化
```python
# Before: グローバル変数
_SHARED_CONNECTION = None
_ATTACHED_DBS = set()

# After: クラス内状態管理（実装では _connection, _attached_dbs）
class DatabaseTools:
    def __init__(self):
        self._connection = None
        self._attached_dbs: set[str] = set()
```

## 実装パターン

### エージェント定義
```python
from sql_agent.tools.database_tools import DatabaseTools

# 環境変数ベース初期化
db_tools = DatabaseTools()

root_agent = Agent(
    tools=[db_tools.run_query]  # メソッド参照
)
```

### 遅延初期化
```python
def run_query(self, sql: str):
    if not self._connection:
        self.connect()  # 初回使用時に接続
    # connection プロパティで DuckDB 接続を取得し SQL 実行
    return self.connection.sql(sql).df()  # 等
```

## 将来拡張への対応

### 新しいデータソースの追加
```python
# 実装では config.DB_TYPE を参照（sql_agent.config）
def connect(self, db_id: str | None = None):
    if config.DB_TYPE == "bird":
        self._attach_bird_databases(db_id)
    elif config.DB_TYPE == "bigquery":
        self._init_bigquery_connection()  # 追加
    else:
        raise ValueError(f"Unsupported database type: {config.DB_TYPE}")
```

### メタデータプロバイダーの追加
```python
# metadata.sync に新しい sync_xxx_metadata を追加
def sync_postgres_metadata(connection_str, metadata_manager):
    # PostgreSQL特有の処理
    pass
```

## 設計決定事項

### ✅ 採用した設計
1. **環境変数ベース設定**: 雑誌読者にとって分かりやすい
2. **クラスベース**: 状態管理の局所化、将来拡張性
3. **責務分離**: SQL Layer ≠ Metadata Layer
4. **遅延初期化**: エージェント定義時の軽量化

### ❌ 却下した設計
1. **config.yml**: 設定ファイル編集が読者にとって煩雑
2. **グローバル関数**: 状態管理が困難、テストしにくい
3. **Tool内でのメタデータ処理**: 責務の混在

## 重要なポイント

### 現状の実装
- **SQL Layer (DatabaseTools)** のみ実装。`config.DB_TYPE` / `config.BIRD_PATH` / `config.DUCKDB_PATH` で接続先を切り替え。
- `connect(db_id)` で `DB_TYPE==bird` のとき `_attach_bird_databases(db_id)` を呼び、dev_databases 配下の SQLite を DuckDB に attach。
- Metadata Layer（MetadataManager, metadata.sync）は未実装。実装時は BIRD の description.csv 等を吸収し、メタデータ付き API を提供する想定。

### 環境変数の適用範囲
```bash
# 接続先の切り替え（config で解決）
SQL_AGENT_DB_TYPE=bird
SQL_AGENT_BIRD_PATH=data/bird/minidev/MINIDEV   # BIRD 用ルート
SQL_AGENT_DUCKDB_PATH=duckdb/workspace.duckdb   # DuckDB ワークスペース（省略時はデフォルト）

# 詳細は db_backend_design.md を参照
```

## まとめ

本設計により、以下を実現：

1. **雑誌読者フレンドリー**: 環境変数で設定変更（詳細は db_backend_design）
2. **拡張性**: 新しいデータソース対応が容易
3. **保守性**: 責務分離による理解しやすいコード
4. **テスタビリティ**: 依存注入可能な設計

**現状**: DatabaseTools は純粋な SQL レイヤーとして実装済み。**将来** Metadata Layer を追加すれば、BIRD 特有処理をそこで吸収し、エージェントは統一 API のみ利用可能になる。