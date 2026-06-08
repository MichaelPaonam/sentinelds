# deploy.py
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 1. Replicate your local PYTHONPATH environment layout programmatically
sys.path.insert(0, os.path.abspath("src"))

import vertexai
from vertexai import agent_engines

from agents.sub_agents.research_agent.agent import research_agent


def generate_requirements():
    """Uses uv to compile pyproject.toml dependencies on the fly."""
    print("Generating pinned requirements.txt via uv...")
    temp_req_path = "requirements_deployment.txt"

    # Run uv pip compile to lock your pyproject.toml dependencies
    subprocess.run(["uv", "pip", "compile", "pyproject.toml", "-o", temp_req_path], check=True)

    # Read the lines from the file, filter out comments/blanks, and append required Vertex versions
    requirements = []
    if os.path.exists(temp_req_path):
        with open(temp_req_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    requirements.append(line)
        os.remove(temp_req_path)  # Clean up local file immediately

    # Ensure the container pulls modern SDK versions to avoid the AdkApp wrapper bugs
    requirements.extend(["google-cloud-aiplatform>=1.70.0", "google-genai>=0.1.0"])

    return list(set(requirements))  # Deduplicate variations

def clean_pycache(root_dir: str):
    """Recursively deletes all __pycache__ folders within the target directory."""
    print("Purging local __pycache__ artifacts...")
    for path in Path(root_dir).rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path)

def main():
    # Clean cache files from your source directory before deployment steps run
    clean_pycache("src")

    print("Initializing Vertex AI Context...")
    vertexai.init(
        project="sentinelds",
        location="europe-west4",
        staging_bucket="gs://sentinelds-agent-staging",
    )

    # 2. Wrap the agent using the correct working SDK implementation
    print("Wrapping research_agent into an AdkApp container...")
    app = agent_engines.AdkApp(agent=research_agent)

    runtime_requirements = generate_requirements()

    local_custom_packages = [
        os.path.abspath("src/core"),
        os.path.abspath("src/tools"),
        os.path.abspath("src/observability"),
        os.path.abspath("src/agents"),
    ]

    # 3. Deploy straight to the cloud runtime engine
    print(
        "Uploading and deploying to Vertex AI Agent Engine (this may take a couple of minutes)..."
    )
    deployed_engine = agent_engines.create(
        app,
        requirements=runtime_requirements,
        extra_packages=local_custom_packages,
        display_name="sentinelds_research_agent"
    )

    print("\n" + "=" * 50)
    print("🎉 DEPLOYMENT SUCCESSFUL!")
    print(f"Resource Name: {deployed_engine.resource_name}")
    print("=" * 50)


if __name__ == "__main__":
    main()
