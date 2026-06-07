from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-modeling-agent", agent_name="modeling_agent")
instrument_genai()

from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from agents.sub_agents.modeling_agent.agent import modeling_agent  # noqa: E402

a2a_modeling_agent = to_a2a(modeling_agent)
