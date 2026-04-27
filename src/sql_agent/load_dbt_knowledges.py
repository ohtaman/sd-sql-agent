"""
dbt の manifest.json からメタデータを読み込んで knowledges テーブルに投入する CLI。

実行例:
  uv run load-dbt-knowledges
  uv run load-dbt-knowledges --dbt-project ./my_dbt_project
  uv run load-dbt-knowledges --manifest ./path/to/manifest.json --source-name my_project
  uv run load-dbt-knowledges --replace  # 既存データを削除してから投入
"""

import json
from pathlib import Path
from typing import Literal, Optional

import click
import duckdb

from sql_agent import config
from sql_agent.knowledges import ensure_attached, insert as knowledges_insert


def load_manifest(dbt_project_path: Path) -> dict:
    """dbt manifest.jsonを読み込む"""
    manifest_path = dbt_project_path / "target" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found at {manifest_path}")

    with open(manifest_path) as f:
        return json.load(f)


def extract_model_metadata(manifest: dict) -> list[dict]:
    """
    manifestからモデルのメタデータを抽出。

    返り値の各要素:
        {
            "model_name": "fct_daily_revenue",
            "schema": "marts_finance",
            "table_description": "日次売上ファクトテーブル...",
            "columns": {
                "revenue": "日次売上。order_itemsのsale_priceを合計...",
                ...
            },
            "lineage": {
                "parents": ["stg_thelook__order_items"],
                "children": []
            },
            "tests": {
                "order_id": ["unique", "not_null"],
                "status": ["accepted_values: ['Processing', 'Shipped', ...]"],
                ...
            }
        }
    """
    models = []

    # まず、すべてのテスト情報を収集
    tests_by_model = {}  # model_id -> {column_name: [test_descriptions]}
    for node_id, node in manifest["nodes"].items():
        if node["resource_type"] != "test":
            continue

        # このテストがどのモデルに関連するか
        attached_node = node.get("attached_node")
        if not attached_node:
            continue

        test_metadata = node.get("test_metadata", {})
        test_name = test_metadata.get("name")
        column_name = node.get("column_name")

        if not test_name or not column_name:
            continue

        # テストの説明を作成
        if test_name == "accepted_values":
            # accepted_values の場合、許可される値のリストを取得
            # v1.8以降は arguments プロパティ配下、それ以前は kwargs 直下
            kwargs = test_metadata.get("kwargs", {})
            # arguments プロパティがあればそこから、なければ kwargs 直下から取得
            arguments = kwargs.get("arguments", kwargs)
            values = arguments.get("values", [])
            test_desc = f"accepted_values: {values}"
        else:
            test_desc = test_name

        # モデルごと、カラムごとにテストを集約
        if attached_node not in tests_by_model:
            tests_by_model[attached_node] = {}
        if column_name not in tests_by_model[attached_node]:
            tests_by_model[attached_node][column_name] = []
        tests_by_model[attached_node][column_name].append(test_desc)

    # モデル情報を抽出
    for node_id, node in manifest["nodes"].items():
        if node["resource_type"] != "model":
            continue

        # 親子関係
        parents = manifest["parent_map"].get(node_id, [])
        children = manifest["child_map"].get(node_id, [])

        # 親子のモデル名のみ抽出（"model.project.xxx" → "xxx"）
        parent_names = [p.split(".")[-1] for p in parents if p.startswith("model.")]
        child_names = [c.split(".")[-1] for c in children if c.startswith("model.")]

        models.append({
            "model_name": node["name"],
            "schema": node["schema"],
            "database": node.get("database", ""),
            "table_description": node.get("description", ""),
            "columns": {
                col_name: col_data.get("description", "")
                for col_name, col_data in node.get("columns", {}).items()
            },
            "lineage": {
                "parents": parent_names,
                "children": child_names,
            },
            "tests": tests_by_model.get(node_id, {})
        })

    return models


def insert_model_knowledges(
    con: duckdb.DuckDBPyConnection,
    scope: str,
    model: dict,
    schema: str,
    source_name: str = "dbt_manifest",
) -> int:
    """
    1つのモデルのメタデータをknowledgesテーブルに投入する。

    Args:
        scope: knowledgesテーブルのscopeカラムに格納する値。
            dbtプロジェクト名（例: "thelook"）を指定する。
        model: dbtモデルのメタデータ
        schema: knowledgesテーブルのスキーマ名
        source_name: knowledgesテーブルのsourceカラムに格納する値

    Returns:
        挿入した行数
    """
    count = 0

    # テーブルの完全修飾名 (dbt_schema.table_name の2階層形式)
    # list_tables()が返す形式と一致させる: staging.stg_thelook__orders
    dbt_schema = model['schema']  # staging, marts_finance, etc.
    table_full_name = f"{dbt_schema}.{model['model_name']}"

    # 1. テーブルdescription
    if model.get("table_description"):
        knowledges_insert(
            con,
            scope=scope,
            table_full_names=[table_full_name],
            column_names=[],
            kind="description",
            content=model["table_description"],
            title=f"Table: {model['model_name']}",
            source=source_name,
            schema=schema,
        )
        count += 1

    # 2. カラムdescription
    for col_name, col_desc in model.get("columns", {}).items():
        if col_desc:
            # カラムの完全修飾名: schema.table_name.column_name (3階層)
            col_full_name = f"{table_full_name}.{col_name}"
            knowledges_insert(
                con,
                scope=scope,
                table_full_names=[table_full_name],
                column_names=[col_full_name],
                kind="description",
                content=col_desc,
                title=f"Column: {model['model_name']}.{col_name}",
                source=source_name,
                schema=schema,
            )
            count += 1

    # 3. Lineage情報
    lineage = model.get("lineage", {})
    if lineage.get("parents") or lineage.get("children"):
        lineage_text = f"Dependencies: parents={lineage.get('parents', [])}, children={lineage.get('children', [])}"
        knowledges_insert(
            con,
            scope=scope,
            table_full_names=[table_full_name],
            column_names=[],
            kind="relation",
            content=lineage_text,
            title=f"Lineage: {model['model_name']}",
            source=source_name,
            schema=schema,
        )
        count += 1

    # 4. データテスト情報
    for col_name, test_list in model.get("tests", {}).items():
        if test_list:
            # カラムの完全修飾名: schema.table_name.column_name (3階層)
            col_full_name = f"{table_full_name}.{col_name}"
            # テストのリストを1つの文字列に
            tests_text = ", ".join(test_list)
            knowledges_insert(
                con,
                scope=scope,
                table_full_names=[table_full_name],
                column_names=[col_full_name],
                kind="test",
                content=tests_text,
                title=f"Tests: {model['model_name']}.{col_name}",
                source=source_name,
                schema=schema,
            )
            count += 1

    return count


@click.command()
@click.option(
    "--dbt-project",
    "dbt_project_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="dbtプロジェクトのパス（省略時はカレントディレクトリからdbt_thelookを探す）",
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="manifest.jsonファイルを直接指定（--dbt-projectより優先）",
)
@click.option(
    "--source-name",
    default="dbt_manifest",
    help="knowledgesテーブルのsourceカラムに格納する値（複数プロジェクト識別用、デフォルト: dbt_manifest）",
)
@click.option(
    "--replace",
    is_flag=True,
    help="指定されたsource-name由来のknowledgesを削除してから投入",
)
def main(
    dbt_project_path: Optional[Path],
    manifest_path: Optional[Path],
    source_name: str,
    replace: bool,
) -> None:
    """dbt の manifest.json からメタデータを読み込んで knowledges に投入する。"""

    # manifest.jsonの取得
    if manifest_path is not None:
        # manifest.jsonを直接指定された場合
        if not manifest_path.exists():
            click.echo(f"Error: manifest.json not found at {manifest_path}", err=True)
            raise SystemExit(1)
        click.echo(f"Loading manifest from: {manifest_path}")
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        # dbtプロジェクトパスから探す
        if dbt_project_path is None:
            # デフォルト: カレントディレクトリのdbt_thelook
            dbt_project_path = Path.cwd() / "dbt_thelook"

        if not dbt_project_path.exists():
            click.echo(f"Error: dbt project directory not found at {dbt_project_path}", err=True)
            raise SystemExit(1)

        click.echo(f"Loading dbt metadata from: {dbt_project_path}")

        # manifest.json読み込み
        try:
            manifest = load_manifest(dbt_project_path)
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            click.echo("\nPlease run 'dbt compile' or 'dbt run' first to generate manifest.json", err=True)
            raise SystemExit(1)

    # モデルメタデータ抽出
    models = extract_model_metadata(manifest)
    click.echo(f"Found {len(models)} dbt models")

    if not models:
        click.echo("No models found in manifest.json")
        return

    # データベース接続
    con = duckdb.connect(str(config.DUCKDB_PATH))
    ensure_attached(con)
    schema = config.KNOWLEDGES_SCHEMA

    # 既存データの削除（--replaceオプション時）
    if replace:
        con.execute(
            f'DELETE FROM "{schema}".knowledges WHERE source = ?',
            [source_name]
        )
        click.echo(f"Deleted existing '{source_name}' knowledges")

    # モデルごとにknowledges挿入
    total_count = 0
    for model in models:
        scope = model.get("database") or "unknown"
        count = insert_model_knowledges(con, scope, model, schema, source_name)
        total_count += count

    con.close()

    click.echo(f"Successfully inserted {total_count} knowledge entries from {len(models)} models")
    click.echo("Done.")


if __name__ == "__main__":
    main()
