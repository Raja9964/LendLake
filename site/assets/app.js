import {
  change, disbursements, dpdBuckets, fmt, kpiSeries, leaderboard, parseRoute, table, vintageCurves,
} from "./model.js";

const DATASETS = ["summary", "dpd", "vintage", "branches", "products"];
const TITLES = { dashboard: "Portfolio dashboard", about: "About this data" };
const SHORT_NAMES = { HL_STD: "Home loan", HL_AFF: "Affordable HL", PL_SAL: "PL salaried", PL_SE: "PL self-employed" };
const BUCKETS = { Current: "Current", "1-30": "1–30 days", "31-60": "31–60 days", "61-90": "61–90 days", "90+": "90+ days" };
const COHORT_COLORS = 4;
const TOP_BRANCHES = 8;
const motion = !matchMedia("(prefers-reduced-motion: reduce)").matches;

const KPIS = [
  { key: "pos", label: "Principal outstanding", show: (v) => fmt.crore(v), kind: "relative", better: "up",
    info: "Unpaid principal on every open loan at month end." },
  { key: "active", label: "Active loans", show: fmt.count, kind: "relative", better: "up",
    info: "Loans still open at month end." },
  { key: "disbursed", label: "Disbursed this month", show: (v) => fmt.crore(v), kind: "relative", better: "up",
    info: "Amount paid out to borrowers during the month." },
  { key: "par30", label: "PAR 30+", show: fmt.pct, kind: "points", better: "down",
    info: "Share of principal outstanding on loans more than 30 days past due." },
  { key: "gnpa", label: "GNPA (90+)", show: fmt.pct, kind: "points", better: "down",
    info: "Share of principal outstanding on loans more than 90 days past due." },
  { key: "ce", label: "Collection efficiency", show: fmt.pct, kind: "points", better: "up",
    info: "EMIs collected by month end as a share of the EMIs due that month." },
];

const state = {
  data: null, months: [], productCodes: [], regionCodes: [], cohorts: [],
  month: null, products: [], regions: [], dpdView: "all", allBranches: false, series: [],
  charts: new Map(),
};

const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.flat().filter((c) => c != null && c !== false));
  return node;
}

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

const productName = (code) =>
  SHORT_NAMES[code] ?? state.data.products.find((p) => p.product === code)?.product_name ?? code;
const filters = () => ({ products: state.products, regions: state.regions });

// ---------- data ----------

async function getJson(path) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  return response.json();
}

async function loadData() {
  const [manifest, ...files] = await Promise.all(["manifest", ...DATASETS].map((n) => getJson(`data/${n}.json`)));
  const data = { manifest };
  DATASETS.forEach((name, i) => { data[name] = table(files[i]); });
  return data;
}

// ---------- url state ----------

function readParams(params) {
  const month = params.get("month");
  state.month = (month && state.months.find((m) => m.startsWith(month))) || state.months.at(-1);
  const list = (key) => (params.get(key) || "").split(",").filter(Boolean);
  state.products = list("product").filter((p) => state.productCodes.includes(p));
  state.regions = list("region").map((r) => r.toUpperCase()).filter((r) => state.regionCodes.includes(r));
}

function dashboardHash() {
  const parts = [];
  if (state.month !== state.months.at(-1)) parts.push(`month=${state.month.slice(0, 7)}`);
  if (state.products.length) parts.push(`product=${state.products.map(encodeURIComponent).join(",")}`);
  if (state.regions.length) parts.push(`region=${state.regions.map((r) => r.toLowerCase()).join(",")}`);
  return `#/dashboard${parts.length ? `?${parts.join("&")}` : ""}`;
}

function commit() {
  const hash = dashboardHash();
  if ((location.hash || "#/dashboard") !== hash) history.replaceState(null, "", hash);
  for (const link of document.querySelectorAll('[data-route="dashboard"], [data-home]')) link.href = hash;
  renderDashboard();
}

// ---------- theme ----------

const darkQuery = matchMedia("(prefers-color-scheme: dark)");
const isDark = () => (document.documentElement.dataset.theme || (darkQuery.matches ? "dark" : "light")) === "dark";

function syncThemeButton() {
  $("#theme-toggle").setAttribute("aria-label", isDark() ? "Switch to light theme" : "Switch to dark theme");
}

function colors() {
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    ink: v("--ink"), ink2: v("--ink-2"), muted: v("--muted"), grid: v("--grid"), axis: v("--axis"),
    surface: v("--surface"), raised: v("--raised"), border: v("--border-strong"), band: v("--band"), accent: v("--accent"),
    series: [1, 2, 3, 4].map((i) => v(`--series-${i}`)),
    dpd: [1, 2, 3, 4, 5].map((i) => v(`--dpd-${i}`)),
    cohort: [1, 2, 3, 4].map((i) => v(`--cohort-${i}`)),
  };
}

const productColor = (c, code) => c.series[state.productCodes.indexOf(code) % c.series.length];

// ---------- filters ----------

function buildFilters() {
  const select = $("#f-month");
  select.replaceChildren(...[...state.months].reverse().map((m) => el("option", { value: m, text: fmt.month(m) })));
  select.addEventListener("change", () => { state.month = select.value; commit(); });
  $("#m-prev").addEventListener("click", () => stepMonth(-1));
  $("#m-next").addEventListener("click", () => stepMonth(1));
  $("#f-reset").addEventListener("click", () => {
    state.month = state.months.at(-1);
    state.products = [];
    state.regions = [];
    commit();
  });

  const c = colors();
  chipGroup($("#f-product"), state.productCodes, "products", (code) => [
    el("span", { class: "key", "data-product": code, style: `background:${productColor(c, code)}` }),
    productName(code),
  ]);
  chipGroup($("#f-region"), state.regionCodes, "regions", (region) => [fmt.title(region)]);
}

function chipGroup(root, values, key, label) {
  const toggle = (value) => {
    if (value === null) state[key] = [];
    else if (state[key].includes(value)) state[key] = state[key].filter((v) => v !== value);
    else state[key] = values.filter((v) => v === value || state[key].includes(v));
    if (state[key].length === values.length) state[key] = [];
    commit();
  };
  root.replaceChildren(
    el("button", { type: "button", class: "chip", "data-value": "", onclick: () => toggle(null) }, "All"),
    ...values.map((value) =>
      el("button", { type: "button", class: "chip", "data-value": value, onclick: () => toggle(value) }, label(value))),
  );
}

function stepMonth(offset) {
  const i = state.months.indexOf(state.month) + offset;
  if (i >= 0 && i < state.months.length) {
    state.month = state.months[i];
    commit();
  }
}

function syncFilters() {
  $("#f-month").value = state.month;
  const i = state.months.indexOf(state.month);
  $("#m-prev").disabled = i <= 0;
  $("#m-next").disabled = i >= state.months.length - 1;
  for (const [root, selected] of [[$("#f-product"), state.products], [$("#f-region"), state.regions]]) {
    for (const chip of root.children) {
      const value = chip.dataset.value;
      chip.setAttribute("aria-pressed", String(value ? selected.includes(value) : !selected.length));
    }
  }
  $("#f-reset").hidden = state.month === state.months.at(-1) && !state.products.length && !state.regions.length;
  const c = colors();
  for (const key of document.querySelectorAll("#f-product .key")) key.style.background = productColor(c, key.dataset.product);
}

// ---------- KPI tiles ----------

function buildKpis() {
  $("#kpis").replaceChildren(...KPIS.map((kpi) => {
    const tip = el("div", { class: "tip", id: `tip-${kpi.key}`, role: "tooltip", hidden: true, text: kpi.info });
    const info = el("button", {
      type: "button", class: "info", "aria-label": `About ${kpi.label}`, "aria-expanded": "false",
      "aria-describedby": `tip-${kpi.key}`,
      onclick: (event) => {
        event.stopPropagation();
        const open = tip.hidden;
        closeTips();
        tip.hidden = !open;
        info.setAttribute("aria-expanded", String(open));
      },
    }, "i");
    return el("div", { class: "kpi", "data-kpi": kpi.key },
      el("div", { class: "kpi-label" }, el("span", { text: kpi.label }), info),
      el("div", { class: "kpi-value" }),
      el("div", { class: "kpi-delta" }),
      el("div", { class: "spark", "aria-hidden": "true" }),
      tip);
  }));
  document.addEventListener("click", closeTips);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeTips(); });
  new ResizeObserver(() => drawSparklines()).observe($("#kpis"));
}

function closeTips() {
  for (const tip of document.querySelectorAll(".tip")) tip.hidden = true;
  for (const info of document.querySelectorAll(".info")) info.setAttribute("aria-expanded", "false");
}

function arrow(direction) {
  const d = direction > 0 ? "M5 1l4 7H1z" : direction < 0 ? "M5 9L1 2h8z" : "M1 4h8v2H1z";
  return svg("svg", { class: "arrow", viewBox: "0 0 10 10", "aria-hidden": "true" }, svg("path", { d }));
}

function renderKpis() {
  const i = state.months.indexOf(state.month);
  const now = state.series[i];
  const prev = state.series[i - 1];
  for (const kpi of KPIS) {
    const tile = $(`[data-kpi="${kpi.key}"]`);
    $(".kpi-value", tile).textContent = kpi.show(now[kpi.key]);
    const delta = $(".kpi-delta", tile);
    const diff = prev ? change(now[kpi.key], prev[kpi.key], kpi.kind) : null;
    if (diff == null) {
      delta.className = "kpi-delta";
      delta.replaceChildren(el("span", { class: "vs", text: prev ? "No comparison" : "First month of history" }));
      continue;
    }
    const flat = Math.abs(diff) < (kpi.kind === "points" ? 0.00005 : 0.0005);
    const direction = flat ? 0 : Math.sign(diff);
    const good = (direction > 0) === (kpi.better === "up");
    delta.className = `kpi-delta ${flat ? "flat" : good ? "good" : "bad"}`;
    const text = kpi.kind === "points"
      ? `${Math.abs(diff * 100).toFixed(1)} pp`
      : `${Math.abs(diff * 100).toFixed(1)}%`;
    const word = flat ? "Flat" : direction > 0 ? "Up" : "Down";
    delta.replaceChildren(
      arrow(direction),
      el("span", { class: "num", text: flat ? "Flat" : text, "aria-label": `${word} ${text}` }),
      el("span", { class: "vs", text: `vs ${fmt.shortMonth(prev.month)}` }),
    );
  }
  drawSparklines();
}

function drawSparklines() {
  if (!state.series.length) return;
  const c = colors();
  const end = state.months.indexOf(state.month);
  const points = state.series.slice(Math.max(0, end - 11), end + 1);
  for (const kpi of KPIS) {
    const box = $(`[data-kpi="${kpi.key}"] .spark`);
    const width = box.clientWidth;
    const values = points.map((p) => p[kpi.key]).filter((v) => v != null);
    if (!width || values.length < 2) {
      box.replaceChildren();
      continue;
    }
    const height = 30;
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const x = (j) => 4 + (j * (width - 8)) / (values.length - 1);
    const y = (v) => (hi === lo ? height / 2 : 4 + ((hi - v) * (height - 8)) / (hi - lo));
    const line = values.map((v, j) => `${j ? "L" : "M"}${x(j).toFixed(1)},${y(v).toFixed(1)}`).join("");
    const last = values.length - 1;
    box.replaceChildren(svg("svg", { viewBox: `0 0 ${width} ${height}`, width, height },
      svg("path", { d: line, fill: "none", stroke: c.axis, "stroke-width": 1.5, "stroke-linejoin": "round", "stroke-linecap": "round" }),
      svg("circle", { cx: x(last), cy: y(values[last]), r: 3.5, fill: c.accent, stroke: c.surface, "stroke-width": 2 })));
  }
}

// ---------- charts ----------

let rerender;

function chart(id) {
  if (!window.echarts) return null;
  let instance = state.charts.get(id);
  if (!instance) {
    const node = document.getElementById(id);
    instance = window.echarts.init(node, null, { renderer: "svg" });
    let width = node.clientWidth;
    new ResizeObserver(() => {
      if (!node.clientWidth || !node.clientHeight) return;
      instance.resize();
      if (Math.abs(node.clientWidth - width) > 40) {
        width = node.clientWidth;
        clearTimeout(rerender);
        rerender = setTimeout(renderCharts, 120);
      }
    }).observe(node);
    if (id === "chart-disb") instance.getZr().on("click", (event) => pickMonth(instance, event));
    state.charts.set(id, instance);
  }
  return instance;
}

function pickMonth(instance, event) {
  const point = [event.offsetX, event.offsetY];
  if (!instance.containPixel("grid", point)) return;
  const month = state.months[instance.convertFromPixel({ xAxisIndex: 0 }, point)[0]];
  if (month && month !== state.month) {
    state.month = month;
    commit();
  }
}

function baseOption(c) {
  return {
    animation: motion,
    animationDuration: 350,
    animationDurationUpdate: 300,
    textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: c.ink2 },
    tooltip: {
      backgroundColor: c.raised, borderColor: c.border, borderWidth: 1, padding: [8, 10],
      textStyle: { color: c.ink, fontSize: 12 }, confine: true,
      extraCssText: "border-radius:10px;box-shadow:0 10px 30px -10px rgba(0,0,0,.3);",
    },
  };
}

function tooltip(title, rows, extra) {
  return el("div", { class: "tt" },
    el("div", { class: "tt-title", text: title }),
    rows.map((r) => el("div", { class: `tt-row${r.total ? " tt-total" : ""}` },
      r.color ? el("span", { class: "tt-key", style: `background:${r.color}` }) : null,
      el("span", { class: "tt-val", text: r.value }),
      el("span", { class: "tt-name", text: r.name }))),
    extra ? el("div", { class: "tt-hint", text: extra }) : null);
}

function setChart(id, option) {
  const instance = chart(id);
  if (instance) instance.setOption(option, { notMerge: true });
  return instance;
}

function emptyChart(id, message) {
  const instance = chart(id);
  if (!instance) return;
  const c = colors();
  instance.setOption({
    ...baseOption(c),
    title: { text: message, left: "center", top: "middle", textStyle: { color: c.muted, fontSize: 13, fontWeight: 400 } },
  }, { notMerge: true });
}

function renderDisbursements() {
  const c = colors();
  const series = disbursements(state.data.summary, state.months, state.productCodes, filters());
  const node = document.getElementById("chart-disb");
  const perBar = (node.clientWidth - 60) / state.months.length;
  const every = perBar >= 34 ? 1 : perBar >= 17 ? 3 : 6;
  const selected = state.months.indexOf(state.month);
  const topOf = state.months.map((_, m) => [...series.keys()].filter((code) => series.get(code)[m] > 0).at(-1));
  const totals = state.months.map((_, m) => [...series.values()].reduce((t, values) => t + values[m], 0));

  renderTable("card-disb", ["Month", ...[...series.keys()].map(productName), "Total"],
    [...state.months.keys()].reverse().map((m) => [
      fmt.month(state.months[m]), ...[...series.values()].map((v) => fmt.crore(v[m], 2)), fmt.crore(totals[m], 2),
    ]));

  setChart("chart-disb", {
    ...baseOption(c),
    grid: { left: 4, right: 8, top: 36, bottom: 4, containLabel: true },
    legend: {
      top: 0, left: 0, selectedMode: false, icon: "roundRect", itemWidth: 10, itemHeight: 10, itemGap: 14,
      textStyle: { color: c.ink2, fontSize: 12 },
    },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: c.band } },
      formatter: (params) => {
        const m = params[0].dataIndex;
        const rows = [...params].reverse().map((p) => ({ color: p.color, value: fmt.crore(p.value * 1e7, 2), name: p.seriesName }));
        rows.push({ value: fmt.crore(totals[m], 2), name: "Total", total: true });
        return tooltip(fmt.month(state.months[m]), rows, m === selected ? "Selected month" : "Click to select this month");
      },
    },
    xAxis: {
      type: "category",
      data: state.months,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: c.axis } },
      axisLabel: {
        color: c.muted, fontSize: 11, interval: (i, value) => (Number(value.slice(5, 7)) - 1) % every === 0,
        formatter: (value) => (value.slice(5, 7) === "01"
          ? `{strong|${fmt.shortMonth(value)}}\n{year|${value.slice(0, 4)}}`
          : fmt.shortMonth(value)),
        rich: { strong: { color: c.ink2, fontSize: 11, fontWeight: 600 }, year: { color: c.muted, fontSize: 10, padding: [2, 0, 0, 0] } },
      },
    },
    yAxis: {
      type: "value",
      splitNumber: 4,
      axisLabel: { color: c.muted, fontSize: 11, formatter: (v) => `₹${v}` },
      splitLine: { lineStyle: { color: c.grid } },
    },
    series: [...series.entries()].map(([code, values], s) => ({
      name: productName(code),
      type: "bar",
      stack: "disbursed",
      barMaxWidth: 24,
      barCategoryGap: "30%",
      itemStyle: { color: productColor(c, code), borderColor: c.surface, borderWidth: 1 },
      emphasis: { disabled: true },
      data: values.map((v, m) => ({
        value: +(v / 1e7).toFixed(4),
        itemStyle: topOf[m] === code ? { borderRadius: [4, 4, 0, 0] } : undefined,
      })),
      markArea: s === 0 && selected >= 0 ? {
        silent: true,
        itemStyle: { color: c.band },
        data: [[{ xAxis: state.month }, { xAxis: state.month }]],
      } : undefined,
    })),
  });
}

function renderDpd() {
  const c = colors();
  const all = dpdBuckets(state.data.dpd, state.month, filters());
  const rows = state.dpdView === "overdue" ? all.filter((b) => b.order > 1) : all;
  const overdue = all.filter((b) => b.order > 1).reduce((t, b) => t + b.share, 0);
  $("#dpd-sub").textContent = all.length
    ? `Principal outstanding, ${fmt.month(state.month)}. ${fmt.pct(overdue)} is overdue.`
    : `Principal outstanding, ${fmt.month(state.month)}`;

  renderTable("card-dpd", ["Bucket", "POS", "Share of POS", "Loans"],
    all.map((b) => [BUCKETS[b.bucket] ?? b.bucket, fmt.crore(b.pos, 2), fmt.pct(b.share, 2), fmt.count(b.loans)]));
  if (!rows.length || !rows.some((b) => b.pos > 0)) {
    emptyChart("chart-dpd", "No open loans match these filters");
    return;
  }
  const max = Math.max(...rows.map((b) => b.pos));
  setChart("chart-dpd", {
    ...baseOption(c),
    grid: { left: 2, right: 6, top: 22, bottom: 0 },
    xAxis: { type: "value", show: false, max },
    yAxis: { type: "category", inverse: true, show: false, data: rows.map((b) => b.bucket) },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: "item",
      formatter: ({ dataIndex }) => {
        const b = rows[dataIndex];
        return tooltip(BUCKETS[b.bucket] ?? b.bucket, [
          { color: c.dpd[b.order - 1], value: fmt.crore(b.pos, 2), name: "principal outstanding" },
          { value: fmt.pct(b.share, 2), name: "of the book" },
          { value: fmt.count(b.loans), name: b.loans === 1 ? "loan" : "loans" },
        ]);
      },
    },
    series: [{
      type: "bar",
      barWidth: 12,
      barMinHeight: 2,
      data: rows.map((b) => ({ value: b.pos, itemStyle: { color: c.dpd[b.order - 1], borderRadius: [0, 4, 4, 0] } })),
      label: {
        show: true,
        position: [0, -17],
        formatter: ({ dataIndex }) => {
          const b = rows[dataIndex];
          return `{name|${BUCKETS[b.bucket] ?? b.bucket}}  {value|${fmt.crore(b.pos)}}  {share|${fmt.pct(b.share)}}`;
        },
        rich: {
          name: { color: c.ink, fontSize: 12, fontWeight: 600 },
          value: { color: c.ink2, fontSize: 12 },
          share: { color: c.muted, fontSize: 12 },
        },
      },
      emphasis: { itemStyle: { opacity: 0.85 } },
    }],
  });
}

function renderVintage() {
  const c = colors();
  const curves = vintageCurves(state.data.vintage, state.month, filters())
    .filter((curve) => state.cohorts.includes(curve.cohort));
  $("#vintage-note").hidden = !state.regions.length;

  const maxMob = Math.max(0, ...curves.flatMap((curve) => curve.points.map((p) => p.mob)));
  renderTable("card-vintage", ["Months on book", ...curves.map((curve) => curve.cohort)],
    Array.from({ length: maxMob + 1 }, (_, mob) => [String(mob), ...curves.map((curve) => {
      const point = curve.points[mob];
      return point ? fmt.pct(point.rate) : "";
    })]));
  if (!curves.length) {
    emptyChart("chart-vintage", "Cohorts appear once all their loans are three months on book");
    return;
  }
  const ramp = c.cohort.slice(c.cohort.length - state.cohorts.length);
  const color = (cohort) => ramp[state.cohorts.indexOf(cohort)];
  setChart("chart-vintage", {
    ...baseOption(c),
    grid: { left: 4, right: 58, top: 36, bottom: 24, containLabel: true },
    legend: {
      top: 0, left: 0, selectedMode: false, itemWidth: 14, itemHeight: 3, itemGap: 14, icon: "rect",
      textStyle: { color: c.ink2, fontSize: 12 },
    },
    tooltip: {
      ...baseOption(c).tooltip,
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: c.axis } },
      formatter: (params) => tooltip(`Month on book ${params[0].value[0]}`, params.map((p) => ({
        color: color(p.seriesName),
        value: fmt.pct(p.value[1]),
        name: `${p.seriesName} · ${fmt.count(p.data.ever)} of ${fmt.count(p.data.loans)} loans`,
      }))),
    },
    xAxis: {
      type: "value", min: 0, max: Math.max(6, Math.ceil(maxMob / 3) * 3), interval: 3,
      name: "Months on book", nameLocation: "middle", nameGap: 26,
      nameTextStyle: { color: c.muted, fontSize: 11 },
      axisLine: { lineStyle: { color: c.axis } }, axisTick: { show: false },
      axisLabel: { color: c.muted, fontSize: 11 }, splitLine: { show: false },
    },
    yAxis: {
      type: "value", min: 0, splitNumber: 4,
      axisLabel: { color: c.muted, fontSize: 11, formatter: (v) => `${Math.round(v * 1000) / 10}%` },
      splitLine: { lineStyle: { color: c.grid } },
    },
    series: curves.map((curve) => ({
      name: curve.cohort,
      type: "line",
      showSymbol: true,
      symbolSize: 8,
      lineStyle: { width: 2, color: color(curve.cohort), cap: "round", join: "round" },
      itemStyle: { color: color(curve.cohort), borderColor: c.surface, borderWidth: 2 },
      emphasis: { focus: "series", scale: false },
      endLabel: {
        show: true, formatter: curve.cohort, color: c.ink2, fontSize: 11, distance: 6,
        textBorderColor: c.surface, textBorderWidth: 3,
      },
      data: curve.points.map((p, j, all) => ({
        value: [p.mob, p.rate],
        ever: p.ever,
        loans: curve.loans,
        symbol: j === all.length - 1 ? "circle" : "none",
      })),
    })),
  });
}

function renderLeaderboard() {
  const rows = leaderboard(state.data.branches, state.month, filters());
  $("#branch-sub").textContent = `Ranked by overall collection efficiency, ${fmt.month(state.month)}`;
  $("#branch-note").hidden = !state.products.length;
  const more = $("#branch-more");
  more.hidden = rows.length <= TOP_BRANCHES;
  more.textContent = state.allBranches ? `Show top ${TOP_BRANCHES}` : `Show all ${rows.length} branches`;
  more.setAttribute("aria-expanded", String(state.allBranches));
  const body = $("#branch-rows");
  if (!rows.length) {
    body.replaceChildren(el("tr", {}, el("td", { colspan: 6, class: "empty", text: "No branches match these filters" })));
    return;
  }
  const shown = state.allBranches ? rows : rows.slice(0, TOP_BRANCHES);
  body.replaceChildren(...shown.map((r) => el("tr", {},
    el("td", { class: "rank" }, r.collection_rank <= 3 ? el("span", { class: "medal", text: r.collection_rank }) : String(r.collection_rank)),
    el("td", {}, el("div", { class: "branch" },
      el("span", { class: "branch-name", text: r.branch_name }),
      el("span", { class: "branch-meta", text: `${r.city} · ${fmt.title(r.region)}` }))),
    el("td", { class: "num", text: (r.outstanding_principal / 1e7).toFixed(2) }),
    el("td", { class: "num hide-sm", text: (r.amount_disbursed / 1e7).toFixed(2) }),
    el("td", { class: "num", text: fmt.pct(r.overall_collection_efficiency) }),
    el("td", { class: "num", text: fmt.pct(r.par30_ratio) }),
  )));
}

function renderTable(cardId, headers, rows) {
  const view = $(`#${cardId} .table-view`);
  view.replaceChildren(el("table", { class: "data-table" },
    el("thead", {}, el("tr", {}, headers.map((h, i) => el("th", { scope: "col", class: i ? "num" : null, text: h })))),
    el("tbody", {}, rows.map((row) => el("tr", {}, row.map((cell, i) => el("td", { class: i ? "num" : null, text: cell })))))));
}

function renderCharts() {
  if ($('[data-view="dashboard"]').hidden || !state.data) return;
  renderDisbursements();
  renderDpd();
  renderVintage();
}

// ---------- dashboard ----------

function renderDashboard() {
  const { manifest, branches } = state.data;
  state.series = kpiSeries(state.data.summary, state.months, filters());
  const branchCount = new Set(branches.filter((b) => b.month === state.month).map((b) => b.branch_code)).size;
  $("#dash-lede").textContent =
    `As of ${fmt.date(state.month)} · ${branchCount} branches in ${state.regionCodes.length} regions`;
  syncFilters();
  renderKpis();
  renderCharts();
  renderLeaderboard();

  const dbt = manifest.dbt;
  const pill = $("#run-pill");
  if (dbt) {
    pill.replaceChildren(
      svg("svg", { viewBox: "0 0 16 16", "aria-hidden": "true" }, svg("path", { d: "M3 8.5l3 3 7-7" })),
      `${dbt.tests_passed} of ${dbt.tests} dbt tests passed`);
    pill.hidden = false;
  }
  $("#dash-foot").replaceChildren(
    `Built by the CI pipeline on ${builtAt(manifest)} from ${manifest.months} monthly batches of synthetic data. `,
    el("a", { href: "#/about", text: "About this data" }));
}

function builtAt(manifest) {
  const d = new Date(manifest.built_at);
  if (Number.isNaN(d.getTime())) return manifest.built_at;
  const day = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(d);
  const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }).format(d);
  return `${day}, ${time} UTC`;
}

// ---------- about ----------

function renderAbout() {
  const m = state.data.manifest;
  const count = (n) => fmt.count(n);
  const datasetBytes = Object.values(m.datasets).reduce((t, d) => t + d.bytes, 0);
  const stage = (tag, color, title, text, value, unit) => el("li", { class: "stage" },
    el("span", { class: "stage-tag" }, el("i", { style: color ? `background:var(${color})` : null }), tag),
    el("h3", { text: title }),
    el("p", { text }),
    el("div", { class: "count" }, value, el("small", { text: unit })));
  const layer = (name) => m.layers[name] ?? { tables: 0, rows: 0 };
  $("#lineage").replaceChildren(
    stage("Sources", null, "Synthetic extracts", "CSV, JSON and JSON Lines files, one batch per month.",
      count(m.simulation?.batches ?? m.months), "monthly batches"),
    stage("Bronze", "--bronze", "raw schema", "Files land as text with batch, file and load-time columns.",
      count(layer("bronze").rows), `rows in ${layer("bronze").tables} tables`),
    stage("Silver", "--silver", "silver and snapshots", "Typed, cleaned and de-duplicated, with SCD2 customer history.",
      count(layer("silver").rows), `rows in ${layer("silver").tables} tables`),
    stage("Gold", "--gold", "gold schema", "Dimensions, facts and the marts this page reads.",
      count(layer("gold").rows), `rows in ${layer("gold").tables} tables`),
    stage("This page", "--series-1", "JSON export", "Read straight into your browser. No server involved.",
      `${Math.round(datasetBytes / 1024)} KB`, `in ${Object.keys(m.datasets).length} files`),
  );

  const facts = [
    ["Built", builtAt(m)],
    ["Run date", fmt.date(m.run_date)],
    ["History", `${fmt.month(m.first_month)} to ${fmt.month(m.run_date)} (${m.months} months)`],
  ];
  if (m.dbt) {
    facts.push(["dbt tests", el("span", { class: "pass" },
      svg("svg", { viewBox: "0 0 16 16", "aria-hidden": "true" }, svg("path", { d: "M3 8.5l3 3 7-7" })),
      `${m.dbt.tests_passed} of ${m.dbt.tests} passed`)]);
    facts.push(["dbt build", `${m.dbt.models} models, ${m.dbt.snapshots} snapshot, ${m.dbt.seeds} seeds on dbt ${m.dbt.version}`]);
  }
  if (m.simulation) facts.push(["Simulation", `Seed ${m.simulation.seed}, scale ${m.simulation.scale}`]);
  if (m.ci) {
    facts.push(["Commit", el("a", { href: m.ci.commit_url }, el("code", { text: m.ci.commit }))]);
    facts.push(["Workflow run", el("a", { href: m.ci.run_url, text: "Build log on GitHub Actions" })]);
  }
  $("#run-facts").replaceChildren(...facts.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", {}, v)]));

  const scale = m.simulation?.scale;
  $("#synthetic-copy").replaceChildren(
    el("p", { text: "Customers, applications, loans and payments all come from a seeded simulation in the repo. "
      + "The same seed always produces the same loan book, so each rebuild of this page shows the same numbers." }),
    el("p", { text: "The extracts are messy on purpose: duplicates, four date formats, Indian digit grouping, city "
      + "aliases, late-arriving rows and a schema change in mid-2024. Bronze keeps them as they arrive, Silver cleans "
      + "them up, and dbt tests check the result." }),
    el("p", { text: `No real borrower data is used anywhere.${scale ? ` This build runs at ${scale}× the default volume to keep CI fast.` : ""}` }),
  );

  $("#dataset-rows").replaceChildren(...Object.values(m.datasets).map((d) => el("tr", {},
    el("td", {}, el("a", { href: d.file }, el("code", { text: d.file.replace(/^data\//, "") }))),
    el("td", {}, el("code", { text: d.source })),
    el("td", { class: "num", text: count(d.rows) }))));
}

// ---------- routing ----------

function showView(name, focus) {
  for (const view of document.querySelectorAll(".view")) view.hidden = view.dataset.view !== name;
  for (const link of document.querySelectorAll("[data-route]")) {
    if (link.dataset.route === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.title = `${TITLES[name]} · LendLake`;
  if (focus) {
    window.scrollTo(0, 0);
    $(`[data-view="${name}"] h1`).focus({ preventScroll: true });
  }
}

function route(focus) {
  const { route: path, params } = parseRoute(location.hash);
  const name = TITLES[path] ? path : "dashboard";
  if (name === "dashboard") readParams(params);
  showView(name, focus);
  if (!state.data) return;
  if (name === "dashboard") commit();
  if (name === "about") renderAbout();
}

// ---------- boot ----------

function wireToggles() {
  for (const button of document.querySelectorAll("[data-table]")) {
    button.addEventListener("click", () => {
      const card = button.closest(".card");
      const on = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", String(on));
      $(".chart", card).hidden = on;
      $(".table-view", card).hidden = !on;
      if (!on) renderCharts();
    });
  }
  $("#branch-more").addEventListener("click", () => {
    state.allBranches = !state.allBranches;
    renderLeaderboard();
  });
  for (const button of document.querySelectorAll("[data-dpd]")) {
    button.addEventListener("click", () => {
      state.dpdView = button.dataset.dpd;
      for (const b of document.querySelectorAll("[data-dpd]")) b.setAttribute("aria-pressed", String(b === button));
      renderDpd();
    });
  }
}

function chartsUnavailable() {
  for (const card of document.querySelectorAll(".card")) {
    const chartNode = $(".chart", card);
    if (!chartNode) continue;
    chartNode.hidden = true;
    $(".table-view", card).hidden = false;
    $("[data-table]", card)?.remove();
  }
  $("#dash-foot").before(el("p", { class: "card-note", text: "The chart library didn't load, so the panels are shown as tables." }));
}

async function boot() {
  syncThemeButton();
  $("#theme-toggle").addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("lendlake-theme", next); } catch { /* storage may be blocked */ }
    syncThemeButton();
    if (state.data) { syncFilters(); drawSparklines(); renderCharts(); }
  });
  darkQuery.addEventListener("change", () => {
    syncThemeButton();
    if (state.data) { syncFilters(); drawSparklines(); renderCharts(); }
  });

  showView(TITLES[parseRoute(location.hash).route] ? parseRoute(location.hash).route : "dashboard");
  try {
    state.data = await loadData();
  } catch (error) {
    const message = $("#load-error");
    message.textContent = `The data files didn't load (${error.message}). Try refreshing the page.`;
    message.hidden = false;
    $("#dash-lede").textContent = "Data unavailable";
    return;
  }

  const { summary, products, manifest } = state.data;
  state.months = [...new Set(summary.map((r) => r.month))].sort();
  state.productCodes = products.map((p) => p.product);
  state.regionCodes = [...new Set(summary.map((r) => r.region))].sort();
  state.cohorts = vintageCurves(state.data.vintage, state.months.at(-1), { products: [], regions: [] })
    .map((curve) => curve.cohort).slice(-COHORT_COLORS);
  $("#notice-built").textContent = ` · refreshed ${fmt.date(manifest.built_at.slice(0, 10))}`;

  buildFilters();
  buildKpis();
  wireToggles();
  if (!window.echarts) chartsUnavailable();
  window.addEventListener("hashchange", () => route(true));
  route(false);
}

boot();
