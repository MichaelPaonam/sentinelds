"""Feature Engineering Agent: ADK-idiomatic SequentialAgent pipeline.

Structure:
  feature_agent (SequentialAgent)
    dataset_profiler       (LlmAgent) - csv_read + pandas_profile
    feature_transformer    (LlmAgent) - save_features
"""

from __future__ import annotations

import logging
from google.adk.agents import Agent, LlmAgent, SequentialAgent

from agents.sub_agents.feature_agent.prompt import (
    DATA_PROFILER_INSTRUCTION,
    FEATURE_ENGINEER_INSTRUCTION,
)
from tools.feature_tools import csv_read, pandas_profile, save_features

logger = logging.getLogger("sentinelds.feature_agent")

DEFAULT_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Pipeline agents
# ---------------------------------------------------------------------------

dataset_profiler = LlmAgent(
    model=DEFAULT_MODEL,
    name="dataset_profiler",
    description="Profiles raw datasets to analyze structures, missing values, and distributions.",
    instruction=DATA_PROFILER_INSTRUCTION,
    tools=[csv_read, pandas_profile],
    output_key="dataset_profile_report",
)

feature_transformer = LlmAgent(
    model=DEFAULT_MODEL,
    name="feature_transformer",
    description="Transforms, normalizes, scales features, and saves the clean dataset.",
    instruction=FEATURE_ENGINEER_INSTRUCTION,
    tools=[save_features],
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
    model="gemini-2.5-flash",
    name="root_agent",
    sub_agents=[feature_agent],
)
