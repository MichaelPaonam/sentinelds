from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-research-agent", agent_name="research_agent")
instrument_genai()

from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from agents.sub_agents.research_agent.agent import research_agent  # noqa: E402

a2a_research_agent = to_a2a(research_agent)
