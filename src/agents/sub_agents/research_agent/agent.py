"""Research Agent implementation using Google ADK for data science research."""

from typing import Any

from google.adk import Agent
from google.genai.types import Tool

from src.agents.sub_agents.research_agent.prompt import (
    RESEARCH_AGENT_SYSTEM_PROMPT,
    RESEARCH_DATASET_ANALYSIS_PROMPT_TEMPLATE,
    RESEARCH_EXPLORATORY_PROMPT_TEMPLATE,
)
from src.tools.dataset_discovery import discover_datasets, suggest_ml_approaches
from src.tools.web_fetch import fetch_url


class ResearchAgent:
    """Data Science Research Agent using Google ADK.

    This agent conducts research, analyzes datasets, and recommends ML approaches
    for data science workflows in the sequential pipeline.
    """

    def __init__(self):
        """Initialize the Research Agent with google.adk and custom tools."""
        # Define custom tools for the agent
        self.tools = {
            "discover_datasets": Tool(
                name="discover_datasets",
                description="Discover public datasets from various \
                repositories for data science projects",
                handler=discover_datasets,
                required_args=["query"],
            ),
            "suggest_ml_approaches": Tool(
                name="suggest_ml_approaches",
                description="Suggest appropriate machine learning approaches based on \
                problem type and data characteristics",
                handler=suggest_ml_approaches,
                required_args=["problem_type"],
            ),
            "fetch_url": Tool(
                name="fetch_url",
                description="Fetch content from URLs to retrieve research papers, \
                documentation, or datasets information",
                handler=fetch_url,
                required_args=["url"],
            ),
        }

        # Initialize the google.adk Agent
        self.agent = Agent(
            name="ResearchAgent",
            description="Expert Data Science Research Agent for \
            conducting research and dataset analysis",
            system_prompt=RESEARCH_AGENT_SYSTEM_PROMPT,
            tools=list(self.tools.values()),
        )

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
            # Create research prompt
            research_prompt = RESEARCH_EXPLORATORY_PROMPT_TEMPLATE.format(
                research_question=research_question
            )

            # If datasets should be included, add to prompt
            if include_datasets:
                research_prompt += "\n\nPlease also search for relevant public datasets."

            # Run the agent with the research prompt
            response = self.agent.run(research_prompt)

            return {
                "success": True,
                "research_question": research_question,
                "findings": response,
                "agent": "ResearchAgent",
            }

        except Exception as e:
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
        """Analyze a dataset and provide recommendations.

        Args:
            dataset_info: Dataset dictionary or path to CSV file
            dataset_name: Name/identifier for the dataset

        Returns:
            Dictionary containing analysis and recommendations
        """
        try:
            # Create analysis prompt
            analysis_prompt = RESEARCH_DATASET_ANALYSIS_PROMPT_TEMPLATE.format(
                dataset_name=dataset_name,
                dataset_path=dataset_info if isinstance(dataset_info, str) else "in-memory",
            )

            # Run the agent with analysis prompt
            response = self.agent.run(analysis_prompt)

            return {
                "success": True,
                "dataset_name": dataset_name,
                "analysis": response,
                "agent": "ResearchAgent",
            }

        except Exception as e:
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
        """Recommend a complete ML pipeline for a data science problem.

        Args:
            problem_description: Description of the data science problem
            data_characteristics: Optional characteristics of the data

        Returns:
            Dictionary containing pipeline recommendations
        """
        try:
            # Build comprehensive recommendation prompt
            prompt = f"""Based on the following problem description,
            recommend a complete ML pipeline:

            **Problem**: {problem_description}

            """
            if data_characteristics:
                prompt += f"**Data Characteristics**: {data_characteristics}\n\n"

            prompt += """Please provide:
                        1. Problem type classification
                        2. Appropriate ML algorithms and frameworks
                        3. Data preprocessing steps
                        4. Model evaluation strategy
                        5. Deployment considerations
                        6. Required tools and libraries"""

            # Run the agent
            response = self.agent.run(prompt)

            return {
                "success": True,
                "problem": problem_description,
                "pipeline_recommendation": response,
                "agent": "ResearchAgent",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "problem": problem_description,
            }
