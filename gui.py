import colorsys
import ctypes
import json
import math
import os
import platform
import re
import socket
import struct
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque

import customtkinter as ctk
import psutil

from system.monitor import SystemMonitor
from system.network import NetworkMonitor

sys = SystemMonitor()
net = NetworkMonitor()

# Appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------- custom font ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "sharkgotyourhand.ttf")


def read_font_family(path):
    """Read the family name stored inside a .ttf/.otf file, because Tk needs
    that name - which is often different from the file name."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if data[:4] == b"ttcf":          # font collections aren't handled
            return None
        tables = struct.unpack(">H", data[4:6])[0]
        name_off = None
        for i in range(tables):
            rec = 12 + i * 16
            if data[rec:rec + 4] == b"name":
                name_off = struct.unpack(">I", data[rec + 8:rec + 12])[0]
                break
        if name_off is None:
            return None
        _, count, str_off = struct.unpack(">HHH", data[name_off:name_off + 6])
        found = {}
        for i in range(count):
            rec = name_off + 6 + i * 12
            plat, _enc, _lang, name_id, length, off = struct.unpack(
                ">HHHHHH", data[rec:rec + 12])
            if name_id not in (1, 16):    # 1 = family, 16 = typographic family
                continue
            start = name_off + str_off + off
            raw = data[start:start + length]
            text = raw.decode("utf-16-be" if plat in (0, 3) else "latin-1",
                              errors="ignore").strip()
            if text and (name_id not in found or plat == 3):
                found[name_id] = text
        return found.get(1) or found.get(16)
    except Exception:
        return None


FONT_LOADED = ctk.FontManager.load_font(FONT_PATH)

# Global font configuration
FONT = read_font_family(FONT_PATH) or "sharkgotyourhand"
ICON_FONT = "Segoe MDL2 Assets"   # title-bar glyphs need an icon font
BOLD = "bold"                     # set to "normal" if the font looks smeared when bolded

# ---------- palette: black & accent ----------
accent_color = "#FFFFFF"  # splash rings / arcs (the splash *text* uses the saved accent)
TEXT = "#FFFFFF"
MUTED = "#8C8C8C"
DIM = "#4D4D4D"

BG = "#050505"            # app background
PANEL = "#0B0B0B"         # sidebar / title bar
CARD = "#0E0E0E"          # cards
BORDER = "#1C1C1C"
TRACK = "#1E1E1E"         # empty part of gauge rings
GRID = "#171717"          # chart grid lines
TRANSPARENT = "#010203"   # colour key: pixels of this colour are see-through on Windows

# Splash animation timing (frames are ~15 ms each)
GROW_FRAMES = 30      # circle blooms in
HOLD_FRAMES = 25      # circle pulses + spinner orbits
MORPH_FRAMES = 45     # circle flows into the full window box
CURTAIN_FRAMES = 20   # box slides away to reveal the dashboard
FRAME_MS = 10

# Live data
UPDATE_MS = 1000      # how often real readings are taken
SMOOTHING = 5.0       # higher = values catch up faster, lower = silkier
HISTORY = 45          # seconds of history on the charts
FRAME_DELAY = 16      # ~60 fps animation loop
PAGE_SLIDE_S = 0.22   # page transition length (seconds)
PAGE_SLIDE_PX = 18    # how far a page glides in

WINDOW_W, WINDOW_H = 1100, 700
TITLEBAR_H = 38

# ---------- saved settings ----------
DEFAULT_ACCENT = "#FFFFFF"
MIN_BRIGHTNESS = 0.35     # keeps the accent readable on black
SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "volt_settings.json")


def load_settings():
    data = {"accent": DEFAULT_ACCENT}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if re.fullmatch(r"#[0-9a-fA-F]{6}", str(saved.get("accent", ""))):
            data["accent"] = saved["accent"].upper()
    except (OSError, ValueError):
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


# ---------- helpers ----------

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def format_speed(bytes_per_sec):
    """Pick a sensible unit so small speeds don't show as 0.00 MB/s."""
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


def ease_in_out_cubic(t):
    return 4 * t ** 3 if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lerp_color(c1, c2, t):
    t = clamp(t)
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    return "#%02x%02x%02x" % (
        int(lerp(r1, r2, t)), int(lerp(g1, g2, t)), int(lerp(b1, b2, t))
    )


def hsv_to_hex(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(clamp(h), clamp(s), clamp(v))
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def hex_to_hsv(h):
    r, g, b = (x / 255 for x in hex_to_rgb(h))
    return colorsys.rgb_to_hsv(r, g, b)


def rounded_rect_points(cx, cy, w, h, r, steps=14):
    """Polygon points for a rounded rectangle (a true circle when r == w/2 == h/2)."""
    r = max(0, min(r, w / 2, h / 2))
    x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if r < 0.5:
        return [x1, y1, x2, y1, x2, y2, x1, y2]

    pts = []
    corners = [
        (x2 - r, y1 + r, -90),   # top-right
        (x2 - r, y2 - r, 0),     # bottom-right
        (x1 + r, y2 - r, 90),    # bottom-left
        (x1 + r, y1 + r, 180),   # top-left
    ]
    for ccx, ccy, start in corners:
        for i in range(steps + 1):
            a = math.radians(start + 90 * i / steps)
            pts.extend([ccx + r * math.cos(a), ccy + r * math.sin(a)])
    return pts


# 12 evenly spaced directions - enough that the glow rings look continuous
DIRS12 = [(math.cos(k * math.pi / 6), math.sin(k * math.pi / 6))
          for k in range(12)]


def glow_text(c, x, y, text, font, color, bg, strength=1.0, spread=4,
              step=1.2, anchor="center", tags=()):
    """Soft glow: `spread` rings of copies around the text, each ring dimmer
    than the one inside it (quadratic falloff, so there are no hard bands)."""
    for d in range(spread, 0, -1):          # outermost (faintest) first
        f = 1 - (d - 1) / spread            # 1.0 for the inner ring
        col = lerp_color(bg, color, 0.5 * strength * f * f)
        r = d * step
        for dx, dy in DIRS12:
            c.create_text(x + dx * r, y + dy * r, text=text, fill=col,
                          font=font, anchor=anchor, tags=tags)
    c.create_text(x, y, text=text, fill=color, font=font, anchor=anchor,
                  tags=tags)


def system_info():
    """Real machine info for the System card."""
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
    """Looks up the processor model, vendor, socket and cache once."""

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
    """Reads NVIDIA stats through nvidia-smi. Other GPUs only get a name."""

    def __init__(self):
        self.name = None
        self.util = 0.0
        self.mem_used = 0.0   # MiB
        self.mem_total = 0.0  # MiB
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


# ---------- custom canvas widgets ----------

class GlowLabel(tk.Canvas):
    """Label with a soft glow around the text. Colour can change at runtime."""

    def __init__(self, master, text, size, bg, scale=1.0, width=240,
                 color=TEXT, weight=BOLD, spread=4, step=1.1,
                 strength=0.9, anchor="w"):
        px = max(1, int(size * scale))
        self.font_t = (FONT, -px, weight)
        font = tkfont.Font(family=FONT, size=-px, weight=weight)
        self.font_obj = font
        self.pad = int(spread * step * scale + 3)
        self.h = font.metrics("linespace") + self.pad * 2
        self.w = int(width * scale)
        super().__init__(master, width=self.w, height=self.h, bg=bg,
                         highlightthickness=0, bd=0)
        self.bg_color = bg
        self.color = color
        self.spread = spread
        self.step = step * scale
        self.strength = strength
        self.text_anchor = anchor
        self.cur_text = None
        self.stale = False          # colour changed while hidden
        self.last_draw = 0.0
        self.set_text(text)

    def _render(self):
        self.stale = False
        self.delete("all")
        needed = self.font_obj.measure(self.cur_text) + 2 * self.pad
        if needed > self.w:               # wider font than planned: widen canvas
            self.w = needed
            self.configure(width=needed)
        x = self.pad if self.text_anchor == "w" else self.w / 2
        glow_text(self, x, self.h / 2, self.cur_text, self.font_t, self.color,
                  self.bg_color, self.strength, self.spread, self.step,
                  anchor=self.text_anchor)
        self.last_draw = time.perf_counter()

    def set_text(self, text):
        if text == self.cur_text and not self.stale:
            return
        # throttle: the glow is the expensive part, ~20 redraws/s is plenty
        if (self.cur_text is not None and not self.stale
                and time.perf_counter() - self.last_draw < 0.05):
            return
        self.cur_text = text
        self._render()

    def set_color(self, color):
        self.color = color
        if self.cur_text is None:
            return
        if self.winfo_viewable():
            self._render()
        else:
            self.stale = True       # redrawn when its page is shown


class RingGauge(tk.Canvas):
    """Circular gauge in the accent colour, with a soft glow."""

    GLOW_LAYERS = 0

    def __init__(self, master, size, bg, scale=1.0, accent=TEXT):
        self.px = int(size * scale)
        super().__init__(master, width=self.px, height=self.px, bg=bg,
                         highlightthickness=0, bd=0)
        self.bg_color = bg
        self.sc = scale
        self.accent = accent
        self.value = -1.0
        self.cur_num = None
        self.stale = False
        self.num_px = int(38 * scale)
        self.pct_px = int(15 * scale)
        self.num_font = tkfont.Font(family=FONT, size=-self.num_px, weight=BOLD)
        self.pct_font = tkfont.Font(family=FONT, size=-self.pct_px, weight=BOLD)
        self.set_value(0)

    def set_accent(self, color):
        self.accent = color
        if self.winfo_viewable():
            self.refresh()
        else:
            self.stale = True

    def refresh(self):
        self.cur_num = None
        self.draw(max(self.value, 0))

    def set_value(self, v):
        v = clamp(v, 0, 100)
        if self.value >= 0 and abs(v - self.value) < 0.08 and not self.stale:
            return  # nothing visible changed, skip the redraw
        self.value = v
        self.draw(v)

    def draw(self, v):
        c = self
        s = self.sc
        px = self.px
        m = 20 * s
        box = (m, m, px - m, px - m)
        cx = cy = px / 2
        radius = (px - 2 * m) / 2
        lw = 9 * s
        accent = self.accent

        # --- arc layer: redrawn every frame ---
        c.delete("dyn")
        c.create_oval(*box, outline=TRACK, width=lw, tags="dyn")

        extent = -359.9 * v / 100
        if v > 0.4:
            # many thin layers, faint at the outside -> smooth falloff
            n = self.GLOW_LAYERS
            for i in range(n):
                f = (i + 1) / n
                extra = 2 + (n - 1 - i) * 2.0
                c.create_arc(*box, start=90, extent=extent, style="arc",
                             outline=lerp_color(self.bg_color, accent,
                                                0.32 * f * f),
                             width=lw + extra * s, tags="dyn")
            c.create_arc(*box, start=90, extent=extent, style="arc",
                         outline=accent, width=lw, tags="dyn")

            # bright head dot at the tip of the arc
            ang = math.radians(90 + extent)
            hx = cx + radius * math.cos(ang)
            hy = cy - radius * math.sin(ang)
            for k in range(5, 0, -1):
                rr = lw / 2 + k * 1.6 * s
                c.create_oval(hx - rr, hy - rr, hx + rr, hy + rr, width=0,
                              fill=lerp_color(self.bg_color, accent,
                                              0.30 * (1 - (k - 1) / 5) ** 2),
                              tags="dyn")
            rr = lw / 2 + 0.5 * s
            c.create_oval(hx - rr, hy - rr, hx + rr, hy + rr, width=0,
                          fill=accent, tags="dyn")
        c.tag_lower("dyn")  # keep the number on top of the arcs

        # --- number layer: only redrawn when the shown integer changes ---
        text = f"{v:.0f}"
        if text != self.cur_num or self.stale:
            self.cur_num = text
            c.delete("num")
            nw = self.num_font.measure(text)
            pw = self.pct_font.measure("%")
            gap = 3 * s
            x0 = cx - (nw + gap + pw) / 2
            glow_text(c, x0, cy, text, (FONT, -self.num_px, BOLD), accent,
                      self.bg_color, strength=0.9, spread=5, step=1.2 * s,
                      anchor="w", tags="num")
            c.create_text(x0 + nw + gap, cy + 6 * s, text="%", anchor="w",
                          fill=MUTED, font=(FONT, -self.pct_px, BOLD),
                          tags="num")
        self.stale = False


class SparkChart(tk.Canvas):
    """Scrolling line chart in the accent colour (1 or more series)."""

    GLOW = ((15, 0.05), (11, 0.09), (8, 0.15), (5.5, 0.25))

    def __init__(self, master, bg, scale=1.0, height=110, accent=TEXT,
                 mixes=(1.0,), fixed_max=None, fmt=format_speed,
                 floor=64 * 1024.0):
        super().__init__(master, height=int(height * scale), bg=bg,
                         highlightthickness=0, bd=0)
        self.bg_color = bg
        self.sc = scale
        self.accent = accent
        self.mixes = mixes
        self.series = [deque([0.0] * HISTORY, maxlen=HISTORY) for _ in mixes]
        self.fixed_max = fixed_max
        self.fmt = fmt
        self.floor = floor
        self.y_scale = float(fixed_max or floor)
        self.t0 = time.perf_counter()
        self.last_draw = 0.0
        self.label_font = (FONT, -int(10 * scale))

    def push(self, *values):
        for data, v in zip(self.series, values):
            data.append(v)
        self.t0 = time.perf_counter()

    def redraw(self, dt):
        W, H = self.winfo_width(), self.winfo_height()
        if W < 40 or H < 30:
            return

        # y axis: fixed (percent charts) or smooth auto-scaling (speed charts)
        if self.fixed_max:
            self.y_scale = float(self.fixed_max)
        else:
            peak = max(max(max(d) for d in self.series), self.floor) * 1.25
            self.y_scale += (peak - self.y_scale) * (1 - math.exp(-3.0 * dt))

        now = time.perf_counter()
        if now - self.last_draw < 0.028:      # ~35 fps is plenty for lines
            return
        self.last_draw = now

        s = self.sc
        self.delete("all")
        pad = 8 * s
        usable = H - 2 * pad

        # faint grid
        for k in (0.25, 0.5, 0.75):
            y = pad + usable * k
            self.create_line(0, y, W, y, fill=GRID, dash=(2, 5))
        self.create_text(W - 2, 2, anchor="ne", fill=DIM, font=self.label_font,
                         text=self.fmt(self.y_scale))

        # scroll smoothly between samples
        frac = clamp((now - self.t0) / (UPDATE_MS / 1000))
        dx = W / (HISTORY - 2)

        # first series is drawn last so it sits on top
        for data, mix in reversed(list(zip(self.series, self.mixes))):
            color = lerp_color(self.bg_color, self.accent, mix)
            coords = []
            for i, v in enumerate(data):
                x = W + dx * (1 - frac) - (HISTORY - 1 - i) * dx
                y = H - pad - clamp(v / self.y_scale) * usable
                coords.extend((x, y))
            for width, glow_mix in self.GLOW:
                self.create_line(*coords, smooth=True, splinesteps=8,
                                 width=width * s,
                                 fill=lerp_color(self.bg_color, color, glow_mix),
                                 capstyle="round", joinstyle="round")
            self.create_line(*coords, smooth=True, splinesteps=8, width=2 * s,
                             fill=color, capstyle="round", joinstyle="round")


class GradientSlider(tk.Canvas):
    """Slider whose track is a colour gradient (0..1)."""

    def __init__(self, master, bg, scale, grad_fn, knob_fn, command, height=28):
        super().__init__(master, height=int(height * scale), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.sc = scale
        self.grad_fn = grad_fn
        self.knob_fn = knob_fn
        self.command = command
        self.value = 0.0
        self.pad = int(13 * scale)
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Button-1>", self.on_drag)
        self.bind("<B1-Motion>", self.on_drag)

    def on_drag(self, event):
        span = max(1, self.winfo_width() - 2 * self.pad)
        self.value = clamp((event.x - self.pad) / span)
        self.draw()
        self.command(self.value)

    def set_value(self, t):
        self.value = clamp(t)
        self.draw()

    def draw(self):
        W, H = self.winfo_width(), self.winfo_height()
        if W < 40:
            return
        s = self.sc
        self.delete("all")
        pad = self.pad
        bar_h = 10 * s
        y0 = (H - bar_h) / 2
        y1 = y0 + bar_h
        n = 56
        span = W - 2 * pad
        sw = span / n
        for i in range(n):
            x0 = pad + i * sw
            self.create_rectangle(x0, y0, x0 + sw + 1, y1,
                                  fill=self.grad_fn(i / (n - 1)), width=0)
        kx = pad + self.value * span
        r = 9 * s
        self.create_oval(kx - r - 2 * s, H / 2 - r - 2 * s,
                         kx + r + 2 * s, H / 2 + r + 2 * s,
                         fill="#000000", width=0)
        self.create_oval(kx - r, H / 2 - r, kx + r, H / 2 + r,
                         fill=self.knob_fn(), outline="#FFFFFF", width=2 * s)


# ---------- pages ----------

class Page(ctk.CTkFrame):
    """Base class: each page builds its own widgets and gets ticked/polled
    only while it is visible."""

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

        # gauge cards
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x")
        cards.grid_columnconfigure((0, 1, 2), weight=1, uniform="stat")

        self.gauges = []
        for col, (title, caption) in enumerate((
                ("CPU", "Processor load"),
                ("MEMORY", "RAM in use"),
                ("DISK", "Space used"))):
            card, gauge = app.gauge_card(cards, title, caption)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else 8, 0 if col == 2 else 8))
            self.gauges.append(gauge)

        # lower row
        middle = ctk.CTkFrame(self, fg_color="transparent")
        middle.pack(fill="both", expand=True, pady=(16, 0))
        middle.grid_columnconfigure(0, weight=3, uniform="low")
        middle.grid_columnconfigure(1, weight=2, uniform="low")
        middle.grid_rowconfigure(0, weight=1)

        # network card
        network = app.make_card(middle)
        network.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        ctk.CTkLabel(
            network, text="NETWORK", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))

        stats = ctk.CTkFrame(network, fg_color="transparent")
        stats.pack(fill="x", padx=22, pady=(10, 0))
        stats.grid_columnconfigure((0, 1), weight=1, uniform="net")

        self.down_label = app.net_stat(stats, "DOWNLOAD", 1.0, 0)
        self.up_label = app.net_stat(stats, "UPLOAD", 0.55, 1)

        self.chart = app.make_chart(network, height=100, mixes=(1.0, 0.55))
        self.chart.pack(fill="both", expand=True, padx=22, pady=(12, 18))
        app.net_charts.append(self.chart)

        # system info card
        system, _ = app.info_card(middle, "SYSTEM", system_info())
        system.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

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

        card, self.gauge = app.gauge_card(row1, "CPU", "Total load")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        hist = app.make_card(row1)
        hist.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(
            hist, text="LOAD HISTORY", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))
        self.chart = app.make_chart(hist, height=120, fixed_max=100,
                                    fmt=lambda v: f"{v:.0f}%")
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.hist_charts["cpu"] = self.chart

        # processor details
        details = app.make_card(self)
        details.pack(fill="both", expand=True, pady=(16, 0))

        ctk.CTkLabel(
            details, text="PROCESSOR", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))

        self.model = ctk.CTkLabel(
            details, text="Detecting processor...", text_color=app.accent,
            font=(FONT, 18, BOLD))
        self.model.pack(anchor="w", padx=22, pady=(4, 6))
        app.accent_widgets.append(self.model)

        cols = ctk.CTkFrame(details, fg_color="transparent")
        cols.pack(fill="x", padx=22, pady=(0, 14))
        cols.grid_columnconfigure((0, 1), weight=1, uniform="pc")

        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(18, 0))

        self.vals = {}
        self.vals.update(app.info_rows(left, [
            ("Manufacturer", "-"),
            ("Socket", "-"),
            ("Cores / threads", "-"),
            ("Architecture", platform.machine() or "-"),
        ], row_pad=7, pad_x=0))
        self.vals.update(app.info_rows(right, [
            ("Current speed", "-"),
            ("Rated speed", "-"),
            ("Cache (L2 / L3)", "-"),
            ("Processes", "-"),
        ], row_pad=7, pad_x=0))

    def poll(self):
        app = self.app
        data = app.cpu_info.data
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

        card, self.gauge = app.gauge_card(row1, "MEMORY", "RAM in use")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        hist = app.make_card(row1)
        hist.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(
            hist, text="USAGE HISTORY", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))
        self.chart = app.make_chart(hist, height=120, fixed_max=100,
                                    fmt=lambda v: f"{v:.0f}%")
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.hist_charts["mem"] = self.chart

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="both", expand=True, pady=(16, 0))
        row2.grid_columnconfigure((0, 1), weight=1, uniform="m2")
        row2.grid_rowconfigure(0, weight=1)

        ram, self.ram_vals = app.info_card(row2, "PHYSICAL MEMORY", [
            ("Total", "-"), ("Used", "-"), ("Available", "-")])
        ram.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        swap, self.swap_vals = app.info_card(row2, "SWAP / PAGE FILE", [
            ("Total", "-"), ("Used", "-"), ("Usage", "-")])
        swap.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

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

        card, self.gauge = app.gauge_card(row1, "GPU", "Graphics load")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        hist = app.make_card(row1)
        hist.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(
            hist, text="LOAD HISTORY", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))
        self.chart = app.make_chart(hist, height=120, fixed_max=100,
                                    fmt=lambda v: f"{v:.0f}%")
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.hist_charts["gpu"] = self.chart

        details, self.vals = app.info_card(self, "DETAILS", [
            ("Graphics card", "Detecting..."), ("Video memory", "-"),
            ("Temperature", "-"), ("Telemetry", "-")])
        details.pack(fill="x", pady=(16, 0))

        self.notice = ctk.CTkLabel(
            self, text="", text_color=DIM, font=(FONT, 11),
            wraplength=int(700 * s), justify="left")
        self.notice.pack(anchor="w", pady=(10, 0))

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
        for col, (key, title, mix) in enumerate((
                ("down", "DOWNLOAD", 1.0), ("up", "UPLOAD", 0.55))):
            card = app.make_card(top)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else 8, 0 if col == 1 else 8))

            legend = ctk.CTkFrame(card, fg_color="transparent")
            legend.pack(anchor="w", padx=22, pady=(18, 0))
            app.legend_dot(legend, mix).pack(side="left", padx=(0, 7))
            ctk.CTkLabel(legend, text=title, text_color=MUTED,
                         font=(FONT, 11, BOLD)).pack(side="left")

            label = app.glow_label(card, "0 B/s", 34, CARD, width=300,
                                   spread=5, step=1.2)
            label.pack(anchor="w", padx=14, pady=(4, 0))
            self.big[key] = label

            sub = ctk.CTkLabel(card, text="", text_color=DIM,
                               font=(FONT, 11))
            sub.pack(anchor="w", padx=22, pady=(0, 18))
            self.sub[key] = sub

        low = ctk.CTkFrame(self, fg_color="transparent")
        low.pack(fill="both", expand=True, pady=(16, 0))
        low.grid_columnconfigure(0, weight=3, uniform="nl")
        low.grid_columnconfigure(1, weight=2, uniform="nl")
        low.grid_rowconfigure(0, weight=1)

        chart_card = app.make_card(low)
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(
            chart_card, text="TRAFFIC", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))
        self.chart = app.make_chart(chart_card, height=120, mixes=(1.0, 0.55))
        self.chart.pack(fill="both", expand=True, padx=22, pady=(10, 18))
        app.net_charts.append(self.chart)

        iface_card = app.make_card(low)
        iface_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(
            iface_card, text="ACTIVE ADAPTERS", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 6))

        self.iface_rows = []
        for _ in range(5):
            row = ctk.CTkFrame(iface_card, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=7)
            name = ctk.CTkLabel(row, text="", text_color=MUTED, font=(FONT, 12))
            name.pack(side="left")
            ip = ctk.CTkLabel(row, text="", text_color=app.accent,
                              font=(FONT, 12, BOLD))
            ip.pack(side="right")
            app.accent_widgets.append(ip)
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

    PRESETS = ["#FFFFFF", "#5CE1FF", "#FF4FD8", "#7CFF6B",
               "#FFC247", "#A78BFA", "#FF5C5C"]

    def __init__(self, app, parent):
        super().__init__(app, parent)
        s = app.ui_scale
        app.page_title(self, "Settings")

        h, sat, val = hex_to_hsv(app.accent)
        self.h, self.s, self.v = h, sat, max(val, MIN_BRIGHTNESS)

        card = app.make_card(self)
        card.pack(fill="x")

        ctk.CTkLabel(
            card, text="ACCENT COLOR", text_color=MUTED,
            font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))
        ctk.CTkLabel(
            card,
            text="Recolors the glowing text, rings and charts. "
                 "Changes preview live; press Save to keep them.",
            text_color=DIM, font=(FONT, 11)
        ).pack(anchor="w", padx=22, pady=(2, 0))

        # live preview
        prev = ctk.CTkFrame(card, fg_color="transparent")
        prev.pack(fill="x", padx=14, pady=(8, 0))
        self.preview = app.glow_label(prev, "Aa  128.4 MB/s", 32, CARD,
                                      width=380, spread=5, step=1.3)
        self.preview.pack(side="left")
        self.hex_label = ctk.CTkLabel(
            prev, text=app.accent, text_color=MUTED, font=(FONT, 12, BOLD))
        self.hex_label.pack(side="right", padx=8)

        # presets
        swatches = ctk.CTkFrame(card, fg_color="transparent")
        swatches.pack(fill="x", padx=22, pady=(6, 0))
        for color in self.PRESETS:
            ctk.CTkButton(
                swatches, text="", width=30, height=30, corner_radius=15,
                fg_color=color, hover_color=color,
                border_width=1, border_color="#2A2A2A",
                command=lambda c=color: self.set_from_hex(c)
            ).pack(side="left", padx=(0, 10))

        # gradient sliders (each one lives in its own labelled row)
        knob = lambda: self.current_hex()
        specs = (
            ("Hue",
             lambda t: hsv_to_hex(t, 1, 1),
             self.on_hue),
            ("Saturation",
             lambda t: hsv_to_hex(self.h, t, self.v),
             self.on_sat),
            ("Brightness",
             lambda t: hsv_to_hex(
                 self.h, self.s,
                 MIN_BRIGHTNESS + (1 - MIN_BRIGHTNESS) * t),
             self.on_bri),
        )
        made = []
        for name, grad, command in specs:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=(8, 0))
            ctk.CTkLabel(row, text=name, text_color=MUTED, width=90,
                         anchor="w", font=(FONT, 12)).pack(side="left")
            slider = GradientSlider(row, CARD, s, grad, knob, command)
            slider.pack(side="left", fill="x", expand=True)
            made.append(slider)
        self.hue, self.sat, self.bri = made
        self.sliders = tuple(made)

        self.hue.set_value(self.h)
        self.sat.set_value(self.s)
        self.bri.set_value((self.v - MIN_BRIGHTNESS) / (1 - MIN_BRIGHTNESS))

        # hex entry + buttons
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=22, pady=(16, 20))

        ctk.CTkLabel(bottom, text="HEX", text_color=MUTED,
                     font=(FONT, 11, BOLD)).pack(side="left", padx=(0, 10))
        self.entry = ctk.CTkEntry(
            bottom, width=110, height=36, corner_radius=8,
            fg_color="#111111", border_color=BORDER, text_color=TEXT,
            font=(FONT, 13))
        self.entry.pack(side="left")
        self.entry.insert(0, app.accent)
        self.entry.bind("<Return>", self.on_entry)
        self.entry.bind("<FocusOut>", self.on_entry)

        ctk.CTkButton(
            bottom, text="Save", width=96, height=36, corner_radius=8,
            fg_color="#FFFFFF", hover_color="#D9D9D9", text_color="#000000",
            font=(FONT, 13, BOLD), command=self.save
        ).pack(side="right")
        ctk.CTkButton(
            bottom, text="Reset", width=84, height=36, corner_radius=8,
            fg_color="transparent", hover_color="#161616",
            border_width=1, border_color="#2A2A2A", text_color=MUTED,
            font=(FONT, 13), command=self.reset
        ).pack(side="right", padx=(0, 10))
        self.status = ctk.CTkLabel(
            bottom, text="Saved", text_color=MUTED, font=(FONT, 12))
        self.status.pack(side="right", padx=16)

    # ----- colour state -----

    def current_hex(self):
        return hsv_to_hex(self.h, self.s, self.v)

    def apply(self):
        color = self.current_hex()
        self.app.set_accent(color)
        self.hex_label.configure(text=color)
        self.entry.delete(0, "end")
        self.entry.insert(0, color)
        for slider in self.sliders:
            slider.draw()
        self.status.configure(
            text="Saved" if color == self.app.saved_accent else "Unsaved changes")

    def on_hue(self, t):
        self.h = t
        self.apply()

    def on_sat(self, t):
        self.s = t
        self.apply()

    def on_bri(self, t):
        self.v = MIN_BRIGHTNESS + (1 - MIN_BRIGHTNESS) * t
        self.apply()

    def set_from_hex(self, hex_color):
        h, s, v = hex_to_hsv(hex_color)
        self.h, self.s, self.v = h, s, max(v, MIN_BRIGHTNESS)
        self.hue.set_value(self.h)
        self.sat.set_value(self.s)
        self.bri.set_value((self.v - MIN_BRIGHTNESS) / (1 - MIN_BRIGHTNESS))
        self.apply()

    def on_entry(self, event=None):
        text = self.entry.get().strip()
        if not text.startswith("#"):
            text = "#" + text
        if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            self.set_from_hex(text)
        else:
            self.status.configure(text="Invalid hex")

    def save(self):
        ok = self.app.save_accent()
        self.status.configure(text="Saved" if ok else "Couldn't save file")

    def reset(self):
        self.set_from_hex(DEFAULT_ACCENT)


class RevoltApp(ctk.CTk):

    PAGE_NAMES = ["Overview", "Processor", "Memory",
                  "Graphics", "Network", "Settings"]

    def check_font(self):
        """Fall back cleanly if the custom font file couldn't be loaded."""
        global FONT
        if not FONT_LOADED:
            print(f"[Volt] Couldn't load the font file: {FONT_PATH}\n"
                  f"       Put sharkgotyourhand.ttf in a 'fonts' folder next to "
                  f"this script. Using Segoe UI for now.")
            FONT = "Segoe UI"
            return
        families = {f.lower(): f for f in tkfont.families(self)}
        if FONT not in families.values() and FONT.lower() in families:
            FONT = families[FONT.lower()]   # fix capitalisation differences

    def __init__(self):
        super().__init__()
        self.check_font()

        self.title("VOLT | System Monitor")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(950, 600)

        try:
            self.ui_scale = self._get_window_scaling()
        except Exception:
            self.ui_scale = 1.0

        # Borderless window; the colour key makes the empty areas see-through
        # so only the animated shape is visible during the splash.
        self.configure(fg_color=TRANSPARENT)
        self.overrideredirect(True)
        self.attributes("-transparentcolor", TRANSPARENT)
        self.center_window(WINDOW_W, WINDOW_H)

        self.is_max = False
        self.restore_geo = None
        self.minimized = False
        self._drag_x = 0
        self._drag_y = 0

        # accent colour - loaded from disk
        self.accent = settings["accent"]
        self.saved_accent = settings["accent"]
        self._accent_job = None

        # things that must be recoloured when the accent changes
        self.glow_labels = []
        self.accent_widgets = []
        self.accent_dots = []     # (frame, mix) legend dots
        self.all_gauges = []
        self.all_charts = []

        # live data: targets come from real readings, disp is what is shown
        keys = ("cpu", "mem", "disk", "gpu", "down", "up")
        self.target = {k: 0.0 for k in keys}
        self.disp = {k: 0.0 for k in keys}
        self.peak = {"down": 0.0, "up": 0.0}
        self.net_charts = []
        self.hist_charts = {}
        self.pages = {}
        self.current = "Overview"
        self.nav_items = {}
        self._slide_token = 0

        self.gpu = GpuMonitor()
        self.gpu.start()
        self.cpu_info = CpuInfo()
        self.cpu_info.start()

        # state for the speed calculation
        self.prev_sent = 0
        self.prev_recv = 0
        self.prev_time = time.time()
        self._last_frame = time.perf_counter()

        # Everything lives inside one container so the root can stay
        # transparent while the splash plays.
        self.container = ctk.CTkFrame(
            self,
            fg_color=BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER
        )
        self.container.pack(fill="both", expand=True)

        self.create_titlebar()
        ctk.CTkFrame(self.container, height=1, corner_radius=0,
                     fg_color=BORDER).pack(fill="x", padx=1)

        self.body = ctk.CTkFrame(
            self.container,
            fg_color="transparent",
            corner_radius=0
        )
        self.body.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        self.create_sidebar()
        ctk.CTkFrame(self.body, width=1, corner_radius=0,
                     fg_color=BORDER).pack(side="left", fill="y")
        self.create_pages()

        self.bind("<Map>", self.on_map)

        self.start_splash()
        # CTk touches the window ~200 ms after creation, so re-apply the
        # borderless style / taskbar entry after that.
        self.after(300, self.init_window)

    # ---------------------------------------------------------------
    # Accent colour
    # ---------------------------------------------------------------

    def set_accent(self, color):
        """Recolour everything that uses the accent. Calls are coalesced so
        dragging a slider never queues more work than the UI can draw."""
        self.accent = color
        if self._accent_job is None:
            self._accent_job = self.after(25, self._apply_accent)

    def _apply_accent(self):
        self._accent_job = None
        color = self.accent
        for label in self.glow_labels:
            label.set_color(color)
        for widget in self.accent_widgets:
            widget.configure(text_color=color)
        for gauge in self.all_gauges:
            gauge.set_accent(color)
        for chart in self.all_charts:
            chart.accent = color
        for dot, mix in self.accent_dots:
            dot.configure(fg_color=lerp_color(CARD, color, mix))
        self.set_active(self.current)

    def save_accent(self):
        self.saved_accent = self.accent
        settings["accent"] = self.accent
        return save_settings(settings)

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
        """Borderless windows get no taskbar icon by default - force one."""
        try:
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            self.withdraw()
            self.after(10, self.deiconify)
        except Exception:
            pass  # not on Windows

    def on_map(self, event):
        # Coming back from the taskbar: go borderless again
        if event.widget is self and self.minimized:
            self.minimized = False
            self.after(10, self.restore_borderless)

    def restore_borderless(self):
        self.overrideredirect(True)
        self.set_appwindow()

    def minimize(self):
        # iconify() doesn't work on borderless windows, so briefly give the
        # window its frame back, minimize it, and undo that on restore.
        self.update_idletasks()
        self.minimized = True
        self.overrideredirect(False)
        self.iconify()

    def work_area(self):
        """Screen area excluding the taskbar."""
        try:
            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
            rect = RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def toggle_maximize(self):
        if self.is_max:
            tk.Tk.geometry(self, self.restore_geo)
            self.is_max = False
            self.max_btn.configure(text="\uE922")  # maximize glyph
        else:
            self.restore_geo = (
                f"{self.winfo_width()}x{self.winfo_height()}"
                f"+{self.winfo_x()}+{self.winfo_y()}"
            )
            l, t, r, b = self.work_area()
            tk.Tk.geometry(self, f"{r - l}x{b - t}+{l}+{t}")
            self.is_max = True
            self.max_btn.configure(text="\uE923")  # restore glyph

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

    def start_move(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def do_move(self, event):
        if self.is_max:
            return
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        tk.Tk.geometry(self, f"+{x}+{y}")

    # ---------------------------------------------------------------
    # Startup animation
    # ---------------------------------------------------------------

    def start_splash(self):
        # Key-coloured canvas = invisible, and it hides the UI underneath
        self.splash = tk.Canvas(self, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.splash.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(self.splash)  # Canvas.lift() means "raise item", so call the widget version
        self.splash_frame = 0
        # small delay so the borderless/taskbar setup finishes first
        self.after(450, self.splash_tick)

    def splash_tick(self):
        f = self.splash_frame
        morph_start = GROW_FRAMES + HOLD_FRAMES
        curtain_start = morph_start + MORPH_FRAMES
        end = curtain_start + CURTAIN_FRAMES

        if f < morph_start:
            self.draw_orb(f)
        elif f < curtain_start:
            t = (f - morph_start + 1) / MORPH_FRAMES
            self.draw_morph(ease_in_out_cubic(clamp(t)))
        elif f < end:
            t = (f - curtain_start + 1) / CURTAIN_FRAMES
            # the finished box slides up and off the window
            self.splash.place(x=0, rely=-ease_in_cubic(clamp(t)),
                              relwidth=1, relheight=1)
        else:
            self.finish_splash()
            return

        self.splash_frame += 1
        self.after(FRAME_MS, self.splash_tick)

    def draw_orb(self, f):
        c = self.splash
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        cx, cy = W / 2, H / 2

        grow = clamp(f / GROW_FRAMES)
        e = ease_out_cubic(grow)
        pulse = 1 + 0.045 * math.sin(f * 0.22) if grow >= 1 else 1
        R = 62 * e * pulse

        # soft glow rings (blend towards the colour key = fades into the desktop)
        for i in range(10, 0, -1):
            rr = R + i * 5.5
            col = lerp_color(TRANSPARENT, accent_color, 0.05 * (11 - i) ** 1.4 / 10 * e)
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                          outline=col, width=2)

        # body of the orb
        c.create_oval(cx - R, cy - R, cx + R, cy + R,
                      fill=PANEL, outline=accent_color, width=3)

        # orbiting arcs
        ar = R + 20
        for offset in (0, 180):
            c.create_arc(cx - ar, cy - ar, cx + ar, cy + ar,
                         start=-f * 7 + offset, extent=80,
                         style="arc", outline=accent_color, width=3)

        # logo text (uses the saved accent colour)
        pulse_glow = 0.75 + 0.25 * math.sin(f * 0.22)
        glow_text(c, cx, cy, "VOLT", (FONT, 18, BOLD),
                  lerp_color(PANEL, self.accent, e), PANEL,
                  strength=e * pulse_glow, spread=5, step=1.5)

    def draw_morph(self, e):
        c = self.splash
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        cx, cy = W / 2, H / 2

        R = 62
        w = lerp(2 * R, W + 2, e)
        h = lerp(2 * R, H + 2, e)
        r = lerp(R, 0, e)

        fill = lerp_color(PANEL, BG, e)
        outline = lerp_color(accent_color, BG, e)

        # glow halo that fades as the shape expands
        for i in range(8, 0, -1):
            pad = i * 5.5 * (1 - e)
            col = lerp_color(TRANSPARENT, accent_color,
                             0.05 * (9 - i) ** 1.4 / 8 * (1 - e))
            c.create_polygon(
                rounded_rect_points(cx, cy, w + pad * 2, h + pad * 2, r + pad),
                fill="", outline=col, width=2
            )

        c.create_polygon(
            rounded_rect_points(cx, cy, w, h, r),
            fill=fill, outline=outline, width=3
        )

        # orbiting arcs peel away early in the morph
        spin = clamp(1 - e * 2.5)
        if spin > 0:
            ar = R + 20
            f = self.splash_frame
            col = lerp_color(TRANSPARENT, accent_color, spin)
            for offset in (0, 180):
                c.create_arc(cx - ar, cy - ar, cx + ar, cy + ar,
                             start=-f * 7 + offset, extent=80,
                             style="arc", outline=col, width=3)

        # logo grows into the title card
        glow_text(c, cx, cy - 6 * e, "VOLT",
                  (FONT, int(lerp(18, 40, e)), BOLD),
                  self.accent, fill,
                  strength=1.0, spread=6, step=lerp(1.4, 1.9, e))

        sub = clamp((e - 0.55) * 2.2)
        if sub > 0:
            c.create_text(cx, cy + 38, text="SYSTEM MONITOR",
                          fill=lerp_color(BG, MUTED, sub),
                          font=(FONT, 11))

    def finish_splash(self):
        self.splash.destroy()
        # the window is now fully covered by the UI: drop the see-through key
        self.attributes("-transparentcolor", "")
        self.configure(fg_color=BG)
        self.start_monitoring()

    # ---------------------------------------------------------------
    # Live data + smooth animation
    # ---------------------------------------------------------------

    def start_monitoring(self):
        # baseline readings for the speed calculation
        self.prev_sent = net.get_bytes_sent()
        self.prev_recv = net.get_bytes_receieved()
        self.prev_time = time.time()
        self._last_frame = time.perf_counter()

        self.poll_stats()      # takes real readings once per UPDATE_MS
        self.animate_loop()    # glides the display towards those readings

    def poll_stats(self):
        """Take real readings. These only set targets; the animation loop
        eases the displayed values towards them."""
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

            # history charts keep collecting even while their page is hidden
            for key, value in (("cpu", cpu), ("mem", mem), ("gpu", gpu)):
                chart = self.hist_charts.get(key)
                if chart:
                    chart.push(value)

            self.pages[self.current].poll()
        except tk.TclError:
            pass  # window closed

    def animate_loop(self):
        try:
            self.after(FRAME_DELAY, self.animate_loop)

            now = time.perf_counter()
            dt = min(now - self._last_frame, 0.1)
            self._last_frame = now

            # frame-rate independent exponential easing
            a = 1 - math.exp(-SMOOTHING * dt)
            for k in self.disp:
                self.disp[k] += (self.target[k] - self.disp[k]) * a

            self.pages[self.current].tick(dt)
        except tk.TclError:
            pass  # window closed

    # ---------------------------------------------------------------
    # Page switching (with a short glide-in)
    # ---------------------------------------------------------------

    def show_page(self, name, animate=True):
        if animate and name == self.current and self.pages[name].winfo_ismapped():
            return

        for page in self.pages.values():
            page.place_forget()

        self.current = name
        page = self.pages[name]
        self._slide_token += 1
        offset = PAGE_SLIDE_PX * self.ui_scale if animate else 0
        page.place(x=0, y=int(offset), relwidth=1, relheight=1)

        self.set_active(name)
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
        """Redraw anything whose accent colour changed while it was hidden."""
        for label in self.glow_labels:
            if label.stale and label.winfo_viewable():
                label._render()
        for gauge in self.all_gauges:
            if gauge.stale and gauge.winfo_viewable():
                gauge.refresh()

    # ---------------------------------------------------------------
    # UI building blocks
    # ---------------------------------------------------------------

    def create_titlebar(self):

        bar = ctk.CTkFrame(
            self.container,
            height=TITLEBAR_H,
            corner_radius=0,
            fg_color=PANEL
        )
        bar.pack(side="top", fill="x", padx=1, pady=(1, 0))
        bar.pack_propagate(False)

        title = ctk.CTkLabel(
            bar,
            text="VOLT   ·   System Monitor",
            font=(FONT, 11),
            text_color=MUTED
        )
        title.pack(side="left", padx=16)

        def make_btn(glyph, command, hover):
            btn = ctk.CTkButton(
                bar,
                text=glyph,
                width=46,
                height=TITLEBAR_H,
                corner_radius=0,
                fg_color="transparent",
                hover_color=hover,
                text_color="#D4D4D4",
                font=(ICON_FONT, 10),
                command=command
            )
            btn.pack(side="right")
            return btn

        # packed right-to-left: close, maximize, minimize
        make_btn("\uE8BB", self.close, "#E81123")
        self.max_btn = make_btn("\uE922", self.toggle_maximize, "#1A1A1A")
        make_btn("\uE921", self.minimize, "#1A1A1A")

        # drag the window by the bar, double-click to maximize
        for widget in (bar, title):
            widget.bind("<ButtonPress-1>", self.start_move)
            widget.bind("<B1-Motion>", self.do_move)
            widget.bind("<Double-Button-1>", lambda e: self.toggle_maximize())

    def draw_logo(self, phase=0.0):
        try:
            c = self.logo_canvas
            c.delete("all")
            strength = 0.7 + 0.3 * math.sin(phase)  # slow breathing glow
            glow_text(c, 110, 26, "VOLT", (FONT, 27, BOLD),
                      self.accent, PANEL, strength=strength,
                      spread=5, step=1.3)
            self.after(50, lambda: self.draw_logo(phase + 0.12))
        except tk.TclError:
            pass  # window closed

    def set_active(self, name):
        for n, (indicator, btn) in self.nav_items.items():
            active = n == name
            indicator.configure(fg_color=self.accent if active else PANEL)
            btn.configure(
                fg_color="#161616" if active else "transparent",
                text_color=self.accent if active else MUTED
            )

    def create_sidebar(self):

        self.sidebar = ctk.CTkFrame(
            self.body,
            width=220,
            corner_radius=0,
            fg_color=PANEL
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Canvas logo so it can glow (labels can't)
        self.logo_canvas = tk.Canvas(
            self.sidebar,
            width=220,
            height=52,
            bg=PANEL,
            highlightthickness=0,
            bd=0
        )
        self.logo_canvas.pack(pady=(28, 4))
        self.draw_logo()

        ctk.CTkLabel(
            self.sidebar,
            text="S Y S T E M   M O N I T O R",
            font=(FONT, 9),
            text_color=DIM
        ).pack(pady=(0, 38))

        for name in self.PAGE_NAMES:

            row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
            row.pack(fill="x", padx=(0, 14), pady=2)

            indicator = ctk.CTkFrame(
                row, width=3, height=20, corner_radius=2, fg_color=PANEL)
            indicator.pack(side="left", padx=(0, 9))

            btn = ctk.CTkButton(
                row,
                text=name,
                height=40,
                anchor="w",
                fg_color="transparent",
                text_color=MUTED,
                hover_color="#121212",
                corner_radius=8,
                font=(FONT, 13),
                command=lambda n=name: self.show_page(n)
            )
            btn.pack(side="left", fill="x", expand=True)
            self.nav_items[name] = (indicator, btn)

        self.set_active("Overview")

        ctk.CTkLabel(
            self.sidebar,
            text="Volt v1.0.0",
            text_color=DIM,
            font=(FONT, 10)
        ).pack(side="bottom", pady=20)

    def create_pages(self):
        self.main = ctk.CTkFrame(self.body, fg_color="transparent")
        self.main.pack(side="left", fill="both", expand=True, padx=32, pady=26)

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
        return ctk.CTkFrame(
            parent,
            fg_color=CARD,
            corner_radius=16,
            border_width=1,
            border_color=BORDER
        )

    def glow_label(self, parent, text, size, bg, width=240, **kw):
        """GlowLabel registered for accent recolouring."""
        label = GlowLabel(parent, text, size, bg, scale=self.ui_scale,
                          width=width, color=self.accent, **kw)
        self.glow_labels.append(label)
        return label

    def page_title(self, parent, text):
        label = self.glow_label(parent, text, 30, BG, width=420,
                                spread=5, step=1.3, strength=0.95)
        label.pack(anchor="w", pady=(0, 18))
        return label

    def make_chart(self, parent, **kw):
        """SparkChart registered for accent recolouring."""
        height = kw.pop("height", 110)
        chart = SparkChart(parent, CARD, scale=self.ui_scale, height=height,
                           accent=self.accent, **kw)
        self.all_charts.append(chart)
        return chart

    def legend_dot(self, parent, mix):
        dot = ctk.CTkFrame(
            parent, width=8, height=8, corner_radius=4,
            fg_color=lerp_color(CARD, self.accent, mix))
        self.accent_dots.append((dot, mix))
        return dot

    def gauge_card(self, parent, title, caption, size=152):
        """Returns (card, gauge). The caller decides how to place the card."""
        card = self.make_card(parent)

        ctk.CTkLabel(
            card, text=title, text_color=MUTED, font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 0))

        gauge = RingGauge(card, size, CARD, scale=self.ui_scale,
                          accent=self.accent)
        gauge.pack(pady=(4, 0))
        self.all_gauges.append(gauge)

        ctk.CTkLabel(
            card, text=caption, text_color=DIM, font=(FONT, 11)
        ).pack(pady=(0, 16))
        return card, gauge

    def info_rows(self, parent, rows, row_pad=9, pad_x=22):
        """Label/value rows with thin separators. Returns {key: value_label}."""
        labels = {}
        for i, (key, value) in enumerate(rows):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=pad_x, pady=row_pad)

            ctk.CTkLabel(
                row, text=key, text_color=MUTED, font=(FONT, 12)
            ).pack(side="left")

            value_label = ctk.CTkLabel(
                row, text=value, text_color=self.accent,
                font=(FONT, 13, BOLD))
            value_label.pack(side="right")
            labels[key] = value_label
            self.accent_widgets.append(value_label)

            if i < len(rows) - 1:
                ctk.CTkFrame(
                    parent, height=1, corner_radius=0, fg_color=BORDER
                ).pack(fill="x", padx=pad_x)
        return labels

    def info_card(self, parent, title, rows):
        """Card with a title and label/value rows. Returns (card, labels)."""
        card = self.make_card(parent)
        ctk.CTkLabel(
            card, text=title, text_color=MUTED, font=(FONT, 11, BOLD)
        ).pack(anchor="w", padx=22, pady=(18, 6))
        labels = self.info_rows(card, rows)
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()
        return card, labels

    def net_stat(self, parent, title, dot_mix, column):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=0, column=column, sticky="w")

        legend = ctk.CTkFrame(cell, fg_color="transparent")
        legend.pack(anchor="w")

        self.legend_dot(legend, dot_mix).pack(side="left", padx=(0, 7))

        ctk.CTkLabel(
            legend, text=title, text_color=MUTED, font=(FONT, 10, BOLD)
        ).pack(side="left")

        label = self.glow_label(cell, "0 B/s", 27, CARD, width=200,
                                spread=4, step=1.2)
        label.pack(anchor="w", pady=(2, 0))
        return label


if __name__ == "__main__":
    app = RevoltApp()
    app.mainloop()