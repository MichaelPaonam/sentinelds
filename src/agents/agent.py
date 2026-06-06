# root_agent

from google.adk.agents.llm_agent import Agent
from .sub_agents.research_agent.agent import research_agent

root_agent = Agent(
    model='gemini-2.5-flash-lite',
    name='root_agent',
    sub_agents=[research_agent],
    description='Data Science Agent',
    instruction='You are a Data Science Agent. You will be given a task and you will need to break it down into smaller sub-tasks and assign them to the research sub-agent. You should also be able to ask follow-up questions to the user if you need more information to complete the task.',
)
