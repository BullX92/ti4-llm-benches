// Generates a self-contained, styled report.html from a Promptfoo results JSON.
// Usage: node generate-report.mjs [inputJson] [outputHtml]

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const inputPath = resolve(__dirname, process.argv[2] ?? 'results.reasoning.json');
const outputPath = resolve(__dirname, process.argv[3] ?? 'report.html');
const inputFileLabel = basename(inputPath);

const raw = JSON.parse(readFileSync(inputPath, 'utf8'));

const shortProvider = (id) => String(id).split('/').pop() || id;

// Heuristically map an assertion expression to the schema field it validates.
const fieldOf = (value) => {
  const v = String(value ?? '');
  const m = v.match(/output\.([a-zA-Z_]\w*)/);
  if (m) return m[1];
  if (/typeof output === 'object'|!Array\.isArray/.test(v)) return 'structure';
  return 'other';
};

const data = {
  evalId: raw.evalId ?? null,
  timestamp: raw.results?.timestamp ?? null,
  results: (raw.results?.results ?? []).map((r) => ({
    testIdx: r.testIdx,
    testName: r.testCase?.metadata?.name ?? `Test ${r.testIdx}`,
    testDescription: r.testCase?.metadata?.description ?? '',
    question: r.vars?.question ?? '',
    providerId: r.provider?.id ?? '',
    providerLabel: shortProvider(r.provider?.id ?? ''),
    success: !!r.success,
    score: r.score ?? 0,
    latencyMs: r.latencyMs ?? 0,
    cost: r.cost ?? 0,
    tokenUsage: r.tokenUsage ?? null,
    error: r.error ?? null,
    output: r.response?.output ?? null,
    components: (r.gradingResult?.componentResults ?? []).map((c) => ({
      pass: !!c.pass,
      value: c.assertion?.value ?? '',
      reason: c.reason ?? '',
      field: fieldOf(c.assertion?.value),
    })),
  })),
};

const html = `<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>TI4 LLM Benchmark Report</title>
<style>
  :root {
    --bg: #0b0f1a;
    --panel: #131a2b;
    --panel-2: #1a2336;
    --border: #26314d;
    --text: #e6ecf5;
    --muted: #8a98b4;
    --accent: #6c8cff;
    --green: #3fd17a;
    --green-bg: rgba(63, 209, 122, 0.12);
    --red: #ff6b7d;
    --red-bg: rgba(255, 107, 125, 0.12);
    --amber: #ffc24b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: radial-gradient(1200px 600px at 80% -10%, #1c2742 0%, var(--bg) 55%);
    color: var(--text);
    font-family: "Segoe UI", system-ui, -apple-system, Roboto, sans-serif;
    line-height: 1.5;
  }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 32px 20px 80px; }
  header h1 { margin: 0 0 6px; font-size: 28px; letter-spacing: 0.2px; }
  header .meta { color: var(--muted); font-size: 13px; display: flex; gap: 16px; flex-wrap: wrap; }
  header .meta code { color: var(--accent); }
  h2 { margin: 40px 0 16px; font-size: 18px; font-weight: 600; }

  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
  .card {
    background: linear-gradient(180deg, var(--panel-2), var(--panel));
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px;
  }
  .card h3 { margin: 0 0 12px; font-size: 15px; font-family: ui-monospace, "Cascadia Code", monospace; }
  .stat-row { display: flex; justify-content: space-between; font-size: 13px; padding: 4px 0; }
  .stat-row span:first-child { color: var(--muted); }
  .bar { height: 8px; border-radius: 6px; background: var(--border); overflow: hidden; margin: 8px 0 12px; }
  .bar > i { display: block; height: 100%; background: linear-gradient(90deg, var(--green), #2fb86a); }
  .pill { font-size: 12px; padding: 2px 9px; border-radius: 999px; font-weight: 600; }
  .pill.pass { color: var(--green); background: var(--green-bg); }
  .pill.fail { color: var(--red); background: var(--red-bg); }

  table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  th, td { padding: 12px 14px; text-align: left; font-size: 13px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 600; background: var(--panel-2); }
  tbody tr:last-child td { border-bottom: none; }
  td.cell { text-align: center; font-weight: 700; }
  td.cell.pass { color: var(--green); }
  td.cell.fail { color: var(--red); }
  .modelname { font-family: ui-monospace, "Cascadia Code", monospace; }

  details.test { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 14px; overflow: hidden; }
  details.test > summary { cursor: pointer; padding: 16px 18px; list-style: none; display: flex; align-items: center; gap: 12px; }
  details.test > summary::-webkit-details-marker { display: none; }
  details.test > summary .tname { font-weight: 600; font-size: 15px; }
  details.test > summary .tdesc { color: var(--muted); font-size: 12px; font-weight: 400; }
  details.test[open] > summary { border-bottom: 1px solid var(--border); }
  .test-body { padding: 8px 18px 18px; }
  .question { color: var(--muted); font-size: 13px; margin: 10px 0 18px; padding: 10px 12px; background: var(--panel-2); border-radius: 8px; border-left: 3px solid var(--accent); white-space: pre-wrap; }

  .prov { border: 1px solid var(--border); border-radius: 10px; margin: 10px 0; }
  .prov > summary { cursor: pointer; padding: 12px 14px; display: flex; align-items: center; gap: 10px; list-style: none; }
  .prov > summary::-webkit-details-marker { display: none; }
  .prov .grow { flex: 1; }
  .prov .small { color: var(--muted); font-size: 12px; }
  .prov-body { padding: 4px 14px 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 780px) { .prov-body { grid-template-columns: 1fr; } }
  .panel-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--muted); margin: 4px 0 8px; }
  pre.json { margin: 0; background: #0a0e18; border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-size: 12px; overflow: auto; font-family: ui-monospace, "Cascadia Code", monospace; }
  .assert { display: flex; gap: 8px; font-size: 12px; padding: 6px 8px; border-radius: 6px; margin-bottom: 4px; }
  .assert.pass { background: var(--green-bg); }
  .assert.fail { background: var(--red-bg); }
  .assert .mark { font-weight: 700; }
  .assert.pass .mark { color: var(--green); }
  .assert.fail .mark { color: var(--red); }
  .assert code { font-family: ui-monospace, "Cascadia Code", monospace; color: var(--text); word-break: break-word; }
  .empty { color: var(--muted); font-style: italic; }

  /* Scientific section */
  .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  @media (max-width: 900px) { .chart-grid { grid-template-columns: 1fr; } }
  .chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; }
  .chart-card h3 { margin: 0 0 4px; font-size: 14px; font-weight: 600; }
  .chart-card .sub { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
  .chart-card.wide { grid-column: 1 / -1; }
  svg.chart { width: 100%; height: auto; display: block; }
  svg.chart text { fill: var(--muted); font-family: "Segoe UI", system-ui, sans-serif; }
  svg.chart .axis { stroke: var(--border); stroke-width: 1; }
  svg.chart .grid { stroke: var(--border); stroke-width: 1; stroke-dasharray: 3 4; opacity: 0.5; }
  svg.chart .err { stroke: var(--text); stroke-width: 1.5; opacity: 0.7; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--muted); margin-top: 10px; }
  .legend .item { display: flex; align-items: center; gap: 6px; }
  .legend .swatch { width: 12px; height: 12px; border-radius: 3px; }

  table.sci { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; font-variant-numeric: tabular-nums; }
  table.sci th, table.sci td { padding: 11px 12px; font-size: 13px; border-bottom: 1px solid var(--border); text-align: right; }
  table.sci th:first-child, table.sci td:first-child { text-align: left; }
  table.sci th { color: var(--muted); font-weight: 600; background: var(--panel-2); }
  table.sci tbody tr:last-child td { border-bottom: none; }
  table.sci .best { color: var(--green); font-weight: 700; }
  .heatcell { text-align: center; font-size: 12px; font-weight: 600; color: #0a0e18; }
  .note { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
  footer { margin-top: 50px; color: var(--muted); font-size: 12px; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>TI4 LLM Benchmark Report</h1>
    <div class="meta" id="meta"></div>
  </header>

  <h2>Modelle im Vergleich</h2>
  <div class="cards" id="summary"></div>

  <h2>Statistische Auswertung</h2>
  <div id="stats"></div>
  <p class="note">Genauigkeit = bestandene Assertions / Gesamt-Assertions. 95%-Konfidenzintervall nach Wilson-Score. Latenz als Mittelwert &plusmn; Standardabweichung &uuml;ber alle Testf&auml;lle.</p>

  <h2>Visualisierung der Benchmark-Scores</h2>
  <div class="chart-grid" id="charts"></div>

  <h2>Ergebnis-Matrix</h2>
  <div id="matrix"></div>

  <h2>Testdetails</h2>
  <div id="details"></div>

  <footer>Generiert aus ${inputFileLabel} &middot; promptfoo TI4 benchmark</footer>
</div>

<script id="data" type="application/json">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtMs = (ms) => ms >= 1000 ? (ms / 1000).toFixed(2) + ' s' : Math.round(ms) + ' ms';

// Header meta
const metaEl = document.getElementById('meta');
const ts = DATA.timestamp ? new Date(DATA.timestamp).toLocaleString('de-DE') : 'unbekannt';
metaEl.innerHTML = '<span>Lauf: <code>' + esc(DATA.evalId ?? '-') + '</code></span><span>Zeitpunkt: ' + esc(ts) + '</span><span>' + DATA.results.length + ' Ergebnisse</span>';

// Group by provider
const providers = {};
const tests = {};
for (const r of DATA.results) {
  (providers[r.providerLabel] ??= []).push(r);
  (tests[r.testIdx] ??= { name: r.testName, description: r.testDescription, question: r.question, rows: [] }).rows.push(r);
}

// Summary cards
const summaryEl = document.getElementById('summary');
summaryEl.innerHTML = Object.entries(providers).map(([name, rows]) => {
  const passed = rows.filter(r => r.success).length;
  const total = rows.length;
  let aPass = 0, aTotal = 0, latency = 0, tokens = 0, cost = 0;
  for (const r of rows) {
    aPass += r.components.filter(c => c.pass).length;
    aTotal += r.components.length;
    latency += r.latencyMs;
    tokens += r.tokenUsage?.total ?? 0;
    cost += r.cost ?? 0;
  }
  const pct = aTotal ? Math.round((aPass / aTotal) * 100) : 0;
  return \`<div class="card">
    <h3>\${esc(name)}</h3>
    <div class="bar"><i style="width:\${pct}%"></i></div>
    <div class="stat-row"><span>Tests bestanden</span><span><span class="pill \${passed===total?'pass':'fail'}">\${passed}/\${total}</span></span></div>
    <div class="stat-row"><span>Assertions</span><span>\${aPass}/\${aTotal} (\${pct}%)</span></div>
    <div class="stat-row"><span>Ø Latenz</span><span>\${fmtMs(latency/Math.max(rows.length,1))}</span></div>
    <div class="stat-row"><span>Tokens</span><span>\${tokens}</span></div>
    <div class="stat-row"><span>Kosten</span><span>$\${cost.toFixed(4)}</span></div>
  </div>\`;
}).join('');

const provNames = Object.keys(providers);
const palette = ['#6c8cff', '#3fd17a', '#ffc24b', '#ff6b7d', '#36c6d3', '#b78cff', '#ff9f6b', '#7de08a'];
const colorOf = {};
provNames.forEach((p, i) => { colorOf[p] = palette[i % palette.length]; });

// ---- Statistics helpers ----
const mean = (a) => a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0;
const std = (a) => { if (a.length < 2) return 0; const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };
// Wilson score interval (95%, z = 1.96)
function wilson(pass, n) {
  if (!n) return { p: 0, low: 0, high: 0 };
  const z = 1.96, phat = pass / n;
  const denom = 1 + z * z / n;
  const center = (phat + z * z / (2 * n)) / denom;
  const margin = (z * Math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)) / denom;
  return { p: phat, low: Math.max(0, center - margin), high: Math.min(1, center + margin) };
}

// Per-model aggregate metrics
const modelStats = provNames.map((p) => {
  const rows = providers[p];
  let aPass = 0, aTotal = 0;
  const lat = [], toks = [];
  let cost = 0, testPass = 0;
  for (const r of rows) {
    aPass += r.components.filter(c => c.pass).length;
    aTotal += r.components.length;
    lat.push(r.latencyMs);
    toks.push(r.tokenUsage?.total ?? 0);
    cost += r.cost ?? 0;
    if (r.success) testPass++;
  }
  const ci = wilson(aPass, aTotal);
  return { name: p, color: colorOf[p], aPass, aTotal, acc: ci.p, ciLow: ci.low, ciHigh: ci.high,
    latMean: mean(lat), latStd: std(lat), tokMean: mean(toks), cost, testPass, testTotal: rows.length };
});

// ---- Statistics table ----
const bestAcc = Math.max(...modelStats.map(m => m.acc));
const bestLat = Math.min(...modelStats.map(m => m.latMean));
const statsEl = document.getElementById('stats');
statsEl.innerHTML = '<table class="sci"><thead><tr>' +
  '<th>Modell</th><th>Tests</th><th>Assertions</th><th>Genauigkeit</th><th>95%-KI</th>' +
  '<th>Ø Latenz</th><th>Ø Tokens</th><th>Kosten</th></tr></thead><tbody>' +
  modelStats.map(m => '<tr>' +
    '<td class="modelname">' + esc(m.name) + '</td>' +
    '<td>' + m.testPass + '/' + m.testTotal + '</td>' +
    '<td>' + m.aPass + '/' + m.aTotal + '</td>' +
    '<td class="' + (m.acc === bestAcc ? 'best' : '') + '">' + (m.acc * 100).toFixed(1) + '%</td>' +
    '<td>[' + (m.ciLow * 100).toFixed(1) + '–' + (m.ciHigh * 100).toFixed(1) + ']</td>' +
    '<td class="' + (m.latMean === bestLat ? 'best' : '') + '">' + fmtMs(m.latMean) + ' ± ' + fmtMs(m.latStd) + '</td>' +
    '<td>' + Math.round(m.tokMean) + '</td>' +
    '<td>$' + m.cost.toFixed(4) + '</td>' +
  '</tr>').join('') +
  '</tbody></table>';

// ---- SVG chart helpers ----
const svgEsc = (s) => esc(s);
function legendHtml(items) {
  return '<div class="legend">' + items.map(i =>
    '<div class="item"><span class="swatch" style="background:' + i.color + '"></span>' + esc(i.label) + '</div>'
  ).join('') + '</div>';
}

// Chart 1: Accuracy per model with Wilson error bars
function chartAccuracy() {
  const W = 520, H = 300, pad = { t: 16, r: 16, b: 70, l: 44 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const n = modelStats.length;
  const bw = iw / n * 0.6, gap = iw / n;
  const y = (v) => pad.t + ih - v * ih;
  let s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '">';
  for (let g = 0; g <= 100; g += 25) {
    const yy = y(g / 100);
    s += '<line class="grid" x1="' + pad.l + '" y1="' + yy + '" x2="' + (W - pad.r) + '" y2="' + yy + '"/>';
    s += '<text x="' + (pad.l - 8) + '" y="' + (yy + 4) + '" text-anchor="end" font-size="11">' + g + '%</text>';
  }
  modelStats.forEach((m, i) => {
    const cx = pad.l + gap * i + gap / 2;
    const x = cx - bw / 2;
    const h = m.acc * ih;
    s += '<rect x="' + x + '" y="' + y(m.acc) + '" width="' + bw + '" height="' + h + '" rx="4" fill="' + m.color + '"/>';
    // error bar
    s += '<line class="err" x1="' + cx + '" y1="' + y(m.ciLow) + '" x2="' + cx + '" y2="' + y(m.ciHigh) + '"/>';
    s += '<line class="err" x1="' + (cx - 5) + '" y1="' + y(m.ciHigh) + '" x2="' + (cx + 5) + '" y2="' + y(m.ciHigh) + '"/>';
    s += '<line class="err" x1="' + (cx - 5) + '" y1="' + y(m.ciLow) + '" x2="' + (cx + 5) + '" y2="' + y(m.ciLow) + '"/>';
    s += '<text x="' + cx + '" y="' + (y(m.acc) - 6) + '" text-anchor="middle" font-size="11" fill="var(--text)">' + (m.acc * 100).toFixed(0) + '%</text>';
    s += '<text x="' + cx + '" y="' + (H - pad.b + 16) + '" text-anchor="end" font-size="10" transform="rotate(-30 ' + cx + ' ' + (H - pad.b + 16) + ')">' + svgEsc(m.name) + '</text>';
  });
  s += '<line class="axis" x1="' + pad.l + '" y1="' + (pad.t + ih) + '" x2="' + (W - pad.r) + '" y2="' + (pad.t + ih) + '"/>';
  s += '</svg>';
  return s;
}

// Chart 2: Grouped bars — accuracy per test per model
function chartPerTest() {
  const testList = Object.entries(tests);
  const W = 520, H = 300, pad = { t: 16, r: 16, b: 60, l: 44 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const groups = testList.length, m = provNames.length;
  const gw = iw / groups, bw = (gw * 0.8) / m;
  const y = (v) => pad.t + ih - v * ih;
  let s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '">';
  for (let g = 0; g <= 100; g += 25) {
    const yy = y(g / 100);
    s += '<line class="grid" x1="' + pad.l + '" y1="' + yy + '" x2="' + (W - pad.r) + '" y2="' + yy + '"/>';
    s += '<text x="' + (pad.l - 8) + '" y="' + (yy + 4) + '" text-anchor="end" font-size="11">' + g + '%</text>';
  }
  testList.forEach(([idx, t], gi) => {
    const gx = pad.l + gw * gi + gw * 0.1;
    provNames.forEach((p, pi) => {
      const r = t.rows.find(x => x.providerLabel === p);
      const acc = r && r.components.length ? r.components.filter(c => c.pass).length / r.components.length : 0;
      const x = gx + bw * pi;
      s += '<rect x="' + x + '" y="' + y(acc) + '" width="' + (bw - 2) + '" height="' + (acc * ih) + '" rx="2" fill="' + colorOf[p] + '"/>';
    });
    const cx = pad.l + gw * gi + gw / 2;
    const label = t.name.length > 22 ? t.name.slice(0, 20) + '…' : t.name;
    s += '<text x="' + cx + '" y="' + (H - pad.b + 18) + '" text-anchor="middle" font-size="10">' + svgEsc(label) + '</text>';
  });
  s += '<line class="axis" x1="' + pad.l + '" y1="' + (pad.t + ih) + '" x2="' + (W - pad.r) + '" y2="' + (pad.t + ih) + '"/>';
  s += '</svg>';
  return s;
}

// Chart 3: Scatter — latency vs accuracy
function chartScatter() {
  const W = 520, H = 300, pad = { t: 16, r: 16, b: 50, l: 50 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const maxLat = Math.max(...modelStats.map(m => m.latMean), 1) * 1.15;
  const x = (v) => pad.l + (v / maxLat) * iw;
  const y = (v) => pad.t + ih - v * ih;
  let s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '">';
  for (let g = 0; g <= 100; g += 25) {
    const yy = y(g / 100);
    s += '<line class="grid" x1="' + pad.l + '" y1="' + yy + '" x2="' + (W - pad.r) + '" y2="' + yy + '"/>';
    s += '<text x="' + (pad.l - 8) + '" y="' + (yy + 4) + '" text-anchor="end" font-size="11">' + g + '%</text>';
  }
  for (let k = 0; k <= 4; k++) {
    const lv = maxLat * k / 4, xx = x(lv);
    s += '<text x="' + xx + '" y="' + (H - pad.b + 18) + '" text-anchor="middle" font-size="10">' + fmtMs(lv) + '</text>';
  }
  modelStats.forEach(m => {
    s += '<circle cx="' + x(m.latMean) + '" cy="' + y(m.acc) + '" r="7" fill="' + m.color + '" fill-opacity="0.85" stroke="#0a0e18" stroke-width="1.5"/>';
  });
  s += '<line class="axis" x1="' + pad.l + '" y1="' + (pad.t + ih) + '" x2="' + (W - pad.r) + '" y2="' + (pad.t + ih) + '"/>';
  s += '<line class="axis" x1="' + pad.l + '" y1="' + pad.t + '" x2="' + pad.l + '" y2="' + (pad.t + ih) + '"/>';
  s += '<text x="' + (pad.l + iw / 2) + '" y="' + (H - 6) + '" text-anchor="middle" font-size="11">Ø Latenz →</text>';
  s += '</svg>';
  return s;
}

// Chart 4: Heatmap — per-field accuracy across models
function chartHeatmap() {
  const fieldSet = [];
  for (const r of DATA.results) for (const c of r.components) if (!fieldSet.includes(c.field)) fieldSet.push(c.field);
  // aggregate pass fraction per field/model
  const cell = {};
  for (const p of provNames) { cell[p] = {}; for (const f of fieldSet) cell[p][f] = { pass: 0, total: 0 }; }
  for (const r of DATA.results) for (const c of r.components) { const e = cell[r.providerLabel][c.field]; e.total++; if (c.pass) e.pass++; }
  const lerp = (a, b, t) => Math.round(a + (b - a) * t);
  const heatColor = (frac) => 'rgb(' + lerp(255, 63, frac) + ',' + lerp(107, 209, frac) + ',' + lerp(125, 122, frac) + ')';
  let s = '<table class="sci"><thead><tr><th>Feld</th>' + provNames.map(p => '<th style="text-align:center" class="modelname">' + esc(p) + '</th>').join('') + '</tr></thead><tbody>';
  for (const f of fieldSet) {
    s += '<tr><td>' + esc(f) + '</td>';
    for (const p of provNames) {
      const e = cell[p][f];
      const frac = e.total ? e.pass / e.total : 0;
      s += '<td class="heatcell" style="background:' + heatColor(frac) + '">' + Math.round(frac * 100) + '%</td>';
    }
    s += '</tr>';
  }
  s += '</tbody></table>';
  return s;
}

const legend = legendHtml(provNames.map(p => ({ label: p, color: colorOf[p] })));
document.getElementById('charts').innerHTML =
  '<div class="chart-card"><h3>Genauigkeit pro Modell</h3><p class="sub">Bestandene Assertions, mit 95%-Wilson-Konfidenzintervall</p>' + chartAccuracy() + '</div>' +
  '<div class="chart-card"><h3>Genauigkeit pro Testfall</h3><p class="sub">Gruppiert nach Modell</p>' + chartPerTest() + legend + '</div>' +
  '<div class="chart-card"><h3>Latenz vs. Genauigkeit</h3><p class="sub">Pareto-Sicht: oben-links ist besser</p>' + chartScatter() + legend + '</div>' +
  '<div class="chart-card"><h3>Feld-Heatmap</h3><p class="sub">Trefferquote je Schema-Feld (rot 0% → grün 100%)</p>' + chartHeatmap() + '</div>';

// Matrix table
const matrixEl = document.getElementById('matrix');
let mt = '<table><thead><tr><th>Test</th>' + provNames.map(p => '<th class="modelname" style="text-align:center">' + esc(p) + '</th>').join('') + '</tr></thead><tbody>';
for (const [idx, t] of Object.entries(tests)) {
  mt += '<tr><td>' + esc(t.name) + '</td>';
  for (const p of provNames) {
    const r = t.rows.find(x => x.providerLabel === p);
    if (!r) { mt += '<td class="cell">–</td>'; continue; }
    const aPass = r.components.filter(c => c.pass).length;
    mt += '<td class="cell ' + (r.success ? 'pass' : 'fail') + '">' + (r.success ? '✓' : '✗') + ' <span style="font-weight:400;color:var(--muted)">' + aPass + '/' + r.components.length + '</span></td>';
  }
  mt += '</tr>';
}
mt += '</tbody></table>';
matrixEl.innerHTML = mt;

// Details
const detailsEl = document.getElementById('details');
detailsEl.innerHTML = Object.entries(tests).map(([idx, t]) => {
  const provBlocks = t.rows.map(r => {
    const aPass = r.components.filter(c => c.pass).length;
    const outputHtml = r.output != null
      ? '<pre class="json">' + esc(JSON.stringify(r.output, null, 2)) + '</pre>'
      : '<div class="empty">Keine Ausgabe' + (r.error ? ': ' + esc(r.error) : '') + '</div>';
    const asserts = r.components.map(c =>
      '<div class="assert ' + (c.pass ? 'pass' : 'fail') + '"><span class="mark">' + (c.pass ? '✓' : '✗') + '</span><code>' + esc(c.value) + '</code></div>'
    ).join('') || '<div class="empty">Keine Assertions</div>';
    return \`<details class="prov">
      <summary>
        <span class="pill \${r.success?'pass':'fail'}">\${r.success?'PASS':'FAIL'}</span>
        <span class="modelname grow">\${esc(r.providerLabel)}</span>
        <span class="small">\${aPass}/\${r.components.length} &middot; \${fmtMs(r.latencyMs)} &middot; \${r.tokenUsage?.total ?? 0} tok</span>
      </summary>
      <div class="prov-body">
        <div><div class="panel-title">Modell-Ausgabe</div>\${outputHtml}</div>
        <div><div class="panel-title">Assertions</div>\${asserts}</div>
      </div>
    </details>\`;
  }).join('');
  const passCount = t.rows.filter(r => r.success).length;
  return \`<details class="test" \${passCount < t.rows.length ? 'open' : ''}>
    <summary>
      <span class="pill \${passCount===t.rows.length?'pass':'fail'}">\${passCount}/\${t.rows.length}</span>
      <span class="tname">\${esc(t.name)}</span>
      <span class="tdesc">\${esc(t.description)}</span>
    </summary>
    <div class="test-body">
      <div class="question">\${esc(t.question)}</div>
      \${provBlocks}
    </div>
  </details>\`;
}).join('');
</script>
</body>
</html>`;

writeFileSync(outputPath, html, 'utf8');
console.log(`Report geschrieben: ${outputPath}`);
