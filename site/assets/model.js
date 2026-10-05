// Data shaping for the dashboard. No DOM here, so it runs in Node tests too.

export function table({ columns, rows }) {
  return rows.map((row) => Object.fromEntries(columns.map((c, i) => [c, row[i]])));
}

export const monthIndex = (iso) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1;

const matches = (list, value) => !list.length || list.includes(value);

export function keep(row, filters) {
  return matches(filters.products, row.product) && matches(filters.regions, row.region);
}

const ratio = (num, den) => (den ? num / den : null);

export function totals(rows) {
  const t = {
    outstanding_principal: 0, active_loans: 0, amount_disbursed: 0, par30_principal: 0,
    npa_principal: 0, collected_against_demand: 0, demand_due: 0,
  };
  for (const row of rows) for (const key in t) t[key] += row[key] || 0;
  return {
    pos: t.outstanding_principal,
    active: t.active_loans,
    disbursed: t.amount_disbursed,
    par30: ratio(t.par30_principal, t.outstanding_principal),
    gnpa: ratio(t.npa_principal, t.outstanding_principal),
    ce: ratio(t.collected_against_demand, t.demand_due),
  };
}

export function kpiSeries(summary, months, filters) {
  const byMonth = new Map(months.map((m) => [m, []]));
  for (const row of summary) if (keep(row, filters)) byMonth.get(row.month)?.push(row);
  return months.map((month) => ({ month, ...totals(byMonth.get(month)) }));
}

// Relative change for amounts and counts, percentage points for ratios.
export function change(current, previous, kind) {
  if (current == null || previous == null) return null;
  if (kind === "points") return current - previous;
  return previous ? current / previous - 1 : null;
}

export function disbursements(summary, months, products, filters) {
  const index = new Map(months.map((m, i) => [m, i]));
  const series = new Map(
    products.filter((p) => matches(filters.products, p)).map((p) => [p, months.map(() => 0)]),
  );
  for (const row of summary) {
    const values = series.get(row.product);
    if (values && matches(filters.regions, row.region) && index.has(row.month)) {
      values[index.get(row.month)] += row.amount_disbursed;
    }
  }
  return series;
}

export function dpdBuckets(dpd, month, filters) {
  const buckets = new Map();
  for (const row of dpd) {
    if (row.month !== month || !keep(row, filters)) continue;
    const b = buckets.get(row.bucket) ?? { bucket: row.bucket, order: row.bucket_order, pos: 0, loans: 0 };
    b.pos += row.outstanding_principal;
    b.loans += row.loans;
    buckets.set(row.bucket, b);
  }
  const list = [...buckets.values()].sort((a, b) => a.order - b.order);
  const total = list.reduce((t, b) => t + b.pos, 0);
  return list.map((b) => ({ ...b, share: total ? b.pos / total : 0 }));
}

// A half-year cohort is drawn only as far as its youngest month has reached on book.
// Ever 30+ is cumulative, so a cohort-month whose loans have all closed keeps its last count.
export function vintageCurves(vintage, asOf, filters, minPoints = 4) {
  const limit = monthIndex(asOf);
  const cells = new Map();
  for (const row of vintage) {
    if (!matches(filters.products, row.product)) continue;
    const key = `${row.cohort_month}|${row.product}`;
    if (!cells.has(key)) cells.set(key, { start: monthIndex(row.cohort_month), loans: row.cohort_loans, ever: [] });
    cells.get(key).ever[row.months_on_book] = row.loans_ever_30_plus;
  }
  const cohorts = new Map();
  for (const cell of cells.values()) {
    const year = Math.floor(cell.start / 12);
    const firstHalf = cell.start % 12 < 6;
    const reached = limit - (year * 12 + (firstHalf ? 5 : 11));
    if (reached < minPoints - 1) continue;
    const name = `${year} H${firstHalf ? 1 : 2}`;
    if (!cohorts.has(name)) cohorts.set(name, { loans: 0, ever: Array(reached + 1).fill(0) });
    const cohort = cohorts.get(name);
    cohort.loans += cell.loans;
    let last = 0;
    for (let mob = 0; mob <= reached; mob++) {
      last = cell.ever[mob] ?? last;
      cohort.ever[mob] += last;
    }
  }
  return [...cohorts.keys()].sort().map((name) => {
    const { loans, ever } = cohorts.get(name);
    return { cohort: name, loans, points: ever.map((count, mob) => ({ mob, rate: ratio(count, loans), ever: count })) };
  });
}

export function leaderboard(branches, month, filters) {
  return branches
    .filter((row) => row.month === month && matches(filters.regions, row.region))
    .sort((a, b) => a.collection_rank - b.collection_rank || a.branch_name.localeCompare(b.branch_name));
}

const DATE_UTC = (iso) => new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10) || 1));
const monthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
const shortMonthFmt = new Intl.DateTimeFormat("en-GB", { month: "short", timeZone: "UTC" });
const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export const fmt = {
  crore(value, digits = 1) {
    if (value == null) return "–";
    const n = (value / 1e7).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return `₹${n} Cr`;
  },
  count: (value) => (value == null ? "–" : Math.round(value).toLocaleString("en-IN")),
  pct: (value, digits = 1) => (value == null ? "–" : `${(value * 100).toFixed(digits)}%`),
  month: (iso) => monthFmt.format(DATE_UTC(iso)),
  shortMonth: (iso) => shortMonthFmt.format(DATE_UTC(iso)),
  date: (iso) => dateFmt.format(DATE_UTC(iso)),
  title: (text) => text.charAt(0) + text.slice(1).toLowerCase(),
};

export function parseRoute(hash) {
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  return { route: path.replace(/^\/+|\/+$/g, "") || "dashboard", params: new URLSearchParams(query) };
}
