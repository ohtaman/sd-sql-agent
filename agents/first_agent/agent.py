from google.adk.agents.llm_agent import Agent

root_agent = Agent(
    model='gemini-2.5-pro',
    name='first_agent',
    description='動作確認用の最小エージェント',
    instruction='簡単な質問に答えてください。',
    tools=[]  # ツールなし
)