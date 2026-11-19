import { useLayoutEffect, useRef, useState } from "react";
import { useStats } from "./context/StatsContext.jsx";
import { HISTORY, bezier, clamp, pct, speed } from "./lib.js";

const KINDS = {
  net: { max: 0, fmt: speed }, // max 0 = auto-scale
  cpu: { max: 100, fmt: pct },
  mem: { max: 100, fmt: pct },
  gpu: { max: 100, fmt: pct },
};

export default function Chart({ kind }) {
  const { hist } = useStats();
  const { max, fmt } = KINDS[kind];
  const data = hist[kind];

  const box = useRef(null), series = useRef(null), prev = useRef(null), spacing = useRef(0);
  const [{ w, h }, setSize] = useState({ w: 0, h: 0 });

  // Track container size
  useLayoutEffect(() => {
    const el = box.current;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const padT = 6, padB = 8, usable = h - padT - padB, dx = w / (HISTORY - 2);
  spacing.current = dx;
  const scale = max || Math.max(...data.flat(), 64 * 1024) * 1.25;

  // Slide the lines left by one step whenever a new reading arrives
  useLayoutEffect(() => {
    if (prev.current && prev.current !== data && series.current && !matchMedia("(prefers-reduced-motion:reduce)").matches) {
      series.current.animate(
        [{ transform: `translateX(${spacing.current}px)` }, { transform: "translateX(0)" }],
        { duration: 1000, easing: "linear" }
      );
    }
    prev.current = data;
  }, [data]);

  return (
    <div className="chart" ref={box}>
      {w >= 40 && h >= 30 && (
        <svg>
          <g>
            {[0.25, 0.5, 0.75].map((p) => {
              const y = padT + usable * p;
              return <line key={p} className="g" x1="0" x2={w} y1={y} y2={y} />;
            })}
          </g>
          <g ref={series}>
            {data.map((d, i) => {
              const pts = d.map((v, j) => [w - (HISTORY - 1 - j) * dx, h - padB - clamp(v / scale) * usable]);
              const line = bezier(pts);
              return (
                <g key={i} style={{ opacity: i ? 0.55 : 1 }}>
                  <path className="f" d={`${line}L${w},${h}L${pts[0][0]},${h}Z`} />
                  <path className="l" d={line} />
                </g>
              );
            }).reverse()}
          </g>
          <text x={w - 2} y="10" textAnchor="end">{fmt(scale)}</text>
        </svg>
      )}
    </div>
  );
}
