#!/bin/bash
set -euo pipefail

trap 'rm -f ./Dockerfile' EXIT

cp src/a2a_agents/a2a_feature/Dockerfile ./Dockerfile

gcloud run deploy sentinelds-a2a-feature \
  --source=. \
  --region=europe-west4 \
  --project=sentinelds \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=sentinelds,GOOGLE_CLOUD_LOCATION=europe-west4" \
  --set-secrets="DYNATRACE_API_URL=dynatrace-api-url:latest,DYNATRACE_API_TOKEN=dynatrace-api-token:latest"
