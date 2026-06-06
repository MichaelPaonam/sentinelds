# root_agent

from google.adk.agents.llm_agent import Agent

from agents.sub_agents.feature_agent import (
    agent as feature_agent_module,
)
from agents.sub_agents.modeling_agent import (
    agent as modeling_agent_module
)
from agents.sub_agents.research_agent import (
    agent as research_agent_module,
)

# Clear parents to avoid duplicate parent validation error when composing under root_agent
research_agent_module.research_agent.parent_agent = None
feature_agent_module.feature_agent.parent_agent = None
# Parent reset pattern to avoid parent dependency cycles in ADK LlmAgent structure
modeling_agent_module.modeling_agent.parent_agent = None

root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    sub_agents=[
        feature_agent_module.feature_agent,
        modeling_agent_module.modeling_agent,
        research_agent_module.research_agent,
    ],
    description="Data Science Agent Team Coordinator",
    instruction="You are the Data Science Lead Agent. You receive high-level data science tasks. \
    Coordinate execution by breaking them down into smaller sub-tasks \
    and delegating them to your specialized sub-agents: \
    1. Delegate domain research, background literature reviews, and finding public \
    datasets to the 'research_agent'. \
    2. Delegate data ingestion, profiling, feature scaling, normalization, and \
    feature preparation to the 'feature_agent'. \
    3. Delegate training of XGBoost and CatBoost candidates, comparison, \
    and winner selection to the 'modeling_agent' once engineered features are available. \
    Coordinate their execution sequentially to prepare and clean the data for \
    downstream training. Ask the user clarifying questions if any specifications \
    are missing or if you need more information to complete the task.",
)
