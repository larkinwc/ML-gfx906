#!/bin/bash

export VLLM_ROCM_VERSION="6.3.3"
export VLLM_REPO="https://github.com/ai-infos/vllm-gfx906-mobydick.git"
export VLLM_BRANCH="gfx906/v0.16.1rc0.x"
export VLLM_TRITON_REPO="https://github.com/ai-infos/triton-gfx906.git"
export VLLM_TRITON_BRANCH="v3.6.0+gfx906"
export VLLM_FA_REPO="https://github.com/ai-infos/flash-attention-gfx906.git"
export VLLM_FA_BRANCH="gfx906/v2.8.3.x"
export VLLM_PRESET_NAME="0.16.1-rocm-$VLLM_ROCM_VERSION-mobydick"
export VLLM_DOCKERFILE="vllm-mobydick.Dockerfile"
