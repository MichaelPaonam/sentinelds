#!/bin/bash
set -euo pipefail

trap 'rm -f ./Dockerfile' EXIT

cp src/sentinel_service/Dockerfile ./Dockerfile

gcloud run deploy sentinelds-sentinel \
  --source=. \
  --region=europe-west4 \
  --project=$GOOGLE_CLOUD_PROJECT \
  --allow-unauthenticated \
  --set-env-vars="OTEL_SEMCONV_STABILITY_OPT_IN=$OTEL_SEMCONV_STABILITY_OPT_IN" \
  --set-secrets="DYNATRACE_API_URL=dynatrace-api-url:latest" \
  --set-secrets="DYNATRACE_API_TOKEN=dynatrace-api-token:latest" \
  --set-secrets="DT_ENVIRONMENT=dt-environment:latest" \
  --set-secrets="DT_PLATFORM_TOKEN=dt-platform-token:latest"
