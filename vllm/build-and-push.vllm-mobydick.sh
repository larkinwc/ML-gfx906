#!/bin/bash
set -e

cd $(dirname $0)
source ../env.sh

VLLM_IMAGE=${VLLM_IMAGE:-docker.io/larkinwc/vllm-gfx906}
VLLM_DOCKERFILE=${VLLM_DOCKERFILE:-vllm-mobydick.Dockerfile}

IMAGE_TAGS=(
  "$VLLM_IMAGE:${VLLM_PRESET_NAME}-${REPO_GIT_REF}"
  "$VLLM_IMAGE:${VLLM_PRESET_NAME}"
)

if docker_image_pushed ${IMAGE_TAGS[0]}; then
  echo "${IMAGE_TAGS[0]} already in registry. Skip"
  exit 0
fi

DOCKER_EXTRA_ARGS=()
for (( i=0; i<${#IMAGE_TAGS[@]}; i++ )); do
  DOCKER_EXTRA_ARGS+=("-t" "${IMAGE_TAGS[$i]}")
done

mkdir ./logs 2>/dev/null || true
docker buildx build ${DOCKER_EXTRA_ARGS[@]} --push \
  --build-arg BASE_ROCM_IMAGE=${PATCHED_ROCM_IMAGE}:${VLLM_ROCM_VERSION}-complete \
  --build-arg VLLM_REPO=$VLLM_REPO \
  --build-arg VLLM_BRANCH=$VLLM_BRANCH \
  --build-arg TRITON_REPO=$VLLM_TRITON_REPO \
  --build-arg TRITON_BRANCH=$VLLM_TRITON_BRANCH \
  --build-arg FA_REPO=${VLLM_FA_REPO} \
  --build-arg FA_BRANCH=${VLLM_FA_BRANCH} \
  --progress=plain --target final -f ./${VLLM_DOCKERFILE} . 2>&1 | tee ./logs/build_$(date +%Y%m%d%H%M%S).log
