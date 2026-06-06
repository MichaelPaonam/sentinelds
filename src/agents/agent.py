# root_agent

from google.adk.agents.llm_agent import Agent

from agents.sub_agents.modeling_agent import (
    agent as modeling_agent_module,
)
from agents.sub_agents.research_agent import (
    agent as research_agent_module,
)

# Parent reset pattern to avoid parent dependency cycles in ADK LlmAgent structure
modeling_agent_module.modeling_agent.parent_agent = None

root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    sub_agents=[
        research_agent_module.research_agent,
        modeling_agent_module.modeling_agent,
    ],
    description="Data Science Agent",
    instruction="You are a Data Science Agent. \
You will be given a task and you will need to break it down \
into smaller sub-tasks and assign them to the sub-agents. \
You can: \
1. Delegate literature review and research tasks to the 'research_agent'. \
2. Delegate training of XGBoost and CatBoost candidates, comparison, \
and winner selection to the 'modeling_agent' once engineered features are available. \
You should also be able to ask follow-up questions to the user \
if you need more information to complete the task.",
)
