import json
import os
import re
import sys
import time

import webview

from monitoring.monitor import SystemMonitor
from monitoring.network import NetworkMonitor
from monitoring.GPUMonitor import GPUMonitor

BASE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(BASE, "volt_settings.json")
FRONTEND = os.path.join(BASE, "frontend")

# Dev mode (python main.py --dev) loads your running dev server, so edits in
# frontend/src show up instantly. Vite uses 5173; Create React App uses 3000
# (set VOLT_DEV_URL=http://localhost:3000 for that).
DEV_URL = os.environ.get("VOLT_DEV_URL", "http://localhost:5173")

window = None


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def byte_conversion(n):
    n = float(n)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n:.0f} B"


def find_built_frontend():
    """The built React app: frontend/dist (Vite) or frontend/build (CRA)."""
    for folder in ("dist", "build"):
        index = os.path.join(FRONTEND, folder, "index.html")
        if os.path.exists(index):
            return index
    return None


class Api:
    # Attributes starting with "_" are hidden from the page; public methods are
    # callable from JavaScript as pywebview.api.<name>().

    def __init__(self):
        self._sys = SystemMonitor()
        self._net = NetworkMonitor()
        self._gpu = GPUMonitor()
        self._sent = self._net.get_bytes_sent()
        self._recv = self._net.get_bytes_receieved()
        self._t = time.time()
        self._maxed = False

    # ----- accent colour (saved to volt_settings.json) -----
    def get_accent(self):
        try:
            with open(SETTINGS, encoding="utf-8") as f:
                color = str(json.load(f).get("accent", ""))
            if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                return color.upper()
        except (OSError, ValueError):
            pass
        return "#FFFFFF"

    def save_accent(self, color):
        try:
            with open(SETTINGS, "w", encoding="utf-8") as f:
                json.dump({"accent": color}, f, indent=2)
            return True
        except OSError:
            return False

    # ----- window controls -----
    def minimize(self):
        window.minimize()

    def toggle_max(self):
        window.restore() if self._maxed else window.maximize()
        self._maxed = not self._maxed

    def close(self):
        window.destroy()

    # ----- live data, called by the page once a second -----
    def stats(self):
        now = time.time()
        sent = self._net.get_bytes_sent()
        recv = self._net.get_bytes_receieved()
        dt = max(now - self._t, 0.001)
        up = max(0.0, (sent - self._sent) / dt)
        down = max(0.0, (recv - self._recv) / dt)
        self._sent, self._recv, self._t = sent, recv, now

        # "netstats" holds text for the detail rows, keyed by group and row label.
        # Any row you don't fill in just shows "-".
        netstats = {
            "net.recv": byte_conversion(recv),
            "net.sent": byte_conversion(sent),
        }

        return {
            "cpu": num(self._sys.get_cpu_usage()),
            "mem": num(self._sys.get_memory_usage()),
            "disk": num(self._sys.get_disk_usage()),
            "gpu": num(self._gpu.get_gpu_usage()),
            "down": down,      # bytes per second
            "up": up,
            "netstats": netstats,
            "ifaces": [],      # add [["Wi-Fi", "192.168.1.5"], ...] for the adapter list
        }


if __name__ == "__main__":
    dev = "--dev" in sys.argv

    if dev:
        url = DEV_URL
    else:
        url = find_built_frontend()
        if url is None:
            sys.exit(
                "No built React app found in frontend/dist or frontend/build.\n"
                "Build it first:   cd frontend  &&  npm run build\n"
                "or run in dev mode:   npm run dev   (in frontend/)   then   python main.py --dev")

    window = webview.create_window(
        "VOLT | System Monitor",
        url,
        js_api=Api(),
        width=1100, height=700, min_size=(950, 600),
        frameless=True, easy_drag=False, background_color="#050505")

    # http_server=True serves the built files over local HTTP, so the absolute
    # /assets/... paths in a normal Vite or CRA build load correctly.
    webview.start(http_server=not dev)
