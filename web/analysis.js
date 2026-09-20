// Analysis tab: score distribution per task with sortable statistics, the three readings of the bounding-box
// tasks, and a what-if panel that recomputes scores with chosen questions left out. Everything follows the model
// chips. Per-question recomputation uses answers/<Task>.json and mirrors vladbench.per_question.

const VARIANTS = window.VARIANTS || { box_tasks: [], models: {} };
const analysis = { sort: "shift.mean", dir: -1, view: "both", whatIfTask: null, excluded: loadExcluded(), whatIfData: null, whatIfFilter: "hardest" };

function loadExcluded() {
  try { return JSON.parse(localStorage.getItem("vladbench-excluded") || "{}"); } catch { return {}; }
}
function saveExcluded() {
  try { localStorage.setItem("vladbench-excluded", JSON.stringify(analysis.excluded)); } catch { /* ignore */ }
}

// ---- 1. distribution per task, 2025 paper models against our 2026 runs -------------------------------

function featured() {
  return MODELS.filter((m) => m.featured !== false);
}

const PAPER_MODEL_LABEL = Object.fromEntries((PUBLISHED.models || []).map((m) => [m.id, `${m.abbreviation || m.label || m.id}${m.size_or_version ? " " + m.size_or_version : ""}`]));

function stats(values) {
  if (!values.length) return null;
  const sorted = values.slice().sort((a, b) => a - b);
  const mean = sorted.reduce((s, v) => s + v, 0) / sorted.length;
  const median = sorted.length % 2 ? sorted[(sorted.length - 1) / 2] : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  const sd = Math.sqrt(sorted.reduce((s, v) => s + (v - mean) ** 2, 0) / sorted.length);
  return { mean, median, sd, min: sorted[0], max: sorted[sorted.length - 1], spread: sorted[sorted.length - 1] - sorted[0], n: sorted.length };
}

function taskStats() {
  return TASKS.map((task) => {
    const now = featured().filter((m) => m.tasks[task.name]?.score != null).map((m) => ({ label: m.label, color: m.color, model: m, value: composite(m, task.name) }));
    const row = PAPER_TASKS.find((r) => r.task === task.name);
    const then = row ? Object.entries(row.scores).filter(([, v]) => v != null).map(([id, v]) => ({ label: PAPER_MODEL_LABEL[id] || id, value: v })) : [];
    if (!now.length && !then.length) return null;
    const s26 = stats(now.map((p) => p.value)), s25 = stats(then.map((p) => p.value));
    const shift = s26 && s25 ? { mean: s26.mean - s25.mean, median: s26.median - s25.median, sd: s26.sd - s25.sd } : { mean: 0, median: 0, sd: 0 };
    return { task, now, then, s26, s25, shift };
  }).filter(Boolean);
}

// Sort keys: "task", or "<series>.<stat>" with series 2025 | 2026 | shift.
function sortValue(row, key) {
  if (key === "task") return TASKS.indexOf(row.task);
  const [series, stat] = key.split(".");
  const source = series === "2025" ? row.s25 : series === "2026" ? row.s26 : row.shift;
  return source ? source[stat] : -Infinity;
}

function sortedStats() {
  const rows = taskStats();
  rows.sort((a, b) => sortValue(a, analysis.sort) - sortValue(b, analysis.sort));
  if (analysis.dir < 0) rows.reverse();
  return rows;
}

function renderDistribution() {
  const host = $("distribution");
  if (!host) return;
  host.replaceChildren();
  const view = analysis.view;   // both | 2026 | 2025
  const rows = sortedStats();
  const rowH = view === "both" ? 30 : 22, left = 210, plotW = 560, top = 30;
  const groups = view === "both" ? [["2025", "2025"], ["2026", "2026"], ["shift", "Δ 2026−2025"]] : [[view, view]];
  const colW = 46, groupGap = 14;
  const right = groups.length * (3 * colW + groupGap) + 20;
  const width = left + plotW + right, height = top + rows.length * rowH + 30;
  const x = (v) => left + (plotW * Math.max(0, Math.min(100, v))) / 100;
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Score distribution per task, 2025 paper models and 2026 runs", class: "dist-svg" });
  for (const v of [0, 25, 50, 75, 100]) {
    root.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: height - 24, class: "chart-grid" }),
                svg("text", { x: x(v), y: height - 8, class: "chart-tick", "text-anchor": "middle" }, v));
  }
  const header = (key, label, px, py, cls = "") => {
    const active = analysis.sort === key;
    const t = svg("text", { x: px, y: py, class: `dist-head ${cls}${active ? " on" : ""}`, role: "button", tabindex: 0 }, `${label}${active ? (analysis.dir > 0 ? " ▲" : " ▼") : ""}`);
    t.onclick = () => { if (analysis.sort === key) analysis.dir *= -1; else { analysis.sort = key; analysis.dir = 1; } renderDistribution(); };
    root.append(t);
  };
  header("task", "task", 8, top - 12);
  const colX = [];
  groups.forEach(([series, title], gi) => {
    const gx = left + plotW + 20 + gi * (3 * colW + groupGap);
    root.append(svg("text", { x: gx, y: top - 22, class: `dist-group ${series === "2025" ? "then" : series === "2026" ? "now" : ""}` }, title));
    ["mean", "median", "sd"].forEach((stat, si) => { header(`${series}.${stat}`, stat, gx + si * colW, top - 10); colX.push([series, stat, gx + si * colW]); });
  });
  const diamond = (cx, cy, cls) => svg("path", { d: `M${cx},${cy - 5} L${cx + 5},${cy} L${cx},${cy + 5} L${cx - 5},${cy} Z`, class: cls });
  rows.forEach((row, i) => {
    const y = top + i * rowH + rowH / 2;
    const label = svg("text", { x: left - 10, y: y + 4, class: "dist-label", "text-anchor": "end", role: "button", tabindex: 0 }, humanize(row.task.name));
    label.onclick = () => { location.hash = "matrix"; selectTask(row.task); };
    root.append(label);
    const lanes = view === "both" ? { "2025": y - 7, "2026": y + 7 } : { [view]: y };
    if (lanes["2025"] !== undefined && row.s25) {
      const ly = lanes["2025"];
      root.append(svg("rect", { x: x(row.s25.mean - row.s25.sd), y: ly - 5, width: x(row.s25.mean + row.s25.sd) - x(row.s25.mean - row.s25.sd), height: 10, class: "dist-band then" }));
      row.then.forEach((p) => { const d = svg("circle", { cx: x(p.value), cy: ly, r: 3, class: "dist-dot then" }); d.append(svg("title", {}, `${humanize(row.task.name)} · 2025 · ${p.label} · ${percent(p.value, 1)}`)); root.append(d); });
      root.append(svg("line", { x1: x(row.s25.median), x2: x(row.s25.median), y1: ly - 6, y2: ly + 6, class: "dist-median then" }), diamond(x(row.s25.mean), ly, "dist-mean then"));
    }
    if (lanes["2026"] !== undefined && row.s26) {
      const ly = lanes["2026"];
      root.append(svg("rect", { x: x(row.s26.mean - row.s26.sd), y: ly - 5, width: x(row.s26.mean + row.s26.sd) - x(row.s26.mean - row.s26.sd), height: 10, class: "dist-band" }));
      row.now.forEach((p) => {
        const d = svg("circle", { cx: x(p.value), cy: ly, r: 3.6, fill: p.color, class: "dist-dot", tabindex: 0, role: "button" });
        d.append(svg("title", {}, `${humanize(row.task.name)} · 2026 · ${p.label} · ${percent(p.value, 1)}`));
        d.onclick = () => { location.hash = "matrix"; selectTask(row.task, p.model); };
        root.append(d);
      });
      root.append(svg("line", { x1: x(row.s26.median), x2: x(row.s26.median), y1: ly - 6, y2: ly + 6, class: "dist-median" }), diamond(x(row.s26.mean), ly, "dist-mean"));
    }
    if (view === "both" && row.s25 && row.s26) {
      root.append(svg("line", { x1: x(row.s25.mean), x2: x(row.s26.mean), y1: y, y2: y, class: `dist-shift ${row.shift.mean >= 0 ? "up" : "down"}` }));
    }
    colX.forEach(([series, stat, px]) => {
      const source = series === "2025" ? row.s25 : series === "2026" ? row.s26 : row.shift;
      const v = source ? source[stat] : null;
      const text = v == null ? "—" : series === "shift" ? `${v >= 0 ? "+" : ""}${v.toFixed(1)}` : v.toFixed(1);
      const cls = series === "shift" ? (v > 0 ? "dist-num up" : v < 0 ? "dist-num down" : "dist-num") : series === "2025" ? "dist-num then" : "dist-num";
      root.append(svg("text", { x: px, y: y + 4, class: cls }, text));
    });
  });
  host.append(root);
  for (const button of document.querySelectorAll("[data-dist-view]")) button.setAttribute("aria-pressed", String(button.dataset.distView === view));
  const note = $("distribution-note");
  const n25 = rows.find((r) => r.s25)?.s25.n || 0;
  if (note) note.textContent = `2025: the ${n25} models in the paper's Table 10, amber. 2026: our ${featured().length} runs${MODELS.length > featured().length ? " without Reka Edge" : ""}, in model colours. Dots are models, the bar the median, the diamond the mean, the band one standard deviation either side; the connector joins the two means. Click a column header to sort, a task or dot to open it in Explore.`;
}

// ---- 2. the bounding-box tasks under three readings -------------------------------------------------

function renderBoxVariants() {
  const host = $("box-variants");
  if (!host) return;
  host.replaceChildren();
  const rows = featured().filter((m) => VARIANTS.models[m.id]).map((m) => ({ model: m, v: VARIANTS.models[m.id] }));
  if (!rows.length) { host.append(element("p", "No variant data for the models shown.", "sub")); return; }
  rows.sort((a, b) => b.v.total.pixels - a.v.total.pixels);
  const table = element("table", undefined, "frontier variants");
  const head = element("tr");
  ["Model", "Answers boxes in", "TOTAL · pixels (protocol)", "TOTAL · paper's rescale", "TOTAL · box tasks left out", ...VARIANTS.box_tasks.map((t) => `${humanize(t)} · pixels → rescale`)].forEach((h) => head.append(element("th", h)));
  const thead = element("thead"); thead.append(head); table.append(thead);
  const body = element("tbody");
  rows.forEach(({ model, v }) => {
    const tr = element("tr");
    const name = element("td");
    const swatch = element("i", undefined, "swatch"); swatch.style.background = model.color;
    name.append(swatch, document.createTextNode(` ${model.label}`));
    tr.append(name, element("td", v.convention === "grid" ? (v.y_first ? "0–1000 grid, y first" : "0–1000 grid") : "pixels"));
    const delta = (a, b) => { const d = b - a; return `${b.toFixed(1)} (${d >= 0 ? "+" : ""}${d.toFixed(1)})`; };
    tr.append(element("td", v.total.pixels.toFixed(1), "num strong"), element("td", delta(v.total.pixels, v.total.grid), "num"), element("td", delta(v.total.pixels, v.total.none), "num"));
    VARIANTS.box_tasks.forEach((t) => {
      const cell = element("td", `${v.tasks[t].pixels.toFixed(0)} → ${v.tasks[t].grid.toFixed(0)}`, "num");
      cell.title = `Box hits: ${((v.tasks[t].box_hits ?? v.tasks[t].accuracy) * 100).toFixed(0)}% · mean IoU ${v.tasks[t].mean_iou.toFixed(2)}`;
      tr.append(cell);
    });
    body.append(tr);
  });
  table.append(body);
  host.append(table);
}

// ---- 3. what-if: leave questions out --------------------------------------------------------------

function pairPartner(question, sampleSize) {
  const half = sampleSize / 2;
  return question.question <= half ? question.question + half : question.question - half;
}

// Task composite for one model from the per-question marks, with a set of positions excluded. Mirrors
// vladbench.per_question.components_from_marks; paired families drop the partner of an excluded question too.
function recompute(data, model, excluded) {
  const family = data.family;
  const sizes = {};
  data.questions.forEach((q) => { sizes[q.sample] = (sizes[q.sample] || 0) + 1; });
  const drop = new Set(excluded);
  if (["Relation_criterion_QA", "RoadChange_criterion_QA", "RoadSpeed_criterion_QA"].includes(family)) {
    for (const q of data.questions) {
      if (!drop.has(q.i)) continue;
      const partner = data.questions.find((p) => p.sample === q.sample && p.question === pairPartner(q, sizes[q.sample]));
      if (partner) drop.add(partner.i);
    }
  }
  const kept = data.questions.filter((q) => !drop.has(q.i) && q.answers[model.id]);
  if (!kept.length) return null;
  const marks = kept.map((q) => ({ kind: q.kind, acc: q.answers[model.id][1], instr: q.answers[model.id][2], other: q.answers[model.id][3], pair: q.answers[model.id][4] }));
  const n = marks.length;
  const mean = (xs) => (xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : 0);
  const instruction = mean(marks.map((m) => m.instr));
  let accuracy, other;
  if (family === "Grounding_criterion_QA") { accuracy = mean(marks.map((m) => m.acc)); other = mean(marks.filter((m) => m.kind === "box").map((m) => m.other || 0)); }
  else if (family === "Judge_criterion_QA") {
    const described = marks.filter((m) => m.kind === "description"), judged = marks.filter((m) => m.kind === "judgment");
    accuracy = described.length ? mean(described.map((m) => m.acc)) : 0; other = judged.length ? mean(judged.map((m) => m.acc)) : 0;
  } else if (["Relation_criterion_QA", "RoadChange_criterion_QA", "RoadSpeed_criterion_QA"].includes(family)) {
    accuracy = mean(marks.map((m) => m.acc)); other = marks.reduce((s, m) => s + (m.pair || 0), 0) * 2 / n;
  } else { accuracy = mean(marks.map((m) => m.acc)); other = 0; }
  const w = weightsFor(model.tasks[data.task]);
  return { score: 100 * (w.accuracy * accuracy + w.other * other + w.instruction_following * instruction), kept: n, dropped: drop.size };
}

function totalWith(model, task, newScore, newCount) {
  const pairs = TASKS.filter((t) => model.tasks[t.name]?.score != null)
    .map((t) => (t.name === task ? [newScore, newCount] : [composite(model, t.name), model.tasks[t.name].questions_scored]));
  return pairs.reduce((s, [v, w]) => s + v * w, 0) / pairs.reduce((s, [, w]) => s + w, 0);
}

function renderWhatIf() {
  const host = $("whatif");
  if (!host) return;
  host.replaceChildren();
  const picker = element("div", undefined, "row whatif-bar");
  const select = element("select", undefined, "grid-sort");
  const blank = element("option", "Choose a task…"); blank.value = ""; select.append(blank);
  TASKS.filter((t) => MODELS.some((m) => m.tasks[t.name]?.score != null)).forEach((t) => {
    const o = element("option", `${humanize(t.name)}${analysis.excluded[t.name]?.length ? ` · ${analysis.excluded[t.name].length} left out` : ""}`); o.value = t.name; o.selected = analysis.whatIfTask === t.name; select.append(o);
  });
  select.onchange = () => { analysis.whatIfTask = select.value || null; analysis.whatIfData = null; renderWhatIf(); };
  picker.append(select);
  const totalLeft = Object.values(analysis.excluded).reduce((s, v) => s + v.length, 0);
  if (totalLeft) {
    const clear = element("button", `Clear all ${totalLeft} exclusions`, "detail-button"); clear.type = "button";
    clear.onclick = () => { analysis.excluded = {}; saveExcluded(); analysis.whatIfData = null; renderWhatIf(); };
    const copy = element("button", "Copy exclusion list as JSON", "detail-button"); copy.type = "button";
    copy.onclick = () => navigator.clipboard.writeText(JSON.stringify(analysis.excluded, null, 2));
    picker.append(clear, copy);
  }
  host.append(picker);
  if (!analysis.whatIfTask) { host.append(element("p", "Pick a task, tick the questions whose reference answer you doubt, and every model's task score and TOTAL are recomputed without them. Exclusions stay in this browser until cleared.", "sub")); return; }
  const task = TASKS.find((t) => t.name === analysis.whatIfTask);
  const body = element("div"); host.append(body);
  body.append(element("p", "Loading answers…", "sub"));
  loadAnswers(task).then((data) => { analysis.whatIfData = data; paintWhatIf(task, data, body); })
    .catch(() => body.replaceChildren(element("p", "Per-question answers could not be loaded.", "sub")));
}

function paintWhatIf(task, data, body) {
  body.replaceChildren();
  const excluded = new Set(analysis.excluded[task.name] || []);
  const models = MODELS.filter((m) => data.models.includes(m.id));

  // Effect table first: original vs recomputed per model.
  const table = element("table", undefined, "frontier whatif-table");
  const head = element("tr");
  ["Model", "Task score", "Without excluded", "Δ task", "TOTAL", "TOTAL without", "Δ TOTAL"].forEach((h) => head.append(element("th", h)));
  const thead = element("thead"); thead.append(head); table.append(thead);
  const tb = element("tbody");
  models.forEach((m) => {
    const before = composite(m, task.name), rc = recompute(data, m, excluded);
    const after = rc ? rc.score : before;
    const tBefore = modelMean(m), tAfter = rc ? totalWith(m, task.name, after, rc.kept) : tBefore;
    const tr = element("tr");
    const name = element("td"); const sw = element("i", undefined, "swatch"); sw.style.background = m.color; name.append(sw, document.createTextNode(` ${m.label}`));
    const d = (a, b) => { const v = b - a; const cell = element("td", `${v >= 0 ? "+" : ""}${v.toFixed(2)}`, "num"); cell.style.color = Math.abs(v) < 0.005 ? "var(--muted)" : v > 0 ? "var(--good)" : "#ff6b6b"; return cell; };
    tr.append(name, element("td", before.toFixed(1), "num"), element("td", after.toFixed(1), "num strong"), d(before, after), element("td", tBefore.toFixed(1), "num"), element("td", tAfter.toFixed(1), "num strong"), d(tBefore, tAfter));
    tb.append(tr);
  });
  table.append(tb);
  const summary = element("p", `${excluded.size} of ${data.questions.length} questions left out${["Relation_criterion_QA", "RoadChange_criterion_QA", "RoadSpeed_criterion_QA"].includes(data.family) ? " (a paired task: the partner of each excluded question is left out with it)" : ""}.`, "sub");
  body.append(summary, table);

  // Then the question list with checkboxes, hardest first so doubtful references surface.
  const bar = element("div", undefined, "grid-bar");
  const pills = element("div", undefined, "grid-pills");
  [["hardest", "Hardest first"], ["excluded", "Excluded only"], ["dataset", "Dataset order"]].forEach(([key, label]) => {
    const b = element("button", label, "pill" + (analysis.whatIfFilter === key ? " on" : "")); b.type = "button";
    b.onclick = () => { analysis.whatIfFilter = key; paintWhatIf(task, data, body); };
    pills.append(b);
  });
  bar.append(pills);
  body.append(bar);
  let rows = data.questions.map((q) => ({ q, right: models.filter((m) => q.answers[m.id]?.[1] >= 1).length }));
  if (analysis.whatIfFilter === "excluded") rows = rows.filter((r) => excluded.has(r.q.i));
  if (analysis.whatIfFilter !== "dataset") rows.sort((a, b) => a.right - b.right || a.q.i - b.q.i);
  const scroller = element("div", undefined, "grid-scroll");
  const grid = element("table", undefined, "answer-grid whatif-grid");
  grid.style.minWidth = `${40 + 56 + 260 + 110 + 84 * models.length}px`;
  const gh = element("tr");
  ["Leave out", "", "Question", "Reference", ...models.map((m) => m.label)].forEach((h) => gh.append(element("th", h)));
  const gthead = element("thead"); gthead.append(gh); grid.append(gthead);
  const gb = element("tbody");
  rows.slice(0, 120).forEach(({ q, right }) => {
    const tr = element("tr", undefined, excluded.has(q.i) ? "excluded" : undefined);
    const box = element("td"); const cb = element("input"); cb.type = "checkbox"; cb.checked = excluded.has(q.i);
    cb.onchange = () => {
      const list = new Set(analysis.excluded[task.name] || []);
      if (cb.checked) list.add(q.i); else list.delete(q.i);
      analysis.excluded[task.name] = [...list].sort((a, b) => a - b);
      if (!analysis.excluded[task.name].length) delete analysis.excluded[task.name];
      saveExcluded(); paintWhatIf(task, data, body);
    };
    box.append(cb);
    const thumb = element("td", undefined, "thumb"); const img = element("img"); img.loading = "lazy"; img.src = data.base + q.images[0]; img.alt = ""; thumb.append(img);
    const text = element("td", undefined, "qtext");
    text.append(element("span", shortPrompt(q.prompt), "ans-text"), element("span", `${q.sequence || q.sample} · q${q.question} · ${right}/${models.length} right`, "sub"));
    text.title = q.prompt;
    text.onclick = () => inspectQuestion(task, { ...q, images: q.images.map((p) => ({ path: data.base + p })), id: q.sample }, null);
    const gold = element("td", goldText(q.gold), "gold"); gold.title = goldText(q.gold);
    tr.append(box, thumb, text, gold);
    models.forEach((m) => tr.append(markCell(q.answers[m.id], q.kind)));
    gb.append(tr);
  });
  grid.append(gb);
  scroller.append(grid);
  body.append(scroller);
  if (rows.length > 120) body.append(element("p", `Showing the first 120 of ${rows.length}. Use Explore for the full grid.`, "sub"));
}

function renderAnalysis() {
  renderDistribution();
  renderBoxVariants();
  renderSuspect();
  renderCutinWording();
  renderWhatIf();
}

for (const button of document.querySelectorAll("[data-dist-view]")) {
  button.addEventListener("click", () => { analysis.view = button.dataset.distView; renderDistribution(); });
}
// renderAnalysis() is called at the very end of this file, after every constant it needs exists.


// ---- 4. suspect references: accuracy by reference label ------------------------------------------

// Tasks whose reference answers deserve a second look, with what the audit found.
const SUSPECT_NOTES = {
  Vehicle_Cutin: "172 of the 174 yes/no references are \"yes\". Answering \"yes\" to every question would score 99% on the judgment component; the models say yes between 7% and 39% of the time, and each model's judgment accuracy equals its yes rate. The question asks whether a vehicle has \"the intention to cross the road\", which reads as odd for a vehicle. See the wording review below.",
  VRU_Cross: "88 of 92 yes/no references are \"yes\". The descriptive references mix \"jaywalking\" (40) with \"cross the crosswalk\" (27), so the same behaviour is labelled two ways depending on the clip.",
  Light: "Seven clips carry the reference \"dawn&dusk\" next to 51 \"daytime\" and 42 \"nighttime\". The second question's lighting labels (\"backlit\", \"diffuse\", \"shadowed light\") are judgment calls that the frames do not always settle.",
  Weather: "Five weather labels, with \"cloudy\" (7) and \"overcast\" (30) both present; the distinction is not one a single frame supports well.",
  Long_Short_Parking: "The reason labels overlap: \"Parking\", \"Temporary parking\", and \"Waiting to start\" describe the same stopped vehicle at different moments.",
};

function renderSuspect() {
  const host = $("suspect");
  if (!host) return;
  host.replaceChildren();
  const bar = element("div", undefined, "row whatif-bar");
  const select = element("select", undefined, "grid-sort");
  const tasks = TASKS.filter((t) => MODELS.some((m) => m.tasks[t.name]?.score != null));
  const suspects = tasks.filter((t) => SUSPECT_NOTES[t.name]), others = tasks.filter((t) => !SUSPECT_NOTES[t.name]);
  const group = (label, list) => { const g = element("optgroup"); g.label = label; list.forEach((t) => { const o = element("option", humanize(t.name)); o.value = t.name; o.selected = analysis.suspectTask === t.name; g.append(o); }); select.append(g); };
  group("Flagged in the audit", suspects); group("Every other task", others);
  if (!analysis.suspectTask) analysis.suspectTask = suspects.find((t) => t.name === "Vehicle_Cutin")?.name || suspects[0]?.name || tasks[0]?.name;
  select.value = analysis.suspectTask;
  select.onchange = () => { analysis.suspectTask = select.value; renderSuspect(); };
  bar.append(select);
  host.append(bar);
  const task = tasks.find((t) => t.name === analysis.suspectTask);
  if (!task) return;
  if (SUSPECT_NOTES[task.name]) host.append(element("p", SUSPECT_NOTES[task.name], "suspect-note"));
  const body = element("div"); host.append(body);
  body.append(element("p", "Loading answers…", "sub"));
  loadAnswers(task).then((data) => paintSuspect(task, data, body)).catch(() => body.replaceChildren(element("p", "Per-question answers could not be loaded.", "sub")));
}

function paintSuspect(task, data, body) {
  body.replaceChildren();
  const models = featured().filter((m) => data.models.includes(m.id));
  const groups = new Map();
  for (const q of data.questions) {
    const key = `${q.kind}::${goldText(q.gold)}`;
    if (!groups.has(key)) groups.set(key, { kind: q.kind, gold: goldText(q.gold), questions: [] });
    groups.get(key).questions.push(q);
  }
  const rows = [...groups.values()].filter((g) => g.kind !== "box").sort((a, b) => b.questions.length - a.questions.length);
  const table = element("table", undefined, "frontier suspect-table");
  const head = element("tr");
  ["Reference answer", "Kind", "Questions", "Best model", ...models.map((m) => m.label)].forEach((h) => head.append(element("th", h)));
  const thead = element("thead"); thead.append(head); table.append(thead);
  const tb = element("tbody");
  rows.forEach((g) => {
    const tr = element("tr");
    const acc = models.map((m) => { const marks = g.questions.map((q) => q.answers[m.id]?.[1]).filter((v) => v != null); return marks.length ? marks.reduce((s, v) => s + v, 0) / marks.length : null; });
    const best = Math.max(...acc.filter((v) => v != null));
    if (best === 0) tr.classList.add("nobody");
    tr.append(element("td", g.gold, "gold"), element("td", g.kind), element("td", g.questions.length, "num"), element("td", best === 0 ? "nobody" : percent(100 * best, 0), "num"));
    acc.forEach((v) => { const cell = element("td", v == null ? "—" : percent(100 * v, 0), "num"); if (v != null) { const { background, ink } = heatColor(100 * v); cell.style.background = background; cell.style.color = ink; } tr.append(cell); });
    tr.onclick = () => { analysis.whatIfTask = task.name; analysis.whatIfFilter = "dataset"; renderWhatIf(); document.querySelector(".whatif-panel")?.scrollIntoView({ behavior: "smooth" }); };
    tb.append(tr);
  });
  table.append(tb);
  const dead = rows.filter((g) => models.every((m) => g.questions.every((q) => !q.answers[m.id]?.[1])));
  const scroll = element("div", undefined, "table-scroll");
  scroll.append(table);
  body.append(element("p", `${rows.length} distinct reference answers${dead.length ? `; ${dead.length} that no model ever matched, marked in red` : ""}. Cells are each model's accuracy on the questions carrying that reference. Click a row to open the task in the what-if panel.`, "sub"), scroll);
}

// ---- 5. the cut-in wording review ----------------------------------------------------------------

// From the earlier Vehicle Cut-in survey (VLADBench-cutin-survey, 260 shared questions, its own runner, before the
// protocol). Official wording asks whether the vehicle has "the intention to cross the road"; the reworded run asks
// whether it "intend[s] to cut in (enter or cross into the ego vehicle's path)". Same references, same scorer.
const CUTIN_SURVEY = [
  { model: "Qwen 3.6 35B A3B FP8", reasoning: "off", official: { score: 43.52, judgment: 31.6 }, reworded: { score: 71.10, judgment: 71.8 } },
  { model: "Qwen 3.6 35B A3B", reasoning: "off", official: { score: 42.03, judgment: 29.3 }, reworded: { score: 66.56, judgment: 65.5 } },
  { model: "GPT-6 Astra", reasoning: "low", official: { score: 40.66, judgment: 25.9 }, reworded: { score: 58.47, judgment: 52.3 } },
  { model: "Gemini 3.8 Flash", reasoning: "on", official: { score: 33.15, judgment: 15.5 }, reworded: { score: 34.66, judgment: 18.4 } },
];

function renderCutinWording() {
  const host = $("cutin-wording");
  if (!host) return;
  host.replaceChildren();
  const width = 900, rowH = 44, left = 230, plotW = 560, top = 34;
  const height = top + CUTIN_SURVEY.length * rowH + 52;
  const x = (v) => left + (plotW * v) / 100;
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Vehicle cut-in judgment accuracy under the official and reworded prompts", class: "dist-svg" });
  for (const v of [0, 25, 50, 75, 100]) root.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: height - 46, class: "chart-grid" }), svg("text", { x: x(v), y: height - 32, class: "chart-tick", "text-anchor": "middle" }, v));
  root.append(svg("text", { x: left, y: top - 14, class: "dist-group" }, "Judgment accuracy, % of yes/no questions right"));
  root.append(svg("text", { x: left + plotW + 10, y: top - 14, class: "dist-group" }, "task score"));
  CUTIN_SURVEY.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2;
    root.append(svg("text", { x: left - 10, y: y - 2, class: "dist-label", "text-anchor": "end" }, r.model), svg("text", { x: left - 10, y: y + 12, class: "chart-tick", "text-anchor": "end" }, `reasoning ${r.reasoning}`));
    root.append(svg("line", { x1: x(r.official.judgment), x2: x(r.reworded.judgment), y1: y, y2: y, class: "cutin-link" }));
    const a = svg("circle", { cx: x(r.official.judgment), cy: y, r: 7, class: "cutin-dot official" }); a.append(svg("title", {}, `official wording · ${r.official.judgment}%`));
    const b = svg("circle", { cx: x(r.reworded.judgment), cy: y, r: 7, class: "cutin-dot reworded" }); b.append(svg("title", {}, `reworded · ${r.reworded.judgment}%`));
    root.append(a, b);
    root.append(svg("text", { x: x(r.reworded.judgment) + 12, y: y + 4, class: "dist-num" }, `+${(r.reworded.judgment - r.official.judgment).toFixed(1)}`));
    root.append(svg("text", { x: left + plotW + 10, y: y + 4, class: "dist-num" }, `${r.official.score.toFixed(1)} → ${r.reworded.score.toFixed(1)}`));
  });
  root.append(svg("circle", { cx: left, cy: height - 8, r: 5, class: "cutin-dot official" }), svg("text", { x: left + 10, y: height - 4, class: "cutin-legend", "text-anchor": "start" }, "official: \"the intention to cross the road\""),
              svg("circle", { cx: left + 290, cy: height - 8, r: 5, class: "cutin-dot reworded" }), svg("text", { x: left + 300, y: height - 4, class: "cutin-legend", "text-anchor": "start" }, "reworded: \"intend to cut in (enter or cross into the ego vehicle's path)\""));
  host.append(root);
}

renderAnalysis();
