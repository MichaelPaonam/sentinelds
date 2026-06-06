"""Research Agent: ADK-idiomatic SequentialAgent + LoopAgent pipeline.

Structure:
  research_agent (SequentialAgent)
    plan_generator         (LlmAgent)   - Google Search only
    research_pipeline      (SequentialAgent)
      section_planner      (LlmAgent)   - no tools
      section_researcher   (LlmAgent)   - Google Search only  (thinking model)
      url_fetcher          (LlmAgent)   - fetch_url + discover_datasets
      refinement_loop      (LoopAgent, max_iterations=5)
        research_evaluator (LlmAgent)   - no tools, structured output
        loop_controller    (LlmAgent)   - escalates when grade==pass
        enhanced_search_executor (LlmAgent) - Google Search only (thinking model)
        enhanced_url_fetcher     (LlmAgent) - fetch_url only
      report_composer      (LlmAgent)   - no tools, citations

All agents run via sub_agent.run_async(ctx) inside the built-in SequentialAgent
and LoopAgent implementations -- same session, same runner, no second runner.

GoogleSearchTool is isolated to agents that have no other tools (Vertex AI
restriction: native grounding cannot be mixed with function tools).

# TODO: wrap fetch_url with sentinel_guard once Sentinel is wired up
# TODO: add OTel span instrumentation around each sub-agent invocation
"""

from __future__ import annotations

import datetime
import logging
import re

from google.adk.agents import Agent, LlmAgent, LoopAgent, SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.planners import BuiltInPlanner
from google.adk.tools.exit_loop_tool import exit_loop
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from agents.sub_agents.research_agent.prompt import (
    ENHANCED_SEARCH_EXECUTOR_INSTRUCTION,
    LOOP_CONTROLLER_INSTRUCTION,
    PLAN_GENERATOR_INSTRUCTION,
    REPORT_COMPOSER_INSTRUCTION,
    RESEARCH_EVALUATOR_INSTRUCTION,
    SECTION_PLANNER_INSTRUCTION,
    SECTION_RESEARCHER_INSTRUCTION,
    URL_FETCHER_INSTRUCTION,
)
from tools.dataset_discovery import discover_datasets
from tools.web_fetch import fetch_url

google_search = GoogleSearchTool(bypass_multi_tools_limit=True)

logger = logging.getLogger("sentinelds.research_agent")

DEFAULT_MODEL = "gemini-2.5-flash"
THINKING_MODEL = "gemini-2.5-flash"  # supports BuiltInPlanner with include_thoughts


# ---------------------------------------------------------------------------
# Structured output schema for the evaluator
# ---------------------------------------------------------------------------


class SearchQuery(BaseModel):
    search_query: str = Field(description="A highly specific and targeted query for web search.")


class Feedback(BaseModel):
    grade: str = Field(description="'pass' if research is sufficient, 'fail' if it needs revision.")
    comment: str = Field(
        description="Detailed evaluation highlighting strengths and/or weaknesses."
    )
    follow_up_queries: list[SearchQuery] | None = Field(
        default=None,
        description="Follow-up queries to fix gaps. Null or empty when grade is 'pass'.",
    )


# ---------------------------------------------------------------------------
# After-agent callbacks
# ---------------------------------------------------------------------------


def collect_research_sources_callback(callback_context: CallbackContext) -> None:
    """Accumulates grounding sources from search events into session state."""
    session = callback_context._invocation_context.session
    url_to_short_id = callback_context.state.get("url_to_short_id", {})
    sources = callback_context.state.get("sources", {})
    id_counter = len(url_to_short_id) + 1

    for event in session.events:
        if not (event.grounding_metadata and event.grounding_metadata.grounding_chunks):
            continue
        chunks_info = {}
        for idx, chunk in enumerate(event.grounding_metadata.grounding_chunks):
            if not chunk.web:
                continue
            url = chunk.web.uri
            title = chunk.web.title if chunk.web.title != chunk.web.domain else chunk.web.domain
            if url not in url_to_short_id:
                short_id = f"src-{id_counter}"
                url_to_short_id[url] = short_id
                sources[short_id] = {
                    "short_id": short_id,
                    "title": title,
                    "url": url,
                    "domain": chunk.web.domain,
                    "supported_claims": [],
                }
                id_counter += 1
            chunks_info[idx] = url_to_short_id[url]

        if event.grounding_metadata.grounding_supports:
            for support in event.grounding_metadata.grounding_supports:
                confidence_scores = support.confidence_scores or []
                chunk_indices = support.grounding_chunk_indices or []
                for i, chunk_idx in enumerate(chunk_indices):
                    if chunk_idx in chunks_info:
                        short_id = chunks_info[chunk_idx]
                        confidence = confidence_scores[i] if i < len(confidence_scores) else 0.5
                        text_segment = support.segment.text if support.segment else ""
                        sources[short_id]["supported_claims"].append(
                            {"text_segment": text_segment, "confidence": confidence}
                        )
                callback_context.state["url_to_short_id"] = url_to_short_id
    callback_context.state["sources"] = sources


def citation_replacement_callback(
    callback_context: CallbackContext,
) -> genai_types.Content:
    """Replaces <cite source="src-N"/> tags with Markdown links."""
    final_report = callback_context.state.get("final_cited_report", "")
    sources = callback_context.state.get("sources", {})

    def tag_replacer(match: re.Match) -> str:
        short_id = match.group(1)
        if not (source_info := sources.get(short_id)):
            logger.warning("Invalid citation tag removed: %s", match.group(0))
            return ""
        display_text = source_info.get("title", source_info.get("domain", short_id))
        return f" [{display_text}]({source_info['url']})"

    processed = re.sub(
        r'<cite\s+source\s*=\s*["\']?\s*(src-\d+)\s*["\']?\s*/>',
        tag_replacer,
        final_report,
    )
    processed = re.sub(r"\s+([.,;:])", r"\1", processed)
    callback_context.state["final_report_with_citations"] = processed
    return genai_types.Content(parts=[genai_types.Part(text=processed)])


# ---------------------------------------------------------------------------
# Pipeline agents
# ---------------------------------------------------------------------------

plan_generator = LlmAgent(
    model=DEFAULT_MODEL,
    name="plan_generator",
    description="Generates the action-oriented data science research plan.",
    instruction=PLAN_GENERATOR_INSTRUCTION.format(
        current_date=datetime.datetime.now().strftime("%Y-%m-%d")
    ),
    tools=[google_search],
    output_key="research_plan",
)

section_planner = LlmAgent(
    model=DEFAULT_MODEL,
    name="section_planner",
    description="Breaks the research plan into a structured markdown outline of sections.",
    instruction=SECTION_PLANNER_INSTRUCTION,
    output_key="report_sections",
)

section_researcher = LlmAgent(
    model=THINKING_MODEL,
    name="section_researcher",
    description="Performs web searches for the research plan goals.",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(include_thoughts=True)),
    instruction=SECTION_RESEARCHER_INSTRUCTION,
    tools=[google_search],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
)

url_fetcher = LlmAgent(
    model=DEFAULT_MODEL,
    name="url_fetcher",
    description="Fetches specific URLs and discovers datasets to supplement search findings.",
    instruction=URL_FETCHER_INSTRUCTION,
    tools=[fetch_url, discover_datasets],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
)

research_evaluator = LlmAgent(
    model=DEFAULT_MODEL,
    name="research_evaluator",
    description="Critically evaluates research findings and generates follow-up queries.",
    instruction=RESEARCH_EVALUATOR_INSTRUCTION.format(
        current_date=datetime.datetime.now().strftime("%Y-%m-%d")
    ),
    output_schema=Feedback,
    output_key="research_evaluation",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

loop_controller = LlmAgent(
    model=DEFAULT_MODEL,
    name="loop_controller",
    description="Checks evaluation grade and calls exit_loop when research quality passes.",
    instruction=LOOP_CONTROLLER_INSTRUCTION,
    tools=[exit_loop],
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)

enhanced_search_executor = LlmAgent(
    model=THINKING_MODEL,
    name="enhanced_search_executor",
    description="Executes follow-up Google searches to address research gaps.",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(include_thoughts=True)),
    instruction=ENHANCED_SEARCH_EXECUTOR_INSTRUCTION,
    tools=[google_search],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
)

enhanced_url_fetcher = LlmAgent(
    model=DEFAULT_MODEL,
    name="enhanced_url_fetcher",
    description="Fetches specific URLs identified during the refinement pass.",
    instruction=URL_FETCHER_INSTRUCTION,
    tools=[fetch_url],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
)

report_composer = LlmAgent(
    model=DEFAULT_MODEL,
    name="report_composer_with_citations",
    include_contents="none",
    description="Transforms research data and a markdown outline into a final cited report.",
    instruction=REPORT_COMPOSER_INSTRUCTION,
    output_key="final_cited_report",
    after_agent_callback=citation_replacement_callback,
)


# ---------------------------------------------------------------------------
# Composite agents
# ---------------------------------------------------------------------------

refinement_loop = LoopAgent(
    name="refinement_loop",
    description="Evaluates research quality and refines until grade=pass or max iterations.",
    max_iterations=5,
    sub_agents=[
        research_evaluator,
        loop_controller,
        enhanced_search_executor,
        enhanced_url_fetcher,
    ],
)

research_pipeline = SequentialAgent(
    name="research_pipeline",
    description="Runs the full research pipeline: outline, search, fetch, refine, compose.",
    sub_agents=[
        section_planner,
        section_researcher,
        url_fetcher,
        refinement_loop,
        report_composer,
    ],
)

research_agent = SequentialAgent(
    name="research_agent",
    description=(
        "Expert Data Science Research Agent. Runs a full cited research pipeline: "
        "plans, researches, evaluates quality, refines, and produces a cited report."
    ),
    sub_agents=[
        plan_generator,
        research_pipeline,
    ],
)

root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    sub_agents=[research_agent],
)
