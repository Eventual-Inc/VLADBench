"use strict";

// Results companion: weights, per-task bars, leaderboard, matrix, and the paper's Table 10.

const $ = (id) => document.getElementById(id);
const TASKS = window.REVIEW_DATA || [];
const AUDIT = window.REVIEW_AUDIT || { tasks: [] };
const PUBLISHED = window.PUBLISHED || { models: [], rows: [] };
const RERUN = window.FULL_RESULTS || { dataset: {}, models: [] };

// One hue per lab; models within a lab differ by lightness, the largest model brightest. Fifteen models cannot each get a hue that passes
// colour-vision checks, so every chart also labels models by name. Keyed by id so a model keeps its colour.
const MODEL_COLORS = {
  astra6: "#f5f5f5", sol6: "#d1d1d1", sol56: "#b1b1b1", luna6: "#959595", luna56: "#7a7a7a",   // OpenAI: grey to white
  opus55: "#d95926",                                                                              // Anthropic: orange
  gemini38: "#ffc15c", gemini25lite: "#e09b2e", gemma431: "#b97600",                              // Google: yellow
  qwen38max: "#b1a8ff", qwen38or: "#8a7fe2", qwen36or: "#6558b7",                                 // Alibaba: purple
  muse13: "#3987e5", minimax3: "#e0355a", rekaedge: "#008300",                                    // Meta blue, MiniMax red, Reka green
};
const COLOURED = RERUN.models.map((model) => ({ ...model, kind: "rerun", color: MODEL_COLORS[model.id] || "#b0b0b0" }));
const ALL_MODELS = groupByLab(COLOURED);
// MODELS is the visible subset; every view iterates it. applyModelFilter swaps its contents in place.
const MODELS = ALL_MODELS.slice();

function frontierIds(models) {
  return paretoFrontier(models.filter((m) => m.usage?.cost_usd && m.featured !== false).map((m) => ({ model: m, cost: m.usage.cost_usd, score: modelMean(m) }))).map((p) => p.model.id);
}

function applyModelFilter(ids, rerender = true) {
  const wanted = new Set(ids);
  MODELS.splice(0, MODELS.length, ...ALL_MODELS.filter((m) => wanted.has(m.id)));
  paintModelFilter();
  if (rerender) renderAll();
}

function paintModelFilter() {
  const box = $("model-filter");
  if (!box) return;
  const visible = new Set(MODELS.map((m) => m.id));
  for (const chip of box.querySelectorAll("[data-model]")) chip.setAttribute("aria-pressed", String(visible.has(chip.dataset.model)));
  const url = new URL(location.href);
  if (visible.size === ALL_MODELS.length) url.searchParams.delete("models"); else url.searchParams.set("models", [...visible].join(","));
  history.replaceState(null, "", url);
}

function buildModelFilter() {
  const box = $("model-filter");
  if (!box) return;
  const preset = (label, title, pick) => {
    const button = element("button", label, "preset");
    button.type = "button"; button.title = title;
    button.addEventListener("click", () => applyModelFilter(pick()));
    return button;
  };
  box.append(preset("All", "Every model", () => ALL_MODELS.map((m) => m.id)),
             preset("Frontier", "Models no other beats for the same cost or less", () => frontierIds(ALL_MODELS)));
  for (const model of ALL_MODELS) {
    const chip = element("button", undefined, "chip");
    chip.type = "button"; chip.dataset.model = model.id; chip.title = `${model.label} · ${model.lab}`;
    const swatch = element("i", undefined, "swatch"); swatch.style.background = model.color;
    chip.append(swatch, document.createTextNode(model.label));
    chip.addEventListener("click", () => {
      const ids = MODELS.map((m) => m.id);
      const next = ids.includes(model.id) ? ids.filter((id) => id !== model.id) : [...ids, model.id];
      if (next.length) applyModelFilter(next);
    });
    box.append(chip);
  }
  const requested = new URLSearchParams(location.search).get("models");
  if (requested === "frontier") applyModelFilter(frontierIds(ALL_MODELS), false);
  else if (requested) applyModelFilter(requested.split(",").filter((id) => ALL_MODELS.some((m) => m.id === id)), false);
  else paintModelFilter();
}

function groupByLab(models) {
  const best = {};
  for (const m of models) best[m.lab] = Math.max(best[m.lab] ?? -1, m.summary.unweighted_mean_task_score);
  return models.slice().sort((a, b) => (best[b.lab] - best[a.lab]) || a.lab.localeCompare(b.lab) || (a.size_rank - b.size_rank));
}

const state = { weights: null, expanded: null, selected: null };

// ---- helpers ------------------------------------------------------------------

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

const NS = "http://www.w3.org/2000/svg";
function svg(tag, attributes = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

// Display names. The released dataset misspells three task keys; the keys stay as released so the scorer and the
// data files match, and only the label is corrected.
const SPELLING = { Bahavior: "Behavior", Obsturction: "Obstruction" };
const humanize = (value) => Object.entries(SPELLING).reduce((text, [wrong, right]) => text.replaceAll(wrong, right), String(value).replaceAll("_", " "));
const percent = (value, digits = 2) => `${Number(value).toFixed(digits)}%`;
const money = (value) => (value === null || value === undefined ? "—" : `$${Number(value).toFixed(2)}`);
const seconds = (value) => `${Number(value).toFixed(1)} s`;
const mean = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
const auditFor = (task) => AUDIT.tasks.find((candidate) => candidate.name === task.name);

// ---- scoring under the current weights ---------------------------------------------

function weightsFor(result) {
  return state.weights || result.weights;
}

function composite(model, taskName) {
  const result = model.tasks[taskName];
  if (!result) return null;
  if (!state.weights) return result.score;
  const c = result.components;
  const w = state.weights;
  return 100 * c.other * w.other + 100 * c.accuracy * w.accuracy + 100 * c.instruction_following * w.instruction_following;
}

// The paper's TOTAL: question-count-weighted mean of the 28 task composites (rule inferred from Table 10; see renderPaperFormat).
function modelMean(model) {
  const pairs = TASKS.filter((task) => model.tasks[task.name]).map((task) => [composite(model, task.name), model.tasks[task.name].questions_scored]);
  return pairs.reduce((sum, [v, w]) => sum + v * w, 0) / pairs.reduce((sum, [, w]) => sum + w, 0);
}

function rankedModels() {
  return MODELS.slice().sort((left, right) => modelMean(right) - modelMean(left));
}


function partsFor(task, model) {
  const result = model.tasks[task.name];
  const w = weightsFor(result);
  return {
    composite: composite(model, task.name),
    q1: 100 * result.components.other, q1Name: result.components.other_name || "other", q1Weight: w.other,
    q2: 100 * result.components.accuracy, q2Name: result.components.accuracy_name || "accuracy", q2Weight: w.accuracy,
    q3: 100 * result.components.instruction_following, q3Name: "instruction_following", q3Weight: w.instruction_following,
  };
}

// ---- weights control ----------------------------------------------------------------




// ---- leaderboard ----------------------------------------------------------------------

function conditionChips(model) {
  const chips = [];
  chips.push(model.declared.input_transport === "video_mp4" ? "video" : "images");
  chips.push(model.reasoning === "off" ? "reasoning off" : `reasoning ${model.reasoning}`);
  if (model.completion_cap === 512) chips.push(model.truncated_answers ? `512 cap · ${model.truncated_answers} truncated` : "512 cap");
  else if (model.carried_from_superseded_condition) chips.push(`${model.carried_from_superseded_condition.toLocaleString()} carried · ${(11193 - model.carried_from_superseded_condition)} re-asked`);
  return chips;
}

function latencyStrip(usage, scaleMax) {
  const wrap = element("div", undefined, "latency");
  const lat = usage?.latency_seconds;
  if (!lat) {
    wrap.append(element("span", "—", "sub"));
    return wrap;
  }
  const x = (value) => `${(100 * Math.min(value, scaleMax)) / scaleMax}%`;
  const track = element("div", undefined, "latency-track");
  const box = element("i", undefined, "latency-box");
  box.style.left = x(lat.p25);
  box.style.width = `calc(${x(lat.p75)} - ${x(lat.p25)})`;
  const median = element("i", undefined, "latency-median");
  median.style.left = x(lat.p50);
  const tail = element("i", undefined, "latency-tail");
  tail.style.left = x(lat.p95);
  track.append(box, median, tail);
  track.title = `Per-request latency · p25 ${seconds(lat.p25)} · median ${seconds(lat.p50)} · p75 ${seconds(lat.p75)} · p95 ${seconds(lat.p95)} · max ${seconds(lat.max)} over ${lat.n.toLocaleString()} requests`;
  wrap.append(track, element("span", `${seconds(lat.p50)}`, "sub"));
  return wrap;
}

function renderLeaderboard() {
  const table = $("leaderboard");
  table.replaceChildren();
  const ranked = rankedModels().filter((m) => m.featured !== false);
  const omitted = MODELS.filter((m) => m.featured === false);
  const scaleMax = Math.max(...MODELS.map((m) => m.usage?.latency_seconds?.p95 || 0)) * 1.05;
  const head = element("tr");
  [["#", ""], ["Model", ""], ["Score", "num"], ["Sweep cost", "num"], ["Input $/frame", "num"], ["Output $/query", "num"], ["Est. $/hour of video", "num"], ["Latency", ""]].forEach(([label, cls]) => head.append(element("th", label, cls)));
  const thead = element("thead");
  thead.append(head);
  table.append(thead);
  const body = element("tbody");
  ranked.forEach((model, rank) => {
    const row = element("tr");
    row.append(element("td", rank + 1, "rank"));
    const name = element("td");
    const title = element("div", undefined, "model-name");
    const swatch = element("i", undefined, "swatch");
    swatch.style.background = model.color;
    title.append(swatch, element("b", model.label));
    const frontierIds = paretoFrontier(MODELS.filter((m) => m.usage?.cost_usd && m.featured !== false).map((m) => ({ model: m, cost: m.usage.cost_usd, score: modelMean(m) }))).map((p) => p.model.id);
    if (frontierIds.includes(model.id)) title.append(element("span", "frontier", "chip-frontier"));
    name.append(title, element("span", conditionChips(model).join(" · "), "chips"));
    row.append(name);
    row.append(element("td", modelMean(model).toFixed(2), "num strong"));
    const spend = element("td", money(model.usage?.cost_usd), "num");
    spend.title = model.usage?.cost_usd === null || model.usage?.cost_usd === undefined
      ? (model.usage?.note || "No per-request cost receipts")
      : model.usage.cost_basis || `Provider-billed API spend for ${model.usage.cost_receipts.toLocaleString()} answers`;
    row.append(spend);
    const metered = meteredHour(model, videoSettings());
    const perFrame = metered ? metered.tokensPerFrame * model.usage.metering.prompt_price : null;
    row.append(element("td", perFrame == null ? "—" : `$${perFrame.toFixed(5)}`, "num"),
               element("td", metered ? `$${metered.outputPerQuery.toFixed(5)}` : "—", "num"));
    const hour = element("td", money(metered ? metered.total : null), "num");
    hour.title = model.usage?.video_cost_basis || "";
    row.append(hour);
    const latency = element("td");
    latency.append(latencyStrip(model.usage, scaleMax));
    row.append(latency);
    body.append(row);
  });
  table.append(body);
  $("leaderboard-note").textContent =
    "Score is TOTAL, the mean of the 28 task scores weighted by question count. Sweep cost is the billed cost of all 11,193 answers. The per-frame, per-query, and hourly costs use the settings of the video cost calculator on the Cost tab. The latency box spans p25 to p75, the tick is the median, and the dot is p95."
    + (omitted.length ? ` Left out of this table and the plot, still in every other tab: ${omitted.map((m) => `${m.label} (${modelMean(m).toFixed(1)}; ${m.not_featured_reason})`).join("; ")}.` : "");
}

// ---- headline: spend vs TOTAL ------------------------------------------------------------

function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

function taskSpread(model) {
  const scores = TASKS.filter((t) => model.tasks[t.name]).map((t) => composite(model, t.name)).sort((a, b) => a - b);
  return { p25: quantile(scores, 0.25), p75: quantile(scores, 0.75) };
}

// Non-dominated models: no other model scores higher for the same cost or less.
function paretoFrontier(points) {
  const dominated = (p) => points.some((q) => q.score > p.score && q.cost <= p.cost);
  return points.filter((p) => !dominated(p)).sort((a, b) => a.cost - b.cost);
}

// Place each label at the first of several candidate anchors that overlaps neither a dot nor an earlier label.
function placeLabels(points, x, y, bounds) {
  const boxes = points.map((p) => ({ x: x(p.cost) - 8, y: y(p.score) - 8, w: 16, h: 16 }));
  const overlaps = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  const out = [];
  for (const p of points) {
    const cx = x(p.cost), cy = y(p.score), w = p.text.length * 6.3 + 4, h = 13;
    const candidates = [[11, 4, "start"], [-11, 4, "end"], [0, -12, "middle"], [0, 20, "middle"], [11, -10, "start"], [11, 18, "start"], [-11, -10, "end"], [-11, 18, "end"]];
    let chosen = null;
    for (let pass = 0; pass < 6 && !chosen; pass += 1) {
      for (const [dx, dy, anchor] of candidates) {
        const ly = cy + dy + pass * 14;
        const bx = anchor === "start" ? cx + dx : anchor === "end" ? cx + dx - w : cx - w / 2;
        const box = { x: bx, y: ly - 10, w, h };
        if (box.x < bounds.x0 || box.x + w > bounds.x1 || box.y < bounds.y0 || box.y + h > bounds.y1) continue;
        if (boxes.some((b) => overlaps(box, b))) continue;
        chosen = { x: cx + dx, y: ly, anchor, box };
        break;
      }
    }
    if (!chosen) chosen = { x: cx + 11, y: cy + 4, anchor: "start", box: { x: cx + 11, y: cy - 6, w, h } };
    boxes.push(chosen.box);
    out.push({ point: p, ...chosen });
  }
  return out;
}

const READINGS = [["pixels", "Pixels"], ["grid", "Own grid"], ["none", "No box tasks"]];
const costState = { reading: ["pixels", "grid", "none"].includes(new URLSearchParams(location.search).get("boxes")) ? new URLSearchParams(location.search).get("boxes") : "pixels" };

// TOTAL under one reading of the box tasks; pixels is the leaderboard's score.
function readingScore(model, reading) {
  if (reading === "pixels") return modelMean(model);
  return window.VARIANTS?.models?.[model.id]?.total?.[reading] ?? null;
}

function costPoints(reading) {
  return MODELS.filter((m) => m.usage?.cost_usd && m.featured !== false && readingScore(m, reading) != null)
    .map((m) => { const score = readingScore(m, reading); return { model: m, cost: m.usage.cost_usd, score, spread: taskSpread(m), gpu: Boolean(m.usage.cost_basis), text: `${m.label} · ${score.toFixed(1)}` }; });
}

function renderCostScore() {
  const chart = $("cost-score");
  if (!chart) return;
  chart.replaceChildren();
  const select = $("box-reading");
  if (select) select.value = costState.reading;
  const points = costPoints(costState.reading);
  const width = 1180, height = 460, margin = { top: 24, right: 48, bottom: 52, left: 54 };
  const plotW = width - margin.left - margin.right, plotH = height - margin.top - margin.bottom;
  const costs = points.map((p) => p.cost);
  const scores = points.map((p) => p.score);
  const linear = Boolean($("cost-linear")?.checked);
  const xMin = linear ? 0 : Math.pow(10, Math.floor(Math.log10(Math.min(...costs))));
  const xMax = linear ? Math.ceil(Math.max(...costs) / 100) * 100 : Math.pow(10, Math.ceil(Math.log10(Math.max(...costs))));
  const yMin = Math.floor((Math.min(...scores) - 3) / 5) * 5, yMax = Math.min(100, Math.ceil((Math.max(...scores) + 3) / 5) * 5);
  const x = linear ? (c) => margin.left + plotW * c / xMax : (c) => margin.left + plotW * (Math.log10(c) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin));
  const y = (v) => margin.top + plotH * (1 - (v - yMin) / (yMax - yMin));
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Sweep spend versus TOTAL score per model" });
  const xTicks = linear ? Array.from({ length: xMax / 100 + 1 }, (_, i) => i * 100) : Array.from({ length: Math.round(Math.log10(xMax / xMin)) + 1 }, (_, i) => xMin * Math.pow(10, i));
  for (const c of xTicks) {
    root.append(svg("line", { x1: x(c), x2: x(c), y1: margin.top, y2: margin.top + plotH, class: "chart-grid" }), svg("text", { x: x(c), y: height - 30, class: "chart-tick", "text-anchor": "middle" }, `$${c}`));
  }
  for (let v = yMin; v <= yMax; v += 5) {
    root.append(svg("line", { x1: margin.left, x2: margin.left + plotW, y1: y(v), y2: y(v), class: "chart-grid" }), svg("text", { x: margin.left - 8, y: y(v) + 4, class: "chart-tick", "text-anchor": "end" }, v));
  }
  root.append(svg("text", { x: margin.left + plotW / 2, y: height - 8, class: "chart-axis", "text-anchor": "middle" }, `Cost of the full sweep, 11,193 answers (${linear ? "linear" : "log"} scale)`));
  root.append(svg("text", { x: 14, y: margin.top + plotH / 2, class: "chart-axis", "text-anchor": "middle", transform: `rotate(-90 14 ${margin.top + plotH / 2})` }, "TOTAL score"));

  // Constant score-per-dollar: TOTAL = k · spend. On a log x axis these are exponentials.
  const ratios = [1, 5, 25];
  for (const k of ratios) {
    const path = [];
    for (let i = 0; i <= 80; i += 1) {
      const c = linear ? xMax * i / 80 : xMin * Math.pow(xMax / xMin, i / 80), v = k * c;
      if (v >= yMin && v <= yMax) path.push(`${path.length ? "L" : "M"}${x(c).toFixed(1)},${y(v).toFixed(1)}`);
    }
    if (!path.length) continue;
    root.append(svg("path", { d: path.join(" "), class: "chart-iso" }));
    const cEnd = Math.min(xMax, yMax / k);
    root.append(svg("text", { x: x(cEnd) - 4, y: y(Math.min(yMax, k * cEnd)) + 12, class: "chart-iso-label", "text-anchor": "end" }, `${k} pts/$`));
  }

  // Pareto frontier as a staircase: at any budget, the best TOTAL attainable.
  const frontier = paretoFrontier(points);
  const steps = frontier.map((p, i) => `${i ? "L" : "M"}${x(p.cost).toFixed(1)},${y(p.score).toFixed(1)}` + (frontier[i + 1] ? ` L${x(frontier[i + 1].cost).toFixed(1)},${y(p.score).toFixed(1)}` : ""));
  root.append(svg("path", { d: steps.join(" "), class: "chart-pareto" }));

  const bounds = { x0: margin.left + 2, x1: margin.left + plotW - 2, y0: margin.top, y1: margin.top + plotH };
  const labels = placeLabels(points.slice().sort((a, b) => b.score - a.score), x, y, bounds);
  for (const { point: p, x: lx, y: ly, anchor } of labels) {
    const cx = x(p.cost), cy = y(p.score);
    const dot = svg("circle", { cx, cy, r: 6.5, fill: p.model.color, stroke: p.gpu ? "#fff" : "#08080b", "stroke-width": 1.5, "stroke-dasharray": p.gpu ? "2 2" : null });
    dot.append(svg("title", {}, `${p.model.label} · TOTAL ${p.score.toFixed(2)} · task scores middle half ${p.spread.p25.toFixed(1)}–${p.spread.p75.toFixed(1)} · ${money(p.cost)}${p.gpu ? " GPU hours" : ""}${frontier.includes(p) ? " · on the frontier" : ""}`));
    root.append(dot, svg("text", { x: lx, y: ly, class: "chart-point-label", "text-anchor": anchor }, p.text));
  }
  chart.append(root);
  renderFrontier(points, frontier);
  renderReadings();
}

// The frontier stated as a table: which model to pick at each budget, and who beats every other model for less.
function renderFrontier(points, frontier) {
  const table = $("frontier");
  if (!table) return;
  table.replaceChildren();
  const head = element("tr");
  [["Sweep cost", ""], ["Best TOTAL available", ""], ["Cost", "num"], ["TOTAL", "num"]].forEach(([label, cls]) => head.append(element("th", label, cls)));
  const thead = element("thead"); thead.append(head); table.append(thead);
  const body = element("tbody");
  frontier.forEach((p, i) => {
    const next = frontier[i + 1];
    const row = element("tr");
    row.append(element("td", next ? `${money(p.cost)} to under ${money(next.cost)}` : `${money(p.cost)} and above`));
    const name = element("td"); const swatch = element("i", undefined, "swatch"); swatch.style.background = p.model.color;
    name.append(swatch, element("b", p.model.label)); row.append(name);
    row.append(element("td", money(p.cost), "num"), element("td", p.score.toFixed(2), "num"));
    body.append(row);
  });
  table.append(body);
}

// Every model's TOTAL under the three box readings, with frontier membership per reading.
function renderReadings() {
  const table = $("readings");
  if (!table) return;
  table.replaceChildren();
  const onFrontier = Object.fromEntries(READINGS.map(([key]) => [key, new Set(paretoFrontier(costPoints(key)).map((p) => p.model.id))]));
  const head = element("tr");
  head.append(element("th", "Model"), element("th", "Sweep cost", "num"));
  READINGS.forEach(([key, label]) => head.append(element("th", label, `num${key === costState.reading ? " active" : ""}`)));
  const thead = element("thead"); thead.append(head); table.append(thead);
  const body = element("tbody");
  costPoints("pixels").sort((a, b) => a.cost - b.cost).forEach((p) => {
    const row = element("tr");
    const name = element("td"); const swatch = element("i", undefined, "swatch"); swatch.style.background = p.model.color;
    name.append(swatch, element("b", p.model.label)); row.append(name, element("td", money(p.cost), "num"));
    READINGS.forEach(([key]) => {
      const score = readingScore(p.model, key);
      row.append(element("td", score == null ? "" : score.toFixed(1), `num${onFrontier[key].has(p.model.id) ? " on-frontier" : ""}`));
    });
    body.append(row);
  });
  table.append(body);
}

$("box-reading")?.addEventListener("change", (event) => {
  costState.reading = event.target.value;
  const url = new URL(location.href); url.searchParams.set("boxes", costState.reading); history.replaceState(null, "", url);
  renderCostScore();
});

// ---- video cost calculator: the metering rules from vladbench.metering, run in the browser -----------------------

const RESOLUTIONS = { "640x360": [640, 360], "1280x720": [1280, 720], "1920x1080": [1920, 1080] };

function clipTokens(rule, width, height, frames) {
  if (rule.kind === "patch") return frames * Math.ceil(width / rule.patch) * Math.ceil(height / rule.patch) * rule.multiplier;
  if (rule.kind === "area") return frames * rule.tokens_per_pixel * width * height;
  if (rule.kind === "pair") return Math.ceil(frames / 2) * rule.tokens_per_pixel * width * height;
  return frames * rule.tokens_per_frame;
}

function videoSettings() {
  const [width, height] = RESOLUTIONS[$("video-res")?.value || "1280x720"];
  return { width, height, fps: Number($("video-fps")?.value || 1), frames: Number($("video-frames")?.value || 8) };
}

function meteredHour(model, s) {
  const m = model.usage?.metering;
  if (!m) return null;
  const framesPerHour = s.fps * 3600, queries = framesPerHour / s.frames;
  const tokensPerFrame = clipTokens(m.rule, s.width, s.height, s.frames) / s.frames;
  const inputPerQuery = clipTokens(m.rule, s.width, s.height, s.frames) * m.prompt_price + m.text_tokens * m.prompt_price;
  const outputPerQuery = m.output_tokens_per_query * m.completion_price;
  return { tokensPerFrame, inputPerQuery, outputPerQuery, input: queries * inputPerQuery, output: queries * outputPerQuery, total: queries * (inputPerQuery + outputPerQuery), queries };
}

function renderVideoCost() {
  const table = $("video-cost");
  if (!table) return;
  const s = videoSettings();
  table.replaceChildren();
  const head = element("tr");
  [["Model", ""], ["Tokens / frame", "num"], ["Input $ / query", "num"], ["Output tokens / query", "num"], ["Output $ / query", "num"], ["$ / hour", "num"]]
    .forEach(([label, cls]) => head.append(element("th", label, cls)));
  const thead = element("thead"); thead.append(head); table.append(thead);
  const body = element("tbody");
  const rows = rankedModels().map((model) => [model, meteredHour(model, s)]).filter(([, h]) => h);
  rows.sort((a, b) => a[1].total - b[1].total);
  for (const [model, h] of rows) {
    const tr = element("tr");
    const name = element("td"); const swatch = element("i", undefined, "swatch"); swatch.style.background = model.color;
    name.append(swatch, element("b", model.label)); tr.append(name);
    tr.append(element("td", h.tokensPerFrame.toFixed(0), "num"), element("td", `$${h.inputPerQuery.toFixed(5)}`, "num"),
              element("td", model.usage.metering.output_tokens_per_query.toFixed(0), "num"), element("td", `$${h.outputPerQuery.toFixed(5)}`, "num"),
              element("td", money(h.total), "num strong"));
    body.append(tr);
  }
  table.append(body);
  const missing = rankedModels().filter((m) => !m.usage?.metering).map((m) => m.label);
  $("video-cost-note").textContent = `One hour of video at ${s.width}x${s.height} is ${(s.fps * 3600).toLocaleString()} frames and ${Math.round(s.fps * 3600 / s.frames).toLocaleString()} queries. `
    + "Tokens per frame use each provider's tokeniser rule, fitted to our billed tokens. Prices are the per-token rates the sweep was billed. Output tokens per query are measured and include reasoning."
    + (missing.length ? ` No fitted rule yet for ${missing.join(", ")}.` : "");
}

// ---- horizontal bar chart -------------------------------------------------------------

// Task families shown in Score by task and the matrix; pills like the model filter. Empty set means all.
state.families = new Set();

function visibleTasks() {
  return TASKS.filter((task) => !state.families.size || state.families.has(task.group));
}

function buildTaskFilter() {
  const box = $("task-filter");
  if (!box) return;
  const families = [...new Map(TASKS.filter((t) => MODELS.some((m) => m.tasks[t.name])).map((t) => [t.group, t.category])).entries()];
  const paint = () => {
    for (const chip of box.querySelectorAll("[data-family]")) chip.setAttribute("aria-pressed", String(!state.families.size || state.families.has(chip.dataset.family)));
    box.querySelector(".preset").setAttribute("aria-pressed", String(!state.families.size));
  };
  const all = element("button", "All tasks", "preset");
  all.type = "button";
  all.addEventListener("click", () => { state.families.clear(); paint(); renderBarChart(); renderMatrix(); });
  box.append(all);
  for (const [group, category] of families) {
    const chip = element("button", humanize(group), "chip");
    chip.type = "button"; chip.dataset.family = group; chip.title = humanize(category);
    chip.addEventListener("click", () => {
      if (!state.families.size) state.families = new Set([group]);
      else if (state.families.has(group)) state.families.delete(group);
      else state.families.add(group);
      paint(); renderBarChart(); renderMatrix();
    });
    box.append(chip);
  }
  paint();
}

function selectTask(task, model) {
  state.expanded = task.name;
  state.selected = model ? { id: model.id, task: task.name } : null;
  renderMatrix();
  document.querySelector(".matrix")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function taskGroups(tasks) {
  const groups = new Map();
  for (const task of tasks) {
    if (!groups.has(task.group)) groups.set(task.group, { category: task.category, tasks: [] });
    groups.get(task.group).tasks.push(task);
  }
  return groups;
}

function smallMultiple(group, tasks) {
  // One chart per task family. Every card shares the same drawing size, so charts render at the same height across
  // the grid; families with more tasks get narrower bars rather than a shorter chart.
  const width = 600, plotHeight = 200;
  const margin = { top: 14, right: 8, bottom: 84, left: 34 };   // room for the longest rotated task label
  const slots = Math.max(tasks.length, 3);
  const groupWidth = (width - margin.left - margin.right) / slots;
  const groupPad = Math.min(16, groupWidth * 0.18);
  const barGap = 1;
  const barWidth = Math.max(2, (groupWidth - groupPad - barGap * (MODELS.length - 1)) / MODELS.length);
  const height = margin.top + plotHeight + margin.bottom;
  const y = (score) => margin.top + plotHeight * (1 - score / 100);
  const offset = ((slots - tasks.length) * groupWidth) / 2;
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${humanize(group)} task scores by model` });
  for (let score = 0; score <= 100; score += 25) {
    root.append(svg("line", { x1: margin.left, x2: width - margin.right, y1: y(score), y2: y(score), class: "chart-grid" }),
                svg("text", { x: margin.left - 6, y: y(score) + 4, class: "chart-tick", "text-anchor": "end" }, score));
  }
  tasks.forEach((task, index) => {
    const left = margin.left + offset + index * groupWidth + groupPad / 2;
    const centre = left + (groupWidth - groupPad) / 2;
    const labelY = margin.top + plotHeight + 10;
    const label = svg("text", { x: centre, y: labelY, class: "chart-task-label", "text-anchor": "end", transform: `rotate(-35 ${centre} ${labelY})`, tabindex: 0, role: "button" }, humanize(task.name));
    label.onclick = () => selectTask(task);
    label.onkeydown = (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectTask(task); } };
    root.append(label);
    const best = Math.max(...MODELS.map((m) => composite(m, task.name) ?? -1));
    MODELS.forEach((model, modelIndex) => {
      const score = composite(model, task.name);
      if (score === null) return;
      const x = left + modelIndex * (barWidth + barGap);
      const bar = svg("rect", { x, y: y(score), width: barWidth, height: Math.max(plotHeight * score / 100, 1), fill: model.color, class: "chart-bar", tabindex: 0, role: "button", "aria-label": `${task.name}, ${model.label}, ${percent(score)}` });
      bar.append(svg("title", {}, `${humanize(task.name)} · ${model.label} · ${percent(score)}`));
      bar.onclick = () => selectTask(task, model);
      bar.onkeydown = (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectTask(task, model); } };
      root.append(bar);
      if (score === best) root.append(svg("text", { x: x + barWidth / 2, y: y(score) - 3, class: "chart-value", "text-anchor": "middle" }, score.toFixed(0)));
    });
  });
  return root;
}

function renderBarChart() {
  const legend = $("bar-legend");
  const chart = $("bar-chart");
  legend.replaceChildren();
  chart.replaceChildren();
  MODELS.forEach((model) => {
    const item = element("span");
    const swatch = element("i");
    swatch.style.background = model.color;
    item.append(swatch, document.createTextNode(model.label));
    legend.append(item);
  });
  const tasks = visibleTasks();
  if (!tasks.length) {
    chart.append(element("p", "No tasks match this search.", "empty"));
    return;
  }
  const grid = element("div", undefined, "multiples");
  const scored = tasks.filter((task) => MODELS.some((m) => m.tasks[task.name]));
  for (const [group, { category, tasks: members }] of taskGroups(scored)) {
    const card = element("div", undefined, "multiple");
    card.append(element("h4", humanize(group)), element("p", `${humanize(category)} · ${members.length} ${members.length === 1 ? "task" : "tasks"}`, "sub"), smallMultiple(group, members));
    grid.append(card);
  }
  chart.append(grid);
}

// ---- matrix ------------------------------------------------------------------------------

// Matrix cells share the Table 10 heat scale, so one colour means one score everywhere on the page.
function scoreHeat(button, value) {
  const { background, ink } = heatColor(value);
  button.style.background = background;
  button.style.color = ink;
}

function labelStrip(task, cell) {
  const group = auditFor(task)?.groups?.slice().sort((a, b) => b.questions - a.questions)[0];
  if (!group) return;
  const bar = element("span", undefined, "dist");
  const shades = ["#ff3bd4", "#ad3fff", "#6755d8", "#4d697b", "#756878"];
  bar.title = `Largest answer group: ${humanize(group.type)} · ${group.questions} questions`;
  Object.entries(group.raw_distribution).sort((a, b) => b[1] - a[1]).forEach(([label, count], index) => {
    const segment = element("i");
    segment.style.width = `${(100 * count) / group.questions}%`;
    segment.style.background = shades[index % shades.length];
    segment.title = `${label}: ${count}`;
    bar.append(segment);
  });
  cell.append(bar);
}

function componentRows(result) {
  const w = weightsFor(result);
  const rows = [[result.components.accuracy_name || "accuracy", result.components.accuracy, w.accuracy]];
  if (w.other || result.components.other) rows.push([result.components.other_name || "other", result.components.other, w.other]);
  rows.push(["instruction_following", result.components.instruction_following, w.instruction_following]);
  return rows;
}

function componentList(result) {
  const list = element("div", undefined, "component-list");
  list.append(element("span", "Component"), element("span", "Value"), element("span", "Weight"));
  for (const [name, value, weight] of componentRows(result)) {
    list.append(element("span", humanize(name)), element("span", percent(100 * value, 1)), element("span", percent(100 * weight, 0)));
  }
  return list;
}

function resultRule(task, model) {
  const result = model.tasks[task.name];
  const formula = componentRows(result).map(([name, , weight]) => `${percent(100 * weight, 0)} ${humanize(name)}`).join(" + ");
  return `${result.scorer_function}: ${formula}.${state.weights ? " (custom global weights)" : ""}`;
}

function inspectQuestion(task, question, model) {
  if (!question) return;
  const detail = $("detail");
  detail.replaceChildren(element("h2", humanize(task.name)), element("p", `${question.sequence || question.id} · question ${question.question}`));
  const frames = element("div", undefined, "frames");
  question.images.forEach((frame, index) => {
    const link = element("a");
    link.href = frame.path; link.target = "_blank"; link.rel = "noopener noreferrer";
    const image = element("img");
    image.loading = "lazy"; image.src = frame.path; image.alt = `Frame ${index + 1}`;
    link.append(image, document.createTextNode(`Frame ${index + 1} ↗`));
    frames.append(link);
  });
  detail.append(frames, element("h3", "Question"), element("pre", question.prompt), element("h3", "Reference"), element("pre", String(question.gold)));
  if (model) {
    detail.append(element("h3", `Scoring · ${model.label}`), element("p", resultRule(task, model)));
    const record = element("details");
    record.append(element("summary", "Compact task score record"), element("pre", JSON.stringify(model.tasks[task.name], null, 2)));
    detail.append(record);
  }
  detail.append(element("h3", "Reference label distributions"));
  for (const group of auditFor(task)?.groups || []) {
    const distribution = element("details");
    distribution.append(element("summary", `${humanize(group.type)} · ${group.questions} questions`), element("pre", JSON.stringify(group.raw_distribution, null, 2)));
    detail.append(distribution);
  }
  detail.append(element("p", `Dataset revision: ${task.revision}`, "scope"));
  const source = element("a", "Open source annotations ↗", "primary-link");
  source.href = task.source; source.target = "_blank"; source.rel = "noopener noreferrer";
  detail.append(source);
  if (!$("inspector").open) $("inspector").showModal();
}

// The expanded task row (clip, question, answer grid) lives in web/task-detail.js.

function renderMatrix() {
  const head = $("head");
  const body = $("body");
  head.replaceChildren();
  body.replaceChildren();
  const header = element("tr");
  const taskHead = element("th", "Benchmark task");
  taskHead.append(element("span", "Cells show composite, then q1 · q2 · q3 components", "sub"));
  header.append(taskHead);
  for (const model of MODELS) {
    const cell = element("th");
    const title = element("div", undefined, "model-name");
    const swatch = element("i", undefined, "swatch");
    swatch.style.background = model.color;
    title.append(swatch, element("b", model.label));
    cell.append(title, element("span", `${percent(modelMean(model), 1)} mean`, "sub"), element("span", conditionChips(model).join(" · "), "sub"));
    header.append(cell);
  }
  head.append(header);
  const tasks = visibleTasks();
  if (!tasks.length) {
    const row = element("tr");
    const cell = element("td", "No tasks match this search.", "empty");
    cell.colSpan = MODELS.length + 1;
    row.append(cell);
    body.append(row);
    return;
  }
  let category = null;
  const showGroups = true;
  for (const task of tasks) {
    if (showGroups && task.category !== category) {
      category = task.category;
      const group = element("tr", undefined, "group");
      const label = element("td", humanize(category));
      label.colSpan = MODELS.length + 1;
      group.append(label);
      body.append(group);
    }
    const row = element("tr");
    const taskCell = element("td");
    const taskButton = element("button", `${state.expanded === task.name ? "▾" : "▸"} ${humanize(task.name)}`, "task-button");
    taskButton.onclick = () => { state.expanded = state.expanded === task.name ? null : task.name; renderMatrix(); };
    taskCell.append(taskButton, element("span", `${humanize(task.group)} · ${(task.question_count ?? task.items.length).toLocaleString()} questions`, "sub"));
    labelStrip(task, taskCell);
    row.append(taskCell);
    const scores = MODELS.map((m) => composite(m, task.name)).filter((s) => s !== null);
    const best = scores.length ? Math.max(...scores) : null;
    for (const model of MODELS) {
      const cell = element("td");
      const score = composite(model, task.name);
      if (score === null) {
        cell.append(element("span", "—", "empty"));
        cell.title = "Unavailable, not zero";
      } else {
        const parts = partsFor(task, model);
        const button = element("button", undefined, "score");
        button.append(element("b", percent(score)));
        const qs = element("span", undefined, "score-qs");
        [["q1", parts.q1, parts.q1Name, parts.q1Weight], ["q2", parts.q2, parts.q2Name, parts.q2Weight], ["q3", parts.q3, parts.q3Name, parts.q3Weight]].forEach(([label, value, name, weight]) => {
          const item = element("span", `${label} ${Number(value).toFixed(1)}`);
          if (weight === 0) item.className = "idle";
          item.title = `${label} ${humanize(name)}: ${percent(value)} · weight ${percent(100 * weight, 0)}`;
          qs.append(item);
        });
        button.append(qs);
        scoreHeat(button, score);
        if (best !== null && Math.abs(score - best) < 1e-9) button.classList.add("winner");
        button.title = `${model.label} · composite ${percent(score)} · fixed 0–100% scale`;
        button.onclick = () => selectTask(task, model);
        cell.append(button);
      }
      row.append(cell);
    }
    body.append(row);
    if (state.expanded === task.name) body.append(renderTaskDetail(task));
  }
}

// ---- the paper's Table 10 -----------------------------------------------------------------

// ---- Table 10 format ------------------------------------------------------------------------
// The paper's Table 10: one column per model ordered by TOTAL ascending, a size row under the header,
// tasks in the paper's order under their source abbreviations, a MEAN row after each task group, and a
// TOTAL row. MEAN and TOTAL are question-count-weighted means of task composites; that rule reproduces the
// published rows for the paper's own models (see paperWeightingCheck).

const PAPER_TASKS = PUBLISHED.rows.filter((row) => !row.aggregate);
const PAPER_TASK_ORDER = PAPER_TASKS.map((row) => row.task);
const PAPER_TASK_LABEL = Object.fromEntries(PAPER_TASKS.map((row) => [row.task, row.source_label]));
const paperGroups = () => {
  const groups = [];
  let current = [];
  for (const row of PUBLISHED.rows) {
    if (row.aggregate && row.source_label === "MEAN") { groups.push(current); current = []; }
    else if (!row.aggregate) current.push(row.task);
  }
  return groups;
};

const weightedMean = (pairs) => pairs.reduce((sum, [value, weight]) => sum + value * weight, 0) / pairs.reduce((sum, [, weight]) => sum + weight, 0);

function ourTable10Columns() {
  const columns = MODELS.map((model) => {
    const value = (task) => composite(model, task);
    const weight = (task) => model.tasks[task].questions_scored;
    const rows = {};
    for (const group of paperGroups()) {
      for (const task of group) rows[task] = value(task);
      rows[`MEAN:${group[0]}`] = weightedMean(group.map((task) => [value(task), weight(task)]));
    }
    rows.TOTAL = weightedMean(PAPER_TASK_ORDER.map((task) => [value(task), weight(task)]));
    const subs = [model.parameters || "undisclosed", model.declared?.input_transport === "video_mp4" ? "video" : "images", model.reasoning === "off" ? "no reasoning" : `${model.reasoning} reasoning`];
    return { id: model.id, label: model.label, lab: model.lab, subs, color: model.color, rows };
  });
  return columns; // MODELS order: grouped by lab, smallest model first
}

function publishedTable10Columns() {
  const total = PUBLISHED.rows.find((row) => row.aggregate && row.source_label === "TOTAL");
  return PUBLISHED.models.map((model) => {
    const rows = {};
    for (const row of PUBLISHED.rows) {
      if (row.aggregate && row.source_label === "TOTAL") rows.TOTAL = row.scores[model.id];
      else if (row.aggregate) rows[`MEAN:${meanGroupStart(row)}`] = row.scores[model.id];
      else rows[row.task] = row.scores[model.id];
    }
    return { id: model.id, label: model.abbreviation, subs: [model.size_or_version], rows, total: total ? total.scores[model.id] : null };
  }).filter((column) => column.total !== null).sort((a, b) => a.total - b.total);
}

function meanGroupStart(meanRow) {
  const index = PUBLISHED.rows.indexOf(meanRow);
  let start = null;
  for (let i = index - 1; i >= 0 && !PUBLISHED.rows[i].aggregate; i -= 1) start = PUBLISHED.rows[i].task;
  return start;
}

function table10Rows() {
  const rows = [];
  for (const group of paperGroups()) {
    for (const task of group) rows.push({ key: task, label: PAPER_TASK_LABEL[task], title: humanize(task), aggregate: false });
    rows.push({ key: `MEAN:${group[0]}`, label: "MEAN", title: `Question-weighted mean of ${group.map(humanize).join(", ")}`, aggregate: true });
  }
  rows.push({ key: "TOTAL", label: "TOTAL", title: "Question-weighted mean of all 28 tasks", aggregate: true });
  return rows;
}

function renderTable10(headId, bodyId, columns) {
  const head = $(headId);
  const body = $(bodyId);
  head.replaceChildren();
  body.replaceChildren();
  if (columns.some((c) => c.lab)) {
    const labs = element("tr", undefined, "table10-labs");
    labs.append(element("th", ""));
    let i = 0;
    while (i < columns.length) {
      let span = 1;
      while (columns[i + span] && columns[i + span].lab === columns[i].lab) span += 1;
      const cell = element("th", columns[i].lab);
      cell.colSpan = span;
      labs.append(cell);
      i += span;
    }
    head.append(labs);
  }
  const names = element("tr");
  names.append(element("th", "Task"));
  const subRows = Math.max(...columns.map((c) => c.subs.length));
  const subs = Array.from({ length: subRows }, () => { const tr = element("tr", undefined, "table10-sub"); tr.append(element("th", "")); return tr; });
  for (const column of columns) {
    const cell = element("th", column.label);
    if (column.color) cell.style.borderTopColor = column.color;
    names.append(cell);
    subs.forEach((tr, i) => tr.append(element("th", column.subs[i] ?? "")));
  }
  head.append(names, ...subs);
  for (const row of table10Rows()) {
    const tr = element("tr", undefined, row.aggregate ? "aggregate" : undefined);
    const label = element("td", row.label);
    label.title = row.title;
    tr.append(label);
    const values = columns.map((column) => column.rows[row.key]);
    const best = Math.max(...values.filter((v) => v !== null && v !== undefined));
    values.forEach((value) => {
      const cell = element("td", value === null || value === undefined ? "—" : Number(value).toFixed(2));
      if (value !== null && value !== undefined) tableHeat(cell, value);
      if (value === best) cell.classList.add("best");
      tr.append(cell);
    });
    body.append(tr);
  }
}

// One scale for both tables so past and present read against the same colours. Three stops, user-adjustable.
const HEAT_DEFAULT = { low: "#b3261e", mid: "#d9a400", high: "#1f8a4c", midpoint: 50 };
function loadHeat() {
  try { return { ...HEAT_DEFAULT, ...JSON.parse(localStorage.getItem("vladbench-heat") || "{}") }; } catch { return { ...HEAT_DEFAULT }; }
}
state.heat = loadHeat();
const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
function heatColor(value) {
  const { low, mid, high, midpoint } = state.heat;
  const v = Math.max(0, Math.min(100, value));
  const rgb = v <= midpoint ? mix(hexToRgb(low), hexToRgb(mid), midpoint ? v / midpoint : 1) : mix(hexToRgb(mid), hexToRgb(high), (v - midpoint) / (100 - midpoint));
  const luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
  return { background: `rgb(${rgb.join(" ")})`, ink: luminance > 0.55 ? "#111" : "#fff" };
}
function tableHeat(cell, value) {
  const { background, ink } = heatColor(value);
  cell.style.background = background;
  cell.style.color = ink;
}
function wireHeatPicker() {
  const ids = { low: "heat-low", mid: "heat-mid", high: "heat-high", midpoint: "heat-midpoint" };
  if (!$(ids.low)) return;
  const paint = () => {
    for (const [key, id] of Object.entries(ids)) $(id).value = state.heat[key];
    $("heat-midpoint-readout").textContent = state.heat.midpoint;
    const legend = $("heat-legend");
    legend.replaceChildren();
    for (let v = 0; v <= 100; v += 5) {
      const step = element("i");
      step.style.background = heatColor(v).background;
      step.title = v;
      legend.append(step);
    }
  };
  for (const [key, id] of Object.entries(ids)) {
    $(id).addEventListener("input", () => {
      state.heat[key] = key === "midpoint" ? Number($(id).value) : $(id).value;
      try { localStorage.setItem("vladbench-heat", JSON.stringify(state.heat)); } catch { /* per-viewer convenience only */ }
      paint();
      renderPaperFormat();
      renderMatrix();
    });
  }
  $("heat-reset").addEventListener("click", () => { state.heat = { ...HEAT_DEFAULT }; try { localStorage.removeItem("vladbench-heat"); } catch { /* ignore */ } paint(); renderPaperFormat(); renderMatrix(); });
  paint();
}

function table10Text(columns, format) {
  const rows = table10Rows();
  if (format === "csv") {
    const lines = [["Task", ...columns.map((c) => c.label)].join(","), ["", ...columns.map((c) => c.subs.join(" / "))].join(",")];
    for (const row of rows) lines.push([row.label, ...columns.map((c) => Number(c.rows[row.key]).toFixed(2))].join(","));
    return lines.join("\n");
  }
  const lines = [`\\begin{tabular}{l${"c".repeat(columns.length)}}`, "\\toprule",
    `Task & ${columns.map((c) => c.label).join(" & ")} \\\\`, ` & ${columns.map((c) => c.subs.join(", ")).join(" & ")} \\\\`, "\\midrule"];
  for (const row of rows) {
    const values = columns.map((c) => Number(c.rows[row.key]).toFixed(2));
    lines.push(`${row.aggregate ? `\\textbf{${row.label}}` : row.label} & ${values.join(" & ")} \\\\`);
    if (row.aggregate) lines.push("\\midrule");
  }
  lines.push("\\bottomrule", "\\end{tabular}");
  return lines.join("\n");
}

function paperWeightingCheck() {
  // How closely question-weighting reproduces the paper's own MEAN and TOTAL rows, over all published columns.
  const weights = Object.fromEntries(PAPER_TASK_ORDER.map((task) => [task, MODELS[0]?.tasks[task]?.questions_scored ?? 1]));
  let within = 0, total = 0;
  for (const column of publishedTable10Columns()) {
    for (const group of paperGroups()) {
      const expected = weightedMean(group.map((task) => [column.rows[task], weights[task]]));
      total += 1;
      if (Math.abs(expected - column.rows[`MEAN:${group[0]}`]) <= 0.1) within += 1;
    }
  }
  return { within, total };
}

function renderPaperFormat() {
  const ours = ourTable10Columns();
  renderTable10("ours-head", "ours-body", ours);
  renderTable10("paper-head", "paper-body", publishedTable10Columns());
  const check = paperWeightingCheck();
  $("table10-note").textContent = `MEAN and TOTAL weight each task by its number of questions. This rule reproduces ${check.within} of the paper's ${check.total} group averages within 0.1.`;
  $("copy-latex").onclick = () => navigator.clipboard.writeText(table10Text(ours, "latex"));
  $("copy-csv").onclick = () => navigator.clipboard.writeText(table10Text(ours, "csv"));
}

// ---- wiring --------------------------------------------------------------------------------

function renderAll() {
  if ($("ours-head")) renderPaperFormat();
  $("method").textContent = `${RERUN.dataset.responses?.toLocaleString?.() || ""} answers · ${MODELS.length} models · original prompts · the paper's scoring criteria`;
  renderCostScore();
  renderVideoCost();
  renderLeaderboard();
  renderBarChart();
  renderMatrix();
  if (typeof renderWheel === "function") renderWheel();
  if (typeof renderAnalysis === "function") renderAnalysis();
}

// Tabs: hash-addressable; phones (<=720px) only get the tabs not marked data-desktop.
function wireTabs() {
  const buttons = [...document.querySelectorAll('.tabs [role="tab"]')];
  if (!buttons.length) return;
  const show = (name) => {
    for (const button of buttons) button.setAttribute("aria-selected", String(button.dataset.tab === name));
    for (const page of document.querySelectorAll(".tab-page")) page.hidden = page.dataset.tab !== name;
    for (const shared of document.querySelectorAll("[data-tabs]")) shared.hidden = !shared.dataset.tabs.split(" ").includes(name);
    history.replaceState(null, "", `#${name}`);
  };
  const phone = () => window.matchMedia("(max-width: 720px)").matches;
  const available = (name) => buttons.some((b) => b.dataset.tab === name && !(phone() && b.hasAttribute("data-desktop")));
  const fromHash = () => { const name = location.hash.slice(1); show(available(name) ? name : "overview"); };
  for (const button of buttons) button.addEventListener("click", () => show(button.dataset.tab));
  window.addEventListener("hashchange", fromHash);
  fromHash();
}
wireTabs();

// Embed mode: ?embed=<name> (see EMBED_TABS) shows one panel with no chrome, for iframes in the blog.
const EMBED_TABS = { quadrants: "caveats", boxes: "caveats", suspect: "caveats", cutin: "caveats", distribution: "analysis", whatif: "analysis", wheel: "overview", overview: "cost", leaderboard: "leaderboard", plot: "cost", frontier: "cost", video: "cost", results: "overview", score: "leaderboard", matrix: "matrix" };
const embed = new URLSearchParams(location.search).get("embed");
if (embed === "full") document.body.classList.add("embed-full");   // whole tabbed page without the site header, for /blog/VLADBench
if (embed && EMBED_TABS[embed]) {
  document.body.classList.add("embed", `embed-${embed}`);
  for (const page of document.querySelectorAll(".tab-page")) page.hidden = page.dataset.tab !== EMBED_TABS[embed];
  for (const shared of document.querySelectorAll("[data-tabs]")) shared.hidden = !["score", "matrix"].includes(embed);
}
for (const [id, target] of [["article-link", window.VLADBENCH_ARTICLE], ["blog-link", window.VLADBENCH_BLOG]]) {
  const link = $(id);
  if (link && target) { link.href = target; link.target = "_top"; link.hidden = false; }   // leave the iframe when embedded
}
$("cost-linear")?.addEventListener("change", renderCostScore);
for (const id of ["video-res", "video-fps", "video-frames"]) $(id)?.addEventListener("change", () => { renderVideoCost(); renderLeaderboard(); });
$("inspector-close").onclick = () => $("inspector").close();

buildModelFilter();
buildTaskFilter();
renderAll();
renderPaperFormat();
wireHeatPicker();
