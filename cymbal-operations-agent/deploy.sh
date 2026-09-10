#!/usr/bin/env bash
# Copyright 2026 Google LLC
# Automated Cloud Run Deployment Script for Cymbal Operations Agent

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project)}"
REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICE_NAME="cymbal-operations-agent"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo "Deploying ${SERVICE_NAME} to Google Cloud Run in ${REGION} (Project: ${PROJECT_ID})..."

gcloud builds submit --tag "${IMAGE_NAME}" .

gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE_NAME}" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated \
    --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_LOCATION=global"

echo "Deployment complete."
