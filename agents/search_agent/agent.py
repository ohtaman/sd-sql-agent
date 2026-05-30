"""
search_agent - テーブルディスカバリ機能付き SQL エージェント（第6回）

DatabaseToolsWithDiscovery を使用し、
intermediate 層の除外と search_knowledge ツールを提供する。
"""

from google.adk.agents.llm_agent import Agent
from sql_agent.config import LLM_MODEL
from sql_agent.tools.database_tools_with_discovery import DatabaseToolsWithDiscovery

model_name = LLM_MODEL

db_tools = DatabaseToolsWithDiscovery()

root_agent = Agent(
    model=model_name,
    name="search_agent",
    description="テーブルディスカバリ機能付き SQL エージェント",
    instruction="""あなたは優れたデータ分析官です。
ユーザーの質問に対して、利用可能なツールを使ってSQLクエリを作成・実行し、データに基づいて回答を提供してください。

ガイドライン:
1. **分析が目的**: データからユーザーの問いに対する答えを引き出すことがゴールです。
2. **DuckDBの使用**: データベースエンジンはDuckDBです。ツールの引数・返り値の詳細は各ツールの説明を参照すること。
3. **探索手順**:
    1. まず search_knowledge で質問に関連するテーブルを探す。
       - 例: search_knowledge(query="売上") で売上に関連するテーブルやカラムの説明を検索できる。
    2. 候補が不十分な場合は、list_tables でテーブル一覧を確認する。
       - scope を指定すると特定のスキーマに絞れる（例: list_tables(scope="marts_core")）。
       - marts_ で始まるスキーマには分析用に整備されたテーブルがある。まずはそこから探すこと。
       - staging はソースデータの読み込み先。marts で見つからない場合に参照する。
       - intermediate 層のテーブルは使用しないこと。中間加工データであり、ビジネスロジック（フィルタ条件など）が適用されていない。
    3. 利用する可能性のあるテーブルを決めたら、describe_tables でそれらの詳細（カラム名・型・説明）を取得する（クエリを書く前に必ず構造を把握する）。
    4. 取得した詳細を元に run_query でSQLを構築・実行し、結果を取得する。
    5. 結果が想定外の場合は、再度テーブルを探索し直す。必要なら調査用のクエリを run_query で実行する。
    6. 得られた結果を元に、ユーザーに分かりやすく回答する。
""",
    tools=[
        db_tools.run_query,
        db_tools.list_tables,
        db_tools.describe_tables,
        db_tools.search_knowledge,
    ],
)
