"""
DatabaseToolsWithKnowledges - 知識付きデータベースツール

DatabaseTools を継承し、スキーマ取得系メソッド（list_tables, describe_tables）の結果に知識（Knowledges）を付与して返します。
これにより、Agent はデータベースの構造だけでなく、蓄積されたドメイン知識も同時に参照できます。
"""

from typing import Any, Dict, List

from sql_agent import config
from sql_agent.knowledges import ensure_attached, get_by_database
from sql_agent.tools.database_tools import DatabaseTools


class DatabaseToolsWithKnowledges(DatabaseTools):
    """
    DatabaseTools のサブクラス。

    list_tables および describe_tables メソッドをオーバーライドし、
    取得したスキーマ情報に対して get_by_database で取得した知識をマージして返します。
    """

    def list_tables(self, database: str = None) -> List[Dict[str, Any]]:
        """
        データベースのスキーマ情報に基づき、テーブル一覧を取得する。

        Args:
            database (str, optional): 対象データベース名を指定する。省略時は attach されている全 DB を対象とする。

        Returns:
            List[Dict[str, Any]]: テーブル情報のリスト。各要素に 'knowledge' キーが追加され、テーブルに関連する知識が格納される。
        """
        ensure_attached(self.connection)
        raw_table_list = super().list_tables(database)
        if database:
            table_full_names = []
            for item in raw_table_list:
                name = item.get("full_name") or item.get("name")
                if name:
                    if "." not in name:
                        name = f"{database}.{name}"
                    table_full_names.append(name)
            if not table_full_names:
                return raw_table_list
            knowledge_rows = get_by_database(
                self.connection, database, table_full_names=table_full_names, schema=config.KNOWLEDGES_SCHEMA
            )
            return self._enrich_list_tables(raw_table_list, knowledge_rows)
        # 引数なし（全 DB 対象）: DB ごとに knowledges を取得してマージ
        tables_by_db: Dict[str, List[str]] = {}
        for item in raw_table_list:
            full_name = item.get("full_name") or item.get("name") or ""
            if not full_name:
                continue
            if "." in full_name:
                db_name = full_name.split(".", 1)[0]
                tables_by_db.setdefault(db_name, []).append(full_name)
            else:
                tables_by_db.setdefault("", []).append(full_name)
        all_knowledge_rows: List[Dict[str, Any]] = []
        for db_name, names in tables_by_db.items():
            if not db_name:
                continue
            all_knowledge_rows.extend(
                get_by_database(
                    self.connection, db_name, table_full_names=names, schema=config.KNOWLEDGES_SCHEMA
                )
            )
        return self._enrich_list_tables(raw_table_list, all_knowledge_rows)

    def describe_tables(self, table_full_names: List[str]) -> Dict[str, Any]:
        """
        指定されたテーブルの構造情報（カラム名、データ型など）を取得し、ナレッジを付与する。

        Args:
            table_full_names (List[str]): 情報を取得したいテーブル名（完全修飾名）のリスト

        Returns:
            Dict[str, Any]: テーブル名ごとに詳細情報を格納した辞書。テーブルおよび各カラム情報に 'knowledge' キーが追加され、関連するナレッジが格納される。
        """

        ensure_attached(self.connection)
        raw_describe_result = super().describe_tables(table_full_names)
        # 先頭のテーブル名からデータベース名を取得（例: "db1.table1" -> "db1"）
        database_name = (
            table_full_names[0].split(".", 1)[0]
            if table_full_names and "." in table_full_names[0]
            else None
        )
        if not database_name:
            return raw_describe_result
        knowledge_rows = get_by_database(
            self.connection,
            database_name,
            table_full_names=list(raw_describe_result.keys()),
            schema=config.KNOWLEDGES_SCHEMA,
        )
        return self._enrich_describe_tables(raw_describe_result, knowledge_rows)

    def _enrich_list_tables(
        self, raw_table_list: List[Dict[str, Any]], knowledge_rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """生の list_tables 結果に knowledges をテーブル単位で載せる。"""
        # テーブル名ごとに、kind（種別）→ content のリスト にまとめる
        table_to_kind_contents: Dict[str, Dict[str, List[str]]] = {}
        for knowledge_row in knowledge_rows:
            for table_name in knowledge_row.get("table_full_names") or []:
                table_to_kind_contents.setdefault(table_name, {}).setdefault(
                    knowledge_row["kind"], []
                ).append(knowledge_row["content"].strip())
        # 完全修飾名のみのとき、短い名前でも lookup できるようにエイリアスを張る
        for table_name in list(table_to_kind_contents):
            if "." in table_name:
                short_name = table_name.split(".")[-1]
                if short_name not in table_to_kind_contents:
                    table_to_kind_contents[short_name] = table_to_kind_contents[table_name]

        def get_knowledge_for_table(table_full_name: str) -> Dict[str, str]:
            """テーブルに紐づく knowledges を kind → 結合した content の辞書で返す。
            完全修飾名でヒットしなければ短い名前（最後の . 以降）でも照合する。
            """
            key = table_full_name
            if key not in table_to_kind_contents and "." in table_full_name:
                key = table_full_name.split(".")[-1]
            if key not in table_to_kind_contents:
                return {}
            return {
                kind: "\n".join(contents).strip()
                for kind, contents in table_to_kind_contents[key].items()
            }

        result = []
        for table_item in raw_table_list:
            table_full_name = table_item.get("full_name") or table_item.get("name") or ""
            result.append({**table_item, "knowledge": get_knowledge_for_table(table_full_name)})
        return result

    def _enrich_describe_tables(
        self, raw_describe_result: Dict[str, Any], knowledge_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """生の describe_tables 結果に knowledges をテーブル・カラム単位で載せる。"""
        # テーブル名ごと・カラム名（完全修飾）ごとに、kind → content のリスト にまとめる
        table_to_kind_contents: Dict[str, Dict[str, List[str]]] = {}
        column_to_kind_contents: Dict[str, Dict[str, List[str]]] = {}
        for knowledge_row in knowledge_rows:
            for table_name in knowledge_row.get("table_full_names") or []:
                table_to_kind_contents.setdefault(table_name, {}).setdefault(
                    knowledge_row["kind"], []
                ).append(knowledge_row["content"].strip())
            for column_full_name in knowledge_row.get("column_names") or []:
                column_to_kind_contents.setdefault(column_full_name, {}).setdefault(
                    knowledge_row["kind"], []
                ).append(knowledge_row["content"].strip())

        def get_knowledge_from_index(
            kind_contents_index: Dict[str, Dict[str, List[str]]], key: str
        ) -> Dict[str, str]:
            """index から key に対応する knowledges を kind → 結合した content の辞書で返す。
            完全修飾名でヒットしなければ短い名前（最後の . 以降）でも照合する。
            """
            lookup_key = key
            if lookup_key not in kind_contents_index and "." in key:
                lookup_key = key.split(".")[-1]
            if lookup_key not in kind_contents_index:
                return {}
            return {
                kind: "\n".join(contents).strip()
                for kind, contents in kind_contents_index[lookup_key].items()
            }

        result: Dict[str, Any] = {}
        for table_name, column_list_or_error in raw_describe_result.items():
            table_knowledge = get_knowledge_from_index(table_to_kind_contents, table_name)
            # エラー時や想定外の型はそのまま載せて返す
            if isinstance(column_list_or_error, dict) and column_list_or_error.get("error"):
                result[table_name] = {"knowledge": table_knowledge, "columns": column_list_or_error}
                continue
            if not isinstance(column_list_or_error, list):
                result[table_name] = {"knowledge": table_knowledge, "columns": column_list_or_error}
                continue
            # 各カラムに knowledges を付与
            enriched_columns = []
            for column_info in column_list_or_error:
                if not isinstance(column_info, dict):
                    enriched_columns.append(column_info)
                    continue
                column_name = column_info.get("column_name") or column_info.get("name")
                column_full_name = f"{table_name}.{column_name}" if column_name else ""
                enriched_columns.append({
                    **column_info,
                    "knowledge": get_knowledge_from_index(
                        column_to_kind_contents, column_full_name
                    ),
                })
            result[table_name] = {"knowledge": table_knowledge, "columns": enriched_columns}
        return result
