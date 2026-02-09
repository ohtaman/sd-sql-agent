"""
BIRD の evidence を LLM で一般化し、knowledges テーブルに投入する CLI。

実行: uv run load-bird-knowledges [--database DB_ID] [--replace-db DB_ID]
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal, Optional

import click
import duckdb
from pydantic import BaseModel, Field

from sql_agent import config
from sql_agent.knowledges import ensure_attached, insert as knowledges_insert


# ---------- 出力スキーマ（knowledges テーブルと揃える） ----------


class KnowledgeItem(BaseModel):
    table_full_names: list[str] = Field(default_factory=list, description="完全修飾テーブル名のリスト")
    column_names: list[str] = Field(default_factory=list, description="完全修飾カラム名のリスト")
    kind: Literal["metric", "relation", "definition", "summary"] = Field(..., description="種別")
    title: Optional[str] = Field(None, description="短い見出し")
    content: str = Field(..., description="ヒント本文")
    source: Optional[str] = Field(None, description="出典")


class KnowledgeList(BaseModel):
    items: list[KnowledgeItem] = Field(default_factory=list)


# ---------- プロンプト（プラン記載の全文） ----------

REFINEMENT_PROMPT = """あなたはText-to-SQLシステムのためのナレッジエンジニアです。以下に与える質問とヒントから、ルールや定義を抽出してください。

## 詳細
1. ヒントから、各テーブルの概要と、ルールや定義を抽出すること
2. 1つのヒントに複数のルールや定義が含まれている場合は、それぞれ独立したものとして扱うこと
3. ルールや定義の重複は除外すること
4. コンテキスト情報を利用して、ルールや定義を適用すべきテーブルやカラムを特定し、table_full_names および column_names に設定すること
5. 適用すべきテーブルは検索に利用するため、幅広く推定すること
6. 適用すべきカラムはクエリ生成に用いるため、確度が高いものに限定すること
7. ヒントが具体的な例を含む場合は、具体例として content に含めること
8. kind は次のいずれかで設定すること
   - 'metric': メトリクス・指標の定義
   - 'relation': テーブル間の関係・結合に関する情報
   - 'definition': 用語・ビジネスルール・データ形式などの定義
   - 'summary': テーブルやカラムの要約、その他上記に当てはまらない説明
9. table_full_names と column_names は必ず完全修飾名で出力すること。テーブルは "database_name.table_name"、カラムは "database_name.table_name.column_name" の形とし、ここで与える database_name をプレフィックスに使うこと。該当するテーブル・カラムがない場合は空リストにすること

## コンテキスト情報
Database: {database_name}
{context_str}

## 質問とヒント
{evidence_text}
"""


async def _run_refinement_async(
    database_name: str,
    context_str: str,
    evidence_text: str,
) -> list[KnowledgeItem]:
    """ADK で refinement を実行し、KnowledgeItem のリストを返す。"""
    from google.adk.agents.llm_agent import Agent
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types

    agent = Agent(
        model="gemini-2.5-pro",
        name="knowledge_refiner",
        output_schema=KnowledgeList,
        output_key="knowledge_result",
    )
    session_service = InMemorySessionService()
    app_name = "knowledge_refiner_app"
    await session_service.create_session(app_name=app_name, user_id="user", session_id="session_1")
    runner = Runner(agent=agent, session_service=session_service, app_name=app_name)

    prompt = REFINEMENT_PROMPT.format(
        database_name=database_name,
        context_str=context_str,
        evidence_text=evidence_text,
    )
    msg = genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])

    async for _ in runner.run_async(user_id="user", session_id="session_1", new_message=msg):
        pass

    session = await session_service.get_session(app_name=app_name, user_id="user", session_id="session_1")
    result: Any = session.state.get("knowledge_result") if session and session.state else None

    if isinstance(result, KnowledgeList):
        return result.items
    if isinstance(result, dict) and "items" in result:
        return [KnowledgeItem(**x) if isinstance(x, dict) else x for x in result["items"]]
    if isinstance(result, list):
        return [KnowledgeItem(**x) if isinstance(x, dict) else x for x in result]
    return []


def _refine_knowledge(database_name: str, context_str: str, evidence_text: str) -> list[KnowledgeItem]:
    """同期ラッパー。"""
    return asyncio.run(_run_refinement_async(database_name, context_str, evidence_text))


@click.command()
@click.option("--database", "db_id", default=None, help="対象 DB（BIRD の db_id）。省略時は全件")
@click.option("--replace-db", "replace_db_id", default=None, help="指定 DB の既存 knowledges を削除してから投入")
def main(db_id: Optional[str], replace_db_id: Optional[str]) -> None:
    """BIRD の evidence を一般化して knowledges に投入する。"""
    bird_path = Path(config.BIRD_PATH) / "mini_dev_sqlite.json"
    if not bird_path.exists():
        click.echo(f"Error: {bird_path} not found.", err=True)
        raise SystemExit(1)

    with open(bird_path) as f:
        data = json.load(f)

    if db_id:
        data = [item for item in data if item.get("db_id") == db_id]
    if not data:
        click.echo("No items to process.")
        return

    con = duckdb.connect(str(config.DUCKDB_PATH))
    ensure_attached(con)
    schema = config.KNOWLEDGES_SCHEMA

    if replace_db_id:
        con.execute(f'DELETE FROM "{schema}".knowledges WHERE database_name = ?', [replace_db_id])
        click.echo(f"Deleted existing knowledges for database '{replace_db_id}'.")

    # db_id ごとにグループ化
    by_db: dict[str, list[dict]] = {}
    for item in data:
        did = item.get("db_id", "")
        if did not in by_db:
            by_db[did] = []
        by_db[did].append(item)

    from sql_agent.tools.database_tools import DatabaseTools
    db_tools = DatabaseTools()

    for database_name, items in by_db.items():
        evidence_text = ""
        for it in items:
            q = it.get("question", "N/A")
            e = it.get("evidence", "")
            evidence_text += f"Question Impact: {q}\n  Evidence Rule: {e}\n\n"

        try:
            db_tools.connect(database_name)
            tables = db_tools.list_tables(database_name)
            table_full_names = [t.get("full_name") or t.get("name", "") for t in tables]
            schema_info = db_tools.describe_tables(table_full_names)
            schema_lines = []
            for t_name, cols in schema_info.items():
                if isinstance(cols, list):
                    col_names = [
                        c.get("column_name") or c.get("name", "")
                        for c in cols
                        if isinstance(c, dict) and (c.get("column_name") or c.get("name"))
                    ]
                    schema_lines.append(f"Table: {t_name} (Columns: {', '.join(col_names)})")
                else:
                    schema_lines.append(f"Table: {t_name} (Columns: (could not describe))")
            context_str = "Schema Summary:\n" + "\n".join(schema_lines)
        except Exception:
            context_str = "Tables: (could not list)"

        click.echo(f"Refining knowledge for database '{database_name}' ({len(items)} items)...")
        refined = _refine_knowledge(database_name, context_str, evidence_text)
        click.echo(f"  Got {len(refined)} knowledge items.")

        for item in refined:
            knowledges_insert(
                con,
                database_name=database_name,
                table_full_names=item.table_full_names or [],
                column_names=item.column_names or [],
                kind=item.kind,
                content=item.content,
                title=item.title,
                source=item.source or "bird_evidence",
                schema=schema,
            )
        click.echo(f"  Inserted {len(refined)} rows for '{database_name}'.")

    con.close()
    click.echo("Done.")
