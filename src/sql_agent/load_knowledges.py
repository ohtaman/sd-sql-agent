"""
YAML ファイルから knowledges テーブルにデータを投入する汎用 CLI。

実行例:
  uv run load-knowledges --file knowledges/metrics.yml --source-name semantic_layer
  uv run load-knowledges --file knowledges/metrics.yml --source-name semantic_layer --replace
  uv run load-knowledges --delete --source-name reference_query
"""

from pathlib import Path
from typing import Optional

import click
import duckdb
import yaml

from sql_agent import config
from sql_agent.knowledges import ensure_attached, insert as knowledges_insert


@click.command()
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="投入する YAML ファイルのパス",
)
@click.option(
    "--source-name",
    default="manual",
    help="knowledges テーブルの source カラムに格納する値（デフォルト: manual）",
)
@click.option(
    "--replace",
    is_flag=True,
    help="指定された source-name 由来の knowledges を削除してから投入",
)
@click.option(
    "--delete",
    is_flag=True,
    help="指定された source-name 由来の knowledges を削除のみ行う（--file 不要）",
)
def main(
    file_path: Optional[Path],
    source_name: str,
    replace: bool,
    delete: bool,
) -> None:
    """YAML ファイルから knowledges テーブルにデータを投入する。"""

    if not delete and file_path is None:
        click.echo("Error: --file is required unless --delete is specified", err=True)
        raise SystemExit(1)

    con = duckdb.connect(str(config.DUCKDB_PATH))
    ensure_attached(con)
    schema = config.KNOWLEDGES_SCHEMA

    # --delete or --replace: 対象 source のデータを削除
    if delete or replace:
        con.execute(
            f'DELETE FROM "{schema}".knowledges WHERE source = ?',
            [source_name],
        )
        click.echo(f"Deleted existing knowledges with source='{source_name}'")

    if delete:
        con.close()
        return

    # 投入
    with open(file_path) as f:
        entries = yaml.safe_load(f)

    if not isinstance(entries, list):
        click.echo("Error: YAML must be a list of entries", err=True)
        raise SystemExit(1)

    click.echo(f"Loading {len(entries)} entries from: {file_path}")

    count = 0
    for entry in entries:
        knowledges_insert(
            con,
            scope=entry["scope"],
            table_full_names=entry.get("table_full_names", []),
            column_names=entry.get("column_names", []),
            kind=entry["kind"],
            content=entry["content"],
            title=entry.get("title"),
            source=source_name,
            schema=schema,
        )
        count += 1

    con.close()
    click.echo(f"Successfully inserted {count} entries")


if __name__ == "__main__":
    main()
