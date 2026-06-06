"""Research Agent implementation using Google ADK for data science research."""

import asyncio
import datetime
import logging
import queue
import re
from collections.abc import AsyncGenerator, Generator
from threading import Thread
from typing import Any, Literal

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.planners import BuiltInPlanner
from google.adk.runners import InMemoryRunner
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import GoogleSearchTool
from google.adk.workflow import Workflow, Edge, START, FunctionNode
from google.genai import types as genai_types
from pydantic import BaseModel, Field, PrivateAttr

# Local prompt imports
from agents.sub_agents.research_agent.prompt import (
    ENHANCED_SEARCH_EXECUTOR_INSTRUCTION,
    PLAN_GENERATOR_INSTRUCTION,
    REPORT_COMPOSER_INSTRUCTION,
    RESEARCH_EVALUATOR_INSTRUCTION,
    SECTION_PLANNER_INSTRUCTION,
    SECTION_RESEARCHER_INSTRUCTION,
)

# Local tool imports
from tools.dataset_discovery import discover_datasets, suggest_ml_approaches
from tools.web_fetch import fetch_url

google_search = GoogleSearchTool(bypass_multi_tools_limit=True)

logger = logging.getLogger("sentinelds.research_agent")


# --- Structured Output Models ---
class SearchQuery(BaseModel):
    """Model representing a specific search query for web search."""

    search_query: str = Field(description="A highly specific and targeted query for web search.")


class Feedback(BaseModel):
    """Model for providing evaluation feedback on research quality."""

    grade: Literal["pass", "fail"] = Field(
        description=(
            "Evaluation result. 'pass' if the research is sufficient, 'fail' if it needs revision."
        )
    )
    comment: str = Field(
        description=(
            "Detailed explanation of the evaluation, highlighting "
            "strengths and/or weaknesses of the research."
        )
    )
    follow_up_queries: list[SearchQuery] | None = Field(
        default=None,
        description=(
            "A list of specific, targeted follow-up search queries needed "
            "to fix research gaps. This should be null or empty if the "
            "grade is 'pass'."
        ),
    )


# --- Callbacks ---
def collect_research_sources_callback(
    callback_context: CallbackContext,
) -> None:
    """Collects and organizes web-based research sources and their supported claims.

    Args:
        callback_context (CallbackContext): The context object providing access to the agent's
            session events and persistent state.
    """
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
                            {
                                "text_segment": text_segment,
                                "confidence": confidence,
                            }
                        )
                    callback_context.state["url_to_short_id"] = url_to_short_id
    callback_context.state["sources"] = sources


def citation_replacement_callback(
    callback_context: CallbackContext,
) -> genai_types.Content:
    """Replaces citation tags in a report with Markdown-formatted links.

    Processes 'final_cited_report' from context state, converting tags like
    `<cite source="src-N"/>` into hyperlinks using source information from
    `callback_context.state["sources"]`.

    Args:
        callback_context (CallbackContext): Contains the report and source information.

    Returns:
        genai_types.Content: The processed report with Markdown citation links.
    """
    final_report = callback_context.state.get("final_cited_report", "")
    sources = callback_context.state.get("sources", {})

    def tag_replacer(match: re.Match) -> str:
        short_id = match.group(1)
        if not (source_info := sources.get(short_id)):
            logger.warning(f"Invalid citation tag found and removed: {match.group(0)}")
            return ""
        display_text = source_info.get("title", source_info.get("domain", short_id))
        return f" [{display_text}]({source_info['url']})"

    processed_report = re.sub(
        r'<cite\s+source\s*=\s*["\']?\s*(src-\d+)\s*["\']?\s*/>',
        tag_replacer,
        final_report,
    )
    processed_report = re.sub(r"\s+([.,;:])", r"\1", processed_report)
    callback_context.state["final_report_with_citations"] = processed_report
    return genai_types.Content(parts=[genai_types.Part(text=processed_report)])


# --- Sub-Agent Definitions ---
# Default model choice in sentinelds workspace
DEFAULT_MODEL = "gemini-2.5-flash-lite"

plan_generator = LlmAgent(
    model=DEFAULT_MODEL,
    name="plan_generator",
    description="Generates or refines the action-oriented data science research plan.",
    instruction=PLAN_GENERATOR_INSTRUCTION.format(
        current_date=datetime.datetime.now().strftime("%Y-%m-%d")
    ),
    tools=[google_search],
)

section_planner = LlmAgent(
    model=DEFAULT_MODEL,
    name="section_planner",
    description="Breaks research plan into a structured markdown outline of sections.",
    instruction=SECTION_PLANNER_INSTRUCTION,
    output_key="report_sections",
)

section_researcher = LlmAgent(
    model=DEFAULT_MODEL,
    name="section_researcher",
    description="Performs the first pass of data science and web research.",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(include_thoughts=True)),
    instruction=SECTION_RESEARCHER_INSTRUCTION,
    tools=[google_search, fetch_url, discover_datasets],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
)

research_evaluator = LlmAgent(
    model=DEFAULT_MODEL,
    name="research_evaluator",
    description="Critically evaluates data science research and generates follow-up queries.",
    instruction=RESEARCH_EVALUATOR_INSTRUCTION.format(
        current_date=datetime.datetime.now().strftime("%Y-%m-%d")
    ),
    output_schema=Feedback,
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
    output_key="research_evaluation",
)

enhanced_search_executor = LlmAgent(
    model=DEFAULT_MODEL,
    name="enhanced_search_executor",
    description="Executes follow-up searches and integrates new findings.",
    planner=BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(include_thoughts=True)),
    instruction=ENHANCED_SEARCH_EXECUTOR_INSTRUCTION,
    tools=[google_search, fetch_url],
    output_key="section_research_findings",
    after_agent_callback=collect_research_sources_callback,
)

report_composer = LlmAgent(
    model=DEFAULT_MODEL,
    name="report_composer_with_citations",
    include_contents="none",
    description="Transforms research data and a markdown outline into a final, cited report.",
    instruction=REPORT_COMPOSER_INSTRUCTION,
    output_key="final_cited_report",
    after_agent_callback=citation_replacement_callback,
)


# --- Custom Function for Loop Control ---
def check_research_feedback(ctx) -> Event:
    """Checks research evaluation feedback and routes execution accordingly.

    If the grade is 'pass' or we have hit the maximum of 5 iterations,
    routes to 'pass' to compose the final report. Otherwise, routes to 'continue'.
    """
    evaluation_result = ctx.state.get("research_evaluation")
    loop_iterations = ctx.state.get("loop_iterations", 0)
    loop_iterations += 1

    # Store updated iterations back in state
    state_update = {"loop_iterations": loop_iterations}

    grade = evaluation_result.get("grade") if evaluation_result else None

    if grade == "pass":
        logger.info(
            f"[check_research_feedback] Evaluation passed on iteration {loop_iterations}. Routing to report_composer."
        )
        return Event(actions=EventActions(route="pass"), state=state_update)
    elif loop_iterations >= 5:
        logger.info(
            f"[check_research_feedback] Reached maximum iteration limit (5). Routing to report_composer."
        )
        return Event(actions=EventActions(route="pass"), state=state_update)
    else:
        logger.info(
            f"[check_research_feedback] Evaluation failed ('{grade}') on iteration {loop_iterations}/5. Routing to enhanced_search_executor."
        )
        return Event(actions=EventActions(route="continue"), state=state_update)


check_feedback_node = FunctionNode(
    name="check_research_feedback",
    func=check_research_feedback,
)


# --- Workflow Graph Definition ---
research_pipeline = Workflow(
    name="research_pipeline",
    description="Executes approved research plans, runs refinement, and composes cited reports.",
    edges=[
        Edge(from_node=START, to_node=section_planner),
        Edge(from_node=section_planner, to_node=section_researcher),
        Edge(from_node=section_researcher, to_node=research_evaluator),
        Edge(from_node=research_evaluator, to_node=check_feedback_node),
        Edge(from_node=check_feedback_node, to_node=enhanced_search_executor, route="continue"),
        Edge(from_node=enhanced_search_executor, to_node=research_evaluator),
        Edge(from_node=check_feedback_node, to_node=report_composer, route="pass"),
    ],
)


# --- Root Agent / Backward Compatible Public Class Interface ---
class ResearchAgent(BaseAgent):
    """Expert Data Science Research Agent.

    Provides both backward compatible programmatic APIs and ADK agent compliance
    for use within parent sub_agents list.
    """

    _plan_generator: Any = PrivateAttr()
    _research_pipeline: Any = PrivateAttr()
    _root_agent: Any = PrivateAttr()

    def __init__(self, **kwargs) -> None:
        """Initialize the Research Agent wrapper and its core agents."""
        kwargs.setdefault("name", "research_agent")
        kwargs.setdefault(
            "description",
            "Expert Data Science Research Agent that executes approved research plans, runs refinement, and composes cited reports."
        )
        super().__init__(**kwargs)
        self._plan_generator = plan_generator
        self._research_pipeline = research_pipeline
        self._root_agent = None  # Will be lazily linked to interactive_planner_agent

    @property
    def plan_generator(self):
        return self._plan_generator

    @property
    def research_pipeline(self):
        return self._research_pipeline

    @property
    def root_agent(self):
        return self._root_agent

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        logger.info(f"[{self.name}] Executing internal research pipeline workflow...")
        runner = InMemoryRunner(node=self._research_pipeline)
        runner.auto_create_session = True
        runner.artifact_service = ctx.artifact_service
        runner.memory_service = ctx.memory_service
        runner.credential_service = ctx.credential_service

        async for event in runner.run_async(
            user_id=ctx.user_id if hasattr(ctx, "user_id") else "ds_user",
            session_id=ctx.session.id,
            new_message=ctx.user_content,
        ):
            yield event

    def conduct_research(
        self,
        research_question: str,
        include_datasets: bool = True,
    ) -> dict[str, Any]:
        """Conduct research on a data science question.

        Args:
            research_question: The data science research question
            include_datasets: Whether to search for relevant datasets

        Returns:
            Dictionary containing research findings
        """
        try:
            logger.info(f"Generating research plan for: {research_question}")
            # 1. Programmatically generate the research plan
            plan_runner = InMemoryRunner(agent=self._plan_generator)
            plan_runner.auto_create_session = True
            generated_plan = ""
            for event in plan_runner.run(
                user_id="ds_user",
                session_id="research_session",
                new_message=genai_types.Content(
                    parts=[genai_types.Part(text=f"Propose a plan for: {research_question}")]
                ),
            ):
                if event.content and event.content.parts:
                    text = "".join(p.text for p in event.content.parts if p.text)
                    if text:
                        generated_plan = text
                elif event.output and isinstance(event.output, str):
                    generated_plan = event.output

            if not generated_plan:
                raise RuntimeError("Failed to generate a research plan.")

            if include_datasets:
                generated_plan += (
                    "\n- **`[DATASET_DISCOVERY]`**: Identify and discover public "
                    "datasets, sources, and directories for this topic."
                )

            logger.info("Executing research pipeline...")
            # 2. Run the research pipeline with the plan injected in session state
            pipeline_runner = InMemoryRunner(node=self._research_pipeline)
            pipeline_runner.auto_create_session = True
            final_report = ""
            for event in _run_runner_sync(
                runner=pipeline_runner,
                user_id="ds_user",
                session_id="pipeline_session",
                new_message=genai_types.Content(
                    parts=[genai_types.Part(text="Execute research on the topic.")]
                ),
                state_delta={"research_plan": generated_plan},
            ):
                if event.content and event.content.parts:
                    text = "".join(p.text for p in event.content.parts if p.text)
                    if text:
                        final_report = text
                elif event.output and isinstance(event.output, str):
                    final_report = event.output

            return {
                "success": True,
                "research_question": research_question,
                "findings": final_report if final_report else "No findings generated.",
                "agent": "ResearchAgent",
            }

        except Exception as e:
            logger.exception("Error during conduct_research")
            return {
                "success": False,
                "error": str(e),
                "research_question": research_question,
            }

    def analyze_dataset(
        self,
        dataset_info: dict[str, Any] | str,
        dataset_name: str = "Dataset",
    ) -> dict[str, Any]:
        """Discover metadata, context, similar public repositories, and typical usage of a dataset.

        Note: Purely statistical profiling (mean, std dev, outlier detection, etc.) is
        relegated to the Feature Engineering Agent. This Research Agent focuses strictly
        on dataset discovery and literature research.

        Args:
            dataset_info: Dataset dictionary or path to CSV file
            dataset_name: Name/identifier for the dataset

        Returns:
            Dictionary containing analysis and recommendations
        """
        try:
            logger.info(f"Analyzing dataset context for: {dataset_name}")
            dataset_desc = dataset_info if isinstance(dataset_info, str) else str(dataset_info)

            prompt = f"""You are a Dataset Discovery specialist.
Retrieve and discover domain information, licensing details, and preprocessing
recommendations from public sources and literature for the following dataset:

**Dataset Name**: {dataset_name}
**Dataset Details**: {dataset_desc}

Provide:
1. Domain Context & Typical Usage in Literature
2. Recommended Preprocessing & Cleaning steps discussed in research papers
3. Similar or related open-source dataset alternatives from standard repositories
"""
            dataset_agent = LlmAgent(
                model=DEFAULT_MODEL,
                name="dataset_context_analyzer",
                description="Discovers dataset licenses, usage, and preprocessing recommendations.",
                instruction="Locate dataset domain insights and literature recommendations.",
                tools=[discover_datasets, google_search],
            )
            runner = InMemoryRunner(agent=dataset_agent)
            runner.auto_create_session = True
            findings = ""
            for event in runner.run(
                user_id="ds_user",
                session_id="analysis_session",
                new_message=genai_types.Content(parts=[genai_types.Part(text=prompt)]),
            ):
                if event.content and event.content.parts:
                    text = "".join(p.text for p in event.content.parts if p.text)
                    if text:
                        findings = text
                elif event.output and isinstance(event.output, str):
                    findings = event.output

            return {
                "success": True,
                "dataset_name": dataset_name,
                "analysis": findings if findings else "No findings generated.",
                "agent": "ResearchAgent",
            }

        except Exception as e:
            logger.exception("Error during analyze_dataset")
            return {
                "success": False,
                "error": str(e),
                "dataset_name": dataset_name,
            }

    def recommend_ml_pipeline(
        self,
        problem_description: str,
        data_characteristics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Recommend a complete high-level ML pipeline based on literature best-practices.

        Args:
            problem_description: Description of the data science problem
            data_characteristics: Optional characteristics of the data

        Returns:
            Dictionary containing pipeline recommendations
        """
        try:
            logger.info(f"Recommending ML pipeline for: {problem_description}")
            prompt = f"""Based on the following problem description, suggest a complete ML pipeline
drawing on academic literature and industry best practices:

**Problem**: {problem_description}
"""
            if data_characteristics:
                prompt += f"**Data Characteristics**: {data_characteristics}\n"

            pipeline_agent = LlmAgent(
                model=DEFAULT_MODEL,
                name="pipeline_recommender",
                description="Recommends ML architectures, preprocessing, and metrics.",
                instruction="Expert ML architect. Propose state-of-the-art frameworks and designs.",
                tools=[suggest_ml_approaches, google_search],
            )
            runner = InMemoryRunner(agent=pipeline_agent)
            runner.auto_create_session = True
            findings = ""
            for event in runner.run(
                user_id="ds_user",
                session_id="pipeline_session",
                new_message=genai_types.Content(parts=[genai_types.Part(text=prompt)]),
            ):
                if event.content and event.content.parts:
                    text = "".join(p.text for p in event.content.parts if p.text)
                    if text:
                        findings = text
                elif event.output and isinstance(event.output, str):
                    findings = event.output

            return {
                "success": True,
                "problem": problem_description,
                "pipeline_recommendation": findings if findings else "No recommendation generated.",
                "agent": "ResearchAgent",
            }

        except Exception as e:
            logger.exception("Error during recommend_ml_pipeline")
            return {
                "success": False,
                "error": str(e),
                "problem": problem_description,
            }


# Instantiate the global ResearchAgent object
research_agent = ResearchAgent()


# --- Root Agent is imported and used from src/agents/agent.py ---
# Note: we do not define or instantiate interactive_planner_agent here to avoid
# double-parent registration issues with root_agent in agent.py.



def _run_runner_sync(
    runner: InMemoryRunner,
    user_id: str,
    session_id: str,
    new_message: genai_types.Content,
    state_delta: dict[str, Any] | None = None,
) -> Generator[Event, None, None]:
    """Synchronously executes the runner with support for state_delta via an async worker thread."""
    event_queue: queue.Queue[Any] = queue.Queue()

    async def _invoke_run_async() -> None:
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
                state_delta=state_delta,
            ):
                event_queue.put(event)
        except Exception as e:
            logger.error(f"Error in async execution thread: {e}")
            event_queue.put(e)
        finally:
            event_queue.put(None)

    def _asyncio_thread_main() -> None:
        try:
            asyncio.run(_invoke_run_async())
        except Exception as e:
            logger.error(f"Error in asyncio.run thread: {e}")
            event_queue.put(e)
        finally:
            event_queue.put(None)

    thread = Thread(target=_asyncio_thread_main)
    thread.start()

    while True:
        event = event_queue.get()
        if event is None:
            break
        elif isinstance(event, Exception):
            raise event
        else:
            yield event

    thread.join()


def main() -> None:
    """Main execution function to test the ResearchAgent module."""
    import argparse
    import sys
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Set up basic console logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(
        description="Test the ResearchAgent module and its multi-agent pipelines."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--research",
        type=str,
        help="Run research on a data science question.",
    )
    group.add_argument(
        "--analyze",
        type=str,
        help="Run dataset analysis on a dataset name/description.",
    )
    group.add_argument(
        "--pipeline",
        type=str,
        help="Run ML pipeline recommendation for a given problem.",
    )

    args = parser.parse_args()

    print("=" * 60)
    print(" SentinelDS - ResearchAgent Test Utility")
    print("=" * 60)

    try:
        agent = research_agent
        print("[✓] ResearchAgent successfully initialized.")
    except Exception as e:
        print(f"[✗] Failed to initialize ResearchAgent: {e}")
        sys.exit(1)

    # Determine what to run
    if args.research:
        print(f"\nRunning conduct_research for: '{args.research}'...")
        res = agent.conduct_research(args.research)
    elif args.analyze:
        print(f"\nRunning analyze_dataset for: '{args.analyze}'...")
        res = agent.analyze_dataset(dataset_info=args.analyze, dataset_name=args.analyze)
    elif args.pipeline:
        print(f"\nRunning recommend_ml_pipeline for: '{args.pipeline}'...")
        res = agent.recommend_ml_pipeline(problem_description=args.pipeline)
    else:
        # Default test run
        default_problem = "Drowsiness detection using driver telemetry and EEG/ECG sensors"
        print(f"\nNo arguments provided. Running default pipeline recommendation test:")
        print(f"Problem: '{default_problem}'\n")
        res = agent.recommend_ml_pipeline(
            problem_description=default_problem,
            data_characteristics={"features": ["heart_rate", "eye_aspect_ratio", "yawn_frequency"]},
        )

    print("\n" + "=" * 60)
    print(" Execution Result")
    print("=" * 60)
    if res.get("success"):
        print("[✓] Execution succeeded!")
        if "pipeline_recommendation" in res:
            print("\nPipeline Recommendation:")
            print(res["pipeline_recommendation"])
        elif "findings" in res:
            print("\nResearch Findings:")
            print(res["findings"])
        elif "analysis" in res:
            print("\nDataset Analysis:")
            print(res["analysis"])
    else:
        print("[✗] Execution failed!")
        print(f"Error: {res.get('error')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
