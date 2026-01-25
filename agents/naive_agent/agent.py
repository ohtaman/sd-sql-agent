"""
SQLクエリの実行のみ可能な最も単純なエージェント
"""

from google.adk.agents.llm_agent import Agent
from sql_agent.config import LLM_MODEL
from sql_agent.tools.database_tools import DatabaseTools

model_name = LLM_MODEL

# データベースツールを初期化
db_tools = DatabaseTools()

root_agent = Agent(
    model=model_name,
    name='naive_agent', 
    description='最も単純なSQLエージェント',
    instruction="""あなたは優れたデータ分析官です。
ユーザーの質問に対して、利用可能なツールを使ってSQLクエリを作成・実行し、データに基づいて回答を提供してください。

利用可能な情報とツール:
- run_query(): SQLクエリを実行（ツール名は必ずrun_queryを使用してください）

重要な指針:
1. **分析が目的**: データからユーザーの問いに対する答えを引き出すことがゴールです
2. **クエリの実行**: SQLクエリを実行して結果を取得してください
3. **DuckDBの使用**: データベースエンジンはDuckDBです
""",
    tools=[db_tools.run_query],
)