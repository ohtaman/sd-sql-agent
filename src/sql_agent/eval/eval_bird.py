"""
BIRDデータセットによるエージェント評価
"""

import asyncio
import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import List, Any, Optional

import click

from sql_agent import config
from google.adk import Runner
from google.adk.cli.utils.agent_loader import AgentLoader
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from sql_agent.tools.database_tools import DatabaseTools

logger = logging.getLogger(__name__)


def _normalize_cell(value: Any) -> Any:
    """数値を丸め、SQLエンジン間で比較しやすくする。"""
    if isinstance(value, (float, int)):
        return round(float(value), 4)
    return value


def normalize_results(results: Any) -> set[tuple]:
    """SQLの結果行を、順序に依存しないタプルの集合に正規化する。"""
    if results is None:
        return set()

    rows = results if isinstance(results, list) else [results]
    out: set[tuple] = set()
    for row in rows:
        if isinstance(row, (list, tuple)):
            out.add(tuple(_normalize_cell(cell) for cell in row))
        else:
            out.add((_normalize_cell(row),))
    return out


def execute_on_sqlite(db_path: Path, sql: str) -> List[tuple]:
    """正解取得のため、SQLiteでSQLを実行する。"""
    conn = sqlite3.connect(db_path)
    try:
        return conn.cursor().execute(sql).fetchall()
    finally:
        conn.close()


def extract_json(text: str) -> Optional[dict]:
    """文字列からJSONを抽出する"""
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    json_str = match.group(1) if match else text

    try:
        return json.loads(json_str)
    except Exception as e:
        logger.warning("Failed to extract JSON from response: %s, error: %s", text[:200], e)
        return None


def create_analysis_agent():
    """失敗分析専用のエージェントを作成"""
    from google.adk.agents.llm_agent import Agent

    return Agent(
        model='gemini-2.5-pro',
        name='failure_analysis_agent',
        description='SQLクエリの失敗理由を分析する専門エージェント',
        instruction="""あなたはSQLクエリの失敗理由を分析する専門家です。
エージェントが生成したSQLと正解SQLの差異を分析し、失敗の主な理由を特定してください。

分析観点:
1. テーブル結合の誤り
2. 集計関数の使い方
3. WHERE条件の論理
4. GROUP BYやORDER BYの問題
5. 日付・型変換の問題
6. ビジネスロジックの理解不足

回答は必ず50文字以内の1行で、簡潔かつ分かりやすく説明してください。

例:
- 「JOINするテーブルが間違っている」
- 「集計対象のカラムが不適切」
- 「WHERE条件でセグメント判定が誤り」
- 「日付フォーマットの処理が不正確」""",
        tools=[]
    )


async def analyze_failure(question: str, agent_sql: str, gold_sql: str, agent_results: Any, gold_results: Any, error_msg: Optional[str] = None) -> str:
    """
    ADKエージェントを使って失敗理由を分析し、1行コメントを生成する
    """
    try:
        analysis_agent = create_analysis_agent()
        
        # 分析プロンプト作成
        analysis_prompt = f"""以下のSQLクエリの失敗を分析してください。

質問: {question}

エージェントが生成したSQL:
{agent_sql}

正解SQL:
{gold_sql}

エージェントの結果: {str(agent_results)[:200]}
正解の結果: {str(gold_results)[:200]}

{f"エラー: {error_msg}" if error_msg else ""}

なぜ失敗したのか、主な理由を1行（50文字以内）で説明してください。"""

        # ADKエージェントで分析実行
        session_service = InMemorySessionService()
        analysis_app_name = analysis_agent.name
        await session_service.create_session(
            app_name=analysis_app_name,
            user_id="analyzer",
            session_id="failure_analysis"
        )
        
        runner = Runner(agent=analysis_agent, session_service=session_service, app_name=analysis_app_name)

        async for event in runner.run_async(
            user_id="analyzer",
            session_id="failure_analysis",
            new_message=genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=analysis_prompt)]
            )
        ):
            if event.is_final_response() and event.content and event.content.parts:
                failure_reason = event.content.parts[0].text
                return failure_reason

    except Exception as e:
        return f"分析エラー: {str(e)[:30]}"


async def evaluate_async(agent: str, limit: int, analyze_failures: bool, include_evidence: bool):
    """指定エージェントをBIRDデータセットで評価する。"""
    # エージェントを動的にロード
    print(f"Loading agent: {agent}")
    root_agent = AgentLoader("agents").load_agent(agent)

    db_tools = DatabaseTools()
    con = db_tools.connection
    
    # BIRDの問題を読み込み
    bird_path = config.BIRD_PATH / "mini_dev_sqlite.json"
    with open(bird_path) as f:
        data = json.load(f)

    session_service = InMemorySessionService()
    app_name = root_agent.name
    runner = Runner(
        agent=root_agent, 
        session_service=session_service, 
        app_name=app_name
    )
    
    print(f"Evaluating '{root_agent.name}' (model: {root_agent.model}) on {limit} BIRD questions")
    print(f"Include evidence: {include_evidence}")
    print(f"Analyze failures: {analyze_failures}")
    print("=" * 70)
    
    # 評価用の集計
    correct_count = 0
    gold_errors = 0
    extraction_errors = 0
    for i, item in enumerate(data[:limit]):
        db_id = item['db_id']
        question = item['question']
        evidence = item.get('evidence', '')
        gold_sql = item['SQL']
        
        print(f"\n[{i+1}/{limit}]")
        print(f"  Database: {db_id}")
        print(f"  Question: {question[:100]}{'...' if len(question) > 100 else ''}")
        
        # DuckDBのDBコンテキストを切り替え
        try:
            db_tools.connect(database_name=db_id)
            con.execute(f"USE {db_id}")
        except Exception as e:
            logger.error("  ✗ DB Context Error: %s", e)
            continue

        # エージェント実行
        agent_json: Optional[dict] = None
        try:
            await session_service.create_session(
                app_name=app_name,
                user_id="eval_user",
                session_id=f"session_{i}"
            )
            
            # プロンプト組み立て（フラグが有効なときだけ evidence を含める）
            evidence_section = ""
            if include_evidence and evidence:
                evidence_section = f"\n## 補助情報（Evidence）\n{evidence}\n"
            
            eval_prompt = (
                "以下の質問に答えるためのSQLクエリを出力してください。\n\n"
                "## 対象データベース\n"
                f"{db_id}\n\n"
                "## 要件:\n"
                "1. 次のキーを持つJSONオブジェクトのみを返してください:\n"
                "   - 'query': ユーザーの質問に対する答えを直接計算する、SQLクエリ。\n"
                "   - 'query_result': そのクエリを実行した結果（文字列として）。\n"
                "   - 'answer': データに基づいた、あなたの最終的な自然言語の回答。\n"
                "2. 'query'は、評価のための最終結果を提供する単一のSQLステートメントでなければなりません。\n"
                "3. **重要** クエリの実行結果には、質問に対する直接の答えとなる列のみを含めてください。計算の過程で使用した列についても、質問で明示的に求められていない限り含めないでください。\n"
                "4. データベースはDuckDBです。DuckDBで実行可能なSQLとしてください。\n"
                f"{evidence_section}"
                "## 質問\n"
                f"{question}\n"
            )
            
            content = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=eval_prompt)]
            )

            start_time = time.time()
            
            # イベントを消費し、最終応答（final_response）のテキストを取得する
            final_response_text = ""
            tool_call_count = 0
            max_tool_calls = 15  # 無限ループ防止の上限

            async for event in runner.run_async(user_id="eval_user", session_id=f"session_{i}", new_message=content):
                if tool_call_count >= max_tool_calls:
                    break  # 上限到達済みならイベントループを抜ける
                if event.content:
                    for part in event.content.parts:
                        if part.function_call:
                            tool_call_count += 1
                            print(f"  [Tool] #{tool_call_count}: {part.function_call.name}")
                        
                    if tool_call_count >= max_tool_calls:
                        logger.warning("  [WARNING] Max tool calls (%s) reached, stopping...", max_tool_calls)
                        break

                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text"):
                            final_response_text += part.text

            agent_json = extract_json(final_response_text)
            duration = time.time() - start_time
            print(f"  [Time] {duration:.2f}s ({tool_call_count} tool calls)")
            
        except Exception as e:
            logger.error("  ✗ Agent Execution Error: %s", e)
            continue
        
        if not agent_json or 'query' not in agent_json:
            logger.warning("  ✗ Failed to extract JSON or query from response.")
            extraction_errors += 1
            continue
        agent_sql = agent_json['query']
        
        # Gold SQL は SQLite のため、元のデータベースを使用して結果を得る
        try:
            db_path = config.BIRD_PATH / "dev_databases" / db_id / f"{db_id}.sqlite"
            gold_results = execute_on_sqlite(db_path, gold_sql)
        except Exception as e:
            logger.error("  ✗ Gold SQL Error: %s", e)
            gold_errors += 1
            continue
            
        # エージェントのSQLを再実行し、正解と比較
        agent_execution_results = None
        sql_error = None
        try:
            agent_execution_results = con.sql(agent_sql).fetchall()
            is_correct = normalize_results(agent_execution_results) == normalize_results(gold_results)
        except Exception as e:
            logger.error("  ✗ Agent SQL Validation Error: %s", e)
            sql_error = str(e)
            is_correct = False
            agent_execution_results = []
            
        # SQLと結果を表示
        print(f"  Agent SQL: {agent_sql}")
        print(f"  Gold SQL:  {gold_sql}")
        print(f"  Agent Results: {str(agent_execution_results)[:100]}{'...' if len(str(agent_execution_results)) > 100 else ''}")
        print(f"  Gold Results:  {str(gold_results)[:100]}{'...' if len(str(gold_results)) > 100 else ''}")
        
        if is_correct:
            print("  ✓ CORRECT")
            correct_count += 1
        else:
            print("  ✗ INCORRECT")
            
            # 失敗理由をLLMで分析（フラグが有効な場合のみ）
            if analyze_failures:
                failure_reason = await analyze_failure(
                    question=question,
                    agent_sql=agent_sql, 
                    gold_sql=gold_sql,
                    agent_results=agent_execution_results,
                    gold_results=gold_results,
                    error_msg=sql_error
                )
                print(f"    Failure Reason: {failure_reason}")

    # === サマリ ===
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)
    print(f"Agent: {root_agent.name}")
    print(f"Model: {root_agent.model}")
    print(f"Questions Evaluated: {limit}")
    print("")
    print(f"✓ Correct Answers: {correct_count}/{limit} ({correct_count/limit*100:.1f}%)")
    print(f"✗ Incorrect Answers: {limit - correct_count - gold_errors - extraction_errors}/{limit}")
    print(f"⚠ Gold SQL Errors: {gold_errors}/{limit}")
    print(f"⚠ JSON Extraction Failures: {extraction_errors}/{limit}")
    print("=" * 70)
    


@click.command()
@click.option('--agent', default='naive_agent', help='評価するエージェント（default: naive_agent）')
@click.option('--limit', default=10, type=int, help='評価する問題数')
@click.option('--analyze-failures', is_flag=True, help='失敗理由をLLMで分析する（遅くなる）')
@click.option('--include-evidence', is_flag=True, help='プロンプトに evidence を含める')
def evaluate(agent, limit, analyze_failures, include_evidence):
    """指定エージェントをBIRDデータセットで評価する。"""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(evaluate_async(agent, limit, analyze_failures, include_evidence))


if __name__ == "__main__":
    evaluate()
