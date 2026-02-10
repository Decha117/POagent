let activeJobId = null;
let source = null;

const statusEl = document.getElementById('status');
const logsEl = document.getElementById('logs');
const statusMetaEl = document.getElementById('statusMeta');
const resultJsonEl = document.getElementById('resultJson');
const saveResultEl = document.getElementById('saveResult');
const poPreviewEl = document.getElementById('poPreview');

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const userId = document.getElementById('userId').value;
  const file = document.getElementById('poFile').files[0];
  if (!file) return;

  logsEl.textContent = '';
  resultJsonEl.value = '';
  saveResultEl.textContent = '';
  poPreviewEl.hidden = true;
  poPreviewEl.removeAttribute('src');

  const fd = new FormData();
  fd.append('user_id', userId);
  fd.append('file', file);

  const resp = await fetch('/upload', { method: 'POST', body: fd });
  const payload = await resp.json();
  activeJobId = payload.job_id;
  statusEl.textContent = payload.status;
  statusMetaEl.textContent = 'Progress: 5%';
  if (payload.file_url) {
    poPreviewEl.src = payload.file_url;
    poPreviewEl.hidden = false;
  }
  connectSSE(activeJobId);
  pollJob(activeJobId);
});

async function pollJob(jobId) {
  const timer = setInterval(async () => {
    const resp = await fetch(`/job/${jobId}`);
    const job = await resp.json();
    renderStatus(job);
    if (job.result) {
      resultJsonEl.value = JSON.stringify(job.result.extracted_fields, null, 2);
    }
    if (['done', 'failed'].includes(job.status)) {
      clearInterval(timer);
      await fetchLogs(jobId);
    }
  }, 1200);
}

function renderStatus(job) {
  statusEl.textContent = job.status;
  const progress = Number.isFinite(job.progress_percent) ? job.progress_percent : 0;
  const updatedAt = job.updated_at ? new Date(job.updated_at).toLocaleString() : '-';
  const lastMessage = job.last_message || '-';
  statusMetaEl.textContent = `Progress: ${progress}% | Last update: ${updatedAt} | Message: ${lastMessage}`;
}

function connectSSE(jobId) {
  if (source) source.close();
  source = new EventSource(`/job/${jobId}/stream`);
  source.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    const at = data.ts || new Date().toISOString();
    const progress = typeof data.progress_percent === 'number' ? ` (${data.progress_percent}%)` : '';
    const detail = data.total_duration_ms ? ` | total=${data.total_duration_ms}ms` : '';
    logsEl.textContent += `[${at}] ${data.status}${progress} - ${data.message}${detail}\n`;
    logsEl.scrollTop = logsEl.scrollHeight;
  };
}

async function fetchLogs(jobId) {
  const resp = await fetch(`/job/${jobId}/logs`);
  const data = await resp.json();
  logsEl.textContent += '\n----- persisted logs -----\n' + (data.logs || []).join('\n');
}

document.getElementById('confirmBtn').addEventListener('click', async () => {
  if (!activeJobId || !resultJsonEl.value) return;
  let fields;
  try {
    fields = JSON.parse(resultJsonEl.value);
  } catch {
    saveResultEl.textContent = 'JSON ไม่ถูกต้อง';
    return;
  }

  const resp = await fetch(`/job/${activeJobId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ extracted_fields: fields }),
  });
  const payload = await resp.json();
  saveResultEl.textContent = JSON.stringify(payload);
});
