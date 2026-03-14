#!/bin/bash

export VLLM_ROCM_VERSION="6.3.4"
export VLLM_REPO="https://github.com/ai-infos/vllm-gfx906-mobydick.git"
export VLLM_BRANCH="main"
export VLLM_TRITON_REPO="https://github.com/ai-infos/triton-gfx906.git"
export VLLM_TRITON_BRANCH="v3.5.1+gfx906"
export VLLM_FA_REPO="https://github.com/ai-infos/flash-attention-gfx906.git"
export VLLM_FA_BRANCH="gfx906/v2.8.3.x"
export VLLM_PRESET_NAME="mobydick-main-rocm-$VLLM_ROCM_VERSION"
export VLLM_DOCKERFILE="vllm-mobydick.Dockerfile"
