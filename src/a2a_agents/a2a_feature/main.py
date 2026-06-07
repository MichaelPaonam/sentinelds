from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-feature-agent", agent_name="feature_agent")
instrument_genai()

from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from agents.sub_agents.feature_agent.agent import feature_agent  # noqa: E402

a2a_feature_agent = to_a2a(feature_agent)
