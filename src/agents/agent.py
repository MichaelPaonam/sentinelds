# root_agent

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-agentic-workflow", agent_name="root_agent")
instrument_genai()

from google.adk.agents import SequentialAgent  # noqa: E402

from agents.sub_agents.feature_agent import (  # noqa: E402
    agent as feature_agent_module,
)
from agents.sub_agents.modeling_agent import agent as modeling_agent_module  # noqa: E402
from agents.sub_agents.research_agent import (  # noqa: E402
    agent as research_agent_module,
)

# Clear parents to avoid duplicate parent validation error when composing under root_agent
research_agent_module.research_agent.parent_agent = None
feature_agent_module.feature_agent.parent_agent = None
modeling_agent_module.modeling_agent.parent_agent = None

# For instantiating agents using RemoteA2aAgent, uncomment the following
# and provide the correct agent_card URIs for each sub-agent.
# a2a_research_agent = RemoteA2aAgent(
#     name="research_agent",
#     agent_card="<URI at which the research_agent is hosted>",
#     description="Research Agent: surveys literature to extract insights
#     and inform feature engineering and modeling.",
# )
# a2a_feature_agent = RemoteA2aAgent(
#     name="feature_agent",
#     agent_card="<URI at which the feature_agent is hosted>",
#     description="Feature Engineering Agent: profiles datasets, performs
#     transformations, and prepares features for modeling.",
# )
# a2a_modeling_agent = RemoteA2aAgent(
#     name="modeling_agent",
#     agent_card="<URI at which the modeling_agent is hosted>",
#     description="Modeling Agent: trains and evaluates ML models based on engineered
#     features and research insights.",
# )

root_agent = SequentialAgent(
    name="root_agent",
    description="Sequential data-science pipeline: research → features → modeling.",
    sub_agents=[
        research_agent_module.research_agent,
        feature_agent_module.feature_agent,
        modeling_agent_module.modeling_agent,
    ],
)
