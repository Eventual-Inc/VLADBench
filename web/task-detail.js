// Expanded task row in the task matrix: the clip the model saw and the task on the left, every model's answer to
// every question on the right. Answers and per-question marks come from answers/<Task>.json, built by
// scripts/build_answers.py under the paper's scoring rules and checked against the released components.

const detailState = { cache: new Map(), question: 0, filter: "all", sort: "hardest", shown: 60, timer: null, frame: 0 };
const PAGE = 60;

function loadAnswers(task) {
  if (!detailState.cache.has(task.name)) {
    detailState.cache.set(task.name, fetch(`answers/${encodeURIComponent(task.name)}.json`).then((r) => {
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    }));
  }
  return detailState.cache.get(task.name);
}

function renderTaskDetail(task) {
  const row = element("tr", undefined, "detail-row");
  const cell = element("td");
  cell.colSpan = MODELS.length + 1;
  const content = element("div", undefined, "task-detail two-thirds");
  const scroller = document.querySelector("section.panel.matrix");
  if (scroller) content.style.width = `${scroller.clientWidth - 36}px`;
  const left = element("div", undefined, "detail-left");
  const right = element("div", undefined, "detail-right");
  content.append(left, right);
  cell.append(content);
  row.append(cell);
  detailState.question = 0; detailState.shown = PAGE; stopClip();
  right.append(element("p", "Loading answers…", "sub"));
  loadAnswers(task).then((data) => {
    detailState.data = data;
    paintLeft(task, data, left);
    paintGrid(task, data, right, left);
  }).catch(() => {
    right.replaceChildren(element("p", "Per-question answers could not be loaded. They are served next to this page as answers/<task>.json.", "sub"));
    paintLeft(task, null, left);
  });
  return row;
}

// ---- left pane: clip, question, scoring -------------------------------------------------------

function stopClip() {
  if (detailState.timer) clearInterval(detailState.timer);
  detailState.timer = null;
}

function clipPlayer(data, question) {
  const wrap = element("div", undefined, "clip");
  const urls = question.images.map((p) => data.base + p);
  const image = element("img", undefined, "clip-frame");
  image.alt = `${question.sequence || question.sample}, frame 1`;
  image.src = urls[0];
  const link = element("a"); link.href = urls[0]; link.target = "_blank"; link.rel = "noopener noreferrer";
  link.append(image);
  wrap.append(link);
  if (urls.length > 1) {
    const controls = element("div", undefined, "clip-controls");
    const toggle = element("button", "❚❚", "clip-button"); toggle.type = "button"; toggle.title = "Pause";
    const counter = element("span", `frame 1 / ${urls.length} · 1 fps`, "sub");
    const strip = element("div", undefined, "clip-strip");
    const ticks = urls.map((url, i) => { const t = element("i"); t.title = `Frame ${i + 1}`; t.onclick = () => { show(i); pause(); }; return t; });
    strip.append(...ticks);
    const show = (i) => {
      detailState.frame = i;
      image.src = urls[i]; link.href = urls[i]; image.alt = `${question.sequence || question.sample}, frame ${i + 1}`;
      counter.textContent = `frame ${i + 1} / ${urls.length} · 1 fps`;
      ticks.forEach((t, j) => t.classList.toggle("on", j === i));
    };
    const play = () => { stopClip(); detailState.timer = setInterval(() => show((detailState.frame + 1) % urls.length), 1000); toggle.textContent = "❚❚"; toggle.title = "Pause"; };
    const pause = () => { stopClip(); toggle.textContent = "▶"; toggle.title = "Play"; };
    toggle.onclick = () => (detailState.timer ? pause() : play());
    urls.forEach((u) => { const pre = new Image(); pre.src = u; });
    controls.append(toggle, strip, counter);
    wrap.append(controls);
    show(0); play();
  }
  return wrap;
}

function paintLeft(task, data, left) {
  stopClip();
  left.replaceChildren();
  const sample = MODELS[0].tasks[task.name];
  const question = data ? data.questions[detailState.question] : null;
  if (question) left.append(clipPlayer(data, question));
  const meta = element("div", undefined, "detail-meta");
  meta.append(element("h4", humanize(task.name)), element("p", `${humanize(task.category)} · ${humanize(task.group)} · ${(data ? data.questions.length : task.items.length).toLocaleString()} questions`, "sub"));
  if (task.description) meta.append(element("p", task.description));
  if (question) {
    const q = element("div", undefined, "detail-question");
    q.append(element("b", `Question ${question.question} · ${question.sequence || question.sample}`), element("p", question.prompt),
             element("p", `Reference: ${goldText(question.gold)}`, "gold"));
    meta.append(q);
  }
  const scoring = element("div", undefined, "detail-scoring");
  scoring.append(element("b", `Scoring · ${task.scoring_label || sample.scorer_function}`), element("p", task.scoring_rule || ""));
  const w = weightsFor(sample);
  const parts = [`${percent(100 * w.accuracy, 0)} ${humanize(sample.components.accuracy_name || "accuracy")}`];
  if (w.other) parts.push(`${percent(100 * w.other, 0)} ${humanize(sample.components.other_name)}`);
  parts.push(`${percent(100 * w.instruction_following, 0)} instruction following`);
  scoring.append(element("p", `Task score = ${parts.join(" + ")}.`, "sub"));
  meta.append(scoring);
  const actions = element("div", undefined, "detail-actions");
  const tryIt = element("a", "Try this task yourself →", "detail-button");
  tryIt.href = `self-test.html?task=${encodeURIComponent(task.name)}`;
  actions.append(tryIt);
  if (question) {
    const open = element("button", "Open in inspector", "detail-button"); open.type = "button";
    open.onclick = () => inspectQuestion(task, { ...question, images: question.images.map((p) => ({ path: data.base + p })), id: question.sample }, null);
    actions.append(open);
  }
  meta.append(actions);
  left.append(meta);
}

// ---- right pane: the answer grid ----------------------------------------------------------------

function gridModels(data) {
  return MODELS.filter((m) => data.models.includes(m.id));
}

function rowsFor(data, models) {
  const rows = data.questions.map((q) => {
    const marks = models.map((m) => q.answers[m.id]);
    const right = marks.filter((a) => a && a[1] >= 1).length;
    return { q, marks, right, wrong: marks.length - right };
  });
  const filtered = detailState.filter === "disagree" ? rows.filter((r) => r.right && r.wrong)
    : detailState.filter === "allwrong" ? rows.filter((r) => !r.right)
    : rows;
  if (detailState.sort === "hardest") filtered.sort((a, b) => a.right - b.right || a.q.i - b.q.i);
  return filtered;
}

const BOILERPLATE = [/^The (sequence|image) is from [^.]+\. /, /^Based on the given sequence of images, /, /^In the (image|sequence), /, /^(At|at) the moment of the last image, /];
function shortPrompt(prompt) {
  let text = prompt;
  for (const pattern of BOILERPLATE) text = text.replace(pattern, "");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function goldText(gold) {
  return Array.isArray(gold) ? `[${gold.join(", ")}]` : String(gold);
}

function markCell(mark, kind) {
  const cell = element("td", undefined, "ans");
  if (!mark) { cell.textContent = "—"; cell.classList.add("na"); return cell; }
  const [text, accuracy, instruction, other] = mark;
  const { background, ink } = heatColor(100 * accuracy);
  cell.style.background = background; cell.style.color = ink;
  const span = element("span", text || "(empty)", "ans-text");
  cell.append(span);
  const notes = [`${percent(100 * accuracy, 0)} credit`, instruction ? "followed the format" : "did not follow the requested format"];
  if (kind === "box" && other != null) notes.push(`IoU ${other.toFixed(2)}`);
  cell.title = `${text || "(empty answer)"}\n${notes.join(" · ")}`;
  if (!instruction) cell.classList.add("noformat");
  return cell;
}

function totalsRows(data, models, sample) {
  const rows = [];
  const w = weightsFor(sample);
  const line = (label, values, strong) => {
    const tr = element("tr", undefined, "totals" + (strong ? " strong" : ""));
    const th = element("th", label); th.colSpan = 3; tr.append(th);
    values.forEach((v) => tr.append(element("td", v == null ? "—" : strong ? v.toFixed(1) : percent(100 * v, 0), "num")));
    return tr;
  };
  const comp = (key) => models.map((m) => m.tasks[data.task]?.components?.[key]);
  rows.push(line(humanize(sample.components.accuracy_name || "accuracy"), comp("accuracy")));
  if (w.other || sample.components.other) rows.push(line(humanize(sample.components.other_name || "other"), comp("other")));
  rows.push(line("instruction following", comp("instruction_following")));
  rows.push(line("task score", models.map((m) => composite(m, data.task)), true));
  return rows;
}

function paintGrid(task, data, right, left) {
  right.replaceChildren();
  const models = gridModels(data);
  const sample = MODELS[0].tasks[task.name];
  const rows = rowsFor(data, models);

  const bar = element("div", undefined, "grid-bar");
  const pills = element("div", undefined, "grid-pills");
  [["all", `All ${data.questions.length.toLocaleString()}`], ["disagree", "Models disagree"], ["allwrong", "Everyone wrong"]].forEach(([key, label]) => {
    const b = element("button", label, "pill" + (detailState.filter === key ? " on" : "")); b.type = "button";
    b.onclick = () => { detailState.filter = key; detailState.shown = PAGE; paintGrid(task, data, right, left); };
    pills.append(b);
  });
  const sort = element("select", undefined, "grid-sort");
  [["hardest", "Hardest first"], ["dataset", "Dataset order"]].forEach(([v, l]) => { const o = element("option", l); o.value = v; o.selected = detailState.sort === v; sort.append(o); });
  sort.onchange = () => { detailState.sort = sort.value; paintGrid(task, data, right, left); };
  bar.append(pills, sort);
  right.append(bar);

  const scroller = element("div", undefined, "grid-scroll");
  const table = element("table", undefined, "answer-grid");
  table.style.minWidth = `${56 + 220 + 90 + 84 * models.length}px`;
  const thead = element("thead"); const head = element("tr");
  ["", "Question", "Reference"].forEach((t) => head.append(element("th", t)));
  models.forEach((m) => {
    const th = element("th", undefined, "model");
    const swatch = element("i", undefined, "swatch"); swatch.style.background = m.color;
    th.append(swatch, element("span", m.label)); th.title = m.label;
    head.append(th);
  });
  thead.append(head); table.append(thead);
  const body = element("tbody");
  rows.slice(0, detailState.shown).forEach(({ q, marks }) => {
    const tr = element("tr", undefined, q.i === detailState.question ? "current" : undefined);
    const thumb = element("td", undefined, "thumb");
    const img = element("img"); img.loading = "lazy"; img.src = data.base + q.images[0]; img.alt = "";
    thumb.append(img);
    const text = element("td", undefined, "qtext");
    text.append(element("span", shortPrompt(q.prompt), "ans-text"),
                element("span", `${q.sequence || q.sample} · q${q.question}`, "sub"));
    text.title = q.prompt;
    const gold = element("td", goldText(q.gold), "gold"); gold.title = goldText(q.gold);
    tr.append(thumb, text, gold);
    marks.forEach((mark) => tr.append(markCell(mark, q.kind)));
    tr.onclick = () => { detailState.question = q.i; body.querySelectorAll("tr.current").forEach((r) => r.classList.remove("current")); tr.classList.add("current"); paintLeft(task, data, left); };
    body.append(tr);
  });
  table.append(body);
  const tfoot = element("tfoot");
  const totals = totalsRows(data, models, sample);
  totals.forEach((r, k) => { r.querySelectorAll("th, td").forEach((c) => { c.style.bottom = `${(totals.length - 1 - k) * 27}px`; }); tfoot.append(r); });
  table.append(tfoot);
  scroller.append(table);
  right.append(scroller);

  const foot = element("div", undefined, "grid-foot");
  const remaining = rows.length - detailState.shown;
  if (remaining > 0) {
    const more = element("button", `Show ${Math.min(PAGE, remaining)} more of ${remaining.toLocaleString()} remaining`, "detail-button"); more.type = "button";
    more.onclick = () => { detailState.shown += PAGE; paintGrid(task, data, right, left); };
    foot.append(more);
  } else if (!rows.length) {
    foot.append(element("p", "No questions match this filter.", "sub"));
  }
  foot.append(element("p", "Cells show each model's answer, tinted by the credit it earned under the paper's scoring code; a dotted underline means the answer was not in the requested format. Marks are our per-question reading of that code and sum exactly to the components in the bottom rows. Click a row to see its clip on the left.", "sub"));
  right.append(foot);
}
