"""Modeling Agent definition and standalone CLI."""

from __future__ import annotations

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-modeling-agent", agent_name="modeling_agent")
instrument_genai()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import logging  # noqa: E402

from google.adk.agents import Agent, LlmAgent  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai.types import Content, Part  # noqa: E402

from agents.sub_agents.modeling_agent.prompt import MODELING_AGENT_INSTRUCTION  # noqa: E402
from core.config import settings  # noqa: E402
from tools.modeling_tools import (  # noqa: E402
    evaluate_cv,
    evaluate_holdout,
    load_features,
    save_model,
    save_report,
    train_catboost,
    train_xgboost,
)

logger = logging.getLogger("sentinelds.modeling_agent")
DEFAULT_MODEL = settings.DEFAULT_MODEL

# Define the Modelling Agent LlmAgent
modeling_agent = LlmAgent(
    model=DEFAULT_MODEL,
    name="modeling_agent",
    description=(
        "Trains XGBoost and CatBoost candidates on engineered features, "
        "selects the winner, persists the model and a markdown report."
    ),
    instruction=MODELING_AGENT_INSTRUCTION,
    tools=[
        load_features,
        train_xgboost,
        train_catboost,
        evaluate_holdout,
        evaluate_cv,
        save_model,
        save_report,
    ],
    output_key="modeling_report",
)


async def run_standalone(features_csv: str, target_col: str) -> None:
    """Runs the modeling agent standalone via in-memory session runner."""
    print(f"--- Activating Standalone Modelling Agent for features: {features_csv} ---")

    session_service = InMemorySessionService()
    runner = Runner(
        agent=modeling_agent,
        app_name="modeling_agent",
        session_service=session_service,
    )

    user_id = "local_modeling_user"
    session_id = "local_modeling_session"

    await session_service.create_session(
        app_name="modeling_agent",
        user_id=user_id,
        session_id=session_id,
    )

    prompt = (
        f"Please train models on features CSV '{features_csv}' "
        f"with target column '{target_col}' and save the winner and report."
    )
    prompt_content = Content(parts=[Part.from_text(text=prompt)])

    event_stream = runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=prompt_content,
    )

    full_response = ""
    for event in event_stream:
        if hasattr(event, "is_final_response") and event.is_final_response():
            content = getattr(event, "content", None)
            if content is not None and getattr(content, "parts", None):
                full_response += "".join(
                    [
                        part.text
                        for part in content.parts
                        if part and getattr(part, "text", None) and isinstance(part.text, str)
                    ]
                )
        elif hasattr(event, "text") and event.text:
            full_response += str(event.text)

    print(f"\n[Agent Output]:\n{full_response.strip()}\n")


root_agent = Agent(
    model=DEFAULT_MODEL,
    name="root_agent",
    sub_agents=[modeling_agent],
)


if __name__ == "__main__":
    import dotenv

    dotenv.load_dotenv()

    parser = argparse.ArgumentParser(description="Run the Modelling Agent standalone CLI.")
    parser.add_argument(
        "--features",
        default="features.csv",
        help="Path to the features CSV file (default: features.csv)",
    )
    parser.add_argument(
        "--target",
        default="label",
        help="Name of the target column (default: label)",
    )
    args = parser.parse_args()

    # Run standalone modeling pipeline
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_standalone(args.features, args.target))
