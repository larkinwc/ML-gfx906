# ROCm GFX906
Open software stack that includes programming models, tools, compilers, libraries, and runtimes for AI and HPC solution development on AMD GPUs.
In 6.4+ gfx906 support was dropped but may be manually compiled.

At this moment rebuild:
- rccl
- rocblas+tensile

Recommend use `docker.io/larkinwc/rocm-gfx906:7.2.0-complete` for the
gfx906 GPU Operator lane. Older tags remain useful for the host-mounted K3s
LXC workflow in this repo.

## Run
### Docker
TODO

### Kubernetes
For GPU Operator based clusters, use the selector
`feature.node.kubernetes.io/amd-gpu-gfx906=true` together with the standard
resource name `amd.com/gpu`.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: rocm-gfx906-smoke
  namespace: llm
spec:
  restartPolicy: Never
  nodeSelector:
    feature.node.kubernetes.io/amd-gpu-gfx906: "true"
  containers:
    - name: rocm
      image: docker.io/larkinwc/rocm-gfx906:7.2.0-complete
      imagePullPolicy: Always
      command: ["/bin/bash", "-lc"]
      args:
        - rocminfo && rocm-smi && sleep infinity
      env:
        - name: HSA_OVERRIDE_GFX_VERSION
          value: "9.0.6"
      resources:
        requests:
          amd.com/gpu: 1
          cpu: "1"
          memory: 2Gi
        limits:
          amd.com/gpu: 1
          memory: 8Gi
```

The full manifest is also checked in at
[`deploy/gpu-operator/rocm-smoke.yaml`](../deploy/gpu-operator/rocm-smoke.yaml).

## Build
See build vars in `./env.sh`. You also may use presetis `./preset.rocm-*.sh`. Exec `./build-and-push.rocm.sh`:
```bash
$ . preset.rocm-7.2.0.sh
$ ./build-and-push.rocm.sh
~/REPOS/mixa3607/llama.cpp-gfx906/rocm ~/REPOS/mixa3607/llama.cpp-gfx906/rocm
~/REPOS/mixa3607/llama.cpp-gfx906/rocm
~/REPOS/mixa3607/llama.cpp-gfx906/llama.cpp ~/REPOS/mixa3607/llama.cpp-gfx906/rocm
~/REPOS/mixa3607/llama.cpp-gfx906/rocm
~/REPOS/mixa3607/llama.cpp-gfx906/comfyui ~/REPOS/mixa3607/llama.cpp-gfx906/rocm
~/REPOS/mixa3607/llama.cpp-gfx906/rocm
~/REPOS/mixa3607/llama.cpp-gfx906/vllm ~/REPOS/mixa3607/llama.cpp-gfx906/rocm
~/REPOS/mixa3607/llama.cpp-gfx906/rocm
#0 building with "remote" instance using remote driver

#1 [internal] load build definition from rocm.Dockerfile
#1 transferring dockerfile: 4.95kB done
#1 DONE 0.0s

#2 [auth] dockerio-proxy/rocm/dev-ubuntu-24.04:pull rocm/dev-ubuntu-24.04:pull token for registry.arkprojects.space
#2 DONE 0.0s

#3 [internal] load metadata for docker.io/rocm/dev-ubuntu-24.04:7.0-complete
#3 DONE 1.8s

#4 [internal] load .dockerignore
#4 transferring context: 2B done
#...............
#24 exporting to image
#24 pushing layers 6.5s done
#24 pushing manifest for docker.io/mixa3607/rocm-gfx906:7.0.0-20251005035204-complete@sha256:00532f62462e80d51e48b021afb7875af53164455c84dc28b24eb29d39aa0005
#24 pushing manifest for docker.io/mixa3607/rocm-gfx906:7.0.0-20251005035204-complete@sha256:00532f62462e80d51e48b021afb7875af53164455c84dc28b24eb29d39aa0005 3.3s done
#24 pushing layers 2.0s done
#24 pushing manifest for docker.io/mixa3607/rocm-gfx906:7.0.0-complete@sha256:00532f62462e80d51e48b021afb7875af53164455c84dc28b24eb29d39aa0005
#24 pushing manifest for docker.io/mixa3607/rocm-gfx906:7.0.0-complete@sha256:00532f62462e80d51e48b021afb7875af53164455c84dc28b24eb29d39aa0005 2.2s done
#24 DONE 17.6s
```
