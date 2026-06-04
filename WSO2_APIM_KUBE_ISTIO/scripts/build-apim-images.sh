#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# When true, pushes images to the registry (e.g., Docker Hub).
PUSH_IMAGES=${PUSH_IMAGES:-true}

CP_IMAGE=${CP_IMAGE:-repo/wso2-apim-acp-mssql:4.7.0}
GW_IMAGE=${GW_IMAGE:-repo/wso2-apim-gw-mssql:4.7.0}

CP_BASE_IMAGE=${CP_BASE_IMAGE:-wso2/wso2am-acp:4.7.0}
GW_BASE_IMAGE=${GW_BASE_IMAGE:-wso2/wso2am-universal-gw:4.7.0}

PLATFORMS="linux/amd64,linux/arm64"

echo "Building APIM CP image: ${CP_IMAGE}"
docker build \
  -f "${ROOT_DIR}/images/apim-cp/Dockerfile" \
  --platform "${PLATFORMS}" \
  --build-arg BASE_IMAGE="${CP_BASE_IMAGE}" \
  -t "${CP_IMAGE}" \
  "${ROOT_DIR}"

echo "Building APIM Universal GW image: ${GW_IMAGE}"
docker build \
  -f "${ROOT_DIR}/images/apim-gw/Dockerfile" \
  --platform "${PLATFORMS}" \
  --build-arg BASE_IMAGE="${GW_BASE_IMAGE}" \
  -t "${GW_IMAGE}" \
  "${ROOT_DIR}"

if [[ "${PUSH_IMAGES}" == "true" ]]; then
  echo "Pushing images (ensure you ran: docker login)"
  docker push "${CP_IMAGE}"
  docker push "${GW_IMAGE}"
fi

echo "Done. Built images:"
echo "- ${CP_IMAGE}"
echo "- ${GW_IMAGE}"
