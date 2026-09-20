// Analysis tab: score distribution per task with sortable statistics, the three readings of the bounding-box
// tasks, and a what-if panel that recomputes scores with chosen questions left out. Everything follows the model
// chips. Per-question recomputation uses answers/<Task>.json and mirrors vladbench.per_question.

const VARIANTS = window.VARIANTS || { box_tasks: [], models: {} };
const analysis = { sort: "mean", dir: 1, whatIfTask: null, excluded: loadExcluded(), whatIfData: null, whatIfFilter: "hardest" };

function loadExcluded() {
  try { return JSON.parse(localStorage.getItem("vladbench-excluded") || "{}"); } catch { return {}; }
}
function saveExcluded() {
  try { localStorage.setItem("vladbench-excluded", JSON.stringify(analysis.excluded)); } catch { /* ignore */ }
}

// ---- 1. distribution per task ----------------------------------------------------------------------

function featured() {
  return MODELS.filter((m) => m.featured !== false);
}

function taskStats() {
  return TASKS.map((task) => {
    const points = featured().filter((m) => m.tasks[task.name]?.score != null).map((m) => ({ model: m, value: composite(m, task.name) }));
    if (!points.length) return null;
    const values = points.map((p) => p.value).sort((a, b) => a - b);
    const mean = values.reduce((s, v) => s + v, 0) / values.length;
    const median = values.length % 2 ? values[(values.length - 1) / 2] : (values[values.length / 2 - 1] + values[values.length / 2]) / 2;
    const sd = Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length);
    return { task, points, mean, median, sd, min: values[0], max: values[values.length - 1], spread: values[values.length - 1] - values[0] };
  }).filter(Boolean);
}

function sortedStats() {
  const rows = taskStats();
  const key = analysis.sort;
  if (key === "task") rows.sort((a, b) => TASKS.indexOf(a.task) - TASKS.indexOf(b.task));
  else rows.sort((a, b) => a[key] - b[key]);
  if (analysis.dir < 0) rows.reverse();
  return rows;
}

function renderDistribution() {
  const host = $("distribution");
  if (!host) return;
  host.replaceChildren();
  const rows = sortedStats();
  const rowH = 22, left = 210, right = 250, plotW = 620, top = 26;
  const width = left + plotW + right, height = top + rows.length * rowH + 30;
  const x = (v) => left + (plotW * v) / 100;
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Score distribution per task across the models shown", class: "dist-svg" });
  for (const v of [0, 25, 50, 75, 100]) {
    root.append(svg("line", { x1: x(v), x2: x(v), y1: top - 6, y2: height - 24, class: "chart-grid" }),
                svg("text", { x: x(v), y: height - 8, class: "chart-tick", "text-anchor": "middle" }, v));
  }
  // Column headers double as sort controls.
  const columns = [["mean", "mean", 0], ["median", "median", 60], ["sd", "sd", 120], ["spread", "spread", 175]];
  columns.forEach(([key, label, dx]) => {
    const active = analysis.sort === key;
    const t = svg("text", { x: left + plotW + 16 + dx, y: top - 10, class: `dist-head${active ? " on" : ""}`, role: "button", tabindex: 0 }, `${label}${active ? (analysis.dir > 0 ? " ▲" : " ▼") : ""}`);
    t.onclick = () => { if (analysis.sort === key) analysis.dir *= -1; else { analysis.sort = key; analysis.dir = 1; } renderDistribution(); };
    root.append(t);
  });
  const byTask = svg("text", { x: 8, y: top - 10, class: `dist-head${analysis.sort === "task" ? " on" : ""}`, role: "button", tabindex: 0 }, `task${analysis.sort === "task" ? (analysis.dir > 0 ? " ▲" : " ▼") : ""}`);
  byTask.onclick = () => { if (analysis.sort === "task") analysis.dir *= -1; else { analysis.sort = "task"; analysis.dir = 1; } renderDistribution(); };
  root.append(byTask);

  rows.forEach((row, i) => {
    const y = top + i * rowH + rowH / 2;
    const label = svg("text", { x: left - 10, y: y + 4, class: "dist-label", "text-anchor": "end", role: "button", tabindex: 0 }, humanize(row.task.name));
    label.onclick = () => { location.hash = "matrix"; selectTask(row.task); };
    root.append(label);
    root.append(svg("rect", { x: x(Math.max(0, row.mean - row.sd)), y: y - 7, width: x(Math.min(100, row.mean + row.sd)) - x(Math.max(0, row.mean - row.sd)), height: 14, class: "dist-band" }));
    row.points.forEach((p) => {
      const dot = svg("circle", { cx: x(p.value), cy: y, r: 4.2, fill: p.model.color, class: "dist-dot", tabindex: 0, role: "button", "aria-label": `${p.model.label} ${percent(p.value, 1)}` });
      dot.append(svg("title", {}, `${humanize(row.task.name)} · ${p.model.label} · ${percent(p.value, 1)}`));
      dot.onclick = () => { location.hash = "matrix"; selectTask(row.task, p.model); };
      root.append(dot);
    });
    root.append(svg("line", { x1: x(row.median), x2: x(row.median), y1: y - 8, y2: y + 8, class: "dist-median" }));
    root.append(svg("path", { d: `M${x(row.mean)},${y - 5} L${x(row.mean) + 5},${y} L${x(row.mean)},${y + 5} L${x(row.mean) - 5},${y} Z`, class: "dist-mean" }));
    columns.forEach(([key, , dx]) => root.append(svg("text", { x: left + plotW + 16 + dx, y: y + 4, class: "dist-num" }, row[key].toFixed(1))));
  });
  host.append(root);
  const note = $("distribution-note");
  if (note) note.textContent = `${rows.length} tasks × ${featured().length} models${MODELS.length > featured().length ? " (Reka Edge left out, as in the leaderboard)" : ""}. Dots are models, the white bar the median, the diamond the mean, the band one standard deviation either side of the mean. Click a header to sort, a dot or a task to open it in Explore.`;
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
  renderWhatIf();
}

renderAnalysis();
