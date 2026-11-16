import ctypes
import json
import math
import os
import platform
import re
import socket
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque

import customtkinter as ctk
import psutil

from monitoring.monitor import SystemMonitor
from monitoring.network import NetworkMonitor

sys = SystemMonitor()
net = NetworkMonitor()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------- typography ----------
# SF Pro is used when installed; otherwise the closest system font.
FONT_CANDIDATES = ("SF Pro Display", "SF Pro Text", "Segoe UI Variable Display",
                   "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue",
                   "Helvetica", "Arial")
FONT = "Segoe UI"
BOLD = "bold"

# ---------- palette: iOS dark mode ----------
TEXT = "#FFFFFF"
MUTED = "#8E8E93"        # secondary label
DIM = "#636366"          # tertiary label
BG = "#000000"           # system background
CARD = "#1C1C1E"         # secondary grouped background
CARD_HI = "#2C2C2E"
SEP = "#38383A"          # separators
GRID = "#2C2C2E"
BORDER = "#2C2C2E"

IOS_BLUE = "#0A84FF"
IOS_GREEN = "#30D158"
IOS_ORANGE = "#FF9F0A"
IOS_PINK = "#FF375F"
IOS_PURPLE = "#BF5AF2"
IOS_TEAL = "#64D2FF"
IOS_YELLOW = "#FFD60A"
IOS_GRAY = "#8E8E93"

# ---------- animation timing ----------
SPLASH_IN = 0.7          # icon springs in
SPLASH_OUT_AT = 1.65     # icon zooms away
SPLASH_OUT_S = 0.45
SPLASH_TOTAL = SPLASH_OUT_AT + SPLASH_OUT_S
FRAME_MS = 8

SMOOTHING = 5.0          # higher = values catch up faster
HISTORY = 45
FRAME_DELAY = 16         # ~60 fps animation loop
PAGE_SLIDE_S = 0.30
PAGE_SLIDE_PX = 22

WINDOW_W, WINDOW_H = 1100, 720
TITLEBAR_H = 44
SIDEBAR_W = 232

# ---------- saved settings ----------
DEFAULT_ACCENT = IOS_BLUE
INTERVALS = (1000, 2000, 5000)
SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "volt_settings.json")


def load_settings():
    data = {"accent": DEFAULT_ACCENT, "reduce_motion": False, "interval": 1000}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if re.fullmatch(r"#[0-9a-fA-F]{6}", str(saved.get("accent", ""))):
            data["accent"] = saved["accent"].upper()
        data["reduce_motion"] = bool(saved.get("reduce_motion", False))
        if saved.get("interval") in INTERVALS:
            data["interval"] = saved["interval"]
    except (OSError, ValueError, AttributeError):
        pass
    return data


def save_settings(data):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError:
        return False


settings = load_settings()
UPDATE_MS = settings["interval"]     # how often real readings are taken


# ---------- helpers ----------

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def format_speed(bytes_per_sec):
    if bytes_per_sec >= 1024 ** 2:
        return f"{bytes_per_sec / 1024 ** 2:.2f} MB/s"
    if bytes_per_sec >= 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    return f"{max(bytes_per_sec, 0):.0f} B/s"


def format_bytes(n):
    n = float(n)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n:.0f} B"


def format_cache(kb):
    kb = num(kb)
    if kb <= 0:
        return "-"
    if kb >= 1024:
        mb = kb / 1024
        return f"{mb:.0f} MB" if mb == int(mb) else f"{mb:.1f} MB"
    return f"{kb:.0f} KB"


def pretty_vendor(v):
    return {"GenuineIntel": "Intel", "AuthenticAMD": "AMD"}.get(v, v or "-")


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_cubic(t):
    return t ** 3


def ease_out_back(t, c1=1.70158):
    """Overshoots slightly then settles - the 'spring' feel."""
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp_color(c1, c2, t):
    t = clamp(t)
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return "#%02x%02x%02x" % (
        int(lerp(r1, r2, t)), int(lerp(g1, g2, t)), int(lerp(b1, b2, t)))


def contrast_text(color):
    r, g, b = hex_to_rgb(color)
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "#FFFFFF"


def rounded_rect_points(cx, cy, w, h, r, steps=10):
    r = max(0, min(r, w / 2, h / 2))
    x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if r < 0.5:
        return [x1, y1, x2, y1, x2, y2, x1, y2]
    pts = []
    corners = [(x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
               (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)]
    for ccx, ccy, start in corners:
        for i in range(steps + 1):
            a = math.radians(start + 90 * i / steps)
            pts.extend([ccx + r * math.cos(a), ccy + r * math.sin(a)])
    return pts


def smooth_points(pts, sub=4):
    """Catmull-Rom spline through the points (gives the soft Stocks-app curve)."""
    n = len(pts)
    if n < 3:
        return list(pts)
    out = []
    for i in range(n - 1):
        p0, p1, p2 = pts[max(i - 1, 0)], pts[i], pts[i + 1]
        p3 = pts[min(i + 2, n - 1)]
        for k in range(sub):
            t = k / sub
            t2, t3 = t * t, t * t * t
            x = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(pts[-1])
    return out


def system_info():
    system = platform.system()
    if system == "Windows":
        try:
            build = int(platform.version().split(".")[-1])
        except ValueError:
            build = 0
        release = "11" if build >= 22000 else platform.release()
        os_name = f"Windows {release}"
    else:
        os_name = f"{system} {platform.release()}"

    cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
    threads = psutil.cpu_count()
    ram_gb = psutil.virtual_memory().total / 1024 ** 3
    return [
        ("Operating System", os_name),
        ("Architecture", platform.machine() or "-"),
        ("Processor", f"{cores} cores / {threads} threads"),
        ("Installed RAM", f"{ram_gb:.0f} GB"),
    ]


# ---------- hardware lookups (background threads so the UI never blocks) ----------

def _no_window_flags():
    return 0x08000000 if platform.system() == "Windows" else 0


class CpuInfo:
    def __init__(self):
        self.data = {}
        self.loaded = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        data = {}
        system = platform.system()
        try:
            if system == "Windows":
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Processor | Select-Object -First 1 "
                     "Name,Manufacturer,SocketDesignation,MaxClockSpeed,"
                     "L2CacheSize,L3CacheSize | ConvertTo-Json -Compress"],
                    capture_output=True, text=True, timeout=20,
                    creationflags=_no_window_flags())
                parsed = json.loads(out.stdout)
                data = {
                    "name": (parsed.get("Name") or "").strip(),
                    "vendor": parsed.get("Manufacturer") or "",
                    "socket": parsed.get("SocketDesignation") or "",
                    "rated_mhz": parsed.get("MaxClockSpeed"),
                    "l2_kb": parsed.get("L2CacheSize"),
                    "l3_kb": parsed.get("L3CacheSize"),
                }
            elif system == "Linux":
                with open("/proc/cpuinfo", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("model name") and "name" not in data:
                            data["name"] = line.split(":", 1)[1].strip()
                        elif line.startswith("vendor_id") and "vendor" not in data:
                            data["vendor"] = line.split(":", 1)[1].strip()
            elif system == "Darwin":
                out = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True, timeout=5)
                data["name"] = out.stdout.strip()
        except Exception:
            pass
        if not data.get("name"):
            data["name"] = platform.processor() or "Unknown processor"
        self.data = data
        self.loaded = True


class GpuMonitor:
    def __init__(self):
        self.name = None
        self.util = 0.0
        self.mem_used = 0.0
        self.mem_total = 0.0
        self.temp = 0.0
        self.available = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _lookup_name(self):
        if platform.system() != "Windows":
            return "Unknown GPU"
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController | "
                 "Select-Object -ExpandProperty Name) -join ', '"],
                capture_output=True, text=True, timeout=10,
                creationflags=_no_window_flags())
            return out.stdout.strip() or "Unknown GPU"
        except Exception:
            return "Unknown GPU"

    def _run(self):
        while True:
            try:
                out = subprocess.run(
                    ["nvidia-smi",
                     "--query-gpu=name,utilization.gpu,memory.used,"
                     "memory.total,temperature.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=_no_window_flags())
                if out.returncode != 0 or not out.stdout.strip():
                    raise RuntimeError("nvidia-smi failed")
                parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
                self.name = parts[0]
                self.util = num(parts[1])
                self.mem_used = num(parts[2])
                self.mem_total = num(parts[3])
                self.temp = num(parts[4])
                self.available = True
                time.sleep(2)
            except Exception:
                self.available = False
                if self.name is None:
                    self.name = self._lookup_name()
                time.sleep(15)


# ---------- icon drawing ----------

BOLT = ((0.12, -0.5), (-0.28, 0.08), (-0.02, 0.08),
        (-0.12, 0.5), (0.28, -0.08), (0.02, -0.08))


def draw_app_icon(c, cx, cy, size, color, fg="#FFFFFF", tags=()):
    """The Volt app icon: a squircle with a lightning bolt."""
    c.create_polygon(rounded_rect_points(cx, cy, size, size, size * 0.225),
                     fill=color, outline="", tags=tags)
    pts = []
    for bx, by in BOLT:
        pts += [cx + bx * size * 0.62, cy + by * size * 0.62]
    c.create_polygon(*pts, fill=fg, outline="", tags=tags)


def draw_nav_icon(c, kind, cx, cy, size, color):
    """Colored rounded-square icon with a white glyph (like iOS Settings)."""
    W = "#FFFFFF"
    u = size
    lw = max(1.5, u * 0.065)
    c.create_polygon(rounded_rect_points(cx, cy, u, u, u * 0.27),
                     fill=color, outline="")
    if kind == "overview":
        for dx in (-1, 1):
            for dy in (-1, 1):
                c.create_polygon(
                    rounded_rect_points(cx + dx * u * 0.15, cy + dy * u * 0.15,
                                        u * 0.22, u * 0.22, u * 0.05, steps=4),
                    fill=W, outline="")
    elif kind == "processor":
        b = u * 0.2
        c.create_rectangle(cx - b, cy - b, cx + b, cy + b, outline=W, width=lw)
        c.create_rectangle(cx - b * 0.45, cy - b * 0.45, cx + b * 0.45,
                           cy + b * 0.45, fill=W, outline="")
        for p in (-0.5, 0.5):
            px, py = cx + p * b, cy + p * b
            c.create_line(px, cy - b, px, cy - b - u * 0.1, fill=W, width=lw)
            c.create_line(px, cy + b, px, cy + b + u * 0.1, fill=W, width=lw)
            c.create_line(cx - b, py, cx - b - u * 0.1, py, fill=W, width=lw)
            c.create_line(cx + b, py, cx + b + u * 0.1, py, fill=W, width=lw)
    elif kind == "memory":
        c.create_rectangle(cx - u * 0.3, cy - u * 0.14, cx + u * 0.3,
                           cy + u * 0.12, outline=W, width=lw)
        for k in (-1, 0, 1):
            c.create_rectangle(cx + k * u * 0.17 - u * 0.05, cy - u * 0.06,
                               cx + k * u * 0.17 + u * 0.05, cy + u * 0.05,
                               fill=W, outline="")
        for i in range(5):
            x = cx - u * 0.24 + i * u * 0.12
            c.create_line(x, cy + u * 0.12, x, cy + u * 0.21, fill=W, width=lw)
    elif kind == "graphics":
        c.create_rectangle(cx - u * 0.29, cy - u * 0.21, cx + u * 0.29,
                           cy + u * 0.1, outline=W, width=lw)
        c.create_line(cx, cy + u * 0.1, cx, cy + u * 0.2, fill=W, width=lw)
        c.create_line(cx - u * 0.13, cy + u * 0.21, cx + u * 0.13,
                      cy + u * 0.21, fill=W, width=lw, capstyle="round")
    elif kind == "network":
        oy = cy + u * 0.17
        c.create_oval(cx - u * 0.045, oy - u * 0.045, cx + u * 0.045,
                      oy + u * 0.045, fill=W, outline="")
        for r in (0.14, 0.25, 0.36):
            rr = u * r
            c.create_arc(cx - rr, oy - rr, cx + rr, oy + rr, start=45,
                         extent=90, style="arc", outline=W, width=lw)
    else:  # settings: three sliders
        for y, kx in ((-0.17, -0.1), (0, 0.12), (0.17, -0.02)):
            c.create_line(cx - u * 0.26, cy + y * u, cx + u * 0.26,
                          cy + y * u, fill=W, width=lw * 0.8)
            kr = u * 0.065
            c.create_oval(cx + kx * u - kr, cy + y * u - kr,
                          cx + kx * u + kr, cy + y * u + kr,
                          fill=W, outline=color, width=lw * 0.5)


# ---------- custom canvas widgets ----------

class ValueLabel(ctk.CTkLabel):
    """Label that skips redraws when the text hasn't changed."""

    def __init__(self, master, text, size, color=TEXT, weight=BOLD, **kw):
        super().__init__(master, text=text, text_color=color,
                         font=(FONT, size, weight), **kw)
        self._shown = text

    def set_text(self, text):
        if text != self._shown:
            self._shown = text
            self.configure(text=text)


class RingGauge(tk.Canvas):
    """Apple-Fitness style ring with rounded caps."""

    def __init__(self, master, size, bg, scale=1.0, accent=TEXT, color=None):
        self.px = int(size * scale)
        super().__init__(master, width=self.px, height=self.px, bg=bg,
                         highlightthickness=0, bd=0)
        self.bg_color = bg
        self.sc = scale
        self.accent = accent
        self.fixed = color          # None -> follows the accent colour
        self.value = -1.0
        self.stale = False
        self.num_px = int(40 * scale)
        self.pct_px = int(16 * scale)
        self.num_font = tkfont.Font(family=FONT, size=-self.num_px, weight=BOLD)
        self.pct_font = tkfont.Font(family=FONT, size=-self.pct_px, weight=BOLD)
        self.set_value(0)

    @property
    def color(self):
        return self.fixed or self.accent

    def set_accent(self, color):
        self.accent = color
        if self.fixed:
            return
        if self.winfo_viewable():
            self.refresh()
        else:
            self.stale = True

    def refresh(self):
        self.draw(max(self.value, 0))

    def set_value(self, v):
        v = clamp(v, 0, 100)
        if self.value >= 0 and abs(v - self.value) < 0.08 and not self.stale:
            return
        self.value = v
        self.draw(v)

    def draw(self, v):
        c, s, px = self, self.sc, self.px
        lw = 17 * s
        m = lw / 2 + 5 * s
        box = (m, m, px - m, px - m)
        cx = cy = px / 2
        radius = (px - 2 * m) / 2
        col = self.color

        c.delete("all")
        c.create_oval(*box, outline=lerp_color(self.bg_color, col, 0.22),
                      width=lw)
        if v > 0.3:
            extent = -359.9 * v / 100
            c.create_arc(*box, start=90, extent=extent, style="arc",
                         outline=col, width=lw)
            cap = lw / 2
            c.create_oval(cx - cap, cy - radius - cap, cx + cap,
                          cy - radius + cap, fill=col, width=0)
            ang = math.radians(90 + extent)
            hx = cx + radius * math.cos(ang)
            hy = cy - radius * math.sin(ang)
            c.create_oval(hx - cap, hy - cap, hx + cap, hy + cap,
                          fill=col, width=0)

        text = f"{v:.0f}"
        nw = self.num_font.measure(text)
        pw = self.pct_font.measure("%")
        gap = 3 * s
        x0 = cx - (nw + gap + pw) / 2
        c.create_text(x0, cy, text=text, anchor="w", fill=TEXT,
                      font=(FONT, -self.num_px, BOLD))
        c.create_text(x0 + nw + gap, cy + self.num_px * 0.14, text="%",
                      anchor="w", fill=MUTED, font=(FONT, -self.pct_px, BOLD))
        self.stale = False


class SparkChart(tk.Canvas):
    """Smooth scrolling area chart. `colors` entries of None follow the accent."""

    def __init__(self, master, bg, scale=1.0, height=110, accent=TEXT,
                 colors=(None,), fixed_max=None, fmt=format_speed,
                 floor=64 * 1024.0):
        super().__init__(master, height=int(height * scale), bg=bg,
                         highlightthickness=0, bd=0)
        self.bg_color = bg
        self.sc = scale
        self.accent = accent
        self.colors = colors
        self.series = [deque([0.0] * HISTORY, maxlen=HISTORY) for _ in colors]
        self.fixed_max = fixed_max
        self.fmt = fmt
        self.floor = floor
        self.y_scale = float(fixed_max or floor)
        self.t0 = time.perf_counter()
        self.last_draw = 0.0
        self.label_font = (FONT, -int(11 * scale))

    def push(self, *values):
        for data, v in zip(self.series, values):
            data.append(v)
        self.t0 = time.perf_counter()

    def redraw(self, dt):
        W, H = self.winfo_width(), self.winfo_height()
        if W < 40 or H < 30:
            return

        if self.fixed_max:
            self.y_scale = float(self.fixed_max)
        else:
            peak = max(max(max(d) for d in self.series), self.floor) * 1.25
            self.y_scale += (peak - self.y_scale) * (1 - math.exp(-3.0 * dt))

        now = time.perf_counter()
        if now - self.last_draw < 0.028:
            return
        self.last_draw = now

        s = self.sc
        self.delete("all")
        pad_t, pad_b = 20 * s, 6 * s
        usable = H - pad_t - pad_b

        for k in (0, 1 / 3, 2 / 3, 1):
            y = pad_t + usable * k
            self.create_line(0, y, W, y, fill=GRID, dash=(2, 4))
        self.create_text(2, 2, anchor="nw", fill=DIM, font=self.label_font,
                         text=self.fmt(self.y_scale))

        frac = clamp((now - self.t0) / (UPDATE_MS / 1000))
        dx = W / (HISTORY - 2)
        floor_y = H - pad_b

        for idx in reversed(range(len(self.series))):
            data = self.series[idx]
            color = self.colors[idx] or self.accent
            pts = []
            for i, v in enumerate(data):
                x = W + dx * (1 - frac) - (HISTORY - 1 - i) * dx
                y = floor_y - clamp(v / self.y_scale) * usable
                pts.append((x, y))
            sm = [(x, min(max(y, pad_t), floor_y))
                  for x, y in smooth_points(pts, 4)]
            flat = [v for p in sm for v in p]
            self.create_polygon(*flat, sm[-1][0], floor_y, sm[0][0], floor_y,
                                fill=lerp_color(self.bg_color, color, 0.14),
                                outline="")
            self.create_line(*flat, width=2.5 * s, fill=color,
                             capstyle="round", joinstyle="round")


class ToggleSwitch(tk.Canvas):
    """iOS switch with an animated knob."""

    def __init__(self, master, bg, scale, value, command, on_color=IOS_GREEN):
        self.sc = scale
        self.w, self.h = int(51 * scale), int(31 * scale)
        super().__init__(master, width=self.w, height=self.h, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.on_color = on_color
        self.value = bool(value)
        self.pos = 1.0 if self.value else 0.0
        self.anim = 0
        self.bind("<Button-1>", self.toggle)
        self.draw()

    def toggle(self, _event=None):
        self.value = not self.value
        self.anim += 1
        self._step(time.perf_counter(), self.pos,
                   1.0 if self.value else 0.0, self.anim)
        self.command(self.value)

    def _step(self, start, frm, to, token):
        if token != self.anim:
            return
        t = clamp((time.perf_counter() - start) / 0.22)
        self.pos = lerp(frm, to, ease_out_cubic(t))
        self.draw()
        if t < 1:
            self.after(8, lambda: self._step(start, frm, to, token))

    def draw(self):
        self.delete("all")
        w, h = self.w, self.h
        self.create_polygon(rounded_rect_points(w / 2, h / 2, w, h, h / 2),
                            fill=lerp_color("#39393D", self.on_color, self.pos),
                            outline="")
        r = h / 2 - 2 * self.sc
        x = lerp(h / 2, w - h / 2, self.pos)
        self.create_oval(x - r, h / 2 - r + 1, x + r, h / 2 + r + 1,
                         fill="#0B0B0B", width=0)
        self.create_oval(x - r, h / 2 - r, x + r, h / 2 + r,
                         fill="#FFFFFF", width=0)


class SegmentedControl(tk.Canvas):
    """iOS segmented control with a sliding thumb."""

    def __init__(self, master, bg, scale, options, index, command, seg_w=60):
        self.sc = scale
        self.options = options
        self.seg_w = int(seg_w * scale)
        self.w = self.seg_w * len(options) + 4
        self.h = int(32 * scale)
        super().__init__(master, width=self.w, height=self.h, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.index = index
        self.pos = float(index)
        self.command = command
        self.anim = 0
        self.bind("<Button-1>", self.on_click)
        self.draw()

    def on_click(self, event):
        i = int(clamp((event.x - 2) // self.seg_w, 0, len(self.options) - 1))
        if i == self.index:
            return
        self.index = i
        self.anim += 1
        self._step(time.perf_counter(), self.pos, float(i), self.anim)
        self.command(i)

    def _step(self, start, frm, to, token):
        if token != self.anim:
            return
        t = clamp((time.perf_counter() - start) / 0.25)
        self.pos = lerp(frm, to, ease_out_back(t, 0.9))
        self.draw()
        if t < 1:
            self.after(8, lambda: self._step(start, frm, to, token))

    def draw(self):
        self.delete("all")
        w, h, s = self.w, self.h, self.sc
        self.create_polygon(rounded_rect_points(w / 2, h / 2, w, h, 9 * s),
                            fill=CARD_HI, outline="")
        tx = 2 + self.pos * self.seg_w + self.seg_w / 2
        self.create_polygon(
            rounded_rect_points(tx, h / 2, self.seg_w - 1, h - 4, 7 * s),
            fill="#636366", outline="")
        for i, label in enumerate(self.options):
            self.create_text(2 + i * self.seg_w + self.seg_w / 2, h / 2,
                             text=label, fill=TEXT,
                             font=(FONT, -int(13 * s),
                                   BOLD if i == self.index else "normal"))


class TrafficLights(tk.Canvas):
    """Close / minimise / zoom dots with glyphs on hover."""

    COLORS = ("#FF5F57", "#FEBC2E", "#28C840")

    def __init__(self, master, bg, commands, scale=1.0):
        self.d = 12 * scale
        self.gap = 8 * scale
        self.hh = int(TITLEBAR_H * scale) - 2
        super().__init__(master, width=int(3 * self.d + 2 * self.gap + 2),
                         height=self.hh, bg=bg, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.commands = commands
        self.hover = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self.on_click)
        self.draw()

    def _set_hover(self, state):
        self.hover = state
        self.draw()

    def on_click(self, event):
        step = self.d + self.gap
        i = int((event.x - 1) // step)
        if 0 <= i < 3 and (event.x - 1) - i * step <= self.d:
            self.commands[i]()

    def draw(self):
        self.delete("all")
        r, cy = self.d / 2, self.hh / 2
        k = r * 0.42
        for i, col in enumerate(self.COLORS):
            cx = 1 + r + i * (self.d + self.gap)
            self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, width=0)
            if not self.hover:
                continue
            g = "#3B1A18"
            if i == 0:
                self.create_line(cx - k, cy - k, cx + k, cy + k, fill=g, width=1.5)
                self.create_line(cx - k, cy + k, cx + k, cy - k, fill=g, width=1.5)
            elif i == 1:
                self.create_line(cx - k * 1.1, cy, cx + k * 1.1, cy, fill=g, width=1.5)
            else:
                self.create_line(cx - k, cy, cx + k, cy, fill=g, width=1.5)
                self.create_line(cx, cy - k, cx, cy + k, fill=g, width=1.5)


NAV_ITEMS = (
    ("Overview", "overview", IOS_BLUE),
    ("Processor", "processor", IOS_PINK),
    ("Memory", "memory", IOS_GREEN),
    ("Graphics", "graphics", IOS_PURPLE),
    ("Network", "network", IOS_ORANGE),
    ("Settings", "settings", IOS_GRAY),
)


class NavSidebar(tk.Canvas):
    """iPadOS-style sidebar with a selection pill that glides between items."""

    ITEM_H, GAP, TOP, PAD = 46, 4, 120, 14

    def __init__(self, master, scale, accent, command):
        self.sc = scale
        super().__init__(master, width=int(SIDEBAR_W * scale), bg=BG,
                         highlightthickness=0, bd=0)
        self.accent = accent
        self.command = command
        self.index = 0
        self.hover = -1
        self.pill_y = self._y(0)
        self.anim = 0
        self.bind("<Configure>", lambda e: self.render())
        self.bind("<Motion>", self.on_motion)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)

    def _y(self, i):
        return (self.TOP + i * (self.ITEM_H + self.GAP)) * self.sc

    def _hit(self, y):
        step = (self.ITEM_H + self.GAP) * self.sc
        rel = y - self.TOP * self.sc
        i = int(rel // step)
        if rel < 0 or not 0 <= i < len(NAV_ITEMS):
            return -1
        return i if rel - i * step <= self.ITEM_H * self.sc else -1

    def on_motion(self, event):
        i = self._hit(event.y)
        self.configure(cursor="hand2" if i >= 0 else "")
        if i != self.hover:
            self.hover = i
            self.render()

    def on_leave(self, _event):
        if self.hover != -1:
            self.hover = -1
            self.render()

    def on_click(self, event):
        i = self._hit(event.y)
        if i >= 0:
            self.command(NAV_ITEMS[i][0])

    def set_accent(self, color):
        self.accent = color
        self.render()

    def select(self, name, animate=True):
        self.index = [n for n, _, _ in NAV_ITEMS].index(name)
        target = self._y(self.index)
        self.anim += 1
        if not animate or abs(target - self.pill_y) < 1:
            self.pill_y = target
            self.render()
            return
        self._glide(time.perf_counter(), self.pill_y, target, self.anim)

    def _glide(self, start, frm, to, token):
        if token != self.anim:
            return
        t = clamp((time.perf_counter() - start) / 0.34)
        self.pill_y = lerp(frm, to, ease_out_back(t, 0.9))
        self.render()
        if t < 1:
            self.after(8, lambda: self._glide(start, frm, to, token))

    def render(self):
        c, s = self, self.sc
        c.delete("all")
        W = max(self.winfo_width(), int(SIDEBAR_W * s))
        H = self.winfo_height()
        pad = self.PAD * s

        # header
        draw_app_icon(c, 46 * s, 54 * s, 40 * s, self.accent,
                      fg=contrast_text(self.accent))
        c.create_text(76 * s, 46 * s, text="Volt", anchor="w", fill=TEXT,
                      font=(FONT, -int(22 * s), BOLD))
        c.create_text(76 * s, 66 * s, text="System Monitor", anchor="w",
                      fill=MUTED, font=(FONT, -int(12 * s)))

        ih = self.ITEM_H * s
        if 0 <= self.hover != self.index:
            c.create_polygon(
                rounded_rect_points(W / 2, self._y(self.hover) + ih / 2,
                                    W - 2 * pad, ih, 12 * s),
                fill="#121214", outline="")
        c.create_polygon(
            rounded_rect_points(W / 2, self.pill_y + ih / 2, W - 2 * pad, ih,
                                12 * s),
            fill=lerp_color(BG, self.accent, 0.30), outline="")

        for i, (name, kind, color) in enumerate(NAV_ITEMS):
            cy = self._y(i) + ih / 2
            active = i == self.index
            draw_nav_icon(c, kind, pad + 29 * s, cy, 30 * s, color)
            c.create_text(pad + 58 * s, cy, text=name, anchor="w",
                          fill=TEXT if active else "#AEAEB2",
                          font=(FONT, -int(15 * s),
                                BOLD if active else "normal"))

        c.create_text(26 * s, H - 24 * s, text="Volt 1.0.0", anchor="w",
                      fill=DIM, font=(FONT, -int(11 * s)))


# ---------- pages ----------

class Page(ctk.CTkFrame):
    def __init__(self, app, parent):
        super().__init__(parent, fg_color="transparent")
        self.app = app

    def on_show(self):
        self.poll()

    def poll(self):
        pass

    def tick(self, dt):
        pass


class OverviewPage(Page):

    def __init__(self, app, parent):
        super().__init__(app, parent)
        app.page_title(self, "System Overview")

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x")
        cards.grid_columnconfigure((0, 1, 2), weight=1, uniform="stat")

        self.gauges = []
        for col, (title, caption, color) in enumerate((
                ("CPU", "Processor load", IOS_PINK),
                ("MEMORY", "RAM in use", IOS_GREEN),
                ("DISK", "Space used", None))):
            card, gauge = app.gauge_card(cards, title, caption, color)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else 7, 0 if col == 2 else 7))
            self.gauges.append(gauge)

        middle = ctk.CTkFrame(self, fg_color="transparent")
        middle.pack(fill="both", expand=True, pady=(14, 0))
        middle.grid_columnconfigure(0, weight=3, uniform="low")
        middle.grid_columnconfigure(1, weight=2, uniform="low")
        middle.grid_rowconfigure(0, weight=1)

        network = app.make_card(middle)
        network.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        app.card_title(network, "NETWORK")

        stats = ctk.CTkFrame(network, fg_color="transparent")
        stats.pack(fill="x", padx=22, pady=(10, 0))
        stats.grid_columnconfigure((0, 1), weight=1, uniform="net")
        self.down_label = app.net_stat(stats, "DOWNLOAD", None, 0)
        self.up_label = app.net_stat(stats, "UPLOAD", IOS_ORANGE, 1)

        self.chart = app.make_chart(network, height=100,
                                    colors=(None, IOS_ORANGE))
        self.chart.pack(fill="both", expand=True, padx=22, pady=(12, 18))
        app.net_charts.append(self.chart)

        system, _ = app.info_card(middle, "SYSTEM", system_info())
        system.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

    def tick(self, dt):
        d = self.app.disp
        self.gauges[0].set_value(d["cpu"])
        self.gauges[1].set_value(d["mem"])
        self.gauges[2].set_value(d["disk"])
        self.down_label.set_text(format_speed(d["down"]))
        self.up_label.set_text(format_speed(d["up"]))
        self.chart.redraw(dt)


class ProcessorPage(Page):

    def __init__(self, app, parent):
        super().__init__(app, parent)
        app.page_title(self, "Processor")

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x")
        row1.grid_columnconfigure(0, weight=1, uniform="p")
        row1.grid_columnconfigure(1, weight=2, uniform="p")

        card, self.gauge = app.gauge_card(row1, "CPU", "Total load", IOS_PINK)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        hist = app.make_card(row1)
        hist.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        app.card_title(hist, "LOAD HISTORY", IOS_PINK)
        self.chart = app.make_chart(hist, height=120, fixed_max=100,
                                    colors=(IOS_PINK,),
                                    fmt=lambda v: f"{v:.0f}%")
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.hist_charts["cpu"] = self.chart

        details = app.make_card(self)
        details.pack(fill="both", expand=True, pady=(14, 0))
        app.card_title(details, "PROCESSOR", MUTED)

        self.model = ctk.CTkLabel(
            details, text="Detecting processor...", text_color=TEXT,
            font=(FONT, 20, BOLD))
        self.model.pack(anchor="w", padx=22, pady=(4, 8))

        cols = ctk.CTkFrame(details, fg_color="transparent")
        cols.pack(fill="x", padx=22, pady=(0, 14))
        cols.grid_columnconfigure((0, 1), weight=1, uniform="pc")
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(18, 0))

        self.vals = {}
        self.vals.update(app.info_rows(left, [
            ("Manufacturer", "-"), ("Socket", "-"),
            ("Cores / threads", "-"),
            ("Architecture", platform.machine() or "-"),
        ], row_pad=7, pad_x=0))
        self.vals.update(app.info_rows(right, [
            ("Current speed", "-"), ("Rated speed", "-"),
            ("Cache (L2 / L3)", "-"), ("Processes", "-"),
        ], row_pad=7, pad_x=0))

    def poll(self):
        data = self.app.cpu_info.data
        self.model.configure(text=data.get("name") or "Detecting processor...")

        cores = psutil.cpu_count(logical=False) or psutil.cpu_count()
        threads = psutil.cpu_count()
        self.vals["Manufacturer"].configure(
            text=pretty_vendor(data.get("vendor", "")) if data else "-")
        self.vals["Socket"].configure(text=data.get("socket") or "-")
        self.vals["Cores / threads"].configure(text=f"{cores} / {threads}")

        freq = psutil.cpu_freq()
        if freq:
            self.vals["Current speed"].configure(
                text=f"{freq.current / 1000:.2f} GHz")
        rated = data.get("rated_mhz") or (freq.max if freq else None)
        if rated:
            self.vals["Rated speed"].configure(text=f"{num(rated) / 1000:.2f} GHz")
        if data:
            self.vals["Cache (L2 / L3)"].configure(
                text=f"{format_cache(data.get('l2_kb'))} / "
                     f"{format_cache(data.get('l3_kb'))}")
        self.vals["Processes"].configure(text=str(len(psutil.pids())))

    def tick(self, dt):
        self.gauge.set_value(self.app.disp["cpu"])
        self.chart.redraw(dt)


class MemoryPage(Page):

    def __init__(self, app, parent):
        super().__init__(app, parent)
        app.page_title(self, "Memory")

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x")
        row1.grid_columnconfigure(0, weight=1, uniform="m")
        row1.grid_columnconfigure(1, weight=2, uniform="m")

        card, self.gauge = app.gauge_card(row1, "MEMORY", "RAM in use", IOS_GREEN)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        hist = app.make_card(row1)
        hist.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        app.card_title(hist, "USAGE HISTORY", IOS_GREEN)
        self.chart = app.make_chart(hist, height=120, fixed_max=100,
                                    colors=(IOS_GREEN,),
                                    fmt=lambda v: f"{v:.0f}%")
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.hist_charts["mem"] = self.chart

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(14, 0))
        row2.grid_columnconfigure((0, 1), weight=1, uniform="m2")
        row2.grid_rowconfigure(0, weight=1)

        ram, self.ram_vals = app.info_card(row2, "PHYSICAL MEMORY", [
            ("Total", "-"), ("Used", "-"), ("Available", "-")])
        ram.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        swap, self.swap_vals = app.info_card(row2, "SWAP / PAGE FILE", [
            ("Total", "-"), ("Used", "-"), ("Usage", "-")])
        swap.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

    def poll(self):
        vm = psutil.virtual_memory()
        self.ram_vals["Total"].configure(text=format_bytes(vm.total))
        self.ram_vals["Used"].configure(text=format_bytes(vm.used))
        self.ram_vals["Available"].configure(text=format_bytes(vm.available))
        sw = psutil.swap_memory()
        self.swap_vals["Total"].configure(text=format_bytes(sw.total))
        self.swap_vals["Used"].configure(text=format_bytes(sw.used))
        self.swap_vals["Usage"].configure(text=f"{sw.percent:.0f}%")

    def tick(self, dt):
        self.gauge.set_value(self.app.disp["mem"])
        self.chart.redraw(dt)


class GraphicsPage(Page):

    def __init__(self, app, parent):
        super().__init__(app, parent)
        s = app.ui_scale
        app.page_title(self, "Graphics")

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x")
        row1.grid_columnconfigure(0, weight=1, uniform="g")
        row1.grid_columnconfigure(1, weight=2, uniform="g")

        card, self.gauge = app.gauge_card(row1, "GPU", "Graphics load", IOS_PURPLE)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))

        hist = app.make_card(row1)
        hist.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        app.card_title(hist, "LOAD HISTORY", IOS_PURPLE)
        self.chart = app.make_chart(hist, height=120, fixed_max=100,
                                    colors=(IOS_PURPLE,),
                                    fmt=lambda v: f"{v:.0f}%")
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.hist_charts["gpu"] = self.chart

        details, self.vals = app.info_card(self, "DETAILS", [
            ("Graphics card", "Detecting..."), ("Video memory", "-"),
            ("Temperature", "-"), ("Telemetry", "-")])
        details.pack(fill="x", pady=(14, 0))

        self.notice = ctk.CTkLabel(
            self, text="", text_color=DIM, font=(FONT, 12),
            wraplength=int(700 * s), justify="left")
        self.notice.pack(anchor="w", pady=(10, 0), padx=4)

    def poll(self):
        g = self.app.gpu
        name = g.name or "Detecting..."
        self.vals["Graphics card"].configure(
            text=name if len(name) <= 34 else name[:33] + "…")
        if g.available:
            self.vals["Video memory"].configure(
                text=f"{g.mem_used / 1024:.1f} / {g.mem_total / 1024:.1f} GB")
            self.vals["Temperature"].configure(text=f"{g.temp:.0f} °C")
            self.vals["Telemetry"].configure(text="Live")
            self.notice.configure(text="")
        else:
            self.vals["Video memory"].configure(text="-")
            self.vals["Temperature"].configure(text="-")
            self.vals["Telemetry"].configure(text="Unavailable")
            self.notice.configure(
                text="Live GPU stats need an NVIDIA card with nvidia-smi "
                     "installed (it comes with the NVIDIA driver). "
                     "Other GPUs only show their name.")

    def tick(self, dt):
        self.gauge.set_value(self.app.disp["gpu"])
        self.chart.redraw(dt)


class NetworkPage(Page):

    def __init__(self, app, parent):
        super().__init__(app, parent)
        app.page_title(self, "Network")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        top.grid_columnconfigure((0, 1), weight=1, uniform="n")

        self.big = {}
        self.sub = {}
        for col, (key, title, color) in enumerate((
                ("down", "DOWNLOAD", None), ("up", "UPLOAD", IOS_ORANGE))):
            card = app.make_card(top)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else 7, 0 if col == 1 else 7))

            legend = ctk.CTkFrame(card, fg_color="transparent")
            legend.pack(anchor="w", padx=22, pady=(18, 0))
            app.legend_dot(legend, color).pack(side="left", padx=(0, 7))
            ctk.CTkLabel(legend, text=title, text_color=MUTED,
                         font=(FONT, 13, BOLD)).pack(side="left")

            label = ValueLabel(card, "0 B/s", 34)
            label.pack(anchor="w", padx=22, pady=(4, 0))
            self.big[key] = label

            sub = ctk.CTkLabel(card, text="", text_color=MUTED, font=(FONT, 12))
            sub.pack(anchor="w", padx=22, pady=(2, 18))
            self.sub[key] = sub

        low = ctk.CTkFrame(self, fg_color="transparent")
        low.pack(fill="both", expand=True, pady=(14, 0))
        low.grid_columnconfigure(0, weight=3, uniform="nl")
        low.grid_columnconfigure(1, weight=2, uniform="nl")
        low.grid_rowconfigure(0, weight=1)

        chart_card = app.make_card(low)
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        app.card_title(chart_card, "TRAFFIC", MUTED)
        self.chart = app.make_chart(chart_card, height=120,
                                    colors=(None, IOS_ORANGE))
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.net_charts.append(self.chart)

        iface_card = app.make_card(low)
        iface_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        app.card_title(iface_card, "ACTIVE ADAPTERS", MUTED)

        self.iface_rows = []
        for _ in range(5):
            row = ctk.CTkFrame(iface_card, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=7)
            name = ctk.CTkLabel(row, text="", text_color=TEXT, font=(FONT, 14))
            name.pack(side="left")
            ip = ctk.CTkLabel(row, text="", text_color=MUTED, font=(FONT, 14))
            ip.pack(side="right")
            self.iface_rows.append((name, ip))

        self.poll_count = 0

    def poll(self):
        app = self.app
        self.sub["down"].configure(
            text=f"Total received  {format_bytes(net.get_bytes_receieved())}"
                 f"     Peak  {format_speed(app.peak['down'])}")
        self.sub["up"].configure(
            text=f"Total sent  {format_bytes(net.get_bytes_sent())}"
                 f"     Peak  {format_speed(app.peak['up'])}")
        if self.poll_count % 5 == 0:
            self.refresh_interfaces()
        self.poll_count += 1

    def refresh_interfaces(self):
        found = []
        try:
            stats = psutil.net_if_stats()
            for name, addrs in psutil.net_if_addrs().items():
                if name in stats and not stats[name].isup:
                    continue
                for a in addrs:
                    if a.family == socket.AF_INET and not a.address.startswith("127."):
                        found.append((name, a.address))
                        break
        except Exception:
            pass
        for i, (name_lbl, ip_lbl) in enumerate(self.iface_rows):
            if i < len(found):
                name = found[i][0]
                name_lbl.configure(text=name if len(name) <= 20 else name[:19] + "…")
                ip_lbl.configure(text=found[i][1])
            else:
                name_lbl.configure(text="")
                ip_lbl.configure(text="")

    def tick(self, dt):
        d = self.app.disp
        self.big["down"].set_text(format_speed(d["down"]))
        self.big["up"].set_text(format_speed(d["up"]))
        self.chart.redraw(dt)


class SettingsPage(Page):

    PRESETS = [IOS_BLUE, IOS_TEAL, IOS_GREEN, IOS_YELLOW,
               IOS_ORANGE, IOS_PINK, IOS_PURPLE, "#FFFFFF"]

    def __init__(self, app, parent):
        super().__init__(app, parent)
        s = app.ui_scale
        app.page_title(self, "Settings")
        self.color = app.accent.upper()

        # ----- accent colour -----
        card = app.make_card(self)
        card.pack(fill="x")
        app.card_title(card, "ACCENT COLOR")
        ctk.CTkLabel(
            card,
            text="Tints charts, rings and the sidebar. Changes preview "
                 "live; tap Save to keep them.",
            text_color=MUTED, font=(FONT, 12)
        ).pack(anchor="w", padx=22, pady=(2, 0))

        swatches = ctk.CTkFrame(card, fg_color="transparent")
        swatches.pack(fill="x", padx=22, pady=(14, 0))
        self.swatches = []
        for color in self.PRESETS:
            btn = ctk.CTkButton(
                swatches, text="", width=36, height=36, corner_radius=18,
                fg_color=color, hover_color=color, border_width=0,
                font=(FONT, 16, BOLD),
                command=lambda c=color: self.set_color(c))
            btn.pack(side="left", padx=(0, 12))
            self.swatches.append((btn, color))

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=22, pady=(16, 20))
        ctk.CTkLabel(bottom, text="HEX", text_color=MUTED,
                     font=(FONT, 12, BOLD)).pack(side="left", padx=(0, 10))
        self.entry = ctk.CTkEntry(
            bottom, width=110, height=38, corner_radius=10,
            fg_color=CARD_HI, border_width=0, text_color=TEXT,
            font=(FONT, 14))
        self.entry.pack(side="left")
        self.entry.insert(0, self.color)
        self.entry.bind("<Return>", self.on_entry)
        self.entry.bind("<FocusOut>", self.on_entry)

        self.save_btn = ctk.CTkButton(
            bottom, text="Save", width=96, height=38, corner_radius=12,
            fg_color=app.accent, hover_color=lerp_color(app.accent, "#000000", 0.2),
            text_color=contrast_text(app.accent), font=(FONT, 14, BOLD),
            command=self.save)
        self.save_btn.pack(side="right")
        app.accent_fills.append(self.save_btn)
        ctk.CTkButton(
            bottom, text="Reset", width=84, height=38, corner_radius=12,
            fg_color=CARD_HI, hover_color="#3A3A3C", text_color=TEXT,
            font=(FONT, 14), command=self.reset
        ).pack(side="right", padx=(0, 10))
        self.status = ctk.CTkLabel(bottom, text="Saved", text_color=MUTED,
                                   font=(FONT, 12))
        self.status.pack(side="right", padx=16)

        # ----- general -----
        general = app.make_card(self)
        general.pack(fill="x", pady=(14, 0))
        app.card_title(general, "GENERAL", MUTED)

        right = app.list_row(general, "Reduce Motion",
                             "Turns off page, sidebar and launch animations")
        ToggleSwitch(right, CARD, s, settings["reduce_motion"],
                     app.set_reduce_motion).pack()

        right = app.list_row(general, "Update Rate",
                             "How often readings are taken", separator=False)
        SegmentedControl(right, CARD, s, ["1 s", "2 s", "5 s"],
                         INTERVALS.index(UPDATE_MS), self.on_rate,
                         seg_w=56).pack()
        ctk.CTkFrame(general, height=8, fg_color="transparent").pack()

        self.refresh_swatches()

    # ----- colour state -----

    def refresh_swatches(self):
        for btn, color in self.swatches:
            selected = color.upper() == self.color.upper()
            btn.configure(text="✓" if selected else "",
                          text_color=contrast_text(color))

    def set_color(self, color):
        self.color = color.upper()
        self.app.set_accent(self.color)
        self.entry.delete(0, "end")
        self.entry.insert(0, self.color)
        self.save_btn.configure(text_color=contrast_text(self.color))
        self.status.configure(
            text="Saved" if self.color == self.app.saved_accent else "Unsaved changes")
        self.refresh_swatches()

    def on_entry(self, event=None):
        text = self.entry.get().strip()
        if not text.startswith("#"):
            text = "#" + text
        if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            self.set_color(text)
        else:
            self.status.configure(text="Invalid hex")

    def on_rate(self, index):
        self.app.set_update_rate(INTERVALS[index])

    def save(self):
        ok = self.app.save_accent()
        self.status.configure(text="Saved" if ok else "Couldn't save file")

    def reset(self):
        self.set_color(DEFAULT_ACCENT)


class RevoltApp(ctk.CTk):

    def check_font(self):
        """Pick SF Pro if installed, otherwise the nearest system font."""
        global FONT
        available = {f.lower(): f for f in tkfont.families(self)}
        for name in FONT_CANDIDATES:
            if name.lower() in available:
                FONT = available[name.lower()]
                return
        FONT = "Helvetica"

    def __init__(self):
        super().__init__()
        self.check_font()

        self.title("VOLT | System Monitor")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(950, 620)

        try:
            self.ui_scale = self._get_window_scaling()
        except Exception:
            self.ui_scale = 1.0

        self.configure(fg_color=BG)
        self.overrideredirect(True)
        self.center_window(WINDOW_W, WINDOW_H)

        self.is_max = False
        self.restore_geo = None
        self.minimized = False
        self._drag_x = 0
        self._drag_y = 0

        self.accent = settings["accent"]
        self.saved_accent = settings["accent"]
        self.reduce_motion = settings["reduce_motion"]
        self._accent_job = None

        self.accent_widgets = []   # text recoloured with the accent
        self.accent_dots = []      # (frame, color-or-None) legend dots
        self.accent_fills = []     # buttons filled with the accent
        self.all_gauges = []
        self.all_charts = []

        keys = ("cpu", "mem", "disk", "gpu", "down", "up")
        self.target = {k: 0.0 for k in keys}
        self.disp = {k: 0.0 for k in keys}
        self.peak = {"down": 0.0, "up": 0.0}
        self.net_charts = []
        self.hist_charts = {}
        self.pages = {}
        self.current = "Overview"
        self._slide_token = 0

        self.gpu = GpuMonitor()
        self.gpu.start()
        self.cpu_info = CpuInfo()
        self.cpu_info.start()

        self.prev_sent = 0
        self.prev_recv = 0
        self.prev_time = time.time()
        self._last_frame = time.perf_counter()

        self.container = ctk.CTkFrame(
            self, fg_color=BG, corner_radius=0,
            border_width=1, border_color=BORDER)
        self.container.pack(fill="both", expand=True)

        self.create_titlebar()
        self.body = ctk.CTkFrame(self.container, fg_color="transparent",
                                 corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        self.nav = NavSidebar(self.body, self.ui_scale, self.accent,
                              lambda n: self.show_page(n))
        self.nav.pack(side="left", fill="y")
        ctk.CTkFrame(self.body, width=1, corner_radius=0,
                     fg_color=CARD).pack(side="left", fill="y")
        self.create_pages()

        self.bind("<Map>", self.on_map)

        self.start_splash()
        self.after(300, self.init_window)

    # ---------------------------------------------------------------
    # Accent colour & settings
    # ---------------------------------------------------------------

    def set_accent(self, color):
        """Calls are coalesced so dragging never queues more work than the UI
        can draw."""
        self.accent = color
        if self._accent_job is None:
            self._accent_job = self.after(25, self._apply_accent)

    def _apply_accent(self):
        self._accent_job = None
        color = self.accent
        for widget in self.accent_widgets:
            widget.configure(text_color=color)
        for gauge in self.all_gauges:
            gauge.set_accent(color)
        for chart in self.all_charts:
            chart.accent = color
        for dot, fixed in self.accent_dots:
            if fixed is None:
                dot.configure(fg_color=color)
        for btn in self.accent_fills:
            btn.configure(fg_color=color,
                          hover_color=lerp_color(color, "#000000", 0.2))
        self.nav.set_accent(color)

    def save_accent(self):
        self.saved_accent = self.accent
        settings["accent"] = self.accent
        return save_settings(settings)

    def set_reduce_motion(self, on):
        self.reduce_motion = bool(on)
        settings["reduce_motion"] = self.reduce_motion
        save_settings(settings)

    def set_update_rate(self, ms):
        global UPDATE_MS
        UPDATE_MS = ms
        settings["interval"] = ms
        save_settings(settings)

    # ---------------------------------------------------------------
    # Window helpers (borderless window management)
    # ---------------------------------------------------------------

    def center_window(self, w, h):
        x = (self.winfo_screenwidth() - int(w * self.ui_scale)) // 2
        y = (self.winfo_screenheight() - int(h * self.ui_scale)) // 2
        tk.Tk.geometry(self, f"+{x}+{y}")

    def init_window(self):
        self.overrideredirect(True)
        self.set_appwindow()

    def set_appwindow(self):
        """Borderless windows get no taskbar icon by default - force one,
        and ask Windows 11 for rounded window corners."""
        try:
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            try:
                pref = ctypes.c_int(2)  # DWMWCP_ROUND
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
            except Exception:
                pass
            self.withdraw()
            self.after(10, self.deiconify)
        except Exception:
            pass

    def on_map(self, event):
        if event.widget is self and self.minimized:
            self.minimized = False
            self.after(10, self.restore_borderless)

    def restore_borderless(self):
        self.overrideredirect(True)
        self.set_appwindow()

    def minimize(self):
        self.update_idletasks()
        self.minimized = True
        self.overrideredirect(False)
        self.iconify()

    def work_area(self):
        try:
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            rect = RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0)
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def toggle_maximize(self):
        if self.is_max:
            tk.Tk.geometry(self, self.restore_geo)
            self.is_max = False
        else:
            self.restore_geo = (
                f"{self.winfo_width()}x{self.winfo_height()}"
                f"+{self.winfo_x()}+{self.winfo_y()}")
            l, t, r, b = self.work_area()
            tk.Tk.geometry(self, f"{r - l}x{b - t}+{l}+{t}")
            self.is_max = True

    def close(self):
        try:
            alpha = float(self.attributes("-alpha"))
        except Exception:
            alpha = 1.0
        self.fade_out(alpha)

    def fade_out(self, alpha):
        if alpha <= 0.05:
            self.destroy()
            return
        self.attributes("-alpha", alpha)
        self.after(12, lambda: self.fade_out(alpha - 0.1))

    def fade_in(self, alpha=0.0):
        alpha = min(1.0, alpha + 0.09)
        try:
            self.attributes("-alpha", alpha)
            if alpha < 1.0:
                self.after(12, lambda: self.fade_in(alpha))
        except tk.TclError:
            pass

    def start_move(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def do_move(self, event):
        if self.is_max:
            return
        tk.Tk.geometry(self, f"+{event.x_root - self._drag_x}"
                             f"+{event.y_root - self._drag_y}")

    # ---------------------------------------------------------------
    # Launch animation (iOS app-launch style)
    # ---------------------------------------------------------------

    def start_splash(self):
        self.splash = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.splash.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(self.splash)
        if self.reduce_motion:
            self.after(50, self.finish_splash)
        else:
            self.after(450, self.splash_begin)

    def splash_begin(self):
        self.splash_start = time.perf_counter()
        self.splash_tick()

    def splash_tick(self):
        try:
            t = time.perf_counter() - self.splash_start
            if t >= SPLASH_TOTAL:
                self.finish_splash()
                return
            self.draw_splash(t)
            self.after(FRAME_MS, self.splash_tick)
        except tk.TclError:
            pass

    def draw_splash(self, t):
        c = self.splash
        c.delete("all")
        s = self.ui_scale
        W, H = c.winfo_width(), c.winfo_height()
        cx, cy = W / 2, H / 2 - 30 * s
        size = 116 * s

        out = ease_in_cubic(clamp((t - SPLASH_OUT_AT) / SPLASH_OUT_S))
        fade = ease_out_cubic(clamp(t / 0.4)) * (1 - out)
        scale = (lerp(0.5, 1.0, ease_out_back(clamp(t / SPLASH_IN)))
                 * lerp(1.0, 1.6, out))

        draw_app_icon(c, cx, cy, size * scale,
                      lerp_color(BG, self.accent, fade),
                      fg=lerp_color(BG, contrast_text(self.accent), fade))

        text_a = clamp((t - 0.45) / 0.35) * (1 - out)
        ty = cy + size * 0.5 + 46 * s
        c.create_text(cx, ty, text="Volt", fill=lerp_color(BG, TEXT, text_a),
                      font=(FONT, -int(30 * s), BOLD))
        c.create_text(cx, ty + 30 * s, text="System Monitor",
                      fill=lerp_color(BG, MUTED, text_a),
                      font=(FONT, -int(14 * s)))

        # iOS-style activity indicator
        spin_a = clamp((t - 0.8) / 0.3) * (1 - out)
        if spin_a > 0:
            sy = ty + 84 * s
            for i in range(12):
                a = i * math.pi / 6
                lead = (t * 1.3 - i / 12) % 1.0
                level = (0.18 + 0.82 * (1 - lead)) * spin_a
                r1, r2 = 8 * s, 15 * s
                c.create_line(cx + math.sin(a) * r1, sy - math.cos(a) * r1,
                              cx + math.sin(a) * r2, sy - math.cos(a) * r2,
                              fill=lerp_color(BG, MUTED, level),
                              width=2.5 * s, capstyle="round")

    def finish_splash(self):
        self.attributes("-alpha", 0.0)
        self.splash.destroy()
        self.start_monitoring()
        if self.reduce_motion:
            self.attributes("-alpha", 1.0)
        else:
            self.fade_in(0.0)

    # ---------------------------------------------------------------
    # Live data + smooth animation
    # ---------------------------------------------------------------

    def start_monitoring(self):
        self.prev_sent = net.get_bytes_sent()
        self.prev_recv = net.get_bytes_receieved()
        self.prev_time = time.time()
        self._last_frame = time.perf_counter()
        self.poll_stats()
        self.animate_loop()

    def poll_stats(self):
        try:
            self.after(UPDATE_MS, self.poll_stats)

            now = time.time()
            sent = net.get_bytes_sent()
            recv = net.get_bytes_receieved()
            elapsed = now - self.prev_time

            if elapsed > 0.2:
                up = max(0.0, (sent - self.prev_sent) / elapsed)
                down = max(0.0, (recv - self.prev_recv) / elapsed)
                self.target["up"] = up
                self.target["down"] = down
                self.peak["up"] = max(self.peak["up"], up)
                self.peak["down"] = max(self.peak["down"], down)
                for chart in self.net_charts:
                    chart.push(down, up)
                self.prev_sent, self.prev_recv, self.prev_time = sent, recv, now

            cpu = num(sys.get_cpu_usage())
            mem = num(sys.get_memory_usage())
            disk = num(sys.get_disk_usage())
            gpu = self.gpu.util if self.gpu.available else 0.0
            self.target.update(cpu=cpu, mem=mem, disk=disk, gpu=gpu)

            for key, value in (("cpu", cpu), ("mem", mem), ("gpu", gpu)):
                chart = self.hist_charts.get(key)
                if chart:
                    chart.push(value)

            self.pages[self.current].poll()
        except tk.TclError:
            pass

    def animate_loop(self):
        try:
            self.after(FRAME_DELAY, self.animate_loop)
            now = time.perf_counter()
            dt = min(now - self._last_frame, 0.1)
            self._last_frame = now

            a = 1 - math.exp(-SMOOTHING * dt)
            for k in self.disp:
                self.disp[k] += (self.target[k] - self.disp[k]) * a

            self.pages[self.current].tick(dt)
        except tk.TclError:
            pass

    # ---------------------------------------------------------------
    # Page switching (glide-in + sliding sidebar pill)
    # ---------------------------------------------------------------

    def show_page(self, name, animate=True):
        animate = animate and not self.reduce_motion
        if animate and name == self.current and self.pages[name].winfo_ismapped():
            return

        for page in self.pages.values():
            page.place_forget()

        self.current = name
        page = self.pages[name]
        self._slide_token += 1
        offset = PAGE_SLIDE_PX * self.ui_scale if animate else 0
        page.place(x=0, y=int(offset), relwidth=1, relheight=1)

        self.nav.select(name, animate=animate)
        page.on_show()
        self.update_idletasks()
        self.refresh_stale()

        if animate:
            self._slide(page, time.perf_counter(), self._slide_token)

    def _slide(self, page, start, token):
        if token != self._slide_token:
            return
        t = clamp((time.perf_counter() - start) / PAGE_SLIDE_S)
        y = int((1 - ease_out_cubic(t)) * PAGE_SLIDE_PX * self.ui_scale)
        try:
            page.place(x=0, y=y, relwidth=1, relheight=1)
            if t < 1:
                self.after(8, lambda: self._slide(page, start, token))
        except tk.TclError:
            pass

    def refresh_stale(self):
        for gauge in self.all_gauges:
            if gauge.stale and gauge.winfo_viewable():
                gauge.refresh()

    # ---------------------------------------------------------------
    # UI building blocks
    # ---------------------------------------------------------------

    def create_titlebar(self):
        bar = ctk.CTkFrame(self.container, height=TITLEBAR_H,
                           corner_radius=0, fg_color=BG)
        bar.pack(side="top", fill="x", padx=1, pady=(1, 0))
        bar.pack_propagate(False)

        self.lights = TrafficLights(
            bar, BG, (self.close, self.minimize, self.toggle_maximize),
            self.ui_scale)
        self.lights.pack(side="left", padx=(18, 0))

        title = ctk.CTkLabel(bar, text="Volt", font=(FONT, 13, BOLD),
                             text_color=MUTED)
        title.place(relx=0.5, rely=0.5, anchor="center")

        for widget in (bar, title):
            widget.bind("<ButtonPress-1>", self.start_move)
            widget.bind("<B1-Motion>", self.do_move)
            widget.bind("<Double-Button-1>", lambda e: self.toggle_maximize())

    def create_pages(self):
        self.main = ctk.CTkFrame(self.body, fg_color="transparent")
        self.main.pack(side="left", fill="both", expand=True,
                       padx=30, pady=(10, 26))

        self.pages = {
            "Overview": OverviewPage(self, self.main),
            "Processor": ProcessorPage(self, self.main),
            "Memory": MemoryPage(self, self.main),
            "Graphics": GraphicsPage(self, self.main),
            "Network": NetworkPage(self, self.main),
            "Settings": SettingsPage(self, self.main),
        }
        self.show_page("Overview", animate=False)

    def make_card(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=20,
                            border_width=0)

    def card_title(self, card, text, color=None, pady=(18, 0)):
        """Small bold widget header. color=None follows the accent."""
        label = ctk.CTkLabel(card, text=text, text_color=color or self.accent,
                             font=(FONT, 13, BOLD))
        label.pack(anchor="w", padx=22, pady=pady)
        if color is None:
            self.accent_widgets.append(label)
        return label

    def page_title(self, parent, text):
        label = ctk.CTkLabel(parent, text=text, text_color=TEXT,
                             font=(FONT, 34, BOLD))
        label.pack(anchor="w", pady=(0, 16))
        return label

    def make_chart(self, parent, **kw):
        height = kw.pop("height", 110)
        chart = SparkChart(parent, CARD, scale=self.ui_scale, height=height,
                           accent=self.accent, **kw)
        self.all_charts.append(chart)
        return chart

    def legend_dot(self, parent, color):
        dot = ctk.CTkFrame(parent, width=9, height=9, corner_radius=5,
                           fg_color=color or self.accent)
        self.accent_dots.append((dot, color))
        return dot

    def gauge_card(self, parent, title, caption, color=None, size=152):
        card = self.make_card(parent)
        self.card_title(card, title, color)
        gauge = RingGauge(card, size, CARD, scale=self.ui_scale,
                          accent=self.accent, color=color)
        gauge.pack(pady=(6, 0))
        self.all_gauges.append(gauge)
        ctk.CTkLabel(card, text=caption, text_color=MUTED,
                     font=(FONT, 12)).pack(pady=(2, 16))
        return card, gauge

    def info_rows(self, parent, rows, row_pad=10, pad_x=22):
        """iOS-style list rows: label left, grey value right, inset separators."""
        labels = {}
        for i, (key, value) in enumerate(rows):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=pad_x, pady=row_pad)
            ctk.CTkLabel(row, text=key, text_color=TEXT,
                         font=(FONT, 14)).pack(side="left")
            value_label = ctk.CTkLabel(row, text=value, text_color=MUTED,
                                       font=(FONT, 14))
            value_label.pack(side="right")
            labels[key] = value_label
            if i < len(rows) - 1:
                ctk.CTkFrame(parent, height=1, corner_radius=0,
                             fg_color=SEP).pack(fill="x", padx=pad_x)
        return labels

    def info_card(self, parent, title, rows):
        card = self.make_card(parent)
        self.card_title(card, title, MUTED, pady=(18, 4))
        labels = self.info_rows(card, rows)
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()
        return card, labels

    def list_row(self, parent, title, subtitle=None, separator=True):
        """Settings row with a slot on the right for a control."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(10, 10))
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=title, text_color=TEXT,
                     font=(FONT, 14)).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(left, text=subtitle, text_color=MUTED,
                         font=(FONT, 12)).pack(anchor="w")
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right")
        if separator:
            ctk.CTkFrame(parent, height=1, corner_radius=0,
                         fg_color=SEP).pack(fill="x", padx=22)
        return right

    def net_stat(self, parent, title, color, column):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=column, sticky="w")

        legend = ctk.CTkFrame(cell, fg_color="transparent")
        legend.pack(anchor="w")
        self.legend_dot(legend, color).pack(side="left", padx=(0, 7))
        ctk.CTkLabel(legend, text=title, text_color=MUTED,
                     font=(FONT, 11, BOLD)).pack(side="left")

        label = ValueLabel(cell, "0 B/s", 26)
        label.pack(anchor="w", pady=(2, 0))
        return label


if __name__ == "__main__":
    app = RevoltApp()
    app.mainloop()