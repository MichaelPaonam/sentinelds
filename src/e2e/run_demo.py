"""E2E demo runner for the SentinelDS pipeline (research → features → modeling)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import pathlib

import dotenv
import pandas as pd
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

dotenv.load_dotenv()

from core.config import settings  # noqa: E402 — must follow dotenv.load_dotenv()

logger = logging.getLogger("sentinelds.e2e")

DEFAULT_CSV = settings.E2E_DEFAULT_CSV
DEFAULT_PAPER_URL = settings.E2E_PAPER_URL
DEFAULT_TARGET = settings.E2E_TARGET_COL
COMBINED_CSV = settings.E2E_COMBINED_CSV


def _prepare_csv(csv_path: str, target: str) -> str:
    """Return csv_path unchanged if it has the target column.

    Otherwise look for its _2 counterpart, concatenate (_1 → label=0, _2 → label=1),
    write to COMBINED_CSV, and return that path.
    """
    df = pd.read_csv(csv_path)
    if target in df.columns:
        return str(pathlib.Path(csv_path).resolve())

    # Try to derive the _2 partner from a _1 file
    p = pathlib.Path(csv_path)
    stem = p.stem
    if not stem.endswith("_1"):
        logger.warning(
            "CSV %s has no '%s' column and is not a _1 file — using as-is", csv_path, target
        )
        return csv_path

    partner = p.with_name(stem[:-1] + "2" + p.suffix)
    if not partner.exists():
        logger.warning("Partner file %s not found — using original CSV as-is", partner)
        return csv_path

    df1 = pd.read_csv(csv_path)
    df1[target] = 0
    df2 = pd.read_csv(str(partner))
    df2[target] = 1

    combined = pd.concat([df1, df2], ignore_index=True)
    out = pathlib.Path(COMBINED_CSV)
    out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out, index=False)
    print(f"[e2e] Synthesized labeled CSV → {out} ({len(combined)} rows)")
    return str(out.resolve())


def _build_prompt(paper_url: str, csv_path: str, target: str) -> str:
    return (
        f"Build a drowsiness-detection model. "
        f"Survey current EEG and eye-tracking literature using `{paper_url}` as a primary source, "
        f"then engineer features from `{csv_path}` (target column: `{target}`), "
        f"then train and evaluate XGBoost and CatBoost candidates."
    )


async def run_demo(prompt: str, csv: str, paper_url: str, target: str) -> None:
    csv_path = str(pathlib.Path(_prepare_csv(csv, target)).resolve())
    final_prompt = prompt or _build_prompt(paper_url, csv_path, target)

    from sentinel import SentinelSession, set_sentinel_session  # noqa: PLC0415

    set_sentinel_session(
        SentinelSession(
            workspace_entity_id=getattr(settings, "DYNATRACE_WORKSPACE_ENTITY_ID", "WORKSPACE-1"),
            agent_name="root_agent",
        )
    )

    # Import here to avoid circular imports at module load
    from agents.agent import root_agent  # noqa: PLC0415

    session_service = InMemorySessionService()
    runner = Runner(
        agent=root_agent,
        app_name="sentinelds_e2e",
        session_service=session_service,
    )

    user_id = "e2e_user"
    session_id = "e2e_session"
    await session_service.create_session(
        app_name="sentinelds_e2e",
        user_id=user_id,
        session_id=session_id,
    )

    print(f"\n[e2e] Starting pipeline with prompt:\n  {final_prompt}\n")

    event_stream = runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=Content(parts=[Part.from_text(text=final_prompt)]),
    )

    for event in event_stream:
        author = getattr(event, "author", None)
        if hasattr(event, "is_final_response") and event.is_final_response():
            content = getattr(event, "content", None)
            if content and getattr(content, "parts", None):
                text = "".join(p.text for p in content.parts if p and getattr(p, "text", None))
                print(f"\n[{author}] FINAL:\n{text.strip()}\n")
        else:
            # Stream intermediate text events for visibility
            raw_text = getattr(event, "text", None)
            if raw_text:
                print(f"[{author}] {str(raw_text).strip()}")

    # Print final session state keys for verification
    session = await session_service.get_session(
        app_name="sentinelds_e2e", user_id=user_id, session_id=session_id
    )
    if session:
        state_keys = list(session.state.keys())
        print(f"\n[e2e] Final session state keys: {state_keys}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Run the SentinelDS e2e demo pipeline.")
    parser.add_argument("--prompt", default="", help="Override the default seeded prompt.")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="Path to the input CSV.")
    parser.add_argument(
        "--paper-url", default=DEFAULT_PAPER_URL, help="URL for the research stage."
    )
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Target column name.")
    args = parser.parse_args()

    asyncio.run(run_demo(args.prompt, args.csv, args.paper_url, args.target))
