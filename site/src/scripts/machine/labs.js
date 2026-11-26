// Hands-on labs, rendered into the right-hand panel.
// The guard lab is a simplified re-implementation of a few pre-bash.py and git-enforce.py rules,
// using the same patterns and messages as the source where possible. It is a teaching aid, not the guard.
import { FAULTS, LABS } from './content.js';
import { MSG } from './messages.js';

/* ------------------------------------------------------------ guard simulation */
const FORCE_RE = /(?:^|\s)(?:--force(?:-with-lease|-if-includes)?(?:=\S+)?|-f)(?=\s|$)/;
const FORCE_REFSPEC_RE = /\s\+[\w./:~^-]+/;
const PUSH_ALL_RE = /(?:^|\s)(?:--all|--mirror)(?=\s|$)/;
const WILDCARD_ADD_RE = /(?:^|\s)(?:-A|--all|-u|--update|\.)(?=\s|$)/;
const PROTECTED_DEST_RE = /^(?:\S+:|:)?(?:refs\/heads\/)?(?:main|master)$/;
const GLOB_RE = /[*?[]/;
const AUDIT_RE = /(?:^|[\s/'"])(overrides\.log|triage\.log|sprint-log\.md|gate-events\.log|decision-log\.md)\b/;
const ADR_RE = /\.codearbiter\/decisions\/(?!decision-log\.md)[\w.-]+/;
const CONTEXT_RE = /\.codearbiter\/CONTEXT\.md/;
const DIRS = new Set(['src', 'lib', 'app', 'test', 'tests', 'docs', 'packages', 'scripts', 'config']);
export { MSG } from './messages.js';
const tokens = (s) => (s.match(/"[^"]*"|'[^']*'|\S+/g) || []);
const writesTo = (seg, re) => {
  if (!re.test(seg)) return false;
  if (/(^|[^>])>(?!>)\s*\S*/.test(seg) && re.test(seg.split(/>(?!>)/).slice(1).join('>'))) return true;
  if (/>>/.test(seg) && re === AUDIT_RE) return false;
  if (/>>/.test(seg)) return true;
  return /^(?:sudo\s+)?(?:rm|mv|cp|truncate|dd|shred|unlink|tee(?!\s+-a))\b|\bsed\s+(?:-\w*\s+)*-i|\bperl\s+-\w*i|\bpython3?\s+-c\b.*\bopen\(.*['"]w/.test(seg);
};

export function simulateGuard(raw, ctx) {
  const branch = ctx.branch;
  const out = { bash: null, git: null, notes: [] };
  const segs = raw.split(/&&|\|\||;|\|/).map((s) => s.trim().replace(/^(?:\w+=\S+\s+)+/, '')).filter(Boolean);
  const block = (tag, key, ...a) => { if (!out.bash) out.bash = { tag, msg: MSG[key](...a) }; };
  const gblock = (tag, key, ...a) => { if (!out.git) out.git = { tag, msg: MSG[key](...a) }; };
  let indirect = false;
  for (const seg of segs) {
    let m;
    if ((m = seg.match(/^git\s+(?:-C\s+\S+\s+)?push\b(.*)$/))) {
      const args = ' ' + m[1];
      const toks = tokens(m[1]).filter((t) => !t.startsWith('-')).map((t) => t.replace(/^["']|["']$/g, '').replace(/^\+/, ''));
      if (toks.includes('--no-verify') || /(?:^|\s)--no-verify(?=\s|$)/.test(args)) block('H-20', 'H-20p');
      if (FORCE_RE.test(args) || FORCE_REFSPEC_RE.test(args)) block('H-02', 'H-02');
      if (PUSH_ALL_RE.test(args)) block('H-01', 'H-01a');
      const dest = toks.find((t) => PROTECTED_DEST_RE.test(t));
      if (dest) block('H-01', 'H-01p', dest);
      if (toks.length < 2 && branch === 'main') block('H-01', 'H-01b');
    } else if ((m = seg.match(/^git\s+(?:-C\s+\S+\s+)?commit\b(.*)$/))) {
      const ts = tokens(m[1]);
      const nv = ts.some((t) => t === '--no-verify' || t === '-n') || ts.some((t) => {
        if (!/^-[a-zA-Z]/.test(t) || t.startsWith('--')) return false;
        for (const ch of t.slice(1)) { if (ch === 'n') return true; if ('mFCct'.includes(ch) || !/[a-zA-Z]/.test(ch)) return false; }
        return false;
      });
      if (nv) block('H-20', 'H-20c');
      if (branch === 'main') block('H-01', 'H-01c', 'main');
      if (ctx.secret) block('H-10b', 'H-10b');
    } else if ((m = seg.match(/^git\s+(?:-C\s+\S+\s+)?add\b(.*)$/))) {
      const args = ' ' + m[1];
      if (WILDCARD_ADD_RE.test(args)) block('H-03', 'H-03a');
      else for (const t0 of tokens(m[1])) {
        const t = t0.replace(/^["']|["']$/g, '');
        if (!t || t === '--' || t.startsWith('-')) continue;
        if (t.startsWith(':')) { block('H-03', 'H-03b', `pathspec magic ('${t}')`); break; }
        if (GLOB_RE.test(t)) { block('H-03', 'H-03b', `a glob pattern ('${t}')`); break; }
        if (t.endsWith('/') || DIRS.has(t)) { block('H-03', 'H-03b', `a directory ('${t}')`); break; }
      }
    } else if (/\bpush\b/.test(seg) && /\$\w|`|\beval\b/.test(seg)) {
      indirect = true;
      const args = ' ' + seg;
      if (FORCE_RE.test(args) || FORCE_REFSPEC_RE.test(args)) gblock('H-02', 'G-02');
      else if (/\s(?:\S+:)?(?:main|master)(?=\s|$)/.test(args) || branch === 'main') gblock('H-01', 'G-01p', 'main');
    } else if (/\bcommit\b/.test(seg) && /\$\w|`|\beval\b/.test(seg)) {
      indirect = true;
      if (branch === 'main') gblock('H-01', 'G-01c', 'main');
    }
    if (AUDIT_RE.test(seg) && writesTo(seg, AUDIT_RE)) block('H-05', 'H-05');
    if (ADR_RE.test(seg) && writesTo(seg, ADR_RE)) block('H-11', 'H-11');
    if (CONTEXT_RE.test(seg) && writesTo(seg, CONTEXT_RE)) block('H-18', 'H-18');
  }
  if (out.bash) out.git = null;
  if (indirect && !out.bash) out.notes.push('The shell gate reads the literal command text. A command assembled from variables can look different from what actually runs, which is exactly what the git-level backstop is for. (In this simulation the shell gate lets it through; the real guard may still catch some indirect spellings.)');
  return out;
}

/* ------------------------------------------------------------ illustrative tokenizer */
const COMMON = new Set(('the a an and or to of in on for with is are was be it this that at by from as not no yes if then else '
  + 'fix test tests fail failing failed pass login user users file files code change changes update add remove run build error '
  + 'new old return const let var function class import export true false null undefined async await type string number '
  + 'src app api data value values item items total reduce map filter get set main branch commit push merge review model '
  + 'token tokens agent tool tools text word words read write edit we you i my your our they he she can will should would '
  + 'have has had do does did make made one two three all any each some more most other into out up down over after before '
  + 'when where what which who how why because so but just only also very about time first last next back still now here there').split(' '));
const PIECES = ['tion', 'ing', 'ment', 'ness', 'able', 'ible', 'ful', 'less', 'ous', 'ive', 'ize', 'ise', 'est', 'er', 'ed', 'ly', 'al', 'es', 's',
  'pre', 'pro', 'con', 'com', 'dis', 'un', 're', 'in', 'ex', 'de', 'en', 'auth', 'ent', 'icat', 'sess', 'ion', 'oken', 'user', 'head', 'req', 'uest', 'ers', 'ure', 'ant', 'ence', 'ance', 'th', 'ch', 'sh', 'st', 'tr', 'pl', 'gr'];
function splitWord(w) {
  const lead = w.startsWith(' ') ? ' ' : '';
  const core = w.trim();
  if (COMMON.has(core.toLowerCase()) && core.length <= 9) return [w];
  const parts = core.split(/(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])/);
  const out = [];
  parts.forEach((p, idx) => {
    let rest = p;
    let first = idx === 0 ? lead : '';
    while (rest.length) {
      if (COMMON.has(rest.toLowerCase()) && rest.length <= 9) { out.push(first + rest); break; }
      let take = 0;
      for (const piece of PIECES) if (rest.toLowerCase().startsWith(piece) && piece.length > take && rest.length - piece.length !== 1) take = piece.length;
      if (!take) take = Math.min(rest.length, rest.length <= 5 ? rest.length : 4);
      out.push(first + rest.slice(0, take)); rest = rest.slice(take); first = '';
    }
  });
  return out;
}
export function tokenize(text) {
  const pre = text.match(/ ?[A-Za-z]+| ?\d{1,3}|=>|==|!=|&&|\|\||\(\)|\s+|[^\sA-Za-z\d]/g) || [];
  const out = [];
  for (const p of pre) { if (/^ ?[A-Za-z]+$/.test(p)) out.push(...splitWord(p)); else if (/^ ?[^\x00-\x7F]/.test(p)) out.push(...Array.from(p)); else out.push(p); }
  return out;
}
export const tokId = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) % 100000; };

/* ------------------------------------------------------------ sampler */
const CANDS = [[' pass', 2.3], [' fail', 1.2], [' are', 0.7], [' should', 0.35], [' still', 0.2], [' run', 0.0], [' need', -0.3], [' look', -0.5], [' might', -0.9], [' explode', -3.0]];
function probs(T, topP) {
  if (T < 0.01) return CANDS.map((_, i) => (i === 0 ? 1 : 0));
  const ex = CANDS.map(([, l]) => Math.exp(l / T));
  const z = ex.reduce((a, b) => a + b, 0);
  const p = ex.map((e) => e / z);
  const order = p.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]);
  let cum = 0; const keep = new Set();
  for (const [v, i] of order) { keep.add(i); cum += v; if (cum >= topP - 1e-9) break; }
  const kept = p.map((v, i) => (keep.has(i) ? v : 0));
  const kz = kept.reduce((a, b) => a + b, 0);
  return kept.map((v) => v / kz);
}

/* ------------------------------------------------------------ context window model (illustrative proportions) */
function simulateContext(turns, on) {
  let conv = 0, results = 0, summary = 0, compactions = 0;
  const fixed = 14, rules = on ? 4 : 0, wf = on ? 5 : 0;
  for (let t = 1; t <= turns; t++) {
    conv += 0.34; results += 0.52;
    if (fixed + rules + wf + summary + conv + results > 92) { summary = Math.min(22, 9 + compactions * 3); conv = 0; results = 0; compactions++; }
  }
  return { fixed, rules, wf, summary, conv, results, compactions, used: fixed + rules + wf + summary + conv + results };
}

/* ------------------------------------------------------------ the panel */
const X_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';
const PLAY_SVG = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';

export function createLabs(ctx) {
  const { el, esc, fmt } = ctx;
  const st = {
    lab: null,
    branch: 'feature', secret: false, cmd: 'git push --force origin feature/login', runs: 0, lastGuard: '',
    T: 1, topP: 1, counts: CANDS.map(() => 0), last: null, samples: 0,
    text: 'Fix the failing login test in src/auth/session.ts', tokTries: 0,
    turns: 40, on: true, lastCompactions: 0,
  };
  const $ = (s) => el.querySelector(s);
  const tabs = () => `<div class="lab-tabs" role="tablist" aria-label="Labs">${Object.entries(LABS).map(([k, v]) => { const d = ctx.isDone('lab:' + k); return `<button role="tab" data-lab="${k}" aria-selected="${st.lab === k}"${d ? ' class="done"' : ''}>${esc(v.tab)}${d ? '<span class="sr"> (done)</span>' : ''}</button>`; }).join('')}</div>`;
  const close = `<button class="tb icon close" data-act="close" aria-label="Close">${X_SVG}</button>`;

  function render() {
    const L = LABS[st.lab];
    const body = { faults: faultsBody, guard: guardBody, sampler: samplerBody, tokens: tokensBody, context: contextBody }[st.lab]();
    el.innerHTML = `<div class="ins-head lab-head">${tabs()}${close}<h2>${esc(L.title)}</h2><p class="tag">${fmt(L.blurb)}</p></div><div class="ins-body lab-body">${body}</div>`;
    if (st.lab === 'guard') $('#g-cmd').value = st.cmd;
    if (st.lab === 'tokens') { $('#t-in').value = st.text; updateTokens(); }
    if (st.lab === 'sampler') updateSampler();
    if (st.lab === 'context') updateContext();
    ctx.glossify(el.querySelector('.lab-body'));
  }

  /* ---- break it */
  function faultsBody() {
    return `<p class="lede">Each scenario is a plausible move for a model that is only predicting likely next steps. Press Play to watch the call travel through the machine and see which part stops it.</p>`
      + FAULTS.map((f) => {
        const done = ctx.isDone('fault:' + f.id);
        return `<div class="fault${done ? ' done' : ''}"><div class="f-top"><h3>${esc(f.title)}</h3>${done ? '<i class="tick" aria-label="(watched)"></i>' : ''}</div><p>${fmt(f.why)}</p><div class="f-row"><span class="pill">Caught by ${ctx.pnameHTML(f.catcher)}</span><span class="pill${/^H-\d/.test(f.tag) ? ' mono' : ''}">${esc(f.tag)}</span><span class="sp"></span><button class="btn ${done ? 'ghost' : 'primary'} sm" data-fault="${esc(f.id)}" aria-label="Play: ${esc(f.title)}">${PLAY_SVG}Play</button></div></div>`;
      }).join('');
  }

  /* ---- guard */
  const EXAMPLES = ['git push --force origin feature/login', 'git push origin main', 'git push origin feature/login', 'git add -A', 'git add src/', 'git add src/auth/session.ts', 'git commit -m "fix: handle empty input"', 'git commit --no-verify -m "fix"', 'git commit -nm "quick fix"', '> .codearbiter/overrides.log', 'rm .codearbiter/decisions/0007-auth.md', "sed -i 's/arbiter: enabled/arbiter: off/' .codearbiter/CONTEXT.md", 'g=git; $g push -f origin feature/login', 'npm test'];
  function guardBody() {
    return `<p class="lede">Pretend you are the agent. Type a command, or pick one below, and see what happens to it on its way to your repository.</p>
      <div class="seg2 nogl"><span>Current branch</span><div class="seg" role="group" aria-label="Current branch"><button data-branch="feature" aria-pressed="${st.branch === 'feature'}">feature/login</button><button data-branch="main" aria-pressed="${st.branch === 'main'}">main</button></div></div>
      <div class="seg2 nogl"><span>Staged change</span><div class="seg" role="group" aria-label="Staged change"><button data-secret="0" aria-pressed="${!st.secret}">Ordinary code</button><button data-secret="1" aria-pressed="${st.secret}">Contains an API key</button></div></div>
      <form id="g-form" class="g-form"><label for="g-cmd" class="sr">Command</label><input id="g-cmd" class="mono-in" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="git push --force"><button class="btn primary" type="submit">Run</button></form>
      <div id="g-out" aria-live="polite">${st.lastGuard || '<p class="muted">Pick an example or type a command, then press Run.</p>'}</div>
      <h3>Try these</h3>
      <div class="chips ex" aria-label="Example commands">${EXAMPLES.map((c) => `<button class="chip mono" data-ex="${esc(c)}">${esc(c)}</button>`).join('')}</div>
      <p class="note">A simplified re-implementation of a few rules from codeArbiter’s <code>pre-bash.py</code> and <code>git-enforce.py</code>, using their patterns and messages. The real guards cover many more spellings, read real git state and run outside the model.</p>`;
  }
  function runGuard(raw) {
    st.cmd = raw.trim(); if (!st.cmd) return;
    const r = simulateGuard(st.cmd, { branch: st.branch, secret: st.secret });
    const gitOp = /\b(commit|push)\b/.test(st.cmd);
    const stage = (n, name, res, detail = '') => `<li class="stage ${res}"><div class="st-h"><b>${n}. ${esc(name)}</b><span class="res">${res === 'ok' ? 'allows' : res === 'no' ? 'blocks' : 'not reached'}</span></div>${detail}</li>`;
    let h = `<ol class="stages">${stage(1, 'Host permissions', 'ok', '<p>Assumed to allow it here. Each harness has its own allow, ask and deny rules.</p>')}`;
    if (r.bash) {
      h += stage(2, 'codeArbiter shell gate (pre-bash.py)', 'no', `<pre class="stderr">BLOCKED [${esc(r.bash.tag)}]: ${esc(r.bash.msg)}</pre><p>The hook exits with code 2, so the harness never runs the command. This message goes back to the model as the tool result.</p>`);
      h += stage(3, 'Git’s own hooks (git-enforce.py)', 'skip');
    } else {
      h += stage(2, 'codeArbiter shell gate (pre-bash.py)', 'ok', '<p>Nothing in the command text matches a hard rule.</p>');
      if (r.git) h += stage(3, 'Git’s own hooks (git-enforce.py)', 'no', `<pre class="stderr">BLOCKED [${esc(r.git.tag)}]: ${esc(r.git.msg)}</pre><p>The hook exits with code 1 and git aborts the operation itself, whatever spelling produced it.</p>`);
      else h += stage(3, 'Git’s own hooks (git-enforce.py)', gitOp ? 'ok' : 'skip', gitOp ? '<p>Nothing to stop at the git level either.</p>' : '');
    }
    h += '</ol>';
    const verdict = r.bash || r.git;
    h = `<div class="verdict ${verdict ? 'no' : 'ok'}">${verdict ? `Blocked by ${esc(verdict.tag)}` : 'Allowed'}</div>` + h;
    const notes = [...r.notes];
    if (!verdict && /\bgit\s+commit\b/.test(st.cmd)) notes.push('Allowed by the guards. codeArbiter’s rules still send commits through the commit lane’s nine phases; the guards are the part that holds even if those rules are ignored.');
    else if (!verdict && /\bgit\s+push\b/.test(st.cmd)) notes.push('Allowed. Pushing a feature branch is normal work; the main branch changes only through a reviewed pull request.');
    for (const n of notes) h += `<p class="note">${esc(n)}</p>`;
    st.lastGuard = h;
    const out = $('#g-out');
    out.innerHTML = h;
    out.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    st.runs++; if (st.runs >= 3) ctx.markDone('lab:guard');
    ctx.api3d.guard?.(st.cmd, r);
  }

  /* ---- sampler */
  function samplerBody() {
    return `<div class="prompt-line"><span class="muted">The model has written</span><p>I changed the parser. Now the tests<span class="cont" id="s-cont"> …</span></p></div>
      <div class="slider"><label for="s-T">Temperature <b id="s-Tv"></b></label><input id="s-T" type="range" min="0" max="2" step="0.05" value="${st.T}"></div>
      <div class="slider"><label for="s-P">Top-p <b id="s-Pv"></b></label><input id="s-P" type="range" min="0.1" max="1" step="0.05" value="${st.topP}"></div>
      <div class="actions"><button class="btn primary" data-act="sample1">Sample once</button><button class="btn" data-act="sample100">Sample 100 times</button><button class="btn ghost" data-act="sreset" id="s-reset">Reset</button></div>
      <p class="insight" id="s-ins" aria-live="polite"></p>
      <div class="probs" id="s-probs" role="list" aria-label="Next-word probabilities"></div>
      <p class="note">Toy numbers chosen to show the mechanism. A real model scores every token in a vocabulary of tens of thousands, every time.</p>`;
  }
  function updateSampler() {
    const p = probs(st.T, st.topP);
    const total = st.counts.reduce((a, b) => a + b, 0);
    $('#s-Tv').textContent = st.T < 0.01 ? '0 (always the top word)' : st.T.toFixed(2);
    $('#s-Pv').textContent = st.topP.toFixed(2);
    $('#s-cont').textContent = st.last !== null ? CANDS[st.last][0] + ' …' : ' …';
    $('#s-probs').innerHTML = CANDS.map(([t], i) => {
      const pct = p[i] * 100;
      return `<div role="listitem" class="prow${p[i] === 0 ? ' out' : ''}${st.last === i ? ' hit' : ''}"><code>${esc(t.trim())}</code><div class="pbar"><i style="width:${pct.toFixed(1)}%"></i></div><span class="pv">${p[i] === 0 ? 'cut' : pct < 0.1 ? '<0.1%' : pct.toFixed(1) + '%'}</span><span class="pc">${total ? st.counts[i] + '×' : ''}</span></div>`;
    }).join('');
    $('#s-reset').hidden = !total;
    const passShare = total ? Math.round((st.counts[0] / total) * 100) : 0;
    let ins;
    if (st.T < 0.01) ins = 'At temperature 0 the sampler always takes the top word, so you get the same answer every time. It is still only a prediction: nothing ran.';
    else if (st.topP < 0.5 && p.filter((v) => v > 0).length <= 2) ins = 'A low top-p cuts the long tail: only the few likeliest words can be picked at all.';
    else if (st.T > 1.5) ins = 'High temperature flattens the odds. More variety, and more nonsense: even “explode” gets picked now and then.';
    else if (total >= 20) ins = `“pass” came out ${passShare}% of the time, and no test ran. It is simply the likeliest word after this sentence. That is why codeArbiter’s commit gate runs the tests itself.`;
    else ins = 'Sample a few times. Watch how often the model “says” the tests pass, without any test having run.';
    $('#s-ins').textContent = ins;
    // the machine's sampler wheel and logits show the same distribution, live
    const items = CANDS.map(([t], i) => ({ label: t.trim(), p: p[i] })).filter((x) => x.p > 0.004);
    const chosen = st.last !== null ? items.findIndex((x) => x.label === CANDS[st.last][0].trim()) : -1;
    const rest = Math.max(0, 1 - items.reduce((s2, x) => s2 + x.p, 0));
    ctx.api3d.showDist?.(rest > 0.004 ? [...items, { label: '', p: rest, other: true }] : items, chosen, st.T < 0.01 ? 0 : +st.T.toFixed(2));
  }
  function sample(n) {
    const p = probs(st.T, st.topP);
    for (let k = 0; k < n; k++) { let r = Math.random(), i = 0; while (i < p.length - 1 && r >= p[i]) { r -= p[i]; i++; } st.counts[i]++; st.last = i; }
    st.samples += n; if (st.samples >= 10) ctx.markDone('lab:sampler');
    updateSampler();
    const p2 = probs(st.T, st.topP);
    const shown = CANDS.map(([t], i) => ({ t: t.trim(), p: p2[i] })).filter((x) => x.p > 0.004);
    ctx.api3d.spin?.(Math.max(0, shown.findIndex((x) => x.t === CANDS[st.last][0].trim())), CANDS[st.last][0]);
  }

  /* ---- tokens */
  const PRESETS = [['Plain English', 'Fix the failing login test in src/auth/session.ts'], ['Code', 'const total = items.reduce((sum, x) => sum + x.price, 0);'], ['Long name', 'getUserAuthenticationTokenFromRequestHeaders'], ['Numbers', 'Order 1234567 shipped on 2026-11-25 for $1,049.99'], ['Spanish', 'La prueba de inicio de sesión está fallando']];
  function tokensBody() {
    return `<label for="t-in" class="sr">Text to cut into tokens</label><textarea id="t-in" rows="3" spellcheck="false"></textarea>
      <div class="chips ex">${PRESETS.map(([k, v]) => `<button class="chip" data-preset="${esc(v)}">${esc(k)}</button>`).join('')}</div>
      <div class="toks" id="t-toks" aria-label="Tokens"></div>
      <p class="tstat" id="t-stat"></p>
      ${ctx.has3d ? '<div class="actions"><button class="btn" data-act="sendtok">Send it into the machine</button></div>' : ''}
      <p class="insight">Code, long names, numbers and other languages cut into more, smaller pieces. Every limit and every price is counted in these pieces, not in words.</p>
      <p class="note">An illustrative tokenizer with simple rules, written for this page. Real tokenizers learn their pieces from data, so exact splits and counts differ by model. A dot (·) marks a space that belongs to the token.</p>`;
  }
  function updateTokens() {
    const toks = tokenize(st.text);
    const chars = st.text.length;
    $('#t-toks').innerHTML = toks.map((t, i) => `<span class="tok c${i % 5}" title="token #${tokId(t)}">${esc(t).replace(/ /g, '<i class="sp">·</i>')}</span>`).join('');
    $('#t-stat').innerHTML = `<b>${toks.length}</b> tokens · <b>${chars}</b> characters · about <b>${toks.length ? (chars / toks.length).toFixed(1) : 0}</b> characters per token`;
  }

  /* ---- context */
  function contextBody() {
    return `<div class="slider"><label for="c-turns">Turns into the session <b id="c-tv"></b></label><input id="c-turns" type="range" min="0" max="220" step="1" value="${st.turns}"></div>
      <div class="seg2"><span>codeArbiter</span><div class="seg" role="group" aria-label="codeArbiter"><button data-on="1" aria-pressed="${st.on}">Enabled</button><button data-on="0" aria-pressed="${!st.on}">Off</button></div></div>
      <div class="ctxbar" id="c-bar" role="img"></div>
      <div class="ctxlegend"><span><i class="k-fixed"></i>System and tools</span><span><i class="k-rules"></i>codeArbiter rules</span><span><i class="k-wf"></i>Lane instructions</span><span><i class="k-sum"></i>Summary</span><span><i class="k-conv"></i>Conversation</span><span><i class="k-res"></i>Tool results</span></div>
      <p class="tstat" id="c-stat"></p>
      <h3>What the model can still see</h3>
      <ul class="checks" id="c-checks"></ul>
      <p class="note">Illustrative proportions, not measurements. Real sessions vary with the model, the harness and the work. The tank in the machine follows this slider.</p>`;
  }
  function updateContext() {
    const c = simulateContext(st.turns, st.on);
    const seg = (cls, v, label) => (v > 0.05 ? `<i class="${cls}" style="width:${v}%" title="${esc(label)}: ${v.toFixed(0)}%"></i>` : '');
    $('#c-tv').textContent = st.turns;
    const bar = $('#c-bar');
    bar.innerHTML = seg('k-fixed', c.fixed, 'System prompt and tool definitions') + seg('k-rules', c.rules, 'codeArbiter rules') + seg('k-wf', c.wf, 'Lane instructions') + seg('k-sum', c.summary, 'Summary of earlier turns') + seg('k-conv', c.conv, 'Conversation') + seg('k-res', c.results, 'Tool results');
    bar.setAttribute('aria-label', `Context window ${c.used.toFixed(0)}% full`);
    $('#c-stat').innerHTML = `<b>${c.used.toFixed(0)}%</b> full · <b>${c.compactions}</b> compaction${c.compactions === 1 ? '' : 's'} so far`;
    const decided = st.turns >= 12, lost = decided && c.compactions > 0;
    const li = (cls, text) => `<li class="${cls}">${text}</li>`;
    $('#c-checks').innerHTML = [
      st.on ? li('ok', 'Operating rules: yes. codeArbiter re-injects them after every compaction.') : c.compactions ? li('no', 'Operating rules: only whatever the summary happened to keep.') : li('ok', 'Operating rules: still in the original prompt, for now.'),
      !decided ? li('maybe', 'You make a decision at turn 12. Drag past it.') : !lost ? li('ok', 'Your decision from turn 12: still in the conversation.') : st.on ? li('ok', 'Your decision from turn 12: yes, because it was written to <code>.codearbiter/</code> and can be read back.') : li('no', 'Your decision from turn 12: only a line in the summary, if that.'),
      st.on ? li('ok', 'Guards: unaffected. Hooks are programs, not text in the window, so nothing here can weaken them.') : li('no', 'Guards: none installed.'),
    ].join('');
    ctx.api3d.setBands?.({ fixed: c.fixed / 100, rules: c.rules / 100, wf: c.wf / 100, summary: c.summary / 100, conv: c.conv / 100, results: c.results / 100 });
    if (c.compactions > st.lastCompactions) { ctx.api3d.compact(); ctx.markDone('lab:context'); }
    st.lastCompactions = c.compactions;
  }

  /* ---- events */
  el.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b || b.classList.contains('gl')) return;
    if (b.dataset.lab) { st.lab = b.dataset.lab; render(); ctx.onOpen?.(st.lab); el.querySelector(`[data-lab="${st.lab}"]`)?.focus({ preventScroll: true }); return; }
    if (b.dataset.fault) { const f = FAULTS.find((x) => x.id === b.dataset.fault); ctx.markDone('fault:' + f.id); if (FAULTS.filter((x) => ctx.isDone('fault:' + x.id)).length >= 3) ctx.markDone('lab:faults'); ctx.playFault(f); return; }
    if (b.dataset.ex) { $('#g-cmd').value = b.dataset.ex; runGuard(b.dataset.ex); return; }
    if (b.dataset.branch) { st.branch = b.dataset.branch; el.querySelectorAll('[data-branch]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.branch === st.branch))); if (st.cmd && st.lastGuard) runGuard(st.cmd); return; }
    if (b.dataset.secret) { st.secret = b.dataset.secret === '1'; el.querySelectorAll('[data-secret]').forEach((x) => x.setAttribute('aria-pressed', String((x.dataset.secret === '1') === st.secret))); if (st.cmd && st.lastGuard) runGuard(st.cmd); return; }
    if (b.dataset.preset) { st.text = b.dataset.preset; $('#t-in').value = st.text; st.tokTries++; if (st.tokTries >= 2) ctx.markDone('lab:tokens'); updateTokens(); return; }
    if (b.dataset.on) { st.on = b.dataset.on === '1'; el.querySelectorAll('[data-on]').forEach((x) => x.setAttribute('aria-pressed', String((x.dataset.on === '1') === st.on))); st.lastCompactions = simulateContext(st.turns, st.on).compactions; updateContext(); return; }
    const a = b.dataset.act;
    if (a === 'close') ctx.onClose();
    else if (a === 'sample1') sample(1);
    else if (a === 'sample100') sample(100);
    else if (a === 'sreset') { st.counts = CANDS.map(() => 0); st.last = null; updateSampler(); }
    else if (a === 'sendtok') { ctx.api3d.feed?.(st.text); ctx.markDone('lab:tokens'); }
  });
  el.addEventListener('submit', (e) => { if (e.target.id === 'g-form') { e.preventDefault(); runGuard($('#g-cmd').value); } });
  el.addEventListener('input', (e) => {
    const t = e.target;
    if (t.id === 's-T') { st.T = +t.value; updateSampler(); }
    else if (t.id === 's-P') { st.topP = +t.value; updateSampler(); }
    else if (t.id === 't-in') { st.text = t.value; st.tokTries++; if (st.tokTries >= 6) ctx.markDone('lab:tokens'); updateTokens(); }
    else if (t.id === 'c-turns') { st.turns = +t.value; updateContext(); }
  });

  return {
    open(lab) { st.lab = lab || st.lab || 'faults'; render(); },
    render,
    get lab() { return st.lab; },
  };
}
