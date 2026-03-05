ARG BASE_ROCM_IMAGE="docker.io/larkinwc/rocm-gfx906:6.3.3-complete"
ARG VLLM_REPO="https://github.com/ai-infos/vllm-gfx906-mobydick.git"
ARG VLLM_BRANCH="gfx906/v0.16.1rc0.x"
ARG TRITON_REPO="https://github.com/ai-infos/triton-gfx906.git"
ARG TRITON_BRANCH="v3.5.1+gfx906"
ARG FA_REPO="https://github.com/ai-infos/flash-attention-gfx906.git"
ARG FA_BRANCH="gfx906/v2.8.3.x"

############# Base image with PyTorch #############
FROM ${BASE_ROCM_IMAGE} AS base
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /usr/lib/python3.12/EXTERNALLY-MANAGED

RUN pip install --no-cache-dir torch==2.9.1 torchvision \
    --index-url https://download.pytorch.org/whl/rocm6.3
RUN pip install --no-cache-dir amdsmi==$(cat /opt/ROCM_VERSION_FULL)

ENV PYTORCH_ROCM_ARCH=gfx906
ENV LD_LIBRARY_PATH=/opt/rocm/lib:/usr/local/lib:
ENV RAY_EXPERIMENTAL_NOSET_ROCR_VISIBLE_DEVICES=1
ENV TOKENIZERS_PARALLELISM=false
ENV HIP_FORCE_DEV_KERNARG=1
ENV VLLM_TARGET_DEVICE=rocm
ENV FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE
ENV HSA_OVERRIDE_GFX_VERSION=9.0.6

############# Build triton #############
FROM base AS build_triton
ARG TRITON_REPO
ARG TRITON_BRANCH
RUN pip install --no-cache-dir ninja 'cmake<4' wheel pybind11 setuptools_scm
WORKDIR /app
RUN git clone --depth 1 --recurse-submodules --shallow-submodules --jobs 4 \
    --branch ${TRITON_BRANCH} ${TRITON_REPO} triton
WORKDIR /app/triton
RUN if [ ! -f setup.py ]; then cd python; fi; \
    python3 setup.py bdist_wheel --dist-dir=/dist && \
    rm -rf /app/triton

############# Build flash-attention #############
FROM base AS build_fa
ARG FA_REPO
ARG FA_BRANCH
RUN pip install --no-cache-dir ninja 'cmake<4' wheel pybind11 setuptools_scm
RUN --mount=type=bind,from=build_triton,src=/dist/,target=/dist_triton \
    pip install --no-cache-dir /dist_triton/*.whl
WORKDIR /app
RUN git clone --depth 1 --recurse-submodules --shallow-submodules --jobs 4 \
    --branch ${FA_BRANCH} ${FA_REPO} flash-attention
WORKDIR /app/flash-attention
RUN FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE python3 setup.py bdist_wheel --dist-dir=/dist && \
    rm -rf /app/flash-attention

############# Build vllm #############
FROM base AS build_vllm
ARG VLLM_REPO
ARG VLLM_BRANCH
RUN pip install --no-cache-dir ninja 'cmake<4' wheel pybind11 setuptools_scm
RUN --mount=type=bind,from=build_triton,src=/dist/,target=/dist_triton \
    pip install --no-cache-dir /dist_triton/*.whl
WORKDIR /app
RUN git clone --depth 1 --recurse-submodules --shallow-submodules --jobs 4 \
    --branch ${VLLM_BRANCH} ${VLLM_REPO} vllm
WORKDIR /app/vllm
RUN pip install --no-cache-dir -r requirements/rocm.txt 2>/dev/null || true
RUN pip wheel --no-cache-dir --no-build-isolation --no-deps -w /dist .
RUN rm -rf /app/vllm

############# Final image #############
FROM base AS final
WORKDIR /app/vllm
RUN --mount=type=bind,from=build_vllm,src=/dist/,target=/dist_vllm \
    --mount=type=bind,from=build_triton,src=/dist/,target=/dist_triton \
    --mount=type=bind,from=build_fa,src=/dist/,target=/dist_fa \
    pip install --no-cache-dir /dist_triton/*.whl /dist_fa/*.whl /dist_vllm/*.whl && \
    pip install --no-cache-dir opentelemetry-sdk opentelemetry-api \
        opentelemetry-semantic-conventions-ai opentelemetry-exporter-otlp modelscope && \
    true

# Patch RMSNormGated to add missing 'activation' parameter (upstream fix not in mobydick fork)
RUN LAYERNORM=$(python3 -c "import vllm.model_executor.layers.layernorm as m; print(m.__file__)") && \
    sed -i 's/norm_before_gate: bool = False,/norm_before_gate: bool = False,\n        activation: str = "swish",/' "$LAYERNORM" && \
    sed -i 's/self.norm_before_gate = norm_before_gate/self.norm_before_gate = norm_before_gate\n        self.activation = activation/' "$LAYERNORM"

CMD ["/bin/bash"]
