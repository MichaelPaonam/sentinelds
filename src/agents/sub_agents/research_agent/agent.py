"""Research Agent: two-stage SequentialAgent (lit_searcher → lit_fetcher).

lit_searcher: Google Search only (Vertex grounding restriction — cannot mix with function tools).
lit_fetcher:  fetch_url only — this is the agent A1 hooks into.
"""

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools.google_search_tool import GoogleSearchTool

from agents.sub_agents.research_agent.prompt import (
    LIT_FETCHER_INSTRUCTION,
    LIT_SEARCHER_INSTRUCTION,
)
from core.config import settings
from tools.web_fetch import fetch_url

google_search = GoogleSearchTool(bypass_multi_tools_limit=True)

lit_searcher = LlmAgent(
    model=settings.DEFAULT_MODEL,
    name="lit_searcher",
    description="Runs Google searches on the research topic and summarises findings.",
    instruction=LIT_SEARCHER_INSTRUCTION,
    tools=[google_search],
    output_key="literature_search",
)

lit_fetcher = LlmAgent(
    model=settings.DEFAULT_MODEL,
    name="lit_fetcher",
    description="Fetches URLs from the search summary and enriches with referenced sources.",
    instruction=LIT_FETCHER_INSTRUCTION,
    tools=[fetch_url],
    output_key="research_findings",
)

research_agent = SequentialAgent(
    name="research_agent",
    description="Surveys literature via search then fetches and enriches from referenced URLs.",
    sub_agents=[lit_searcher, lit_fetcher],
)
