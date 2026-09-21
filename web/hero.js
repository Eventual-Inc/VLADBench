// Front page: cost against score, with every model drawn as a five-axis glyph of its domain scores. The frontier is
// the magenta staircase; the 2025 field sits as grey ticks on the left edge for scale. Follows the model chips.

const HERO = { w: 1400, h: 720, margin: { top: 56, right: 60, bottom: 70, left: 120 }, glyph: 42, floor: 40 };   // glyph axes run from `floor` at the centre to 100 at the ring
const DOMAINS = [...new Set(TASKS.map((t) => t.category))];
const DOMAIN_LABEL = { Traffic_Knowledge_Understanding: "traffic knowledge", General_Element_Recognition: "element recognition",
                       Traffic_Graph_Generation: "traffic graph", Target_Attribute_Comprehension: "target attributes", Ego_Decision_Planning: "ego decisions" };

function domainScores(model) {
  return DOMAINS.map((category) => {
    const pairs = TASKS.filter((t) => t.category === category && model.tasks[t.name]?.score != null).map((t) => [composite(model, t.name), model.tasks[t.name].questions_scored]);
    return pairs.length ? weightedMean(pairs) : 0;
  });
}

function glyphPath(cx, cy, r, values) {
  const n = values.length, floor = HERO.floor;
  const pts = values.map((v, i) => { const a = -Math.PI / 2 + (i * 2 * Math.PI) / n; const rr = r * Math.max(0, v - floor) / (100 - floor); return [cx + rr * Math.cos(a), cy + rr * Math.sin(a)]; });
  return "M" + pts.map((p) => p.join(",")).join(" L") + " Z";
}

// Labels beside glyphs: try eight anchors around each glyph, then further out, never over another glyph or label.
function heroLabels(points, x, y, bounds) {
  const r = HERO.glyph + 4;
  const boxes = points.map((p) => ({ x: x(p.cost) - r, y: y(p.score) - r, w: 2 * r, h: 2 * r }));
  const overlaps = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  const out = [];
  for (const p of points.slice().sort((a, b) => b.score - a.score)) {
    const text = `${p.model.label} · ${p.score.toFixed(1)}`;
    const cx = x(p.cost), cy = y(p.score), w = text.length * 7 + 6, h = 15;
    const candidates = [[r, 4, "start"], [-r, 4, "end"], [0, -r - 4, "middle"], [0, r + 12, "middle"], [r, -r + 6, "start"], [r, r + 2, "start"], [-r, -r + 6, "end"], [-r, r + 2, "end"]];
    let chosen = null;
    for (let pass = 0; pass < 5 && !chosen; pass += 1) {
      for (const [dx, dy, anchor] of candidates) {
        const ly = cy + dy + pass * 16;
        const bx = anchor === "start" ? cx + dx : anchor === "end" ? cx + dx - w : cx - w / 2;
        const box = { x: bx, y: ly - 11, w, h };
        if (box.x < bounds.x0 || box.x + w > bounds.x1 || box.y < bounds.y0 || box.y + h > bounds.y1) continue;
        if (boxes.some((b) => overlaps(box, b))) continue;
        chosen = { x: cx + dx, y: ly, anchor, box };
        break;
      }
    }
    if (!chosen) chosen = { x: cx + r, y: cy + 4, anchor: "start", box: { x: cx + r, y: cy - 7, w, h } };
    boxes.push(chosen.box);
    out.push({ text, ...chosen });
  }
  return out;
}

function paperTotals() {
  const row = PUBLISHED.rows.find((r) => r.aggregate && r.source_label === "TOTAL");
  return row ? Object.entries(row.scores).filter(([, v]) => v != null).map(([id, v]) => ({ id, value: v })) : [];
}

function renderHero() {
  const host = $("hero");
  if (!host) return;
  host.replaceChildren();
  const { w, h, margin, glyph } = HERO;
  const models = MODELS.filter((m) => m.usage?.cost_usd && m.featured !== false);
  const points = models.map((m) => ({ model: m, cost: m.usage.cost_usd, score: modelMean(m), domains: domainScores(m), text: m.label }));
  if (!points.length) { host.append(element("p", "No models with a recorded sweep cost are shown.", "sub")); return; }
  const then = paperTotals();
  const costs = points.map((p) => p.cost);
  const xMin = Math.pow(10, Math.floor(Math.log10(Math.min(...costs)))), xMax = Math.pow(10, Math.ceil(Math.log10(Math.max(...costs))));
  const yMin = Math.min(50, Math.floor((Math.min(...points.map((p) => p.score)) - 5) / 10) * 10), yMax = 90;
  const x = (c) => margin.left + ((Math.log10(c) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin))) * (w - margin.left - margin.right);
  const y = (s) => margin.top + (1 - (s - yMin) / (yMax - yMin)) * (h - margin.top - margin.bottom);
  const root = svg("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", class: "hero-svg", "aria-label": "Cost against score for every model, each drawn as a glyph of its five domain scores, with the cost-performance frontier" });

  // Grid: decades on x, tens on y.
  for (let c = xMin; c <= xMax; c *= 10) {
    root.append(svg("line", { x1: x(c), x2: x(c), y1: margin.top, y2: h - margin.bottom, class: "chart-grid" }),
                svg("text", { x: x(c), y: h - margin.bottom + 22, class: "hero-tick", "text-anchor": "middle" }, c >= 1 ? `$${c}` : `$${c}`));
  }
  for (let s = yMin; s <= yMax; s += 10) {
    root.append(svg("line", { x1: margin.left, x2: w - margin.right, y1: y(s), y2: y(s), class: "chart-grid" }),
                svg("text", { x: margin.left - 12, y: y(s) + 4, class: "hero-tick", "text-anchor": "end" }, s));
  }
  root.append(svg("text", { x: w - margin.right, y: h - margin.bottom + 46, class: "hero-axis", "text-anchor": "end" }, "sweep cost, USD, log scale"),
              svg("text", { x: margin.left - 12, y: margin.top - 22, class: "hero-axis", "text-anchor": "end" }, "score"));

  // The 2025 field on the left edge: one tick per paper model, most below the axis floor.
  if (then.length) {
    const lo = Math.min(...then.map((t) => t.value)), hi = Math.max(...then.map((t) => t.value));
    then.forEach((t) => { if (t.value >= yMin) root.append(svg("line", { x1: margin.left - 46, x2: margin.left - 30, y1: y(t.value), y2: y(t.value), class: "hero-then" })); });
    const below = then.filter((t) => t.value < yMin).length;
    root.append(svg("text", { x: margin.left - 50, y: y(Math.max(hi, yMin)) - 8, class: "hero-then-label", "text-anchor": "end" }, "2025"),
                svg("text", { x: margin.left - 50, y: y(Math.max(hi, yMin)) + 6, class: "hero-then-label", "text-anchor": "end" }, `${then.length} models`),
                svg("text", { x: margin.left - 50, y: y(Math.max(hi, yMin)) + 20, class: "hero-then-label", "text-anchor": "end" }, `${lo.toFixed(0)} to ${hi.toFixed(0)}`));
    if (below) root.append(svg("text", { x: margin.left - 50, y: y(yMin) + 4, class: "hero-then-label", "text-anchor": "end" }, `${below} below ${yMin}`));
  }

  // Frontier staircase and the region beneath it.
  const frontier = paretoFrontier(points);
  if (frontier.length) {
    let d = `M${x(frontier[0].cost)},${y(frontier[0].score)}`;
    for (let i = 1; i < frontier.length; i++) d += ` L${x(frontier[i].cost)},${y(frontier[i - 1].score)} L${x(frontier[i].cost)},${y(frontier[i].score)}`;
    const last = frontier[frontier.length - 1];
    root.append(svg("path", { d: `${d} L${x(xMax)},${y(last.score)} L${x(xMax)},${y(yMin)} L${x(frontier[0].cost)},${y(yMin)} Z`, class: "hero-frontier-area" }));
    root.append(svg("path", { d: `${d} L${x(xMax)},${y(last.score)}`, class: "hero-frontier" }));
  }

  // Glyph key.
  const kx = margin.left + 130, ky = margin.top + 80, kr = 44;
  root.append(svg("path", { d: glyphPath(kx, ky, kr, [100, 100, 100, 100, 100]), class: "hero-key-ring" }));
  DOMAINS.forEach((d, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / DOMAINS.length;
    root.append(svg("line", { x1: kx, y1: ky, x2: kx + kr * Math.cos(a), y2: ky + kr * Math.sin(a), class: "hero-key-axis" }));
    const lx = kx + (kr + 10) * Math.cos(a), ly = ky + (kr + 10) * Math.sin(a);
    root.append(svg("text", { x: lx, y: ly + 4, class: "hero-key-label", "text-anchor": Math.abs(Math.cos(a)) < 0.3 ? "middle" : Math.cos(a) > 0 ? "start" : "end" }, DOMAIN_LABEL[d] || humanize(d)));
  });
  root.append(svg("text", { x: kx - kr - 30, y: ky + kr + 34, class: "hero-key-label", "text-anchor": "start" }, `glyph axes: ${HERO.floor} at the centre, 100 at the ring`));

  // Glyphs, weakest first so leaders draw on top; labels placed to avoid each other.
  const ordered = points.slice().sort((a, b) => a.score - b.score);
  const frontierIdsHere = new Set(frontier.map((p) => p.model.id));
  ordered.forEach((p) => {
    const cx = x(p.cost), cy = y(p.score);
    const g = svg("g", { class: `hero-glyph${frontierIdsHere.has(p.model.id) ? " on-frontier" : ""}`, tabindex: 0, role: "button", "aria-label": `${p.model.label}, score ${p.score.toFixed(1)}, sweep cost $${p.cost.toFixed(2)}` });
    g.append(svg("path", { d: glyphPath(cx, cy, glyph, [100, 100, 100, 100, 100]), class: "hero-glyph-ring" }));
    g.append(svg("path", { d: glyphPath(cx, cy, glyph, p.domains), fill: p.model.color, stroke: p.model.color, class: "hero-glyph-shape" }));
    g.append(svg("circle", { cx, cy, r: 2.5, fill: p.model.color }));
    g.append(svg("title", {}, `${p.model.label} · ${p.score.toFixed(1)} · $${p.cost.toFixed(2)}\n${DOMAINS.map((d, i) => `${DOMAIN_LABEL[d] || humanize(d)}: ${p.domains[i].toFixed(1)}`).join("\n")}`));
    g.onclick = () => { location.hash = "leaderboard"; };
    g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); location.hash = "leaderboard"; } };
    root.append(g);
  });
  for (const l of heroLabels(points, x, y, { x0: margin.left, x1: w - margin.right, y0: margin.top, y1: h - margin.bottom })) {
    root.append(svg("text", { x: l.x, y: l.y, class: "hero-label", "text-anchor": l.anchor }, l.text));
  }

  host.append(root);
  const note = $("hero-note");
  if (note) note.textContent = `${points.length} models. Position is the sweep cost and the overall score; the shape is the score in each of the benchmark's five domains. The magenta line is the frontier: at each cost, the model no other beats for the same money or less. Grey ticks on the left are the ${then.length} models in the 2025 paper. Hover a glyph for its numbers.`;
}

renderHero();
