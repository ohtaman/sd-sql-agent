"""
DatabaseToolsWithDiscovery - 探索機能付きデータベースツール（第6回）

DatabaseToolsWithKnowledges を継承し、以下の機能を追加します:
- list_tables: intermediate 層を除外
- search_knowledge: knowledges テーブルのキーワード検索
"""

from typing import Any, Dict, List

from sql_agent import config
from sql_agent.knowledges import ensure_attached, get_by_database, search_knowledge as _search_knowledge
from sql_agent.tools.database_tools_with_knowledges import DatabaseToolsWithKnowledges

# intermediate 層はエージェントに見せない
_EXCLUDED_SCHEMAS = {"intermediate"}


class DatabaseToolsWithDiscovery(DatabaseToolsWithKnowledges):
    """
    DatabaseToolsWithKnowledges のサブクラス。

    list_tables から intermediate 層を除外し、
    search_knowledge ツールを追加します。
    """

    def list_tables(self, scope: str = None) -> List[Dict[str, Any]]:
        """
        テーブル一覧を取得する。intermediate 層は除外される。
        knowledge はテーブルの description のみに絞られる（カラムの description や
        relation, test は含まない）。

        Args:
            scope (str, optional): 対象のスコープ（スキーマ名またはデータベース名）を指定する。
                省略時は intermediate を除く全スコープを対象とする。

        Returns:
            List[Dict[str, Any]]: テーブル情報のリスト。
        """
        # 親の DatabaseTools.list_tables を呼ぶ（knowledge マージなし）
        from sql_agent.tools.database_tools import DatabaseTools
        ensure_attached(self.connection)
        raw_table_list = DatabaseTools.list_tables(self, scope)

        # テーブル完全修飾名を収集
        table_full_names = []
        for item in raw_table_list:
            name = item.get("full_name") or item.get("name")
            if name:
                if scope and "." not in name:
                    name = f"{scope}.{name}"
                table_full_names.append(name)

        # テーブルレベルの description のみ取得してマージ
        table_descriptions: Dict[str, str] = {}
        if table_full_names:
            knowledge_rows = get_by_database(
                self.connection, table_full_names=table_full_names, schema=config.KNOWLEDGES_SCHEMA
            )
            # テーブルレベル（column_names が空）の description だけ抽出
            for row in knowledge_rows:
                if row.get("kind") != "description":
                    continue
                if row.get("column_names"):
                    continue  # カラムレベルの description はスキップ
                for table_name in row.get("table_full_names") or []:
                    table_descriptions[table_name] = row["content"].strip()

        result = []
        for item in raw_table_list:
            full_name = item.get("full_name") or item.get("name") or ""
            knowledge = {}
            if full_name in table_descriptions:
                knowledge["description"] = table_descriptions[full_name]
            result.append({**item, "knowledge": knowledge})

        if scope:
            return result
        # scope 省略時は intermediate 層を除外
        return [
            item for item in result
            if not any(
                (item.get("full_name") or "").startswith(f"{excluded}.")
                for excluded in _EXCLUDED_SCHEMAS
            )
        ]

    def describe_tables(self, table_full_names: List[str]) -> Dict[str, Any]:
        """
        テーブルの構造情報を取得する。intermediate 層のテーブルは除外される。

        Args:
            table_full_names (List[str]): テーブル名（完全修飾名）のリスト

        Returns:
            Dict[str, Any]: テーブル名ごとの詳細情報。intermediate 層のテーブルは含まない。
        """
        # intermediate 層のテーブルを除外
        filtered = [
            name for name in table_full_names
            if not any(name.startswith(f"{excluded}.") for excluded in _EXCLUDED_SCHEMAS)
        ]
        if not filtered:
            return {}
        return super().describe_tables(filtered)

    def search_knowledge(self, query: str, scope: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        knowledges テーブルを keyword 検索し、マッチ数でランキングして返す。

        テーブルの説明やカラムの意味を調べたいときに使う。
        list_tables で全体像を掴んだ後、特定のキーワードに関連するテーブルを絞り込むのに有効。

        Args:
            query (str): 検索キーワード（例: "売上", "商品", "ユーザー"）
            scope (str, optional): スコープで絞り込む場合に指定（例: "thelook"）
            limit (int): 返却する最大件数（デフォルト: 10）

        Returns:
            List[Dict[str, Any]]: マッチ数降順でソートされた knowledges のリスト。
                各要素には table_full_names, title, content, kind, match_count が含まれる。
        """
        ensure_attached(self.connection)
        results = _search_knowledge(
            self.connection, query=query, scope=scope, limit=limit, schema=config.KNOWLEDGES_SCHEMA
        )
        # intermediate 層のknowledgeを除外
        return [
            r for r in results
            if not any(
                t.startswith(f"{excluded}.")
                for excluded in _EXCLUDED_SCHEMAS
                for t in (r.get("table_full_names") or [])
            )
        ]
