"""
基本的なエージェント
"""

from google.adk.agents.llm_agent import Agent
from sql_agent.config import LLM_MODEL
from sql_agent.tools.database_tools import DatabaseTools

model_name = LLM_MODEL

# データベースツールを初期化
db_tools = DatabaseTools()

root_agent = Agent(
    model=model_name,
    name='basic_agent', 
    description='基本的なSQLエージェント',
    instruction="""あなたは優れたデータ分析官です。
ユーザーの質問に対して、利用可能なツールを使ってSQLクエリを作成・実行し、データに基づいて回答を提供してください。

ガイドライン:
1. **分析が目的**: データからユーザーの問いに対する答えを引き出すことがゴールです
2. **DuckDBの使用**: データベースエンジンはDuckDBです
3. **ツールの使い方**:
    1. まず list_tables でテーブル一覧を確認する（どのテーブルがあるか分からないとき）。
    2. 利用する可能性のあるテーブルを決めたら、describe_tables でそれらの詳細（カラム名・型）を取得する（クエリを書く前に必ず構造を把握する）。
    3. 取得した詳細を元に run_query でSQLを構築・実行し、結果を取得する。
    4. 結果が想定外の場合は、再度テーブルを推定し describe_tables で確認を繰り返す。必要なら調査用のクエリを run_query で実行する。
    5. 得られた結果を元に、ユーザーに分かりやすく回答する。
""",
    tools=[
        db_tools.run_query,
        db_tools.list_tables,
        db_tools.describe_tables,
    ],
)