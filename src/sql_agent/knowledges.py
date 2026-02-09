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
            database_name VARCHAR NOT NULL,
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
            database_name VARCHAR NOT NULL,
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
    database_name: str,
    table_full_names: list[str],
    column_names: list[str],
    kind: str,
    content: str,
    title: str | None = None,
    source: str | None = None,
    schema: str | None = None,
) -> None:
    """knowledges に1行挿入する。updated_at=now(), deleted_at=NULL。"""
    schema = schema or config.KNOWLEDGES_SCHEMA
    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        f"""
        INSERT INTO "{schema}".knowledges (
            database_name, table_full_names, column_names, kind, title, content, source, updated_at, deleted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?::TIMESTAMP, NULL)
        """,
        [database_name, table_full_names, column_names, kind, title or None, content, source or None, now],
    )


def get_by_database(
    con: duckdb.DuckDBPyConnection,
    database_name: str,
    table_full_names: list[str] | None = None,
    schema: str | None = None,
) -> list[dict[str, Any]]:
    """
    指定データベースの knowledges を取得。deleted_at IS NULL のみ。
    table_full_names を指定した場合、そのテーブルいずれかに紐づく行だけ返す
    （行の table_full_names と引数の table_full_names に共通要素があるもの）。
    """
    schema = schema or config.KNOWLEDGES_SCHEMA
    con.execute(
        f'SELECT database_name, table_full_names, column_names, kind, title, content, source FROM "{schema}".knowledges WHERE database_name = ? AND deleted_at IS NULL',
        [database_name],
    )
    rows = con.fetchall()
    columns = ["database_name", "table_full_names", "column_names", "kind", "title", "content", "source"]
    result = [dict(zip(columns, row)) for row in rows]
    if table_full_names:
        want = set(table_full_names)
        result = [r for r in result if want & set(r["table_full_names"])]
    return result
