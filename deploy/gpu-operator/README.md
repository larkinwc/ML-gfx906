# GPU Operator gfx906 examples

These manifests assume the gfx906 lane from
[`gpu-operator-gfx906`](https://github.com/larkinwc/gpu-operator-gfx906) is
installed and that the target nodes expose:

- `feature.node.kubernetes.io/amd-gpu-gfx906=true`
- allocatable `amd.com/gpu`

Files:

- `rocm-smoke.yaml`: Base ROCm 7.2 pod for `rocminfo` and `rocm-smi`
- `vllm-qwen3.5-27b.yaml`: vLLM deployment scheduled onto gfx906 nodes through
  the device plugin

Apply:

```bash
kubectl apply -f deploy/gpu-operator/rocm-smoke.yaml
kubectl apply -f deploy/gpu-operator/vllm-qwen3.5-27b.yaml
```
