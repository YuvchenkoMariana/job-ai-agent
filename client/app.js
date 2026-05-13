const API_BASE = window.location.origin;

// --- DOM refs ---
const authEmail    = document.getElementById('authEmail');
const authPassword = document.getElementById('authPassword');
const registerBtn  = document.getElementById('registerBtn');
const loginBtn     = document.getElementById('loginBtn');
const logoutBtn    = document.getElementById('logoutBtn');
const guestBtn     = document.getElementById('guestBtn');
const authStatus   = document.getElementById('authStatus');

const cvFile     = document.getElementById('cvFile');
const uploadBtn  = document.getElementById('uploadBtn');
const cvStatus   = document.getElementById('cvStatus');

const startBtn        = document.getElementById('startBtn');
const refreshBtn      = document.getElementById('refreshBtn');
const pipelineStatus  = document.getElementById('pipelineStatus');

const jobsMeta = document.getElementById('jobsMeta');
const jobsEl   = document.getElementById('jobs');

const matchRefreshBtn = document.getElementById('matchRefreshBtn');
const matchStatus     = document.getElementById('matchStatus');
const matchList       = document.getElementById('matchList');
const matchReport     = document.getElementById('matchReport');

const historySection = document.getElementById('historySection');
const historyList    = document.getElementById('historyList');

// ── Step flow ──────────────────────────────────────────────────────────────
const STEP_CARDS = [
  { id: 'stepAccount',  step: 0 },
  { id: 'stepCvUpload', step: 1 },
  { id: 'stepEnrich',   step: 2 },
  { id: 'stepJobs',     step: 2 },
];

function setCurrentStep(step) {
  for (const { id, step: cardStep } of STEP_CARDS) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.classList.remove('step-active', 'step-done', 'step-future');
    if (cardStep < step)       el.classList.add('step-done');
    else if (cardStep === step) el.classList.add('step-active');
    else                        el.classList.add('step-future');
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function setStatus(el, text)  { el.textContent = text; }
function setHtml(el, html)    { el.innerHTML = html; }
function fmtPct(x)            { return `${Math.round(Number(x ?? 0) * 100)}%`; }

async function apiJson(path, opts = {}) {
  const token = localStorage.getItem('authToken');
  const headers = new Headers(opts.headers || {});
  if (token) headers.set('X-Auth-Token', token);
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const ct = res.headers.get('content-type') || '';
    let msg = `${res.status} ${res.statusText}`;
    if (ct.includes('application/json')) {
      try {
        const j = await res.json();
        msg += ': ' + (j.detail || JSON.stringify(j));
      } catch (_) {}
    } else {
      const txt = await res.text();
      if (txt.includes('<html') || txt.includes('<!doctype')) {
        // HTML error page = server is running old code or route doesn't exist
        msg += ' — API route not found. Please restart the server.';
      } else if (txt.length < 300) {
        msg += ': ' + txt;
      }
    }
    throw new Error(msg);
  }
  const ct2 = res.headers.get('content-type') || '';
  if (ct2.includes('application/json')) return await res.json();
  return await res.text();
}

// ── Selected run ───────────────────────────────────────────────────────────
function getSelectedRunId() {
  // Run IDs are now UUID strings — return as-is (no Number() parsing).
  return localStorage.getItem('selectedRunId') || null;
}
function setSelectedRunId(runId) {
  if (runId == null) localStorage.removeItem('selectedRunId');
  else               localStorage.setItem('selectedRunId', String(runId));
}

// ── Auth state + step ──────────────────────────────────────────────────────
function setAuthState({ token, email, user_id } = {}) {
  if (token)    localStorage.setItem('authToken',  token);
  if (email)    localStorage.setItem('authEmail',  email);
  if (user_id != null) localStorage.setItem('authUserId', String(user_id));

  const curEmail = localStorage.getItem('authEmail');
  const curToken = localStorage.getItem('authToken');
  const isGuest  = localStorage.getItem('guestMode') === '1';

  if (curToken) {
    setStatus(authStatus, `✅ Logged in as ${curEmail || 'user'}. Token saved.`);
    logoutBtn.disabled = false;
    registerBtn.classList.remove('is-active');
    loginBtn.classList.remove('is-active');
    setCurrentStep(1);
    if (historySection) historySection.hidden = false;
  } else {
    setStatus(authStatus, 'Not logged in (guest mode).');
    logoutBtn.disabled = true;
    if (historySection) historySection.hidden = true;
    setCurrentStep(isGuest ? 1 : 0);
  }

  loadHistory().catch(() => {});
}

// ── Auth button toggle (visual only when fields empty) ─────────────────────
let _authAction = null; // 'register' | 'login' | null

function selectAuthAction(which) {
  if (_authAction === which) {
    _authAction = null;
  } else {
    _authAction = which;
  }
  registerBtn.classList.toggle('is-active', _authAction === 'register');
  loginBtn.classList.toggle('is-active',    _authAction === 'login');
}

async function trySubmitAuth(preferred) {
  // preferred is the button just clicked: 'register' | 'login'
  selectAuthAction(preferred);

  const email    = (authEmail.value || '').trim();
  const password = authPassword.value || '';

  if (!email || !password) {
    // No data yet — just show a gentle hint, no API call at all
    const action = _authAction === 'register' ? 'Register' : _authAction === 'login' ? 'Login' : 'a button';
    setStatus(authStatus, `📝 Fill in email and password, then click ${action} again.`);
    return;
  }

  if (!email.includes('@') || email.split('@')[1]?.length < 2) {
    setStatus(authStatus, '❌ Enter a valid email address (e.g. name@gmail.com).');
    return;
  }

  // We have both fields — try the selected action or fallback to the just-clicked one
  const action = _authAction || preferred;
  if (action === 'register') {
    await doRegister(email, password);
  } else {
    await doLogin(email, password);
  }
}

async function doRegister(email, password) {
  setStatus(authStatus, 'Registering...');
  const res = await apiJson('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  setAuthState(res);
  setStatus(authStatus, `✅ Registered successfully! Logged in as ${res.email}.`);
}

async function doLogin(email, password) {
  setStatus(authStatus, 'Logging in...');
  const res = await apiJson('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  setAuthState(res);
  setStatus(authStatus, `✅ Welcome back, ${res.email}!`);
}

function logoutUser() {
  localStorage.removeItem('authToken');
  localStorage.removeItem('authEmail');
  localStorage.removeItem('authUserId');
  localStorage.removeItem('guestMode');
  setSelectedRunId(null);
  _authAction = null;

  // Clear input fields immediately
  authEmail.value    = '';
  authPassword.value = '';
  registerBtn.classList.remove('is-active');
  loginBtn.classList.remove('is-active');

  setAuthState();
}

// ── CV upload ──────────────────────────────────────────────────────────────
async function uploadCv() {
  const file = cvFile.files && cvFile.files[0];
  if (!file) {
    setStatus(cvStatus, 'Please choose a .txt or .md file first.');
    return;
  }

  setStatus(cvStatus, '⏳ Uploading CV and starting scraping...');
  const form = new FormData();
  form.append('file', file);

  const data = await apiJson('/api/cv/run?headless=1', {
    method: 'POST',
    body: form,
  });

  if (data.run_id != null) setSelectedRunId(data.run_id);

  const reuseNote = data.reused
    ? `\n♻️  Reused cached run from ${data.reused_age_hours ?? '?'}h ago (no scraping needed).`
    : '';

  setStatus(cvStatus,
    `✅ CV uploaded. job_title=${data.job_title || '—'}\n` +
    `Experience: ${data.years_experience ?? '—'} yr(s) (${data.experience_bucket || '—'})\n` +
    `Category: ${data.category} | DOU URL: ${data.dou_url}\n` +
    `Scrape: jobs_found=${data.scrape?.jobs_found}, synced=${data.scrape?.synced}` +
    reuseNote
  );

  setCurrentStep(2);
  await loadHistory();
}

// ── Job list ───────────────────────────────────────────────────────────────
function renderJobs(jobs) {
  jobsEl.innerHTML = '';
  for (const job of jobs) {
    const div = document.createElement('div');
    div.className = 'job';

    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = job.job_title || '(no title)';

    const enrichedPill = document.createElement('span');
    enrichedPill.className = 'pill';
    enrichedPill.textContent = job.role_summary ? 'enriched' : 'not enriched';
    title.appendChild(enrichedPill);

    const link = document.createElement('a');
    link.href = job.source_url;
    link.textContent = job.source_url;
    link.target = '_blank';
    link.rel = 'noreferrer';

    const meta = document.createElement('div');
    meta.className = 'muted';
    meta.textContent = `${job.company_name || '—'} • ${job.location || '—'} • ${job.work_type || '—'}`;

    div.appendChild(title);
    div.appendChild(meta);
    div.appendChild(link);

    if (job.role_summary) {
      const summary = document.createElement('div');
      summary.className = 'muted';
      summary.style.marginTop = '8px';
      summary.textContent = job.role_summary;
      div.appendChild(summary);
    }

    jobsEl.appendChild(div);
  }
}

async function refreshJobs() {
  const runId = getSelectedRunId();
  const path = runId ? `/api/jobs?run_id=${encodeURIComponent(runId)}` : '/api/jobs';
  const jobs = await apiJson(path);
  jobsMeta.textContent = `Total jobs in DB: ${jobs.length}`;
  renderJobs(jobs);
}

// ── Match ──────────────────────────────────────────────────────────────────
function renderMatch(items) {
  matchList.innerHTML = '';
  if (!items || items.length === 0) {
    matchList.innerHTML = '<div class="muted">No jobs to rank yet.</div>';
    return;
  }

  for (const it of items) {
    const div = document.createElement('div');
    div.className = 'match-item';
    div.tabIndex = 0;

    const top = document.createElement('div');
    top.className = 'row';

    const titleEl = document.createElement('div');
    titleEl.className = 'match-title';
    titleEl.textContent = it.job_title || `(job ${it.job_id})`;

    const score = document.createElement('div');
    score.className = 'match-score';
    score.textContent = fmtPct(it.score);

    top.appendChild(titleEl);
    top.appendChild(score);

    const link = document.createElement('a');
    link.className = 'match-url';
    link.href = it.source_url || '#';
    link.textContent = it.source_url || '';
    link.target = '_blank';
    link.rel = 'noreferrer';
    link.addEventListener('click', (e) => e.stopPropagation());

    const reasons = document.createElement('div');
    reasons.className = 'muted match-reasons';
    reasons.textContent = (it.reasons && it.reasons.length) ? it.reasons.join(' • ') : '—';

    const analysis = document.createElement('div');
    analysis.className = 'match-analysis';
    analysis.hidden = true;

    div.appendChild(top);
    if (it.source_url) div.appendChild(link);
    div.appendChild(reasons);
    div.appendChild(analysis);
    matchList.appendChild(div);

    async function onSelect() {
      for (const el of matchList.querySelectorAll('.match-analysis')) {
        if (el !== analysis) { el.hidden = true; el.innerHTML = ''; }
      }
      analysis.hidden = false;
      setStatus(analysis, `Analyzing job #${it.job_id}...`);
      try {
        const runId = getSelectedRunId();
        const p = runId
          ? `/api/match/job/${it.job_id}/analysis?run_id=${encodeURIComponent(runId)}`
          : `/api/match/job/${it.job_id}/analysis`;
        const res = await apiJson(p);
        if (res.html) {
          setHtml(analysis, res.html);
        } else {
          const method = res.method || 'heuristic';
          const head = `${res.job?.job_title || it.job_title}\nScore: ${fmtPct(res.score)}\nMethod: ${method}`;
          const urlLine = res.job?.source_url ? `\nURL: ${res.job.source_url}` : '';
          setStatus(analysis, `${head}${urlLine}\n\n${res.summary || ''}`.trim());
        }
      } catch (e) {
        setStatus(analysis, `Analysis failed: ${e.message}`);
      }
    }

    div.addEventListener('click', () => onSelect());
    div.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(); }
    });
  }
}

async function refreshMatch() {
  const runId = getSelectedRunId();
  setStatus(matchStatus, 'Computing match scores...');
  try {
    const p = runId ? `/api/match/scores?limit=15&run_id=${encodeURIComponent(runId)}` : '/api/match/scores?limit=15';
    const scores = await apiJson(p);
    renderMatch(scores.items);
    setStatus(matchStatus, `Ranked ${scores.items.length} / ${scores.total_jobs} jobs.`);
  } catch (e) {
    renderMatch([]);
    setStatus(matchStatus, `Match scoring failed: ${e.message}`);
    setStatus(matchReport, '—');
    return;
  }

  setStatus(matchReport, 'Building analysis...');
  try {
    const p = runId ? `/api/match/report?top_n=8&run_id=${encodeURIComponent(runId)}` : '/api/match/report?top_n=8';
    const rep = await apiJson(p);
    setStatus(matchReport, `[${rep.method || 'heuristic'}]\n${rep.summary || ''}`);
  } catch (e) {
    setStatus(matchReport, `Report: ${e.message}`);
  }
}

// ── Enrich pipeline ────────────────────────────────────────────────────────
async function runPipeline() {
  setStatus(pipelineStatus, '⏳ Step 2: fetching job texts...');
  const step2 = await apiJson('/api/jobs/fetch-text-all', { method: 'POST' });
  setStatus(pipelineStatus, `Step 2 done. done=${step2.done}, failed=${step2.failed}\n⏳ Step 3: enriching with AI...`);
  const step3 = await apiJson('/api/jobs/enrich-all', { method: 'POST' });
  setStatus(pipelineStatus, `✅ Finished. Enriched=${step3.enriched}, failed=${step3.failed}\nRefreshing...`);
  await refreshJobs();
  await refreshMatch();
  setStatus(pipelineStatus, `✅ All done. Enriched=${step3.enriched}, failed=${step3.failed}`);
}

// ── History ────────────────────────────────────────────────────────────────
function renderHistory(items) {
  if (!historyList) return;
  historyList.innerHTML = '';
  const selected = getSelectedRunId();

  if (!items || items.length === 0) {
    historyList.innerHTML = '<div class="muted">No previous runs yet.</div>';
    return;
  }

  for (const r of items) {
    const div = document.createElement('div');
    div.className = 'history-item';
    if (selected && String(r.run_id) === String(selected)) div.classList.add('is-selected');

    const titleEl = document.createElement('div');
    titleEl.className = 'history-item-title';
    titleEl.textContent = r.cv_job_title || r.category || `Run #${r.run_id}`;

    const meta = document.createElement('div');
    meta.className = 'history-item-meta';
    const bucket = r.experience_bucket ? ` • exp=${r.experience_bucket}` : '';
    const jobs   = r.jobs_found != null ? ` • ${r.jobs_found} jobs` : '';
    meta.textContent = `${r.created_at || ''}${bucket}${jobs}`.trim();

    div.appendChild(titleEl);
    div.appendChild(meta);

    div.addEventListener('click', async () => {
      setSelectedRunId(r.run_id);
      setCurrentStep(2);
      await refreshJobs();
      await refreshMatch();
      await loadHistory();
    });

    historyList.appendChild(div);
  }
}

async function loadHistory() {
  if (!historySection || !historyList) return;

  const token = localStorage.getItem('authToken');
  if (!token) {
    // Not logged in — hide history entirely, no errors shown
    historySection.hidden = true;
    return;
  }

  historySection.hidden = false;

  try {
    const items = await apiJson('/api/history/runs?limit=15');
    renderHistory(items);
  } catch (_) {
    // Silently ignore — server may be starting up or history not yet available
    historyList.innerHTML = '<div class="muted">No previous runs yet.</div>';
  }
}

// ── Event listeners ────────────────────────────────────────────────────────
registerBtn.addEventListener('click', () => {
  trySubmitAuth('register').catch((e) => setStatus(authStatus, `❌ Register failed: ${e.message}`));
});

loginBtn.addEventListener('click', () => {
  trySubmitAuth('login').catch((e) => setStatus(authStatus, `❌ Login failed: ${e.message}`));
});

logoutBtn.addEventListener('click', () => logoutUser());

guestBtn.addEventListener('click', () => {
  localStorage.setItem('guestMode', '1');
  setCurrentStep(1);
  setStatus(authStatus, 'Continuing as guest. Your data is shared with all other guests.');
});

uploadBtn.addEventListener('click', () => {
  uploadCv().catch((e) => setStatus(cvStatus, `❌ Upload failed: ${e.message}`));
});

refreshBtn.addEventListener('click', () => {
  refreshJobs().catch((e) => setStatus(pipelineStatus, `Refresh failed: ${e.message}`));
});

startBtn.addEventListener('click', () => {
  runPipeline().catch((e) => setStatus(pipelineStatus, `❌ Pipeline failed: ${e.message}`));
});

matchRefreshBtn.addEventListener('click', () => {
  refreshMatch().catch((e) => setStatus(matchStatus, `Refresh match failed: ${e.message}`));
});

// ── Init ───────────────────────────────────────────────────────────────────
// Always start fresh — clear any persisted auth/session state on every page load.
localStorage.removeItem('authToken');
localStorage.removeItem('authEmail');
localStorage.removeItem('authUserId');
localStorage.removeItem('guestMode');
localStorage.removeItem('selectedRunId');

setStatus(pipelineStatus, 'Upload your CV to start a new run.');
setStatus(matchStatus,    'Upload your CV to compute matches.');
setStatus(matchReport,    '—');

setAuthState();         // sets step based on localStorage token / guestMode
loadHistory().catch(() => {});

