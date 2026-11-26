// Scene construction for the codeArbiter machine view.
// Layout is concentric: model (r<10) > agent loop (r=17) > hook bus (r=22) > guard ring (r=27)
// > skills (r=36.5) > lanes (r=50) > record, repository, outside and the console (r>64).
// Angles are degrees clockwise from the front (+z) toward the right (+x).

import * as THREE from './three.js';
import { LANE_ORDER } from './content.js';

const rad = (d) => (d * Math.PI) / 180;
export const polar = (r, deg, y = 0) => new THREE.Vector3(r * Math.sin(rad(deg)), y, r * Math.cos(rad(deg)));
const V = (x, y, z) => new THREE.Vector3(x, y, z);

// The site's meaning tokens: gold for gates and decisions, green verified, red blocked, blue model and agent activity, orange preview.
export const C = { bg: 0x090d12, gold: 0xf0b92f, green: 0x58d68d, red: 0xff7b72, blue: 0x7ab7ff, orange: 0xed946d, ink: 0xc7d0da };

/* ---------------------------------------------------------------- materials */

const TEMPLATES = {
  steel: { color: 0x283544, metalness: 0.8, roughness: 0.42 },
  steel2: { color: 0x3a4d62, metalness: 0.74, roughness: 0.36 },
  trim: { color: 0x8d9db2, metalness: 0.92, roughness: 0.24 },
  dark: { color: 0x0d131a, metalness: 0.4, roughness: 0.7 },
  panel: { color: 0x131c27, metalness: 0.3, roughness: 0.7 },
  stone: { color: 0x3b4755, metalness: 0.08, roughness: 0.88 },
  paper: { color: 0xd8dee6, metalness: 0, roughness: 0.92 },
  ink: { color: 0xb9c4d1, metalness: 0.55, roughness: 0.38 },
  glass: { color: 0xa9d5ff, metalness: 0.05, roughness: 0.06, transparent: true, opacity: 0.17, depthWrite: false },
  screen: { color: 0x0a1520, metalness: 0.1, roughness: 0.45, emissive: 0x14304a, emissiveIntensity: 0.9 },
  gold: { color: 0xf0b92f, metalness: 0.86, roughness: 0.3, emissive: 0x9b6811, emissiveIntensity: 0.3 },
  blue: { color: 0x7cc4ff, metalness: 0.2, roughness: 0.4, emissive: 0x7cc4ff, emissiveIntensity: 1.1 },
  blueDim: { color: 0x2a5d88, metalness: 0.4, roughness: 0.45, emissive: 0x1b4a72, emissiveIntensity: 0.55 },
  blueprint: { color: 0x1d4f7c, metalness: 0.1, roughness: 0.7, emissive: 0x16426b, emissiveIntensity: 0.7 },
  red: { color: 0xff7b72, metalness: 0.3, roughness: 0.4, emissive: 0xff7b72, emissiveIntensity: 0.5 },
  green: { color: 0x58d68d, metalness: 0.3, roughness: 0.4, emissive: 0x58d68d, emissiveIntensity: 0.6 },
  orange: { color: 0xed946d, metalness: 0.55, roughness: 0.42, emissive: 0x7a3f25, emissiveIntensity: 0.45 },
  lampOff: { color: 0x3a4757, metalness: 0.3, roughness: 0.5, emissive: 0x000000, emissiveIntensity: 0 },
};

function makeMat(key) {
  const t = TEMPLATES[key];
  return new THREE.MeshStandardMaterial({ ...t });
}

function scope() {
  const cache = new Map();
  const list = [];
  const reg = (m) => { if (!list.includes(m)) list.push(m); return m; };
  return { list, reg, m: (k) => { if (!cache.has(k)) cache.set(k, reg(makeMat(k))); return cache.get(k); }, u: (k) => reg(makeMat(k)) };
}

let GLOW;
function glowTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const x = c.getContext('2d');
  const g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.22, 'rgba(255,255,255,0.6)');
  g.addColorStop(0.55, 'rgba(255,255,255,0.12)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g;
  x.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/* ---------------------------------------------------------------- geometry kit */

const GC = new Map();
const geo = (key, make) => { if (!GC.has(key)) GC.set(key, make()); return GC.get(key); };

function kit(g, S) {
  const M = (m) => (typeof m === 'string' ? S.m(m) : S.reg(m));
  const mesh = (geom, m, x, y, z) => { const o = new THREE.Mesh(geom, M(m)); o.position.set(x, y, z); g.add(o); return o; };
  const k = {
    g, S,
    sub(x = 0, y = 0, z = 0) { const c = new THREE.Group(); c.position.set(x, y, z); g.add(c); return kit(c, S); },
    box(w, h, d, m, x = 0, y = 0, z = 0, r = 0.1) {
      const rr = Math.max(0.001, Math.min(r, Math.min(w, h, d) / 2 - 0.002));
      return mesh(geo(`b${w}|${h}|${d}|${rr}`, () => new THREE.RoundedBoxGeometry(w, h, d, 2, rr)), m, x, y + h / 2, z);
    },
    cyl(r, h, m, x = 0, y = 0, z = 0, seg = 28, rt = r, open = false) {
      return mesh(geo(`c${r}|${h}|${seg}|${rt}|${open}`, () => new THREE.CylinderGeometry(rt, r, h, seg, 1, open)), m, x, y + h / 2, z);
    },
    rod(r, len, m, x, y, z, axis = 'x', seg = 16) {
      const o = mesh(geo(`c${r}|${len}|${seg}|${r}|false`, () => new THREE.CylinderGeometry(r, r, len, seg)), m, x, y, z);
      if (axis === 'x') o.rotation.z = Math.PI / 2; else if (axis === 'z') o.rotation.x = Math.PI / 2;
      return o;
    },
    tor(R, t, m, x = 0, y = 0, z = 0, rx = Math.PI / 2, arc = Math.PI * 2, seg = 48) {
      const o = mesh(geo(`t${R}|${t}|${arc}|${seg}`, () => new THREE.TorusGeometry(R, t, 10, seg, arc)), m, x, y, z);
      o.rotation.x = rx;
      return o;
    },
    sph(r, m, x = 0, y = 0, z = 0, seg = 20) {
      return mesh(geo(`s${r}|${seg}`, () => new THREE.SphereGeometry(r, seg, Math.max(8, (seg * 0.65) | 0))), m, x, y, z);
    },
    cone(r, h, m, x = 0, y = 0, z = 0, seg = 24) {
      return mesh(geo(`k${r}|${h}|${seg}`, () => new THREE.ConeGeometry(r, h, seg)), m, x, y + h / 2, z);
    },
    cap(r, m, x, y, z, open = 0.9) {
      return mesh(geo(`cap${r}|${open}`, () => new THREE.SphereGeometry(r, 28, 12, 0, Math.PI * 2, 0, open)), m, x, y, z);
    },
    tube(pts, r, m, seg = 64, closed = false) {
      const curve = new THREE.CatmullRomCurve3(pts, closed, 'centripetal');
      const o = mesh(new THREE.TubeGeometry(curve, seg, r, 10, closed), m, 0, 0, 0);
      o.userData.curve = curve;
      return o;
    },
    dyn(o) { o.userData.dyn = true; return o; },
    local(p) { g.updateMatrixWorld(true); return g.worldToLocal(p.clone()); },
    tubeAbs(pts, r, m, seg = 64) { return k.tube(pts.map((p) => k.local(p)), r, m, seg); },
    inst(geom, m, n) { const o = new THREE.InstancedMesh(geom, M(m), n); g.add(o); return o; },
    glow(color, size, x, y, z, op = 0.85) {
      const mat = S.reg(new THREE.SpriteMaterial({ map: GLOW, color, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false }));
      const sp = new THREE.Sprite(mat);
      sp.scale.set(size, size, 1);
      sp.position.set(x, y, z);
      sp.userData.nopick = true;
      g.add(sp);
      return sp;
    },
    lamp(color, x, y, z, r = 0.2, gs = 1.3, on = true) {
      const mat = S.reg(new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: on ? 1.5 : 0.08, roughness: 0.35 }));
      const s = k.sph(r, mat, x, y, z, 14);
      const gl = k.glow(color, gs, x, y, z, on ? 0.55 : 0);
      gl.visible = on;
      return { s, gl, mat, set(c, i = 1.5, o = 0.55) { mat.color.set(c); mat.emissive.set(c); mat.emissiveIntensity = i; gl.material.color.set(c); gl.material.opacity = o; gl.visible = o > 0 && !gl.userData.ghost; } };
    },
  };
  return k;
}

function sectorShape(r0, r1, a0, a1) {
  const s = new THREE.Shape();
  const p0 = rad(a0 - 90), p1 = rad(a1 - 90);
  s.absarc(0, 0, r1, p0, p1, false);
  s.absarc(0, 0, r0, p1, p0, true);
  return s;
}
function sectorGeo(r0, r1, a0, a1, h) {
  const g = new THREE.ExtrudeGeometry(sectorShape(r0, r1, a0, a1), { depth: h, bevelEnabled: false, curveSegments: Math.max(8, Math.ceil(Math.abs(a1 - a0) / 2)) });
  g.rotateX(-Math.PI / 2);
  return g;
}
function flatRing(r0, r1, a0 = 0, a1 = 360, seg = 200) {
  const g = new THREE.RingGeometry(r0, r1, seg, 1, rad(a0 - 90), rad(a1 - a0));
  g.rotateX(-Math.PI / 2);
  return g;
}

/* ---------------------------------------------------------------- layout */

export function laneAngles() {
  const out = {};
  let a = 24;
  LANE_ORDER.forEach(([, cmds], fi) => {
    if (fi > 0) a += 4.6;
    cmds.forEach((c, i) => { if (fi > 0 || i > 0) a += 10.6; out['ca-' + c] = a; });
  });
  return out;
}
const LA = laneAngles();
export const R = { loop: 17, bus: 22, wall: 27, skills: 36.5, lanes: 50 };

// [id] -> [radius, angle, y, facing] ; facing: 'out' (front to the outside), 'in' (front to the core), null (unrotated)
const PLACE = {
  weights: [0, 0, 0.9, null], transformer: [0, 0, 0.9, null], attention: [0, 0, 0.9, null], embedding: [0, 0, 0.9, null],
  tokenizer: [7.4, 0, 0.9, 'out'], 'context-window': [6.9, 73, 0.9, null], 'kv-cache': [6.9, -73, 0.9, 'out'],
  logits: [0, 0, 18.5, null], sampler: [0, 0, 20.1, null], autoregress: [0, 0, 0, null], reasoning: [5.4, 214, 17.6, null],
  router: [0, 0, 21.2, null],
  'agent-loop': [0, 0, 0, null], 'prompt-assembly': [17, 0, 0, 'out'], 'tool-parser': [17, 38, 0, 'out'],
  permissions: [15.0, 66, 0, 'out'], 'tool-router': [17, 80, 0, 'out'],
  'tool-read': [19.6, 61, 0, 'out'], 'tool-bash': [19.6, 72, 0, 'out'], 'tool-write': [19.6, 88, 0, 'out'], 'tool-mcp': [19.6, 109, 0, 'out'],
  'tool-results': [17.2, 121, 0, 'out'], 'hook-bus': [0, 0, 0, null], compaction: [17, 205, 0, 'out'], subagents: [17, 245, 0, 'out'],
  hosts: [14.3, 292, 0, 'out'],
  'guard-ring': [0, 0, 0, null], activation: [28.4, 331, 0, 'out'], 'session-start': [28.4, 15, 0, 'out'], 'persona-injector': [27, 0, 0, 'out'],
  'mode-selector': [28.6, 345, 0, 'out'], 'fail-closed': [28.4, 52, 0, 'out'], 'guard-bash': [27, 72, 0, 'out'], 'guard-write': [27, 88, 0, 'out'],
  'advisory-lamps': [28.5, 103, 0, 'out'], 'security-pass': [28.7, 118, 0, 'out'], 'conflict-hierarchy': [28.6, 200, 0, 'out'],
  'spec-plan': [R.skills, 45, 0, 'out'], 'skill-tdd': [R.skills, 62, 0, 'out'], authors: [R.skills, 79, 0, 'out'],
  'security-skills': [R.skills, 126, 0, 'out'], 'reviewer-fleet': [R.skills, 174, 0, 'out'], triage: [R.skills, 192, 0, 'out'], smarts: [R.skills, 233, 0, 'out'],
  vault: [87, 210, 0, 'in'], maturity: [77.5, 202.5, 0, 'in'], 'specs-plans': [77.5, 218, 0, 'in'], 'adr-tablets': [74, 210, 0, 'in'],
  'task-board': [78, 195.5, 0, 'in'], 'audit-ledger': [78, 225.5, 0, 'in'], 'evidence-shelf': [86, 224, 0, 'in'], receipts: [77, 188, 0, 'in'],
  repo: [80, 116, 0, 'in'], 'branch-rails': [0, 0, 0, null], 'main-vault': [93, 140.5, 0, 'in'], 'git-hooks': [86.4, 132.6, 0, 'in'], 'remote-ci': [93, 108, 0, 'in'],
  network: [80, 266, 0, 'in'], farm: [86, 285, 0, 'in'], sandbox: [84, 303, 0, 'in'],
  operator: [66, 0, 0, 'in'], confirm: [64.6, -7.6, 0, 'in'], 'approval-key': [64.6, 7.6, 0, 'in'],
};
for (const [id, a] of Object.entries(LA)) PLACE[id] = [R.lanes, a, 0, 'out'];

/* ---------------------------------------------------------------- builders */

const B = {};
const T = []; // global idle ticks: fn(t, dt)

// ---- model
B.weights = (k) => {
  for (let i = 0; i < 8; i++) { const p = polar(4.3, i * 45 + 22.5); k.cyl(0.15, 18.4, 'steel2', p.x, 0, p.z, 10); }
  k.tor(4.3, 0.2, 'steel2', 0, 0.35, 0); k.tor(4.3, 0.18, 'steel2', 0, 9.2, 0); k.tor(4.3, 0.22, 'trim', 0, 18.4, 0);
};
B.transformer = (k) => {
  k.cyl(3.1, 15.6, 'glass', 0, 1.2, 0, 40, 3.1, true);
  const discs = [];
  for (let i = 0; i < 12; i++) {
    const y = 1.85 + i * 1.25;
    k.tor(2.65, 0.13, 'steel2', 0, y, 0, Math.PI / 2, Math.PI * 2, 40);
    const m = k.S.u('blueDim');
    k.cyl(2.45, 0.07, m, 0, y - 0.035, 0, 36);
    discs.push(m);
  }
  const shaft = k.S.u('blue');
  k.cyl(0.3, 15.4, shaft, 0, 1.3, 0, 16);
  let pass = -1; // a forward pass: one bright wave up all twelve layers, once per token
  return {
    pulse() { pass = 0; },
    tick(t, dt) {
      const ph = (t * 0.32) % 1.25;
      if (pass >= 0) { pass += dt / 0.5; if (pass > 1.25) pass = -1; }
      discs.forEach((m, i) => {
        const d = i / 11 - ph, e = i / 11 - pass;
        m.emissiveIntensity = 0.4 + 1.5 * Math.exp(-(d * d) / 0.006) * (pass >= 0 ? 0.35 : 1) + (pass >= 0 ? 2.4 * Math.exp(-(e * e) / 0.004) : 0);
      });
      shaft.emissiveIntensity = 0.9 + 0.25 * Math.sin(t * 2.1) + (pass >= 0 ? 0.8 : 0);
    },
  };
};
B.attention = (k) => {
  const n = 60;
  const im = k.inst(new THREE.TorusGeometry(0.3, 0.06, 8, 20), k.S.u('blue'), n);
  im.material.emissiveIntensity = 0.75;
  const o = new THREE.Object3D();
  const place = (t) => {
    for (let i = 0; i < 12; i++) for (let j = 0; j < 5; j++) {
      const a = rad(j * 72 + i * 23) + t * (i % 2 ? 0.45 : -0.35);
      o.position.set(1.55 * Math.sin(a), 2.18 + i * 1.25, 1.55 * Math.cos(a));
      o.rotation.set(0, a, 0);
      o.updateMatrix();
      im.setMatrixAt(i * 5 + j, o.matrix);
    }
    im.instanceMatrix.needsUpdate = true;
  };
  place(0);
  im.computeBoundingSphere();
  let fl = 0;
  return { flash() { fl = 1; }, tick(t, dt) { place(t); fl = Math.max(0, fl - dt * 2.2); im.material.emissiveIntensity = 0.75 + fl * 1.6; } };
};
B.embedding = (k) => {
  k.tor(3.45, 0.42, 'steel2', 0, 0.95, 0, Math.PI / 2, Math.PI * 2, 64);
  for (let i = 0; i < 20; i++) { const a = i * 18; const p = polar(3.95, a); const f = k.box(0.08, 0.7, 0.75, 'trim', p.x, 0.6, p.z, 0.02); f.rotation.y = rad(a); }
  const ring = k.S.u('blue');
  k.tor(3.0, 0.07, ring, 0, 1.45, 0, Math.PI / 2, Math.PI * 2, 64);
};
B.tokenizer = (k) => {
  k.box(2.8, 1.3, 2.2, 'steel', 0, 0, 0);
  k.box(0.18, 2.7, 0.18, 'steel2', -1.25, 1.3, 1.0); k.box(0.18, 2.7, 0.18, 'steel2', 1.25, 1.3, 1.0);
  k.box(2.7, 0.2, 0.3, 'steel2', 0, 4.0, 1.0);
  const blade = k.dyn(k.box(2.3, 0.12, 0.14, 'trim', 0, 3.4, 1.0, 0.02));
  k.box(1.5, 0.04, 2.6, 'paper', 0, 1.3, 2.3, 0.01);
  k.box(1.2, 0.12, 2.8, 'dark', 0, 1.3, -2.3, 0.04);
  const toks = [];
  for (let i = 0; i < 5; i++) toks.push(k.dyn(k.box(0.34, 0.34, 0.34, 'blue', 0, 1.42, -1, 0.04)));
  let chop = -1;
  return {
    chop() { chop = 0; },
    tick(t, dt) {
      const c = (t * 1.1) % 1;
      if (chop >= 0) { chop += dt / 0.28; blade.position.y = 1.55 + Math.abs(Math.cos(Math.min(1, chop) * Math.PI)) * 2.2; if (chop >= 1) chop = -1; }
      else blade.position.y = 1.55 + Math.abs(Math.sin(c * Math.PI)) * 2.2;
      toks.forEach((m, i) => { const u = ((t * 0.55 + i / 5) % 1); m.position.z = -1.0 - u * 2.9; m.position.x = Math.sin(i * 1.7) * 0.25; });
    },
  };
};
B['context-window'] = (k) => {
  k.cyl(2.3, 0.55, 'steel', 0, 0, 0, 36);
  k.cyl(2.0, 13, 'glass', 0, 0.55, 0, 40, 2.0, true);
  k.tor(2.02, 0.14, 'trim', 0, 13.55, 0); k.tor(2.02, 0.12, 'trim', 0, 0.6, 0);
  // Bands, bottom to top, use the same colours as the Context lab: system and tools, codeArbiter rules,
  // lane instructions, summary of compacted turns, conversation, tool results. Heights are fractions of capacity.
  const CAP = 12.9;
  const ORDER = ['fixed', 'rules', 'wf', 'summary', 'conv', 'results'];
  const COL = { fixed: [0x9fb7d4, 0.3], rules: [0xb8a1e6, 0.55], wf: [0x8b78c9, 0.45], summary: [0xe8dcc0, 0.35], conv: [0x2c6aa0, 0.55], results: [0x7cc4ff, 0.8] };
  const fill = k.sub(0, 0.6, 0);
  const unit = new THREE.CylinderGeometry(1.82, 1.82, 1, 32); unit.translate(0, 0.5, 0);
  const meshes = {};
  for (const b of ORDER) {
    const [c, e] = COL[b];
    const m = new THREE.Mesh(unit, k.S.reg(new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: e, metalness: 0.1, roughness: 0.5, transparent: true, opacity: 0.9 })));
    m.userData.dyn = true; fill.g.add(m); meshes[b] = m;
  }
  k.box(0.12, 12.9, 0.34, 'panel', 2.18, 0.6, 0, 0.03);
  const mark = k.dyn(k.box(0.55, 0.1, 0.55, 'ink', 2.18, 0.6, 0, 0.02));
  const DEF = { fixed: 0.14, rules: 0.04, wf: 0.05, summary: 0, conv: 0.2, results: 0.17 };
  const cur = { ...DEF }, tgt = { ...DEF };
  const sum = (o) => ORDER.reduce((a, b) => a + o[b], 0);
  const api = {
    bands: () => ({ ...tgt }),
    setBands(f) { for (const b of ORDER) if (f[b] !== undefined) tgt[b] = Math.max(0, f[b]); const s2 = sum(tgt); if (s2 > 0.98) for (const b of ORDER) tgt[b] *= 0.98 / s2; },
    setFill(f) {
      f = Math.max(0.05, Math.min(0.98, f));
      const base = tgt.fixed + tgt.rules + tgt.wf + tgt.summary, room = Math.max(0, f - base), was = tgt.conv + tgt.results || 1;
      tgt.conv = room * (tgt.conv / was || 0.55); tgt.results = room - tgt.conv;
    },
    add(b, v) { tgt[b] = Math.max(0, (tgt[b] || 0) + v); const s2 = sum(tgt); if (s2 > 0.98) for (const k2 of ORDER) tgt[k2] *= 0.98 / s2; },
    compactBands() { tgt.summary = Math.min(0.2, tgt.summary + 0.05 + 0.12 * (tgt.conv + tgt.results)); tgt.conv = 0.05; tgt.results = 0; },
    reset() { Object.assign(tgt, DEF); },
    tick(t, dt) {
      let y = 0;
      for (const b of ORDER) {
        cur[b] += (tgt[b] - cur[b]) * Math.min(1, dt * 2.5);
        const h = cur[b] * CAP;
        meshes[b].visible = h > 0.02; meshes[b].scale.set(1, Math.max(0.001, h - 0.03), 1); meshes[b].position.y = y;
        y += h;
      }
      mark.position.y = 0.6 + y + 0.05;
    },
  };
  api.tick(0, 1);
  return api;
};
B['kv-cache'] = (k) => {
  k.box(3.3, 0.4, 1.5, 'steel', 0, 0, 0);
  k.box(0.24, 9.6, 0.24, 'steel2', -1.4, 0.4, 0); k.box(0.24, 9.6, 0.24, 'steel2', 1.4, 0.4, 0);
  k.box(3.1, 0.26, 0.42, 'steel2', 0, 10.0, 0);
  const n = 30;
  const im = k.inst(geo('kvcell', () => new THREE.BoxGeometry(0.74, 0.42, 0.55)), k.S.reg(new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x15324e, emissiveIntensity: 0.6, metalness: 0.3, roughness: 0.45 })), n);
  const o = new THREE.Object3D();
  for (let i = 0; i < n; i++) { const c = i % 3, r = (i / 3) | 0; o.position.set((c - 1) * 0.86, 0.95 + r * 0.9, 0); o.updateMatrix(); im.setMatrixAt(i, o.matrix); }
  const on = new THREE.Color(0x7cc4ff), off = new THREE.Color(0x1a2838);
  let lit = 18;
  const paint = () => { for (let i = 0; i < n; i++) im.setColorAt(i, i < lit ? on : off); im.instanceColor.needsUpdate = true; };
  paint();
  let acc = 0, driven = 0;
  return {
    push() { driven = 9; lit = Math.min(n, lit + 1); paint(); },
    clear() { driven = 9; lit = 0; paint(); },
    tick(t, dt) { if (driven > 0) { driven -= dt; return; } acc += dt; if (acc > 0.45) { acc = 0; lit = lit >= n ? 6 : lit + 1; paint(); } },
  };
};
B.logits = (k) => {
  k.cyl(2.9, 0.3, 'steel2', 0, 0, 0, 40);
  k.tor(2.9, 0.07, 'trim', 0, 0.3, 0);
  const bars = [];
  const N = 11;
  for (let i = 0; i < N; i++) {
    const a = rad(-75 + (150 * i) / (N - 1));
    const m = k.S.u(i === 3 ? 'blue' : 'blueDim');
    const b = k.dyn(k.box(0.3, 1, 0.3, m, 2.1 * Math.sin(a), 0, 2.1 * Math.cos(a), 0.04));
    b.rotation.y = a;
    bars.push(b);
  }
  const dist = () => { const peak = (Math.random() * 6) | 0; return bars.map((_, i) => 0.25 + 2.4 * Math.exp(-((i - peak - 2) ** 2) / 2.2) + Math.random() * 0.25); };
  let cur = dist(), next = dist(), acc = 0, pick = -1;
  const white = new THREE.Color(0xeaf6ff), base = new THREE.Color(C.blue);
  const apply = () => bars.forEach((b, i) => {
    const h = cur[i]; b.scale.y = h; b.position.y = 0.3 + h / 2;
    const hot = i === pick;
    b.material.emissiveIntensity = hot ? 2.4 : h > 1.6 ? 1.2 : 0.45;
    b.material.emissive.copy(hot ? white : base);
  });
  apply();
  // Candidates sit at fixed "vocabulary" positions, so the display looks like a distribution, not a sorted chart.
  const SLOT = [5, 2, 8, 0, 9, 6, 3, 10, 1, 7, 4];
  return {
    show(probs, chosen = 0) {
      const top = Math.max(...probs, 1e-6);
      next = bars.map((_, i) => 0.18 + Math.random() * 0.12);
      probs.forEach((p, j) => { if (j < SLOT.length) next[SLOT[j]] = 0.25 + 2.6 * (p / top); });
      pick = SLOT[chosen] ?? -1; acc = -6;
    },
    tick(t, dt) { acc += dt; if (acc > 3.2) { acc = 0; next = dist(); pick = -1; } cur = cur.map((h, i) => h + (next[i] - h) * Math.min(1, dt * 3)); apply(); },
  };
};
// The sampler is a wheel of fortune whose slices are sized by probability: likely tokens get wide slices.
// It spins once per token and stops under the fixed pointer at the front.
// Categorical slices in blues, slates and violets, so no slice borrows a state colour.
const WHEEL_COL = ['#2f6c9e', '#5b4ea0', '#3f6f8f', '#6a5aa8', '#46597a', '#3d4b5c', '#2a3a4c'];
function drawWheel(ctx, items) {
  const S2 = 512, c = S2 / 2, R2 = 250;
  ctx.clearRect(0, 0, S2, S2);
  let a = -Math.PI / 2; const centers = [];
  const tot = items.reduce((s, it) => s + it.p, 0) || 1;
  items.forEach((it, i) => {
    const span = Math.max(0.05, (it.p / tot) * Math.PI * 2);
    ctx.beginPath(); ctx.moveTo(c, c); ctx.arc(c, c, R2, a, a + span); ctx.closePath();
    ctx.fillStyle = it.other ? '#1d2733' : WHEEL_COL[i % WHEEL_COL.length]; ctx.fill();
    ctx.strokeStyle = 'rgba(9,13,18,0.9)'; ctx.lineWidth = 4; ctx.stroke();
    const mid = a + span / 2; centers.push(mid);
    if (span > 0.2 && it.label) {
      ctx.save(); ctx.translate(c, c); ctx.rotate(mid);
      ctx.fillStyle = it.other ? 'rgba(199,208,218,0.6)' : '#f4f8fc';
      ctx.font = `700 ${span > 0.7 ? 34 : 26}px "JetBrains Mono Variable", "JetBrains Mono", ui-monospace, monospace`;
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      ctx.fillText(it.label.length > 9 ? it.label.slice(0, 8) + '…' : it.label, R2 - 18, 0);
      ctx.restore();
    }
    a += span;
  });
  ctx.beginPath(); ctx.arc(c, c, 34, 0, Math.PI * 2); ctx.fillStyle = '#0d131a'; ctx.fill();
  return centers;
}
B.sampler = (k) => {
  k.cyl(1.95, 0.3, 'panel', 0, 0, 0, 44);
  k.tor(1.95, 0.08, 'trim', 0, 0.3, 0);
  for (let i = 0; i < 24; i++) { const p = polar(1.84, i * 15); const tk = k.box(0.05, 0.05, 0.14, 'ink', p.x, 0.31, p.z, 0.01); tk.rotation.y = rad(i * 15); }
  const cv = document.createElement('canvas'); cv.width = cv.height = 512;
  const ctx = cv.getContext('2d');
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  const wg = k.sub(0, 0.315, 0);
  const disc = new THREE.Mesh(new THREE.CircleGeometry(1.74, 72), k.S.reg(new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false })));
  disc.rotation.x = -Math.PI / 2; disc.userData.dyn = true; wg.g.add(disc);
  wg.sph(0.16, 'trim', 0, 0.06, 0, 14);
  // fixed pointer at the front rim, pointing inward
  const ptr = k.cone(0.16, 0.42, 'gold', 0, 0, 0, 3); ptr.rotation.x = -Math.PI / 2; ptr.position.set(0, 0.5, 1.98); ptr.userData.dyn = true;
  k.cyl(0.32, 0.5, 'trim', 2.3, -0.2, 0); k.cyl(0.32, 0.5, 'trim', -2.3, -0.2, 0);
  let items = [], centers = [], phi = 0, from = 0, to = 0, st = -1, dur = 0.9, onStop = null;
  const api = {
    setWheel(list) { items = list; centers = drawWheel(ctx, list); tex.needsUpdate = true; },
    // pointer reads canvas angle (pi/2 + phi); land the chosen slice's centre under it after a few turns
    spinTo(i, d = 0.9, cb) {
      const target = centers[i] ?? 0;
      let end = target - Math.PI / 2;
      while (end < phi + Math.PI * 4) end += Math.PI * 2;
      from = phi; to = end; st = 0; dur = d; onStop = cb || null;
    },
    pick() { const tot = items.reduce((s, it) => s + it.p, 0); let r = Math.random() * tot; for (let i = 0; i < items.length; i++) { r -= items[i].p; if (r <= 0) return i; } return 0; },
    sample() { if (items.length) api.spinTo(api.pick(), 1.1); },
    tick(t, dt) {
      if (st >= 0) {
        st += dt / dur; const u = Math.min(1, st); phi = from + (to - from) * (1 - (1 - u) ** 3);
        if (st >= 1) { st = -1; const cb = onStop; onStop = null; cb?.(); }
      } else phi += Math.sin(t * 0.7) * 0.0015;
      wg.g.rotation.y = phi;
    },
  };
  api.setWheel([{ label: 'pass', p: 0.48 }, { label: 'fail', p: 0.16 }, { label: 'are', p: 0.1 }, { label: 'should', p: 0.07 }, { label: 'still', p: 0.06 }, { label: '', p: 0.13, other: true }]);
  return api;
};
B.autoregress = (k) => {
  const pts = [];
  for (let i = 0; i <= 24; i++) { const u = i / 24; const a = -330 + 395 * u; pts.push(polar(3.85, a, 20.0 - 4.9 * u)); }
  pts.push(V(5.8, 14.9, 2.1), V(6.6, 14.6, 2.0));
  const tube = k.tube(pts, 0.11, 'trim', 220);
  const tok = k.dyn(k.box(0.32, 0.32, 0.32, 'blue', 0, 0, 0, 0.05));
  const gl = k.glow(C.blue, 1.2, 0, 0, 0, 0.6);
  const curve = tube.userData.curve;
  return {
    anchor: polar(3.85, -150, 18.2),
    tick(t) { const u = (t * 0.22) % 1; const p = curve.getPointAt(u); tok.position.copy(p); gl.position.copy(p); tok.rotation.y = t * 3; },
  };
};
B.reasoning = (k) => {
  k.sph(1.25, 'glass', 0, 0, 0, 28);
  k.tor(1.27, 0.06, 'trim', 0, 0, 0);
  const sw = k.sub(0, 0, 0);
  for (let i = 0; i < 7; i++) { const p = polar(0.6 + (i % 3) * 0.18, i * 51, Math.sin(i) * 0.4); sw.sph(0.12, 'blue', p.x, p.y, p.z, 10); }
  k.tubeAbs([polar(4.2, 214, 17.6), polar(3.1, 214, 17.0)], 0.12, 'steel2', 8);
  return { tick(t) { sw.g.rotation.y = t * 0.9; sw.g.rotation.x = Math.sin(t * 0.5) * 0.4; } };
};
B.router = (k) => {
  k.cyl(1.05, 0.7, 'steel2', 0, 0, 0, 32);
  k.tor(1.05, 0.07, 'trim', 0, 0.7, 0);
  const head = k.sub(0, 0.7, 0);
  head.box(1.1, 0.85, 1.7, 'steel', 0, 0, 0, 0.18);
  const nose = head.cone(0.36, 0.9, 'ink', 0, 0, 0); nose.rotation.x = Math.PI / 2; nose.position.set(0, 0.42, 1.25);
  head.sph(0.17, 'blue', 0, 0.42, 1.72, 12);
  const beamG = new THREE.Group(); beamG.position.set(0, 0.42, 1.7); head.g.add(beamG);
  const bgeo = new THREE.CylinderGeometry(0.07, 0.07, 1, 10, 1, true); bgeo.rotateX(Math.PI / 2); bgeo.translate(0, 0, 0.5);
  const bmat = k.S.reg(new THREE.MeshBasicMaterial({ color: C.blue, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  const beam = new THREE.Mesh(bgeo, bmat); beam.userData.nopick = true; beam.visible = false; beamG.add(beam);
  let target = null, yaw = 0, want = 0, hold = 0;
  return {
    aim(world, ms = 6000) {
      const me = new THREE.Vector3(); beamG.getWorldPosition(me);
      want = Math.atan2(world.x, world.z);
      target = world.clone(); hold = ms / 1000;
    },
    clear() { hold = 0; },
    tick(t, dt) {
      if (hold > 0) {
        hold -= dt;
        let d = want - yaw; d = Math.atan2(Math.sin(d), Math.cos(d));
        yaw += d * Math.min(1, dt * 4);
        head.g.rotation.y = yaw;
        const me = new THREE.Vector3(); beamG.getWorldPosition(me);
        const v = target.clone().sub(me); const hd = Math.hypot(v.x, v.z);
        beamG.rotation.x = Math.atan2(-v.y, hd) * 1; // pitch down
        beam.scale.z = v.length();
        beam.visible = true;
        bmat.opacity = Math.min(0.55, bmat.opacity + dt * 2) * (Math.abs(d) < 0.08 ? 1 : 0.4);
      } else {
        yaw += dt * 0.12; head.g.rotation.y = yaw;
        bmat.opacity = Math.max(0, bmat.opacity - dt * 1.5);
        beam.visible = bmat.opacity > 0.01;
      }
    },
  };
};

// ---- harness
B['agent-loop'] = (k) => {
  const plate = new THREE.Mesh(flatRing(15.6, 18.4), k.S.m('dark')); plate.position.y = 0.03; k.g.add(plate);
  k.tor(R.loop, 0.34, 'steel2', 0, 1.15, 0, Math.PI / 2, Math.PI * 2, 200);
  k.tor(R.loop, 0.07, 'trim', 0, 1.58, 0, Math.PI / 2, Math.PI * 2, 200);
  for (let i = 0; i < 16; i++) { const p = polar(R.loop, i * 22.5 + 11.25); k.cyl(0.12, 1.1, 'steel', p.x, 0, p.z, 8); }
  const pods = [];
  for (let i = 0; i < 7; i++) pods.push({ m: k.dyn(k.sph(0.3, 'blue', 0, 0, 0, 14)), g: k.glow(C.blue, 1.6, 0, 0, 0, 0.5), o: i / 7 });
  const place = (t) => pods.forEach((p) => { const a = (p.o + t * 0.035) * 360; const v = polar(R.loop, a, 1.62); p.m.position.copy(v); p.g.position.copy(v); });
  place(0);
  return { anchor: polar(R.loop, -32, 2.2), tick: (t) => place(t) };
};
B['prompt-assembly'] = (k) => {
  k.box(0.22, 3.3, 0.22, 'steel2', -1.55, 0, 0); k.box(0.22, 3.3, 0.22, 'steel2', 1.55, 0, 0);
  k.cyl(0.35, 0.9, 'steel', 0, 0.55, 0, 24, 1.15);
  [['ink', 1.65], ['blueDim', 2.0], ['steel2', 2.35], ['panel', 2.7]].forEach(([m, y]) => k.box(2.7, 0.16, 1.7, m, 0, y, 0, 0.04));
  k.tubeAbs([polar(16.2, 0, 1.0), polar(13.2, 0, 1.3), polar(10.0, 0, 2.0), polar(9.2, 0, 2.25)], 0.24, 'steel2', 24);
};
B['tool-parser'] = (k) => {
  k.cyl(0.78, 1.7, 'steel2', 0, 0.3, 0, 28); k.cyl(0.88, 0.2, 'trim', 0, 2.0, 0, 28);
  k.rod(0.24, 1.6, 'steel', 0.9, 1.1, 0, 'x'); k.rod(0.24, 1.4, 'steel', 0, 1.1, 0.85, 'z');
  k.lamp(C.blue, 0, 2.35, 0, 0.16, 1.0);
  k.tubeAbs([polar(3.3, 38, 19.4), polar(7.5, 38, 17.2), polar(13.5, 38, 7.5), polar(16.7, 38, 2.5)], 0.15, 'steel2', 60);
};
B.permissions = (k) => {
  k.box(1.5, 1.2, 1.0, 'steel', 0, 0, 0);
  k.cyl(0.08, 0.6, 'trim', 0, 1.2, 0, 8);
  const w = k.sub(0, 2.15, 0);
  w.tor(0.6, 0.08, 'trim', 0, 0, 0, 0);
  for (let i = 0; i < 4; i++) { const r = w.box(1.2, 0.06, 0.06, 'trim', 0, -0.03, 0, 0.01); r.rotation.z = (i * Math.PI) / 4; }
  return { tick(t) { w.g.rotation.z = Math.sin(t * 0.4) * 0.3; } };
};
B['tool-router'] = (k) => {
  k.cyl(1.1, 1.9, 'steel', 0, 0, 0, 32); k.cyl(1.2, 0.22, 'trim', 0, 1.9, 0, 32);
  const ring = k.S.u('blue'); k.tor(1.14, 0.08, ring, 0, 1.0, 0);
  return { tick(t) { ring.emissiveIntensity = 0.6 + 0.5 * Math.sin(t * 3); } };
};
function arm(k, head) {
  k.cyl(0.55, 0.5, 'steel2', 0, 0, 0, 20);
  k.sph(0.32, 'trim', 0, 0.9, 0, 14);
  k.tube([V(0, 0.5, 0), V(0, 1.6, 0.2), V(0, 2.5, 0.9), V(0, 2.2, 2.2), V(0, 1.8, 2.9)], 0.17, 'steel2', 30);
  const h = k.sub(0, 1.8, 3.0);
  head(h);
  return h;
}
B['tool-read'] = (k) => { arm(k, (h) => { h.rod(0.32, 0.5, 'trim', 0, 0, 0, 'z'); h.sph(0.26, 'blue', 0, 0, 0.3, 14); }); };
B['tool-bash'] = (k) => { arm(k, (h) => { h.box(0.85, 0.65, 0.95, 'steel', 0, -0.32, 0, 0.1); h.lamp(C.blue, 0, 0, 0.52, 0.12, 0.8); }); };
B['tool-write'] = (k) => { arm(k, (h) => { const c = h.cone(0.32, 0.8, 'trim', 0, 0, 0); c.rotation.x = Math.PI / 2; c.position.set(0, 0, 0.3); h.sph(0.1, 'blue', 0, 0, 0.75, 10); }); };
B['tool-mcp'] = (k) => {
  arm(k, (h) => { h.box(0.6, 0.5, 0.5, 'steel2', 0, -0.25, 0, 0.08); for (let i = -1; i <= 1; i++) h.rod(0.05, 0.35, 'trim', i * 0.18, 0, 0.42, 'z'); });
  k.tubeAbs([polar(22.6, 109, 1.8), polar(25.0, 109, 3.4), polar(29.0, 109, 3.4), polar(31.0, 109, 1.6), polar(31.6, 109, 0.4)], 0.1, 'trim', 40);
  const p = k.local(polar(31.6, 109, 0)); k.cyl(0.45, 0.5, 'steel2', p.x, 0, p.z, 16);
};
B['tool-results'] = (k) => {
  k.cyl(0.4, 1.0, 'steel', 0, 0.7, 0, 24, 0.95);
  k.cyl(0.5, 0.7, 'steel2', 0, 0, 0, 20);
  k.tubeAbs([polar(25.8, 95, 2.9), polar(23.4, 108, 3.5), polar(19.4, 117, 2.9), polar(17.35, 121, 1.9)], 0.2, 'steel2', 50);
};
B['hook-bus'] = (k) => {
  const m = k.S.u('blueDim');
  k.tor(R.bus, 0.09, m, 0, 0.36, 0, Math.PI / 2, Math.PI * 2, 240);
  const jb = k.sub(); jb.g.position.copy(polar(R.bus, 326)); jb.g.rotation.y = rad(326);
  jb.box(1.8, 1.1, 1.1, 'steel2', 0, 0, 0, 0.12); jb.box(1.2, 0.5, 0.06, 'screen', 0, 0.35, 0.56, 0.02);
  for (const a of [0, 15, 345, 331, 52, 72, 88, 103, 118, 200]) k.tubeAbs([polar(R.bus, a, 0.36), polar(24.4, a, 0.55), polar(26.3, a, 0.95)], 0.045, m, 8);
  return { anchor: polar(R.bus, 326, 1.6), tick(t) { m.emissiveIntensity = 0.5 + 0.35 * Math.sin(t * 1.6); } };
};
B.compaction = (k) => {
  k.box(2.7, 0.6, 2.5, 'steel', 0, 0, 0);
  for (const [x, z] of [[-1.1, -0.95], [1.1, -0.95], [-1.1, 0.95], [1.1, 0.95]]) k.box(0.24, 3.6, 0.24, 'steel2', x, 0.6, z, 0.04);
  k.box(2.7, 0.35, 2.3, 'steel2', 0, 4.2, 0);
  const ram = k.sub(0, 3.3, 0); ram.box(1.9, 0.6, 1.7, 'trim', 0, 0, 0, 0.06);
  const block = k.dyn(k.box(1.8, 1.6, 1.6, 'paper', 0, 0.6, 0, 0.04));
  let anim = -1;
  const setH = (h) => { block.scale.y = h / 1.6; block.position.y = 0.6 + h / 2; };
  return {
    compact() { anim = 0; },
    tick(t, dt) {
      if (anim < 0) return;
      anim += dt;
      const a = anim;
      if (a < 0.8) { const u = a / 0.8; ram.g.position.y = 3.3 - u * (3.3 - 1.25); setH(1.6 - u * 1.05); }
      else if (a < 1.6) { const u = (a - 0.8) / 0.8; ram.g.position.y = 1.25 + u * 2.05; }
      else if (a > 7) { setH(1.6); anim = -1; }
    },
  };
};
B.subagents = (k) => {
  k.cyl(1.9, 0.4, 'steel', 0, 0, 0, 32);
  k.tor(1.6, 0.15, 'steel2', 0, 0.85, 0);
  const pods = [];
  for (let i = 0; i < 3; i++) { const p = polar(1.6, i * 120); k.cyl(0.18, 0.5, 'trim', p.x, 0.4, p.z, 10); pods.push({ m: k.dyn(k.sph(0.42, 'blue', p.x, 1.35, p.z, 16)), base: p }); }
  return {
    tick(t) {
      pods.forEach((p, i) => { p.m.position.y = 1.35 + Math.sin(t * 1.4 + i * 2) * 0.12; });
      const c = (t % 7) / 7; const p = pods[0];
      const out = c < 0.5 ? Math.sin(c * Math.PI * 2) : 0;
      p.m.position.z = p.base.z + out * 3.2; p.m.position.y += out * 1.6;
    },
  };
};
B.hosts = (k) => {
  k.box(4.4, 0.3, 1.9, 'steel', 0, 0, 0);
  const segs = [32, 6, 3], lamps = [], cups = [];
  for (let i = 0; i < 3; i++) {
    const x = (i - 1) * 1.4;
    const c = k.sub(x, 0.3, 0);
    c.cyl(0.55, 0.95, 'steel2', 0, 0, 0, segs[i]);
    c.cyl(0.4, 0.2, 'trim', 0, 0.95, 0, segs[i]);
    cups.push(c);
    lamps.push(c.lamp(C.blue, 0, 1.4, 0, 0.13, 0.9, i === 0));
  }
  let sel = 0;
  return {
    setHost(i) { sel = i; lamps.forEach((l, j) => (j === i ? l.set(C.blue, 1.5, 0.55) : l.set(0x3a4757, 0.05, 0))); },
    tick(t, dt) { cups.forEach((c, j) => { const want = j === sel ? 0.6 : 0.3; c.g.position.y += (want - c.g.position.y) * Math.min(1, dt * 5); }); },
  };
};

// ---- guards
B['guard-ring'] = (k) => {
  const gaps = [[-5.5, 5.5], [68.2, 75.8], [84.2, 91.8]];
  const spans = [[5.5, 68.2], [75.8, 84.2], [91.8, 354.5]];
  for (const [a0, a1] of spans) {
    k.g.add(new THREE.Mesh(sectorGeo(26.6, 27.4, a0, a1, 1.9), k.S.m('steel')));
    const top = new THREE.Mesh(sectorGeo(26.5, 27.5, a0, a1, 0.14), k.S.m('trim')); top.position.y = 1.9; k.g.add(top);
  }
  const plate = new THREE.Mesh(flatRing(25.9, 28.1), k.S.m('dark')); plate.position.y = 0.02; k.g.add(plate);
  const ribs = [];
  for (let a = 0; a < 360; a += 6) if (!gaps.some(([g0, g1]) => a > g0 - 3 && a < g1 + 3) && !(a > 351 || a < 9)) ribs.push(a);
  const im = k.inst(geo('rib', () => new THREE.BoxGeometry(0.3, 2.3, 1.05)), 'steel2', ribs.length);
  const o = new THREE.Object3D();
  ribs.forEach((a, i) => { o.position.copy(polar(27, a, 1.15)); o.rotation.set(0, rad(a), 0); o.updateMatrix(); im.setMatrixAt(i, o.matrix); });
  im.computeBoundingSphere();
  return { anchor: polar(27, 160, 2.6) };
};
B.activation = (k) => {
  k.box(1.7, 1.4, 1.3, 'steel', 0, 0, 0, 0.12);
  k.box(1.35, 0.46, 0.05, 'screen', 0, 0.55, 0.66, 0.02);
  const lv = k.sub(0, 1.45, 0); lv.g.rotation.x = -0.5;
  lv.box(0.16, 1.5, 0.16, 'trim', 0, 0, 0, 0.04); lv.sph(0.24, 'gold', 0, 1.55, 0, 16);
  k.lamp(C.green, 0.6, 1.62, 0.45, 0.12, 0.8);
};
B['session-start'] = (k) => {
  k.cyl(0.6, 0.3, 'steel', 0, 0, 0, 20);
  k.cyl(0.17, 3.6, 'steel2', 0, 0.3, 0, 12);
  k.tor(0.55, 0.06, 'trim', 0, 3.95, 0);
  const dome = k.S.u('blue');
  k.sph(0.48, dome, 0, 4.25, 0, 18);
  const gl = k.glow(C.blue, 3.2, 0, 4.25, 0, 0.5);
  return { tick(t) { const p = 0.5 + 0.5 * Math.sin(t * 1.3); dome.emissiveIntensity = 0.6 + p; gl.material.opacity = 0.25 + 0.4 * p; } };
};
B['persona-injector'] = (k) => {
  k.box(0.45, 4.3, 0.7, 'steel2', -2.4, 0, 0); k.box(0.45, 4.3, 0.7, 'steel2', 2.4, 0, 0);
  k.box(5.4, 0.55, 0.9, 'steel2', 0, 4.25, 0, 0.12);
  k.cyl(0.6, 1.7, 'steel', 0, 2.55, 0, 24);
  k.cyl(0.12, 0.75, 'trim', 0, 1.8, 0, 20, 0.6);
  const res = k.S.u('blueDim');
  k.cyl(0.46, 0.95, res, 0, 4.8, 0, 20);
  k.lamp(C.blue, 0, 5.95, 0, 0.13, 0.9);
  let pulse = 0;
  return { inject() { pulse = 1.2; }, state(s) { if (s) pulse = 1.6; }, tick(t, dt) { pulse = Math.max(0, pulse - dt); res.emissiveIntensity = 0.55 + pulse * 1.4 + 0.15 * Math.sin(t * 2); } };
};
B['mode-selector'] = (k) => {
  k.box(1.6, 1.3, 1.4, 'steel', 0, 0, 0, 0.12);
  k.cyl(0.78, 0.2, 'panel', 0, 1.3, 0, 32);
  const ptr = k.sub(0, 1.52, 0); ptr.box(0.16, 0.12, 0.72, 'trim', 0, 0, 0.3, 0.03);
  const lamps = [-50, 0, 50].map((a, i) => { const p = polar(0.62, a); return k.lamp(i === 1 ? C.green : 0x3a4757, p.x, 1.56, p.z, 0.08, 0.5, i === 1); });
  return { lamps };
};
B['fail-closed'] = (k) => {
  k.box(1.5, 2.4, 0.95, 'steel2', 0, 0, 0, 0.1);
  k.box(1.2, 1.9, 0.06, 'steel', 0, 0.25, 0.49, 0.02);
  k.box(0.14, 0.6, 0.14, 'trim', 0.35, 1.05, 0.6, 0.03);
  const l = k.lamp(C.red, -0.38, 2.0, 0.52, 0.11, 0.7, false);
  return { state(s) { const on = s === 'block' || s === 'stop'; l.set(C.red, on ? 1.8 : 0.08, on ? 0.7 : 0); } };
};
function gate(k, arch) {
  k.box(0.95, 4.3, 1.7, 'steel2', -2.1, 0, 0, 0.12); k.box(0.95, 4.3, 1.7, 'steel2', 2.1, 0, 0, 0.12);
  if (arch) k.tor(2.1, 0.32, 'steel', 0, 4.3, 0, 0, Math.PI, 32);
  else k.box(5.2, 0.6, 1.7, 'steel', 0, 4.3, 0, 0.12);
  k.box(1.9, 0.46, 0.05, 'screen', 0, arch ? 3.4 : 4.36, 0.88, 0.02);
  const lamps = [k.lamp(0x3a4757, -2.1, 4.7, 0.9, 0.15, 1.0, false), k.lamp(0x3a4757, 2.1, 4.7, 0.9, 0.15, 1.0, false)];
  const bar = k.sub(-1.62, 1.5, 0.95);
  bar.box(3.3, 0.22, 0.22, 'gold', 1.65, -0.11, 0, 0.05);
  bar.g.rotation.z = 1.25;
  let want = 1.25, reset = 0;
  const api = {
    lamps,
    block() { want = 0; lamps.forEach((l) => l.set(C.red, 1.8, 0.7)); reset = 4.5; },
    open() { want = 1.45; lamps.forEach((l) => l.set(C.green, 1.6, 0.6)); reset = 3.5; },
    idle() { want = 1.25; lamps.forEach((l) => l.set(0x3a4757, 0.05, 0)); },
    // a tour step holds the state until the step ends (state(null)); one-off blocks from effects reset on a timer
    state(s) { if (s === 'block' || s === 'stop') { api.block(); reset = 0; } else if (s === 'pass') { api.open(); reset = 0; } else if (s === 'gate' || s === 'ask') lamps.forEach((l) => l.set(C.gold, 1.4, 0.5)); else if (!s) api.idle(); },
    tick(t, dt) {
      bar.g.rotation.z += (want - bar.g.rotation.z) * Math.min(1, dt * (want === 0 ? 14 : 4));
      if (reset > 0) { reset -= dt; if (reset <= 0) api.idle(); }
    },
  };
  return api;
}
B['guard-bash'] = (k) => gate(k, false);
B['guard-write'] = (k) => gate(k, true);
B['advisory-lamps'] = (k) => {
  k.cyl(0.5, 0.25, 'steel', 0, 0, 0, 18);
  k.cyl(0.13, 3.9, 'steel2', 0, 0.25, 0, 10);
  const lamps = [];
  [1.4, 2.05, 2.7, 3.35].forEach((y) => {
    k.box(1.9, 0.07, 0.07, 'trim', 0, y - 0.035, 0, 0.01);
    lamps.push(k.lamp(0xe8dcc0, -0.95, y, 0, 0.16, 0.8, false), k.lamp(0xe8dcc0, 0.95, y, 0, 0.16, 0.8, false));
  });
  let acc = 0, i = 0;
  return { tick(t, dt) { acc += dt; if (acc > 1.6) { acc = 0; lamps.forEach((l) => l.set(0xe8dcc0, 0.08, 0)); i = (i + 3) % 8; lamps[i].set(0xe8dcc0, 1.1, 0.4); } } };
};
B['security-pass'] = (k) => {
  k.box(1.9, 0.6, 1.7, 'steel', 0, 0, 0);
  k.box(0.42, 3.1, 0.42, 'steel2', 0, 0.6, -0.6, 0.06);
  k.box(1.25, 0.05, 1.0, 'paper', 0, 0.6, 0.15, 0.01);
  const head = k.sub(0, 3.0, 0.15);
  head.box(1.25, 0.5, 1.2, 'steel2', 0, 0, 0, 0.08); head.box(0.95, 0.22, 0.95, 'gold', 0, -0.22, 0, 0.04);
  return { tick(t) { const c = t % 6; head.g.position.y = c < 0.35 ? 3.0 - Math.sin((c / 0.35) * Math.PI) * 2.0 : 3.0; } };
};
B['conflict-hierarchy'] = (k) => {
  k.box(2.1, 0.3, 0.9, 'steel', 0, 0, 0);
  k.box(0.18, 5.9, 0.18, 'steel2', -0.78, 0.3, 0, 0.04); k.box(0.18, 5.9, 0.18, 'steel2', 0.78, 0.3, 0, 0.04);
  for (let i = 0; i < 5; i++) k.rod(i === 4 ? 0.11 : 0.07, 1.56, i === 4 ? 'ink' : 'trim', 0, 1.25 + i * 1.08, 0, 'x');
};

// ---- skills
B['spec-plan'] = (k) => {
  for (const [x, z] of [[-1.4, -0.9], [1.4, -0.9], [-1.4, 0.9], [1.4, 0.9]]) k.box(0.12, 1.6, 0.12, 'steel2', x, 0, z, 0.03);
  const top = k.sub(0, 1.75, 0); top.g.rotation.x = 0.35;
  top.box(3.3, 0.12, 2.3, 'panel', 0, 0, 0, 0.04);
  top.box(2.7, 0.03, 1.7, 'blueprint', 0, 0.12, 0, 0.01);
  k.rod(0.18, 2.6, 'paper', 0, 2.55, -1.15, 'x');
  k.box(0.1, 1.4, 0.1, 'trim', 1.55, 1.7, -1.1, 0.02);
  k.lamp(0xe8dcc0, 1.2, 3.1, -0.7, 0.14, 1.2);
};
B['skill-tdd'] = (k) => {
  k.box(2.7, 0.7, 2.2, 'steel', 0, 0, 0);
  k.box(0.32, 4.1, 0.32, 'steel2', -1.05, 0.7, 0, 0.05); k.box(0.32, 4.1, 0.32, 'steel2', 1.05, 0.7, 0, 0.05);
  k.box(2.7, 0.6, 1.1, 'steel2', 0, 4.8, 0, 0.08);
  const ram = k.sub(0, 3.4, 0); ram.box(1.6, 0.5, 1.2, 'trim', 0, 0, 0, 0.05);
  k.box(1.2, 0.45, 1.0, 'ink', 0, 0.7, 0, 0.05);
  const L = k.lamp(C.red, 0, 5.75, 0.25, 0.26, 2.0);
  const pips = []; for (let i = 0; i < 6; i++) pips.push(k.lamp(0x3a4757, -1.0 + i * 0.4, 5.15, 0.58, 0.08, 0.5, false));
  let ov = null;
  return {
    override(c) { ov = c; if (c) L.set(c, 1.8, 0.7); },
    state(s) { const c = s === 'fail' || s === 'block' || s === 'stop' ? C.red : s === 'pass' ? C.green : s === 'gate' ? C.gold : null; ov = c; if (c) L.set(c, 1.8, 0.7); },
    tick(t) {
      const c = t % 6, ph = Math.floor(c);
      pips.forEach((p, i) => p.set(i <= ph ? (i < 2 ? C.red : C.green) : 0x3a4757, i <= ph ? 1.1 : 0.05, i <= ph ? 0.35 : 0));
      if (!ov) L.set(ph < 2 ? C.red : C.green, 1.5, 0.55);
      ram.g.position.y = ph === 2 ? 3.4 - Math.sin((c - 2) * Math.PI) * 2.1 : 3.4;
    },
  };
};
B.authors = (k) => {
  k.box(4.6, 0.5, 2.1, 'steel', 0, 0, 0);
  const arms = [];
  for (let i = 0; i < 3; i++) {
    const x = (i - 1) * 1.45;
    k.cyl(0.36, 0.4, 'steel2', x, 0.5, 0, 18);
    const a = k.sub(x, 0.95, 0);
    a.box(0.24, 1.7, 0.24, 'steel2', 0, 0, 0, 0.05);
    const b = a.sub(0, 1.7, 0); b.sph(0.18, 'trim', 0, 0, 0, 12); b.box(0.2, 1.3, 0.2, 'trim', 0, 0, 0, 0.04);
    b.box(0.55, 0.14, 0.32, 'blue', 0, 1.3, 0, 0.03);
    arms.push([a, b]);
  }
  return { tick(t) { arms.forEach(([a, b], i) => { a.g.rotation.x = 0.35 + Math.sin(t * 0.9 + i * 2.1) * 0.25; b.g.rotation.x = 0.9 + Math.sin(t * 1.3 + i) * 0.35; }); } };
};
B['security-skills'] = (k) => {
  k.box(2.7, 3.1, 2.3, 'steel2', 0, 0, 0, 0.14);
  k.box(1.7, 1.15, 0.06, 'glass', 0, 1.35, 1.16, 0.02);
  k.box(3.0, 0.26, 2.6, 'steel', 0, 3.1, 0, 0.08);
  k.lamp(C.blue, 0, 1.9, 0.6, 0.18, 1.0);
};
B['reviewer-fleet'] = (k) => {
  k.box(9.2, 0.4, 1.7, 'steel', 0, 0, 0);
  const hs = [2.4, 3.0, 2.6, 3.2, 2.2, 2.8, 2.5];
  const lamps = hs.map((h, i) => {
    const x = -3.6 + i * 1.2;
    k.cyl(0.38, h, 'steel2', x, 0.4, 0, 6);
    k.cyl(0.43, 0.32, 'trim', x, 0.4 + h, 0, 6);
    return k.lamp(C.blue, x, 0.4 + h + 0.55, 0, 0.15, 1.0, false);
  });
  return { tick(t) { const c = (t * 1.2) % (lamps.length + 3); lamps.forEach((l, i) => l.set(Math.abs(c - i) < 0.6 ? C.blue : 0x3a4757, Math.abs(c - i) < 0.6 ? 1.5 : 0.05, Math.abs(c - i) < 0.6 ? 0.5 : 0)); } };
};
B.triage = (k) => {
  k.box(2.9, 0.5, 1.9, 'steel', 0, 0, 0);
  k.cyl(0.25, 1.1, 'steel2', 0, 0.5, 0, 16);
  k.cyl(0.35, 1.6, 'steel2', 0, 1.6, 0, 28, 1.5);
  k.tor(1.5, 0.08, 'trim', 0, 3.2, 0);
  ['red', 'ink', 'ink', 'ink'].forEach((m, i) => k.box(0.6, 0.75, 0.75, m, -1.05 + i * 0.7, 0.5, 0.75, 0.06));
};
B.smarts = (k) => {
  k.cyl(1.45, 0.5, 'steel', 0, 0, 0, 6);
  const pr = k.sub(0, 0.5, 0);
  const m = k.S.reg(new THREE.MeshStandardMaterial({ color: 0xa9d5ff, metalness: 0.1, roughness: 0.08, transparent: true, opacity: 0.35, emissive: 0x1d4a72, emissiveIntensity: 0.5 }));
  pr.cyl(1.15, 2.4, m, 0, 0.1, 0, 6);
  pr.cyl(0.5, 2.5, 'blue', 0, 0.05, 0, 6);
  for (let i = 0; i < 6; i++) { const p = polar(1.45, i * 60 + 30); k.lamp(C.blue, p.x, 0.6, p.z, 0.09, 0.6); }
  return { tick(t) { pr.g.rotation.y = t * 0.25; } };
};

// ---- lanes
function base(k) {
  k.box(6.0, 0.55, 4.8, 'steel', 0, 0, 0, 0.14);
  k.box(6.0, 0.06, 0.08, 'trim', 0, 0.55, 2.36, 0.02);
  k.box(3.2, 0.36, 0.05, 'screen', 0, 0.1, 2.42, 0.02);
  return 0.55;
}
const L = {};
L.init = (k, y) => {
  k.box(4.3, 0.7, 3.5, 'stone', 0, y, 0, 0.05); k.box(3.1, 0.7, 2.5, 'stone', 0, y + 0.7, 0, 0.05); k.box(1.9, 0.7, 1.5, 'steel2', 0, y + 1.4, 0, 0.08);
  k.box(0.5, 0.18, 0.05, 'gold', 0, y + 1.66, 0.76, 0.02);
  k.cyl(0.32, 1.5, 'steel2', -2.45, y, 1.65, 14); k.cyl(0.32, 1.5, 'steel2', 2.45, y, 1.65, 14);
};
L.feature = (k, y) => {
  k.box(5.3, 0.3, 1.3, 'dark', 0, y + 0.7, 0.4, 0.05);
  for (const x of [-2.3, 2.3]) k.box(0.15, 0.7, 1.1, 'steel2', x, y, 0.4, 0.03);
  k.box(0.9, 0.05, 0.7, 'paper', -1.8, y + 1.0, 0.4, 0.01); k.box(0.9, 0.05, 0.7, 'blueprint', -0.4, y + 1.0, 0.4, 0.01);
  k.box(1.1, 0.8, 1.0, 'steel2', 1.4, y + 1.0, 0.4, 0.08);
  k.box(0.2, 3.0, 0.2, 'steel2', 2.2, y, -1.2, 0.04); k.box(2.3, 0.2, 0.2, 'trim', 1.2, y + 3.0, -1.2, 0.04); k.cyl(0.03, 1.1, 'trim', 0.3, y + 1.9, -1.2, 6);
  const items = [0, 1, 2].map(() => k.dyn(k.box(0.42, 0.42, 0.42, 'blue', 0, y + 1.0, 0.4, 0.05)));
  return { tick(t) { items.forEach((m, i) => { m.position.x = -2.4 + ((t * 0.5 + i / 3) % 1) * 4.8; }); } };
};
L.sprint = (k, y) => {
  k.box(5.4, 0.3, 1.3, 'dark', 0, y + 0.7, 0.6, 0.05);
  for (const x of [-2.4, 2.4]) k.box(0.15, 0.7, 1.1, 'steel2', x, y, 0.6, 0.03);
  const drum = k.sub(-0.6, y + 2.1, -0.9); drum.rod(0.8, 2.6, 'steel2', 0, 0, 0, 'x'); drum.rod(0.82, 0.12, 'trim', 0.9, 0, 0, 'x'); drum.rod(0.82, 0.12, 'trim', -0.9, 0, 0, 'x');
  k.box(0.2, 1.45, 0.2, 'steel2', -2.0, y, -0.9, 0.04); k.box(0.2, 1.45, 0.2, 'steel2', 0.8, y, -0.9, 0.04);
  k.box(0.9, 0.7, 0.7, 'steel2', 2.1, y, -1.3, 0.06);
  const tape = k.box(0.45, 0.02, 1.9, 'paper', 2.1, y + 0.36, 0.2, 0.005); tape.rotation.x = -0.18;
  k.cyl(0.25, 0.5, 'orange', -2.6, y, -1.8, 12);
  const items = [0, 1, 2, 3].map(() => k.dyn(k.box(0.38, 0.38, 0.38, 'blue', 0, y + 1.0, 0.6, 0.05)));
  return { tick(t) { drum.g.rotation.x = t * 0.8; items.forEach((m, i) => { m.position.x = -2.5 + ((t * 0.8 + i / 4) % 1) * 5.0; }); } };
};
L.fix = (k, y) => {
  k.box(0.3, 3.4, 0.3, 'steel2', -1.0, y, 0, 0.05); k.box(0.3, 3.4, 0.3, 'steel2', 1.0, y, 0, 0.05);
  k.box(2.6, 0.5, 1.1, 'steel2', 0, y + 3.4, 0, 0.08);
  const ram = k.sub(0, y + 2.6, 0); ram.box(1.4, 0.45, 1.0, 'trim', 0, 0, 0, 0.05);
  k.box(1.2, 0.4, 0.9, 'ink', 0, y, 0, 0.05);
  const L1 = k.lamp(C.red, 0, y + 4.25, 0.3, 0.22, 1.6);
  return { tick(t) { const c = t % 5; L1.set(c < 2 ? C.red : C.green, 1.5, 0.55); ram.g.position.y = c > 2 && c < 2.6 ? y + 2.6 - Math.sin(((c - 2) / 0.6) * Math.PI) * 1.75 : y + 2.6; } };
};
L.refactor = (k, y) => {
  k.cone(0.55, 1.25, 'steel2', 0, y, 0, 4);
  k.box(4.8, 0.18, 0.45, 'trim', 0, y + 1.25, 0, 0.04);
  k.box(1.15, 1.15, 1.15, 'ink', -1.85, y + 1.43, 0, 0.12); k.box(1.15, 1.15, 1.15, 'ink', 1.85, y + 1.43, 0, 0.12);
  k.lamp(C.green, 0, y + 1.75, 0.3, 0.1, 0.6);
};
L.chore = (k, y) => {
  k.box(4.4, 0.9, 2.6, 'steel2', 0, y + 0.35, 0, 0.1);
  for (const [x, z] of [[-1.7, 1.2], [1.7, 1.2], [-1.7, -1.2], [1.7, -1.2]]) k.rod(0.35, 0.25, 'dark', x, y + 0.35, z, 'x');
  [-1.4, 0, 1.4].forEach((x) => k.box(1.2, 0.85, 2.2, 'panel', x, y + 1.25, 0, 0.06));
  for (let i = 0; i < 3; i++) k.box(0.8, 0.04, 1.1, 'paper', -1.4, y + 2.1 + i * 0.06, 0, 0.01);
  for (let i = 0; i < 3; i++) k.box(0.5, 0.5, 0.5, 'stone', 0 + (i - 1) * 0.3, y + 2.1, (i - 1) * 0.45, 0.05);
  const r = k.tor(0.45, 0.08, 'trim', 1.4, y + 2.4, 0, 0, Math.PI * 1.5); r.rotation.y = Math.PI / 2;
};
L.spike = (k, y) => {
  for (const [x, z] of [[-2.1, -0.9], [2.1, -0.9], [-2.1, 0.9], [2.1, 0.9]]) k.box(0.14, 1.3, 0.14, 'steel2', x, y, z, 0.03);
  k.box(4.7, 0.2, 2.2, 'steel2', 0, y + 1.3, 0, 0.05);
  k.cyl(0.42, 1.0, 'glass', -1.2, y + 1.5, 0, 20); k.sph(0.55, 'glass', -1.2, y + 2.9, 0, 18);
  k.cyl(0.3, 0.6, 'blue', -1.2, y + 1.55, 0, 16);
  k.cyl(0.75, 1.4, 'steel', 1.4, y + 1.5, 0, 20); k.cyl(0.8, 0.14, 'trim', 1.4, y + 2.9, 0, 20);
};
L['add-dep'] = (k, y) => {
  k.box(5.6, 0.25, 1.2, 'dark', 0, y + 0.15, 0.6, 0.04);
  k.box(1.4, 2.5, 1.4, 'steel2', -2.1, y, -1.2, 0.12); k.box(0.9, 0.7, 0.05, 'glass', -2.1, y + 1.4, -0.48, 0.02);
  const arch = k.tor(1.35, 0.15, 'trim', 0.4, y + 0.4, 0.6, 0, Math.PI, 32); arch.rotation.y = Math.PI / 2;
  const crate = k.dyn(k.box(0.8, 0.8, 0.8, 'stone', 0, y + 0.4, 0.6, 0.06));
  k.lamp(C.blue, 0.4, y + 1.95, 0.6, 0.12, 0.8);
  return { tick(t) { crate.position.x = -2.4 + ((t * 0.35) % 1) * 4.8; } };
};
L.debug = (k, y) => {
  k.box(1.6, 1.0, 1.4, 'ink', -0.5, y, -0.5, 0.1);
  k.box(0.25, 3.2, 0.25, 'steel2', 1.6, y, -1.3, 0.04);
  const p = k.sub(1.6, y + 3.1, -1.3); p.box(2.2, 0.2, 0.2, 'trim', -1.0, 0, 0, 0.04); p.cyl(0.05, 0.9, 'trim', -2.05, -0.9, 0, 8); p.sph(0.12, 'blue', -2.05, -0.95, 0, 10);
  for (let i = 0; i < 5; i++) { const c = k.cyl(0.18, 1.1, 'steel2', -2.0 + i * 1.0, y, 1.5, 12); c.rotation.x = 0.55; c.position.y = y + 0.45; }
  return { tick(t) { p.g.rotation.y = Math.sin(t * 0.7) * 0.25; } };
};
L.commit = (k, y) => {
  k.box(2.0, 0.3, 4.6, 'dark', 0, y, 0, 0.05);
  const lamps = [];
  for (let i = 0; i < 9; i++) {
    const z = -2.0 + i * 0.5;
    k.tor(1.25, 0.13, 'steel2', 0, y + 1.6, z, 0, Math.PI * 2, 28);
    lamps.push(k.lamp(0x3a4757, 0, y + 2.92, z, 0.08, 0.5, false));
  }
  return { tick(t) { const c = (t * 2.2) % 12; lamps.forEach((l, i) => (i < c ? l.set(C.blue, 1.2, 0.4) : l.set(0x3a4757, 0.05, 0))); } };
};
L.pr = (k, y) => {
  k.box(5.4, 0.5, 2.7, 'steel2', 0, y, -0.6, 0.08);
  k.box(0.3, 3.9, 0.3, 'steel2', -2.3, y + 0.5, -1.5, 0.05);
  const boom = k.sub(-2.3, y + 4.4, -1.5);
  boom.box(3.4, 0.24, 0.3, 'trim', 1.7, 0, 0, 0.04); boom.cyl(0.03, 1.4, 'trim', 2.9, -1.4, 0, 6);
  k.box(1.2, 1.0, 1.0, 'paper', 0.6, y + 0.5, -0.6, 0.06);
  k.lamp(C.blue, -2.3, y + 4.7, -1.5, 0.12, 0.8);
  return { tick(t) { boom.g.rotation.y = Math.sin(t * 0.4) * 0.35; } };
};
L.release = (k, y) => {
  k.box(0.5, 5.4, 0.5, 'steel2', -1.6, y, 0, 0.06);
  for (const h of [1.4, 2.9, 4.4]) k.box(1.4, 0.15, 0.18, 'trim', -0.85, y + h, 0, 0.03);
  k.cyl(0.6, 2.7, 'ink', 0.3, y + 0.3, 0, 24); k.cone(0.6, 1.0, 'trim', 0.3, y + 3.0, 0, 24);
  k.cyl(0.8, 0.3, 'steel', 0.3, y, 0, 24);
  k.tor(0.72, 0.12, 'gold', 0.3, y + 0.85, 0);
};
L.review = (k, y) => {
  k.box(5.6, 0.3, 1.3, 'dark', 0, y + 0.3, 0.3, 0.05);
  k.box(0.35, 3.1, 0.35, 'steel2', -2.5, y, 0.3, 0.05); k.box(0.35, 3.1, 0.35, 'steel2', 2.5, y, 0.3, 0.05);
  k.box(5.4, 0.42, 0.65, 'steel', 0, y + 3.1, 0.3, 0.08);
  const h = k.sub(0, y + 2.85, 0.3); h.box(0.75, 0.42, 0.62, 'trim', 0, 0, 0, 0.06);
  const bm = h.g; const bmat = k.S.reg(new THREE.MeshBasicMaterial({ color: C.blue, transparent: true, opacity: 0.18, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 2.2), bmat); plane.position.y = -1.1; plane.userData.nopick = true; bm.add(plane);
  return { tick(t) { h.g.position.x = Math.sin(t * 0.9) * 2.0; } };
};
L.checkpoint = (k, y) => {
  k.cyl(0.6, 0.5, 'steel2', 0, y, 0, 18); k.cyl(0.2, 2.0, 'steel2', 0, y + 0.5, 0, 12);
  const d = k.sub(0, y + 2.6, 0);
  const dish = d.cap(1.5, 'trim', 0, 0, 0, 0.85); dish.rotation.x = -Math.PI / 2 + 0.55; dish.position.z = -0.4; dish.material.side = THREE.DoubleSide;
  d.cyl(0.05, 1.2, 'trim', 0, 0, 0.1, 6).rotation.x = 1.0;
  return { tick(t) { d.g.rotation.y = t * 0.6; } };
};
L['threat-model'] = (k, y) => {
  k.box(0.3, 1.6, 0.3, 'steel2', 0, y, -0.2, 0.05);
  const s = k.sub(0, y + 2.6, 0);
  for (let i = 0; i < 6; i++) {
    const g2 = new THREE.CylinderGeometry(1.5, 1.5, 0.3, 1, 1, false, rad(i * 60), rad(60));
    const m = new THREE.Mesh(g2, k.S.m(i % 2 ? 'steel2' : 'ink')); m.rotation.x = Math.PI / 2; s.g.add(m);
  }
  s.tor(1.5, 0.08, 'trim', 0, 0, 0, 0, Math.PI * 2, 6).rotation.z = Math.PI / 6;
};
L.tribunal = (k, y) => {
  k.cyl(0.55, 1.4, 'steel2', 0, y, 0, 16); k.sph(0.48, 'ink', 0, y + 1.9, 0, 18);
  const ring = k.sub(0, y + 1.9, 0);
  ring.tor(2.05, 0.1, 'steel2', 0, 0, 0);
  const im = ring.inst(geo('lens', () => { const g2 = new THREE.CylinderGeometry(0.3, 0.3, 0.07, 18); g2.rotateZ(Math.PI / 2); return g2; }), k.S.u('blueDim'), 13);
  const o = new THREE.Object3D();
  for (let i = 0; i < 13; i++) { const a = (i / 13) * Math.PI * 2; o.position.set(2.05 * Math.sin(a), 0, 2.05 * Math.cos(a)); o.rotation.set(0, a + Math.PI / 2, 0); o.updateMatrix(); im.setMatrixAt(i, o.matrix); }
  im.computeBoundingSphere();
  for (let i = 0; i < 4; i++) { const p = polar(2.05, i * 90 + 14); k.cyl(0.05, 1.9, 'trim', p.x, y, p.z, 6); }
  return { tick(t) { ring.g.rotation.y = t * 0.2; } };
};
L.adr = (k, y) => {
  k.box(2.4, 3.0, 0.45, 'stone', 0.5, y, -0.6, 0.06);
  k.box(1.8, 1.9, 0.05, 'dark', 0.5, y + 0.7, -0.36, 0.02);
  k.box(0.25, 3.5, 0.25, 'steel2', -1.8, y, 0.6, 0.04);
  const a = k.sub(-1.8, y + 3.3, 0.6); a.box(2.2, 0.16, 0.16, 'trim', 1.1, 0, 0, 0.03); a.cone(0.09, 0.5, 'gold', 2.2, -0.5, 0, 10).rotation.x = Math.PI;
  return { tick(t) { a.g.rotation.y = 0.35 + Math.sin(t * 0.8) * 0.2; } };
};
L['adr-status'] = (k, y) => {
  k.box(1.3, 1.3, 1.0, 'steel2', 0, y, 0.6, 0.08);
  const top = k.box(1.6, 0.1, 1.2, 'panel', 0, y + 1.35, 0.6, 0.03); top.rotation.x = 0.4;
  const mg = k.dyn(k.tor(0.38, 0.06, 'trim', 0.3, y + 1.9, 0.9, 0.3)); k.rod(0.05, 0.6, 'trim', 0.7, y + 1.65, 0.9, 'x');
  [-1.6, -0.8, 0, 0.8, 1.6].forEach((x, i) => k.box(0.6, 1.4 + (i % 2) * 0.4, 0.22, 'stone', x, y, -1.3, 0.04));
  return { tick(t) { mg.position.x = 0.3 + Math.sin(t * 0.6) * 0.3; } };
};
L.reconcile = (k, y) => {
  k.box(0.25, 3.0, 0.25, 'steel2', 0, y, 0, 0.04);
  const bm = k.sub(0, y + 3.0, 0); bm.box(4.4, 0.14, 0.2, 'trim', 0, 0, 0, 0.03);
  for (const x of [-2.1, 2.1]) { bm.cyl(0.02, 1.2, 'trim', x, -1.2, 0, 6); bm.cyl(0.8, 0.08, 'steel2', x, -1.25, 0, 24); }
  bm.cyl(0.32, 0.55, 'blue', 0, 0.1, 0, 6);
  return { tick(t) { bm.g.rotation.z = Math.sin(t * 0.7) * 0.06; } };
};
L.conflict = (k, y) => {
  k.cyl(0.95, 1.3, 'steel2', 0, y, 0.4, 24);
  k.tor(0.98, 0.12, 'gold', 0, y + 1.3, 0.4);
  k.cyl(0.78, 0.38, 'red', 0, y + 1.32, 0.4, 28); k.cap(0.78, 'red', 0, y + 1.7, 0.4, 0.5);
  k.cyl(0.12, 2.4, 'steel2', -1.9, y, -1.4, 10);
  const b = k.lamp(C.red, -1.9, y + 2.65, -1.4, 0.24, 1.6, false);
  let on = false;
  return { state(s) { on = !!s; if (!on) b.set(C.red, 0.08, 0); }, tick(t) { if (on) { const f = Math.sin(t * 7) > 0; b.set(C.red, f ? 2 : 0.2, f ? 0.8 : 0.1); } } };
};
L.status = (k, y) => {
  k.box(0.15, 1.2, 0.15, 'steel2', -1.8, y, -0.6, 0.03); k.box(0.15, 1.2, 0.15, 'steel2', 1.8, y, -0.6, 0.03);
  k.box(4.2, 2.3, 0.3, 'steel2', 0, y + 1.0, -0.6, 0.1);
  const nds = [-1.3, 0, 1.3].map((x) => {
    const d = k.cyl(0.55, 0.08, 'panel', x, 0, 0, 28); d.rotation.x = Math.PI / 2; d.position.set(x, y + 2.15, -0.42);
    const n = k.sub(x, y + 2.15, -0.36); n.box(0.06, 0.45, 0.03, 'blue', 0, 0, 0, 0.01); return n;
  });
  return { tick(t) { nds.forEach((n, i) => { n.g.rotation.z = -0.6 + Math.sin(t * 0.5 + i * 1.7) * 0.4 + i * 0.4; }); } };
};
L.task = (k, y) => {
  k.box(0.15, 1.3, 0.15, 'steel2', -1.9, y, -0.5, 0.03); k.box(0.15, 1.3, 0.15, 'steel2', 1.9, y, -0.5, 0.03);
  k.box(4.4, 2.6, 0.2, 'panel', 0, y + 1.0, -0.5, 0.06);
  const cards = [[-1.4, 3, 0xb9c4d1], [0, 2, 0x7cc4ff], [1.4, 4, 0x58d68d]];
  const n = cards.reduce((a, c) => a + c[1], 0);
  const im = k.inst(geo('card', () => new THREE.BoxGeometry(0.95, 0.42, 0.05)), k.S.reg(new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.7, emissive: 0x0a1620, emissiveIntensity: 0.5 })), n);
  const o = new THREE.Object3D(); let i = 0;
  for (const [x, c, col] of cards) for (let j = 0; j < c; j++) { o.position.set(x, y + 3.25 - j * 0.52, -0.37); o.updateMatrix(); im.setMatrixAt(i, o.matrix); im.setColorAt(i, new THREE.Color(col)); i++; }
  im.computeBoundingSphere();
};
L.doctor = (k, y) => {
  k.box(0.6, 1.8, 0.6, 'steel2', 1.4, y, -0.6, 0.06); k.box(0.6, 1.8, 0.6, 'steel2', 2.5, y, -0.6, 0.06); k.box(1.8, 0.3, 0.6, 'steel', 1.95, y + 1.8, -0.6, 0.06);
  k.box(0.3, 2.8, 0.3, 'steel2', -2.0, y, 0.3, 0.05);
  const a = k.sub(-2.0, y + 2.7, 0.3); a.box(3.2, 0.16, 0.16, 'trim', 1.6, 0, 0, 0.03); a.sph(0.14, 'blue', 3.25, -0.05, 0, 10);
  const sp = k.glow(C.red, 1.6, 1.95, y + 1.2, -0.6, 0);
  return { tick(t) { const c = t % 4; sp.material.opacity = c < 0.25 ? 0.8 * (1 - c / 0.25) : 0; } };
};
L.override = (k, y) => {
  k.cyl(0.6, 1.3, 'steel2', -1.1, y, 0.4, 20); k.cyl(0.42, 0.12, 'trim', -1.1, y + 1.3, 0.4, 20);
  k.tor(0.22, 0.06, 'gold', -1.1, y + 1.85, 0.4, 0); k.box(0.08, 0.42, 0.04, 'gold', -1.1, y + 1.28, 0.4, 0.01);
  k.box(1.7, 1.0, 1.2, 'steel2', 1.2, y, -0.4, 0.08);
  const tape = k.box(0.6, 0.02, 1.6, 'paper', 1.2, y + 0.55, 0.9, 0.005); tape.rotation.x = 0.45;
};
L.standup = (k, y) => {
  k.box(0.2, 3.0, 0.2, 'steel2', -1.2, y, 0, 0.04); k.box(1.4, 0.15, 0.15, 'trim', -0.6, y + 3.0, 0, 0.03);
  const bell = k.sub(0.05, y + 2.95, 0); bell.cyl(0.62, 0.8, 'trim', 0, -0.85, 0, 24, 0.22); bell.sph(0.1, 'steel2', 0, -0.95, 0, 8);
  k.box(1.1, 1.5, 0.08, 'paper', 1.6, y + 0.4, -0.2, 0.02);
  return { tick(t) { bell.g.rotation.z = Math.sin(t * 2.2) * 0.12 * (Math.sin(t * 0.3) > 0.6 ? 1 : 0.1); } };
};
L.audit = (k, y) => {
  k.box(3.0, 0.3, 2.0, 'steel2', 0, y, 0, 0.06);
  for (let i = 0; i < 5; i++) k.box(1.9, 0.18, 1.3, i % 2 ? 'paper' : 'ink', 0, y + 0.3 + i * 0.2, 0, 0.02);
  for (const x of [-1.25, 1.25]) k.box(0.18, 2.6, 0.18, 'trim', x, y + 0.3, 0, 0.04);
  const pl = k.sub(0, y + 2.4, 0); pl.box(2.9, 0.25, 1.9, 'steel2', 0, 0, 0, 0.05); pl.cyl(0.1, 0.9, 'trim', 0, 0.25, 0, 10);
  return { tick(t) { pl.g.position.y = y + 2.3 + Math.sin(t * 0.8) * 0.12; } };
};
L.statusline = (k, y) => {
  k.box(5.6, 0.4, 0.5, 'panel', 0, y + 0.6, 0.6, 0.06);
  for (const x of [-2.5, 2.5]) k.box(0.15, 0.6, 0.15, 'steel2', x, y, 0.6, 0.03);
  const segs = [];
  for (let i = 0; i < 12; i++) segs.push(k.lamp(i === 11 ? C.gold : C.blue, -2.2 + i * 0.4, y + 1.05, 0.88, 0.09, 0.45, true));
  let on = true;
  return {
    setAvailable(v) { on = v; },
    tick(t) { const c = (t * 6) % 14; segs.forEach((s, i) => { const lit = on && (i === 11 || Math.abs(i - c) < 2.2); s.set(i === 11 ? C.gold : C.blue, lit ? 1.4 : 0.05, lit ? 0.4 : 0); }); },
  };
};
L.prune = (k, y) => {
  k.box(3.2, 0.4, 2.2, 'steel', 0, y, 0, 0.06);
  for (const x of [-1.3, 1.3]) k.box(0.25, 2.8, 0.25, 'orange', x, y + 0.4, 0, 0.04);
  k.box(3.0, 0.3, 1.0, 'orange', 0, y + 3.2, 0, 0.06);
  const p = k.sub(0, y + 2.4, 0); p.box(2.2, 0.35, 0.9, 'trim', 0, 0, 0, 0.04);
  const blk = k.dyn(k.box(1.6, 1.0, 0.8, 'paper', 0, y + 0.4, 0, 0.03));
  return { tick(t) { const c = (t % 5) / 5; const d = c < 0.25 ? Math.sin(c * 4 * Math.PI) : 0; p.g.position.y = y + 2.4 - d * 1.0; blk.scale.y = 1 - d * 0.35; blk.position.y = y + 0.4 + (1 - d * 0.35) * 0.5; } };
};
for (const [id] of Object.entries(LA)) { const c = id.slice(3); B[id] = (k) => { const y = base(k); return L[c] ? L[c](k, y) : null; }; }

// ---- record
B.vault = (k) => {
  k.box(16, 0.8, 9.5, 'steel', 0, 0, 0, 0.2);
  k.box(13, 9, 7, 'steel2', 0, 0.8, -0.7, 0.25);
  k.box(14, 0.6, 8.2, 'steel', 0, 9.8, -0.7, 0.2);
  k.box(7.2, 6.4, 0.3, 'dark', 0, 1.1, 2.9, 0.05);
  const books = k.inst(geo('book', () => new THREE.BoxGeometry(0.28, 0.9, 0.5)), k.S.reg(new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.75 })), 88);
  const o = new THREE.Object3D(); const cols = [0xb9c4d1, 0x2c3a4a, 0x7cc4ff, 0xd8dee6, 0x3b4755]; let n = 0;
  for (let s = 0; s < 4; s++) { k.box(6.8, 0.12, 0.7, 'trim', 0, 1.5 + s * 1.5, 3.1, 0.02); for (let i = 0; i < 22; i++) { const h = 0.65 + ((i * 7 + s * 3) % 5) * 0.06; o.position.set(-3.1 + i * 0.29, 1.62 + s * 1.5 + h / 2, 3.15); o.scale.set(1, h / 0.9, 1); o.updateMatrix(); books.setMatrixAt(n, o.matrix); books.setColorAt(n, new THREE.Color(cols[(i * 3 + s) % 5])); n++; } }
  books.computeBoundingSphere();
  for (const x of [-5.6, -4.6, 4.6, 5.6]) k.box(0.32, 8.6, 0.5, 'trim', x, 1.0, 2.9, 0.05);
  k.box(6.2, 0.9, 0.1, 'screen', 0, 8.0, 2.9, 0.03);
};
B.maturity = (k) => {
  k.box(1.7, 1.7, 1.1, 'steel2', 0, 0, 0, 0.1);
  const d = k.cyl(0.95, 0.16, 'panel', 0, 0, 0, 32); d.rotation.x = Math.PI / 2; d.position.set(0, 2.55, 0);
  k.tor(0.96, 0.06, 'trim', 0, 2.55, 0.08, 0);
  for (let i = 0; i < 4; i++) { const a = rad(-60 + i * 40); k.lamp(C.blue, Math.sin(a) * 0.7, 2.55 + Math.cos(a) * 0.7, 0.14, 0.07, 0.4, false); }
  const p = k.sub(0, 2.55, 0.14); p.box(0.08, 0.7, 0.05, 'ink', 0, 0, 0, 0.01); p.g.rotation.z = -0.3;
};
B['specs-plans'] = (k) => {
  for (const x of [-1.3, 1.3]) k.box(0.15, 1.5, 1.0, 'steel2', x, 0, 0, 0.03);
  k.box(2.9, 0.15, 1.2, 'steel2', 0, 1.5, 0, 0.04);
  [[-0.5, 0], [0, 0], [0.5, 0], [-0.25, 0.42], [0.25, 0.42]].forEach(([z, dy], i) => k.rod(0.21, 2.5, i % 2 ? 'blueprint' : 'paper', 0, 1.86 + dy, z, 'x'));
};
B['adr-tablets'] = (k) => {
  k.box(8.6, 0.25, 1.3, 'steel', 0, 0, 0, 0.06);
  [2.4, 2.9, 3.3, 2.9, 2.4].forEach((h, i) => { const x = -3.2 + i * 1.6; k.box(1.15, h, 0.38, 'stone', x, 0.25, 0, 0.08); k.box(0.8, h * 0.55, 0.04, 'dark', x, 0.25 + h * 0.25, 0.2, 0.01); });
};
B['task-board'] = (k) => {
  k.box(0.12, 0.9, 0.12, 'steel2', -1.6, 0, 0, 0.02); k.box(0.12, 0.9, 0.12, 'steel2', 1.6, 0, 0, 0.02);
  k.box(3.7, 2.5, 0.16, 'panel', 0, 0.9, 0, 0.05);
  const cols = [[-1.15, 3, 0xb9c4d1], [0, 2, 0x7cc4ff], [1.15, 3, 0x58d68d]];
  const im = k.inst(geo('tcard', () => new THREE.BoxGeometry(0.85, 0.42, 0.04)), k.S.reg(new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.7, emissive: 0x0a1620, emissiveIntensity: 0.5 })), 8);
  const o = new THREE.Object3D(); let i = 0;
  for (const [x, c, col] of cols) for (let j = 0; j < c; j++) { o.position.set(x, 3.0 - j * 0.52, 0.1); o.updateMatrix(); im.setMatrixAt(i, o.matrix); im.setColorAt(i, new THREE.Color(col)); i++; }
  im.computeBoundingSphere();
};
B['audit-ledger'] = (k) => {
  k.box(2.3, 1.4, 1.5, 'steel2', 0, 0, 0, 0.1);
  k.rod(0.45, 2.1, 'paper', 0, 1.8, -0.35, 'x');
  const tape = k.sub(0, 0, 0);
  const fresh = k.S.reg(new THREE.MeshStandardMaterial({ color: 0xd8dee6, roughness: 0.9, emissive: 0x7ab7ff, emissiveIntensity: 0 }));
  for (let i = 0; i < 6; i++) { const s = tape.box(1.6, 0.02, 0.55, i === 0 ? fresh : 'paper', 0, 1.2 - i * 0.22, 0.95 + i * 0.45, 0.004); s.rotation.x = 0.42; }
  const head = k.sub(0, 1.42, 0.55); head.box(0.5, 0.2, 0.3, 'trim', 0, 0, 0, 0.03);
  let pr = -1;
  // print(): the head sweeps, the tape advances by one line and the newest line glows. It never rewinds.
  return {
    print() { pr = 0; },
    tick(t, dt) {
      if (pr >= 0) {
        pr += dt / 0.7; const u = Math.min(1, pr);
        head.g.position.x = Math.sin(u * Math.PI * 3) * 0.7;
        tape.g.position.set(0, -0.22 * u * 0.4, 0.45 * u * 0.4);
        fresh.emissiveIntensity = 1.2 * (1 - Math.max(0, pr - 1) / 2.5);
        if (pr >= 1) tape.g.position.set(0, 0, 0);
        if (pr >= 3.5) { pr = -1; fresh.emissiveIntensity = 0; }
      } else head.g.position.x = Math.sin(t * 2.4) * 0.6;
    },
  };
};
B['evidence-shelf'] = (k) => {
  k.box(3.3, 3.5, 1.1, 'steel2', 0, 0, -0.2, 0.08);
  const im = k.inst(geo('vol', () => new THREE.BoxGeometry(0.3, 0.85, 0.75)), k.S.reg(new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.7 })), 27);
  const o = new THREE.Object3D(); const cols = [0x2c3a4a, 0xb9c4d1, 0x58d68d, 0x3b4755]; let n = 0;
  for (let s = 0; s < 3; s++) { k.box(3.0, 0.08, 0.9, 'trim', 0, 0.35 + s * 1.05, 0.15, 0.01); for (let i = 0; i < 9; i++) { o.position.set(-1.25 + i * 0.31, 0.85 + s * 1.05, 0.2); o.updateMatrix(); im.setMatrixAt(n, o.matrix); im.setColorAt(n, new THREE.Color(cols[(i + s) % 4])); n++; } }
  im.computeBoundingSphere();
};
B.receipts = (k) => {
  for (const x of [-1.1, 1.1]) k.box(0.12, 1.2, 0.7, 'steel2', x, 0, 0, 0.02);
  k.box(2.6, 0.18, 0.9, 'steel2', 0, 1.2, 0, 0.04);
  for (let i = 0; i < 6; i++) { const x = -1.0 + i * 0.4; k.box(0.3, 0.9, 0.03, 'paper', x, 1.38, 0, 0.005); k.sph(0.07, 'green', x, 2.15, 0.03, 8); }
};

// ---- world
B.repo = (k) => {
  k.box(19, 0.6, 13, 'steel', 0, 0, 0, 0.2);
  const N = 84;
  const im = k.inst(geo('file', () => new THREE.BoxGeometry(1, 1, 1)), k.S.reg(new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 0.5, roughness: 0.45 })), N);
  const o = new THREE.Object3D(); const cols = [0x2c3a4a, 0x3b4755, 0x8d9db2, 0x2a5d88, 0x1d2732]; let n = 0; let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let gx = 0; gx < 12; gx++) for (let gz = 0; gz < 7; gz++) {
    if (gx === 5) continue; if (n >= N) break;
    const h = 0.5 + rnd() * rnd() * 3.6;
    o.position.set(-7.7 + gx * 1.4, 0.6 + h / 2, -4.2 + gz * 1.4); o.scale.set(1.05, h, 1.05); o.updateMatrix();
    im.setMatrixAt(n, o.matrix); im.setColorAt(n, new THREE.Color(cols[(rnd() * 5) | 0])); n++;
  }
  im.count = n; im.computeBoundingSphere();
};
B['branch-rails'] = (k) => {
  const path = [[78.5, 125.5], [83.5, 129.8], [88.0, 134.6], [90.4, 137.8]];
  for (const off of [-0.42, 0.42]) k.tube(path.map(([r, a]) => polar(r, a + off * (57.3 / r), 0.25)), 0.09, 'trim', 60);
  const curve = new THREE.CatmullRomCurve3(path.map(([r, a]) => polar(r, a, 0.12)));
  const im = k.inst(geo('sleeper', () => new THREE.BoxGeometry(2.0, 0.14, 0.35)), 'steel2', 12);
  const o = new THREE.Object3D();
  for (let i = 0; i < 12; i++) { const u = i / 11; const p = curve.getPointAt(u); const tg = curve.getTangentAt(u); o.position.copy(p); o.rotation.set(0, Math.atan2(tg.x, tg.z) + Math.PI / 2, 0); o.updateMatrix(); im.setMatrixAt(i, o.matrix); }
  im.computeBoundingSphere();
  const spur = [[81.0, 127.6], [83.0, 125.4], [84.5, 124.3]];
  for (const off of [-0.42, 0.42]) k.tube(spur.map(([r, a]) => polar(r, a + off * (57.3 / r), 0.25)), 0.07, 'steel2', 20);
  const b = polar(84.9, 124.0); k.box(1.3, 0.7, 0.6, 'stone', b.x, 0, b.z, 0.08).rotation.y = rad(214);
  return { anchor: polar(86, 132, 1.2) };
};
B['main-vault'] = (k) => {
  k.cyl(3.6, 5.6, 'steel', 0, 0, 0, 48); k.cyl(3.8, 0.4, 'trim', 0, 5.6, 0, 48); k.cyl(3.9, 0.3, 'steel2', 0, 0, 0, 48);
  const d = k.cyl(2.2, 0.35, 'steel2', 0, 0, 0, 40); d.rotation.x = Math.PI / 2; d.position.set(0, 2.8, 3.55);
  k.tor(2.22, 0.15, 'gold', 0, 2.8, 3.75, 0, Math.PI * 2, 48);
  const w = k.sub(0, 2.8, 3.85); for (let i = 0; i < 6; i++) { const s = w.box(1.7, 0.12, 0.1, 'trim', 0, -0.06, 0, 0.02); s.rotation.z = (i * Math.PI) / 6; }
  return { tick(t) { w.g.rotation.z = Math.sin(t * 0.2) * 0.05; } };
};
B['git-hooks'] = (k) => {
  k.box(2.2, 1.1, 1.6, 'steel2', 0, 0.2, 0, 0.12);
  k.box(1.0, 0.75, 0.45, 'steel', 0, 1.3, 0, 0.08);
  k.tor(0.36, 0.09, 'gold', 0, 2.05, 0, 0, Math.PI, 20);
};
B['remote-ci'] = (k) => {
  k.box(3.2, 4.2, 1.7, 'steel2', -1.6, 0, 0, 0.12);
  const im = k.inst(geo('rackled', () => new THREE.BoxGeometry(0.32, 0.12, 0.05)), k.S.reg(new THREE.MeshStandardMaterial({ color: 0x58d68d, emissive: 0x58d68d, emissiveIntensity: 1.0 })), 24);
  const o = new THREE.Object3D(); for (let i = 0; i < 24; i++) { o.position.set(-2.6 + (i % 4) * 0.62, 0.6 + ((i / 4) | 0) * 0.6, 0.88); o.updateMatrix(); im.setMatrixAt(i, o.matrix); }
  im.computeBoundingSphere();
  k.cyl(0.18, 4.6, 'steel2', 1.9, 0, 0, 12);
  const seg = [[C.red, 0.05], [C.gold, 0.05], [C.green, 1.4]].map(([c, e], i) => { const m = k.S.reg(new THREE.MeshStandardMaterial({ color: c, emissive: c, emissiveIntensity: e, roughness: 0.4, transparent: true, opacity: 0.92 })); k.cyl(0.36, 0.55, m, 1.9, 4.6 + i * 0.6, 0, 20); return m; });
  return { state(s) { const idx = { block: 0, fail: 0, stop: 0, gate: 1, ask: 1, pass: 2 }[s] ?? 2; seg.forEach((m, i) => (m.emissiveIntensity = i === idx ? 1.5 : 0.05)); } };
};

// ---- outside
B.network = (k) => {
  k.cyl(1.2, 0.4, 'steel', 0, 0, 0, 20); k.cyl(0.18, 6.6, 'steel2', 0, 0.4, 0, 10);
  const d = k.cap(1.3, 'trim', 0, 6.4, 0.3, 0.8); d.rotation.x = -0.9; d.material.side = THREE.DoubleSide;
  const l = k.lamp(C.blue, 0, 7.4, 0, 0.14, 1.0);
  return { tick(t) { const on = t % 3 < 0.2; l.set(C.blue, on ? 1.8 : 0.1, on ? 0.6 : 0.05); } };
};
B.farm = (k) => {
  k.box(3.2, 5.2, 1.9, 'steel2', 0, 0, -0.6, 0.12);
  k.box(3.3, 0.12, 2.0, 'orange', 0, 5.2, -0.6, 0.03);
  const lamps = []; for (let i = 0; i < 8; i++) lamps.push(k.lamp(C.orange, -1.1 + (i % 4) * 0.72, 1.2 + ((i / 4) | 0) * 2.2, 0.38, 0.09, 0.5));
  k.box(1.0, 1.0, 1.0, 'steel2', 0, 0.4, 2.4, 0.1);
  k.tube([V(0, 0.9, 0.4), V(0, 0.9, 1.9)], 0.12, 'orange', 6);
  return { tick(t) { lamps.forEach((l, i) => { const on = Math.sin(t * 2 + i * 1.3) > 0.4; l.set(C.orange, on ? 1.3 : 0.1, on ? 0.4 : 0); }); } };
};
B.sandbox = (k) => {
  k.box(4.8, 0.4, 4.8, 'steel', 0, 0, 0, 0.1);
  k.box(4.8, 0.08, 0.12, 'orange', 0, 0.4, 2.36, 0.02);
  k.box(4.3, 3.2, 4.3, 'glass', 0, 0.45, 0, 0.06);
  k.cyl(0.38, 1.5, 'blueDim', 0, 0.45, 0, 16); k.tor(1.1, 0.08, 'steel2', 0, 1.0, 0);
};

// ---- you
B.operator = (k) => {
  k.box(7.2, 1.1, 2.7, 'steel', 0, 0, 0, 0.15);
  const top = k.sub(0, 1.2, 0.2); top.g.rotation.x = -0.28; top.box(6.8, 0.12, 1.7, 'screen', 0, 0, 0, 0.04);
  for (const x of [-1.5, 1.5]) { k.box(0.12, 0.7, 0.12, 'steel2', x, 1.1, 0.85, 0.02); k.box(2.6, 1.55, 0.1, 'screen', x, 1.8, 0.9, 0.04); }
  k.tubeAbs([polar(64.4, 0, 1.25), polar(48, 0, 1.25), polar(32, 0, 1.25), polar(28.4, 0, 1.25)], 0.3, 'steel2', 24);
  for (const r of [60, 52, 44, 36, 31]) { const p = k.local(polar(r, 0, 0)); k.cyl(0.1, 1.0, 'steel', p.x, 0, p.z, 8); k.box(0.7, 0.12, 0.5, 'steel2', p.x, 0, p.z, 0.02); }
};
B.confirm = (k) => {
  k.box(1.3, 1.15, 1.1, 'steel2', 0, 0, 0, 0.1);
  k.box(0.32, 0.05, 0.85, 'dark', 0, 1.15, 0, 0.01);
  const lv = k.sub(0, 1.2, 0); lv.g.rotation.x = 0.45; lv.box(0.14, 1.4, 0.14, 'trim', 0, 0, 0, 0.03); lv.sph(0.23, 'gold', 0, 1.45, 0, 16);
  return { lever: lv };
};
B['approval-key'] = (k) => {
  k.cyl(0.62, 1.15, 'steel2', 0, 0, 0, 24);
  k.cyl(0.44, 0.12, 'trim', 0, 1.15, 0, 24);
  const key = k.sub(0, 1.27, 0);
  key.box(0.08, 0.4, 0.05, 'gold', 0, 0, 0, 0.01); key.tor(0.2, 0.06, 'gold', 0, 0.6, 0, 0, Math.PI * 2, 20);
  return { key };
};

/* ---------------------------------------------------------------- decor */

function decor(scene) {
  const S = scope();
  const g = new THREE.Group();
  const c = document.createElement('canvas'); c.width = c.height = 2048;
  const x = c.getContext('2d');
  const gr = x.createRadialGradient(1024, 1024, 0, 1024, 1024, 1024);
  gr.addColorStop(0, '#16222f'); gr.addColorStop(0.35, '#101924'); gr.addColorStop(0.8, '#0b1118'); gr.addColorStop(1, '#090d12');
  x.fillStyle = gr; x.fillRect(0, 0, 2048, 2048);
  // engineering grid: 2.5-unit minor and 25-unit major lines (canvas spans 300 units)
  const ppu = 2048 / 300;
  for (let i = -60; i <= 60; i++) {
    const p = 1024 + i * 2.5 * ppu, major = i % 10 === 0;
    x.strokeStyle = major ? 'rgba(124,196,255,0.075)' : 'rgba(199,208,218,0.035)';
    x.lineWidth = major ? 1.6 : 1;
    x.beginPath(); x.moveTo(p, 0); x.lineTo(p, 2048); x.moveTo(0, p); x.lineTo(2048, p); x.stroke();
  }
  const vg = x.createRadialGradient(1024, 1024, 700, 1024, 1024, 1024);
  vg.addColorStop(0, 'rgba(9,13,18,0)'); vg.addColorStop(1, 'rgba(9,13,18,1)');
  x.fillStyle = vg; x.fillRect(0, 0, 2048, 2048);
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
  const floor = new THREE.Mesh(new THREE.CircleGeometry(150, 96), new THREE.MeshStandardMaterial({ map: tex, metalness: 0.35, roughness: 0.82 }));
  floor.rotation.x = -Math.PI / 2; g.add(floor);
  const line = S.reg(new THREE.MeshBasicMaterial({ color: 0x273647 }));
  const lineB = S.reg(new THREE.MeshBasicMaterial({ color: 0x1b2836 }));
  for (const r of [10.9, 31.5, 41.5, 44.4, 55.6, 62.5, 70, 100]) { const m = new THREE.Mesh(flatRing(r - 0.07, r + 0.07, 0, 360, 256), r === 44.4 || r === 55.6 ? line : lineB); m.position.y = 0.02; g.add(m); }
  // family sector plates on the lane band
  const angs = laneAngles();
  const plate = S.reg(new THREE.MeshStandardMaterial({ color: 0x172231, metalness: 0.45, roughness: 0.7 }));
  const fams = [];
  for (const [fam, cmds] of LANE_ORDER) {
    const a0 = angs['ca-' + cmds[0]] - 4.6, a1 = angs['ca-' + cmds[cmds.length - 1]] + 4.6;
    const m = new THREE.Mesh(flatRing(44.6, 55.4, a0, a1, 64), plate); m.position.y = 0.035; g.add(m);
    for (const a of [a0, a1]) { const t = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.08, 11), S.m('trim')); t.position.copy(polar(50, a, 0.06)); t.rotation.y = rad(a); g.add(t); }
    fams.push({ fam, mid: (a0 + a1) / 2 });
  }
  // core plinth
  const pl = new THREE.Mesh(new THREE.CylinderGeometry(10.4, 10.7, 0.9, 72), S.m('steel')); pl.position.y = 0.45; g.add(pl);
  const glowBlue = S.reg(new THREE.MeshBasicMaterial({ color: new THREE.Color(C.blue).multiplyScalar(1.9) }));
  const pt = new THREE.Mesh(new THREE.TorusGeometry(10.4, 0.08, 8, 160), glowBlue); pt.rotation.x = Math.PI / 2; pt.position.y = 0.9; g.add(pt);
  const glowDim = S.reg(new THREE.MeshBasicMaterial({ color: new THREE.Color(C.blue).multiplyScalar(0.75) }));
  for (const r of [15.6, 18.4]) { const l = new THREE.Mesh(flatRing(r - 0.06, r + 0.06, 0, 360, 256), glowDim); l.position.y = 0.05; g.add(l); }
  const wallLine = S.reg(new THREE.MeshBasicMaterial({ color: new THREE.Color(0xc7d0da).multiplyScalar(0.55) }));
  for (const r of [25.95, 28.05]) { const l = new THREE.Mesh(flatRing(r - 0.05, r + 0.05, 0, 360, 256), wallLine); l.position.y = 0.05; g.add(l); }
  // walkway in the aisle
  const walk = new THREE.Mesh(new THREE.BoxGeometry(5.2, 0.06, 36), S.m('panel')); walk.position.set(0, 0.04, 46); g.add(walk);
  g.traverse((o) => { o.userData.nopick = true; });
  scene.add(g);
  return { group: g, families: fams };
}

/* ---------------------------------------------------------------- static batching */

// Parts with no animation hooks are merged into one mesh per material, which cuts draw calls.
// Only direct children are merged; animated sub-groups and instanced meshes are left alone.
function mergeStatic(g) {
  const buckets = new Map();
  for (const o of g.children) {
    if (!o.isMesh || o.isInstancedMesh || o.userData.nopick || o.userData.dyn || o.children.length) continue;
    const key = o.material.uuid + (o.geometry.index ? ':i' : ':n');
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(o);
  }
  for (const list of buckets.values()) {
    if (list.length < 2) continue;
    const geos = list.map((o) => { o.updateMatrix(); const c = o.geometry.clone(); c.applyMatrix4(o.matrix); return c; });
    const merged = THREE.mergeGeometries(geos, false);
    geos.forEach((x) => x.dispose());
    if (!merged) continue;
    list.forEach((o) => g.remove(o));
    g.add(new THREE.Mesh(merged, list[0].material));
  }
}

/* ---------------------------------------------------------------- build */

export function getGlow() { GLOW = GLOW || glowTexture(); return GLOW; }

export function buildMachine(scene, PARTS) {
  GLOW = GLOW || glowTexture();
  const parts = new Map();
  const pickables = [];
  const dec = decor(scene);
  const haloGeo = new THREE.RingGeometry(0.975, 1.0, 96); haloGeo.rotateX(-Math.PI / 2);

  for (const [id, meta] of Object.entries(PARTS)) {
    const pl = PLACE[id];
    const build = B[id];
    if (!pl || !build) { console.warn('no placement or builder for', id); continue; }
    const [r, a, y, face] = pl;
    const S = scope();
    const g = new THREE.Group();
    g.name = id;
    g.position.copy(polar(r, a, y));
    if (face === 'out') g.rotation.y = rad(a);
    else if (face === 'in') g.rotation.y = rad(a + 180);
    scene.add(g);
    g.updateMatrixWorld(true);
    const api = build(kit(g, S)) || {};
    mergeStatic(g);
    g.updateMatrixWorld(true);

    const box = new THREE.Box3();
    g.traverse((o) => { if (o.isMesh && !o.userData.nopick) { o.updateWorldMatrix(true, false); box.union(new THREE.Box3().setFromObject(o)); } });
    const sphere = box.getBoundingSphere(new THREE.Sphere());
    const center = box.getCenter(new THREE.Vector3());
    const anchor = api.anchor ? api.anchor.clone() : new THREE.Vector3(center.x, box.max.y, center.z);

    const haloMat = new THREE.MeshBasicMaterial({ color: 0xc7d0da, transparent: true, opacity: 0, depthWrite: false });
    const halo = new THREE.Mesh(haloGeo, haloMat);
    halo.visible = false;
    const hr = api.anchor ? 3.2 : Math.max(2.0, Math.min(8, Math.hypot(box.max.x - box.min.x, box.max.z - box.min.z) * 0.56));
    halo.scale.setScalar(hr);
    halo.position.set(api.anchor ? anchor.x : center.x, 0.07, api.anchor ? anchor.z : center.z);
    halo.userData.nopick = true;
    scene.add(halo);

    const lampMat = new THREE.SpriteMaterial({ map: GLOW, color: C.blue, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const lamp = new THREE.Sprite(lampMat);
    lamp.visible = false;
    lamp.scale.set(4, 4, 1);
    lamp.position.copy(anchor).add(new THREE.Vector3(0, 1.3, 0));
    lamp.userData.nopick = true;
    scene.add(lamp);

    g.traverse((o) => { if ((o.isMesh || o.isInstancedMesh) && !o.userData.nopick) { o.userData.pid = id; pickables.push(o); } });
    const mats = S.list.map((m) => ({ m, op: m.opacity, tr: m.transparent, dw: m.depthWrite, em: m.emissive ? m.emissive.clone() : null, ei: m.emissiveIntensity }));
    const radial = Math.hypot(center.x, center.z);
    parts.set(id, { id, meta, group: g, api, mats, center, sphere, anchor, halo, lamp, radial, angle: a, face, zone: meta.zone });
  }
  // soft contact shadows under everything outside the core, merged into a single draw call
  const sc = document.createElement('canvas'); sc.width = sc.height = 128;
  const sx = sc.getContext('2d'); const sg = sx.createRadialGradient(64, 64, 0, 64, 64, 64);
  sg.addColorStop(0, 'rgba(0,0,0,0.62)'); sg.addColorStop(0.55, 'rgba(0,0,0,0.28)'); sg.addColorStop(1, 'rgba(0,0,0,0)');
  sx.fillStyle = sg; sx.fillRect(0, 0, 128, 128);
  const pos = [], uv = [], idx = [];
  for (const p of parts.values()) {
    if (p.zone === 'model' || (p.radial < 3 && p.sphere.radius > 12) || p.id === 'branch-rails') continue;
    const bb = new THREE.Box3(); p.group.traverse((o) => { if (o.isMesh && !o.userData.nopick) bb.union(new THREE.Box3().setFromObject(o)); });
    const r = Math.max(bb.max.x - bb.min.x, bb.max.z - bb.min.z) * 0.78 + 0.8;
    const cx = (bb.min.x + bb.max.x) / 2, cz = (bb.min.z + bb.max.z) / 2, n = pos.length / 3;
    pos.push(cx - r, 0.045, cz - r, cx + r, 0.045, cz - r, cx + r, 0.045, cz + r, cx - r, 0.045, cz + r);
    uv.push(0, 0, 1, 0, 1, 1, 0, 1);
    idx.push(n, n + 2, n + 1, n, n + 3, n + 2);
  }
  const sgeo = new THREE.BufferGeometry();
  sgeo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  sgeo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  sgeo.setIndex(idx);
  const stex = new THREE.CanvasTexture(sc);
  const shadows = new THREE.Mesh(sgeo, new THREE.MeshBasicMaterial({ map: stex, transparent: true, depthWrite: false, color: 0xffffff }));
  shadows.userData.nopick = true; shadows.renderOrder = -1;
  scene.add(shadows);

  return { parts, pickables, families: dec.families, laneAngles: LA, ticks: T };
}
