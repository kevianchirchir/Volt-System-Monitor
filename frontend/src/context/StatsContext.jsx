import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import { HISTORY } from "../lib.js";

const ZERO = { cpu: 0, mem: 0, disk: 0, gpu: 0, down: 0, up: 0 };
const blank = () => Array(HISTORY).fill(0);
// Each chart's history is an array of series: net has two (down, up), the rest one.
const initialHist = () => ({ cpu: [blank()], mem: [blank()], gpu: [blank()], net: [blank(), blank()] });
const push = (series, v) => [...series.slice(1), v];

const StatsContext = createContext(null);
export const useStats = () => useContext(StatsContext);

export function StatsProvider({ enabled, children }) {
  // Raw target + eased display values live in refs and are written straight to the DOM
  // by subscribers every frame, so the 60fps animation never re-renders React.
  const target = useRef({ ...ZERO });
  const disp = useRef({ ...ZERO });
  const subs = useRef(new Set());

  const [hist, setHist] = useState(initialHist);
  const [info, setInfo] = useState({});
  const [ifaces, setIfaces] = useState([]);
  const [peak, setPeak] = useState({ down: 0, up: 0 });
  const [ready, setReady] = useState(false);

  // Smoothing loop
  useEffect(() => {
    let raf, last = performance.now();
    const frame = (now) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      const ease = 1 - Math.exp(-5 * dt);
      for (const k in disp.current) disp.current[k] += (target.current[k] - disp.current[k]) * ease;
      subs.current.forEach((s) => s.fn(disp.current[s.key]));
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  // Polling loop (1s)
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false, timer;
    const poll = async () => {
      const s = await api("stats").catch(() => null);
      if (cancelled) return;
      if (s) {
        for (const k in target.current) target.current[k] = s[k];
        setPeak((p) => ({ down: Math.max(p.down, s.down), up: Math.max(p.up, s.up) }));
        setHist((h) => ({
          cpu: [push(h.cpu[0], s.cpu)],
          mem: [push(h.mem[0], s.mem)],
          gpu: [push(h.gpu[0], s.gpu)],
          net: [push(h.net[0], s.down), push(h.net[1], s.up)],
        }));
        setInfo((i) => ({ ...i, ...s.netstats }));
        setIfaces(s.ifaces || []);
        setReady(true);
      }
      timer = setTimeout(poll, 1000);
    };
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [enabled]);

  const subscribe = useCallback((key, fn) => {
    const sub = { key, fn };
    subs.current.add(sub);
    fn(disp.current[key]); // paint immediately so remounted pages don't flash zero
    return () => { subs.current.delete(sub); };
  }, []);

  const value = useMemo(() => ({ hist, info, ifaces, peak, ready, subscribe }), [hist, info, ifaces, peak, ready, subscribe]);
  return <StatsContext.Provider value={value}>{children}</StatsContext.Provider>;
}

// Calls `apply(easedValue)` every animation frame while the component is mounted.
export function useDisplayValue(key, apply) {
  const { subscribe } = useStats();
  const ref = useRef(apply);
  useEffect(() => { ref.current = apply; });
  useLayoutEffect(() => subscribe(key, (v) => ref.current(v)), [key, subscribe]);
}
