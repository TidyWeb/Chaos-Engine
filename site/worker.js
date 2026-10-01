// Runs Python (Pyodide) off the main thread so the page never freezes.
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

let py = null;
let excelReady = null;

async function boot() {
  py = await loadPyodide();
  await py.loadPackage(["numpy", "pandas"]);
  const zip = await (await fetch("chaos.zip")).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide" });
  const api = await (await fetch("web_api.py")).text();
  py.FS.writeFile("/home/pyodide/web_api.py", api);
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide'); import web_api");
  self.postMessage({ type: "ready" });
}

function needExcel() {
  if (!excelReady) {
    excelReady = (async () => {
      await py.loadPackage("micropip");
      await py.pyimport("micropip").install("openpyxl");
    })();
  }
  return excelReady;
}

const ready = boot().catch((err) => self.postMessage({ type: "failed", error: String(err) }));

self.onmessage = async (event) => {
  const { id, fn, args } = event.data;
  try {
    await ready;
    if (fn === "make_xlsx" || (fn === "load" && /\.xls[xm]$/i.test(args[0]))) await needExcel();
    let out = py.pyimport("web_api")[fn](...args);
    if (out && out.toJs) { const js = out.toJs(); out.destroy(); out = js; }   // bytes -> Uint8Array
    self.postMessage({ id, ok: true, result: out });
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err) });
  }
};
