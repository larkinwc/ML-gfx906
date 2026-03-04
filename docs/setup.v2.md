# Hardware + software setup V2 (aimemer)

## HW
- 64 CPUs, ~256GB RAM
- 4x AMD Vega 20 (Radeon Instinct MI50, gfx906, **32GB VRAM each = 128GB total**)
- 1.86TB NVMe (LVM thin pool)

## SW
- Proxmox VE 9.1 -> privileged LXC -> K3s -> Helm
- Kernel cmdline: `intel_iommu=on iommu=pt` (prevents DMAR crashes on GPU DMA)

## Architecture
```
Proxmox host (192.168.1.198)
├── Kernel: 6.17.2-1-pve, intel_iommu=on iommu=pt
├── Host kernel modules: br_netfilter, overlay, ip_tables, ip_vs, nf_conntrack
├── Host sysctl: ip_forward, bridge-nf-call-iptables, nf_conntrack_max
├── /dev/dri/card0-4, renderD128-131 (4x Vega 20 + ASPEED BMC)
├── /dev/kfd (ROCm compute)
├── LVM thin pool "data" (1.75TB)
│   ├── vm-100-disk-0 (200GB) - LXC rootfs
│   └── docker (500GB) - Docker build storage on host
│
└── LXC 100 (CTID 100, IP: 192.168.1.199)
    ├── Ubuntu 24.04, 48 cores, 200GB RAM
    ├── Privileged: apparmor unconfined, GPU device passthrough
    ├── k3s-lxc-fix.service (mount propagation + /dev/kmsg)
    ├── K3s v1.34 (server + worker, no taints)
    │   └── Namespace: llm
    │       ├── llama-cpp (Helm release)
    │       │   ├── Image: larkinwc/llama.cpp-gfx906:full-rocm-6.3.3
    │       │   ├── Model: /models/Qwen3.5-35B-A3B-Q8_0.gguf (hostPath)
    │       │   ├── GPU: all 4x via /dev/kfd + /dev/dri hostPath mounts
    │       │   ├── API key auth via LLAMA_API_KEY
    │       │   └── 262K context (131K per slot x 2 parallel)
    │       ├── rocm-exporter (Deployment)
    │       │   ├── Image: larkinwc/rocm-gfx906:6.3.3-complete
    │       │   └── Prometheus metrics on :9101 (temps, VRAM, power, clocks)
    │       ├── prometheus (Deployment)
    │       │   └── Scrapes llamacpp :8080 + rocm-exporter :9101
    │       ├── grafana (Deployment)
    │       │   └── Dashboards: GPU Monitoring, LLM Inference
    │       └── cloudflared (Deployment)
    │           └── Cloudflare tunnel -> llama-server
    └── /root/models/ (GGUF model files)
```

## Docker Hub images
Built from this repo on the Proxmox host:
- `docker.io/larkinwc/rocm-gfx906:6.3.3-complete` - ROCm base with recompiled rocBLAS (Tensile gfx906) + rccl
- `docker.io/larkinwc/llama.cpp-gfx906:full-rocm-6.3.3` - llama.cpp latest master on ROCm 6.3.3

Build process:
```bash
# ROCm base (takes ~1hr on 64 cores)
source rocm/preset.rocm-6.3.3.sh && bash rocm/build-and-push.rocm.sh

# llama.cpp (takes ~5min)
source llama.cpp/preset.rocm-6.3.3.sh && bash llama.cpp/build-and-push.rocm.sh
```

## API
- **Auth**: `Authorization: Bearer <API_KEY>` (standard OpenAI-compatible, set via `LLAMA_API_KEY` env var)
- OpenAI-compatible: `/v1/chat/completions`, `/v1/models`, `/health`
- Exposed via Cloudflare tunnel (cloudflared deployment in K3s)

## K3s LXC setup

### Key gotchas
- K3s in LXC needs `/dev/kmsg` - add `lxc.cgroup2.devices.allow: c 1:11 rwm` and bind mount
- Must set `lxc.apparmor.profile: unconfined` and `lxc.mount.auto: proc:rw sys:rw cgroup:rw`
- Load kernel modules on the **host**, not inside the LXC
- `k3s-lxc-fix.service` must run before k3s to set mount propagation (`mount --make-rshared /`)
- `HSA_OVERRIDE_GFX_VERSION=9.0.6` is required as env var for ROCm on gfx906
- `intel_iommu=on iommu=pt` in GRUB - prevents DMAR/VT-d crashes during heavy GPU DMA

### Config files
All in [`deploy/k3s-lxc/`](../deploy/k3s-lxc/):
- `lxc.conf` - LXC container config (copy to `/etc/pve/lxc/<CTID>.conf`)
- `k3s-lxc-fix.service` - systemd unit (install inside LXC)
- `host-sysctl.conf` - sysctl settings (install on Proxmox host at `/etc/sysctl.d/k3s.conf`)
- `host-modules.conf` - kernel modules (install on host at `/etc/modules-load.d/k3s.conf`)
- `llamacpp-values.yaml` - Helm values for llama.cpp deployment
- `rocm-exporter.py` - GPU metrics exporter script (temps, VRAM, power, clocks)
- `rocm-exporter.yaml` - K8s manifests for the exporter (Deployment + Service)
- `monitoring.yaml` - Prometheus + Grafana stack

### Deploy llama.cpp
```bash
# Inside LXC (pct exec 100 -- bash)
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Clone chart
git clone https://github.com/mixa3607/charts.git /root/charts
cd /root/charts/charts/llamacpp && helm dependency build

# Download model
mkdir -p /root/models
curl -L -o /root/models/Qwen3.5-35B-A3B-Q8_0.gguf \
  https://huggingface.co/unsloth/Qwen3.5-35B-A3B-GGUF/resolve/main/Qwen3.5-35B-A3B-Q8_0.gguf

# Deploy
helm install llama-cpp /root/charts/charts/llamacpp \
  -f /path/to/llamacpp-values.yaml -n llm --create-namespace

# Verify
kubectl get pods -n llm
curl http://<service-ip>:8080/health
```

### Deploy monitoring
```bash
# Inside LXC (pct exec 100 -- bash)
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Deploy Prometheus + Grafana
kubectl apply -f /path/to/monitoring.yaml

# Deploy ROCm GPU exporter
kubectl create configmap rocm-exporter-script -n llm \
  --from-file=exporter.py=/path/to/rocm-exporter.py
kubectl apply -f /path/to/rocm-exporter.yaml

# Verify
kubectl get pods -n llm
curl http://<rocm-exporter-svc>:9101/metrics
```

Grafana dashboards (GPU Monitoring + LLM Inference) can be imported via the API
or manually after first deploy. Grafana is on port 3000 (admin/admin).

### Switching models
```bash
# Inside LXC (pct exec 100 -- bash)
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# 1. Download new model to /root/models/
curl -L -o /root/models/NewModel.gguf <huggingface-url>

# 2. Update the deployment env vars
kubectl set env deployment/llama-cpp-llamacpp -n llm \
  LLAMA_ARG_MODEL=/models/NewModel.gguf \
  LLAMA_ARG_ALIAS=new-model-name \
  LLAMA_ARG_CTX_SIZE=262144

# Pod will auto-restart and load the new model.
# Old model files can be removed from /root/models/ to free space.

# To revert, just set env vars back to the previous model path.
```

### VRAM budget (128GB total)
| Component | Q8_0 (current) | BF16 |
|-----------|----------------|------|
| Weights | ~35GB | ~69GB |
| KV cache (262K ctx) | ~5GB | ~5GB |
| Recurrent state | ~125MB | ~125MB |
| Compute buffers | ~3.5GB | ~4GB |
| **Total** | **~44GB** | **~78GB** |
| **Free VRAM** | **~84GB** | **~50GB** |

Q8_0 is recommended — practically lossless quality with 84GB VRAM headroom.

### Model performance
- Qwen3.5-35B-A3B Q8_0 (35GB) on 4x MI50 32GB
- ~45 tokens/sec generation speed
- 262K total context (131K per slot x 2 parallel)
- Pipeline parallelism across all 4 GPUs
- KV cache: 5120 MiB across GPUs (only 10 attention layers, rest is linear/recurrent)
