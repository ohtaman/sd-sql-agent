"""search_knowledge ツールのテスト。

インメモリ DuckDB にテストデータを投入し、keyword 検索とランキングの動作を確認する。
"""

from datetime import datetime, timezone

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
def con():
    """インメモリ DuckDB にknowledges テーブルを作成し、テストデータを投入する。"""
    connection = duckdb.connect(":memory:")
    init_schema(connection)

    # theLook のテストデータ（scope="thelook"）
    _insert_row(
        connection, "thelook", ["marts_core.fct_orders"], [],
        "description", "Table: fct_orders",
        "注文ファクトテーブル。各行は1件の注文を表す。主キーはorder_id。",
    )
    _insert_row(
        connection, "thelook", ["marts_finance.fct_daily_sales"], [],
        "description", "Table: fct_daily_sales",
        "日次売上ファクトテーブル。各行は1日の売上サマリを表す。売上は発送基準で計上。",
    )
    _insert_row(
        connection, "thelook", ["marts_finance.fct_daily_sales"],
        ["marts_finance.fct_daily_sales.revenue"],
        "description", "Column: fct_daily_sales.revenue",
        "日次売上。発送基準（Shipped, Complete）で計上。",
    )
    _insert_row(
        connection, "thelook", ["marts_core.dim_products"], [],
        "description", "Table: dim_products",
        "商品ディメンションテーブル。各行は1商品を表す。主キーはproduct_id。",
    )
    _insert_row(
        connection, "thelook", ["marts_finance.fct_product_margin"], [],
        "description", "Table: fct_product_margin",
        "商品別粗利ファクトテーブル。各行は1商品の累計粗利を表す。粗利はsale_price - costで算出。",
    )
    _insert_row(
        connection, "thelook", ["staging.stg_thelook__orders"], [],
        "description", "Table: stg_thelook__orders",
        "注文ステージングテーブル。ソーステーブル thelook_ecommerce.orders と1:1対応。",
    )
    # BIRD のテストデータ（別scope）
    _insert_row(
        connection, "debit_card_specializing",
        ["debit_card_specializing.customers"], [],
        "definition", "Currency codes",
        "Currency column uses EUR for Euro and CZK for Czech Koruna.",
    )

    yield connection
    connection.close()


class TestSearchKnowledge:
    """search_knowledge ツールのテスト。"""

    def test_keyword_search_returns_matching_results(self, con):
        """キーワードにマッチする knowledges が返される。"""
        from sql_agent.knowledges import search_knowledge

        results = search_knowledge(con, query="売上", scope="thelook")
        assert len(results) > 0
        # fct_daily_sales が含まれるはず（「売上」が content に複数回出現）
        table_names = [
            t for r in results for t in r["table_full_names"]
        ]
        assert "marts_finance.fct_daily_sales" in table_names

    def test_keyword_search_ranks_by_match_count(self, con):
        """マッチ数が多い順にランキングされる。"""
        from sql_agent.knowledges import search_knowledge

        results = search_knowledge(con, query="売上", scope="thelook")
        # match_count が降順であることを確認
        match_counts = [r["match_count"] for r in results]
        assert match_counts == sorted(match_counts, reverse=True)

    def test_keyword_search_respects_scope(self, con):
        """scope でフィルタされ、他の scope のデータは返さない。"""
        from sql_agent.knowledges import search_knowledge

        results = search_knowledge(con, query="Currency", scope="thelook")
        # thelook には Currency を含むデータがないので空
        assert len(results) == 0

        results = search_knowledge(
            con, query="Currency", scope="debit_card_specializing"
        )
        assert len(results) > 0

    def test_keyword_search_without_scope(self, con):
        """scope 省略時は全 scope から検索される。"""
        from sql_agent.knowledges import search_knowledge

        results = search_knowledge(con, query="テーブル")
        assert len(results) > 0

    def test_keyword_search_with_limit(self, con):
        """limit で返却件数を制限できる。"""
        from sql_agent.knowledges import search_knowledge

        results = search_knowledge(con, query="テーブル", scope="thelook", limit=2)
        assert len(results) <= 2

    def test_keyword_search_no_match(self, con):
        """マッチしないキーワードでは空リストが返る。"""
        from sql_agent.knowledges import search_knowledge

        results = search_knowledge(con, query="存在しないキーワード", scope="thelook")
        assert len(results) == 0

    def test_keyword_search_returns_expected_fields(self, con):
        """返却結果に必要なフィールドが含まれている。"""
        from sql_agent.knowledges import search_knowledge

        results = search_knowledge(con, query="売上", scope="thelook")
        assert len(results) > 0
        row = results[0]
        assert "table_full_names" in row
        assert "title" in row
        assert "content" in row
        assert "kind" in row
        assert "match_count" in row
