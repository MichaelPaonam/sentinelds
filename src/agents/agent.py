# root_agent

from google.adk.agents.llm_agent import Agent

from agents.sub_agents.research_agent import (
    agent as research_agent_module,
)
from agents.sub_agents.feature_agent import (
    agent as feature_agent_module,
)

# Clear parents to avoid duplicate parent validation error when composing under root_agent
research_agent_module.research_agent.parent_agent = None
feature_agent_module.feature_agent.parent_agent = None

root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    sub_agents=[
        research_agent_module.research_agent,
        feature_agent_module.feature_agent,
    ],
    description="Data Science Agent Team Coordinator",
    instruction=(
        "You are the Data Science Lead Agent. You receive high-level data science tasks "
        "and coordinate execution by breaking them down and delegating them to your specialized sub-agents:\n"
        "1. Delegate domain research, background literature reviews, and finding public datasets to the 'research_agent'.\n"
        "2. Delegate data ingestion, profiling, feature scaling, normalization, and feature preparation to the 'feature_agent'.\n\n"
        "Coordinate their execution sequentially to prepare and clean the data for downstream training. "
        "Ask the user clarifying questions if any specifications are missing."
    ),
)
