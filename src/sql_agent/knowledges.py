"""
Knowledges ストア（スキーマ・INSERT・取得）。

list_tables / describe_tables へのマージは database_tools_with_knowledges 側で実施。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import duckdb

from sql_agent import config


def ensure_attached(con: duckdb.DuckDBPyConnection) -> None:
    """メイン DuckDB 接続に knowledges 用 DB を ATTACH し、テーブルが無ければ作成する。"""
    schema = config.KNOWLEDGES_SCHEMA
    path = str(config.KNOWLEDGES_DUCKDB_PATH)
    con.execute(f"ATTACH IF NOT EXISTS '{path}' AS {schema} (TYPE duckdb)")
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS "{schema}".knowledges (
            scope VARCHAR NOT NULL,
            table_full_names VARCHAR[] NOT NULL,
            column_names VARCHAR[] NOT NULL,
            kind VARCHAR NOT NULL,
            title VARCHAR,
            content VARCHAR NOT NULL,
            source VARCHAR,
            updated_at TIMESTAMP NOT NULL,
            deleted_at TIMESTAMP
        )
    """)


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """knowledges テーブルを未作成なら作成する。"""
    con.execute("""
        CREATE TABLE IF NOT EXISTS knowledges (
            scope VARCHAR NOT NULL,
            table_full_names VARCHAR[] NOT NULL,
            column_names VARCHAR[] NOT NULL,
            kind VARCHAR NOT NULL,
            title VARCHAR,
            content VARCHAR NOT NULL,
            source VARCHAR,
            updated_at TIMESTAMP NOT NULL,
            deleted_at TIMESTAMP
        )
    """)


def insert(
    con: duckdb.DuckDBPyConnection,
    scope: str,
    table_full_names: list[str],
    column_names: list[str],
    kind: str,
    content: str,
    title: str | None = None,
    source: str | None = None,
    schema: str | None = None,
) -> None:
    """
    knowledges に1行挿入する。

    Args:
        scope: スコープ（スキーマ名またはデータベース名）。
            BIRDの場合はデータベース名、thelook/dbtの場合はスキーマ名。
        table_full_names: この知識が関連するテーブルの完全修飾名のリスト。
        column_names: この知識が関連するカラムの完全修飾名のリスト。
        kind: 知識の種類（"description", "evidence", "metric", "test", "relation"など）。
        content: 知識の内容。
        title: 知識のタイトル（任意）。
        source: 知識の出所（"bird", "dbt_manifest"など、任意）。
        schema: knowledgesテーブルが存在するスキーマ名。

    Note:
        updated_at は現在時刻、deleted_at は NULL で挿入される。
    """
    schema = schema or config.KNOWLEDGES_SCHEMA
    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        f"""
        INSERT INTO "{schema}".knowledges (
            scope, table_full_names, column_names, kind, title, content, source, updated_at, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?::TIMESTAMP, NULL)
        """,
        [scope, table_full_names, column_names, kind, title or None, content, source or None, now],
    )


def get_by_database(
    con: duckdb.DuckDBPyConnection,
    scope: str | None = None,
    table_full_names: list[str] | None = None,
    schema: str | None = None,
) -> list[dict[str, Any]]:
    """
    knowledges を取得。deleted_at IS NULL のみ。

    Args:
        scope: スコープ（データソース名またはデータベース名）。
            BIRDの場合はデータベース名（例: "debit_card_specializing"）、
            dbtの場合はプロジェクト名（例: "thelook"）。
            省略時は全スコープを対象とする。
        table_full_names: 特定のテーブルに絞り込む場合、テーブル完全修飾名のリスト。
        schema: knowledgesテーブルが存在するスキーマ名。

    Returns:
        条件に一致するknowledgesのリスト。
        table_full_names を指定した場合、そのテーブルいずれかに紐づく行だけ返す。
    """
    schema = schema or config.KNOWLEDGES_SCHEMA
    if scope:
        con.execute(
            f'SELECT scope, table_full_names, column_names, kind, title, content, source FROM "{schema}".knowledges WHERE scope = ? AND deleted_at IS NULL',
            [scope],
        )
    else:
        con.execute(
            f'SELECT scope, table_full_names, column_names, kind, title, content, source FROM "{schema}".knowledges WHERE deleted_at IS NULL',
        )
    rows = con.fetchall()
    columns = ["scope", "table_full_names", "column_names", "kind", "title", "content", "source"]
    result = [dict(zip(columns, row)) for row in rows]
    if table_full_names:
        want = set(table_full_names)
        result = [r for r in result if want & set(r["table_full_names"])]
    return result
