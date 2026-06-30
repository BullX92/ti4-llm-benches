const statusEl = document.getElementById('status');
const reportState = document.getElementById('reportState');
const reportMeta = document.getElementById('reportMeta');
const reportSummary = document.getElementById('reportSummary');
const resultCards = document.getElementById('resultCards');
const output = document.getElementById('output');
const publishedStateEl = document.getElementById('publishedState');
const manifestMeta = document.getElementById('manifestMeta');
const manifestList = document.getElementById('manifestList');
const aggregateView = document.getElementById('aggregateView');
const aggregateJson = document.getElementById('aggregateJson');
const runBtn = document.getElementById('runBtn');
const copyBtn = document.getElementById('copyBtn');
const cmdPreview = document.getElementById('cmdPreview');

const providerForm = document.getElementById('providerForm');
const providerList = document.getElementById('providerList');
const providerMessage = document.getElementById('providerMessage');
const refreshBtn = document.getElementById('refreshBtn');

const testcaseForm = document.getElementById('testcaseForm');
const testcaseList = document.getElementById('testcaseList');
const testcaseMessage = document.getElementById('testcaseMessage');
const reloadTestcasesBtn = document.getElementById('reloadTestcasesBtn');
const addAssertionBtn = document.getElementById('addAssertionBtn');
const assertionRows = document.getElementById('assertionRows');

const statProviders = document.getElementById('statProviders');
const statModels = document.getElementById('statModels');
const statTestcases = document.getElementById('statTestcases');
const statLastExit = document.getElementById('statLastExit');

const cmd = '/opt/hermes/.venv/bin/python evals/llm_bench/server.py';
const state = {
  providers: [],
  testcases: [],
  modelsByProvider: {},
  status: null,
  resultsManifest: null,
  currentResultId: '',
  currentAggregate: null,
  lastManifestGeneratedAt: '',
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }
  if (!response.ok) {
    throw new Error(data.error || data.raw || `${response.status} ${response.statusText}`);
  }
  return data;
}

function setMessage(target, msg, kind = 'muted') {
  if (!target) return;
  target.textContent = msg;
  target.dataset.kind = kind;
}

function setReportState(text, kind = 'muted') {
  setMessage(reportState, text, kind);
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatDuration(value) {
  if (!value) return 'n/a';
  return String(value);
}

function formatAssertionLabel(assertion = {}) {
  const matcher = String(assertion.type || 'contains');
  const value = String(assertion.value || '');
  const key = String(assertion.key || '').trim();
  return key ? `${key} · ${matcher} · ${value}` : `${matcher} · ${value}`;
}

function formatSourcePath(sourcePath) {
  const value = String(sourcePath || '').trim();
  if (!value) return '';
  const marker = '/evals/llm_bench/';
  const idx = value.indexOf(marker);
  return idx >= 0 ? value.slice(idx + 1) : value;
}

function compactMaskedSecret(value) {
  const text = String(value || '').trim();
  if (!text) return '(empty)';
  if (text.length <= 18) return text;
  return `${text.slice(0, 6)}…${text.slice(-4)}`;
}

function createAssertionRow(assertion = {}) {
  const row = document.createElement('div');
  row.className = 'assertion-row';
  row.innerHTML = `
    <input data-assertion-field="key" placeholder="JSON key path (optional)" value="${escapeHtml(assertion.key || '')}" />
    <select data-assertion-field="type">
      <option value="equals">equals</option>
      <option value="contains">contains</option>
      <option value="icontains">icontains</option>
      <option value="regex">regex</option>
    </select>
    <input data-assertion-field="value" placeholder="Expected value" value="${escapeHtml(assertion.value || '')}" />
    <button type="button" class="secondary danger" data-action="remove-assertion">Remove</button>
  `;
  row.querySelector('[data-assertion-field="type"]').value = String(assertion.type || 'contains');
  row.querySelector('[data-action="remove-assertion"]').addEventListener('click', () => {
    row.remove();
    if (!assertionRows.children.length) {
      appendAssertionRow();
    }
  });
  return row;
}

function appendAssertionRow(assertion = {}) {
  assertionRows.append(createAssertionRow(assertion));
}

function readAssertionRows() {
  const rows = Array.from(assertionRows.querySelectorAll('.assertion-row'));
  const seen = new Set();
  return rows
    .map((row) => ({
      key: String(row.querySelector('[data-assertion-field="key"]').value || '').trim(),
      type: String(row.querySelector('[data-assertion-field="type"]').value || 'contains').trim(),
      value: String(row.querySelector('[data-assertion-field="value"]').value || '').trim(),
    }))
    .filter((item) => item.value)
    .filter((item) => {
      const dedupeKey = JSON.stringify(item).toLowerCase();
      if (seen.has(dedupeKey)) return false;
      seen.add(dedupeKey);
      return true;
    });
}

function resetAssertionRows(assertions = [{ type: 'contains', value: '' }]) {
  assertionRows.innerHTML = '';
  (assertions.length ? assertions : [{ type: 'contains', value: '' }]).forEach((assertion) => appendAssertionRow(assertion));
}

function updateTopStats() {
  if (statProviders) statProviders.textContent = String(state.providers.length);
  if (statModels) statModels.textContent = String(state.providers.reduce((sum, provider) => sum + Number(provider.selected_count || 0), 0));
  if (statTestcases) statTestcases.textContent = String(state.testcases.length);
  if (statLastExit) {
    const exitCode = state.status?.last_run?.exit_code;
    statLastExit.textContent = exitCode == null ? '—' : String(exitCode);
  }
}

function renderSummaryCards(runPayload) {
  reportSummary.innerHTML = '';
  const summary = runPayload.report_summary || {};
  const cards = [
    ['Selected models', String(summary.selected_model_count ?? runPayload.selected_models?.length ?? 0)],
    ['Testcases', String(summary.testcase_count ?? runPayload.testcases?.length ?? 0)],
    ['Pass', String(summary.pass_count ?? 0)],
    ['Fail', String(summary.fail_count ?? 0)],
    ['Errors', String(summary.error_count ?? 0)],
    ['Fresh', String(summary.fresh_count ?? 0)],
    ['Skipped', String(summary.skipped_count ?? 0)],
    ['Duration', formatDuration(summary.duration)],
    ['Exit code', String(runPayload.exit_code ?? 'n/a')],
  ];
  cards.forEach(([label, value]) => {
    const card = document.createElement('article');
    card.className = 'metric-card';
    card.innerHTML = `<span class="metric-label">${escapeHtml(label)}</span><strong class="metric-value">${escapeHtml(value)}</strong>`;
    reportSummary.append(card);
  });
}

function groupMatrixResults(results = []) {
  const groups = new Map();
  results.forEach((item) => {
    const key = String(item.testcase_id ?? item.testcase_name ?? 'unknown');
    if (!groups.has(key)) {
      groups.set(key, {
        testcase_id: item.testcase_id,
        testcase_name: item.testcase_name || 'Unnamed testcase',
        prompt_text: item.prompt_text || '',
        assertions: item.assertions || [],
        rows: [],
      });
    }
    groups.get(key).rows.push(item);
  });
  return Array.from(groups.values()).sort((a, b) => a.testcase_name.localeCompare(b.testcase_name));
}

function renderMatrixResults(results = []) {
  resultCards.innerHTML = '';
  if (!results.length) {
    resultCards.innerHTML = '<p class="empty">No testcase/model results saved yet.</p>';
    return;
  }

  const groups = groupMatrixResults(results);
  groups.forEach((group) => {
    const section = document.createElement('article');
    section.className = 'result-card testcase-result-card';

    const assertionChips = (group.assertions || [])
      .map((item) => `<span class="chip">${escapeHtml(formatAssertionLabel(item))}</span>`)
      .join('');

    const rowsHtml = group.rows
      .sort((a, b) => String(a.model_name).localeCompare(String(b.model_name)))
      .map((row) => {
        const bodyText = row.response_output || row.error_text || row.detail || 'No response captured.';
        return `
          <div class="matrix-row result-${escapeHtml(row.result_kind)}">
            <div class="matrix-row-topline">
              <div>
                <h3>${escapeHtml(row.model_name)}</h3>
                <p class="muted">${escapeHtml(row.provider_name)}</p>
              </div>
              <span class="result-badge badge-${escapeHtml(row.result_kind)}">${escapeHtml(row.label || row.result_kind)}</span>
            </div>
            <p class="result-detail">${escapeHtml(row.detail || '')}</p>
            <details>
              <summary>Captured output</summary>
              <pre>${escapeHtml(bodyText)}</pre>
            </details>
          </div>
        `;
      })
      .join('');

    section.innerHTML = `
      <div class="result-topline testcase-heading">
        <div>
          <h3>${escapeHtml(group.testcase_name)}</h3>
          <p class="muted">${escapeHtml(group.prompt_text)}</p>
        </div>
      </div>
      <div class="chips testcase-assertions">${assertionChips}</div>
      <div class="matrix-list">${rowsHtml}</div>
    `;
    resultCards.append(section);
  });
}

function renderRawOutput(runPayload) {
  output.textContent = [
    `Saved at: ${runPayload.saved_at || '(unknown)'}`,
    `Run state: ${runPayload.run_state || 'unknown'}`,
    '',
    'STDOUT:',
    runPayload.stdout || '(empty)',
    '',
    'STDERR:',
    runPayload.stderr || '(empty)',
  ].join('\n');
}

function setPublishedState(text, kind = 'muted') {
  setMessage(publishedStateEl, text, kind);
}

function renderManifestList() {
  if (!manifestList) return;
  const items = state.resultsManifest?.testcases || [];
  manifestList.innerHTML = '';
  if (!items.length) {
    manifestList.innerHTML = '<p class="empty">No published testcase JSON files yet.</p>';
    return;
  }
  items.forEach((item) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = `manifest-card ${state.currentResultId === item.content_hash ? 'active' : ''}`;
    card.innerHTML = `
      <div class="manifest-card-topline">
        <strong>${escapeHtml(item.name || item.slug || 'Unnamed testcase')}</strong>
        <span class="result-badge badge-${item.error_count ? 'error' : item.fail_count ? 'fail' : 'pass'}">${escapeHtml(item.file || '')}</span>
      </div>
      <p class="muted">${escapeHtml(item.content_hash || '')}</p>
      <div class="chips">
        <span class="chip">models ${escapeHtml(String(item.model_count ?? 0))}</span>
        <span class="chip">pass ${escapeHtml(String(item.pass_count ?? 0))}</span>
        <span class="chip">fail ${escapeHtml(String(item.fail_count ?? 0))}</span>
        <span class="chip">error ${escapeHtml(String(item.error_count ?? 0))}</span>
      </div>
    `;
    card.addEventListener('click', () => loadPublishedTestcase(item.content_hash));
    manifestList.append(card);
  });
}

function renderAggregateView(payload) {
  if (!aggregateView || !aggregateJson) return;
  if (!payload) {
    aggregateView.innerHTML = '<p class="empty">Select a testcase result to inspect the published JSON aggregate.</p>';
    aggregateJson.textContent = '';
    return;
  }
  const testcase = payload.testcase || {};
  const summary = payload.summary || {};
  const expected = testcase.expected_result || {};
  const expectedChips = Object.entries(expected).map(([key, value]) => {
    const pretty = Array.isArray(value) ? value.join(' · ') : String(value);
    return `<span class="chip">${escapeHtml(key)} · ${escapeHtml(pretty)}</span>`;
  }).join('');
  const models = payload.models || [];
  const modelRows = models.map((row) => {
    const bodyText = row.response_output || row.error_text || row.detail || 'No response captured.';
    return `
      <div class="matrix-row result-${escapeHtml(row.result_kind || 'unknown')}">
        <div class="matrix-row-topline">
          <div>
            <h3>${escapeHtml(row.model_name || 'unknown')}</h3>
            <p class="muted">${escapeHtml(row.provider_name || '')} · ${escapeHtml(row.result_subtype || row.result_kind || 'unknown')}</p>
          </div>
          <span class="result-badge badge-${escapeHtml(row.result_kind || 'unknown')}">${escapeHtml(row.label || row.result_kind || 'unknown')}</span>
        </div>
        <p class="result-detail">${escapeHtml(row.detail || '')}</p>
        <div class="chips">
          <span class="chip">score ${escapeHtml(String(row.score ?? 'n/a'))}</span>
          <span class="chip">saved ${escapeHtml(String(row.saved_at || 'n/a'))}</span>
          <span class="chip">latency ${escapeHtml(String(row.latency_ms ?? 'n/a'))}</span>
        </div>
        <details>
          <summary>Captured output</summary>
          <pre>${escapeHtml(bodyText)}</pre>
        </details>
      </div>
    `;
  }).join('');

  aggregateView.innerHTML = `
    <article class="result-card testcase-result-card">
      <div class="result-topline testcase-heading">
        <div>
          <h3>${escapeHtml(testcase.name || 'Unnamed testcase')}</h3>
          <p class="muted">${escapeHtml(testcase.prompt_text || '')}</p>
        </div>
      </div>
      <div class="report-summary">
        <article class="metric-card compact"><span class="metric-label">Models</span><strong class="metric-value">${escapeHtml(String(summary.model_count ?? 0))}</strong></article>
        <article class="metric-card compact"><span class="metric-label">Pass</span><strong class="metric-value">${escapeHtml(String(summary.pass_count ?? 0))}</strong></article>
        <article class="metric-card compact"><span class="metric-label">Fail</span><strong class="metric-value">${escapeHtml(String(summary.fail_count ?? 0))}</strong></article>
        <article class="metric-card compact"><span class="metric-label">Error</span><strong class="metric-value">${escapeHtml(String(summary.error_count ?? 0))}</strong></article>
      </div>
      <div class="selected-models">
        <p class="muted">Expected result</p>
        <div class="chips">${expectedChips || '<span class="chip">No explicit expected-result mapping</span>'}</div>
      </div>
      <div class="selected-models">
        <p class="muted">Source</p>
        <div class="chips">
          <span class="chip">slug ${escapeHtml(testcase.slug || '')}</span>
          <span class="chip">hash ${escapeHtml(testcase.content_hash || '')}</span>
          <span class="chip">updated ${escapeHtml(summary.last_updated || payload.generated_at || '')}</span>
        </div>
      </div>
      <div class="matrix-list">${modelRows || '<p class="empty">No saved model results for this testcase yet.</p>'}</div>
    </article>
  `;
  aggregateJson.textContent = JSON.stringify(payload, null, 2);
}

async function loadPublishedTestcase(identifier) {
  if (!identifier) return;
  setPublishedState('Loading testcase aggregate…');
  const payload = await fetchJson(`/api/results/testcases/${encodeURIComponent(identifier)}`);
  state.currentResultId = payload?.testcase?.content_hash || identifier;
  state.currentAggregate = payload;
  renderManifestList();
  renderAggregateView(payload);
  setPublishedState('Published testcase JSON loaded');
}

async function refreshPublishedResults(forceCurrent = false) {
  if (!manifestList) return;
  const manifest = await fetchJson('/api/results/manifest');
  state.resultsManifest = manifest;
  manifestMeta.textContent = `Generated ${manifest.generated_at || '(unknown)'} · ${String((manifest.testcases || []).length)} testcase JSON files`;
  const changed = state.lastManifestGeneratedAt !== String(manifest.generated_at || '');
  state.lastManifestGeneratedAt = String(manifest.generated_at || '');
  renderManifestList();

  const items = manifest.testcases || [];
  if (!items.length) {
    renderAggregateView(null);
    setPublishedState('No published testcase JSON yet');
    return;
  }

  const current = items.find((item) => item.content_hash === state.currentResultId);
  if (forceCurrent || changed) {
    await loadPublishedTestcase((current || items[0]).content_hash);
    return;
  }

  if (!state.currentResultId) {
    await loadPublishedTestcase(items[0].content_hash);
    return;
  }

  setPublishedState('Watching testcase JSON for changes');
}

function renderRunOutput(runPayload) {
  if (!runPayload) return;
  state.status = { ...(state.status || {}), last_run: runPayload };
  updateTopStats();
  renderSummaryCards(runPayload);
  renderMatrixResults(runPayload.matrix_results || []);
  renderRawOutput(runPayload);
  reportMeta.textContent = `Saved ${runPayload.saved_at || '(unknown)'} · ${runPayload.run_state || 'fresh'} · ${(runPayload.report_summary?.skipped_count ?? 0)} skipped from cache`;
  const statusKind = runPayload.exit_code === 0 ? 'pass' : runPayload.exit_code === 100 ? 'fail' : 'error';
  setReportState(`${runPayload.run_state || 'Run'} · exit ${runPayload.exit_code}`, statusKind);
}

function renderProviderCard(provider) {
  const card = document.createElement('article');
  card.className = 'provider-card';
  card.dataset.providerId = provider.id;

  const chips = [
    `<span class="meta-chip">${escapeHtml(provider.provider_type)}</span>`,
    `<span class="meta-chip meta-url">${escapeHtml(provider.base_url)}</span>`,
    `<span class="meta-chip">key ${escapeHtml(compactMaskedSecret(provider.api_key_masked))}</span>`,
  ].join('');
  const configPreview = {
    provider_id: provider.promptfoo_provider_id,
    apiBaseUrl: provider.api_base_url,
    modelsUrl: provider.models_url,
    selected_models: provider.selected_models || [],
  };

  card.innerHTML = `
    <div class="provider-header">
      <div>
        <h3>${escapeHtml(provider.name)}</h3>
        <p class="provider-subtitle">${chips}</p>
      </div>
      <div class="provider-actions">
        <button type="button" class="secondary" data-action="load-models">${state.modelsByProvider[provider.id] ? 'Refresh models' : 'Load models'}</button>
        <button type="button" class="danger secondary" data-action="delete-provider">Delete</button>
      </div>
    </div>
    <div class="selected-models">
      <p class="muted">${provider.selected_models.length ? 'Saved shortlist from config' : 'No saved model selection yet'}</p>
      ${provider.selected_models.length ? `<div class="chips">${provider.selected_models.map((name) => `<span class="chip">${escapeHtml(name)}</span>`).join('')}</div>` : ''}
    </div>
    <div class="selected-models testcase-prompt-box">
      <p class="muted">Config-derived Promptfoo preview</p>
      <pre>${escapeHtml(JSON.stringify(configPreview, null, 2))}</pre>
    </div>
    <div class="models-box" data-models-box="${provider.id}">Click “Load models” to fetch the available models from this config.</div>
    <div class="provider-footer">
      <button type="button" data-action="save-selection">Save selection</button>
      <span class="muted" data-provider-status="${provider.id}">${provider.selected_count ? `${provider.selected_count} chosen` : 'Ready'}</span>
    </div>
  `;

  card.querySelector('[data-action="load-models"]').addEventListener('click', () => loadModels(provider.id, card));
  card.querySelector('[data-action="delete-provider"]').addEventListener('click', async () => {
    if (!confirm(`Delete config ${provider.name}?`)) return;
    await fetchJson(`/api/providers/${provider.id}`, { method: 'DELETE' });
    await refreshProviders();
  });
  card.querySelector('[data-action="save-selection"]').addEventListener('click', () => saveSelection(provider.id, card));
  return card;
}

function renderProviders() {
  providerList.innerHTML = '';
  if (!state.providers.length) {
    providerList.innerHTML = '<p class="empty">No configs saved yet. Add one above to start browsing models.</p>';
    return;
  }
  state.providers.forEach((provider) => providerList.append(renderProviderCard(provider)));
}

async function refreshProviders() {
  setMessage(providerMessage, 'Loading configs…');
  const data = await fetchJson('/api/providers');
  state.providers = data.providers || [];
  renderProviders();
  updateTopStats();
  setMessage(providerMessage, `Saved configs: ${state.providers.length}`);
  setMessage(statusEl, 'Ready');
}

async function loadModels(providerId, card = null) {
  const modelsBox = card ? card.querySelector('[data-models-box]') : document.querySelector(`[data-models-box="${providerId}"]`);
  const providerStatus = document.querySelector(`[data-provider-status="${providerId}"]`);
  try {
    if (modelsBox) modelsBox.textContent = 'Loading models…';
    if (providerStatus) providerStatus.textContent = 'Loading…';
    const data = await fetchJson(`/api/providers/${providerId}/models`);
    state.modelsByProvider[providerId] = data.models || [];
    renderModelList(providerId, data.models || [], card);
    if (providerStatus) providerStatus.textContent = `${(data.models || []).length} available`;
  } catch (error) {
    if (modelsBox) modelsBox.textContent = `Could not load models: ${error.message}`;
    if (providerStatus) providerStatus.textContent = 'Model fetch failed';
  }
}

function renderModelList(providerId, models, card = null) {
  const modelsBox = card ? card.querySelector('[data-models-box]') : document.querySelector(`[data-models-box="${providerId}"]`);
  if (!modelsBox) return;
  modelsBox.innerHTML = '';
  if (!models.length) {
    modelsBox.textContent = 'No models returned by this config.';
    return;
  }

  const existing = new Set((state.providers.find((provider) => provider.id === providerId)?.selected_models || []).map(String));
  const list = document.createElement('div');
  list.className = 'model-list';
  models.forEach((name) => {
    const label = document.createElement('label');
    label.className = 'model-item';
    label.innerHTML = `<input type="checkbox" value="${escapeHtml(name)}" ${existing.has(name) ? 'checked' : ''} /><span>${escapeHtml(name)}</span>`;
    list.append(label);
  });

  const toolbar = document.createElement('div');
  toolbar.className = 'toolbar';
  const allBtn = document.createElement('button');
  allBtn.type = 'button';
  allBtn.className = 'secondary';
  allBtn.textContent = 'Select all';
  allBtn.addEventListener('click', () => list.querySelectorAll('input[type="checkbox"]').forEach((el) => (el.checked = true)));

  const noneBtn = document.createElement('button');
  noneBtn.type = 'button';
  noneBtn.className = 'secondary';
  noneBtn.textContent = 'Select none';
  noneBtn.addEventListener('click', () => list.querySelectorAll('input[type="checkbox"]').forEach((el) => (el.checked = false)));

  toolbar.append(allBtn, noneBtn);
  modelsBox.append(toolbar, list);
}

async function saveSelection(providerId, card) {
  const checks = card.querySelectorAll('.model-item input[type="checkbox"]:checked');
  const model_names = Array.from(checks).map((el) => el.value);
  const target = card.querySelector(`[data-provider-status="${providerId}"]`);
  setMessage(target, 'Saving…');
  try {
    const data = await fetchJson(`/api/providers/${providerId}/models`, {
      method: 'POST',
      body: JSON.stringify({ model_names }),
    });
    setMessage(target, `${data.selected_models.length} saved`);
    await refreshProviders();
  } catch (error) {
    setMessage(target, error.message, 'error');
  }
}

async function addProvider(event) {
  event.preventDefault();
  const formData = new FormData(providerForm);
  const payload = {
    name: String(formData.get('name') || '').trim(),
    base_url: String(formData.get('base_url') || '').trim(),
    api_key: String(formData.get('api_key') || ''),
    provider_type: String(formData.get('provider_type') || 'ollama').trim(),
  };
  if (!payload.name || !payload.base_url) {
    setMessage(providerMessage, 'Config name and base URL are required.', 'error');
    return;
  }
  setMessage(providerMessage, 'Saving config…');
  try {
    const data = await fetchJson('/api/providers', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    providerForm.reset();
    setMessage(providerMessage, `Saved ${data.provider.name}`);
    await refreshProviders();
  } catch (error) {
    setMessage(providerMessage, error.message, 'error');
  }
}

function renderTestcaseCard(testcase) {
  const sourcePath = formatSourcePath(testcase.source_path);
  const subtitleChips = [`<span class="meta-chip">trace ${escapeHtml(testcase.content_hash.slice(0, 12))}</span>`];
  if (sourcePath) subtitleChips.push(`<span class="meta-chip">yaml ${escapeHtml(sourcePath)}</span>`);
  const summaryText = testcase.source_description || testcase.source_question || '';
  const yamlPreview = String(testcase.source_yaml || '').trim();
  const card = document.createElement('article');
  card.className = 'provider-card testcase-card';
  card.innerHTML = `
    <div class="provider-header">
      <div>
        <h3>${escapeHtml(testcase.name)}</h3>
        <p class="provider-subtitle">${subtitleChips.join('')}</p>
      </div>
      <div class="provider-actions">
        <button type="button" class="danger secondary" data-action="delete-testcase" ${sourcePath ? 'disabled title="Delete the YAML file on disk to remove this testcase"' : ''}>${sourcePath ? 'YAML synced' : 'Delete'}</button>
      </div>
    </div>
    ${summaryText ? `<div class="selected-models"><p class="muted">YAML description</p><p>${escapeHtml(summaryText)}</p></div>` : ''}
    <div class="selected-models testcase-prompt-box">
      <p class="muted">Benchmark prompt</p>
      <pre>${escapeHtml(testcase.prompt_text)}</pre>
    </div>
    <div class="selected-models">
      <p class="muted">Expected results</p>
      <div class="chips">${(testcase.assertions || []).map((item) => `<span class="chip">${escapeHtml(formatAssertionLabel(item))}</span>`).join('')}</div>
    </div>
    ${yamlPreview ? `<details class="raw-output"><summary>YAML testcase source</summary><pre>${escapeHtml(yamlPreview)}</pre></details>` : ''}
  `;
  const deleteBtn = card.querySelector('[data-action="delete-testcase"]');
  if (!sourcePath) deleteBtn.addEventListener('click', async () => {
    if (!confirm(`Delete testcase ${testcase.name}?`)) return;
    await fetchJson(`/api/testcases/${testcase.id}`, { method: 'DELETE' });
    await refreshTestcases();
  });
  return card;
}

function renderTestcases() {
  testcaseList.innerHTML = '';
  if (!state.testcases.length) {
    testcaseList.innerHTML = '<p class="empty">No testcases saved yet. Add one above to start benchmarking.</p>';
    return;
  }
  state.testcases.forEach((testcase) => testcaseList.append(renderTestcaseCard(testcase)));
}

async function refreshTestcases() {
  setMessage(testcaseMessage, 'Loading testcases…');
  const data = await fetchJson('/api/testcases');
  state.testcases = data.testcases || [];
  renderTestcases();
  updateTopStats();
  setMessage(testcaseMessage, `Saved testcases: ${state.testcases.length}`);
}

async function saveTestcase(event) {
  event.preventDefault();
  const formData = new FormData(testcaseForm);
  const payload = {
    name: String(formData.get('name') || '').trim(),
    prompt_text: String(formData.get('prompt_text') || '').trim(),
    assertions: readAssertionRows(),
  };
  if (!payload.name || !payload.prompt_text || !payload.assertions.length) {
    setMessage(testcaseMessage, 'Name, prompt, and at least one expected result are required.', 'error');
    return;
  }
  setMessage(testcaseMessage, 'Saving testcase…');
  try {
    const data = await fetchJson('/api/testcases', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    testcaseForm.reset();
    resetAssertionRows();
    setMessage(testcaseMessage, `Saved ${data.testcase.name}`);
    await refreshTestcases();
  } catch (error) {
    setMessage(testcaseMessage, error.message, 'error');
  }
}

async function refreshStatus() {
  const status = await fetchJson('/api/status');
  state.status = status;
  updateTopStats();
  if (status.last_run) {
    renderRunOutput(status.last_run);
  } else {
    setReportState('Idle');
    reportMeta.textContent = 'Run the benchmark to generate a testcase/model matrix.';
    reportSummary.innerHTML = '';
    resultCards.innerHTML = '';
    output.textContent = 'Add a config, select models, and save at least one testcase to start.';
  }
  setMessage(statusEl, 'Ready');
}

async function runBenchmark() {
  runBtn.disabled = true;
  setMessage(statusEl, 'Running', 'running');
  setReportState('Running', 'running');
  reportMeta.textContent = 'Running benchmark matrix…';
  resultCards.innerHTML = '';
  reportSummary.innerHTML = '';
  output.textContent = 'Running Promptfoo against pending testcase/model combinations…';
  try {
    const data = await fetchJson('/api/run', { method: 'POST' });
    renderRunOutput(data);
    await refreshPublishedResults(true);
    setMessage(statusEl, data.run_state === 'cached' ? 'Cached' : 'Done');
  } catch (error) {
    setMessage(statusEl, 'Error', 'error');
    setReportState('Error', 'error');
    output.textContent = String(error.message || error);
  } finally {
    runBtn.disabled = false;
  }
}

async function init() {
  providerForm.addEventListener('submit', addProvider);
  testcaseForm.addEventListener('submit', saveTestcase);
  reloadTestcasesBtn?.addEventListener('click', refreshTestcases);
  addAssertionBtn.addEventListener('click', () => appendAssertionRow());
  resetAssertionRows();
  runBtn.addEventListener('click', runBenchmark);
  refreshBtn.addEventListener('click', refreshProviders);
  copyBtn.addEventListener('click', async () => {
    await navigator.clipboard.writeText(cmd);
    setMessage(statusEl, 'Command copied');
  });
  if (cmdPreview) cmdPreview.textContent = cmd;

  await refreshProviders();
  await refreshTestcases();
  await refreshStatus();
  await refreshPublishedResults(true);
  window.setInterval(() => {
    refreshPublishedResults().catch((error) => setPublishedState(error.message || String(error), 'error'));
  }, 15000);
}

init().catch((error) => {
  setMessage(statusEl, 'Startup error', 'error');
  setReportState('Startup error', 'error');
  output.textContent = String(error);
});
