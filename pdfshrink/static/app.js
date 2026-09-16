'use strict';

const $ = (id) => document.getElementById(id);
const SECTIONS = ['waiting', 'working', 'done', 'refused', 'failed'];

let chosen = null;
let targetOk = false;
let job = null;

function show(name) {
  SECTIONS.forEach((s) => { $(s).hidden = (s !== name); });
}

/* French style: a narrow no-break space as the thousands separator. */
function ko(bytes) {
  const value = Math.round(bytes / 1024);
  return value.toLocaleString('fr-FR').replace(/[   ]/g, ' ')
    + ' Ko';
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
  $('drop').querySelector('.big').textContent = file.name;
  refresh();
}

/* ---- the size box -------------------------------------------------- */

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
    ? 'compris : ' + data.label
    : 'je ne comprends pas cette taille';
  $('echo').classList.toggle('bad', !data.ok);
  refresh();
}

function refresh() { $('go').disabled = !(chosen && targetOk); }

/* ---- running ------------------------------------------------------- */

$('go').addEventListener('click', async () => {
  const body = new FormData();
  body.append('file', chosen);
  body.append('target', $('target').value);
  $('working-name').textContent = chosen.name;
  $('bar').value = 0;
  $('working-stage').textContent = 'Analyse du document…';
  show('working');
  const response = await fetch('/api/shrink', { method: 'POST', body });
  if (!response.ok) { show('failed'); return; }
  job = (await response.json()).job;
  poll();
});

const STAGES = {
  inspect: () => 'Analyse du document…',
  compress: (d, t) => t ? `Compression (page ${d} sur ${t})…` : 'Compression…',
  verify: () => 'Vérification du texte…',
};

async function poll() {
  const data = await (await fetch('/api/job/' + job)).json();
  if (data.state === 'working') {
    const label = STAGES[data.stage] || STAGES.inspect;
    $('working-stage').textContent = label(data.done, data.total);
    if (data.total) { $('bar').value = (data.done / data.total) * 100; }
    setTimeout(poll, 300);
    return;
  }
  if (data.state === 'done') { finish(data); }
  else if (data.state === 'refused') { refuse(data); }
  else { show('failed'); }
}

function saved(data, size) {
  $('done-sizes').textContent = ko(data.before) + ' → ' + ko(size);
  $('download').href = '/api/download/' + job;
  $('done-saved').textContent =
    'Enregistré aussi dans le dossier PDF-réduits';
  $('done-textlayer').hidden = !data.lost_text_layer;
  show('done');
}

function finish(data) { saved(data, data.size); }

function refuse(data) {
  $('refused-title').textContent =
    'Ce fichier ne peut pas descendre à ' + $('target').value.trim()
    + ' sans risque pour le texte.';

  if (data.reason === 'digital_floor') {
    $('refused-why').textContent =
      "C'est un document de texte ; il est déjà à sa taille minimale. "
      + 'Essayez de le couper en deux fichiers.';
    $('keep').hidden = true;
  } else if (data.reason === 'substitution_risk') {
    $('refused-why').textContent =
      'À cette taille, des caractères risquent d’être remplacés. '
      + 'Demandez une taille plus grande.';
    $('keep').hidden = true;
  } else if (data.reason === 'already_minimal' || !data.best_safe_size) {
    $('refused-why').textContent =
      'Ce fichier est déjà à peu près aussi petit que possible ; '
      + 'aucun réglage ne le réduirait vraiment. '
      + 'Essayez de le couper en deux fichiers.';
    $('keep').hidden = true;
  } else {
    $('refused-why').textContent =
      'C’est un document de ' + data.pages + ' pages ; à cette taille, '
      + 'les caractères deviendraient illisibles.';
    $('keep').textContent = 'Réduire quand même à ' + ko(data.best_safe_size);
    $('keep').hidden = false;
  }
  show('refused');
}

$('keep').addEventListener('click', async () => {
  const response = await fetch('/api/keep/' + job, { method: 'POST' });
  if (!response.ok) { show('failed'); return; }
  const data = await (await fetch('/api/job/' + job)).json();
  saved(data, data.best_safe_size);
});

$('reveal').addEventListener('click', () =>
  fetch('/api/reveal/' + job, { method: 'POST' }));

['again', 'again2', 'again3'].forEach((id) =>
  $(id).addEventListener('click', () => window.location.reload()));

checkTarget();
