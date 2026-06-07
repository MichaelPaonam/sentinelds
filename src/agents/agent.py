# root_agent

from google.adk.agents import SequentialAgent

from agents.sub_agents.feature_agent import (
    agent as feature_agent_module,
)
from agents.sub_agents.modeling_agent import agent as modeling_agent_module
from agents.sub_agents.research_agent import (
    agent as research_agent_module,
)

# Clear parents to avoid duplicate parent validation error when composing under root_agent
research_agent_module.research_agent.parent_agent = None
feature_agent_module.feature_agent.parent_agent = None
# Parent reset pattern to avoid parent dependency cycles in ADK LlmAgent structure
modeling_agent_module.modeling_agent.parent_agent = None

root_agent = SequentialAgent(
    name="root_agent",
    description="Sequential data-science pipeline: research → features → modeling.",
    sub_agents=[
        research_agent_module.research_agent,
        feature_agent_module.feature_agent,
        modeling_agent_module.modeling_agent,
    ],
)
