#!/usr/bin/env python3
"""Prometheus exporter for llama.cpp prompt cache metrics.

Streams llama.cpp pod logs via K8s API and extracts prompt cache
hit/miss statistics per slot.

Exports on :9102/metrics.
"""
import os, re, sys, threading, collections, time, urllib.request, ssl
from http.server import HTTPServer, BaseHTTPRequestHandler

history = collections.deque(maxlen=100)
total_prompt_tokens = 0
total_cached_tokens = 0
total_processed_tokens = 0
total_requests = 0
lock = threading.Lock()

RE_SIM = re.compile(
    r"slot get_availabl:.*sim_best\s*=\s*([\d.]+).*f_keep\s*=\s*([\d.]+)"
)
RE_PROMPT = re.compile(
    r"slot update_slots:.*prompt processing done,\s*n_tokens\s*=\s*(\d+),\s*"
    r"batch\.n_tokens\s*=\s*(\d+)"
)
pending_sim = {}


def parse_line(line):
    global total_prompt_tokens, total_cached_tokens
    global total_processed_tokens, total_requests

    m = RE_SIM.search(line)
    if m:
        sim_best = float(m.group(1))
        f_keep = float(m.group(2))
        sid = re.search(r"id\s+(\d+)", line)
        if sid:
            pending_sim[sid.group(1)] = (sim_best, f_keep)
        return

    m = RE_PROMPT.search(line)
    if m:
        n_tokens = int(m.group(1))
        batch_tokens = int(m.group(2))
        cached = n_tokens - batch_tokens

        sid = re.search(r"id\s+(\d+)", line)
        slot_id = sid.group(1) if sid else "?"
        sim_best, f_keep = pending_sim.pop(slot_id, (0.0, 0.0))

        with lock:
            total_prompt_tokens += n_tokens
            total_cached_tokens += cached
            total_processed_tokens += batch_tokens
            total_requests += 1
            history.append({
                "slot": slot_id,
                "n_tokens": n_tokens,
                "batch_tokens": batch_tokens,
                "cached": cached,
                "sim_best": sim_best,
                "f_keep": f_keep,
            })


def k8s_log_stream():
    """Stream logs from the llama-cpp pod via K8s API."""
    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    ns = os.environ.get("POD_NAMESPACE", "llm")
    label = os.environ.get("LLAMA_LABEL_SELECTOR", "app.kubernetes.io/name=llamacpp")
    api = "https://kubernetes.default.svc"

    ctx = ssl.create_default_context(cafile=ca_path)

    while True:
        try:
            with open(token_path) as f:
                token = f.read().strip()
            headers = {"Authorization": f"Bearer {token}"}

            # Find the llama-cpp pod
            url = f"{api}/api/v1/namespaces/{ns}/pods?labelSelector={label}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx) as resp:
                import json
                pods = json.loads(resp.read())

            if not pods["items"]:
                print("No llama-cpp pods found, retrying in 10s", flush=True)
                time.sleep(10)
                continue

            pod_name = pods["items"][0]["metadata"]["name"]
            print(f"Streaming logs from pod: {pod_name}", flush=True)

            # Stream logs with follow
            url = (f"{api}/api/v1/namespaces/{ns}/pods/{pod_name}/log"
                   f"?follow=true&sinceSeconds=10")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=3600) as resp:
                for raw_line in resp:
                    parse_line(raw_line.decode("utf-8", errors="replace"))

        except Exception as e:
            print(f"Log stream error: {e}, reconnecting in 5s", flush=True)
            time.sleep(5)


def stdin_stream():
    for line in sys.stdin:
        parse_line(line)


def build_metrics():
    with lock:
        lines = [
            "# HELP llamacpp_cache_prompt_tokens_total Total prompt tokens seen",
            "# TYPE llamacpp_cache_prompt_tokens_total counter",
            f"llamacpp_cache_prompt_tokens_total {total_prompt_tokens}",
            "# HELP llamacpp_cache_cached_tokens_total Tokens served from cache",
            "# TYPE llamacpp_cache_cached_tokens_total counter",
            f"llamacpp_cache_cached_tokens_total {total_cached_tokens}",
            "# HELP llamacpp_cache_processed_tokens_total Tokens actually processed",
            "# TYPE llamacpp_cache_processed_tokens_total counter",
            f"llamacpp_cache_processed_tokens_total {total_processed_tokens}",
            "# HELP llamacpp_cache_requests_total Total requests with cache data",
            "# TYPE llamacpp_cache_requests_total counter",
            f"llamacpp_cache_requests_total {total_requests}",
        ]

        if history:
            avg_hit = sum(
                h["cached"] / max(h["n_tokens"], 1) for h in history
            ) / len(history)
            avg_sim = sum(h["sim_best"] for h in history) / len(history)
            last = history[-1]
        else:
            avg_hit = avg_sim = 0.0
            last = {"cached": 0, "n_tokens": 0, "batch_tokens": 0,
                     "sim_best": 0, "f_keep": 0}

        lines.extend([
            "# HELP llamacpp_cache_hit_ratio Rolling avg cache hit ratio",
            "# TYPE llamacpp_cache_hit_ratio gauge",
            f"llamacpp_cache_hit_ratio {avg_hit:.4f}",
            "# HELP llamacpp_cache_similarity Rolling avg LCP similarity",
            "# TYPE llamacpp_cache_similarity gauge",
            f"llamacpp_cache_similarity {avg_sim:.4f}",
            "# HELP llamacpp_cache_last_total Last request total prompt tokens",
            "# TYPE llamacpp_cache_last_total gauge",
            f'llamacpp_cache_last_total {last["n_tokens"]}',
            "# HELP llamacpp_cache_last_cached Last request cached tokens",
            "# TYPE llamacpp_cache_last_cached gauge",
            f'llamacpp_cache_last_cached {last["cached"]}',
            "# HELP llamacpp_cache_last_processed Last request processed tokens",
            "# TYPE llamacpp_cache_last_processed gauge",
            f'llamacpp_cache_last_processed {last["batch_tokens"]}',
        ])
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(build_metrics().encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    mode = os.environ.get("MODE", "k8s")
    if mode == "k8s":
        threading.Thread(target=k8s_log_stream, daemon=True).start()
    else:
        threading.Thread(target=stdin_stream, daemon=True).start()

    port = int(os.environ.get("PORT", "9102"))
    print(f"llamacpp cache exporter listening on :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
