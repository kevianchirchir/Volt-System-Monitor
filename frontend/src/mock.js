// Dev-only fake data for browser preview. Never used in production builds.
let t = 0;
const wave = (base, amp, rate) =>
  Math.max(0, Math.min(100, base + amp * Math.sin(t * rate) + Math.random() * 4));

export function mockApi(method) {
  if (method !== "stats") return null;
  t += 1;
  return {
    cpu: wave(35, 25, 0.4), mem: wave(58, 3, 0.1), disk: 62, gpu: wave(20, 15, 0.3),
    down: Math.random() * 2.5e6 * (1 + Math.sin(t * 0.3)), up: Math.random() * 3e5,
    ifaces: [["Ethernet", "192.168.1.20"], ["Wi-Fi", "192.168.1.34"]],
    netstats: {
      "sys.Operating System": "Windows 11", "sys.Architecture": "AMD64",
      "sys.Processor": "Demo CPU @ 3.6 GHz", "sys.Installed RAM": "16.0 GB",
      "cpu.model": "Demo CPU 8-Core Processor", "cpu.Manufacturer": "Demo", "cpu.Socket": "AM4",
      "cpu.Cores / threads": "8 / 16", "cpu.Architecture": "x64", "cpu.Current speed": "3.60 GHz",
      "cpu.Rated speed": "3.60 GHz", "cpu.Cache (L2 / L3)": "4 MB / 32 MB", "cpu.Processes": "214",
      "ram.Total": "16.0 GB", "ram.Used": "9.2 GB", "ram.Available": "6.8 GB",
      "swap.Total": "4.0 GB", "swap.Used": "0.6 GB", "swap.Usage": "15%",
      "gpu.Graphics card": "Demo GPU", "gpu.Video memory": "8 GB", "gpu.Temperature": "54 °C",
      "gpu.Telemetry": "Available", "gpu.notice": "Demo data (browser preview).",
      "net.recv": "1.2 GB", "net.sent": "210 MB",
    },
  };
}
