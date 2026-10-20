#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Deployment Script for Data Extraction Studio
# - Backend (FastAPI + PyMuPDF + OpenCV + Playwright) -> Google Cloud Run
# - Frontend (Angular) -> Firebase Hosting (Site: baogia-836e4-studio)
# - Shared GCP / Firebase Project: baogia-836e4 (cùng project với site1 & site2)
# ==============================================================================

PROJECT_ID="baogia-836e4"
REGION="asia-southeast1"
SERVICE_NAME="ai-crawler-api"
HOSTING_TARGET="studio"
IMAGE_URI="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Ensure gcloud is in PATH if installed in /mnt/data/development/google-cloud-sdk
if [ -d "/mnt/data/development/google-cloud-sdk/bin" ]; then
    export PATH="/mnt/data/development/google-cloud-sdk/bin:$PATH"
fi

usage() {
    echo "Usage: ./deploy.sh [all|be|fe|docker-test]"
    echo "  all         : Deploy cả Backend (Cloud Run) và Frontend (Firebase Hosting)"
    echo "  be          : Build & Deploy Backend lên Google Cloud Run (${REGION})"
    echo "  fe          : Build Angular & Deploy Frontend lên Firebase Hosting (target: ${HOSTING_TARGET})"
    echo "  docker-test : Build Docker image tại máy local và kiểm tra thử container"
}

deploy_be() {
    echo "🚀 [1/2] Deploying Backend (${SERVICE_NAME}) to Google Cloud Run..."
    echo "   Project : ${PROJECT_ID}"
    echo "   Region  : ${REGION}"

    if ! command -v gcloud >/dev/null 2>&1; then
        echo "❌ Không tìm thấy lệnh 'gcloud'. Vui lòng kiểm tra cài đặt Google Cloud SDK."
        exit 1
    fi

    gcloud config set project "${PROJECT_ID}"

    # Deploy directly from source using Cloud Build + Cloud Run
    gcloud run deploy "${SERVICE_NAME}" \
        --source . \
        --project "${PROJECT_ID}" \
        --region "${REGION}" \
        --platform managed \
        --allow-unauthenticated \
        --memory 2Gi \
        --cpu 2 \
        --timeout 300 \
        --set-env-vars "HEADLESS=true,AI_CRAWLER_DATA_DIR=/tmp/ai_crawler_data"

    BE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format 'value(status.url)')
    echo "✅ Backend deployed tại: ${BE_URL}"
}

deploy_fe() {
    echo "🚀 [2/2] Building & Deploying Frontend to Firebase Hosting (target: ${HOSTING_TARGET})..."
    cd "${DIR}/frontend"
    npm run build

    cd "${DIR}"
    npx --yes firebase-tools deploy --only "hosting:${HOSTING_TARGET}" --project "${PROJECT_ID}"
    echo "✅ Frontend deployed tại: https://${PROJECT_ID}-studio.web.app"
}

docker_test() {
    echo "🐳 Building local Docker image: ${SERVICE_NAME}:local ..."
    docker build -t "${SERVICE_NAME}:local" .
    echo "✅ Docker image built successfully!"
    echo "👉 Để chạy thử container local tại cổng 8080:"
    echo "   docker run --rm -p 8080:8080 ${SERVICE_NAME}:local"
}

MODE="${1:-all}"

case "$MODE" in
    be)
        deploy_be
        ;;
    fe)
        deploy_fe
        ;;
    docker-test)
        docker_test
        ;;
    all)
        deploy_be
        deploy_fe
        ;;
    *)
        usage
        exit 1
        ;;
esac
