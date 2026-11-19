import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { DEFAULT, MINB, hex2hsv, hsv2hex } from "./lib.js";

export function useAccent() {
  const [hsv, setHsv] = useState({ hue: 0, sat: 0, bri: 1 });
  const [saved, setSaved] = useState(DEFAULT);
  const [msg, setMsg] = useState(null); // transient status ("Invalid hex", save result)

  const hex = useMemo(() => hsv2hex(hsv.hue, hsv.sat, hsv.bri), [hsv]);

  // Live preview: push the accent into the CSS variable
  useEffect(() => { document.documentElement.style.setProperty("--accent", hex); }, [hex]);

  const patch = useCallback((p) => { setMsg(null); setHsv((c) => ({ ...c, ...p })); }, []);
  const setHex = useCallback((value) => {
    const [hue, sat, bri] = hex2hsv(value);
    patch({ hue, sat, bri: Math.max(bri, MINB) });
  }, [patch]);

  const load = useCallback(async () => {
    const c = (await api("get_accent")) || DEFAULT;
    setSaved(c);
    setHex(c);
  }, [setHex]);

  const save = async () => {
    const ok = await api("save_accent", hex);
    if (ok !== false) setSaved(hex);
    setMsg(ok === false ? "Couldn't save file" : "Saved");
  };

  return {
    hex, ...hsv, patch, setHex, load, save,
    reset: () => setHex(DEFAULT),
    flag: setMsg,
    status: msg ?? (hex === saved ? "Saved" : "Unsaved changes"),
  };
}
