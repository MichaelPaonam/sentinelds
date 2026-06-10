#!/bin/bash
set -euo pipefail

trap 'rm -f ./Dockerfile' EXIT

cp src/a2a_agents/a2a_modeling/Dockerfile ./Dockerfile

gcloud run deploy sentinelds-a2a-feature \
  --source=. \
  --region=europe-west4 \
  --project=$GOOGLE_CLOUD_PROJECT \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT" \
  --set-env-vars="GOOGLE_CLOUD_LOCATION=europe-west4" \
  --set-env-vars="OTEL_SEMCONV_STABILITY_OPT_IN=$OTEL_SEMCONV_STABILITY_OPT_IN" \
  --set-env-vars="GCS_BUCKET_NAME=$GCS_BUCKET_NAME" \
  --set-secrets="DYNATRACE_API_URL=dynatrace-api-url:latest" \
  --set-secrets="DYNATRACE_API_TOKEN=dynatrace-api-token:latest" \
  --set-secrets="DT_ENVIRONMENT=dt-environment:latest" \
  --set-secrets="DT_PLATFORM_TOKEN=dt-platform-token:latest"
