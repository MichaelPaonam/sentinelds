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
    subprocess.run(["uv", "pip", "compile", "pyproject.toml", "-o", temp_req_path], check=True)

    requirements = []
    if os.path.exists(temp_req_path):
        with open(temp_req_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    requirements.append(line)
        os.remove(temp_req_path)

    requirements.extend(["google-cloud-aiplatform>=1.70.0", "google-genai>=0.1.0"])
    return list(set(requirements))


def prepare_staged_src(source_dir: str, target_dir: str, exclude_names: list):
    """Copies source_dir to target_dir 
    while completely omitting unwanted modules and __pycache__ folders."""
    print(f"Preparing clean staging directory at {target_dir}...")
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)

    os.makedirs(target_dir)

    for item in os.listdir(source_dir):
        s = os.path.join(source_dir, item)
        d = os.path.join(target_dir, item)

        # Strip hidden system files, pycache, and targeted testing folders completely
        if item.startswith(".") or item == "__pycache__" or item in exclude_names:
            continue

        if os.path.isdir(s):
            # shutil.ignore_patterns ensures __pycache__ isn't copied inside nested children folders
            shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".*"))
        else:
            shutil.copy2(s, d)


def main():
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

    # Define directories to manipulate
    source_src = "src"
    staged_src = "src_staged"
    folders_to_exclude = [
                    "smoke",
                    "test",
                    "attack_server",
                    "e2e",
                    "InMemoryRunner",
                    "a2a_agents",
                    "ref",
                    "sentinel"
                ]

    # Execute the isolation copy
    prepare_staged_src(source_src, staged_src, folders_to_exclude)

    # Point extra_packages directly to the absolute path of the staging directory
    local_custom_packages = [
        os.path.abspath(staged_src)
    ]

    # 3. Deploy straight to the cloud runtime engine
    print("Uploading and deploying to Vertex AI Agent Engine (this may take a couple of minutes)...")
    try:
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

    finally:
        # Guarantee cleanup of your working tree directory even if Vertex AI encounters an error
        if os.path.exists(staged_src):
            print(f"Cleaning up staging directory: {staged_src}")
            shutil.rmtree(staged_src)


if __name__ == "__main__":
    main()
