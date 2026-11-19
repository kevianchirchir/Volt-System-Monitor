import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { StatsProvider } from "./context/StatsContext.jsx";
import { useAccent } from "./useAccent.js";
import { Graphics, Memory, Network, Overview, Processor, Settings } from "./pages.jsx";

const PAGES = { Overview, Processor, Memory, Graphics, Network, Settings };

function Splash({ out }) {
  return (
    <div id="splash" className={out ? "out" : ""}>
      <div className="orb">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="48" pathLength="100" />
          <circle cx="50" cy="50" r="48" pathLength="100" style={{ transform: "rotate(180deg)" }} />
        </svg>
        <span>VOLT</span>
      </div>
    </div>
  );
}

function TitleBar() {
  return (
    <div className="bar pywebview-drag-region" onDoubleClick={() => api("toggle_max")}>
      <span>VOLT &nbsp;·&nbsp; System Monitor</span>
      <div className="win">
        <button onClick={() => api("minimize")} aria-label="Minimize"><svg viewBox="0 0 10 10"><path d="M0 5h10" /></svg></button>
        <button className="x" onClick={() => api("close")} aria-label="Close"><svg viewBox="0 0 10 10"><path d="M0 0l10 10M10 0L0 10" /></svg></button>
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("Overview");
  const [booted, setBooted] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [splashGone, setSplashGone] = useState(false);
  const accent = useAccent();
  const started = useRef(false);

  // Boot once pywebview is ready (or after 800ms in a plain browser)
  useEffect(() => {
    const boot = async () => {
      if (started.current) return;
      started.current = true;
      if (!window.pywebview) document.documentElement.style.background = "#000";
      await accent.load();
      setBooted(true);
    };
    window.addEventListener("pywebviewready", boot);
    let t;
    if (window.pywebview?.api) boot();
    else if (!window.pywebview) t = setTimeout(() => { if (!window.pywebview) boot(); }, 800);
    return () => { window.removeEventListener("pywebviewready", boot); clearTimeout(t); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Splash timeline: reveal app at 2.3s, remove splash at 3.2s
  useEffect(() => {
    if (!booted) return;
    const a = setTimeout(() => setRevealed(true), 2300);
    const b = setTimeout(() => setSplashGone(true), 3200);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, [booted]);

  const Page = PAGES[page];

  return (
    <StatsProvider enabled={booted}>
      {!splashGone && <Splash out={revealed} />}
      <div className={revealed ? "app show" : "app"}>
        <TitleBar />
        <div className="body">
          <aside>
            <div className="logo">VOLT</div>
            <div className="tag">SYSTEM MONITOR</div>
            <nav>
              {Object.keys(PAGES).map((p) => (
                <button key={p} className={p === page ? "on" : ""} onClick={() => setPage(p)}>
                  <i />{p}
                </button>
              ))}
            </nav>
            <div className="ver">Volt v1.2.0</div>
          </aside>
          <main><Page accent={accent} /></main>
        </div>
      </div>
    </StatsProvider>
  );
}
