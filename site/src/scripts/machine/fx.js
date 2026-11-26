// Visual effects: bloom, token streams, dust, idle tool traffic, gate flashes, power-on sequence.
// Everything here is decoration on top of the machine; the teaching content never depends on it.
import * as THREE from './three.js';
import { polar } from './machine.js';

const V = (x, y, z) => new THREE.Vector3(x, y, z);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const easeOutBack = (u) => { const c1 = 1.5, c3 = c1 + 1; return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2; };

export function createFX({ renderer, scene, camera, M, glow, C }) {
  /* ---------------------------------------------------------- post-processing */
  const composer = new THREE.EffectComposer(renderer);
  composer.addPass(new THREE.RenderPass(scene, camera));
  // strength is set per frame by the app from camera distance: rich from afar, restrained up close
  const bloom = new THREE.UnrealBloomPass(new THREE.Vector2(512, 512), 0.55, 0.45, 0.82);
  composer.addPass(bloom);
  composer.addPass(new THREE.OutputPass());
  let high = true;

  /* ---------------------------------------------------------- shared helpers */
  const pointsMat = (color, size, opacity) => new THREE.PointsMaterial({ map: glow, color, size, sizeAttenuation: true, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false, vertexColors: false });
  const anchor = (id) => M.parts.get(id).anchor.clone().add(V(0, 0.4, 0));

  /* ---------------------------------------------------------- dust */
  const DN = 650;
  const dustGeo = new THREE.BufferGeometry();
  const dp = new Float32Array(DN * 3), dv = new Float32Array(DN);
  for (let i = 0; i < DN; i++) {
    const r = 6 + Math.sqrt(Math.random()) * 104, a = Math.random() * Math.PI * 2;
    dp[i * 3] = r * Math.sin(a); dp[i * 3 + 1] = 0.5 + Math.random() * 42; dp[i * 3 + 2] = r * Math.cos(a);
    dv[i] = 0.15 + Math.random() * 0.35;
  }
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dp, 3));
  const dust = new THREE.Points(dustGeo, pointsMat(0x9fb7d4, 0.45, 0.32));
  dust.frustumCulled = false;
  scene.add(dust);

  /* ---------------------------------------------------------- inference stream */
  const helix = [];
  for (let i = 0; i <= 14; i++) { const u = i / 14; helix.push(polar(3.85, -330 + 395 * u, 20.0 - 4.9 * u)); }
  const streamCurve = new THREE.CatmullRomCurve3([
    polar(16.4, 0, 1.4), polar(12.5, 0, 1.7), polar(9.4, 0, 2.4), polar(7.4, 0, 2.7), polar(4.9, 0, 2.3),
    V(0, 2.9, 1.0), V(0, 7, 0.2), V(0, 12, 0.2), V(0, 16.8, 0.3), V(0, 18.9, 0.9), V(0, 20.6, 0.5),
    ...helix, V(5.8, 14.9, 2.1), V(6.6, 14.4, 2.0), V(6.6, 10.5, 2.0),
  ], false, 'centripetal');
  const SN = 110;
  const sGeo = new THREE.BufferGeometry();
  const sp = new Float32Array(SN * 3), sc = new Float32Array(SN * 3), sj = new Float32Array(SN * 3);
  for (let i = 0; i < SN; i++) { sj[i * 3] = (Math.random() - 0.5) * 0.5; sj[i * 3 + 1] = (Math.random() - 0.5) * 0.5; sj[i * 3 + 2] = (Math.random() - 0.5) * 0.5; }
  sGeo.setAttribute('position', new THREE.BufferAttribute(sp, 3));
  sGeo.setAttribute('color', new THREE.BufferAttribute(sc, 3));
  const sMat = new THREE.PointsMaterial({ map: glow, size: 0.75, sizeAttenuation: true, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false, vertexColors: true });
  const stream = new THREE.Points(sGeo, sMat);
  stream.frustumCulled = false;
  scene.add(stream);
  const cBlue = new THREE.Color(C.blue), cWhite = new THREE.Color(0xe6f3ff), tmp = new THREE.Color(), pv = new THREE.Vector3();
  let streamBoost = 0;

  /* ---------------------------------------------------------- agent loop trails */
  const LN = 84;
  const lGeo = new THREE.BufferGeometry();
  const lp = new Float32Array(LN * 3), lc = new Float32Array(LN * 3);
  lGeo.setAttribute('position', new THREE.BufferAttribute(lp, 3));
  lGeo.setAttribute('color', new THREE.BufferAttribute(lc, 3));
  const loopPts = new THREE.Points(lGeo, new THREE.PointsMaterial({ map: glow, size: 0.6, sizeAttenuation: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false, vertexColors: true }));
  loopPts.frustumCulled = false;
  scene.add(loopPts);

  /* ---------------------------------------------------------- one-shot pods (idle traffic, lab effects) */
  const podGeo = new THREE.SphereGeometry(0.38, 14, 10);
  const pods = Array.from({ length: 8 }, () => {
    const m = new THREE.Mesh(podGeo, new THREE.MeshBasicMaterial({ color: C.blue }));
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glow, color: C.blue, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false }));
    s.scale.set(2.8, 2.8, 1); m.add(s); m.visible = false; scene.add(m);
    return { m, s, busy: false };
  });
  const arcCurve = (a, b, lift = 1) => { const mid = a.clone().add(b).multiplyScalar(0.5); mid.y = Math.max(a.y, b.y) + (2.5 + a.distanceTo(b) * 0.2) * lift; return new THREE.QuadraticBezierCurve3(a, mid, b); };
  // path: array of points (world). Pod travels segments in sequence; onArrive(i) fires per waypoint.
  function launch(path, color, speed = 26, onArrive) {
    const p = pods.find((q) => !q.busy); if (!p) return null;
    const segs = [];
    for (let i = 0; i < path.length - 1; i++) { const c = arcCurve(path[i], path[i + 1], i === path.length - 2 ? 1 : 0.6); segs.push({ c, len: c.getLength() }); }
    Object.assign(p, { busy: true, segs, i: 0, d: 0, speed, onArrive });
    p.m.material.color.set(color); p.s.material.color.set(color); p.m.visible = true;
    p.m.position.copy(path[0]);
    return p;
  }
  function tickPods(dt) {
    for (const p of pods) {
      if (!p.busy) continue;
      const seg = p.segs[p.i];
      p.d += p.speed * dt;
      if (p.d >= seg.len) {
        p.d -= seg.len; p.i++;
        p.onArrive?.(p.i);
        if (p.i >= p.segs.length) { p.busy = false; p.m.visible = false; continue; }
      }
      const s2 = p.segs[p.i];
      p.m.position.copy(s2.c.getPoint(clamp(p.d / s2.len, 0, 1)));
    }
  }

  /* ---------------------------------------------------------- gate effects */
  const flash = new THREE.PointLight(0xff5a4f, 0, 34, 1.6);
  scene.add(flash);
  const BN = 70;
  const bGeo = new THREE.BufferGeometry();
  const bp = new Float32Array(BN * 3), bv = new Float32Array(BN * 3);
  bGeo.setAttribute('position', new THREE.BufferAttribute(bp, 3));
  const burst = new THREE.Points(bGeo, pointsMat(0xff8a5c, 0.7, 0));
  burst.frustumCulled = false;
  scene.add(burst);
  let burstT = -1, flashT = -1, shakeT = 0;
  const shakeOff = new THREE.Vector3();
  const rippleGeo = new THREE.RingGeometry(0.92, 1, 64); rippleGeo.rotateX(-Math.PI / 2);
  const ripples = Array.from({ length: 4 }, () => { const m = new THREE.Mesh(rippleGeo, new THREE.MeshBasicMaterial({ color: C.green, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending })); m.visible = false; scene.add(m); return { m, t: -1 }; });

  function sparks(at, color, lift = 1) {
    burst.material.color.set(color);
    for (let i = 0; i < BN; i++) {
      bp[i * 3] = at.x; bp[i * 3 + 1] = at.y; bp[i * 3 + 2] = at.z;
      const a = Math.random() * Math.PI * 2, s = 4 + Math.random() * 9;
      bv[i * 3] = Math.cos(a) * s * 0.6; bv[i * 3 + 1] = (5 + Math.random() * 9) * lift; bv[i * 3 + 2] = Math.sin(a) * s * 0.6;
    }
    bGeo.attributes.position.needsUpdate = true;
    burstT = 0;
  }
  function slam(id, motion = true) {
    const p = M.parts.get(id); if (!p) return;
    const at = p.sphere.center.clone(); at.y = Math.max(2.5, at.y);
    flash.color.set(0xff5a4f); flash.position.copy(at).add(V(0, 2, 0)); flashT = 0;
    sparks(at, 0xff8a5c);
    ripple(id, C.red);
    if (motion) shakeT = 0.38;
  }
  function celebrate(id) {
    const p = M.parts.get(id); if (!p) return;
    const at = p.sphere.center.clone(); at.y = Math.max(3, at.y);
    flash.color.set(0x58d68d); flash.position.copy(at).add(V(0, 3, 0)); flashT = 0;
    sparks(at, 0xb6f5cf, 1.35);
    ripple(id, C.green); setTimeout(() => ripple(id, C.gold), 260); setTimeout(() => ripple(id, C.green), 520);
  }
  function ripple(id, color = C.green) {
    const p = M.parts.get(id); if (!p) return;
    const r = ripples.find((q) => q.t < 0) || ripples[0];
    r.m.material.color.set(color);
    r.m.position.set(p.sphere.center.x, 0.09, p.sphere.center.z);
    r.t = 0; r.m.visible = true;
  }

  /* ---------------------------------------------------------- idle tool traffic */
  const routes = [
    { arm: 'tool-read', gate: null, color: C.blue },
    { arm: 'tool-bash', gate: 'guard-bash', color: C.blue },
    { arm: 'tool-write', gate: 'guard-write', color: C.blue },
    { arm: 'tool-read', gate: null, color: C.blue },
  ];
  let trafficT = 3, trafficOn = true, busyGates = new Set();
  function traffic(dt) {
    if (!trafficOn) return;
    trafficT -= dt;
    if (trafficT > 0) return;
    trafficT = 4.5 + Math.random() * 4;
    const r = routes[(Math.random() * routes.length) | 0];
    if (r.gate && busyGates.has(r.gate)) return;
    const repo = M.parts.get('repo').sphere.center.clone(); repo.y = 3;
    const path = [anchor('tool-router'), anchor(r.arm)];
    if (r.gate) path.push(anchor(r.gate));
    path.push(repo);
    launch(path, r.color, 30, (i) => {
      if (r.gate && i === 2 && !busyGates.has(r.gate)) { const g = M.parts.get(r.gate).api; g.lamps?.forEach((l) => l.set(C.green, 1.4, 0.5)); setTimeout(() => { if (!busyGates.has(r.gate)) g.idle?.(); }, 700); }
    });
  }

  /* ---------------------------------------------------------- power-on sequence */
  const ZD = { model: 0.15, harness: 0.75, guards: 1.35, skills: 1.95, you: 3.9, record: 4.1, world: 4.3, outside: 4.5 };
  let bootT = -1, bootDone = null, bootSpeed = 1, bootStart = 0;
  const bootList = [...M.parts.values()].map((p) => {
    let d = ZD[p.zone] ?? 2.4;
    if (p.zone === 'lanes') d = 2.4 + ((((p.angle - 20) % 360) + 360) % 360) / 360 * 1.5;
    return { p, d };
  });
  // wall-clock timing, so a slow device still finishes on schedule (and stays in step with the intro captions)
  function boot(done, speed = 1) {
    bootT = 0; bootDone = done; bootSpeed = speed; bootStart = performance.now();
    for (const { p } of bootList) p.group.scale.setScalar(0.0001);
  }
  function tickBoot() {
    if (bootT < 0) return false;
    bootT = ((performance.now() - bootStart) / 1000) * bootSpeed;
    let all = true;
    for (const { p, d } of bootList) {
      const u = clamp((bootT - d) / 0.7, 0, 1);
      if (u < 1) all = false;
      p.group.scale.setScalar(Math.max(0.0001, u === 1 ? 1 : easeOutBack(u)));
      const f = clamp((bootT - d) / 0.9, 0, 1);
      if (f > 0 && f < 1) { p.halo.visible = true; p.halo.material.opacity = 0.7 * (1 - f); }
      else if (f >= 1 && p.booted !== true) { p.booted = true; if (!p.keepHalo) { p.halo.material.opacity = 0; p.halo.visible = false; } }
    }
    if (all) { bootT = -1; const d = bootDone; bootDone = null; d?.(); }
    return true;
  }
  function finishBoot() {
    if (bootT < 0) return;
    for (const { p } of bootList) { p.group.scale.setScalar(1); p.booted = true; p.halo.material.opacity = 0; p.halo.visible = false; }
    bootT = -1; const d = bootDone; bootDone = null; d?.();
  }

  /* ---------------------------------------------------------- tick and render */
  let streamT = 0;
  function tick(dt, motion) {
    tickBoot();
    if (motion) {
      for (let i = 0; i < DN; i++) { dp[i * 3 + 1] += dv[i] * dt; if (dp[i * 3 + 1] > 44) dp[i * 3 + 1] = 0.5; }
      dustGeo.attributes.position.needsUpdate = true;
      streamT += dt * (0.055 + streamBoost * 0.08);
      streamBoost = Math.max(0, streamBoost - dt * 0.4);
    }
    for (let i = 0; i < SN; i++) {
      const u = (streamT + i / SN) % 1;
      streamCurve.getPointAt(u, pv);
      sp[i * 3] = pv.x + sj[i * 3]; sp[i * 3 + 1] = pv.y + sj[i * 3 + 1]; sp[i * 3 + 2] = pv.z + sj[i * 3 + 2];
      const hot = Math.exp(-((u - 0.47) ** 2) / 0.004);
      tmp.copy(cBlue).lerp(cWhite, hot * 0.8).multiplyScalar(0.55 + 0.45 * Math.sin(i * 12.9898) ** 2 + streamBoost * 0.6);
      sc[i * 3] = tmp.r; sc[i * 3 + 1] = tmp.g; sc[i * 3 + 2] = tmp.b;
    }
    sGeo.attributes.position.needsUpdate = true; sGeo.attributes.color.needsUpdate = true;
    // agent-loop trails behind the seven pods (pods move at 0.035 turns per second in machine.js)
    const t = performance.now() / 1000;
    for (let i = 0; i < LN; i++) {
      const pod = i % 7, k = (i / 7) | 0, behind = k * 0.0035;
      const a = ((pod / 7 + (motion ? t * 0.035 : 0) - behind) % 1) * 360;
      const v = polar(17, a, 1.62);
      lp[i * 3] = v.x; lp[i * 3 + 1] = v.y; lp[i * 3 + 2] = v.z;
      const f = (1 - k / 12) * 0.8;
      lc[i * 3] = cBlue.r * f; lc[i * 3 + 1] = cBlue.g * f; lc[i * 3 + 2] = cBlue.b * f;
    }
    lGeo.attributes.position.needsUpdate = true; lGeo.attributes.color.needsUpdate = true;
    if (motion) { tickPods(dt); traffic(dt); }
    // flash, burst, ripples
    if (flashT >= 0) { flashT += dt; flash.intensity = 420 * Math.max(0, 1 - flashT / 0.9); if (flashT > 0.9) { flashT = -1; flash.intensity = 0; } }
    if (burstT >= 0) {
      burstT += dt;
      for (let i = 0; i < BN; i++) { bv[i * 3 + 1] -= 18 * dt; bp[i * 3] += bv[i * 3] * dt; bp[i * 3 + 1] = Math.max(0.15, bp[i * 3 + 1] + bv[i * 3 + 1] * dt); bp[i * 3 + 2] += bv[i * 3 + 2] * dt; }
      bGeo.attributes.position.needsUpdate = true;
      burst.material.opacity = Math.max(0, 1 - burstT / 1.3);
      if (burstT > 1.3) burstT = -1;
    }
    for (const r of ripples) {
      if (r.t < 0) continue;
      r.t += dt; const u = r.t / 1.3;
      r.m.scale.setScalar(1 + u * 11); r.m.material.opacity = 0.75 * (1 - u);
      if (u >= 1) { r.t = -1; r.m.visible = false; }
    }
    return bootT >= 0 || flashT >= 0 || burstT >= 0 || ripples.some((r) => r.t >= 0) || pods.some((p) => p.busy);
  }
  // camera shake: undo last offset before controls update, apply new after
  function unshake() { camera.position.sub(shakeOff); shakeOff.set(0, 0, 0); }
  function shake(dt) {
    if (shakeT <= 0) return;
    shakeT -= dt;
    const a = 0.45 * Math.max(0, shakeT / 0.38);
    shakeOff.set((Math.random() - 0.5) * a, (Math.random() - 0.5) * a, (Math.random() - 0.5) * a);
    camera.position.add(shakeOff);
  }
  function render() { if (high) composer.render(); else renderer.render(scene, camera); }
  function resize(w, h) { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(w, h); }
  function setQuality(q) {
    high = q === 'high';
    dust.visible = high;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, high ? 1.75 : 1));
  }

  return {
    render, resize, tick, setQuality, slam, celebrate, ripple, launch, boot, finishBoot, unshake, shake,
    pulseStream() { streamBoost = 1.4; },
    setTraffic(on) { trafficOn = on; },
    holdGate(id, on) { if (on) busyGates.add(id); else busyGates.delete(id); },
    get booting() { return bootT >= 0; },
    get high() { return high; },
    bloom,
  };
}
