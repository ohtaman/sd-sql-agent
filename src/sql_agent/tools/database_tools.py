"""
Database Tools - データベース接続・SQL 実行

設定は sql_agent.config を参照。DB_TYPE=bird のときは BIRD_PATH の dev_databases を DuckDB に attach する。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import duckdb

from sql_agent import config

logger = logging.getLogger(__name__)


class DatabaseTools:
    """データベースツール群（設定は config から取得）"""

    def __init__(self):
        self._duckdb_path = config.DUCKDB_PATH
        self._connection = None
        self._attached_dbs: set[str] = set()
        print(f"DatabaseTools: type={config.DB_TYPE}")

    @property
    def connection(self):
        """初回アクセス時に DuckDB 接続を作成し、DB_TYPE=bird のときは dev_databases を attach する。"""
        if self._connection is None:
            self._connection = duckdb.connect(str(self._duckdb_path))
            self.connect()  # BIRD の attach 等
        return self._connection

    def _attach_bird_databases(self, db_id: str | None = None) -> None:
        """DB_TYPE=bird のとき、BIRD_PATH の dev_databases 配下の SQLite を DuckDB に attach する。"""
        bird_path = Path(config.BIRD_PATH)
        dev_databases_path = bird_path / "dev_databases"
        if not dev_databases_path.exists():
            raise FileNotFoundError(f"dev_databases not found: {dev_databases_path}")

        if db_id:
            if db_id in self._attached_dbs:
                return
            sqlite_path = dev_databases_path / db_id / f"{db_id}.sqlite"
            if sqlite_path.exists():
                try:
                    self.connection.execute(
                        f"ATTACH IF NOT EXISTS '{sqlite_path}' AS {db_id} (TYPE sqlite);"
                    )
                    self._attached_dbs.add(db_id)
                    print(f"Attached: {db_id}")
                except Exception as e:
                    logger.warning("Failed to attach %s: %s", db_id, e)
            return

        for db_dir in dev_databases_path.iterdir():
            if db_dir.is_dir() and db_dir.name not in self._attached_dbs:
                sqlite_path = db_dir / f"{db_dir.name}.sqlite"
                if sqlite_path.exists():
                    db_name = db_dir.name
                    try:
                        self.connection.execute(
                            f"ATTACH IF NOT EXISTS '{sqlite_path}' AS {db_name} (TYPE sqlite);"
                        )
                        self._attached_dbs.add(db_name)
                        print(f"Attached: {db_name}")
                    except Exception as e:
                        logger.warning("Failed to attach %s: %s", db_name, e)

    def connect(self, database_name: str | None = None) -> None:
        """接続の準備（DB_TYPE=bird のときは dev_databases を attach）。"""
        if config.DB_TYPE == "bird":
            self._attach_bird_databases(database_name)
        else:
            raise ValueError(f"Unsupported database type: {config.DB_TYPE}")
    
    def run_query(self, sql: str) -> List[Dict[str, Any]]:
        """
        SQLクエリを実行し、結果を返す

        Args:
            sql (str): 実行するSQLクエリ

        Returns:
            List[Dict[str, Any]]: クエリ結果のリスト
        """
        try:
            con = self.connection
            result_df = con.sql(sql).df()
            json_str = result_df.to_json(orient='records', date_format='iso')
            return json.loads(json_str)
            
        except Exception as e:
            return [{"error": str(e)}]
    
    def list_tables(self, database: str = None) -> List[Dict[str, Any]]:
        """
        データベースのスキーマ情報に基づき、テーブル一覧を取得する。

        Args:
            database (str, optional): 対象データベース名を指定する。省略時は attach されている全 DB を対象に各スキーマのテーブルを返す。
        Returns:
            List[Dict[str, Any]]: テーブル情報のリスト。完全修飾名（database.table）を含む。
        """
        con = self.connection
        if database:
            query = f"SHOW TABLES FROM {database}"
            result_df = con.sql(query).df()
            result_df['full_name'] = result_df['name'].apply(lambda x: f"{database}.{x}")
            json_str = result_df.to_json(orient='records', date_format='iso')
            return json.loads(json_str)
        # 引数なし: attach 済みの全 DB をループしてテーブル一覧を集める
        rows: List[Dict[str, Any]] = []
        for db_name in sorted(self._attached_dbs):
            try:
                result_df = con.sql(f"SHOW TABLES FROM {db_name}").df()
                result_df['full_name'] = result_df['name'].apply(lambda x: f"{db_name}.{x}")
                rows.extend(result_df.to_dict(orient='records'))
            except Exception as e:
                logger.warning("Failed to list tables from %s: %s", db_name, e)
        return rows
    
    def describe_tables(self, table_full_names: List[str]) -> Dict[str, Any]:
        """
        スキーマ情報からテーブル構造（カラム名、データ型、制約など）を取得する。

        Args:
            table_full_names (List[str]): 構造情報を取得したいテーブル名（完全修飾名）のリスト

        Returns:
            Dict[str, Any]: テーブル名ごとに「カラム情報（リスト）」を格納した辞書
        """
        con = self.connection
        result = {}
        
        for table_name in table_full_names:
            try:    
                schema_df = con.sql(f"DESCRIBE {table_name}").df()
                json_str = schema_df.to_json(orient='records', date_format='iso')
                result[table_name] = json.loads(json_str)
            except Exception as e:
                result[table_name] = {"error": str(e)}
        
        return result
