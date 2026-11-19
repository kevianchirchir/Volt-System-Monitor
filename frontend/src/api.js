import { mockApi } from "./mock.js";

// Bridge to the Python side (pywebview). Outside pywebview it resolves null,
// except in `npm run dev`, where fake stats are served so the UI is previewable.
export const api = (method, ...args) => {
  if (window.pywebview) return window.pywebview.api[method](...args);
  return Promise.resolve(import.meta.env.DEV ? mockApi(method) : null);
};
