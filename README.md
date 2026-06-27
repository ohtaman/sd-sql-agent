# SQL Agent Tutorial Repository

雑誌連載「[データ分析とSQLエージェント](https://gihyo.jp/magazine/SD/archive/2026/202601#:~:text=%E3%80%90%E6%96%B0%E9%80%A3%E8%BC%89%E3%80%91%E3%83%87%E3%83%BC%E3%82%BF%E5%88%86%E6%9E%90%E3%81%A8SQL%E3%82%A8%E3%83%BC%E3%82%B8%E3%82%A7%E3%83%B3%E3%83%88)」の公式リポジトリです。本連載では、AI時代のデータ分析手法であるSQLエージェントについて、Google ADK (Agent Development Kit) を用いた実装をベースに解説します。このリポジトリは連載の進行に合わせて更新されていきます。

## 🏗️ アーキテクチャ

### 1. エージェント (`agents/`)
- 実装: `google.adk.agents.llm_agent.Agent` を使用
- 役割: ユーザーの質問を受け取り、SQLを生成して実行する

### 2. ツール (`src/sql_agent/tools/database_tools.py`)
- `DatabaseTools`: DuckDBを介してデータベースに接続し、SQLを実行する機能を提供します。
    - `run_query(sql)`: SQLを実行し、結果を返します。
    - `connect(db_id)`: BIRDデータセット内の特定のデータベースに接続します。

### 3. 評価システム (`src/sql_agent/eval/eval_bird.py`)
- BIRDデータセット（mini_dev）の質問に対してエージェントを実行し、生成されたSQLの実行結果を正解データと比較します。

## 📁 ディレクトリ構成

```
sql_agent/
├── agents/
│   ├── naive_agent/           # 最も単純なSQLエージェント（第2〜4回）
│   ├── basic_agent/           # スキーマ探索機能付き（第4回）
│   ├── semantic_agent/        # セマンティック知識活用（第4回）
│   └── search_agent/          # テーブルディスカバリ機能付き（第6回）
├── src/sql_agent/
│   ├── tools/                 # データベース接続・操作ツール
│   │   ├── database_tools.py                  # 基本ツール（第3回）
│   │   ├── database_tools_with_knowledges.py  # 知識マージ（第4回）
│   │   └── database_tools_with_discovery.py   # 探索機能（第6回）
│   ├── eval/                  # 評価スクリプト
│   └── knowledges.py          # ナレッジストア・キーワード探索（第4・6回）
├── data/bird/minidev/         # BIRDデータセット（配置場所）
├── knowledges/                # セマンティックレイヤー定義（第7回）
│   ├── metrics.yml            # 指標の計算ルール
│   ├── reference_queries.yml  # 参照クエリ（golden queries）
│   └── business_context.yml   # ビジネスコンテキスト（施策・計測変更）
├── dbt_thelook/               # dbtプロジェクト（第5回〜）
│   └── models/                # dbtモデル（staging/intermediate/marts）
└── duckdb/                    # DuckDBワークスペース
```

## セットアップ

### 1. BIRDデータセット（Mini-Dev）のダウンロード

1. [GitHubページ](https://github.com/bird-bench/mini_dev) にアクセスします。
2. README内の **Download BIRD Mini-Dev Complete Package** をクリックして、Googleドライブからデータをダウンロードしてください。
3. ダウンロードしたファイルを `data/bird` ディレクトリに配置し、展開します。

```bash
mkdir -p data/bird
# ダウンロードしたファイルを移動（ファイル名はダウンロードした時期により異なる場合があります）
mv ~/Downloads/minidev_0703.zip data/bird/ 
cd data/bird
unzip minidev_0703.zip
```

展開後の構成が `data/bird/minidev/MINIDEV/dev_databases/...` となっていることを確認してください。

### 2. 環境変数の設定

1. `.env.example` を `.env` にコピーします
2. `GEMINI_API_KEY` を自身のものに設定します

設定は `sql_agent.config` から参照します。`.env` は config を import したときに読み込まれます。

## 🚀 実行方法

### 1. Web UIでの実行
ブラウザ上でエージェントと対話できます。

```bash
uv run adk web agents
```
ブラウザで `http://localhost:8000` にアクセスし、使用するエージェントを選択してください。

- `naive_agent`: 基本的なSQLエージェント（第3回）
- `basic_agent`: スキーマ探索機能付き（第4回）
- `semantic_agent`: セマンティック知識活用（第4回）
- `search_agent`: テーブルディスカバリ機能付き（第6回〜）。thelookデータセットで使用します。

### 2. 評価の実行（第3〜4回）
BIRDデータセットを用いてエージェントの性能を評価します。

```bash
# 最初の3問だけテスト実行
uv run eval-bird --agent naive_agent --limit 3

# 少し多めに実行
uv run eval-bird --agent naive_agent --limit 10

# 失敗理由をLLMで分析（オプション）
uv run eval-bird --agent naive_agent --analyze-failures --limit 3
```

### 3. dbtプロジェクトの実行（第5回〜）

第5回以降では、thelookデータセットを使用します。`.env` の設定を以下のように変更してください。

```
SQL_AGENT_DB_TYPE=thelook
SQL_AGENT_DUCKDB_PATH=duckdb/thelook.duckdb
```

BigQueryの公開データセット `thelook_ecommerce` を使用したdbtプロジェクトです。

```bash
cd dbt_thelook

# モデルのビルド
uv run dbt run

# テスト実行
uv run dbt test

# ドキュメント生成・表示
uv run dbt docs generate
uv run dbt docs serve
```

dbtのメタデータ（テーブル説明、カラム説明、リネージ、テスト情報）をknowledgesテーブルに登録するには：

```bash
uv run load-dbt-knowledges
```

### 4. セマンティックレイヤーの投入（第7回〜）

指標定義、参照クエリ、ビジネスコンテキストをknowledgesテーブルに投入します。

```bash
uv run load-knowledges --file knowledges/metrics.yml --source-name semantic_layer --replace
uv run load-knowledges --file knowledges/reference_queries.yml --source-name reference_query --replace
uv run load-knowledges --file knowledges/business_context.yml --source-name business_context --replace
```

**重要**: すべてのdbtコマンドは `uv run dbt ...` の形式で実行してください。グローバル環境に依存せず、プロジェクト固有の環境で実行できます。

詳細は [`dbt_thelook/README.md`](dbt_thelook/README.md) を参照してください。
