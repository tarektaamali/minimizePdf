'use strict';

const $ = (id) => document.getElementById(id);
const SECTIONS = ['waiting', 'working', 'done', 'refused', 'failed'];

let chosen = null;
let targetOk = false;
let job = null;

function show(name) {
  SECTIONS.forEach((s) => { $(s).hidden = (s !== name); });
}

function kb(bytes) {
  return Math.round(bytes / 1024).toLocaleString('en-US') + ' KB';
}

/* ---- choosing a file ---------------------------------------------- */

$('drop').addEventListener('click', () => $('file').click());
$('drop').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); }
});
['dragenter', 'dragover'].forEach((e) =>
  $('drop').addEventListener(e, (ev) => {
    ev.preventDefault(); $('drop').classList.add('over');
  }));
['dragleave', 'drop'].forEach((e) =>
  $('drop').addEventListener(e, () => $('drop').classList.remove('over')));
$('drop').addEventListener('drop', (ev) => {
  ev.preventDefault();
  if (ev.dataTransfer.files.length) { pick(ev.dataTransfer.files[0]); }
});
$('file').addEventListener('change', (ev) => {
  if (ev.target.files.length) { pick(ev.target.files[0]); }
});

function pick(file) {
  chosen = file;
  $('drop-title').textContent = file.name;
  refresh();
}

/* ---- the size field ------------------------------------------------ */

let timer = null;
$('target').addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(checkTarget, 200);
});

async function checkTarget() {
  const response = await fetch('/api/size', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: $('target').value }),
  });
  const data = await response.json();
  targetOk = data.ok;
  $('echo').textContent = data.ok
    ? 'reads as ' + data.label.replace('Ko', 'KB').replace('Mo', 'MB')
    : 'not a size I can read';
  $('echo').classList.toggle('bad', !data.ok);
  refresh();
}

function refresh() { $('go').disabled = !(chosen && targetOk); }

/* ---- running -------------------------------------------------------- */

$('go').addEventListener('click', async () => {
  const body = new FormData();
  body.append('file', chosen);
  body.append('target', $('target').value);
  $('working-name').textContent = chosen.name;
  $('bar').style.width = '0%';
  $('working-stage').textContent = 'Reading the document…';
  show('working');
  const response = await fetch('/api/shrink', { method: 'POST', body });
  job = (await response.json()).job;
  poll();
});

const STAGES = {
  inspect: () => 'Reading the document…',
  compress: (d, t) => (t ? `Compressing — page ${d} of ${t}…` : 'Compressing…'),
  verify: () => 'Checking every character…',
};

async function poll() {
  const data = await (await fetch('/api/job/' + job)).json();
  if (data.state === 'working') {
    const label = STAGES[data.stage] || STAGES.inspect;
    $('working-stage').textContent = label(data.done, data.total);
    if (data.total) { $('bar').style.width = (data.done / data.total) * 100 + '%'; }
    setTimeout(poll, 300);
    return;
  }
  if (data.state === 'done') { finish(data, data.size); }
  else if (data.state === 'refused') { refuse(data); }
  else { show('failed'); }
}

/* ---- the result, and the measurement behind it ---------------------- */

function sizes(before, after) {
  $('done-sizes').innerHTML = '';
  const b = document.createElement('span');
  b.textContent = kb(before);
  const arrow = document.createElement('span');
  arrow.className = 'arrow';
  arrow.textContent = '→';
  const a = document.createElement('span');
  a.className = 'after';
  a.textContent = kb(after);
  $('done-sizes').append(b, arrow, a);
}

function proof(data) {
  const gauge = $('gauge');
  // A bilevel scan is the only path where a glyph can be substituted, so it
  // is the only one with a measurement to show. The others say what they did.
  if (data.check && data.check[0] >= 0) {
    const [largest, page] = data.check;
    const limit = data.threshold;
    $('verdict').textContent = 'Verified — no character altered';
    $('gauge-note').textContent =
      `largest change ${largest} px of ${limit} · page ${page} · edge noise only`;
    gauge.hidden = false;
    requestAnimationFrame(() => {
      $('gauge-fill').style.width =
        Math.min(100, (largest / limit) * 100).toFixed(1) + '%';
    });
  } else if (data.kind === 'digital') {
    $('verdict').textContent = 'Text untouched — never rasterised';
    $('gauge-note').textContent = '';
    gauge.hidden = true;
  } else {
    $('verdict').textContent = 'Re-rendered as images';
    $('gauge-note').textContent = data.dpi ? `at ${data.dpi} dpi` : '';
    gauge.hidden = true;
  }
}

function folderName(data) {
  // Name the folder the server actually wrote to, rather than repeating a
  // constant here: the two would drift, and the user would go looking in
  // the wrong place. Handles both separators.
  if (!data.saved) { return 'your Desktop'; }
  const parts = data.saved.split(/[\\/]/);
  return parts.length > 1 ? parts[parts.length - 2] : 'your Desktop';
}

function finish(data, after) {
  sizes(data.before, after);
  proof(data);
  $('download').href = '/api/download/' + job;
  $('done-saved').textContent =
    'Also saved to the ' + folderName(data) + ' folder on your Desktop.';
  $('done-textlayer').hidden = !data.lost_text_layer;
  show('done');
}

function refuse(data) {
  const asked = $('target').value.trim();
  $('refused-title').textContent = `This file can’t reach ${asked} without risking the text.`;

  if (data.reason === 'digital_floor') {
    $('refused-why').textContent =
      'It is a text PDF and already at its floor. Splitting it into two files '
      + 'will get you under the limit; rasterising it would turn the text into pictures.';
    $('keep').hidden = true;
  } else if (data.reason === 'substitution_risk') {
    $('refused-why').textContent =
      'Every setting small enough risks replacing a character. Ask for a larger size.';
    $('keep').hidden = true;
  } else if (data.reason === 'already_minimal' || !data.best_safe_size) {
    $('refused-why').textContent =
      'This file is already as small as it safely gets - no setting '
      + 'would make it meaningfully smaller. Try splitting it into two files.';
    $('keep').hidden = true;
  } else {
    $('refused-why').textContent =
      `It is ${data.pages} pages. At that size the characters would stop being readable.`;
    $('keep').textContent = 'Compress to ' + kb(data.best_safe_size) + ' instead';
    $('keep').hidden = false;
  }
  show('refused');
}

$('keep').addEventListener('click', async () => {
  await fetch('/api/keep/' + job, { method: 'POST' });
  const data = await (await fetch('/api/job/' + job)).json();
  finish(data, data.best_safe_size);
});

$('reveal').addEventListener('click', () =>
  fetch('/api/reveal/' + job, { method: 'POST' }));

['again', 'again2', 'again3'].forEach((id) =>
  $(id).addEventListener('click', () => window.location.reload()));

checkTarget();
