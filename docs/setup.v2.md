# Hardware + software setup V2 (aimemer)

## HW
- 64 CPUs, ~256GB RAM
- 4x AMD Vega 20 (Radeon Instinct MI50, gfx906, 16GB VRAM each = 64GB total)
- 1.86TB NVMe (LVM thin pool)

## SW
- Proxmox VE 9.1 -> privileged LXC -> K3s -> Helm

## Architecture
```
Proxmox host (192.168.1.198)
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
    │       └── llama-cpp (Helm release)
    │           ├── Image: larkinwc/llama.cpp-gfx906:full-rocm-6.3.3
    │           ├── Model: /models/Qwen3.5-35B-A3B-Q8_0.gguf (hostPath)
    │           └── GPU: all 4x via /dev/kfd + /dev/dri hostPath mounts
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

## K3s LXC setup

### Key gotchas
- K3s in LXC needs `/dev/kmsg` - add `lxc.cgroup2.devices.allow: c 1:11 rwm` and bind mount
- Must set `lxc.apparmor.profile: unconfined` and `lxc.mount.auto: proc:rw sys:rw cgroup:rw`
- Load kernel modules on the **host**, not inside the LXC
- `k3s-lxc-fix.service` must run before k3s to set mount propagation (`mount --make-rshared /`)
- `HSA_OVERRIDE_GFX_VERSION=9.0.6` is required as env var for ROCm on gfx906

### Config files
All in [`deploy/k3s-lxc/`](../deploy/k3s-lxc/):
- `lxc.conf` - LXC container config (copy to `/etc/pve/lxc/<CTID>.conf`)
- `k3s-lxc-fix.service` - systemd unit (install inside LXC)
- `host-sysctl.conf` - sysctl settings (install on Proxmox host at `/etc/sysctl.d/k3s.conf`)
- `host-modules.conf` - kernel modules (install on host at `/etc/modules-load.d/k3s.conf`)
- `llamacpp-values.yaml` - Helm values for llama.cpp deployment

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

### Model performance
- Qwen3.5-35B-A3B Q8_0 (35GB) on 4x MI50
- ~45 tokens/sec generation speed
- 131K context (65K per slot x 2 parallel)
- Pipeline parallelism across all 4 GPUs
- KV cache: 2560 MiB across GPUs
