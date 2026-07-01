import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));

const reasoningJsonPath = resolve(__dirname, 'results.reasoning.json');
const modelsJsonPath = resolve(__dirname, 'results.models.json');
const reasoningReportPath = resolve(__dirname, 'report.reasoning.html');
const modelsReportPath = resolve(__dirname, 'report.models.html');
const sitePath = resolve(__dirname, 'benchmark-site.html');

execFileSync(process.execPath, [resolve(__dirname, 'generate-report.mjs'), reasoningJsonPath, reasoningReportPath], {
  stdio: 'inherit',
});
execFileSync(process.execPath, [resolve(__dirname, 'generate-report.mjs'), modelsJsonPath, modelsReportPath], {
  stdio: 'inherit',
});

const parseResults = (path) => JSON.parse(readFileSync(path, 'utf8'));

const shortProvider = (id) => String(id).split('/').pop() || id;

const summarize = (raw) => {
  const providers = new Map();
  for (const result of raw.results?.results ?? []) {
    const label = shortProvider(result.provider?.label ?? result.provider?.id ?? '');
    const entry = providers.get(label) ?? {
      label,
      tests: 0,
      testPass: 0,
      assertionPass: 0,
      assertionTotal: 0,
      latencyMs: 0,
      totalTokens: 0,
    };
    entry.tests += 1;
    if (result.success) entry.testPass += 1;
    const components = result.gradingResult?.componentResults ?? [];
    entry.assertionPass += components.filter((c) => c.pass).length;
    entry.assertionTotal += components.length;
    entry.latencyMs += result.latencyMs ?? 0;
    entry.totalTokens += result.tokenUsage?.total ?? 0;
    providers.set(label, entry);
  }
  return {
    evalId: raw.evalId ?? 'unknown',
    timestamp: raw.results?.timestamp ?? null,
    providers: [...providers.values()].sort((a, b) => a.label.localeCompare(b.label)),
  };
};

const reasoningSummary = summarize(parseResults(reasoningJsonPath));
const modelsSummary = summarize(parseResults(modelsJsonPath));

const esc = (value) =>
  String(value ?? '').replace(/[&<>"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));

const fmtTime = (value) => (value ? new Date(value).toLocaleString('de-DE') : 'unbekannt');
const fmtMs = (ms, count) => {
  const avg = count ? ms / count : 0;
  return avg >= 1000 ? `${(avg / 1000).toFixed(2)} s` : `${Math.round(avg)} ms`;
};

const renderCards = (summary, title, reportName, description) => `
  <section class="panel">
    <div class="panel-head">
      <div>
        <h2>${esc(title)}</h2>
        <p>${esc(description)}</p>
      </div>
      <div class="meta">
        <span>Lauf: <code>${esc(summary.evalId)}</code></span>
        <span>Zeitpunkt: ${esc(fmtTime(summary.timestamp))}</span>
        <a href="${esc(reportName)}">Detailreport öffnen</a>
      </div>
    </div>
    <div class="cards">
      ${summary.providers
        .map((provider) => {
          const pct = provider.assertionTotal ? Math.round((provider.assertionPass / provider.assertionTotal) * 100) : 0;
          return `
            <article class="card">
              <h3>${esc(provider.label)}</h3>
              <div class="bar"><span style="width:${pct}%"></span></div>
              <dl>
                <div><dt>Tests</dt><dd>${provider.testPass}/${provider.tests}</dd></div>
                <div><dt>Assertions</dt><dd>${provider.assertionPass}/${provider.assertionTotal} (${pct}%)</dd></div>
                <div><dt>Ø Latenz</dt><dd>${esc(fmtMs(provider.latencyMs, provider.tests))}</dd></div>
                <div><dt>Tokens</dt><dd>${provider.totalTokens}</dd></div>
              </dl>
            </article>
          `;
        })
        .join('')}
    </div>
  </section>
`;

const html = `<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TI4 Benchmark Site</title>
  <style>
    :root {
      --bg: #09111d;
      --panel: rgba(18, 26, 44, 0.9);
      --panel-strong: #17233a;
      --text: #eef3fb;
      --muted: #95a3bf;
      --accent: #7dc8ff;
      --accent-2: #7ef0c6;
      --border: rgba(125, 200, 255, 0.16);
      --track: #24334f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(900px 500px at 10% -10%, rgba(126, 240, 198, 0.18), transparent 60%),
        radial-gradient(900px 700px at 100% 0%, rgba(125, 200, 255, 0.2), transparent 60%),
        linear-gradient(180deg, #0a1220 0%, var(--bg) 100%);
    }
    .wrap {
      max-width: 1240px;
      margin: 0 auto;
      padding: 40px 20px 72px;
    }
    header {
      margin-bottom: 28px;
    }
    h1 {
      margin: 0 0 10px;
      font-size: clamp(32px, 5vw, 52px);
      letter-spacing: -0.03em;
    }
    header p {
      margin: 0;
      max-width: 780px;
      color: var(--muted);
      font-size: 16px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 22px;
      backdrop-filter: blur(16px);
      margin-bottom: 22px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.22);
    }
    .panel-head {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
      margin-bottom: 18px;
    }
    .panel-head h2 {
      margin: 0 0 8px;
      font-size: 24px;
    }
    .panel-head p {
      margin: 0;
      color: var(--muted);
    }
    .meta {
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }
    .meta a, .cta a {
      color: var(--accent);
      text-decoration: none;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }
    .card {
      background: linear-gradient(180deg, rgba(23, 35, 58, 0.95), rgba(14, 21, 36, 0.92));
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
    }
    .card h3 {
      margin: 0 0 12px;
      font-size: 15px;
      font-family: ui-monospace, "Cascadia Code", monospace;
    }
    .bar {
      height: 8px;
      background: var(--track);
      border-radius: 999px;
      overflow: hidden;
      margin-bottom: 14px;
    }
    .bar span {
      display: block;
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      border-radius: inherit;
    }
    dl {
      margin: 0;
      display: grid;
      gap: 8px;
    }
    dl div {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      font-size: 13px;
    }
    dt {
      color: var(--muted);
    }
    dd {
      margin: 0;
      text-align: right;
    }
    .cta {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 24px;
    }
    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 16px;
      border-radius: 999px;
      text-decoration: none;
      font-weight: 600;
      border: 1px solid var(--border);
      background: var(--panel-strong);
      color: var(--text);
    }
    .button.primary {
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      color: #08111c;
      border: none;
    }
    code {
      font-family: ui-monospace, "Cascadia Code", monospace;
      color: var(--accent);
    }
    @media (max-width: 860px) {
      .panel-head {
        flex-direction: column;
      }
      .meta {
        text-align: left;
      }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>TI4 Benchmark Site</h1>
      <p>Single entrypoint for the current reasoning and model-comparison runs, including the new Claude Sonnet 5 coverage.</p>
      <div class="cta">
        <a class="button primary" href="report.reasoning.html">Reasoning Report</a>
        <a class="button" href="report.models.html">Models Report</a>
      </div>
    </header>
    ${renderCards(reasoningSummary, 'Reasoning Comparison', 'report.reasoning.html', 'OpenAI GPT-5.4 and Claude Sonnet 5 across low, medium, and high reasoning effort.')}
    ${renderCards(modelsSummary, 'Model Comparison', 'report.models.html', 'Cross-model benchmark including GPT-4.1, GPT-5.4, and Claude Sonnet 5.')}
  </div>
</body>
</html>`;

writeFileSync(sitePath, html, 'utf8');
console.log(`Site geschrieben: ${sitePath}`);
