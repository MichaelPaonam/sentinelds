"""Feature Engineering Agent: ADK-idiomatic SequentialAgent pipeline.

Structure:
  feature_agent (SequentialAgent)
    dataset_profiler       (LlmAgent) - csv_read + pandas_profile
    feature_transformer    (LlmAgent) - save_features
"""

from __future__ import annotations

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-feature-agent", agent_name="feature_agent")
instrument_genai()

import logging  # noqa: E402
import warnings  # noqa: E402

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from google.adk.agents import Agent, LlmAgent, SequentialAgent  # noqa: E402

from agents.sub_agents.feature_agent.prompt import (  # noqa: E402
    DATA_PROFILER_INSTRUCTION,
    FEATURE_ENGINEER_INSTRUCTION,
)
from core.config import settings  # noqa: E402
from tools.feature_tools import csv_read, find_files, pandas_profile  # noqa: E402
from tools.file_creation_tools import make_csv_file  # noqa: E402

logger = logging.getLogger("sentinelds.feature_agent")

DEFAULT_MODEL = settings.DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Pipeline agents
# ---------------------------------------------------------------------------

dataset_profiler = LlmAgent(
    model=DEFAULT_MODEL,
    name="dataset_profiler",
    description="Profiles raw datasets to analyze structures, missing values, and distributions.",
    instruction=DATA_PROFILER_INSTRUCTION,
    tools=[csv_read, pandas_profile, find_files],
    output_key="dataset_profile_report",
)

feature_transformer = LlmAgent(
    model=DEFAULT_MODEL,
    name="feature_transformer",
    description="Transforms, normalizes, scales features, and saves the clean dataset.",
    instruction=FEATURE_ENGINEER_INSTRUCTION,
    tools=[make_csv_file],
    output_key="feature_engineering_report",
)


# ---------------------------------------------------------------------------
# Composite agent
# ---------------------------------------------------------------------------

feature_agent = SequentialAgent(
    name="feature_agent",
    description=(
        "Expert Feature Engineering Agent. Ingests raw data files, "
        "profiles their statistical properties, performs normalization and scaling, "
        "and saves/registers the cleaned features for model training."
    ),
    sub_agents=[
        dataset_profiler,
        feature_transformer,
    ],
)

root_agent = Agent(
    model=DEFAULT_MODEL,
    name="root_agent",
    sub_agents=[feature_agent],
)
