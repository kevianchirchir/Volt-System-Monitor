import { useEffect, useState } from "react";
import Chart from "./Chart.jsx";
import { useStats } from "./context/StatsContext.jsx";
import { Gauge, Rows, Speed } from "./ui.jsx";
import { MINB, PRESETS, hsv2hex, speed } from "./lib.js";

export function Overview() {
  return (
    <section className="page on">
      <h1>System Overview</h1>
      <div className="row c3">
        <Gauge id="cpu" title="CPU" caption="Processor load" />
        <Gauge id="mem" title="MEMORY" caption="RAM in use" />
        <Gauge id="disk" title="DISK" caption="Space used" />
      </div>
      <div className="row c32 fill">
        <div className="card">
          <div className="h">NETWORK</div>
          <div className="stats">
            <div><div className="h"><i className="dot" />DOWNLOAD</div><Speed k="down" className="big med" /></div>
            <div><div className="h"><i className="dot up" />UPLOAD</div><Speed k="up" className="big med up-s" /></div>
          </div>
          <Chart kind="net" />
        </div>
        <div className="card">
          <div className="h">SYSTEM</div>
          <Rows group="sys" keys={["Operating System", "Architecture", "Processor", "Installed RAM"]} />
        </div>
      </div>
    </section>
  );
}

export function Processor() {
  const { info } = useStats();
  return (
    <section className="page on">
      <h1>Processor</h1>
      <div className="row c12">
        <Gauge id="cpu" title="CPU" caption="Total load" />
        <div className="card"><div className="h">LOAD HISTORY</div><Chart kind="cpu" /></div>
      </div>
      <div className="card" style={{ flex: 1 }}>
        <div className="h">PROCESSOR</div>
        <div className="model">{info["cpu.model"] ?? "Detecting processor..."}</div>
        <div className="row c2" style={{ gap: 36 }}>
          <Rows tight group="cpu" keys={["Manufacturer", "Socket", "Cores / threads", "Architecture"]} />
          <Rows tight group="cpu" keys={["Current speed", "Rated speed", "Cache (L2 / L3)", "Processes"]} />
        </div>
      </div>
    </section>
  );
}

export function Memory() {
  return (
    <section className="page on">
      <h1>Memory</h1>
      <div className="row c12">
        <Gauge id="mem" title="MEMORY" caption="RAM in use" />
        <div className="card"><div className="h">USAGE HISTORY</div><Chart kind="mem" /></div>
      </div>
      <div className="row c2 fill">
        <div className="card"><div className="h">PHYSICAL MEMORY</div><Rows group="ram" keys={["Total", "Used", "Available"]} /></div>
        <div className="card"><div className="h">SWAP / PAGE FILE</div><Rows group="swap" keys={["Total", "Used", "Usage"]} /></div>
      </div>
    </section>
  );
}

export function Graphics() {
  const { info } = useStats();
  return (
    <section className="page on">
      <h1>Graphics</h1>
      <div className="row c12">
        <Gauge id="gpu" title="GPU" caption="Graphics load" />
        <div className="card"><div className="h">LOAD HISTORY</div><Chart kind="gpu" /></div>
      </div>
      <div className="card">
        <div className="h">DETAILS</div>
        <Rows group="gpu" keys={["Graphics card", "Video memory", "Temperature", "Telemetry"]} />
      </div>
      <p className="notice">{info["gpu.notice"]}</p>
    </section>
  );
}

export function Network() {
  const { info, ifaces, peak, ready } = useStats();
  return (
    <section className="page on">
      <h1>Network</h1>
      <div className="row c2">
        <div className="card">
          <div className="h"><i className="dot" />DOWNLOAD</div>
          <Speed k="down" className="big" />
          <div className="sub">{ready && `Total received ${info["net.recv"] ?? "-"}   Peak ${speed(peak.down)}`}</div>
        </div>
        <div className="card">
          <div className="h"><i className="dot up" />UPLOAD</div>
          <Speed k="up" className="big up-s" />
          <div className="sub">{ready && `Total sent ${info["net.sent"] ?? "-"}   Peak ${speed(peak.up)}`}</div>
        </div>
      </div>
      <div className="row c32 fill">
        <div className="card"><div className="h">TRAFFIC</div><Chart kind="net" /></div>
        <div className="card">
          <div className="h">ACTIVE ADAPTERS</div>
          <div className="rows">
            {ifaces.map(([name, ip], i) => <div key={name + i}><span>{name}</span><em>{ip}</em></div>)}
          </div>
        </div>
      </div>
    </section>
  );
}

const HUE_GRADIENT = "linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00)";

export function Settings({ accent: a }) {
  // Text box edits locally; committed on blur/Enter (like a native "change" event)
  const [text, setText] = useState(a.hex);
  useEffect(() => setText(a.hex), [a.hex]);

  const commit = () => {
    if (text === a.hex) return;
    let t = text.trim();
    if (!t.startsWith("#")) t = "#" + t;
    if (/^#[0-9a-f]{6}$/i.test(t)) a.setHex(t.toUpperCase());
    else a.flag("Invalid hex");
  };

  return (
    <section className="page on">
      <h1>Settings</h1>
      <div className="card" style={{ flex: "0 0 auto" }}>
        <div className="h">ACCENT COLOR</div>
        <div className="sub" style={{ marginTop: 2 }}>
          Recolors the glowing text, rings and charts. Changes preview live; press Save to keep them.
        </div>
        <div className="sw">
          {PRESETS.map((c) => (
            <button key={c} className={c === a.hex ? "on" : ""} style={{ background: c }} aria-label={c} onClick={() => a.setHex(c)} />
          ))}
        </div>
        <div className="sl"><span>Hue</span>
          <input type="range" min="0" max="1000" value={a.hue * 1000} style={{ "--g": HUE_GRADIENT }}
            onChange={(e) => a.patch({ hue: e.target.value / 1000 })} />
        </div>
        <div className="sl"><span>Saturation</span>
          <input type="range" min="0" max="1000" value={a.sat * 1000}
            style={{ "--g": `linear-gradient(90deg,${hsv2hex(a.hue, 0, a.bri)},${hsv2hex(a.hue, 1, a.bri)})` }}
            onChange={(e) => a.patch({ sat: e.target.value / 1000 })} />
        </div>
        <div className="sl"><span>Brightness</span>
          <input type="range" min="0" max="1000" value={((a.bri - MINB) / (1 - MINB)) * 1000}
            style={{ "--g": `linear-gradient(90deg,${hsv2hex(a.hue, a.sat, MINB)},${hsv2hex(a.hue, a.sat, 1)})` }}
            onChange={(e) => a.patch({ bri: MINB + ((1 - MINB) * e.target.value) / 1000 })} />
        </div>
        <div className="act">
          <span className="h">HEX</span>
          <input type="text" maxLength={7} value={text} onChange={(e) => setText(e.target.value)}
            onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} />
          <span className="sp">{a.status}</span>
          <button className="btn" onClick={a.reset}>Reset</button>
          <button className="btn p" onClick={a.save}>Save</button>
        </div>
      </div>
    </section>
  );
}
