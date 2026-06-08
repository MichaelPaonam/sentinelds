#!/bin/bash

# 1. Temporarily copy your specialized Dockerfile to the root directory
cp src/a2a_agents/a2a_feature/Dockerfile ./Dockerfile

# 2. Deploy using the plain source flag (Cloud Build will automatically find the root Dockerfile)
gcloud run deploy sentinelds-a2a-feature \
  --source=. \
  --region=europe-west4 \
  --project=sentinelds \
  --allow-unauthenticated \
  --set-secrets="DYNATRACE_API_URL=dynatrace-api-url:latest,DYNATRACE_API_TOKEN=dynatrace-api-token:latest,GEMINI_API_KEY=gemini-api-key:latest"

# 3. Remove the temporary root Dockerfile
rm ./Dockerfile
