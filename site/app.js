/* PIB Exam Daily: reads data/index.json and data/YYYY-MM-DD.json written by scripts/fetch_pib.py */
(() => {
  'use strict';

  // ---------------------------------------------------------------- helpers
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: keep going in memory */ } },
  };

  const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: 'Asia/Kolkata' });
  const ymd = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)); };
  const fmtLong = (s) => new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }).format(ymd(s));
  const fmtShort = (s) => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(ymd(s));
  const fmtWeekday = (s) => new Intl.DateTimeFormat('en-IN', { weekday: 'short', timeZone: 'UTC' }).format(ymd(s));
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  const DEFAULT_TH = { must: 7, good: 5, skim: 3 };
  const TIERS = [
    { k: 'must', h: 'Read first' },
    { k: 'good', h: 'Read next' },
    { k: 'skim', h: 'Skim if you have time' },
    { k: 'skip', h: 'Probably skip' },
  ];

  // Lens bonuses re-rank items for the exam the person is preparing for.
  const LENS = {
    upsc: { 'International Relations': 1, 'Environment & Ecology': 1, 'Polity & Governance': 1, 'Science & Tech': 0.5, 'Schemes & Welfare': 0.5 },
    appsc: { Economy: 1, 'Science & Tech': 1, 'Polity & Governance': 1, 'History, Art & Culture': 0.5, 'Geography & Disasters': 0.5, __ap: 1.5 },
  };

  // ------------------------------------------------------------------ state
  let read = new Set(store.get('pib.read', []));
  let saved = store.get('pib.saved', {});
  const prefs = Object.assign({ lens: 'all', apOnly: false, ministry: '', showSkip: false }, store.get('pib.prefs', {}));
  const state = {
    index: null, range: 'day', date: null, q: '', subjects: new Set(),
    cache: new Map(), open: new Set(), notes: new Set(), mcq: new Map(),
  };
  const main = $('#main');

  const persist = () => {
    store.set('pib.read', [...read].slice(-4000));
    store.set('pib.saved', saved);
    store.set('pib.prefs', prefs);
  };

  // ------------------------------------------------------------------- data
  async function loadDay(date) {
    if (state.cache.has(date)) return state.cache.get(date);
    const r = await fetch(`data/${date}.json?v=${encodeURIComponent(state.index.generated_at)}`);
    if (!r.ok) throw new Error(`Could not load ${date} (HTTP ${r.status})`);
    const doc = await r.json();
    state.cache.set(date, doc);
    return doc;
  }

  function daysForRange() {
    const all = state.index.days.map((d) => d.date);
    if (state.q.trim().length >= 2) return all.slice(0, 30);
    if (state.range === 'week') return all.slice(0, 7);
    if (state.range === 'month') return all.slice(0, 30);
    return [state.date];
  }

  const lensScore = (it) => {
    if (prefs.lens === 'all') return it.score;
    const b = LENS[prefs.lens];
    let s = it.score;
    for (const sub of it.subjects || []) s += b[sub] || 0;
    if (it.ap && b.__ap) s += b.__ap;
    return s;
  };
  const tierOf = (score, th) => (score >= th.must ? 'must' : score >= th.good ? 'good' : score >= th.skim ? 'skim' : 'skip');

  function matches(it) {
    if (prefs.apOnly && !it.ap) return false;
    if (prefs.ministry && it.ministry !== prefs.ministry) return false;
    if (state.subjects.size && !(it.subjects || []).some((s) => state.subjects.has(s))) return false;
    const q = state.q.trim().toLowerCase();
    if (q.length >= 2) {
      const hay = `${it.title} ${it.ministry} ${(it.hooks || []).join(' ')} ${it.excerpt}`.toLowerCase();
      if (!q.split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  // ----------------------------------------------------------------- render
  function itemHtml(it, multiDay) {
    const key = it.prid;
    const isRead = read.has(key);
    const isSaved = !!saved[key];
    const open = state.open.has(key);
    const showNotes = state.notes.has(key);
    const time = timeFmt.format(new Date(it.posted_at));
    const tags = [];
    if (it.type) tags.push(`<span class="tag type">${esc(it.type)}</span>`);
    if (it.ap) tags.push(`<span class="tag ap">Andhra Pradesh</span>`);
    for (const s of (it.subjects || []).slice(0, 2)) tags.push(`<span class="tag">${esc(s)}</span>`);

    const hooks = (it.hooks || []).length
      ? `<p class="hooks"><span class="sr">Names and acronyms to remember: </span>${it.hooks.map((h) => `<span class="hook">${esc(h)}</span>`).join('')}</p>` : '';
    const figs = (it.figures || []).length ? `<p class="figs"><span class="sr">Numbers: </span>${esc(it.figures.join(', '))}</p>` : '';
    const why = open
      ? `<p class="figs">Flagged because: ${esc((it.reasons || []).join(', ') || 'ministry weight only')}. Score ${esc(it.score)}.</p>` : '';

    return `
    <li class="item${isRead ? ' read' : ''}${open ? ' open' : ''}" data-prid="${esc(key)}">
      <button class="omr" type="button" data-act="read" data-prid="${esc(key)}" aria-pressed="${isRead}" aria-label="Mark as read: ${esc(it.title)}"></button>
      <div>
        <div class="meta"><span class="min">${esc(it.ministry)}</span><span>${multiDay ? esc(fmtShort(it.date)) + ', ' : ''}${esc(time)}</span></div>
        <h4 class="title" style="margin-block:3px 6px"><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></h4>
        <div class="tags">${tags.join('')}</div>
        <p class="excerpt">${esc(it.excerpt)}</p>
        ${hooks}${figs}${why}
        <div class="actions">
          <button class="link-btn" type="button" data-act="more" data-prid="${esc(key)}" aria-expanded="${open}">${open ? 'Show less' : 'Show more'}</button>
          ${it.ai ? `<button class="link-btn" type="button" data-act="notes" data-prid="${esc(key)}" aria-expanded="${showNotes}">AI notes</button>` : ''}
          <button class="link-btn" type="button" data-act="save" data-prid="${esc(key)}" aria-pressed="${isSaved}">${isSaved ? 'Saved' : 'Save'}</button>
          <button class="link-btn" type="button" data-act="copy" data-prid="${esc(key)}">Copy note</button>
          <a href="${esc(it.url)}" target="_blank" rel="noopener">Open on PIB</a>
        </div>
        ${showNotes && it.ai ? notesHtml(it) : ''}
      </div>
    </li>`;
  }

  function notesHtml(it) {
    const a = it.ai;
    const chosen = state.mcq.get(it.prid);
    const facts = (a.prelims_facts || []).length ? `<h4>Prelims facts</h4><ul>${a.prelims_facts.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>` : '';
    const angle = a.mains_angle ? `<h4>Mains angle${(a.gs_papers || []).length ? ` (${esc(a.gs_papers.join(', '))})` : ''}</h4><p>${esc(a.mains_angle)}</p>` : '';
    const te = a.telugu ? `<h4>తెలుగులో సారాంశం</h4><p class="te" lang="te">${esc(a.telugu)}</p>` : '';
    let mcq = '';
    if (a.mcq) {
      const opts = a.mcq.options.map((o, i) => {
        let cls = 'opt';
        if (chosen !== undefined) cls += i === a.mcq.answer ? ' right' : i === chosen ? ' wrong' : '';
        return `<button type="button" class="${cls}" data-act="opt" data-prid="${esc(it.prid)}" data-i="${i}" ${chosen !== undefined ? 'disabled' : ''}>${esc(o)}</button>`;
      }).join('');
      mcq = `<h4>Test yourself</h4><div class="mcq"><p class="q">${esc(a.mcq.q)}</p>${opts}${chosen !== undefined ? `<p class="why">${chosen === a.mcq.answer ? 'Correct. ' : 'Not quite. '}${esc(a.mcq.explanation)}</p>` : ''}</div>`;
    }
    return `<div class="notes">${facts}${angle}${mcq}${te}<p class="caveat">Written by an AI model from the release text. Check it against the PIB page before you rely on it.</p></div>`;
  }

  function groupHtml(tier, items, multiDay) {
    const readN = items.filter((i) => read.has(i.prid)).length;
    const list = `<ol class="items">${items.map((i) => itemHtml(i, multiDay)).join('')}</ol>`;
    const collapsed = tier.k === 'skip' || (multiDay && tier.k === 'skim');
    if (collapsed) {
      const open = tier.k === 'skip' ? prefs.showSkip : false;
      return `<section class="group" data-tier="${tier.k}"><details class="skipwrap" ${open ? 'open' : ''}><summary>${esc(tier.h)} (${items.length})</summary>${list}</details></section>`;
    }
    const bubbles = items.slice(0, 16).map((i) => `<i class="bubble${read.has(i.prid) ? ' on' : ''}"></i>`).join('');
    return `<section class="group" data-tier="${tier.k}">
      <header><h3>${esc(tier.h)}</h3><span class="tally">${readN} of ${items.length} read</span><span class="bubbles" aria-hidden="true">${bubbles}</span></header>
      ${list}</section>`;
  }

  async function render(focus) {
    if (!state.index) return;
    if (state.range === 'saved') return renderSaved(focus);

    const dates = daysForRange();
    let docs;
    try {
      docs = await Promise.all(dates.map(loadDay));
    } catch (e) {
      main.innerHTML = `<p class="banner err">${esc(e.message)}. Reload the page; if it keeps failing the data files may be mid-update.</p>`;
      return;
    }
    const multiDay = dates.length > 1;
    const all = docs.flatMap((doc) => (doc.items || []).map((it) => ({ ...it, date: doc.date, th: doc.thresholds || DEFAULT_TH })));
    syncFilterOptions(all);

    const shown = all.filter(matches).map((it) => ({ ...it, ls: lensScore(it) }));
    shown.forEach((it) => { it.tier = tierOf(it.ls, it.th); });
    shown.sort((a, b) => b.ls - a.ls || (a.posted_at < b.posted_at ? 1 : -1));

    const searching = state.q.trim().length >= 2;
    const title = searching ? 'Search results' : state.range === 'day' ? fmtLong(state.date) : state.range === 'week' ? 'The last 7 days' : 'The last 30 days';
    const must = shown.filter((i) => i.tier === 'must');
    const apN = shown.filter((i) => i.ap).length;
    const updated = state.range === 'day' && docs[0]?.updated_at ? ` Updated ${timeFmt.format(new Date(docs[0].updated_at))}.` : '';
    const summary = `${plural(shown.length, 'release', 'releases')}, ${must.length} to read first${apN ? `, ${apN} linked to Andhra Pradesh` : ''}.${updated}`;

    const demo = docs.some((d) => d.sample)
      ? `<p class="banner">You are looking at demo data. Real releases replace it after the first scheduled run (see the README).</p>` : '';

    let body;
    if (!shown.length) {
      body = `<div class="empty"><p><b>Nothing matches these filters.</b></p><p>Clear the search box, switch off "Only Andhra Pradesh items", or choose a longer range.</p></div>`;
    } else {
      body = TIERS.map((t) => {
        const items = shown.filter((i) => i.tier === t.k);
        return items.length ? groupHtml(t, items, multiDay) : '';
      }).join('');
    }

    main.innerHTML = `${demo}<div class="head"><h2>${esc(title)}</h2><p>${esc(summary)}</p></div>${body}
      <p class="foot">Releases come from the Press Information Bureau, Government of India. Titles link to the original page. The sorting is a rule-based guess at exam relevance (see <a href="guide.html#scoring">how items are scored</a>), so open the skip list now and then.</p>`;
    restoreFocus(focus);
  }

  // ------------------------------------------------------------ saved view
  function renderSaved(focus) {
    const items = Object.values(saved).sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
    const list = items.map((it) => `
      <li class="item${read.has(it.prid) ? ' read' : ''}" data-prid="${esc(it.prid)}">
        <button class="omr" type="button" data-act="read" data-prid="${esc(it.prid)}" aria-pressed="${read.has(it.prid)}" aria-label="Mark as read: ${esc(it.title)}"></button>
        <div>
          <div class="meta"><span class="min">${esc(it.ministry)}</span><span>${esc(fmtShort(it.date))}</span></div>
          <h4 class="title" style="margin-block:3px 6px"><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></h4>
          ${(it.hooks || []).length ? `<p class="hooks">${it.hooks.map((h) => `<span class="hook">${esc(h)}</span>`).join('')}</p>` : ''}
          <label class="sr" for="n-${esc(it.prid)}">Your note</label>
          <textarea id="n-${esc(it.prid)}" data-act="note" data-prid="${esc(it.prid)}" rows="2" placeholder="Why was this in the news? One line you will recognise in the exam." style="width:100%;max-width:68ch;padding:8px;border:1px solid var(--rule);border-radius:8px;background:var(--surface);color:var(--ink);font:inherit">${esc(it.note || '')}</textarea>
          <div class="actions"><button class="link-btn" type="button" data-act="unsave" data-prid="${esc(it.prid)}">Remove</button></div>
        </div>
      </li>`).join('');
    main.innerHTML = `<div class="head"><h2>Saved for revision</h2><p>${plural(items.length, 'release', 'releases')} saved in this browser.</p></div>
      ${items.length ? `<div class="actions" style="margin-top:14px"><button class="link-btn" type="button" data-act="export">Download as Markdown</button><button class="link-btn" type="button" data-act="print">Print</button></div><section class="group"><ol class="items">${list}</ol></section>`
        : `<div class="empty"><p><b>Nothing saved yet.</b></p><p>Choose Save under any release and it appears here with a note box. Saved items stay in this browser only.</p></div>`}`;
    restoreFocus(focus);
  }

  function restoreFocus(f) {
    if (!f) return;
    const el = $(`[data-act="${f.act}"][data-prid="${CSS.escape(f.prid)}"]${f.i !== undefined ? `[data-i="${f.i}"]` : ''}`, main);
    if (el) el.focus({ preventScroll: true });
  }

  // ------------------------------------------------------------------ rail
  function renderDays() {
    const box = $('#days');
    box.innerHTML = state.index.days.slice(0, 14).map((d) => {
      const dots = Array.from({ length: Math.min(d.must, 5) }, () => '<i class="on"></i>').join('') || '<i></i>';
      return `<button type="button" class="day" data-date="${d.date}" aria-pressed="${state.range === 'day' && d.date === state.date}" aria-label="${esc(fmtLong(d.date))}, ${d.must} to read first">
        <b>${esc(fmtShort(d.date))}</b><span>${esc(fmtWeekday(d.date))}</span><span class="dots" aria-hidden="true">${dots}</span></button>`;
    }).join('');
  }

  function syncFilterOptions(all) {
    const mins = [...new Set(all.map((i) => i.ministry))].sort();
    const sel = $('#ministry');
    if (sel.dataset.sig !== mins.join('|')) {
      sel.innerHTML = `<option value="">All ministries</option>` + mins.map((m) => `<option ${m === prefs.ministry ? 'selected' : ''}>${esc(m)}</option>`).join('');
      sel.dataset.sig = mins.join('|');
    }
    const counts = {};
    all.forEach((i) => (i.subjects || []).forEach((s) => { counts[s] = (counts[s] || 0) + 1; }));
    const subs = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    const chips = $('#subjectChips');
    if (chips.dataset.sig !== subs.join('|')) {
      chips.innerHTML = subs.map((s) => `<button type="button" class="chip" data-subject="${esc(s)}" aria-pressed="${state.subjects.has(s)}">${esc(s)}</button>`).join('');
      chips.dataset.sig = subs.join('|');
    }
  }

  function syncControls() {
    $$('#rangeSeg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.range === state.range)));
    $$('#lensSeg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.lens === prefs.lens)));
    $('#apOnly').checked = prefs.apOnly;
    $('#showSkip').checked = prefs.showSkip;
    $('#savedCount').textContent = Object.keys(saved).length ? `(${Object.keys(saved).length})` : '';
    renderDays();
  }

  function setHash() {
    const h = state.range === 'day' ? state.date : state.range;
    history.replaceState(null, '', `#${h}`);
  }

  // ---------------------------------------------------------------- actions
  function findItem(prid) {
    for (const doc of state.cache.values()) {
      const it = (doc.items || []).find((i) => i.prid === prid);
      if (it) return { ...it, date: doc.date };
    }
    return saved[prid] || null;
  }
  const noteText = (it) => [
    it.title,
    `Ministry: ${it.ministry} | Date: ${it.date}`,
    `Remember: ${[...(it.hooks || []), ...(it.figures || [])].join(', ') || '-'}`,
    `Why in news: `,
    `Static link: `,
    it.url,
  ].join('\n');

  function exportMarkdown() {
    const items = Object.values(saved).sort((a, b) => (a.date < b.date ? 1 : -1));
    const md = `# PIB revision list\n\n` + items.map((it) => `## ${it.title}\n- Ministry: ${it.ministry}\n- Date: ${it.date}\n- Remember: ${[...(it.hooks || []), ...(it.figures || [])].join(', ') || '-'}\n- Note: ${it.note || ''}\n- Source: ${it.url}\n`).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }));
    a.download = 'pib-revision-list.md';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  main.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.dataset.act, prid = btn.dataset.prid;
    const focus = prid ? { act, prid, i: btn.dataset.i } : null;
    switch (act) {
      case 'read': read.has(prid) ? read.delete(prid) : read.add(prid); persist(); return render(focus);
      case 'more': state.open.has(prid) ? state.open.delete(prid) : state.open.add(prid); return render(focus);
      case 'notes': state.notes.has(prid) ? state.notes.delete(prid) : state.notes.add(prid); return render(focus);
      case 'opt': state.mcq.set(prid, Number(btn.dataset.i)); return render(focus);
      case 'save': {
        const it = findItem(prid);
        if (!it) return;
        if (saved[prid]) delete saved[prid];
        else saved[prid] = { prid, url: it.url, title: it.title, ministry: it.ministry, date: it.date, hooks: it.hooks || [], figures: it.figures || [], subjects: it.subjects || [], note: '' };
        persist(); syncControls(); return render(focus);
      }
      case 'unsave': delete saved[prid]; persist(); syncControls(); return render();
      case 'copy': {
        const it = findItem(prid);
        if (!it) return;
        try { await navigator.clipboard.writeText(noteText(it)); btn.textContent = 'Copied'; }
        catch { window.prompt('Copy this note:', noteText(it)); }
        setTimeout(() => { btn.textContent = 'Copy note'; }, 1500);
        return;
      }
      case 'export': return exportMarkdown();
      case 'print': return window.print();
      default:
    }
  });
  main.addEventListener('input', (e) => {
    const t = e.target;
    if (t.dataset.act === 'note' && saved[t.dataset.prid]) { saved[t.dataset.prid].note = t.value; persist(); }
  });

  $('#days').addEventListener('click', (e) => {
    const b = e.target.closest('.day');
    if (!b) return;
    state.range = 'day'; state.date = b.dataset.date; state.q = ''; $('#q').value = '';
    syncControls(); setHash(); render();
  });
  $('#rangeSeg').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    state.range = b.dataset.range;
    if (state.range === 'day' && !state.date) state.date = state.index.days[0].date;
    syncControls(); setHash(); render();
  });
  $('#lensSeg').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    prefs.lens = b.dataset.lens; persist(); syncControls(); render();
  });
  $('#apOnly').addEventListener('change', (e) => { prefs.apOnly = e.target.checked; persist(); render(); });
  $('#showSkip').addEventListener('change', (e) => { prefs.showSkip = e.target.checked; persist(); render(); });
  $('#ministry').addEventListener('change', (e) => { prefs.ministry = e.target.value; persist(); render(); });
  $('#subjectChips').addEventListener('click', (e) => {
    const b = e.target.closest('.chip');
    if (!b) return;
    const s = b.dataset.subject;
    state.subjects.has(s) ? state.subjects.delete(s) : state.subjects.add(s);
    b.setAttribute('aria-pressed', String(state.subjects.has(s)));
    render();
  });
  let timer;
  $('#q').addEventListener('input', (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = e.target.value; if (state.range === 'saved') state.range = 'day'; syncControls(); render(); }, 250);
  });

  // -------------------------------------------------------------------- boot
  async function boot() {
    try {
      const r = await fetch('data/index.json', { cache: 'no-cache' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      state.index = await r.json();
    } catch (e) {
      main.innerHTML = `<div class="empty"><p class="banner err"><b>No release data found.</b></p><p>The site reads <code>data/index.json</code>, which the daily workflow creates. Run the workflow once from the Actions tab, or run <code>python scripts/fetch_pib.py</code> locally (details in the README).</p></div>`;
      return;
    }
    if (!state.index.days.length) {
      main.innerHTML = `<div class="empty"><p><b>The data folder is empty.</b></p><p>Run the workflow once and releases will appear here.</p></div>`;
      return;
    }
    const h = location.hash.slice(1);
    if (['week', 'month', 'saved'].includes(h)) state.range = h;
    state.date = state.index.days.some((d) => d.date === h) ? h : state.index.days[0].date;
    syncControls();
    await render();
  }
  boot();
})();
