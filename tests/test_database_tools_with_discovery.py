"""DatabaseToolsWithDiscovery のテスト。

- list_tables が intermediate 層を除外すること
- search_knowledge が動作すること
を確認する。
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
    """インメモリ DuckDB にテーブルと knowledges を作成する。"""
    connection = duckdb.connect(":memory:")

    # テーブル作成（theLook の構造を模倣）
    connection.execute("CREATE SCHEMA marts_core")
    connection.execute("CREATE SCHEMA marts_finance")
    connection.execute("CREATE SCHEMA intermediate")
    connection.execute("CREATE SCHEMA staging")

    connection.execute("CREATE TABLE marts_core.dim_products (product_id INTEGER, product_name VARCHAR)")
    connection.execute("CREATE TABLE marts_core.fct_orders (order_id INTEGER, user_id INTEGER)")
    connection.execute("CREATE TABLE marts_finance.fct_daily_sales (sales_date DATE, revenue DOUBLE)")
    connection.execute("CREATE TABLE intermediate.int_order_items_with_products (order_item_id INTEGER)")
    connection.execute("CREATE TABLE staging.stg_thelook__orders (order_id INTEGER)")

    # knowledges テーブル
    init_schema(connection)
    _insert_row(
        connection, "thelook", ["marts_core.dim_products"], [],
        "description", "Table: dim_products",
        "商品ディメンションテーブル。各行は1商品を表す。",
    )
    _insert_row(
        connection, "thelook", ["marts_core.fct_orders"], [],
        "description", "Table: fct_orders",
        "注文ファクトテーブル。各行は1件の注文を表す。",
    )
    _insert_row(
        connection, "thelook", ["marts_finance.fct_daily_sales"], [],
        "description", "Table: fct_daily_sales",
        "日次売上ファクトテーブル。売上は発送基準で計上。",
    )
    _insert_row(
        connection, "thelook", ["marts_finance.fct_daily_sales"],
        ["marts_finance.fct_daily_sales.revenue"],
        "description", "Column: fct_daily_sales.revenue",
        "日次売上。発送基準で計上。",
    )
    _insert_row(
        connection, "thelook", ["marts_finance.fct_daily_sales"], [],
        "relation", "Lineage: fct_daily_sales",
        "Dependencies: parents=['int_order_items_with_products'], children=[]",
    )
    _insert_row(
        connection, "thelook", ["intermediate.int_order_items_with_products"], [],
        "description", "Table: int_order_items_with_products",
        "注文明細と商品マスタを結合した中間テーブル。",
    )

    yield connection
    connection.close()


def _make_tools(con):
    """テスト用の DatabaseToolsWithDiscovery インスタンスを作る。"""
    from sql_agent.tools.database_tools_with_discovery import DatabaseToolsWithDiscovery

    tools = DatabaseToolsWithDiscovery.__new__(DatabaseToolsWithDiscovery)
    tools._connection = con
    tools._duckdb_path = ":memory:"
    tools._attached_dbs = set()
    return tools


@pytest.fixture(autouse=True)
def _mock_config():
    """config をモックする。"""
    with patch("sql_agent.tools.database_tools_with_knowledges.config") as mock_tools_config, \
         patch("sql_agent.tools.database_tools_with_discovery.config") as mock_discovery_config, \
         patch("sql_agent.knowledges.config") as mock_knowledges_config, \
         patch("sql_agent.tools.database_tools_with_knowledges.ensure_attached"), \
         patch("sql_agent.tools.database_tools_with_discovery.ensure_attached"):
        mock_tools_config.KNOWLEDGES_SCHEMA = "main"
        mock_discovery_config.KNOWLEDGES_SCHEMA = "main"
        mock_knowledges_config.KNOWLEDGES_SCHEMA = "main"
        yield


class TestListTablesExcludesIntermediate:
    """list_tables が intermediate 層を除外するかテスト。"""

    def test_list_tables_with_marts_scope(self, con_with_tables_and_knowledges):
        """marts_core を指定すると marts_core のテーブルのみ返る。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables(scope="marts_core")

        table_names = [r.get("full_name") for r in result]
        assert "marts_core.dim_products" in table_names
        assert "marts_core.fct_orders" in table_names

    def test_list_tables_excludes_intermediate(self, con_with_tables_and_knowledges):
        """scope 省略時に intermediate 層のテーブルが含まれない。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables()

        table_names = [r.get("full_name") for r in result]
        assert "intermediate.int_order_items_with_products" not in table_names

    def test_list_tables_staging_scope(self, con_with_tables_and_knowledges):
        """staging を指定すると staging のテーブルが返る。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables(scope="staging")

        table_names = [r.get("full_name") for r in result]
        assert "staging.stg_thelook__orders" in table_names

    def test_list_tables_intermediate_scope_still_works(self, con_with_tables_and_knowledges):
        """intermediate を明示的に指定すれば返る（除外は scope 省略時のみ）。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables(scope="intermediate")

        table_names = [r.get("full_name") for r in result]
        assert "intermediate.int_order_items_with_products" in table_names

    def test_list_tables_merges_knowledges(self, con_with_tables_and_knowledges):
        """list_tables の結果に knowledges がマージされている。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables(scope="marts_core")

        dim_products = [r for r in result if r.get("full_name") == "marts_core.dim_products"][0]
        assert "knowledge" in dim_products
        assert "description" in dim_products["knowledge"]

    def test_list_tables_knowledge_only_table_description(self, con_with_tables_and_knowledges):
        """list_tables の knowledge にはテーブルの description のみ含まれる。
        カラムの description や relation, test は含まない。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.list_tables(scope="marts_finance")

        fct_daily_sales = [r for r in result if r.get("full_name") == "marts_finance.fct_daily_sales"][0]
        knowledge = fct_daily_sales.get("knowledge", {})
        # テーブルの description は含まれる
        assert "description" in knowledge
        assert "日次売上ファクトテーブル" in knowledge["description"]
        # カラムの description が混在していない（カラム revenue の description は「日次売上。発送基準で計上。」）
        assert "日次売上。発送基準で計上。" not in knowledge["description"]
        # relation は含まれない
        assert "relation" not in knowledge


class TestDescribeTablesExcludesIntermediate:
    """describe_tables が intermediate 層を除外するかテスト。"""

    def test_describe_tables_excludes_intermediate(self, con_with_tables_and_knowledges):
        """intermediate 層のテーブルを describe_tables すると空（またはエラー）が返る。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.describe_tables(["intermediate.int_order_items_with_products"])

        # intermediate のテーブルは結果に含まれない
        assert "intermediate.int_order_items_with_products" not in result

    def test_describe_tables_marts_still_works(self, con_with_tables_and_knowledges):
        """marts 層のテーブルは describe_tables で正常に返る。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        result = tools.describe_tables(["marts_core.dim_products"])

        assert "marts_core.dim_products" in result
        assert "knowledge" in result["marts_core.dim_products"]


class TestSearchKnowledge:
    """search_knowledge メソッドのテスト。"""

    def test_search_returns_results(self, con_with_tables_and_knowledges):
        """キーワード検索で結果が返る。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        results = tools.search_knowledge(query="売上")

        assert len(results) > 0

    def test_search_finds_by_column_description(self, con_with_tables_and_knowledges):
        """カラムの説明文からテーブルを見つけられる。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        results = tools.search_knowledge(query="発送基準")

        table_names = [t for r in results for t in r["table_full_names"]]
        assert "marts_finance.fct_daily_sales" in table_names

    def test_search_excludes_intermediate(self, con_with_tables_and_knowledges):
        """intermediate 層のknowledgeが検索結果に含まれない。"""
        tools = _make_tools(con_with_tables_and_knowledges)
        results = tools.search_knowledge(query="中間テーブル")

        table_names = [t for r in results for t in r["table_full_names"]]
        assert "intermediate.int_order_items_with_products" not in table_names
