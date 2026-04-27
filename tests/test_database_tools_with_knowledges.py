"""database_tools_with_knowledges のマージロジックテスト。

scope="thelook" の knowledges が、list_tables / describe_tables で
正しくマージされることを確認する。
"""

from datetime import datetime, timezone
from unittest.mock import patch

import duckdb
import pytest

from sql_agent.knowledges import init_schema


def _insert_row(con, scope, table_full_names, column_names, kind, title, content):
    """テスト用: インメモリ knowledges テーブルに直接 INSERT する。"""
    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        """
        INSERT INTO knowledges (scope, table_full_names, column_names, kind, title, content, source, updated_at, deleted_at)
        VALUES (?, ?, ?, ?, ?, ?, 'test', ?::TIMESTAMP, NULL)
        """,
        [scope, table_full_names, column_names, kind, title, content, now],
    )


@pytest.fixture
def con_with_tables_and_knowledges():
    """
    インメモリ DuckDB に:
    - marts_core / staging スキーマとテーブル
    - knowledges テーブル（scope="thelook"）
    を作成する。
    """
    connection = duckdb.connect(":memory:")

    # テーブルを作成（theLook の構造を模倣）
    connection.execute("CREATE SCHEMA marts_core")
    connection.execute("CREATE SCHEMA staging")
    connection.execute("""
        CREATE TABLE marts_core.dim_products (
            product_id INTEGER,
            product_name VARCHAR
        )
    """)
    connection.execute("""
        CREATE TABLE marts_core.fct_orders (
            order_id INTEGER,
            user_id INTEGER
        )
    """)
    connection.execute("""
        CREATE TABLE staging.stg_thelook__orders (
            order_id INTEGER,
            user_id INTEGER,
            order_status VARCHAR
        )
    """)

    # knowledges テーブル（scope="thelook"）
    init_schema(connection)
    _insert_row(
        connection, "thelook", ["marts_core.dim_products"], [],
        "description", "Table: dim_products",
        "商品ディメンションテーブル。各行は1商品を表す。",
    )
    _insert_row(
        connection, "thelook", ["marts_core.dim_products"],
        ["marts_core.dim_products.product_id"],
        "description", "Column: dim_products.product_id",
        "商品の一意識別子（主キー）",
    )
    _insert_row(
        connection, "thelook", ["marts_core.fct_orders"], [],
        "description", "Table: fct_orders",
        "注文ファクトテーブル。各行は1件の注文を表す。",
    )
    _insert_row(
        connection, "thelook", ["staging.stg_thelook__orders"], [],
        "description", "Table: stg_thelook__orders",
        "注文ステージングテーブル。",
    )

    yield connection
    connection.close()


def _make_tools(con):
    """テスト用の DatabaseToolsWithKnowledges インスタンスを作る。"""
    from sql_agent.tools.database_tools_with_knowledges import DatabaseToolsWithKnowledges

    tools = DatabaseToolsWithKnowledges.__new__(DatabaseToolsWithKnowledges)
    tools._connection = con
    tools._duckdb_path = ":memory:"
    tools._attached_dbs = set()
    return tools


@pytest.fixture(autouse=True)
def _mock_knowledges_schema():
    """config.KNOWLEDGES_SCHEMA をモックし、インメモリの knowledges テーブルを直接参照させる。"""
    with patch("sql_agent.tools.database_tools_with_knowledges.config") as mock_tools_config, \
         patch("sql_agent.knowledges.config") as mock_knowledges_config, \
         patch("sql_agent.tools.database_tools_with_knowledges.ensure_attached"):
        mock_tools_config.KNOWLEDGES_SCHEMA = "main"
        mock_knowledges_config.KNOWLEDGES_SCHEMA = "main"
        yield


class TestKnowledgeMergeWithNewScope:
    """scope="thelook" の knowledges が list_tables / describe_tables でマージされるかテスト。"""

    def test_list_tables_with_scope_merges_knowledges(self, con_with_tables_and_knowledges):
        """list_tables(scope="marts_core") で scope="thelook" の knowledges がマージされる。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables(scope="marts_core")

        # dim_products と fct_orders が返る
        table_names = [r.get("full_name") or r.get("name") for r in result]
        assert "marts_core.dim_products" in table_names
        assert "marts_core.fct_orders" in table_names

        # knowledges がマージされている
        dim_products = [r for r in result if r.get("full_name") == "marts_core.dim_products"][0]
        assert "knowledge" in dim_products
        assert "description" in dim_products["knowledge"]
        assert "商品ディメンション" in dim_products["knowledge"]["description"]

    def test_list_tables_staging_scope_merges_knowledges(self, con_with_tables_and_knowledges):
        """list_tables(scope="staging") でも scope="thelook" の knowledges がマージされる。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables(scope="staging")

        table_names = [r.get("full_name") or r.get("name") for r in result]
        assert "staging.stg_thelook__orders" in table_names

        stg_orders = [r for r in result if r.get("full_name") == "staging.stg_thelook__orders"][0]
        assert "knowledge" in stg_orders
        assert "description" in stg_orders["knowledge"]
        assert "ステージング" in stg_orders["knowledge"]["description"]

    def test_describe_tables_merges_knowledges(self, con_with_tables_and_knowledges):
        """describe_tables で scope="thelook" の knowledges がマージされる。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.describe_tables(["marts_core.dim_products"])

        assert "marts_core.dim_products" in result
        table_info = result["marts_core.dim_products"]
        assert "knowledge" in table_info
        assert "description" in table_info["knowledge"]
        assert "商品ディメンション" in table_info["knowledge"]["description"]

        # カラムレベルの knowledge もマージされている
        columns = table_info["columns"]
        product_id_col = [c for c in columns if c.get("column_name") == "product_id"][0]
        assert "knowledge" in product_id_col
        assert "description" in product_id_col["knowledge"]
        assert "主キー" in product_id_col["knowledge"]["description"]
