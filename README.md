# SQL Agent Tutorial Repository

雑誌連載「[データ分析とSQLエージェント](https://gihyo.jp/magazine/SD/archive/2026/202601#:~:text=%E3%80%90%E6%96%B0%E9%80%A3%E8%BC%89%E3%80%91%E3%83%87%E3%83%BC%E3%82%BF%E5%88%86%E6%9E%90%E3%81%A8SQL%E3%82%A8%E3%83%BC%E3%82%B8%E3%82%A7%E3%83%B3%E3%83%88)」の公式リポジトリです。本連載では、AI時代のデータ分析手法であるSQLエージェントについて、Google ADK (Agent Development Kit) を用いた実装をベースに解説します。このリポジトリは連載の進行に合わせて更新されていきます。

## 🏗️ アーキテクチャ

### 1. エージェント (`agents/`)
実装: `google.adk.agents.llm_agent.Agent` を使用

- **naive_agent**: 最も単純なSQLエージェント（第3回）
  - SQLを実行するツールのみを持つ
- **basic_agent**: テーブル構造情報を利用するエージェント（第4回）
  - テーブル一覧取得、スキーマ情報取得のツールを追加
- **semantic_agent**: 知識を活用するエージェント（第4回）
  - テーブル・カラムに紐づく知識を利用してSQL生成精度を向上

### 2. ツール (`src/sql_agent/tools/`)
- **database_tools.py**: 基本的なデータベース操作ツール
  - `run_query(sql)`: SQLを実行し、結果を返します
  - `connect(db_id)`: BIRDデータセット内の特定のデータベースに接続します
  - `list_tables(database)`: テーブル一覧を取得します（第4回で追加）
  - `describe_tables(table_full_names)`: テーブルのスキーマ詳細を取得します（第4回で追加）

- **database_tools_with_knowledges.py**: 知識を含むツール（第4回で追加）
  - 上記のツールに加えて、テーブル・カラムに紐づく知識情報を返します

### 3. 評価システム (`src/sql_agent/eval/eval_bird.py`)
- BIRDデータセット（mini_dev）の質問に対してエージェントを実行し、生成されたSQLの実行結果を正解データと比較します。

### 4. 知識管理システム（第4回で追加）
- **知識データベース** (`duckdb/knowledges.duckdb`)
  - テーブル・カラムに紐づく知識を格納
  - 種別（definition, metric, ruleなど）、タイトル、内容を管理
- **知識抽出ツール** (`src/sql_agent/load_bird_knowledges.py`)
  - BIRDデータセットの補助情報（evidence）からテーブル・カラムに紐づく知識を抽出
  - LLMを使って質問ごとのヒントを構造化された知識に変換

## 📁 ディレクトリ構成

```
sql_agent/
├── agents/
│   ├── naive_agent/           # 最も単純なSQLエージェント（第3回）
│   ├── basic_agent/           # テーブル構造情報を利用するエージェント（第4回）
│   └── semantic_agent/        # 知識を活用するエージェント（第4回）
├── src/sql_agent/
│   ├── tools/                 # データベース接続・操作ツール
│   │   ├── database_tools.py              # 基本ツール
│   │   └── database_tools_with_knowledges.py  # 知識付きツール（第4回）
│   ├── eval/                  # 評価スクリプト
│   └── load_bird_knowledges.py  # 知識抽出ツール（第4回）
├── data/bird/minidev/         # BIRDデータセット（配置場所）
└── duckdb/                    # DuckDBワークスペース
    └── knowledges.duckdb      # 知識データベース（第4回）
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
ブラウザで `http://localhost:8000` にアクセスし、利用したいエージェントを選択してください。
- `naive_agent`: 最も単純なエージェント
- `basic_agent`: テーブル構造情報を利用
- `semantic_agent`: 知識を活用（事前に知識の抽出が必要）

### 2. 知識の抽出（semantic_agentを使う場合）
BIRDデータセットの補助情報から知識を抽出し、データベースに保存します。

```bash
# 特定のデータベースの知識を抽出
uv run load-bird-knowledges --database debit_card_specializing

# すべてのデータベースの知識を抽出
uv run load-bird-knowledges --all
```

実行後、`duckdb/knowledges.duckdb` に知識が保存されます。

### 3. 評価の実行
BIRDデータセットを用いてエージェントの性能を評価します。

```bash
# 最初の3問だけテスト実行
uv run eval-bird --agent naive_agent --limit 3

# basic_agent で評価
uv run eval-bird --agent basic_agent --limit 10

# semantic_agent で評価（知識を利用）
uv run eval-bird --agent semantic_agent --limit 10

# 補助情報（evidence）を含めて評価
uv run eval-bird --agent basic_agent --include-evidence --limit 10

# 失敗理由をLLMで分析（オプション）
uv run eval-bird --agent basic_agent --analyze-failures --limit 3
```

**主な評価オプション**:
- `--agent`: 使用するエージェント（naive_agent, basic_agent, semantic_agent）
- `--limit`: 評価する質問数
- `--include-evidence`: BIRDの補助情報を質問に含める
- `--analyze-failures`: 失敗した質問の原因をLLMで分析
