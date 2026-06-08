from google.adk.agents.remote_a2a_agent import RemoteA2aAgent  # noqa: E402

root_agent = RemoteA2aAgent(
    name="research_agent",
    agent_card="http://localhost:8080/.well-known/agent-card.json",
    description="Research Agent: surveys literature to extract insights \
    and inform feature engineering and modeling.",
)
