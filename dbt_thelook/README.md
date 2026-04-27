# thelook_ecommerce dbtプロジェクト

Software Design連載「データ分析とSQLエージェント」第5回のサンプルdbtプロジェクトです。
BigQueryの公開データセット `thelook_ecommerce` を使用して、dbtの3層構成（staging/intermediate/marts）を実装しています。

## プロジェクト構成

```
dbt_thelook/
├── models/
│   ├── staging/
│   │   └── thelook/              # ソースと1:1、型変換・リネーム（4テーブル）
│   │       ├── sources.yml
│   │       ├── stg_thelook__users.sql / .yml
│   │       ├── stg_thelook__orders.sql / .yml
│   │       ├── stg_thelook__order_items.sql / .yml
│   │       └── stg_thelook__products.sql / .yml
│   ├── intermediate/             # 結合・中間処理（1テーブル）
│   │   ├── _intermediate__models.yml
│   │   └── int_order_items_with_products.sql
│   └── marts/                    # ビジネス領域別の最終成果物（6テーブル）
│       ├── core/                 # 共通ディメンション・ファクト（4テーブル）
│       │   ├── dim_users.sql / .yml
│       │   ├── dim_products.sql / .yml
│       │   ├── fct_orders.sql / .yml
│       │   └── fct_order_items.sql / .yml
│       └── finance/              # 財務分析用（2テーブル）
│           ├── fct_daily_sales.sql / .yml
│           └── fct_product_margin.sql / .yml
├── macros/
│   └── generate_schema_name.sql
├── dbt_project.yml
└── profiles.yml.example
```

**合計11テーブル**: staging 4 + intermediate 1 + marts 6

## セットアップ

### 1. 依存関係のインストール

```bash
# プロジェクトルートで実行
uv sync
```

### 2. プロファイル設定

`dbt_thelook` ディレクトリ内で `profiles.yml.example` をコピーし、GCPプロジェクトIDを設定します。

```bash
cd dbt_thelook
cp profiles.yml.example profiles.yml
# profiles.yml の <your_project_id> を自分のGCPプロジェクトIDに置き換える
```

`profiles.yml` はプロジェクトディレクトリ（`dbt_thelook/`）に配置します。dbt-duckdbはカレントディレクトリの `profiles.yml` を自動的に読み込みます。

### 3. BigQuery認証

```bash
gcloud auth login
gcloud auth application-default login
```

### 4. dbt動作確認

```bash
cd dbt_thelook
uv run dbt --version
```

## 実行方法

すべてのdbtコマンドは `uv run dbt ...` の形式で実行します。

### モデルのビルド

```bash
# 全モデルをビルド
uv run dbt run

# ビルド + テスト
uv run dbt build

# 特定のモデルをビルド
uv run dbt run --select fct_daily_sales
```

### テストの実行

```bash
# 全テストを実行
uv run dbt test

# 特定のモデルのテストのみ
uv run dbt test --select stg_thelook__users
```

### ドキュメント生成

```bash
uv run dbt docs generate
uv run dbt docs serve
```

## モデル説明

### Staging層（4テーブル）

ソースと1:1対応。型変換・カラム選択のみ実施。

- `stg_thelook__users`: ユーザーマスタ
- `stg_thelook__orders`: 注文ヘッダー
- `stg_thelook__order_items`: 注文明細
- `stg_thelook__products`: 商品マスタ

### Intermediate層（1テーブル）

JOINや中間処理。複数のmartsテーブルで再利用する処理を配置。

- `int_order_items_with_products`: 明細×商品の結合

### Marts層（6テーブル）

#### Core（4テーブル）

共通ディメンション・ファクト。

- `dim_users`: ユーザーディメンション（1行=1ユーザー）
- `dim_products`: 商品ディメンション（1行=1商品）
- `fct_orders`: 注文ファクト（1行=1注文）
- `fct_order_items`: 注文明細ファクト（1行=1明細）

#### Finance（2テーブル）

財務分析用のファクト。

- `fct_daily_sales`: 日次売上（1行=1日）
- `fct_product_margin`: 商品別粗利（1行=1商品）

## データソース

BigQuery公開データセット: `bigquery-public-data.thelook_ecommerce`

- **データ期間**: 2019年〜現在（継続更新中）
- **注文数**: 約125,000件
- **商品数**: 約30,000商品
- **ユーザー数**: 約100,000人

詳細は[Google Cloud公式ドキュメント](https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce)を参照。

## 参考資料

- [dbt Documentation](https://docs.getdbt.com/)
- [dbt Best Practices](https://docs.getdbt.com/guides/best-practices)
- [BigQuery Public Datasets](https://cloud.google.com/bigquery/public-data)
