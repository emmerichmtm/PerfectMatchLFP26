'use strict';
// PerfectMatchLFP26 - interact (weights, must-haves), compute, review, iterate, save.
const token = document.querySelector('meta[name="session-token"]').content;
const $ = id => document.getElementById(id);
const GRADE_FLOORS = [[0.9, 5], [0.8, 4], [0.65, 3], [0.5, 2]];
const LEVELS = {1: 'basic', 2: 'good', 3: 'native/very good'};
const NEEDS_VALUES = new Set(['partner_gender', 'partner_language', 'partner_hobby', 'partner_profile', 'partner_age', 'partner_country', 'partner_no_pet']);
const state = {
  defaults: null, survey: null, data: null, settings: null, rules: [], impact: new Map(),
  locks: [], forbids: [], iterations: [], view: -1, dirty: false, busy: false, stopped: false,
  filter: 'all', editing: new Set(), open: new Set(), uid: 0,
};

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key in node && typeof value !== 'string') node[key] = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) if (child != null && child !== false) node.append(child instanceof Node ? child : String(child));
  return node;
}
const clone = value => JSON.parse(JSON.stringify(value));
const natural = (a, b) => a.localeCompare(b, undefined, {numeric: true});
const title = text => String(text).replace(/(^|[\s/(-])\p{L}/gu, m => m.toUpperCase());
const pct = x => `${Math.round(x * 100)} %`;
const grade = d => (GRADE_FLOORS.find(([floor]) => Math.round(d * 1e6) / 1e6 >= floor) || [0, 1])[1];
const gradeName = g => state.defaults.grades[g];
const chip = (g, text) => el('span', {class: `grade g${g}`, text: text ?? g, 'aria-label': `grade ${g}, ${gradeName(g)}`});
const key = (s, l) => `${s}|${l}`;

async function api(path, body) {
  const options = body === undefined ? {} : {method: 'POST', body: JSON.stringify(body),
    headers: {'Content-Type': 'application/json', 'X-Session-Token': token}};
  let response;
  try { response = await fetch(path, options); }
  catch { throw new Error('Cannot reach the app. Start PerfectMatchLFP26 again and reload this page.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Something went wrong. Try again.');
  return data;
}
async function readText(file) {
  if (file.size > 4 * 1024 * 1024) throw new Error(`${file.name} is larger than 4 MB.`);
  const buffer = await file.arrayBuffer();
  try { return new TextDecoder('utf-8', {fatal: true}).decode(buffer); }
  catch { return new TextDecoder('windows-1252').decode(buffer); }  // Excel "CSV" without UTF-8
}
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], {type}));
  const link = el('a', {href: url, download: name});
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// ---------- tooltip ----------
const tip = $('tooltip');
function tooltip(node, text) {
  const show = event => {
    tip.textContent = typeof text === 'function' ? text() : text; tip.hidden = false;
    const box = event.type === 'focus' ? node.getBoundingClientRect() : {left: event.clientX, bottom: event.clientY};
    const x = Math.min(box.left + 12, innerWidth - tip.offsetWidth - 8), y = Math.min(box.bottom + 12, innerHeight - tip.offsetHeight - 8);
    tip.style.left = `${Math.max(8, x)}px`; tip.style.top = `${Math.max(8, y)}px`;
  };
  node.addEventListener('mouseenter', show); node.addEventListener('mousemove', show); node.addEventListener('focus', show);
  for (const ev of ['mouseleave', 'blur']) node.addEventListener(ev, () => { tip.hidden = true; });
  return node;
}

// ---------- status, phase, dirty ----------
function setStatus(text, kind = '') { const s = $('compute-status'); s.textContent = text; s.className = `hint ${kind}`; }
function refreshChrome() {
  const n = state.iterations.length;
  $('compute').textContent = state.busy ? 'Computing…' : `Compute iteration ${n + 1} →`;
  $('compute').disabled = state.busy || state.stopped || !state.data;
  for (const id of ['survey-file', 'example', 'settings-file', 'rules-file']) $(id).disabled = state.busy || state.stopped;
  let phase;
  if (state.stopped) phase = 'The app is closed.';
  else if (!state.data) phase = 'Load the survey export to begin.';
  else if (state.busy) phase = 'Compute phase: finding the best pairs…';
  else if (!n) phase = 'Interact phase: adjust weights and must-haves, then compute iteration 1.';
  else if (state.dirty) phase = `Interact phase: changes since iteration ${n}. Compute iteration ${n + 1} to see their effect.`;
  else phase = `Iteration ${n} ready. Review, adjust and compute again to iterate.`;
  $('phase').textContent = phase;
  const stale = $('stale');
  stale.replaceChildren(); stale.hidden = true;
  if (n && state.view < n - 1) {
    stale.hidden = false;
    stale.append(el('span', {text: `You are viewing iteration ${state.view + 1} of ${n}.`}),
      el('button', {class: 'secondary small', text: 'Restore its settings', onclick: () => restore(state.view)}),
      el('button', {class: 'link', text: 'Back to latest', onclick: () => { state.view = n - 1; renderResults(); }}));
  } else if (n && state.dirty) {
    stale.hidden = false;
    stale.append(el('span', {text: `Settings changed after iteration ${n}. The results below do not include those changes yet.`}),
      el('button', {class: 'primary small', text: `Compute iteration ${n + 1}`, onclick: compute, disabled: state.busy}));
  }
}
function markDirty() { state.dirty = true; refreshChrome(); }
function busy(on) { state.busy = on; refreshChrome(); }

// ---------- survey data ----------
async function loadSurvey(name, text) {
  if (state.iterations.length && !confirm('Loading new survey data clears all iterations, locks and must-have edits. Continue?')) return;
  busy(true); setStatus('Reading the survey…');
  try {
    const data = await api('/api/analyse', {survey: text, settings: state.settings});
    Object.assign(state, {survey: {name, text}, data, locks: [], forbids: [], iterations: [], view: -1, dirty: false});
    state.rules = data.rules.map(withUid); state.editing.clear(); state.open.clear();
    setImpact(state.rules, data.impact);
    renderLeft(); renderIterations(); renderResults();
    setStatus(`Read ${name}. Check the must-haves, then compute.`);
  } catch (error) {
    setStatus(error.message, 'error');
    $('survey-status').textContent = error.message;
  } finally { busy(false); }
}
function withUid(rule) { return {...rule, uid: ++state.uid}; }
function renderData() {
  const d = state.data, box = $('data-summary');
  box.replaceChildren();
  if (!d) return;
  $('survey-status').textContent = `Loaded: ${state.survey.name}`;
  const flagged = Object.values(d.people).filter(p => p.flags.length).sort((a, b) => natural(a.id, b.id));
  box.append(el('div', {class: 'summary-line'},
    el('span', {}, el('strong', {text: d.rows}), ' rows'),
    el('span', {}, el('strong', {text: d.counts.internationals}), ' internationals'),
    el('span', {}, el('strong', {text: d.counts.locals}), ' locals'),
    el('span', {}, el('strong', {text: d.excluded.length}), ' excluded'),
    el('span', {}, el('strong', {text: flagged.length}), ' flagged')));
  if (d.excluded.length || flagged.length) {
    box.append(el('details', {open: d.excluded.length > 0}, el('summary', {text: 'Data check: excluded rows and flags'}),
      el('ul', {class: 'issues'},
        d.excluded.map(e => el('li', {}, el('b', {text: `${e.id} excluded`}), ` (line ${e.line}): ${e.reasons.join('; ')}`)),
        flagged.map(p => el('li', {}, el('b', {text: p.id}), `: ${p.flags.join('; ')}`)))));
  }
}

// ---------- weights and settings ----------
function weightShare(c) {
  const s = state.settings, total = Object.keys(state.defaults.criteria).reduce((sum, x) => sum + s[`weight_${x}`], 0);
  return s[`weight_${c}`] / total;
}
function updateWeights() {
  for (const c of Object.keys(state.defaults.criteria)) {
    $(`weight-${c}-out`).textContent = state.settings[`weight_${c}`];
    $(`weight-${c}-share`).textContent = pct(weightShare(c));
    $(`weight-${c}`).setAttribute('aria-valuetext', `${state.settings[`weight_${c}`]} of 10, share ${pct(weightShare(c))}`);
  }
}
function renderWeights() {
  const s = state.settings;
  $('weights').replaceChildren(...Object.entries(state.defaults.criteria).map(([c, label]) => {
    const id = `weight-${c}`;
    const input = el('input', {type: 'range', id, min: 1, max: 10, step: 1, value: String(s[`weight_${c}`]),
      oninput: event => { s[`weight_${c}`] = Number(event.target.value); updateWeights(); markDirty(); }});
    const share = tooltip(el('span', {class: 'share', id: `${id}-share`}), () => `${label}: exponent share ${pct(weightShare(c))} of the overall desirability`);
    return el('div', {class: 'weight'}, el('label', {for: id, text: label}), input, el('output', {for: id, id: `${id}-out`}), share);
  }));
  updateWeights();
}
function settingInput(name, {percent = false, select = null} = {}) {
  const s = state.settings, spec = state.defaults.spec.find(x => x.name === name);
  const apply = async value => {
    s[name] = value; markDirty();
    if (name === 'max_missing_answers') await reanalyse();
  };
  if (select) {
    return el('select', {'aria-label': spec.description, onchange: e => apply(Number(e.target.value))},
      Object.entries(select).map(([v, label]) => el('option', {value: v, text: label, selected: Number(v) === s[name]})));
  }
  const input = el('input', {type: 'number', class: 'num', 'aria-label': spec.description,
    min: percent ? spec.min * 100 : spec.min, max: percent ? spec.max * 100 : spec.max, step: spec.type === 'int' || percent ? 1 : 0.5,
    value: String(percent ? Math.round(s[name] * 100) : s[name]),
    onchange: e => {
      const v = Number(e.target.value);
      if (!Number.isFinite(v)) return;
      apply(percent ? v / 100 : v);
    }});
  tooltip(input, spec.description);
  return input;
}
function renderAnchors() {
  const levels = {1: 'basic', 2: 'good', 3: 'native'};
  $('anchors').replaceChildren(
    el('span', {class: 'head', text: 'Criterion'}), el('span', {class: 'head', text: 'Just acceptable · 50 %'}), el('span', {class: 'head', text: 'Fully satisfactory · 80 %'}),
    el('span', {text: 'Shared language level'}), settingInput('language_acceptable', {select: levels}), settingInput('language_satisfactory', {select: levels}),
    el('span', {text: 'Shared hobby categories'}), settingInput('hobbies_acceptable'), settingInput('hobbies_satisfactory'),
    el('span', {text: 'Age outside wish (%)'}), settingInput('age_tolerance', {percent: true}), settingInput('age_satisfactory', {percent: true}),
    el('span', {text: 'Missed profile wish counts (%)'}), settingInput('profile_missed', {percent: true}), el('span'));
  const toggle = (name, label) => el('label', {}, el('input', {type: 'checkbox', checked: state.settings[name],
    onchange: e => { state.settings[name] = e.target.checked; markDirty(); }}), label);
  $('hard-rules').replaceChildren(
    toggle('enforce_gender', 'Respect gender wishes (hard rule)'),
    toggle('enforce_pets', 'No pet conflicts (hard rule)'),
    toggle('require_shared_language', 'At least one shared language (hard rule)'),
    el('label', {}, 'Exclude rows missing more than … of 8 key answers', settingInput('max_missing_answers')),
    el('label', {}, 'Solver time limit per stage (s)', settingInput('solver_time_limit_seconds')));
}
async function reanalyse() {
  if (!state.survey) return;
  try {
    const data = await api('/api/analyse', {survey: state.survey.text, settings: state.settings});
    const before = new Set(Object.keys(state.data.people)), now = new Set(Object.keys(data.people));
    const dropped = state.rules.filter(r => !now.has(r.id));
    state.rules = state.rules.filter(r => now.has(r.id)).concat(data.rules.filter(r => !before.has(r.id)).map(withUid));
    state.data = data;
    renderData(); renderRules(); scheduleImpact();
    if (dropped.length) setStatus(`Must-haves removed for excluded rows: ${[...new Set(dropped.map(r => r.id))].join(', ')}.`);
  } catch (error) { setStatus(error.message, 'error'); }
}

// ---------- must-have rules ----------
function describe(r) {
  const values = r.values.map(v => r.kind === 'partner_language' ? title(v) : v).join(', ') || '?';
  switch (r.kind) {
    case 'partner_language': return `Partner speaks ${values} (at least ${LEVELS[r.level]})`;
    case 'shared_language': return `A shared language at least ${LEVELS[r.level]}`;
    case 'partner_hobby': return `Partner has ${r.count === 1 ? 'any' : `at least ${r.count}`} of: ${values}`;
    case 'shared_hobbies': return `At least ${r.count} shared hobby categor${r.count === 1 ? 'y' : 'ies'}`;
    case 'partner_no_pet': return r.values.includes('any') ? 'Partner has no pets' : `Partner has no ${values}`;
    case 'staff_check': return `Staff check: ${r.note || r.text || 'see the survey answer'}`;
    default: return `${state.defaults.kinds[r.kind]} ${values}`;
  }
}
const complete = r => !NEEDS_VALUES.has(r.kind) || r.values.length > 0;
const plainRule = r => ({id: r.id, kind: r.kind, values: r.values, level: r.level, count: r.count, status: r.status, note: r.note, text: r.text});
function setImpact(rules, counts) { rules.forEach((r, i) => state.impact.set(r.uid, counts[i])); }
let impactTimer = null;
function scheduleImpact() {
  clearTimeout(impactTimer);
  impactTimer = setTimeout(async () => {
    const rules = state.rules.filter(complete);
    try {
      const {impact} = await api('/api/impact', {survey: state.survey.text, settings: state.settings, rules: rules.map(plainRule)});
      setImpact(rules, impact); renderRules();
    } catch (error) { setStatus(error.message, 'error'); }
  }, 350);
}
function ruleChanged(rule) { rule.status = 'confirmed'; markDirty(); renderRules(); scheduleImpact(); }
function choices(options, selected, onToggle, labelOf = x => x) {
  return el('div', {class: 'choices'}, options.map(option => el('button', {type: 'button', class: 'chip',
    'aria-pressed': String(selected.includes(option)), text: labelOf(option), onclick: () => onToggle(option)})));
}
function toggleValue(rule, value) {
  rule.values = rule.values.includes(value) ? rule.values.filter(v => v !== value) : [...rule.values, value];
  ruleChanged(rule);
}
function ageValue(label) {
  const m = label.match(/(\d+)\s*-\s*(\d+)/), over = label.match(/over\s*(\d+)/i);
  return m ? `${m[1]}-${m[2]}` : over ? `${Number(over[1]) + 1}-${Number(over[1]) + 15}` : label;
}
function ruleEditor(rule) {
  const o = state.data.options;
  const levelSelect = () => el('label', {}, 'at least ', el('select', {onchange: e => { rule.level = Number(e.target.value); ruleChanged(rule); }},
    Object.entries(LEVELS).map(([v, label]) => el('option', {value: v, text: label, selected: Number(v) === rule.level}))));
  const countInput = text => el('label', {}, text, ' ', el('input', {type: 'number', min: 1, max: 20, value: String(rule.count),
    onchange: e => { rule.count = Math.max(1, Math.min(20, Number(e.target.value) || 1)); ruleChanged(rule); }}));
  const listInput = placeholder => el('input', {type: 'text', placeholder, value: rule.values.join('; '),
    'aria-label': placeholder, onchange: e => { rule.values = e.target.value.split(';').map(v => v.trim()).filter(Boolean); ruleChanged(rule); }});
  const body = {
    partner_gender: () => [choices([...new Set(['female', 'male', ...o.genders])], rule.values, v => toggleValue(rule, v), title)],
    partner_language: () => [choices(o.languages, rule.values, v => toggleValue(rule, v), title), levelSelect()],
    shared_language: () => [levelSelect()],
    partner_hobby: () => [choices(o.hobbies, rule.values, v => toggleValue(rule, v)), countInput('Partner has at least')],
    shared_hobbies: () => [countInput('Shared categories, at least')],
    partner_profile: () => [choices(o.profiles.filter((p, i, a) => a.indexOf(p) === i), rule.values, v => toggleValue(rule, v))],
    partner_age: () => [choices(o.wanted_ages.map(ageValue), rule.values, v => toggleValue(rule, v)), listInput('Age ranges, e.g. 20-30; 31-35')],
    partner_country: () => [choices(o.countries, rule.values, v => toggleValue(rule, v)), listInput('Countries, e.g. Japan; Korea')],
    partner_no_pet: () => [choices(o.pet_kinds, rule.values, v => toggleValue(rule, v))],
    staff_check: () => [el('input', {type: 'text', value: rule.note, placeholder: 'What staff should check', 'aria-label': 'What staff should check',
      onchange: e => { rule.note = e.target.value; ruleChanged(rule); }})],
  }[rule.kind]();
  return el('div', {class: 'editor'},
    el('label', {}, 'Rule type ', el('select', {onchange: e => { Object.assign(rule, {kind: e.target.value, values: [], level: 1, count: 1, note: ''}); ruleChanged(rule); }},
      Object.entries(state.defaults.kinds).map(([k, label]) => el('option', {value: k, text: label, selected: k === rule.kind})))),
    ...body,
    !complete(rule) && el('p', {class: 'impact none', text: 'Choose at least one value, or remove this must-have.'}));
}
function renderRules() {
  const people = state.data ? state.data.people : {};
  const counts = {all: state.rules.length, proposed: state.rules.filter(r => r.status === 'proposed').length,
    staff: state.rules.filter(r => r.kind === 'staff_check').length,
    international: state.rules.filter(r => people[r.id]?.side === 'international').length};
  counts.local = counts.all - counts.international;
  const labels = {all: 'All', proposed: 'To confirm', staff: 'Staff checks', international: 'Internationals', local: 'Locals'};
  $('rule-filters').replaceChildren(...Object.entries(labels).map(([k, label]) => el('button', {type: 'button', class: 'chip',
    'aria-pressed': String(state.filter === k), text: `${label} ${counts[k]}`, onclick: () => { state.filter = k; renderRules(); }})));
  const shown = state.rules.filter(r => state.filter === 'all' || (state.filter === 'proposed' && r.status === 'proposed')
    || (state.filter === 'staff' && r.kind === 'staff_check') || people[r.id]?.side === state.filter);
  const box = $('rules');
  if (!state.data) return;
  box.replaceChildren(...(shown.length ? [] : [el('p', {class: 'hint', text: 'No must-haves in this view.'})]), ...shown.map(rule => {
    const person = people[rule.id], count = state.impact.get(rule.uid), editing = state.editing.has(rule.uid);
    const other = person.side === 'international' ? 'locals' : 'internationals';
    const impact = rule.kind === 'staff_check' ? el('span', {class: 'impact', text: 'checked by staff, not automatically'})
      : !complete(rule) ? null : count == null ? el('span', {class: 'impact', text: 'counting…'})
      : el('span', {class: `impact ${count === 0 ? 'none' : ''}`, text: count === 0 ? `no ${other} meet this` : `${count} ${other} meet this`});
    return el('div', {class: `rule ${complete(rule) ? '' : 'incomplete'}`},
      el('div', {class: 'rule-top'}, el('span', {class: 'who', text: rule.id}), el('span', {class: 'side', text: person.side}),
        person.must_criterion && el('span', {class: 'impact', text: person.must_criterion}),
        el('span', {class: `status ${rule.status}`, text: rule.status === 'proposed' ? 'proposed' : 'checked'})),
      rule.text && el('p', {class: 'quote', text: `"${rule.text}"`}),
      el('p', {class: 'rule-label', text: describe(rule)}), impact,
      el('div', {class: 'rule-actions'},
        el('button', {class: 'link', text: editing ? 'Done' : 'Edit', 'aria-expanded': String(editing),
          onclick: () => { editing ? state.editing.delete(rule.uid) : state.editing.add(rule.uid); renderRules(); }}),
        rule.status === 'proposed' && el('button', {class: 'link', text: 'Mark checked', onclick: () => { rule.status = 'confirmed'; renderRules(); }}),
        el('button', {class: 'link', text: 'Remove', onclick: () => { state.rules = state.rules.filter(r => r !== rule); markDirty(); renderRules(); scheduleImpact(); }})),
      editing && ruleEditor(rule));
  }));
  const add = $('add-rule');
  add.hidden = false;
  const ids = Object.keys(people).sort(natural);
  const who = el('select', {'aria-label': 'Person'}, ids.map(id => el('option', {value: id, text: `${id} · ${people[id].side}`})));
  const kind = el('select', {'aria-label': 'Rule type'}, Object.entries(state.defaults.kinds).map(([k, label]) => el('option', {value: k, text: label})));
  add.replaceChildren(el('span', {class: 'hint', text: 'Add a must-have:'}), who, kind, el('button', {class: 'secondary small', text: 'Add', onclick: () => {
    const rule = withUid({id: who.value, kind: kind.value, values: [], level: 1, count: 1, status: 'confirmed', note: 'added by staff', text: people[who.value].must_text || ''});
    state.rules.push(rule); state.editing.add(rule.uid); state.filter = 'all'; markDirty(); renderRules(); scheduleImpact();
  }}));
}

// ---------- locks and forbids ----------
function pinned(list, s, l) { return list.some(([a, b]) => a === s && b === l); }
function togglePin(kind, s, l) {
  const list = kind === 'lock' ? 'locks' : 'forbids', other = kind === 'lock' ? 'forbids' : 'locks';
  state[other] = state[other].filter(([a, b]) => !(a === s && b === l));
  state[list] = pinned(state[list], s, l) ? state[list].filter(([a, b]) => !(a === s && b === l)) : [...state[list], [s, l]];
  markDirty(); renderPins(); renderResults();
}
function renderPins() {
  const items = [...state.locks.map(p => ['lock', ...p]), ...state.forbids.map(p => ['forbid', ...p])];
  $('pins-card').hidden = !items.length;
  $('pins').replaceChildren(...items.map(([kind, s, l]) => el('li', {},
    el('span', {text: `${kind === 'lock' ? 'Locked' : 'Forbidden'}: ${s} – ${l}`}),
    el('button', {class: 'link', text: 'Remove', onclick: () => togglePin(kind, s, l)}))));
}

// ---------- compute and iterations ----------
async function compute() {
  if (!state.data || state.busy) return;
  const incomplete = state.rules.filter(r => !complete(r));
  if (incomplete.length) { setStatus(`Complete or remove the must-have for ${incomplete.map(r => r.id).join(', ')} first.`, 'error'); return; }
  const n = state.iterations.length + 1;
  busy(true); setStatus(`Computing iteration ${n}…`);
  try {
    const result = await api('/api/compute', {survey: state.survey.text, survey_name: state.survey.name, settings: state.settings,
      rules: state.rules.map(plainRule), locks: state.locks, forbids: state.forbids, iteration: n});
    state.iterations.push({n, at: new Date(), result, settings: clone(state.settings), rules: clone(state.rules),
      locks: clone(state.locks), forbids: clone(state.forbids)});
    state.view = state.iterations.length - 1; state.dirty = false;
    renderIterations(); renderResults();
    const s = result.summary;
    setStatus(s.unmatched_internationals ? `Iteration ${n}: ${s.unmatched_internationals} international(s) not matched. See the results.`
      : `Iteration ${n}: all ${s.internationals} internationals matched.`, s.unmatched_internationals ? 'error' : '');
  } catch (error) { setStatus(error.message, 'error'); }
  finally { busy(false); }
}
function restore(index) {
  const it = state.iterations[index];
  Object.assign(state, {settings: clone(it.settings), locks: clone(it.locks), forbids: clone(it.forbids)});
  state.rules = clone(it.rules); state.editing.clear(); state.view = state.iterations.length - 1;
  renderLeft(); renderResults(); markDirty(); scheduleImpact();
  setStatus(`Settings of iteration ${it.n} restored. Compute to continue from them.`);
}
function renderIterations() {
  $('iterations').replaceChildren(...state.iterations.map((it, i) => {
    const s = it.result.summary, before = state.iterations[i - 1];
    const changed = before ? it.result.pairs.filter(p => !before.result.pairs.some(q => q.student === p.student && q.local === p.local)).length : null;
    return el('button', {class: 'iteration', 'aria-pressed': String(i === state.view), onclick: () => { state.view = i; renderResults(); }},
      el('b', {text: `#${it.n}  ${s.matched}/${s.internationals} matched`}),
      `lowest ${s.lowest_grade ?? '–'} · avg ${s.average != null ? s.average.toFixed(2) : '–'}`, changed != null ? ` · ${changed} changed` : '');
  }));
}

// ---------- results ----------
function tile(label, value, sub, kind = '') {
  return el('div', {class: `tile ${kind}`}, el('div', {class: 'label', text: label}), el('div', {class: 'value'}, value), sub && el('div', {class: 'sub', text: sub}));
}
function renderResults() {
  refreshChrome();
  renderIterations();
  const it = state.iterations[state.view];
  $('empty').hidden = Boolean(it); $('results').hidden = !it;
  if (!it) return;
  const r = it.result, s = r.summary, people = r.people;
  $('result-title').textContent = `Iteration ${it.n} · ${it.at.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
  const allMatched = !s.unmatched_internationals;
  $('tiles').replaceChildren(
    tile('Internationals matched', [el('span', {text: allMatched ? '✓' : '⚠', 'aria-hidden': 'true'}), `${s.matched} / ${s.internationals}`],
      allMatched ? 'all matched' : `${s.unmatched_internationals} not matched`, allMatched ? 'good' : 'critical'),
    tile('Lowest pair', s.lowest != null ? [chip(s.lowest_grade), s.lowest.toFixed(2)] : '–', s.lowest != null ? gradeName(s.lowest_grade) : ''),
    tile('Average pair', s.average != null ? [chip(s.average_grade), s.average.toFixed(2)] : '–', s.average != null ? gradeName(s.average_grade) : ''),
    tile('Locals matched', `${s.matched} / ${s.locals}`, `${s.unmatched_locals} without a partner`),
    tile('Staff checks', String(s.staff_checks), 'pairs with a wish to check by hand'),
    tile('Gender to resolve', String(s.to_resolve), 'pairs scored as min–max'));
  const alerts = [];
  if (!allMatched) alerts.push(el('div', {class: 'banner critical'}, el('strong', {text: 'Not every international is matched. '}),
    el('span', {text: r.unmatched.internationals.map(u => `${u.id}: ${u.reason}`).join(' · ')})));
  for (const w of r.warnings) alerts.push(el('div', {class: 'banner', text: w}));
  $('alerts').replaceChildren(...alerts);

  const criteria = state.defaults.criteria;
  $('legend').replaceChildren(...[1, 2, 3, 4, 5].map(g => el('span', {}, chip(g), gradeName(g))));
  const rows = [['overall', 'Overall', null], ...Object.entries(criteria).map(([c, label]) => [c, label, r.weights[c]])];
  $('distribution').replaceChildren(...rows.map(([c, label, weight]) => {
    const counts = r.distribution[c], total = counts.reduce((a, b) => a + b, 0) || 1;
    const gradeOf = p => c === 'overall' ? p.grade : p.criteria[c].grade;
    const stack = el('div', {class: 'stack', role: 'img', 'aria-label': `${label}: ` + counts.map((n, i) => `${n} pairs grade ${i + 1}`).join(', ')},
      counts.map((n, i) => {
        if (!n) return null;
        const seg = el('div', {class: `seg g${i + 1}`, text: n / total >= 0.08 ? n : ''});
        seg.style.flex = `${n} 1 0`;
        const names = r.pairs.filter(p => gradeOf(p) === i + 1).map(p => `${p.student}–${p.local}`);
        return tooltip(seg, `${label} · grade ${i + 1} (${gradeName(i + 1)}): ${n} pair${n === 1 ? '' : 's'}\n${names.join(', ')}`);
      }));
    const mean = c === 'overall' ? s.average : r.means[c];
    return el('div', {class: `dist-row ${c === 'overall' ? 'overall' : ''}`},
      el('div', {class: 'name'}, label, el('small', {text: weight != null ? `weight ${pct(weight)}` : 'weighted product'})),
      r.pairs.length ? stack : el('span', {class: 'hint', text: 'no pairs'}),
      el('div', {class: 'mean'}, mean != null ? [chip(grade(mean)), ` ${mean.toFixed(2)}`] : '–'));
  }));
  $('constraints').replaceChildren(...r.constraints.map(c => {
    const kind = !c.enabled ? 'off' : c.status;
    return el('li', {}, el('span', {class: `icon ${kind}`, text: {ok: '✓', warn: '!', off: '○'}[kind], 'aria-hidden': 'true'}),
      el('strong', {text: c.name + (c.enabled ? '' : ' (off)')}), el('span', {text: c.enabled ? c.text : 'switched off in the settings - review by hand'}));
  }));

  const body = $('pairs');
  body.replaceChildren();
  for (const p of r.pairs) {
    const k = key(p.student, p.local), open = state.open.has(k);
    const crit = c => {
      const x = p.criteria[c];
      const sides = x.sides ? `\nInternational's wish: grade ${x.side_grades.student} · Local's wish: grade ${x.side_grades.local}` : '';
      return tooltip(el('td', {tabindex: 0}, chip(x.grade)), `${criteria[c]}: ${x.d.toFixed(2)} · ${gradeName(x.grade)}\n${x.detail}${sides}`);
    };
    const staff = p.rules.filter(x => x.result === 'staff').length;
    const overall = p.uncertain ? `${p.score.toFixed(2)} (${p.score_min.toFixed(2)}–${p.score_max.toFixed(2)})` : p.score.toFixed(2);
    const row = el('tr', {class: `pair ${open ? 'open' : ''}`, 'aria-expanded': String(open), onclick: () => { open ? state.open.delete(k) : state.open.add(k); renderResults(); }},
      el('td', {class: 'num'}, el('strong', {text: p.student}), ' – ', el('strong', {text: p.local}), p.locked ? ' 🔒' : ''),
      el('td', {}, el('span', {class: 'overall-cell'}, chip(p.grade), overall)),
      ...Object.keys(criteria).map(crit),
      el('td', {class: 'flags'}, staff ? el('span', {class: 'flag staff', text: `⚑ ${staff}`, title: 'wish to check by hand'}) : null,
        p.uncertain ? el('span', {class: 'flag resolve', text: '? gender', title: 'blank gender: min–max'}) : null,
        p.notes.length && !staff && !p.uncertain ? el('span', {text: `${p.notes.length} note${p.notes.length === 1 ? '' : 's'}`}) : null),
      el('td', {class: 'num'},
        el('button', {class: 'pin lock', 'aria-pressed': String(pinned(state.locks, p.student, p.local)), text: pinned(state.locks, p.student, p.local) ? 'Locked' : 'Lock',
          onclick: e => { e.stopPropagation(); togglePin('lock', p.student, p.local); }}),
        el('button', {class: 'pin forbid', 'aria-pressed': String(pinned(state.forbids, p.student, p.local)), text: 'Forbid',
          onclick: e => { e.stopPropagation(); togglePin('forbid', p.student, p.local); }})));
    body.append(row);
    if (open) body.append(el('tr', {class: 'detail'}, el('td', {colspan: 8}, pairDetail(p, people, r))));
  }

  const u = r.unmatched;
  $('unmatched').replaceChildren(
    u.internationals.length ? el('ul', {class: 'unmatched-list critical'}, u.internationals.map(x => el('li', {}, el('b', {text: x.id}), ` (international): ${x.reason}`)))
      : el('p', {class: 'hint', text: 'Every international has a partner.'}),
    u.locals.length ? el('details', {}, el('summary', {text: `${u.locals.length} locals without a partner`}),
      el('ul', {class: 'unmatched-list'}, u.locals.map(x => el('li', {}, el('b', {text: x.id}), `: ${x.reason}`)))) : null,
    r.excluded.length ? el('details', {open: true}, el('summary', {text: `${r.excluded.length} rows excluded from the analysis`}),
      el('ul', {class: 'unmatched-list'}, r.excluded.map(x => el('li', {}, el('b', {text: x.id}), ` (line ${x.line}): ${x.reasons.join('; ')}`)))) : null);
  $('report').textContent = r.report;
}
function personCard(p, other, sideLabel, sharedHobbies) {
  const languages = Object.entries(p.languages).map(([n, l]) => `${title(n)} (${LEVELS[l]})`).join(', ') || '–';
  const pets = [p.has_pets && `has pets${p.pet_text ? `: ${p.pet_text}` : ''}`, p.no_pets_at_home && 'no pets at home',
    p.pets_welcome && 'all pets welcome', p.no_pets_wanted && 'no pets at visits', p.unwanted_pet_text && `not wanted: ${p.unwanted_pet_text}`].filter(Boolean).join('; ') || '–';
  const hobbies = p.hobbies.length ? p.hobbies.flatMap((h, i) => [i ? ', ' : '', sharedHobbies.includes(h) ? el('span', {class: 'shared', text: h}) : h]) : '–';
  const rows = [['Country', p.country], ['Profile', p.profile.join(', ')], ['Wishes profile', p.wanted_profile.join(', ')],
    ['Age', p.age_label], ['Wishes age', p.wanted_age.length ? p.wanted_age_labels.join(', ') : 'all ages'],
    ['Gender', p.gender ? title(p.gender) : 'blank - to resolve'], ['Wishes gender', p.wanted_gender === 'any' ? 'all are fine' : title(p.wanted_gender)],
    ['Languages', languages], ['Hobbies', hobbies], ['Other hobbies', p.hobbies_other], ['Pets', pets],
    ['Must-have', p.must_criterion ? `${p.must_criterion}${p.must_text ? `: "${p.must_text}"` : ''}` : ''],
    ['Motivation', p.motivation], ['Appreciates', p.appreciate], ['Additional info', p.additional], ['Associates', p.associates],
    ['Flags', p.flags.join('; ')]];
  return el('div', {class: 'person'}, el('h4', {text: `${p.id} · ${sideLabel}`}),
    el('dl', {}, rows.filter(([, v]) => v && (!Array.isArray(v) || v.length)).flatMap(([k, v]) => [el('dt', {text: k}), el('dd', {}, v)])));
}
function pairDetail(p, people, r) {
  const criteria = state.defaults.criteria;
  const card = (label, g, d, lines) => el('div', {class: 'crit'}, el('div', {class: 'top'}, el('span', {text: label}), el('span', {}, chip(g), ` ${d.toFixed(2)}`)),
    lines.filter(Boolean).map(t => el('p', {text: t})));
  const strip = el('div', {class: 'crit-strip'},
    card('Overall', p.grade, p.score, [gradeName(p.grade), p.uncertain ? `min ${p.score_min.toFixed(2)} – max ${p.score_max.toFixed(2)} (blank gender)` : '']),
    ...Object.entries(criteria).map(([c, label]) => {
      const x = p.criteria[c];
      return card(label, x.grade, x.d, [x.detail, x.sides ? `international: grade ${x.side_grades.student} · local: grade ${x.side_grades.local}` : '']);
    }));
  const shared = p.criteria.hobbies.shared || [];
  const notes = p.notes.filter(n => !n.startsWith('staff check'));  // already listed with the must-have results
  return el('div', {}, strip,
    el('div', {class: 'detail-grid'}, personCard(people[p.student], people[p.local], 'international', shared), personCard(people[p.local], people[p.student], 'local', shared)),
    p.rules.length ? el('ul', {class: 'rule-results'}, p.rules.map(x => el('li', {},
      el('span', {class: `icon ${x.result === 'met' ? 'ok' : 'warn'}`, text: x.result === 'met' ? '✓ ' : x.result === 'staff' ? '⚑ ' : '? '}),
      x.result === 'staff' ? `${x.owner}: check by hand - ${x.wish}` : `${x.owner}: ${x.label} - ${x.result}`))) : null,
    notes.length ? el('ul', {class: 'rule-results'}, notes.map(n => el('li', {text: `• ${n}`}))) : null);
}

function renderLeft() { renderData(); renderWeights(); renderAnchors(); renderRules(); renderPins(); refreshChrome(); }

// ---------- wiring ----------
async function init() {
  try {
    state.defaults = await api('/api/defaults');
    state.settings = clone(state.defaults.settings);
    renderWeights(); renderAnchors(); refreshChrome();
  } catch (error) { setStatus(error.message, 'error'); }
  if (location.protocol === 'file:') {
    state.stopped = true; refreshChrome();
    setStatus('Start the app (start.bat or python app.py); it opens this page at a localhost address.', 'error');
  }
}
$('survey-file').addEventListener('change', async event => {
  const file = event.target.files[0]; event.target.value = '';
  if (!file) return;
  try { await loadSurvey(file.name, await readText(file)); } catch (error) { setStatus(error.message, 'error'); }
});
$('example').addEventListener('click', async () => {
  try { const {name, survey} = await api('/api/example'); await loadSurvey(name, survey); } catch (error) { setStatus(error.message, 'error'); }
});
$('settings-file').addEventListener('change', async event => {
  const file = event.target.files[0]; event.target.value = '';
  if (!file) return;
  try {
    const before = state.settings.max_missing_answers;
    state.settings = (await api('/api/import-settings', {csv: await readText(file)})).settings;
    renderWeights(); renderAnchors(); markDirty();
    if (state.settings.max_missing_answers !== before) await reanalyse();
    setStatus(`Settings loaded from ${file.name}.`);
  } catch (error) { setStatus(error.message, 'error'); }
});
$('rules-file').addEventListener('change', async event => {
  const file = event.target.files[0]; event.target.value = '';
  if (!file) return;
  if (!state.survey) { setStatus('Load the survey before loading must-have rules.', 'error'); return; }
  try {
    const data = await api('/api/import-rules', {csv: await readText(file), survey: state.survey.text, settings: state.settings});
    state.rules = data.rules.map(withUid); state.editing.clear(); setImpact(state.rules, data.impact);
    renderRules(); markDirty(); setStatus(`${state.rules.length} must-haves loaded from ${file.name}.`);
  } catch (error) { setStatus(error.message, 'error'); }
});
async function exportFiles() { return api('/api/export', {settings: state.settings, rules: state.rules.filter(complete).map(plainRule)}); }
$('save-settings').addEventListener('click', async () => {
  try { download('settings.csv', '﻿' + (await exportFiles()).settings_csv, 'text/csv;charset=utf-8'); } catch (error) { setStatus(error.message, 'error'); }
});
$('save-rules').addEventListener('click', async () => {
  if (!state.data) { setStatus('Load the survey first.', 'error'); return; }
  try { download('must_haves.csv', '﻿' + (await exportFiles()).rules_csv, 'text/csv;charset=utf-8'); } catch (error) { setStatus(error.message, 'error'); }
});
$('reset-settings').addEventListener('click', async () => {
  const before = state.settings.max_missing_answers;
  state.settings = clone(state.defaults.settings); renderWeights(); renderAnchors(); markDirty();
  if (state.settings.max_missing_answers !== before) await reanalyse();
});
$('compute').addEventListener('click', compute);
$('download-result').addEventListener('click', () => { const it = state.iterations[state.view]; if (it) download('result.csv', '﻿' + it.result.result_csv, 'text/csv;charset=utf-8'); });
$('download-report').addEventListener('click', () => { const it = state.iterations[state.view]; if (it) download('report.txt', it.result.report, 'text/plain;charset=utf-8'); });
$('stop').addEventListener('click', async () => {
  if (state.iterations.length && !confirm('Have you saved result.csv, report.txt and your settings? Close the app now?')) return;
  try { await api('/api/stop', {}); state.stopped = true; refreshChrome(); setStatus('The app is closed. You can close this tab.'); }
  catch (error) { setStatus(error.message, 'error'); }
});
init();
