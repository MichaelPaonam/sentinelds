#!/bin/bash
set -euo pipefail

trap 'rm -f ./Dockerfile' EXIT

cp src/a2a_agents/a2a_research/Dockerfile ./Dockerfile

gcloud run deploy sentinelds-a2a-research \
  --source=. \
  --region=europe-west4 \
  --project=sentinelds \
  --allow-unauthenticated \
  --set-secrets="DYNATRACE_API_URL=dynatrace-api-url:latest,DYNATRACE_API_TOKEN=dynatrace-api-token:latest,GEMINI_API_KEY=gemini-api-key:latest"
