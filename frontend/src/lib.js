export const HISTORY = 45;
export const DEFAULT = "#FFFFFF";
export const MINB = 0.35;
export const PRESETS = ["#FFFFFF", "#5CE1FF", "#FF4FD8", "#7CFF6B", "#FFC247", "#A78BFA", "#FF5C5C"];

export const clamp = (v, min = 0, max = 1) => Math.max(min, Math.min(max, v));

export const speed = (b) => {
  if (b >= 1048576) return (b / 1048576).toFixed(2) + " MB/s";
  if (b >= 1024) return (b / 1024).toFixed(1) + " KB/s";
  return Math.max(b, 0).toFixed(0) + " B/s";
};

export const pct = (v) => v.toFixed(0) + "%";

// Catmull-Rom points -> smooth SVG path
export function bezier(p) {
  let d = `M${p[0][0]},${p[0][1]}`;
  for (let i = 0; i < p.length - 1; i++) {
    const a = p[Math.max(i - 1, 0)], b = p[i], c = p[i + 1], e = p[Math.min(i + 2, p.length - 1)];
    d += `C${b[0] + (c[0] - a[0]) / 6},${b[1] + (c[1] - a[1]) / 6} ` +
         `${c[0] - (e[0] - b[0]) / 6},${c[1] - (e[1] - b[1]) / 6} ${c[0]},${c[1]}`;
  }
  return d;
}

export function hsv2hex(h, s, v) {
  const ch = (n) => {
    const k = (n + h * 6) % 6;
    return v - v * s * Math.max(0, Math.min(k, 4 - k, 1));
  };
  return "#" + [5, 3, 1].map((n) => Math.round(ch(n) * 255).toString(16).padStart(2, "0")).join("").toUpperCase();
}

export function hex2hsv(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), d = max - Math.min(r, g, b);
  let h = 0;
  if (d !== 0) {
    if (max === r) h = ((g - b) / d + 6) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
  }
  return [h / 6, max === 0 ? 0 : d / max, max];
}
