// The 3D viewer for /concepts/machine/: camera, picking, labels, inspector, tours, labs, glossary and intro.
// mountMachine() renders into a shadow root on the page's stage element, so the viewer's styles and the
// docs site's cannot collide, and returns a handle whose dispose() releases the WebGL context, every
// listener and every timer. Nothing plays until the reader asks, and nothing is stored between visits.
import { setModel, PARTS, TOURS, ZONES, FAMILIES, HOSTS, STATES, LANE_ORDER, META, SIMPLE, GLOSSARY, FAULTS, LABS } from './content.js';
import { createLabs, tokenize, tokId, MSG, simulateGuard } from './labs.js';
import { frameSVG, frameOf, FRAME_KEY, MOTION_KEY } from './symbols.js';
import markup from './viewer.html?raw';
import styles from './viewer.css?inline';

export async function mountMachine(hostEl, model, options = {}) {
  setModel(model);
  // The 3D engine is its own chunk; without WebGL the parts index, tours, labs and glossary still work.
  let THREE = null, buildMachine, polar, C, getGlow, createFX, createStory;
  try {
    const [t, m, f, st] = await Promise.all([import('./three.js'), import('./machine.js'), import('./fx.js'), import('./story.js')]);
    THREE = t; ({ buildMachine, polar, C, getGlow } = m); ({ createFX } = f); ({ createStory } = st);
  } catch (e) {
    THREE = null;
    console.warn('3D view unavailable:', e && e.message);
  }
  const root = hostEl.shadowRoot ?? hostEl.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>${styles}</style>${markup}`;
  const app = root.querySelector('.app');
  const ac = new AbortController();
  const { signal } = ac;
  const listen = (target, type, fn, opts = {}) => target.addEventListener(type, fn, { ...opts, signal });
  const timers = new Set();
  const setT = (fn, ms) => { const id = setTimeout(() => { timers.delete(id); if (!signal.aborted) fn(); }, ms); timers.add(id); return id; };
  let rafId = 0, resizeObs = null;

  const $ = (s) => root.querySelector(s);
  const rad = (d) => (d * Math.PI) / 180;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  // Nothing is stored: the docs site keeps no preferences or completion state between visits.
  const store = { get: (_k, d) => d, set() {} };
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const narrow = () => hostEl.clientWidth <= 860;
  const TIER = { core: 'Core lane', advanced: 'Advanced', internal: 'Internal protocol' };
  const ZONE_ORDER = ['you', 'model', 'harness', 'guards', 'skills', 'lanes', 'record', 'world', 'outside'];
  const TABS = ['tours', 'parts', 'glossary'];

  const S = {
    host: HOSTS[store.get('host', 'claude')] ? store.get('host', 'claude') : 'claude',
    labels: store.get('labels', true),
    motion: store.get('motion', !reduced),
    quality: ['auto', 'high', 'low'].includes(store.get('quality', 'auto')) ? store.get('quality', 'auto') : 'auto',
    sel: null, hov: null, iso: null, drawer: false, tab: 'tours', session: !!options.session,
    ins: false, lab: null, tour: null, step: 0, auto: false, tourAt: null, hash: '', say: false, intro: null, returnLab: null,
  };
  const progress = store.get('progress', {}) || {};
  const isDone = (k) => !!progress[k];
  function markDone(k) {
    if (progress[k]) return;
    progress[k] = 1; store.set('progress', progress);
    if (S.drawer && S.tab === 'tours') renderDrawer();
  }

  /* ------------------------------------------------------------ text helpers */
  const cmd = (n, a = '') => HOSTS[S.host].fmt(n) + (a ? ' ' + a : '');
  const fmt = (t) => esc(t)
    .replace(/\{\{([a-z-]+)((?: [^}]*)?)\}\}/g, (_, n, a) => `<code class="cmd">${cmd(n, a.trim())}</code>`)
    .replace(/`([^`]+)`/g, '<code>$1</code>');
  const isWf = (id) => PARTS[id]?.kind === 'Lane';
  const pname = (id) => (isWf(id) ? cmd(PARTS[id].cmd) : PARTS[id]?.name ?? id);
  const pnameHTML = (id) => (isWf(id) ? `<code class="cmd">${esc(cmd(PARTS[id].cmd))}</code>` : esc(PARTS[id].name));
  const omitted = (id) => isWf(id) && HOSTS[S.host].omits.includes(PARTS[id].cmd);
  const srcURL = (p) => {
    const path = p.replace(/\s*\(.*\)\s*$/, '').trim();
    return `${META.repo}/${path.endsWith('/') ? 'tree' : 'blob'}/main/${path.replace(/\/$/, '')}`;
  };
  const plainText = (html) => { const d = document.createElement('div'); d.innerHTML = html; return d.textContent.replace(/\s+/g, ' ').trim(); };

  /* ------------------------------------------------------------ glossary terms inside any text */
  const GL = (() => {
    const entries = [];
    GLOSSARY.forEach(([term, aliases], i) => { for (const a of new Set([term.replace(/\s*\(.*\)\s*$/, ''), ...aliases])) entries.push([a, i]); });
    entries.sort((a, b) => b[0].length - a[0].length);
    const map = new Map();
    for (const [a, i] of entries) { const k = a.toLowerCase().replace(/\s+/g, ' '); if (!map.has(k)) map.set(k, i); }
    const reEsc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // acronyms and mixed-case names match exactly; ordinary words also match with a capital first letter
    const pat = entries.map(([a]) => {
      const e = reEsc(a).replace(/ /g, '\\s+');
      return /[A-Z]/.test(a.slice(1)) ? e : `[${a[0].toUpperCase()}${a[0].toLowerCase()}]${e.slice(1)}`;
    }).join('|');
    return { re: new RegExp(`(?<![\\w-])(?:${pat})(?![\\w-])`, 'g'), map };
  })();
  const GL_SKIP = new Set(['CODE', 'BUTTON', 'A', 'PRE', 'KBD', 'H1', 'H2', 'H3', 'LABEL', 'TEXTAREA', 'INPUT', 'SELECT', 'OPTION']);
  // Wraps the first occurrence of each glossary term in a definition button. `seen` spans one block of text.
  function glossify(root, seen = new Set()) {
    if (!root) return seen;
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        for (let e = n.parentElement; e; e = e.parentElement) {
          if (GL_SKIP.has(e.tagName) || e.classList.contains('nogl') || e.classList.contains('pill')) return NodeFilter.FILTER_REJECT;
          if (e === root) break;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const nodes = [];
    while (tw.nextNode()) nodes.push(tw.currentNode);
    for (const n of nodes) {
      const text = n.nodeValue;
      if (text.length < 2) continue;
      GL.re.lastIndex = 0;
      let m, last = 0, frag = null;
      while ((m = GL.re.exec(text))) {
        const i = GL.map.get(m[0].toLowerCase().replace(/\s+/g, ' '));
        if (i === undefined || seen.has(i)) continue;
        seen.add(i);
        frag ??= document.createDocumentFragment();
        frag.append(text.slice(last, m.index));
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'gl'; b.dataset.g = String(i); b.textContent = m[0];
        b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false');
        frag.append(b);
        last = m.index + m[0].length;
      }
      if (frag) { frag.append(text.slice(last)); n.replaceWith(frag); }
    }
    return seen;
  }
  const pop = $('#glpop');
  let popFor = null, popPinned = false, popHide = null;
  function showPop(b, pin) {
    clearTimeout(popHide);
    const g = GLOSSARY[+b.dataset.g]; if (!g) return;
    popFor?.setAttribute('aria-expanded', 'false');
    popFor = b; popPinned = !!pin;
    pop.innerHTML = `<b>${esc(g[0])}</b><p>${fmt(g[2])}</p>${g[3] && PARTS[g[3]] && G ? `<button class="chip" data-go="${esc(g[3])}">Show it in the machine</button>` : ''}`;
    pop.hidden = false;
    const r = b.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    const hb = hostEl.getBoundingClientRect();
    const x = clamp(r.left - hb.left + r.width / 2 - w / 2, 8, hostEl.clientWidth - w - 8);
    let y = r.bottom - hb.top + 8;
    if (y + h > hostEl.clientHeight - 8) y = r.top - hb.top - h - 8;
    pop.style.left = x + 'px'; pop.style.top = Math.max(8, y) + 'px';
    b.setAttribute('aria-expanded', 'true');
  }
  function hidePop(delay = 0) {
    clearTimeout(popHide);
    const go = () => { pop.hidden = true; popFor?.setAttribute('aria-expanded', 'false'); popFor = null; popPinned = false; };
    if (delay) popHide = setT(go, delay); else go();
  }
  listen(root, 'pointerover', (e) => {
    if (e.pointerType === 'touch') return;
    const b = e.target.closest?.('.gl');
    if (b) { if (b !== popFor) showPop(b, false); else clearTimeout(popHide); }
    else if (e.target.closest?.('#glpop')) clearTimeout(popHide);
  });
  listen(root, 'pointerout', (e) => {
    if (e.pointerType === 'touch' || popPinned || !popFor) return;
    if (!e.target.closest?.('.gl, #glpop')) return;
    const to = e.relatedTarget?.closest?.('.gl, #glpop');
    if (to === popFor || to === pop) return;
    hidePop(240);
  });
  listen(root, 'click', (e) => {
    const b = e.target.closest?.('.gl');
    if (b) { e.preventDefault(); e.stopPropagation(); if (popFor === b && popPinned) hidePop(); else showPop(b, true); return; }
    if (!pop.hidden && !e.target.closest?.('#glpop')) hidePop();
  }, true);
  listen(root, 'focusin', (e) => { const b = e.target.closest?.('.gl'); if (b && b !== popFor) showPop(b, false); });
  listen(root, 'focusout', (e) => {
    if (popPinned || !popFor) return;
    const to = e.relatedTarget?.closest?.('.gl, #glpop');
    if (!to) hidePop(160);
  });
  pop.addEventListener('click', (e) => { const b = e.target.closest('button[data-go]'); if (b) { hidePop(); select(b.dataset.go); } });

  /* ------------------------------------------------------------ 3D */
  const stage = $('#stage');
  let G = null;
  if (THREE) {
    try { G = { renderer: new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' }) }; } catch { G = null; }
  }

  let invalidate = () => {};
  const flows = [];
  let settle = 0, autoLow = false;
  const effQuality = () => (S.quality === 'auto' ? (autoLow ? 'low' : 'high') : S.quality);

  if (G) {
    const { renderer } = G;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.toneMappingExposure = 1.0;
    stage.prepend(renderer.domElement);
    const canvas = renderer.domElement;
    canvas.setAttribute('aria-hidden', 'true');

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(C.bg);
    scene.fog = new THREE.Fog(C.bg, 260, 640);
    const pm = new THREE.PMREMGenerator(renderer);
    scene.environment = pm.fromScene(new THREE.RoomEnvironment(), 0.04).texture;
    scene.environmentIntensity = 0.78;
    scene.add(new THREE.HemisphereLight(0xa9c1de, 0x0b0f14, 0.95));
    const key = new THREE.DirectionalLight(0xffffff, 2.1); key.position.set(60, 110, 80); scene.add(key);
    const rim = new THREE.DirectionalLight(0x7cc4ff, 0.55); rim.position.set(-90, 50, -100); scene.add(rim);
    const coreLight = new THREE.PointLight(0x7cc4ff, 260, 46, 1.4); coreLight.position.set(0, 12, 0); scene.add(coreLight);

    const camera = new THREE.PerspectiveCamera(40, 1, 0.5, 1500);
    const labelR = new THREE.CSS2DRenderer({ element: $('#labels') });
    const controls = new THREE.OrbitControls(camera, canvas);
    Object.assign(controls, { enableDamping: true, dampingFactor: 0.08, maxPolarAngle: rad(84), minDistance: 5, maxDistance: 380, zoomToCursor: true, screenSpacePanning: false, rotateSpeed: 0.6, zoomSpeed: 1.1, panSpeed: 0.9 });

    const M = buildMachine(scene, PARTS);
    const glow = getGlow();
    let fx;
    try { fx = createFX({ renderer, scene, camera, M, glow, C }); } catch (e) {
      console.warn('Effects unavailable:', e && e.message);
      const no = () => {};
      fx = { render: () => renderer.render(scene, camera), resize: no, tick: () => false, setQuality: no, slam: no, celebrate: no, ripple: no, launch: no, boot: (d) => d?.(), finishBoot: no, unshake: no, shake: no, pulseStream: no, setTraffic: no, holdGate: no, booting: false, high: false };
    }
    fx.setTraffic(false); // the story engine replaces anonymous traffic with labelled tool calls
    const NOSTORY = { active: false, setActive() {}, play() {}, playGen() {}, playInput() {}, playCall() {}, playGuard() {}, cancel() {}, tag() {}, ledger() {}, line() {}, phase() {}, clear() {}, showDist() {}, spin() {}, contextChanged() {}, overlays: () => [], tick: () => false };
    let story = NOSTORY;
    try { story = createStory({ scene, camera, M, fx, C, tokenize, tokId, esc, frameSVG, MSG }); } catch (e) { console.warn('Story unavailable:', e && e.message); }
    Object.assign(G, { scene, camera, controls, labelR, M, canvas, fx, story });
    if (options.debug) window.__machine = G; // test hook, off unless the page asks for it

    /* labels */
    const labels = new Map();
    for (const [id, p] of M.parts) {
      const el = document.createElement('div');
      el.className = 'lbl' + (isWf(id) ? ' cmd' : '') + (p.meta.preview ? ' prev' : '');
      el.innerHTML = `${frameSVG(frameOf(PARTS[id]))}<span class="nm">${esc(pname(id))}</span>`;
      el.addEventListener('click', (e) => { e.stopPropagation(); select(id); });
      el.addEventListener('pointerenter', () => setHover(id, true));
      el.addEventListener('pointerleave', () => setHover(null, true));
      el.addEventListener('wheel', (e) => { e.preventDefault(); canvas.dispatchEvent(new WheelEvent('wheel', e)); }, { passive: false });
      const o = new THREE.CSS2DObject(el);
      o.position.copy(p.anchor).add(new THREE.Vector3(0, 0.6, 0));
      o.center.set(0.5, 1);
      scene.add(o);
      labels.set(id, { el, o, p });
    }
    const ZPOS = { model: [0, 27.6, 0], harness: polar(17.5, 318, 2.6), guards: polar(28, 306, 3.6), record: polar(87, 210, 13.4), world: polar(84, 116, 8.5), outside: polar(84, 287, 9.5), you: polar(70, 0, 5.8) };
    const zoneLabels = Object.entries(ZPOS).map(([z, p]) => {
      const el = document.createElement('div'); el.className = 'zlbl'; el.textContent = ZONES[z].name;
      const o = new THREE.CSS2DObject(el); o.position.copy(Array.isArray(p) ? new THREE.Vector3(...p) : p); scene.add(o);
      return { z, o, el };
    });
    const famLabels = M.families.map(({ fam, mid }) => {
      const el = document.createElement('div'); el.className = 'flbl'; el.textContent = FAMILIES[fam].name;
      const o = new THREE.CSS2DObject(el); o.position.copy(polar(58.8, mid, 0.4)); scene.add(o);
      return { o, el };
    });
    G.labels = labels;

    /* tour flows */
    const podGeo = new THREE.SphereGeometry(0.45, 16, 12);
    const pool = Array.from({ length: 6 }, () => {
      const m = new THREE.Mesh(podGeo, new THREE.MeshBasicMaterial({ color: C.blue }));
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glow, color: C.blue, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false }));
      s.scale.set(3.2, 3.2, 1); m.add(s); m.visible = false; scene.add(m);
      return { m, s, busy: false };
    });
    const anchorOf = (id) => M.parts.get(id).anchor.clone().add(new THREE.Vector3(0, 0.5, 0));
    G.anchorOf = anchorOf;
    const arc = (a, b) => { const mid = a.clone().add(b).multiplyScalar(0.5); mid.y = Math.max(a.y, b.y) + 3 + a.distanceTo(b) * 0.22; return new THREE.QuadraticBezierCurve3(a, mid, b); };
    const lineMat = new THREE.MeshBasicMaterial({ color: C.blue, transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending, depthWrite: false });
    const routeMat = new THREE.MeshBasicMaterial({ color: 0xc7d0da, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false });
    const lineGroup = new THREE.Group(); scene.add(lineGroup);
    G.flow = (from, to, color) => {
      const curve = arc(anchorOf(from), anchorOf(to));
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.07, 6), lineMat);
      lineGroup.add(tube);
      flows.push({ curve, color: new THREE.Color(color), acc: 99, dur: clamp(0.7 + curve.getLength() / 45, 0.9, 2.4), tube });
    };
    G.clearFlows = () => { flows.length = 0; lineGroup.children.slice().forEach((c) => { c.geometry.dispose(); lineGroup.remove(c); }); pool.forEach((p) => { p.busy = false; p.m.visible = false; }); };
    const routeGroup = new THREE.Group(); scene.add(routeGroup);
    G.showRoute = (id) => {
      G.hideRoute();
      const seq = [];
      for (const [at] of PARTS[id].route || []) if (seq[seq.length - 1] !== at) seq.push(at);
      for (let i = 0; i < seq.length - 1; i++) routeGroup.add(new THREE.Mesh(new THREE.TubeGeometry(arc(anchorOf(seq[i]), anchorOf(seq[i + 1])), 40, 0.06, 6), routeMat));
    };
    G.hideRoute = () => routeGroup.children.slice().forEach((c) => { c.geometry.dispose(); routeGroup.remove(c); });
    const tickFlows = (dt) => {
      for (const f of flows) {
        f.acc += dt;
        if (S.motion && f.acc > f.dur + 0.5) {
          const p = pool.find((q) => !q.busy);
          if (p) { f.acc = 0; Object.assign(p, { busy: true, t: 0, f }); p.m.material.color.copy(f.color); p.s.material.color.copy(f.color); p.m.visible = true; }
        }
      }
      for (const p of pool) {
        if (!p.busy) continue;
        p.t += dt / p.f.dur;
        if (p.t >= 1 || !flows.includes(p.f)) { p.busy = false; p.m.visible = false; continue; }
        const u = p.t < 0.5 ? 2 * p.t * p.t : 1 - (-2 * p.t + 2) ** 2 / 2;
        p.m.position.copy(p.f.curve.getPoint(u));
      }
    };

    /* camera */
    const tw = { on: false };
    const sph0 = new THREE.Spherical(), sph1 = new THREE.Spherical();
    const ease = (u) => (u < 0.5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2);
    const fitDist = (r) => { const v = rad(camera.fov) / 2; const h = Math.atan(Math.tan(v) * camera.aspect); return r / Math.sin(Math.min(v, h)); };
    const tweenTo = (pos, target, dur = 1.15) => {
      if (!S.motion) { camera.position.copy(pos); controls.target.copy(target); controls.update(); invalidate(); return; }
      Object.assign(tw, { on: true, start: performance.now(), dur, t0: controls.target.clone(), t1: target.clone() });
      sph0.setFromVector3(camera.position.clone().sub(tw.t0));
      sph1.setFromVector3(pos.clone().sub(tw.t1));
      tw.dth = Math.atan2(Math.sin(sph1.theta - sph0.theta), Math.cos(sph1.theta - sph0.theta));
    };
    const stepTween = (now) => {
      const u = ease(Math.min(1, (now - tw.start) / 1000 / tw.dur));
      controls.target.lerpVectors(tw.t0, tw.t1, u);
      const r = Math.exp(Math.log(sph0.radius) + (Math.log(sph1.radius) - Math.log(sph0.radius)) * u);
      const s = new THREE.Spherical(r, sph0.phi + (sph1.phi - sph0.phi) * u, sph0.theta + tw.dth * u);
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(s));
      if (u >= 1) tw.on = false;
    };
    controls.addEventListener('start', () => { tw.on = false; });
    const camAz = () => { const v = camera.position.clone().sub(controls.target); return Math.atan2(v.x, v.z); };
    const fromAngles = (target, az, el, d) => target.clone().add(new THREE.Vector3(Math.sin(az) * Math.cos(el) * d, Math.sin(el) * d, Math.cos(az) * Math.cos(el) * d));
    const rightW = () => (S.ins || S.lab ? 442 : 0);
    const PRE = {
      model: { t: [0, 11.5, 0], el: 10, R: 15 },
      harness: { t: [0, 2, 0], el: 44, R: 25 },
      guards: { t: [0, 2, 0], el: 48, R: 34 },
      lanes: { t: [0, 1, 0], el: 58, R: 60 },
      skills: { t: [0, 2, 0], el: 50, R: 44 },
    };
    G.overview = (instant) => {
      const el = rad(narrow() ? 50 : 33), az = rad(-14);
      const w = stage.clientWidth, panels = narrow() ? 0 : (S.drawer ? 382 : 0) + rightW();
      const v = rad(camera.fov) / 2, h = Math.atan(Math.tan(v) * camera.aspect * Math.max(0.45, (w - panels) / w));
      const R = narrow() ? 58 : 86;
      const d = Math.max(R / Math.tan(h), (R * Math.sin(el) + 9) / Math.tan(v));
      const target = new THREE.Vector3(0, 2, narrow() ? 4 : 9);
      const pos = fromAngles(target, az, el, d);
      if (instant) { tw.on = false; camera.position.copy(pos); controls.target.copy(target); controls.update(); } else tweenTo(pos, target, 1.3);
    };
    G.preset = (name) => {
      if (name === 'overview') return G.overview();
      const p = PRE[name]; if (!p) return;
      const target = new THREE.Vector3(...p.t);
      tweenTo(fromAngles(target, p.az !== undefined ? rad(p.az) : camAz(), rad(p.el), fitDist(p.R)), target);
    };
    G.shot = (t, az, el, d, dur) => {
      const target = new THREE.Vector3(...t), pos = fromAngles(target, rad(az), rad(el), d);
      if (!dur) { tw.on = false; camera.position.copy(pos); controls.target.copy(target); controls.update(); invalidate(); } else tweenTo(pos, target, dur);
    };
    G.flyTo = (id, close) => {
      const p = M.parts.get(id); if (!p) return;
      const c = p.sphere.center.clone(); const r = p.sphere.radius;
      const camH = camera.position.clone().sub(controls.target).setY(0);
      if (camH.lengthSq() < 1e-6) camH.set(0, 0, 1);
      camH.normalize();
      let dir, el;
      if (p.radial < 2 && r > 12) { dir = camH; el = rad(48); }
      else if (p.face === 'in' && ['record', 'world', 'outside'].includes(p.zone)) { dir = new THREE.Vector3(-c.x, 0, -c.z).normalize().multiplyScalar(0.8).add(camH.multiplyScalar(0.2)).normalize(); el = rad(close ? 22 : 30); }
      else if (p.radial > 12) { dir = new THREE.Vector3(c.x, 0, c.z).normalize().multiplyScalar(0.72).add(camH.multiplyScalar(0.28)).normalize(); el = rad(close ? 24 : 27); }
      else { dir = camH; el = rad(12); }
      const spread = close ? 1.15 : p.zone === 'lanes' || p.zone === 'skills' || p.zone === 'guards' ? 2.7 : p.radial > 12 ? 2.0 : 1.45;
      const d = clamp(fitDist(r * spread + 1.5), close ? 7 : 12, 150);
      tweenTo(c.clone().add(dir.multiplyScalar(Math.cos(el) * d)).add(new THREE.Vector3(0, Math.sin(el) * d, 0)), c);
    };
    G.aim = (laneId) => { const p = M.parts.get(laneId); const r = M.parts.get('router'); if (p && r) r.api.aim(p.anchor.clone().add(new THREE.Vector3(0, 0.3, 0)), 9000); };
    G.unaim = () => M.parts.get('router')?.api.clear?.();

    /* view offset so the subject sits in the visible area between panels */
    const off = { x: 0, y: 0, wx: 0, wy: 0 };
    G.updateOffset = () => {
      const w = stage.clientWidth;
      if (narrow()) { off.wx = 0; off.wy = S.ins || S.lab || S.drawer ? stage.clientHeight * 0.26 : S.tour ? 90 : 0; }
      else { const li = S.drawer ? 382 : 0, ri = rightW(); off.wx = (ri - li) / 2; off.wy = S.tour ? 95 : 0; }
      if (!S.motion) { off.x = off.wx; off.y = off.wy; applyOffset(); }
      invalidate();
      return w;
    };
    const applyOffset = () => { const w = stage.clientWidth, h = stage.clientHeight; camera.setViewOffset(w, h, off.x, off.y, w, h); camera.updateProjectionMatrix(); };

    const resize = () => {
      const w = stage.clientWidth, h = stage.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      fx.resize(w, h);
      labelR.setSize(w, h);
      camera.aspect = w / h;
      camera.fov = w / h < 0.8 ? 56 : 40;
      applyOffset();
      invalidate();
    };
    G.resize = resize;
    fx.setQuality(effQuality());
    resizeObs = new ResizeObserver(resize); resizeObs.observe(stage);
    resize();

    /* picking */
    const ray = new THREE.Raycaster(); const ndc = new THREE.Vector2();
    let pending = null, down = null;
    const pickAt = (x, y) => {
      const r = canvas.getBoundingClientRect();
      ndc.set(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const targets = S.iso ? M.pickables.filter((o) => PARTS[o.userData.pid].zone === S.iso) : M.pickables;
      const hit = ray.intersectObjects(targets, false)[0];
      return hit ? hit.object.userData.pid : null;
    };
    canvas.addEventListener('pointermove', (e) => { if (e.pointerType !== 'touch') pending = e; });
    canvas.addEventListener('pointerleave', () => { pending = null; setHover(null); });
    canvas.addEventListener('pointerdown', (e) => {
      if (S.intro === 'play') { endIntro(true); return; }
      down = { x: e.clientX, y: e.clientY, t: performance.now(), b: e.button };
    });
    canvas.addEventListener('pointerup', (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y), quick = performance.now() - down.t < 700, b = down.b;
      down = null;
      if (moved < 7 && quick && b === 0) { const id = pickAt(e.clientX, e.clientY); if (id) select(id); else if (!S.tour) deselect(); }
    });
    canvas.addEventListener('dblclick', (e) => { const id = pickAt(e.clientX, e.clientY); if (id) { select(id, { fly: false }); G.flyTo(id, true); } });
    G.doPick = () => {
      if (!pending) return;
      const e = pending; pending = null;
      const id = pickAt(e.clientX, e.clientY);
      setHover(id);
      const tip = $('#tip');
      if (id) { const hb = hostEl.getBoundingClientRect(); tip.style.left = Math.min(hostEl.clientWidth - 310, e.clientX - hb.left + 16) + 'px'; tip.style.top = Math.min(hostEl.clientHeight - 80, e.clientY - hb.top + 18) + 'px'; }
    };

    /* emphasis, ghosting, lamps */
    const HL2 = new THREE.Color(0x3a4656), HL1 = new THREE.Color(0x242d38);
    G.emph = (id) => {
      const p = M.parts.get(id); if (!p) return;
      const lvl = id === S.sel || id === S.tourAt ? 2 : id === S.hov ? 1 : 0;
      for (const r of p.mats) {
        if (!r.em || r.em.r + r.em.g + r.em.b > 0.02) continue;
        if (lvl) { r.m.emissive.copy(lvl === 2 ? HL2 : HL1); r.m.emissiveIntensity = 1; } else { r.m.emissive.copy(r.em); r.m.emissiveIntensity = r.ei; }
      }
      p.halo.material.opacity = lvl === 2 ? 0.85 : lvl === 1 ? 0.4 : 0;
      p.halo.visible = lvl > 0 && !p.ghost;
      invalidate();
    };
    G.applyIso = () => {
      for (const p of M.parts.values()) {
        const on = !S.iso || p.zone === S.iso;
        if (!!p.ghost === !on) continue;
        p.ghost = !on;
        for (const r of p.mats) {
          if (r.m.isSpriteMaterial) continue;
          if (on) { r.m.transparent = r.tr; r.m.opacity = r.op; r.m.depthWrite = r.dw; } else { r.m.transparent = true; r.m.opacity = r.op * 0.07; r.m.depthWrite = false; }
          r.m.needsUpdate = true;
        }
        p.group.traverse((o) => { if (o.isSprite) { o.userData.ghost = !on; o.visible = on && o.material.opacity > 0; } });
        p.lamp.visible = on && !!p.lampOn;
        if (!on) p.halo.visible = false;
      }
      G.lod(); invalidate();
    };
    G.lamp = (id, st) => {
      const p = M.parts.get(id); if (!p) return;
      if (st) { p.lamp.material.color.set(STATES[st].color); p.lamp.material.opacity = 0.9; p.lampOn = true; } else { p.lamp.material.opacity = 0; p.lampOn = false; }
      p.lamp.visible = p.lampOn && !p.ghost;
      p.api.state?.(st || null);
      if (st && id === 'persona-injector') p.api.inject?.();
      settle = 4;
    };
    G.settle = () => { settle = Math.max(settle, 4); invalidate(); };

    /* label level of detail */
    const NUDGE = [0, 24, -24, 48, -48, 80, -80, 120, -120, 170, -170];
    const UI_OBSTACLES = ['.brand', '.toolbar', '#drawer', '#inspector', '#lab', '#player', '#zonebar', '#legend'];
    const LOD = { lanes: 1e9, model: 50, harness: 68, guards: 80, skills: 86, record: 118, world: 118, outside: 118, you: 118 };
    const _v = new THREE.Vector3();
    const sizeOf = (L) => {
      if (!L.ok) {
        const w = L.el.offsetWidth;
        if (w) { L.w = w; L.h = L.el.offsetHeight; L.ok = true; if (L.defW) { L.defW = L.w; L.defH = L.h; } } // overlays remember their last real size while hidden
        else if (L.defW) { L.w = L.defW; L.h = L.defH; }
        else { const mono = L.el.classList.contains('cmd'); L.w = L.el.textContent.length * (mono ? 7.4 : 6.9) + 18; L.h = 24; }
      }
      return L;
    };
    G.resetLabelSizes = () => { for (const L of labels.values()) L.ok = false; };
    let farMode = null;
    G.lod = () => {
      const camD = camera.position.distanceTo(controls.target);
      const far = camD > 110;
      if (far !== farMode) { farMode = far; $('#labels').classList.toggle('far', far); G.resetLabelSizes(); }
      const W = stage.clientWidth, H = stage.clientHeight;
      const cand = [];
      const ovs = G.story.overlays();
      const suppressed = new Set(ovs.filter((o) => o.want && o.suppress).map((o) => o.suppress));
      const push = (L, pr, kind) => {
        _v.copy(L.o.position).project(camera);
        if (_v.z > 1 || _v.z < -1) { L.o.visible = false; return; }
        const x = (_v.x * 0.5 + 0.5) * W, y = (-_v.y * 0.5 + 0.5) * H;
        cand.push({ L, pr, d: camera.position.distanceTo(L.o.position), x, y, kind });
      };
      for (const [id, L] of labels) {
        const p = L.p;
        const special = id === S.sel || id === S.hov || id === S.tourAt;
        let want = special;
        if (!want && S.labels && !p.ghost && !suppressed.has(id)) want = camera.position.distanceTo(L.o.position) < LOD[p.zone] && !(p.zone === 'lanes' && camD > 340);
        if (!want) { L.o.visible = false; continue; }
        push(sizeOf(L), special ? 0 : p.zone === 'lanes' ? 3 : 2, 'part');
      }
      for (const ov of ovs) { if (!ov.want) { ov.o.visible = false; continue; } ov.defW ??= ov.id === 'bubble' ? 330 : 270; ov.defH ??= ov.id === 'bubble' ? 130 : 120; sizeOf(ov); cand.push({ L: ov, pr: ov.pr, d: 0, ov: true }); }
      for (const z of zoneLabels) { const want = S.labels && camD > 78 && (!S.iso || S.iso === z.z); if (want) push(sizeOf(z), 1, 'zone'); else z.o.visible = false; }
      for (const f of famLabels) { const want = S.labels && camD > 40 && camD < 340 && (!S.iso || S.iso === 'lanes'); if (want) push(sizeOf(f), 1, 'fam'); else f.o.visible = false; }
      cand.sort((a, b) => a.pr - b.pr || a.d - b.d);
      // panels over the stage count as occupied space, so labels never hide under them
      const placed = [];
      for (const sel of UI_OBSTACLES) { const el = root.querySelector(sel); if (el && !el.hidden && el.getClientRects().length) { const b = el.getBoundingClientRect(); if (b.width && b.height) placed.push([b.left, b.top, b.right, b.bottom]); } }
      const free = (r) => !(r[0] < 2 || r[2] > W - 2 || r[1] < 2 || r[3] > H - 2) && !placed.some((q) => r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]);
      for (const c of cand) {
        if (c.ov) {
          // overlays try their candidate positions, keeping the last one that worked so they do not jump around
          const alts = c.L.alts?.length ? c.L.alts : [c.L.o.position.clone()];
          const order = [...new Set([c.L.alt ?? 0, ...alts.keys()])].filter((i) => i < alts.length);
          let ok = false;
          for (const i of order) {
            _v.copy(alts[i]).project(camera);
            if (_v.z > 1 || _v.z < -1) continue;
            const x = (_v.x * 0.5 + 0.5) * W, y = (-_v.y * 0.5 + 0.5) * H, w = c.L.w + 6, h = c.L.h + 4;
            // slide sideways a little before giving up on a position
            for (const dx of NUDGE) {
              const r = [x + dx - w / 2, y - 6 - h, x + dx + w / 2, y - 6];
              if (!free(r)) continue;
              if (dx) c.L.o.position.set(_v.x + (2 * dx) / W, _v.y, _v.z).unproject(camera); else c.L.o.position.copy(alts[i]);
              c.L.alt = i; placed.push(r); ok = true; break;
            }
            if (ok) break;
          }
          if (!ok && c.L.hud) {
            // last resort for the transcript: a fixed slot clear of the panels, held at the model's depth
            const w = c.L.w + 6, h = c.L.h + 4;
            const top = Math.max(0, ...['.brand', '.toolbar'].map((q) => { const e = root.querySelector(q); return e && e.getClientRects().length ? e.getBoundingClientRect().bottom : 0; })) + 8;
            const zb = root.querySelector('#zonebar'), bottom = zb && zb.getClientRects().length ? zb.getBoundingClientRect().top - 8 : H - 8;
            _v.copy(MODEL_C).project(camera);
            const z = _v.z > -1 && _v.z < 1 ? _v.z : 0.98;
            for (const [x, y] of [[W / 2, top + h + 6], [12 + w / 2, top + h + 6], [W - 12 - w / 2, top + h + 6], [12 + w / 2, bottom + 6], [W / 2, bottom + 6]]) {
              const r = [x - w / 2, y - 6 - h, x + w / 2, y - 6];
              if (!free(r)) continue;
              c.L.o.position.set((x / W) * 2 - 1, -(y / H) * 2 + 1, z).unproject(camera);
              placed.push(r); ok = true; break;
            }
          }
          c.L.o.visible = ok;
          continue;
        }
        const w = c.L.w + 6, h = c.L.h + 4;
        const cx = c.kind === 'part' ? c.y - 6 - h / 2 : c.y;
        const r = [c.x - w / 2, cx - h / 2, c.x + w / 2, cx + h / 2];
        const clipped = c.pr > 0 && (r[0] < 2 || r[2] > W - 2 || r[1] < 2 || r[3] > H - 2);
        const hit = clipped || (c.pr > 0 && placed.some((q) => r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]));
        c.L.o.visible = !hit;
        if (!hit) placed.push(r);
      }
    };

    /* render loop */
    const MODEL_C = new THREE.Vector3(0, 11, 0);
    let needs = 3, last = performance.now(), simT = 0, frameN = 0;
    const perf = { arm: performance.now() + 2500, samples: [], done: false };
    invalidate = () => { needs = Math.max(needs, 2); };
    controls.addEventListener('change', invalidate);
    const loop = (now) => {
      rafId = requestAnimationFrame(loop);
      const raw = now - last;
      const dt = Math.min(0.05, Math.max(0.001, raw / 1000)); last = now;
      if (document.hidden) return;
      if (S.motion) simT += dt;
      fx.unshake();
      if (tw.on) stepTween(now);
      if (Math.abs(off.x - off.wx) > 0.5 || Math.abs(off.y - off.wy) > 0.5) { off.x += (off.wx - off.x) * Math.min(1, dt * 7); off.y += (off.wy - off.y) * Math.min(1, dt * 7); applyOffset(); needs = 2; }
      const moved = controls.update();
      const t = controls.target;
      if (Math.hypot(t.x, t.z) > 115) { const s = 115 / Math.hypot(t.x, t.z); t.x *= s; t.z *= s; }
      t.y = clamp(t.y, 0, 30);
      if (S.motion) { for (const p of M.parts.values()) p.api.tick?.(simT, dt); }
      else if (settle > 0) { settle--; for (const p of M.parts.values()) p.api.tick?.(simT, 1); needs = 2; }
      tickFlows(dt);
      const fxBusy = fx.tick(dt, S.motion);
      // the story keeps wall-clock time (capped), so a slow device sees the same narrative pace
      const storyBusy = G.story.tick(Math.min(0.25, Math.max(0.001, raw / 1000)), S.motion, { labels: S.labels && !S.intro, camToModel: camera.position.distanceTo(MODEL_C), narrowHidden: narrow() && (!!S.drawer || S.ins || !!S.lab || !!S.tour) });
      fx.shake(dt);
      let pulsing = false;
      for (const p of M.parts.values()) if (p.lampOn) { pulsing = true; p.lamp.material.opacity = S.motion ? 0.6 + 0.35 * Math.sin(now / 260) : 0.9; }
      G.doPick();
      if (moved || ++frameN % (storyBusy ? 3 : 6) === 0) G.lod();
      if (S.motion || tw.on || moved || flows.length || pulsing || fxBusy || storyBusy || needs > 0) {
        if (fx.bloom) {
          const u = clamp((camera.position.distanceTo(controls.target) - 25) / 70, 0, 1);
          fx.bloom.strength = 0.36 + 0.28 * u * u * (3 - 2 * u) + (S.intro === 'play' ? 0.3 : 0);
        }
        fx.render();
        labelR.render(scene, camera);
        needs = Math.max(0, needs - 1);
        // automatic quality: one measurement, a little after start; drops effects if frames run slow
        if (!perf.done && S.quality === 'auto' && S.motion && fx.high && !fx.booting && now > perf.arm && raw < 500) {
          perf.samples.push(raw);
          if (perf.samples.length >= 120) {
            perf.done = true;
            const med = perf.samples.sort((a, b) => a - b)[60];
            if (med > 34) { autoLow = true; applyQuality(); toast('Lighter effects switched on to keep the machine smooth here. Change it under Help.'); }
          }
        }
      }
    };
    G.overview(true);
    G.lod();
    rafId = requestAnimationFrame(loop);
  } else {
    $('#fallback').style.display = 'block';
    app.classList.add('no3d');
  }
  function applyQuality() {
    if (G) { G.fx.setQuality(effQuality()); G.resize(); }
    renderQualitySeg();
  }

  /* bridge for labs and tours (all no-ops without 3D) */
  const fxOK = () => G && S.motion;
  const api3d = {
    flyTo(id) { G?.flyTo(id); },
    slam(id) {
      if (!G) return;
      G.flyTo(id);
      setT(() => { G.M.parts.get(id)?.api.block?.(); if (fxOK()) G.fx.slam(id, true); G.settle(); }, S.motion ? 700 : 0);
    },
    open(id) {
      if (!G) return;
      G.flyTo(id);
      setT(() => { G.M.parts.get(id)?.api.open?.(); if (fxOK()) G.fx.ripple(id, C.green); G.settle(); }, S.motion ? 700 : 0);
    },
    sample() { if (!G) return; G.M.parts.get('sampler')?.api.sample?.(); G.fx.pulseStream(); G.settle(); },
    setFill(v) { if (!G) return; G.M.parts.get('context-window')?.api.setFill?.(v); G.settle(); },
    compact() { if (!G) return; G.M.parts.get('compaction')?.api.compact?.(); G.settle(); },
    pulse() { G?.fx.pulseStream(); },
    // the guard lab sends the typed command down the bash arm to the gate that decides it
    guard(cmd, r) { if (!G) return; G.flyTo(r.git ? 'git-hooks' : 'guard-bash'); setT(() => { G.story.cancel(); G.story.playGuard(cmd, r); }, S.motion ? 650 : 0); if (!S.motion) { const id = r.bash ? 'guard-bash' : r.git ? 'git-hooks' : null; if (id) { G.M.parts.get(id)?.api.block?.(); G.settle(); } } },
    showDist(items, chosen, temp) { if (!G) return; G.story.showDist(items, chosen, temp); G.settle(); },
    spin(i, label) { if (!G) return; G.story.spin(i, label); G.settle(); },
    feed(text) { if (!G) return; G.flyTo('tokenizer'); G.story.cancel(); setT(() => G.story.playInput(text, 'pa'), S.motion ? 600 : 0); },
    setBands(b) { if (!G) return; G.M.parts.get('context-window')?.api.setBands?.(b); G.story.contextChanged(); G.settle(); },
  };
  const resetTank = () => { if (G && !S.tour) { G.M.parts.get('context-window')?.api.reset?.(); G.settle(); } };
  // the example session plays only when nothing else is asking for attention
  const syncTraffic = () => { G?.story.setActive(S.session && !S.tour && !S.lab && !S.intro && S.motion); setToggle($('#b-session'), S.session); };

  /* ------------------------------------------------------------ hover tip */
  function setHover(id, fromLabel) {
    if (S.hov === id) return;
    const prev = S.hov; S.hov = id;
    if (G) { if (prev) G.emph(prev); if (id) G.emph(id); G.canvas.style.cursor = id ? 'pointer' : ''; }
    labelClasses();
    const tip = $('#tip');
    if (id && !fromLabel && !narrow()) { tip.innerHTML = `<b>${frameSVG(frameOf(PARTS[id]))}${pnameHTML(id)}</b><span>${fmt(PARTS[id].tagline)}</span>`; tip.style.opacity = 1; } else tip.style.opacity = 0;
  }

  function labelClasses() {
    if (!G) return;
    for (const [id, L] of G.labels) {
      L.el.classList.toggle('sel', id === S.sel);
      L.el.classList.toggle('hot', id === S.hov);
      L.el.classList.toggle('off', omitted(id));
      const st = id === S.tourAt ? S.tour?.steps[S.step]?.state || 'run' : null;
      if (st) { L.el.dataset.st = st; L.el.style.setProperty('--stc', STATES[st].color); } else { delete L.el.dataset.st; }
    }
    G.lod();
  }

  /* ------------------------------------------------------------ panels */
  const ins = $('#inspector'), labEl = $('#lab');
  function setPanels() {
    app.classList.toggle('ins-open', S.ins || !!S.lab);
    app.classList.toggle('drawer-open', !!S.drawer);
    app.classList.toggle('touring', !!S.tour);
    ins.hidden = !S.ins;
    labEl.hidden = !S.lab;
    $('#drawer').hidden = !S.drawer;
    for (const t of ['tours', 'parts']) $('#b-' + t).setAttribute('aria-expanded', String(!!S.drawer && S.tab === t));
    $('#b-labs').setAttribute('aria-expanded', String(!!S.lab));
    syncTraffic();
    G?.updateOffset();
  }

  /* ------------------------------------------------------------ selection and inspector */
  function select(id, o = {}) {
    if (!PARTS[id]) return;
    const prev = S.sel; S.sel = id;
    if (G) { if (prev && prev !== id) G.emph(prev); G.emph(id); }
    if (narrow() && S.drawer) S.drawer = false;
    if (S.lab) { S.lab = null; resetTank(); }
    S.ins = true; renderInspector(); setPanels(); labelClasses(); markIndex();
    if (G) {
      if (o.fly !== false) G.flyTo(id);
      if (isWf(id)) { G.aim(id); G.showRoute(id); } else if (!S.tour) { G.hideRoute(); }
    }
    setHash(S.tour ? S.tour.id : id);
  }
  function deselect() {
    const prev = S.sel; S.sel = null; S.ins = false;
    if (G && prev) { G.emph(prev); if (!S.tour) { G.hideRoute(); G.unaim(); } }
    setPanels(); labelClasses(); markIndex();
    if (!S.tour && !S.lab) setHash('');
  }

  const X_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>';
  function renderInspector() {
    const id = S.sel; if (!id) return;
    const p = PARTS[id], wf = isWf(id);
    const kc = wf ? 'k-lane' : p.kind === 'AI concept' ? 'k-ai' : '';
    const sec = (h, body) => (body ? `<h3>${h}</h3>${body}` : '');
    let h = `<div class="ins-head"><div class="meta"><span class="pill ${kc}">${frameSVG(frameOf(p))}${esc(p.kind)}</span><span class="pill">${esc(wf ? FAMILIES[p.family].name : ZONES[p.zone].name)}</span>`;
    if (wf) h += `<span class="pill">${esc(TIER[p.tier])}</span>`;
    if (p.preview) h += `<span class="pill k-prev">Feature Forge preview</span>`;
    h += `</div><button class="tb icon close" data-act="close" aria-label="Close details">${X_SVG}</button>`;
    h += `<h2>${wf ? `<code>${esc(cmd(p.cmd))}</code>` : esc(p.name)}</h2><p class="tag">${fmt(p.tagline)}</p>`;
    if (wf && p.args) h += `<p class="tag" style="font-size:13.5px;color:var(--muted)">Arguments: <code>${esc(p.args)}</code></p>`;
    if (omitted(id)) h += `<p class="note">${esc(HOSTS[S.host].name)} does not ship this command.</p>`;
    h += `<div class="actions">`;
    if (wf && p.route) h += `<button class="btn primary" data-act="run"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>Run this lane</button>`;
    h += `${G ? '<button class="btn ghost" data-act="fly">Fly closer</button>' : ''}${canSay ? '<button class="btn ghost" data-act="say" aria-pressed="false">Read aloud</button>' : ''}</div></div><div class="ins-body">`;
    if (SIMPLE[id]) h += sec('In plain terms', `<p class="plain">${fmt(SIMPLE[id])}</p>`);
    h += sec(SIMPLE[id] ? 'In more detail' : 'What it is', `<p>${fmt(p.what)}</p>`);
    h += sec('In the machine', `<p>${fmt(p.machine)}</p>`);
    if (p.how) h += sec(wf ? 'Phases' : 'How it runs', `<ol>${p.how.map((s) => `<li>${fmt(s)}</li>`).join('')}</ol>`);
    if (wf && p.route) h += sec('Route through the machine', `<ol>${p.route.map(([at, st, t]) => `<li><button class="chip" data-go="${esc(at)}" style="margin:2px 0">${pnameHTML(at)}</button> <span style="color:${STATES[st].color};font-size:12.5px;font-weight:700">${esc(STATES[st].label)}</span><br>${fmt(t)}</li>`).join('')}</ol>`);
    if (p.stops) h += `<div class="stops">${sec('Gates and stops', `<p>${fmt(p.stops)}</p>`)}</div>`;
    if (p.produces) h += sec('Produces', `<p>${fmt(p.produces)}</p>`);
    if (p.watch) h += sec('Watch for', `<p>${fmt(p.watch)}</p>`);
    if (p.hooks) h += sec('Hook tags', `<div class="hooks">${p.hooks.map((x) => `<span>${esc(x)}</span>`).join('')}</div>`);
    if (p.aliases) h += sec('Other entry points', `<p>${fmt(p.aliases)}</p>`);
    if (p.related?.length) h += sec('Related parts', `<div class="chips">${p.related.map((r) => `<button class="chip" data-go="${esc(r)}">${pnameHTML(r)}</button>`).join('')}</div>`);
    if (p.source?.length) h += sec('Source in codeArbiter', `<ul class="src">${p.source.map((s) => `<li><a href="${esc(srcURL(s))}" target="_blank" rel="noopener">${esc(s)}</a></li>`).join('')}</ul>`);
    if (p.kind === 'AI concept') h += `<p class="note">General AI concept. Exact mechanisms vary by model and provider; the description covers how current large language models work in broad terms.</p>`;
    h += `</div>`;
    ins.innerHTML = h;
    glossify(ins.querySelector('.ins-body'));
  }
  ins.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.go) return select(b.dataset.go);
    const a = b.dataset.act;
    if (a === 'close') deselect();
    else if (a === 'fly' && S.sel) G?.flyTo(S.sel, true);
    else if (a === 'run' && S.sel) startTour(routeTour(S.sel));
    else if (a === 'say' && S.sel) {
      const on = b.getAttribute('aria-pressed') !== 'true';
      b.setAttribute('aria-pressed', String(on)); b.textContent = on ? 'Stop reading' : 'Read aloud';
      if (on) speak(`${plainText(pnameHTML(S.sel))}. ${plainText(fmt(SIMPLE[S.sel] || ''))} ${plainText(fmt(PARTS[S.sel].what))}`, () => { b.setAttribute('aria-pressed', 'false'); b.textContent = 'Read aloud'; });
      else hush();
    }
  });

  /* ------------------------------------------------------------ drawer: learn, tours, parts, glossary */
  const body = $('#drawer-body');
  function toggleDrawer(tab) {
    if (!tab || (S.drawer && S.tab === tab)) S.drawer = false;
    else { S.drawer = true; S.tab = tab; store.set('tab', tab); if (narrow()) { S.ins = false; if (S.lab) { S.lab = null; resetTank(); } } }
    store.set('drawer', S.drawer);
    renderDrawer(); setPanels();
  }
  function renderDrawer() {
    for (const t of TABS) $('#t-' + t).setAttribute('aria-selected', String(S.tab === t));
    const searching = S.tab === 'parts' || S.tab === 'glossary';
    $('#searchbox').hidden = !searching;
    if (searching) $('#q').placeholder = S.tab === 'parts' ? 'Search parts, commands, hook tags' : 'Search terms';
    if (S.tab === 'tours') {
      body.innerHTML = TOURS.map((t, i) => {
        const done = isDone('tour:' + t.id);
        return `<div class="tour${done ? ' done' : ''}"><h3>${esc(t.title)}${done ? ' <i class="tick" aria-label="(done)"></i>' : ''}</h3><p>${fmt(t.summary)}</p><div class="row"><span>${t.steps.length} stops</span><button class="btn ${i === 0 && !done ? 'primary' : ''}" data-tour="${esc(t.id)}">Start</button></div></div>`;
      }).join('') + `<p class="note">Every lane also has its own run. Select a lane on the outer ring and press Run, or pick one under Parts.</p>`;
    } else if (S.tab === 'parts') renderParts();
    else renderGlossary();
  }
  function renderParts() {
    const words = $('#q').value.toLowerCase().split(/\s+/).filter(Boolean);
    const hit = (id) => {
      if (!words.length) return true;
      const p = PARTS[id];
      const hay = [pname(id), p.name, p.cmd, p.tagline, p.what, SIMPLE[id], p.kind, (p.hooks || []).join(' '), p.family && FAMILIES[p.family].name].join(' ').toLowerCase();
      return words.every((w) => hay.includes(w));
    };
    const item = (id) => `<button class="item${omitted(id) ? ' dim' : ''}" data-id="${esc(id)}"${id === S.sel ? ' aria-current="true"' : ''}><b>${frameSVG(frameOf(PARTS[id]))}${pnameHTML(id)}</b><span>${fmt(PARTS[id].tagline)}</span></button>`;
    let h = '', n = 0;
    for (const z of ZONE_ORDER) {
      if (z === 'lanes') {
        for (const [fam, cmds] of LANE_ORDER) {
          const ids = cmds.map((c) => 'ca-' + c).filter(hit);
          if (!ids.length) continue;
          n += ids.length;
          h += `<div class="grp"><span>${esc(FAMILIES[fam].name)} lanes</span><span>${ids.length}</span></div>` + ids.map(item).join('');
        }
        continue;
      }
      const ids = Object.keys(PARTS).filter((id) => PARTS[id].zone === z && hit(id));
      if (!ids.length) continue;
      n += ids.length;
      h += `<div class="grp"><span>${esc(ZONES[z].name)}</span><span>${ids.length}</span></div>` + ids.map(item).join('');
    }
    body.innerHTML = n ? h : `<p class="note">No part matches “${esc($('#q').value)}”. Try a command name such as <code>commit</code>, a hook tag such as <code>H-02</code>, or a concept such as <code>attention</code>.</p>`;
  }
  function renderGlossary() {
    const words = $('#q').value.toLowerCase().split(/\s+/).filter(Boolean);
    const list = GLOSSARY.map((g, i) => [g, i])
      .filter(([g]) => !words.length || words.every((w) => `${g[0]} ${g[1].join(' ')} ${g[2]}`.toLowerCase().includes(w)))
      .sort((a, b) => a[0][0].localeCompare(b[0][0]));
    body.innerHTML = list.length
      ? `<p class="gl-intro">${GLOSSARY.length} terms in plain language.</p><dl class="gloss">${list.map(([g]) => `<div class="gi"><dt>${esc(g[0])}</dt><dd>${fmt(g[2])}${g[3] && PARTS[g[3]] ? ` <button class="linkbtn" data-id="${esc(g[3])}">Show in the machine</button>` : ''}</dd></div>`).join('')}</dl>`
      : `<p class="note">No term matches “${esc($('#q').value)}”.</p>`;
  }
  function markIndex() { if (S.drawer && S.tab === 'parts') body.querySelectorAll('.item').forEach((b) => b.toggleAttribute('aria-current', b.dataset.id === S.sel)); }
  body.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.tour) startTour(TOURS.find((t) => t.id === b.dataset.tour));
    else if (b.dataset.id) select(b.dataset.id);
  });
  $('#q').addEventListener('input', () => (S.tab === 'parts' ? renderParts() : renderGlossary()));
  for (const t of TABS) $('#t-' + t).addEventListener('click', () => { S.tab = t; store.set('tab', t); renderDrawer(); setPanels(); });
  for (const t of ['tours', 'parts']) $('#b-' + t).addEventListener('click', () => toggleDrawer(t));

  /* ------------------------------------------------------------ labs */
  const labs = createLabs({
    el: labEl, esc, fmt, glossify, isDone, markDone, pnameHTML, api3d, has3d: !!G,
    playFault(f) { startTour(faultTour(f), { fromLab: true }); },
    onClose: closeLab,
    onOpen(lab) { setHash('lab-' + lab); if (lab !== 'context') resetTank(); },
  });
  function clearSelection() { if (S.sel) { const p = S.sel; S.sel = null; G?.emph(p); if (!S.tour) { G?.hideRoute(); G?.unaim(); } labelClasses(); } }
  function openLab(id) {
    clearSelection();
    S.ins = false;
    if (narrow()) S.drawer = false;
    S.lab = id; labs.open(id);
    setPanels();
    setHash('lab-' + id);
    if (id !== 'context') resetTank();
    labEl.querySelector('[aria-selected="true"]')?.focus({ preventScroll: true });
  }
  function closeLab() {
    if (!S.lab) return;
    S.lab = null; resetTank(); hush();
    setPanels();
    setHash(S.tour ? S.tour.id : S.sel || '');
    $('#b-labs').focus({ preventScroll: true });
  }
  $('#b-labs').addEventListener('click', () => { if (S.lab) closeLab(); else openLab(labs.lab || 'faults'); });

  /* ------------------------------------------------------------ speech */
  const canSay = 'speechSynthesis' in window && typeof SpeechSynthesisUtterance === 'function';
  let sayId = 0;
  function speak(text, onend) {
    if (!canSay) return;
    const id = ++sayId;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.rate = 1;
      u.onend = () => { if (id === sayId) onend?.(); };
      speechSynthesis.speak(u);
    } catch { /* speech unavailable */ }
  }
  function hush() { sayId++; if (canSay) { try { speechSynthesis.cancel(); } catch { /* ignore */ } } }

  /* ------------------------------------------------------------ tours */
  let autoT = null;
  const fxTs = [];
  const fxLater = (fn) => fxTs.push(setT(fn, S.motion ? 750 : 0));
  function routeTour(id) {
    const p = PARTS[id];
    return { id: 'run-' + id, title: 'Run', route: id, steps: p.route.map(([at, state, text]) => ({ at, state, text })) };
  }
  const faultTour = (f) => (f.ref ? TOURS.find((t) => t.id === f.id) : { id: f.id, title: 'Break it: ' + f.title, steps: f.steps, fault: true });
  function startTour(t, o = {}) {
    if (!t) return;
    if (S.intro) closeIntro();
    endStep();
    S.tour = t; S.step = 0; S.auto = false; S.returnLab = o.fromLab ? 'faults' : null;
    if (narrow()) { S.drawer = false; if (S.lab) { S.lab = null; } }
    S.ins = false;
    if (S.sel) { const prev = S.sel; S.sel = null; G?.emph(prev); }
    if (G) { G.hideRoute(); if (t.route) G.aim(t.route); }
    setPanels();
    $('#player').hidden = false;
    goStep(0);
    setHash(t.id);
    if (!o.fromHash) $('#pl-next').focus({ preventScroll: true });
  }
  function endStep() {
    clearTimeout(autoT); fxTs.splice(0).forEach(clearTimeout); hush();
    if (!G || !S.tour) return;
    const prev = S.tourAt; S.tourAt = null;
    if (prev) { G.lamp(prev, null); G.emph(prev); G.fx.holdGate(prev, false); }
    G.clearFlows();
  }
  const DEMO_DIST = [{ label: 'pass', p: 0.48 }, { label: 'fail', p: 0.16 }, { label: 'are', p: 0.1 }, { label: 'should', p: 0.07 }, { label: 'still', p: 0.06 }, { label: '', p: 0.13, other: true }];
  // A state change shows as a floating verdict carrying the hook tag the step names, so the rule is always visible.
  // Blocks at the shell or write gate also print a ledger line, as block() appends one to gate-events.log.
  const TAGKIND = { block: 'block', stop: 'block', fail: 'block', pass: 'pass', gate: 'remind', ask: 'ask', preview: 'info' };
  function stateFx(id, s, st) {
    if (!fxOK() || !s || s === 'run') return;
    const fx = G.fx;
    if (s === 'block') fx.slam(id, true);
    else if (s === 'stop' || s === 'fail') fx.ripple(id, C.red);
    else if (s === 'pass') fx.ripple(id, C.green);
    else if (s === 'gate' || s === 'ask') fx.ripple(id, C.gold);
    else if (s === 'preview') fx.ripple(id, C.orange);
    const tagM = `${st?.title || ''} ${st?.text || ''}`.match(/\b(H-\d{2}[a-z]?)\b/);
    // "passed" is a verdict only where something is actually checked
    const checks = ['Enforcement', 'Lane', 'Agent', 'Skill'].includes(PARTS[id]?.kind) || ['remote-ci', 'receipts', 'git-hooks'].includes(id);
    if (s !== 'pass' || checks) G.story.tag(id, TAGKIND[s] || 'info', `${esc(STATES[s].label)}${tagM ? ` <b>${tagM[1]}</b>` : ''}`, { life: 4.5 });
    if (s === 'block' && tagM && (id === 'guard-bash' || id === 'guard-write')) G.story.ledger(id, tagM[1], id === 'guard-write' ? 'pre-write.py' : 'pre-bash.py');
  }
  function goStep(i) {
    const t = S.tour; if (!t) return;
    endStep();
    S.step = clamp(i, 0, t.steps.length - 1);
    const st = t.steps[S.step], prev = S.step > 0 ? t.steps[S.step - 1] : null;
    S.tourAt = st.at || null;
    if (G) {
      if (st.view) G.preset(st.view); else if (st.at) G.flyTo(st.at);
      if (st.at) {
        G.emph(st.at); G.lamp(st.at, st.state || 'run');
        G.fx.holdGate(st.at, true);
        // a step that sends a live tool call lets the call itself show the verdict when it reaches the gate
        if (!/(^|\|)call:/.test(st.fx || '')) fxLater(() => stateFx(st.at, st.state, st));
      }
      if (prev?.at && st.at && prev.at !== st.at) G.flow(prev.at, st.at, STATES[st.state || 'run'].color);
      G.story.cancel();
      if (st.fx) String(st.fx).split('|').forEach((f) => runFx(f, st));
      if (st.at && isWf(st.at) && !st.fx) G.aim(st.at);
    }
    renderPlayer(); labelClasses();
    if (S.step === t.steps.length - 1) markDone('tour:' + t.id);
    if (S.say) speak(`${plainText(stepTitle(st))}. ${plainText(fmt(st.text))}`, () => { if (S.auto && S.tour === t) { clearTimeout(autoT); autoT = setT(advance, 900); } });
    if (S.auto) scheduleAuto();
  }
  function runFx(fx, st) {
    const ci = fx.indexOf(':'), k = ci < 0 ? fx : fx.slice(0, ci), v = ci < 0 ? '' : fx.slice(ci + 1);
    const api = (id) => G.M.parts.get(id)?.api || {};
    // live demonstrations: input:<text> tokenizes text, gen:<text> samples it token by token,
    // call:<tool>|<verdict>|<tag>|<cmd> sends a labelled tool call to its gate
    if (k === 'input') { if (S.motion) fxLater(() => G.story.playInput(v, 'pa')); }
    else if (k === 'say') { if (S.motion) fxLater(() => G.story.playInput(v, 'op')); }
    else if (k === 'ring') { if (S.motion) fxLater(() => G.story.playInput(v, 'ring')); }
    else if (k === 'gen') { if (S.motion) fxLater(() => G.story.playGen(v)); }
    else if (k === 'pass') { [0, 700, 1400].forEach((ms) => setT(() => api('transformer').pulse?.(), ms + 400)); G.fx.pulseStream(); }
    else if (k === 'dist') G.story.showDist(DEMO_DIST, -1, 1);
    else if (k === 'spin') { G.story.showDist(DEMO_DIST, -1, 1); const i = api('sampler').pick?.() ?? 0; fxLater(() => G.story.spin(i, DEMO_DIST[i].label)); }
    else if (k === 'guard') { if (S.motion) fxLater(() => G.story.playGuard(v, simulateGuard(v, { branch: 'feature', secret: false }))); }
    else if (k === 'print') fxLater(() => api('audit-ledger').print?.());
    else if (k === 'call') {
      const [tool, verdict, tagName, ...rest] = v.split(';');
      // the message the gate prints for this tool: a Write to an ADR is refused by pre-write.py, a shell write by pre-bash.py
      const msgKey = tool === 'write' && tagName === 'H-11' ? 'H-11w' : { 'H-01': 'H-01p', 'H-02': 'H-02', 'H-03': 'H-03a', 'H-05': 'H-05', 'H-11': 'H-11', 'H-14': 'H-14', 'H-18': 'H-18', 'H-20': 'H-20c', 'H-10b': 'H-10b' }[tagName];
      if (S.motion) fxLater(() => G.story.playCall({ tool, verdict, tag: tagName, cmd: rest.join(';'), msg: msgKey ? MSG[msgKey]('main') : '' }, { shake: true, from: 'parser' }));
      else if (verdict === 'block') { api(tool === 'write' ? 'guard-write' : 'guard-bash').block?.(); }
    }
    else if (k === 'sample') { api('sampler').sample?.(); G.fx.pulseStream(); }
    else if (k === 'compact') { api('compaction').compact?.(); setT(() => { if (api('context-window').compactBands) api('context-window').compactBands(); else api('context-window').setFill?.(0.4); G.story.contextChanged(); }, 650); }
    else if (k === 'fill') api('context-window').setFill?.(parseFloat(v));
    else if (k === 'route') G.aim(v);
    else if (k === 'block') { if (!(st.at === v && st.state === 'block')) { api(v).block?.(); fxLater(() => { if (fxOK()) G.fx.slam(v, true); }); } }
    else if (k === 'open') api(v).open?.();
    G.settle();
  }
  function stopTour(o = {}) {
    if (!S.tour) return;
    endStep();
    S.tour = null; S.auto = false;
    $('#player').hidden = true;
    if (G) { G.unaim(); G.M.parts.get('context-window')?.api.reset?.(); ['guard-bash', 'guard-write'].forEach((g) => G.M.parts.get(g)?.api.idle?.()); G.settle(); }
    const back = o.back && S.returnLab;
    S.returnLab = null;
    setPanels(); labelClasses();
    if (back && !S.lab) openLab('faults');
    else { if (back && S.lab) labs.render(); setHash(S.lab ? 'lab-' + labs.lab : S.sel || ''); }
  }
  const stepTitle = (st) => (st.title ? fmt(st.title) : pnameHTML(st.at));
  function renderPlayer() {
    const t = S.tour, st = t.steps[S.step], n = t.steps.length;
    const title = t.route ? `Run: ${cmd(PARTS[t.route].cmd)}` : t.title;
    $('#pl-ttl').textContent = `${title} · stop ${S.step + 1} of ${n}`;
    const s = st.state && st.state !== 'run' ? STATES[st.state] : null;
    $('#pl-h').innerHTML = `<span>${stepTitle(st)}</span>${s ? `<span class="st" style="color:${s.color}">${esc(s.label)}</span>` : ''}`;
    $('#pl-t').innerHTML = fmt(st.text);
    glossify($('#pl-t'));
    $('#pl-prev').disabled = S.step === 0;
    $('#pl-nl').textContent = S.step === n - 1 ? (S.returnLab ? 'Back to Break it' : 'Finish') : 'Next';
    $('#pl-more').hidden = !st.at;
    $('#pl-auto').setAttribute('aria-pressed', String(S.auto));
    $('#pl-auto').textContent = S.auto ? 'Pause' : 'Autoplay';
    $('#pl-say').setAttribute('aria-pressed', String(S.say));
    $('#pl-bar').style.width = ((S.step + 1) / n) * 100 + '%';
  }
  function scheduleAuto() {
    clearTimeout(autoT);
    const st = S.tour.steps[S.step];
    const words = (st.text || '').split(/\s+/).length;
    // with reading aloud, the end of speech advances the tour; this timer is only a safety net
    autoT = setT(advance, S.say && canSay ? clamp(words * 600, 9000, 45000) : clamp(words * 290, 4200, 14000));
  }
  const advance = () => { if (!S.tour) return; if (S.step < S.tour.steps.length - 1) goStep(S.step + 1); else { S.auto = false; renderPlayer(); } };
  const next = () => { if (!S.tour) return; if (S.step < S.tour.steps.length - 1) goStep(S.step + 1); else stopTour({ back: true }); };
  const prev = () => { if (S.tour && S.step > 0) goStep(S.step - 1); };
  const toggleAuto = () => { if (!S.tour) return; S.auto = !S.auto; renderPlayer(); if (S.auto) scheduleAuto(); else clearTimeout(autoT); };
  $('#pl-next').addEventListener('click', next);
  $('#pl-prev').addEventListener('click', prev);
  $('#pl-auto').addEventListener('click', toggleAuto);
  $('#pl-x').addEventListener('click', () => stopTour({ back: true }));
  $('#pl-more').addEventListener('click', () => { const st = S.tour?.steps[S.step]; if (st?.at) { S.auto = false; clearTimeout(autoT); renderPlayer(); select(st.at, { fly: false }); } });
  if (canSay) {
    $('#pl-say').addEventListener('click', () => {
      S.say = !S.say; renderPlayer();
      if (S.say && S.tour) { const st = S.tour.steps[S.step]; speak(`${plainText(stepTitle(st))}. ${plainText(fmt(st.text))}`, () => { if (S.auto && S.tour) { clearTimeout(autoT); autoT = setT(advance, 900); } }); if (S.auto) scheduleAuto(); }
      else hush();
    });
  } else $('#pl-say').hidden = true;

  /* ------------------------------------------------------------ toolbar */
  const hostseg = $('#hostseg');
  hostseg.innerHTML = Object.entries(HOSTS).map(([k, h]) => `<button data-host="${k}" aria-pressed="${k === S.host}" title="Show commands as ${esc(h.name)} spells them">${esc(h.name.replace(' (preview)', ''))}</button>`).join('');
  hostseg.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) setHost(b.dataset.host); });
  const hostsel = $('#hostsel');
  hostsel.innerHTML = Object.entries(HOSTS).map(([k, h]) => `<option value="${k}"${k === S.host ? ' selected' : ''}>${esc(h.name.replace(/ \(preview\)| Code| CLI/g, ''))}</option>`).join('');
  hostsel.addEventListener('change', () => setHost(hostsel.value));
  function setHost(h) {
    S.host = h; store.set('host', h);
    hostseg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.host === h)));
    hostsel.value = h;
    if (G) {
      for (const [id, L] of G.labels) if (isWf(id)) L.el.querySelector('.nm').textContent = pname(id);
      G.resetLabelSizes();
      G.M.parts.get('hosts')?.api.setHost?.(Object.keys(HOSTS).indexOf(h));
      G.M.parts.get('ca-statusline')?.api.setAvailable?.(!HOSTS[h].omits.includes('statusline'));
    }
    labelClasses();
    if (S.ins) renderInspector();
    if (S.drawer) renderDrawer();
    if (S.tour) renderPlayer();
    if (S.lab) labs.render();
  }
  const setToggle = (btn, on) => btn.setAttribute('aria-pressed', String(on));
  function toggleLabels() { S.labels = !S.labels; store.set('labels', S.labels); setToggle($('#b-labels'), S.labels); setToggle($('#h-labels'), S.labels); G?.lod(); invalidate(); }
  function toggleMotion() {
    S.motion = !S.motion; store.set('motion', S.motion);
    setToggle($('#b-motion'), S.motion); setToggle($('#h-motion'), S.motion);
    app.classList.toggle('still', !S.motion);
    if (!S.motion && S.intro === 'play') endIntro(true);
    if (!S.motion) G?.fx.finishBoot();
    syncTraffic();
    settle = 4; G?.updateOffset(); invalidate();
  }
  function resetView() { S.iso = null; renderZonebar(); G?.applyIso(); G?.overview(); }
  $('#b-labels').addEventListener('click', toggleLabels);
  $('#b-motion').addEventListener('click', toggleMotion);
  $('#b-reset').addEventListener('click', resetView);
  app.classList.toggle('still', !S.motion);
  setToggle($('#b-labels'), S.labels); setToggle($('#b-motion'), S.motion); setToggle($('#h-labels'), S.labels); setToggle($('#h-motion'), S.motion);
  $('#h-labels').addEventListener('click', toggleLabels);
  $('#h-motion').addEventListener('click', toggleMotion);
  $('#h-reset').addEventListener('click', () => { closeHelp(); resetView(); });
  $('#h-key').addEventListener('click', () => { closeHelp(); openKey($('#b-help')); });

  /* zone bar and legend */
  const ZFLY = { model: 'model', harness: 'harness', guards: 'guards', skills: 'skills', lanes: 'lanes', record: 'vault', world: 'repo', you: 'operator', outside: 'network' };
  function renderZonebar() {
    $('#zonebar').innerHTML = `<button data-z="" aria-pressed="${!S.iso}">All</button>` + ['model', 'harness', 'guards', 'skills', 'lanes', 'record', 'world', 'you', 'outside'].map((z) => `<button data-z="${z}" aria-pressed="${S.iso === z}">${esc(ZONES[z].name)}</button>`).join('');
  }
  $('#zonebar').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    const z = b.dataset.z || null;
    S.iso = S.iso === z ? null : z;
    renderZonebar();
    if (G) { G.applyIso(); if (S.iso) { const f = ZFLY[S.iso]; if (PARTS[f]) G.flyTo(f); else G.preset(f); } }
  });
  renderZonebar();
  const COLORS = [['#f0b92f', 'Gate or decision', 'Something waits at a check, or on you.'], ['#58d68d', 'Verified or passed', 'Allowed, or proven with current evidence.'], ['#ff7b72', 'Blocked or failing', 'Refused, or a test failing on purpose (red before green).'], ['#7ab7ff', 'Model and agent activity', 'Work in progress: tokens, tool calls, results.'], ['#ed946d', 'Feature Forge preview', 'Shipping but opt-in until it earns stable status.']];
  $('#legend').innerHTML = COLORS.map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join('') + '<button class="linkbtn kbtn" data-act="key">How to read the machine</button>';
  // the key: shape, colour and motion each carry one meaning everywhere in the machine
  $('#key-shapes').innerHTML = FRAME_KEY.map(([sh, n, d]) => `<div class="krow"><span class="ks">${frameSVG(sh)}</span><div><b>${esc(n)}</b><span>${esc(d)}</span></div></div>`).join('');
  $('#key-colors').innerHTML = COLORS.map(([c, n, d]) => `<div class="krow"><span class="ks"><i class="dot" style="background:${c}"></i></span><div><b>${esc(n)}</b><span>${esc(d)}</span></div></div>`).join('');
  $('#key-motion').innerHTML = MOTION_KEY.map(([cls, n, d]) => `<div class="krow"><span class="ks ${cls}" aria-hidden="true"></span><div><b>${esc(n)}</b><span>${esc(d)}</span></div></div>`).join('');
  const keyEl = $('#key');
  let keyFrom = null;
  function openKey(from) { keyFrom = from || root.activeElement; keyEl.hidden = false; $('#key-x').focus(); }
  function closeKey() { keyEl.hidden = true; keyFrom?.focus?.({ preventScroll: true }); }
  $('#legend').addEventListener('click', (e) => { if (e.target.closest('[data-act="key"]')) openKey(e.target); });
  $('#key-x').addEventListener('click', closeKey);
  keyEl.addEventListener('click', (e) => { if (e.target === keyEl) closeKey(); });

  /* help */
  const help = $('#help');
  const openHelp = () => { help.hidden = false; $('#help-x').focus(); };
  function closeHelp() { help.hidden = true; $('#b-help').focus({ preventScroll: true }); }
  $('#b-help').addEventListener('click', openHelp);
  $('#help-x').addEventListener('click', closeHelp);
  help.addEventListener('click', (e) => { if (e.target === help) closeHelp(); });
  $('#help-src').innerHTML = `Checked against ${esc(META.version)} when this page was built. Gate IDs, block messages, command names, lanes and host spellings come from the plugin sources; each part lists the files it describes. <a href="${esc(META.repo)}">github.com/arbiterForge/codeArbiter</a>`;
  function renderQualitySeg() {
    const q = $('#h-quality');
    q.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.q === S.quality)));
    $('#h-qnote').textContent = S.quality === 'auto' ? (autoLow ? 'Auto chose Light on this device.' : 'Auto: rich effects unless this device runs slowly.') : '';
  }
  $('#h-quality').addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; S.quality = b.dataset.q; store.set('quality', S.quality); applyQuality(); });
  renderQualitySeg();
  $('#h-intro').addEventListener('click', () => { closeHelp(); if (S.tour) stopTour(); if (S.lab) closeLab(); deselect(); S.drawer = false; renderDrawer(); setPanels(); startIntro(true); });
  if (!G) { $('#h-intro').hidden = true; $('#h-quality').closest('.hrow').hidden = true; }

  /* toast */
  let toastT = null;
  function toast(msg, ms = 4600) {
    const t = $('#toast');
    t.textContent = msg; t.hidden = false;
    requestAnimationFrame(() => t.classList.add('on'));
    clearTimeout(toastT);
    toastT = setT(() => { t.classList.remove('on'); setT(() => { t.hidden = true; }, 350); }, ms);
  }

  /* ------------------------------------------------------------ first-visit intro */
  const introEl = $('#intro');
  const introTimers = [];
  const later = (ms, fn) => introTimers.push(setT(fn, ms));
  const CAPS = ['Every AI coding agent has a model at its heart.', 'It does not look anything up. It predicts the next word, over and over.', 'Give it tools, and every prediction can become an action on your code.', 'codeArbiter is the machinery that decides which actions are allowed.'];
  $('#intro-lede').textContent = CAPS.join(' ');
  function startIntro(replay) {
    if (!G || !S.motion) { showWelcome(); return; }
    S.intro = 'play';
    app.classList.add('intro', 'booting');
    introEl.hidden = false; $('#intro-card').hidden = true; $('#intro-skip').hidden = false; $('#intro-lede').hidden = true;
    syncTraffic();
    const fx = G.fx, part = (id) => G.M.parts.get(id);
    const cap = $('#intro-cap');
    const caption = (i) => { cap.classList.remove('on'); later(420, () => { cap.textContent = CAPS[i]; cap.classList.add('on'); }); };
    G.shot([0, 11, 0], -32, 3, 36, 0);
    fx.boot(null, replay ? 1.15 : 1);
    G.shot([0, 14, 0], 16, 13, 27, 4.6);
    caption(0);
    later(4400, () => { caption(1); G.shot([0, 19.5, 0], 38, 24, 17, 2.6); });
    // the wheel picks each next word; the tokens ride the loop down into the context window
    later(4900, () => G.story.playGen('The tests pass.'));
    later(8700, () => { caption(2); const c = polar(20, 82, 2); G.shot([c.x, c.y, c.z], 60, 30, 44, 2.6); });
    // labelled tool calls: what each one does is written on it
    later(9300, () => G.story.playCall({ tool: 'read', cmd: 'src/auth/session.ts', verdict: 'allow' }, { speed: 32 }));
    later(10100, () => G.story.playCall({ tool: 'bash', cmd: 'npm test', verdict: 'allow' }, { speed: 32 }));
    later(10900, () => G.story.playCall({ tool: 'write', cmd: 'src/auth/session.ts', verdict: 'allow' }, { speed: 32 }));
    later(12800, () => { caption(3); const c = part('guard-bash').sphere.center; G.shot([c.x, 2.4, c.z], 100, 26, 20, 2.2); });
    later(13500, () => G.story.playCall({ tool: 'bash', cmd: 'git push --force', verdict: 'block', tag: 'H-02', msg: MSG['H-02']() }, { speed: 20, shake: true }));
    later(17600, () => { cap.classList.remove('on'); G.overview(); });
    later(18900, () => endIntro(true));
  }
  function showWelcome() {
    S.intro = 'card';
    app.classList.add('intro');
    introEl.hidden = false; $('#intro-skip').hidden = true; $('#intro-lede').hidden = false; $('#intro-card').hidden = false;
    syncTraffic();
    $('#intro-learn').focus({ preventScroll: true });
  }
  function endIntro(card) {
    introTimers.splice(0).forEach(clearTimeout);
    G?.story.cancel();
    G?.fx.finishBoot();
    app.classList.remove('booting');
    $('#intro-skip').hidden = true;
    $('#intro-cap').classList.remove('on');
    if (card) { S.intro = 'card'; $('#intro-card').hidden = false; G?.overview(); $('#intro-learn').focus({ preventScroll: true }); }
    else closeIntro();
  }
  function closeIntro() {
    if (!S.intro) return;
    introTimers.splice(0).forEach(clearTimeout);
    G?.fx.finishBoot();
    introEl.hidden = true; S.intro = null;
    app.classList.remove('intro', 'booting');
    store.set('introSeen', true);
    syncTraffic(); G?.updateOffset();
  }
  $('#intro-skip').addEventListener('click', () => endIntro(true));
  $('#intro-learn').addEventListener('click', () => { closeIntro(); toggleDrawer('tours'); });
  $('#intro-explore').addEventListener('click', () => { closeIntro(); G?.overview(); });

  /* keyboard */
  // Keys work while focus is anywhere in the viewer, including the stage itself; the event's own target
  // comes from its composed path, because the shadow boundary retargets it to the host.
  listen(hostEl, 'keydown', (e) => {
    const target = e.composedPath()[0] || e.target;
    const tag = (target.tagName || '').toLowerCase();
    const typing = tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
    if (e.key === 'Escape') {
      if (!pop.hidden) { const f = popFor; hidePop(); f?.focus({ preventScroll: true }); }
      else if (!keyEl.hidden) closeKey();
      else if (!help.hidden) closeHelp();
      else if (S.intro === 'play') endIntro(true);
      else if (S.intro === 'card') closeIntro();
      else if (typing) target.blur();
      else if (S.tour) stopTour({ back: true });
      else if (S.lab) closeLab();
      else if (S.ins) deselect();
      else if (S.drawer) toggleDrawer(null);
      return;
    }
    if (typing || e.metaKey || e.ctrlKey || e.altKey || S.intro) return;
    const onPage = target === hostEl || target === stage || target === app || target === G?.canvas;
    switch (e.key) {
      case '/': e.preventDefault(); if (!(S.drawer && S.tab === 'parts')) toggleDrawer('parts'); $('#q').focus(); break;
      case 't': case 'T': toggleDrawer('tours'); break;
      case 'r': case 'R': resetView(); break;
      case 'l': case 'L': toggleLabels(); break;
      case 'm': case 'M': toggleMotion(); break;
      case '?': openHelp(); break;
      case 'f': case 'F': if (S.sel) G?.flyTo(S.sel, true); break;
      case 'ArrowRight': if (S.tour) { e.preventDefault(); next(); } break;
      case 'ArrowLeft': if (S.tour) { e.preventDefault(); prev(); } break;
      case ' ': if (S.tour && onPage) { e.preventDefault(); toggleAuto(); } break;
      default:
    }
  });

  /* routes: the page asks for a part, tour, failure scenario, lane run or lab by id (no address-bar changes) */
  function setHash(h) { S.hash = h; options.onRoute?.(h); }
  function routeHash(h = '') {
    if (!h || h === S.hash) return;
    S.hash = h;
    const t = TOURS.find((x) => x.id === h);
    if (t) return startTour(t, { fromHash: true });
    const f = FAULTS.find((x) => x.id === h && !x.ref);
    if (f) return startTour(faultTour(f), { fromHash: true });
    if (h.startsWith('run-') && PARTS[h.slice(4)]?.route) return startTour(routeTour(h.slice(4)), { fromHash: true });
    if (h.startsWith('lab-') && LABS[h.slice(4)]) { if (S.tour) stopTour(); return openLab(h.slice(4)); }
    const part = h.startsWith('part-') ? h.slice(5) : h;
    if (PARTS[part]) { if (S.tour) stopTour(); select(part); }
  }

  /* start */
  if (G) { G.M.parts.get('hosts')?.api.setHost?.(Object.keys(HOSTS).indexOf(S.host)); G.M.parts.get('ca-statusline')?.api.setAvailable?.(!HOSTS[S.host].omits.includes('statusline')); }
  labelClasses();
  const linked = !!options.route;
  if (!G) { S.drawer = true; S.tab = 'parts'; }
  renderDrawer(); setPanels();
  routeHash(options.route || '');
  if (G && !linked && S.motion) {
    app.classList.add('booting');
    G.fx.boot(() => { app.classList.remove('booting'); for (const id of [S.sel, S.hov, S.tourAt]) if (id) G.emph(id); }, 1.9);
  }
  syncTraffic();
  requestAnimationFrame(() => requestAnimationFrame(() => $('#loading').classList.add('done')));

  /* page controls: the example session, full screen, and closing the viewer */
  $('#b-session').addEventListener('click', () => {
    S.session = !S.session;
    if (S.session && !S.motion) toggleMotion(); // asking for the session is asking for its motion
    syncTraffic();
    if (S.session) toast('Example session playing. It is scripted and slowed down.');
  });
  $('#b-full').addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else hostEl.requestFullscreen?.().catch(() => toast('Full screen is not available here.'));
  });
  listen(document, 'fullscreenchange', () => { setToggle($('#b-full'), document.fullscreenElement === hostEl); G?.resize?.(); });
  $('#b-close').addEventListener('click', () => options.onClose?.());

  return {
    /** Open a part, tour, failure scenario, lane run (run-ca-<command>) or lab (lab-<id>) by id. */
    route(id) { routeHash(id); },
    /** Start the scripted example session. */
    playSession() { S.session = true; if (!S.motion) toggleMotion(); syncTraffic(); },
    /** Release the WebGL context, listeners, timers, speech and the shadow content. */
    dispose() {
      ac.abort();
      for (const id of timers) clearTimeout(id);
      timers.clear();
      cancelAnimationFrame(rafId);
      resizeObs?.disconnect();
      hush();
      if (document.fullscreenElement === hostEl) document.exitFullscreen?.();
      if (G) {
        try { G.story?.cancel?.(); G.controls?.dispose?.(); G.renderer.dispose(); G.renderer.forceContextLoss(); } catch { /* already gone */ }
        if (window.__machine === G) delete window.__machine;
      }
      root.innerHTML = '<slot></slot>';
    },
  };
}
