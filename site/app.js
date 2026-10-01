// Chaos Engine page. All the real work is Python (chaos/ + web_api.py) running in worker.js.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ROLE_BADGE = { integer: ["num", "INT"], decimal: ["num", "DEC"], date: ["date", "DATE"], bool: ["bool", "BOOL"],
  id: ["id", "ID"], email: ["text", "EMAIL"], category: ["text", "CAT"], text: ["text", "TEXT"], empty: ["text", "EMPTY"] };
const ROLES = ["id", "integer", "decimal", "date", "bool", "email", "category", "text", "empty"];
const PROBLEMS = {
  missing_value: "Missing values", number_stored_as_text: "Numbers stored as text", date_format: "Mixed date formats",
  invalid_date: "Impossible dates", inconsistent_case: "Inconsistent capitals", stray_spaces: "Stray spaces", typo: "Typos",
  invalid_email: "Broken email addresses", mixed_boolean: "Mixed yes/no styles", outlier: "Outliers",
  duplicate_row: "Exact duplicate rows", near_duplicate_row: "Near-duplicate rows", conflicting_duplicate_id: "Same ID, different values",
  repeated_header_row: "Repeated header row", blank_row: "Blank rows", messy_header: "Messy column names" };
const label = (p) => PROBLEMS[p] || p.replace(/_/g, " ");

const EMPTY = $("grid").innerHTML;
const FLAME = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12.6 1.8c.9 3.3-.9 5-2.5 7-1.6 2-2.7 3.6-2.7 6.1a5.2 5.2 0 0 0 10.4 0c0-2.2-1-3.8-2.2-5-.3 1.2-1 1.9-1.8 2.2.7-3.5-.2-7.1-1.2-10.3z"/></svg>';
const state = { raw: null, name: "", loaded: null, chaos: null, view: "chaos", intensity: "realistic", overrides: {}, ready: false, busy: false };

// ---- worker ----------------------------------------------------------------------------------
const worker = new Worker("worker.js", { type: "module" });
let nextId = 1;
const waiting = new Map();
worker.onmessage = (event) => {
  const m = event.data;
  if (m.type === "ready") { state.ready = true; setStatus(""); refresh(); return; }
  if (m.type === "failed") { setStatus("The Python engine could not start: " + m.error, true); return; }
  const w = waiting.get(m.id);
  if (w) { waiting.delete(m.id); m.ok ? w.resolve(m.result) : w.reject(new Error(m.error)); }
};
const py = (fn, args = []) => new Promise((resolve, reject) => {
  const id = nextId++;
  waiting.set(id, { resolve, reject });
  worker.postMessage({ id, fn, args });
});
setStatus("Starting the Python engine (first visit downloads about 15 MB)...");

function setStatus(text, bad) {
  $("msg").innerHTML = text ? `<div class="${bad ? "err" : "status"}">${esc(text)}</div>` : "";
}
function busy(on) { state.busy = on; document.body.classList.toggle("busy-cursor", on); refresh(); }

// ---- loading a file --------------------------------------------------------------------------
async function loadFile(name, bytes, sheet = "") {
  state.raw = bytes; state.name = name; state.chaos = null; state.overrides = {};
  setStatus("Reading " + name + "...");
  busy(true);
  try {
    const r = JSON.parse(await py("load", [name, bytes, sheet]));
    if (!r.ok) { state.loaded = null; setStatus(r.error, true); render(); return; }
    state.loaded = r; state.view = "original"; setStatus("");
  } catch (e) { setStatus("Something went wrong reading this file: " + e.message, true); }
  finally { busy(false); }
  render();
}
async function pickFile(file) {
  if (!file) return;
  const bytes = new Uint8Array(await file.arrayBuffer());
  await loadFile(file.name, bytes);
}
$("file").onchange = (e) => pickFile(e.target.files[0]);
const drop = $("drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => pickFile(e.dataTransfer.files[0]));
$("sheet").onchange = () => loadFile(state.name, state.raw, $("sheet").value);
$("sample").onclick = () => {
  const cities = ["Leeds", "York", "Bristol", "Cardiff", "Glasgow", "Norwich"], first = ["Ann", "Ben", "Cara", "Dev", "Elif"], last = ["Smith", "Jones", "Patel", "Okafor"];
  let s = 17; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const rows = ["customer_id,full_name,email,city,signup_date,order_total,items,is_member"];
  for (let i = 0; i < 60; i++) {
    const d = new Date(Date.UTC(2024, 0, 1) + Math.floor(rnd() * 600) * 86400000).toISOString().slice(0, 10);
    rows.push([1000 + i, first[Math.floor(rnd() * 5)] + " " + last[Math.floor(rnd() * 4)], `user${i}@example.com`, cities[Math.floor(rnd() * 6)],
      d, (5 + rnd() * 400).toFixed(2), 1 + Math.floor(rnd() * 9), rnd() < 0.5 ? "Yes" : "No"].join(","));
  }
  loadFile("sample_customers.csv", new TextEncoder().encode(rows.join("\n")));
};

// ---- chaos -----------------------------------------------------------------------------------
$("intensity").onclick = (e) => {
  const b = e.target.closest("button"); if (!b) return;
  state.intensity = b.dataset.v;
  [...$("intensity").children].forEach((x) => x.classList.toggle("on", x === b));
};
$("go").onclick = async () => {
  if (!state.loaded) return;
  setStatus("Creating chaos...");
  busy(true);
  try {
    const seed = $("seed").value.trim();
    const r = JSON.parse(await py("chaos", [seed, state.intensity, JSON.stringify(state.overrides)]));
    if (!r.ok) { setStatus(r.error, true); return; }
    state.chaos = r; state.view = "chaos"; setStatus("");
  } catch (e) { setStatus("Something went wrong creating chaos: " + e.message, true); }
  finally { busy(false); }
  render();
};
$("view").onclick = (e) => {
  const b = e.target.closest("button"); if (!b || !state.chaos) return;
  state.view = b.dataset.v; render();
};

// ---- downloads -------------------------------------------------------------------------------
function save(name, bytes, type) {
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
}
async function download(fn, name, type, note) {
  busy(true);
  if (note) setStatus(note);
  try { save(name, await py(fn), type); setStatus(""); }
  catch (e) { setStatus("Download failed: " + e.message, true); }
  finally { busy(false); }
}
$("dl-csv").onclick = () => download("make_csv", state.chaos.csv_name, "text/csv");
$("dl-key").onclick = () => download("make_key", state.chaos.key_name, "text/csv");
$("dl-xlsx").onclick = () => download("make_xlsx", state.chaos.xlsx_name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Building the Excel file (first time loads an extra library)...");

// ---- drawing ---------------------------------------------------------------------------------
function roleOf(i) {
  const p = state.loaded.profile[i];
  return state.overrides[p.name] || p.role;
}
function drawTable() {
  const L = state.loaded, C = state.chaos, showChaos = C && state.view === "chaos";
  const columns = showChaos ? C.columns : L.columns, rows = showChaos ? C.rows : L.rows;
  const total = showChaos ? C.total : L.total;
  const head = columns.map((c, i) => {
    const [cls, txt] = ROLE_BADGE[roleOf(i)] || ROLE_BADGE.text;
    const hm = showChaos && C.header_marks[i];
    return `<th class="${hm ? "hit" : ""}" ${hm ? `data-tip="${esc(label(hm.problem))}&#10;Original name: ${esc(hm.was)}"` : ""}><span class="n">${esc(c)}</span><span class="t ${cls}">${txt}</span></th>`;
  }).join("");
  const body = rows.map((r, ri) => {
    const rm = showChaos && C.row_marks[ri];
    return `<tr class="${rm ? "rowfault" : ""}" ${rm ? `data-tip="${esc(label(rm.problem))}&#10;${esc(rm.note)}"` : ""}><td class="idx">${ri + 1}</td>` +
      r.map((v, ci) => {
        const m = showChaos && C.marks[ri + "," + ci];
        const shown = v === "" ? "(blank)" : v;
        return `<td class="${v === "" ? "empty " : ""}${m ? "hit" : ""}" ${m ? `data-tip="${esc(label(m.problem))}&#10;Original: ${m.was === "" ? "(blank)" : esc(m.was)}"` : ""}>${esc(shown)}</td>`;
      }).join("") + "</tr>";
  }).join("");
  $("grid").innerHTML = `<table><thead><tr><th class="idx"></th>${head}</tr></thead><tbody>${body}</tbody></table>`;
  $("hint").textContent = (rows.length < total ? `Showing the first ${rows.length} of ${total.toLocaleString()} rows. Downloads contain every row. ` : "") +
    (showChaos ? "Highlighted cells were changed; tinted rows were added. Hover for details." : "");
}
function drawColumns() {
  const P = state.loaded.profile;
  $("cols").innerHTML = P.map((p, i) => `<div class="c"><b title="${esc(p.name)}">${esc(p.name)}</b>
    <select data-i="${i}">${ROLES.map((r) => `<option value="${r}" ${r === roleOf(i) ? "selected" : ""}>${r}</option>`).join("")}</select>
    ${p.already_messy ? `<div class="already">Already has ${p.marker_cells} missing-value markers</div>` : ""}</div>`).join("");
  $("cols").querySelectorAll("select").forEach((s) => s.onchange = () => {
    const p = P[+s.dataset.i];
    if (s.value === p.role) delete state.overrides[p.name]; else state.overrides[p.name] = s.value;
    if (state.chaos) { state.chaos = null; state.view = "original"; }   // the old result no longer matches the settings
    render();
  });
}
function render() {
  const L = state.loaded, C = state.chaos;
  $("colbox").hidden = !L; $("sumbox").hidden = !C; $("viewbar").hidden = !C; $("actions").hidden = !L;
  $("snip").hidden = !C;
  if (!L) {
    $("title").textContent = "No file yet"; $("sub").textContent = ""; $("chips").innerHTML = ""; $("fileinfo").innerHTML = ""; $("sheetbox").hidden = true; $("grid").innerHTML = EMPTY; $("hint").textContent = "";
    refresh(); return;
  }
  const i = L.info;
  $("fileinfo").innerHTML = `<strong>${esc(i.file)}</strong><br>${L.total.toLocaleString()} rows &times; ${L.columns.length} columns` +
    (i.format === "text" ? `<br>${i.encoding}, delimiter ${i.delimiter === "\t" ? "tab" : "&ldquo;" + esc(i.delimiter) + "&rdquo;"}` : "") +
    (i.warnings.length ? `<br><span style="color:var(--warn-ink)">${esc(i.warnings.join(" "))}</span>` : "");
  $("sheetbox").hidden = i.sheets.length < 2;
  if (i.sheets.length > 1) $("sheet").innerHTML = i.sheets.map((s) => `<option ${s === i.sheet ? "selected" : ""}>${esc(s)}</option>`).join("");
  $("title").textContent = C ? "Chaos created" : i.file;
  $("sub").textContent = C ? `${C.changes.toLocaleString()} changes made. The answer key lists every one.` : "Original file, unchanged. Next: press the big orange Create Chaos button on the right.";
  $("chips").innerHTML = `<span class="chip">${(C && state.view === "chaos" ? C.total : L.total).toLocaleString()} rows</span><span class="chip">${L.columns.length} cols</span>` + (C ? `<span class="chip">seed ${C.seed}</span>` : "");
  if (C) {
    $("sum").innerHTML = Object.entries(C.summary).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div><span>${esc(label(k))}</span><span>${v}</span></div>`).join("");
    $("snip").textContent = `pd.read_csv("${C.csv_name}")`;
    $("legend").innerHTML = `<i></i>changed cell &nbsp; <i class="r"></i>added row`;
    [...$("view").children].forEach((b) => b.classList.toggle("on", b.dataset.v === state.view));
  }
  drawColumns(); drawTable(); refresh();
}
function refresh() {
  const can = state.ready && !state.busy;
  $("go").disabled = !(can && state.loaded);
  ["dl-csv", "dl-xlsx", "dl-key"].forEach((id) => $(id).disabled = !(can && state.chaos));
  $("file").disabled = !can; $("sample").disabled = !can;
  $("go").innerHTML = FLAME + (state.busy ? "<span class=\"lbl\">Working&hellip;</span>" : "<span class=\"lbl\">Create<br>Chaos</span>");
  $("dlhint").textContent = state.chaos ? "" : "(available after you create chaos)";
}
render();

// ---- instant tooltip for changed cells (the browser's own title tooltip is slow and easy to miss) -----
const tip = document.body.appendChild(Object.assign(document.createElement("div"), { className: "tip", hidden: true }));
$("grid").addEventListener("mouseover", (e) => {
  const t = e.target.closest("[data-tip]");
  if (!t) { tip.hidden = true; return; }
  tip.innerHTML = esc(t.dataset.tip).replace(/\n/g, "<br>");
  tip.hidden = false;
});
$("grid").addEventListener("mousemove", (e) => {
  if (tip.hidden) return;
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + "px"; tip.style.top = (e.clientY + 18) + "px";
});
$("grid").addEventListener("mouseleave", () => { tip.hidden = true; });

// ---- side panel show/hide (remembered for next visit) -------------------------------------------
try { if (localStorage.getItem("chaos-side") === "closed") document.body.classList.add("side-closed"); } catch (e) {}
$("toggleside").onclick = () => {
  const closed = document.body.classList.toggle("side-closed");
  try { localStorage.setItem("chaos-side", closed ? "closed" : "open"); } catch (e) {}
};


// Light / dark toggle. Follows the system until the user picks; the choice is remembered.
(function () {
  const btn = document.getElementById("theme");
  const root = document.documentElement;
  const dark = () => root.dataset.theme
    ? root.dataset.theme === "dark"
    : window.matchMedia("(prefers-color-scheme: dark)").matches;
  const label = () => { btn.textContent = dark() ? "\u2600 Light" : "\u263E Dark"; };
  btn.addEventListener("click", () => {
    const next = dark() ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("ce-theme", next); } catch (e) {}
    label();
  });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", label);
  label();
})();
