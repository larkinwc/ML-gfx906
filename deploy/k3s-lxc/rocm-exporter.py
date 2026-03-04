#!/usr/bin/env python3
"""Prometheus exporter for AMD GPUs using rocm-smi.

Works with pre-CDNA GPUs (Vega 20 / MI50 / gfx906) where the official
AMD device-metrics-exporter reports 0 for temperature and power.

Exports on :9101/metrics every 5 seconds.
"""
import subprocess, json, re, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

metrics_text = ""


def parse_mhz(s):
    m = re.search(r"(\d+)", str(s))
    return float(m.group(1)) if m else 0


def collect():
    global metrics_text
    while True:
        try:
            r = subprocess.run(["rocm-smi", "--showallinfo", "--json"],
                               capture_output=True, text=True, timeout=10)
            data = json.loads(r.stdout)

            r2 = subprocess.run(["rocm-smi", "--showmeminfo", "vram", "--json"],
                                capture_output=True, text=True, timeout=10)
            memdata = json.loads(r2.stdout)

            lines = [
                "# HELP rocm_gpu_temperature_edge GPU edge temperature C",
                "# TYPE rocm_gpu_temperature_edge gauge",
                "# HELP rocm_gpu_temperature_junction GPU junction temperature C",
                "# TYPE rocm_gpu_temperature_junction gauge",
                "# HELP rocm_gpu_temperature_memory GPU memory temperature C",
                "# TYPE rocm_gpu_temperature_memory gauge",
                "# HELP rocm_gpu_power_watts GPU power draw Watts",
                "# TYPE rocm_gpu_power_watts gauge",
                "# HELP rocm_gpu_power_max_watts GPU max power cap Watts",
                "# TYPE rocm_gpu_power_max_watts gauge",
                "# HELP rocm_gpu_vram_used_bytes VRAM used bytes",
                "# TYPE rocm_gpu_vram_used_bytes gauge",
                "# HELP rocm_gpu_vram_total_bytes VRAM total bytes",
                "# TYPE rocm_gpu_vram_total_bytes gauge",
                "# HELP rocm_gpu_vram_pct VRAM usage percent",
                "# TYPE rocm_gpu_vram_pct gauge",
                "# HELP rocm_gpu_utilization GPU utilization percent",
                "# TYPE rocm_gpu_utilization gauge",
                "# HELP rocm_gpu_mem_activity Memory controller activity percent",
                "# TYPE rocm_gpu_mem_activity gauge",
                "# HELP rocm_gpu_fan_speed_pct Fan speed percent",
                "# TYPE rocm_gpu_fan_speed_pct gauge",
                "# HELP rocm_gpu_sclk_mhz Shader clock MHz",
                "# TYPE rocm_gpu_sclk_mhz gauge",
                "# HELP rocm_gpu_mclk_mhz Memory clock MHz",
                "# TYPE rocm_gpu_mclk_mhz gauge",
                "# HELP rocm_gpu_voltage_mv GPU voltage mV",
                "# TYPE rocm_gpu_voltage_mv gauge",
            ]

            for key in sorted(data):
                if not key.startswith("card"):
                    continue
                gid = key.replace("card", "")
                gpu = data[key]

                def fval(k, default=0):
                    v = gpu.get(k, default)
                    try:
                        return float(str(v).split()[0])
                    except Exception:
                        return default

                temp_edge = fval("Temperature (Sensor edge) (C)")
                temp_junc = fval("Temperature (Sensor junction) (C)")
                temp_mem = fval("Temperature (Sensor memory) (C)")
                power = fval("Current Socket Graphics Package Power (W)")
                power_max = fval("Max Graphics Package Power (W)")
                gpu_use = fval("GPU use (%)")
                vram_pct = fval("GPU Memory Allocated (VRAM%)")
                mem_rw = fval("GPU Memory Read/Write Activity (%)")
                fan = fval("Fan speed (%)")
                voltage = fval("Voltage (mV)")
                sclk = parse_mhz(gpu.get("sclk clock speed:", "0"))
                mclk = parse_mhz(gpu.get("mclk clock speed:", "0"))

                vram_used = 0
                vram_total = 0
                if key in memdata:
                    mg = memdata[key]
                    try: vram_total = float(str(mg.get("VRAM Total Memory (B)", 0)))
                    except Exception: pass
                    try: vram_used = float(str(mg.get("VRAM Total Used Memory (B)", 0)))
                    except Exception: pass

                l = lines.append
                l(f'rocm_gpu_temperature_edge{{gpu_id="{gid}"}} {temp_edge}')
                l(f'rocm_gpu_temperature_junction{{gpu_id="{gid}"}} {temp_junc}')
                l(f'rocm_gpu_temperature_memory{{gpu_id="{gid}"}} {temp_mem}')
                l(f'rocm_gpu_power_watts{{gpu_id="{gid}"}} {power}')
                l(f'rocm_gpu_power_max_watts{{gpu_id="{gid}"}} {power_max}')
                l(f'rocm_gpu_vram_used_bytes{{gpu_id="{gid}"}} {vram_used}')
                l(f'rocm_gpu_vram_total_bytes{{gpu_id="{gid}"}} {vram_total}')
                l(f'rocm_gpu_vram_pct{{gpu_id="{gid}"}} {vram_pct}')
                l(f'rocm_gpu_utilization{{gpu_id="{gid}"}} {gpu_use}')
                l(f'rocm_gpu_mem_activity{{gpu_id="{gid}"}} {mem_rw}')
                l(f'rocm_gpu_fan_speed_pct{{gpu_id="{gid}"}} {fan}')
                l(f'rocm_gpu_sclk_mhz{{gpu_id="{gid}"}} {sclk}')
                l(f'rocm_gpu_mclk_mhz{{gpu_id="{gid}"}} {mclk}')
                l(f'rocm_gpu_voltage_mv{{gpu_id="{gid}"}} {voltage}')

            metrics_text = "\n".join(lines) + "\n"
        except Exception as e:
            print(f"collect error: {e}", flush=True)
        time.sleep(5)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(metrics_text.encode())

    def log_message(self, *a):
        pass


threading.Thread(target=collect, daemon=True).start()
time.sleep(3)
print("rocm-smi exporter listening on :9101", flush=True)
HTTPServer(("0.0.0.0", 9101), Handler).serve_forever()
