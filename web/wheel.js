// The benchmark as a wheel, after the paper's task pinwheel: five domains, ten task groups, 28 tasks, and inside
// every task's wedge one radial bar per model. A radar view puts the same models over the ten groups, one polygon
// each, for direct comparison. Both follow the model chips.

const WHEEL = { size: 1000, cx: 500, cy: 500, rings: { domain: [78, 132], group: [136, 188], label: [192, 236], bars: [242, 480] } };
const DOMAIN_SHORT = { Traffic_Knowledge_Understanding: "Traffic knowledge", General_Element_Recognition: "Element recognition",
                       Traffic_Graph_Generation: "Traffic graph", Target_Attribute_Comprehension: "Target attributes", Ego_Decision_Planning: "Ego decisions" };

const wheelState = { mode: (() => { try { return localStorage.getItem("vladbench-wheel") || "wheel"; } catch { return "wheel"; } })() };

function polar(r, angle) {
  return [WHEEL.cx + r * Math.cos(angle), WHEEL.cy + r * Math.sin(angle)];
}

// Annular sector from angle a0 to a1 (radians, clockwise on screen) between radii r0 and r1.
function sectorPath(r0, r1, a0, a1) {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const [x0, y0] = polar(r1, a0), [x1, y1] = polar(r1, a1), [x2, y2] = polar(r0, a1), [x3, y3] = polar(r0, a0);
  return `M${x0},${y0} A${r1},${r1} 0 ${large} 1 ${x1},${y1} L${x2},${y2} A${r0},${r0} 0 ${large} 0 ${x3},${y3} Z`;
}

// Text along an arc at radius r, reading left to right on both halves of the wheel.
function arcLabel(root, r, a0, a1, text, className, id) {
  const mid = (a0 + a1) / 2;
  const lower = Math.sin(mid) > 0;      // bottom half: run the path the other way so the text is not upside down
  const radius = lower ? r - 4 : r + 4;
  const [sx, sy] = polar(radius, lower ? a1 : a0), [ex, ey] = polar(radius, lower ? a0 : a1);
  const path = svg("path", { id, d: `M${sx},${sy} A${radius},${radius} 0 0 ${lower ? 0 : 1} ${ex},${ey}`, fill: "none" });
  const label = svg("text", { class: className });
  const textPath = svg("textPath", { href: `#${id}`, startOffset: "50%", "text-anchor": "middle" }, text);
  const arcLength = radius * (a1 - a0) * 0.92;
  const estimate = text.length * 5.6;
  if (estimate > arcLength) { textPath.setAttribute("textLength", Math.max(arcLength, 12)); textPath.setAttribute("lengthAdjust", "spacingAndGlyphs"); }
  label.append(textPath);
  root.append(path, label);
}

function wheelTasks() {
  return TASKS.filter((task) => MODELS.some((m) => m.tasks[task.name]?.score != null));
}

function drawWheel(root) {
  const tasks = wheelTasks();
  const n = tasks.length;
  const step = (2 * Math.PI) / n;
  const start = -Math.PI / 2;
  const angleOf = (index) => start + index * step;
  const { domain, group, label, bars } = WHEEL.rings;

  // Guide rings for the bars at 25, 50, 75, 100.
  for (const score of [25, 50, 75, 100]) {
    root.append(svg("circle", { cx: WHEEL.cx, cy: WHEEL.cy, r: bars[0] + (bars[1] - bars[0]) * score / 100, class: "wheel-guide" }));
    root.append(svg("text", { x: WHEEL.cx + 3, y: WHEEL.cy - (bars[0] + (bars[1] - bars[0]) * score / 100) - 2, class: "wheel-tick" }, score));
  }

  // Domain and group rings: contiguous runs of tasks.
  const runs = (key) => {
    const out = [];
    tasks.forEach((task, index) => {
      const last = out[out.length - 1];
      if (last && last.key === task[key]) last.end = index + 1; else out.push({ key: task[key], start: index, end: index + 1 });
    });
    return out;
  };
  runs("category").forEach((run, i) => {
    const a0 = angleOf(run.start) + 0.004, a1 = angleOf(run.end) - 0.004;
    root.append(svg("path", { d: sectorPath(domain[0], domain[1], a0, a1), class: `wheel-domain d${i}` }));
    arcLabel(root, (domain[0] + domain[1]) / 2, a0, a1, DOMAIN_SHORT[run.key] || humanize(run.key), "wheel-domain-label", `wd${i}`);
  });
  runs("group").forEach((run, i) => {
    const a0 = angleOf(run.start) + 0.004, a1 = angleOf(run.end) - 0.004;
    root.append(svg("path", { d: sectorPath(group[0], group[1], a0, a1), class: "wheel-group" }));
    arcLabel(root, (group[0] + group[1]) / 2, a0, a1, humanize(run.key), "wheel-group-label", `wg${i}`);
  });

  // Task wedges: abbreviation on the label ring, then one bar per model.
  const pad = step * 0.12;
  tasks.forEach((task, index) => {
    const a0 = angleOf(index), a1 = a0 + step;
    const wedge = svg("path", { d: sectorPath(label[0], bars[1], a0 + 0.002, a1 - 0.002), class: "wheel-wedge" });
    wedge.append(svg("title", {}, `${humanize(task.name)} · ${humanize(task.group)}`));
    wedge.onclick = () => { location.hash = "matrix"; selectTask(task); };
    root.append(wedge);
    const mid = (a0 + a1) / 2;
    const [tx, ty] = polar((label[0] + label[1]) / 2, mid);
    let rotate = (mid * 180) / Math.PI + 90;
    if (Math.sin(mid) > 0) rotate += 180;
    root.append(svg("text", { x: tx, y: ty, class: "wheel-task-label", "text-anchor": "middle", transform: `rotate(${rotate} ${tx} ${ty})` }, PAPER_TASK_LABEL[task.name] || humanize(task.name)));
    const scored = MODELS.filter((m) => m.tasks[task.name]?.score != null);
    const width = (step - 2 * pad) / Math.max(scored.length, 1);
    scored.forEach((model, k) => {
      const score = composite(model, task.name);
      const b0 = a0 + pad + k * width, b1 = b0 + width * 0.82;
      const bar = svg("path", { d: sectorPath(bars[0], bars[0] + (bars[1] - bars[0]) * score / 100, b0, b1), fill: model.color, class: "wheel-bar", tabindex: 0, role: "button",
                                 "aria-label": `${humanize(task.name)}, ${model.label}, ${percent(score, 1)}` });
      bar.append(svg("title", {}, `${humanize(task.name)} · ${model.label} · ${percent(score, 1)}`));
      bar.onclick = () => { location.hash = "matrix"; selectTask(task, model); };
      root.append(bar);
    });
  });

  root.append(svg("text", { x: WHEEL.cx, y: WHEEL.cy - 6, class: "wheel-center", "text-anchor": "middle" }, `${n} tasks`),
              svg("text", { x: WHEEL.cx, y: WHEEL.cy + 14, class: "wheel-center sub", "text-anchor": "middle" }, `${MODELS.length} models`));
}

// Radar: one axis per task group, question-weighted mean of the group's tasks, one polygon per model.
function groupScore(model, tasks) {
  const pairs = tasks.filter((t) => model.tasks[t.name]?.score != null).map((t) => [composite(model, t.name), model.tasks[t.name].questions_scored]);
  return pairs.length ? weightedMean(pairs) : null;
}

function drawRadar(root) {
  const groups = [...taskGroups(wheelTasks())];
  const n = groups.length;
  const rMax = 330, start = -Math.PI / 2;   // leaves room for the axis labels inside the 1000px box
  const angle = (i) => start + (i * 2 * Math.PI) / n;
  for (const score of [25, 50, 75, 100]) {
    const points = groups.map((_, i) => polar(rMax * score / 100, angle(i)).join(",")).join(" ");
    root.append(svg("polygon", { points, class: "wheel-guide" }));
    root.append(svg("text", { x: WHEEL.cx + 4, y: WHEEL.cy - rMax * score / 100 + 10, class: "wheel-tick" }, score));
  }
  groups.forEach(([name, { category }], i) => {
    const [x, y] = polar(rMax, angle(i));
    root.append(svg("line", { x1: WHEEL.cx, y1: WHEEL.cy, x2: x, y2: y, class: "wheel-axis" }));
    const [lx, ly] = polar(rMax + 30, angle(i));
    const anchor = Math.abs(Math.cos(angle(i))) < 0.2 ? "middle" : Math.cos(angle(i)) > 0 ? "start" : "end";
    root.append(svg("text", { x: lx, y: ly, class: "wheel-axis-label", "text-anchor": anchor }, humanize(name)),
                svg("text", { x: lx, y: ly + 13, class: "wheel-axis-sub", "text-anchor": anchor }, DOMAIN_SHORT[category] || humanize(category)));
  });
  const ranked = MODELS.slice().sort((a, b) => modelMean(a) - modelMean(b));   // weakest drawn first, leaders on top
  for (const model of ranked) {
    const values = groups.map(([, { tasks }]) => groupScore(model, tasks));
    if (values.some((v) => v == null)) continue;
    const points = values.map((v, i) => polar(rMax * v / 100, angle(i)));
    const polygon = svg("polygon", { points: points.map((p) => p.join(",")).join(" "), class: "radar-shape", stroke: model.color, fill: model.color });
    polygon.append(svg("title", {}, `${model.label}\n${groups.map(([g], i) => `${humanize(g)}: ${percent(values[i], 1)}`).join("\n")}`));
    root.append(polygon);
    points.forEach(([x, y], i) => {
      const dot = svg("circle", { cx: x, cy: y, r: 4, fill: model.color, class: "radar-dot" });
      dot.append(svg("title", {}, `${model.label} · ${humanize(groups[i][0])} · ${percent(values[i], 1)}`));
      root.append(dot);
    });
  }
}

function renderWheel() {
  const host = $("wheel");
  if (!host) return;
  host.replaceChildren();
  const root = svg("svg", { viewBox: `0 0 ${WHEEL.size} ${WHEEL.size}`, role: "img", class: `wheel-svg ${wheelState.mode}`,
                            "aria-label": wheelState.mode === "radar" ? "Radar of model scores by task group" : "Task wheel with every model's score on every task" });
  if (wheelState.mode === "radar") drawRadar(root); else drawWheel(root);
  host.append(root);
  const legend = $("wheel-legend");
  if (legend) {
    legend.replaceChildren();
    MODELS.forEach((model) => {
      const item = element("span");
      const swatch = element("i"); swatch.style.background = model.color;
      item.append(swatch, document.createTextNode(model.label));
      legend.append(item);
    });
  }
  for (const button of document.querySelectorAll("[data-wheel-mode]")) button.setAttribute("aria-pressed", String(button.dataset.wheelMode === wheelState.mode));
  const note = $("wheel-note");
  if (note) note.textContent = wheelState.mode === "radar"
    ? "Each axis is one of the benchmark's ten task groups; a model's value is the mean of the group's tasks, each weighted by its number of questions. The outer ring is 100. Use the model chips to compare a few models at a time."
    : "Five domains inside, ten task groups, then the 28 scored tasks under the paper's abbreviations. In each task's wedge one bar per model, growing outward from 0 to 100. Click a wedge or a bar to open that task in Explore.";
}

for (const button of document.querySelectorAll("[data-wheel-mode]")) {
  button.addEventListener("click", () => {
    wheelState.mode = button.dataset.wheelMode;
    try { localStorage.setItem("vladbench-wheel", wheelState.mode); } catch { /* ignore */ }
    renderWheel();
  });
}

renderWheel();   // results.js has already rendered everything else by the time this script runs
