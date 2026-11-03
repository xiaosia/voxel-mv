// S1 · Claude · 相遇 — voxel diorama MV segment (frames 0–687, global song time)
import * as THREE from 'three';

const FPS = 24, BEAT0 = 0.1406, SPB = 0.852;
const START_F = 0, END_F = 688;
const beatOf = t => (t - BEAT0) / SPB;
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const smooth = (a, b, x) => { x = clamp((x - a) / (b - a), 0, 1); return x * x * (3 - 2 * x); };
const lerp = (a, b, k) => a + (b - a) * k;
const easeIO = x => (x = clamp(x, 0, 1), x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const easeOut = x => 1 - Math.pow(1 - clamp(x, 0, 1), 3);
const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
const pulse = (f, f0, len) => (f >= f0 && f < f0 + len) ? Math.exp(-(f - f0) / (len / 3)) : 0;

// ---------- renderer ----------
const canvas = document.getElementById('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(1920, 1080, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(28, 1920 / 1080, 0.1, 400);
scene.fog = new THREE.Fog(0xcfc8e8, 30, 120);

const hemi = new THREE.HemisphereLight(0xe6e0ff, 0x8d8399, 1.1);
scene.add(hemi);
const key = new THREE.DirectionalLight(0xfff0dc, 2.4);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -18, right: 18, top: 18, bottom: -18, near: 1, far: 80 });
key.shadow.bias = -0.0008;
key.shadow.radius = 4;
scene.add(key, key.target);

// ---------- voxel helpers ----------
const boxGeo = new THREE.BoxGeometry(1, 1, 1);
const paintables = []; // town elements that go grey → colour
function box(parent, w, h, d, color, x, y, z, o = {}) {
  const m = new THREE.Mesh(boxGeo, new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, emissive: o.emissive || 0x000000, emissiveIntensity: o.ei ?? 1, transparent: !!o.opacity, opacity: o.opacity ?? 1 }));
  m.scale.set(w, h, d);
  m.position.set(x, y + h / 2, z);
  m.castShadow = o.cast ?? true; m.receiveShadow = true;
  parent.add(m);
  if (o.paint) paintables.push({ m, c: new THREE.Color(color), e: new THREE.Color(o.emissive || 0x000000) });
  return m;
}
function instanced(parent, n, color, o = {}) {
  const im = new THREE.InstancedMesh(boxGeo, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, emissive: o.emissive || 0, transparent: !!o.opacity, opacity: o.opacity ?? 1 }), n);
  im.castShadow = o.cast ?? false; im.receiveShadow = true;
  im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  parent.add(im);
  return im;
}
const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = new THREE.Vector3(), _p = new THREE.Vector3(), _e = new THREE.Euler();
function setInst(im, i, x, y, z, sx, sy, sz, rx = 0, ry = 0, rz = 0) {
  _e.set(rx, ry, rz); _q.setFromEuler(_e); _p.set(x, y, z); _s.set(sx, sy, sz);
  _m.compose(_p, _q, _s); im.setMatrixAt(i, _m);
}
const grey = c => { const l = c.r * 0.3 + c.g * 0.55 + c.b * 0.15; return new THREE.Color(l * 0.92, l * 0.92, l * 0.98); };

// =====================================================================
// SET A — grey town (origin)
// =====================================================================
const town = new THREE.Group(); scene.add(town);
const townTiles = [];
{
  const nx = 96, nz = 30, n = nx * nz;
  const im = instanced(town, n, 0xffffff);
  let i = 0;
  for (let ix = 0; ix < nx; ix++) for (let iz = 0; iz < nz; iz++) {
    const x = -24 + ix * 0.5 + 0.25, z = -9 + iz * 0.5 + 0.25;
    const street = z > -3.5 && z < 2.5;
    const h = 0.2 + hash(i * 3.1) * 0.06;
    setInst(im, i, x, h / 2 - 0.1, z, 0.48, h, 0.48);
    const base = street ? new THREE.Color().setHSL(0.08, 0.25, 0.62 + hash(i) * 0.08) : new THREE.Color().setHSL(0.28, 0.45, 0.5 + hash(i) * 0.08);
    townTiles.push({ x, z, c: base });
    im.setColorAt(i, base); i++;
  }
  im.userData.tiles = townTiles; town.userData.tiles = im;
  // houses
  const walls = [0xf6e3c8, 0xf3c6cf, 0xcfe8d5, 0xf7d2b2, 0xd9d4f3, 0xf1e9a8];
  const roofs = [0xc8664f, 0x5b7fc0, 0xb05a7a, 0x4f9a8a];
  let k = 0;
  for (let x = -22; x <= 22; x += 5.5, k++) {
    const h = 3.2 + hash(k * 7.7) * 1.6, w = 4.4, d = 3, z = -6.2;
    const wc = walls[k % walls.length], rc = roofs[k % roofs.length];
    box(town, w, h, d, wc, x, 0, z, { paint: 1 });
    for (let s = 0; s < 3; s++) box(town, w + 0.4 - s * 1.4, 0.55, d + 0.4 - s * 0.8, rc, x, h + s * 0.55, z, { paint: 1 });
    box(town, 0.9, 1.6, 0.2, 0x7a4e35, x - 1.2, 0, z + 1.55, { paint: 1 });
    for (let wx = 0; wx < 2; wx++) box(town, 0.8, 0.8, 0.12, 0x3a3a48, x + 0.4 + wx * 1.1, 1.4, z + 1.56, { paint: 1, emissive: 0xffc46b, ei: 0.0 });
    box(town, 0.5, 0.9, 0.5, 0x8c8c8c, x + 1.4, h + 1.0, z - 0.6, { paint: 1 }); // chimney
  }
  // trees and flower boxes
  for (let j = 0; j < 8; j++) {
    const x = -20 + j * 6 + 2.7, z = -3.9;
    box(town, 0.3, 1.1, 0.3, 0x7b5236, x, 0, z, { paint: 1 });
    box(town, 1.3, 0.9, 1.3, 0x5fae5a, x, 1.1, z, { paint: 1 });
    box(town, 0.9, 0.6, 0.9, 0x79c66a, x, 2.0, z, { paint: 1 });
  }
  // far hills
  for (let j = 0; j < 12; j++) box(town, 7, 3 + hash(j) * 5, 4, 0x8fbf8a, -36 + j * 6.5, 0, -18 - hash(j + 3) * 4, { paint: 1, cast: false });
  // lamppost
  box(town, 0.18, 3.2, 0.18, 0x3b3646, -6, 0, -1.6, { paint: 1 });
  box(town, 0.9, 0.12, 0.18, 0x3b3646, -5.6, 3.1, -1.6, { paint: 1 });
  town.userData.lamp = box(town, 0.45, 0.4, 0.45, 0xfff1c9, -5.2, 2.75, -1.6, { emissive: 0xffd27a, ei: 0.2 });
}
// grey crowd (simple voxel people)
const crowd = [];
for (let i = 0; i < 5; i++) {
  const g = new THREE.Group();
  box(g, 0.7, 0.9, 0.5, 0x8a8a96, 0, 0, 0); box(g, 0.75, 0.7, 0.6, 0x9a9aa6, 0, 0.9, 0);
  box(g, 0.2, 0.35, 0.2, 0x6f6f7a, -0.18, -0.35, 0); box(g, 0.2, 0.35, 0.2, 0x6f6f7a, 0.18, -0.35, 0);
  g.children.forEach(c => c.position.y += 0.35);
  town.add(g); crowd.push(g);
}

// rain (shared, moved to wherever the camera looks)
const RAIN_N = 700;
const rain = instanced(scene, RAIN_N, 0xffffff, { opacity: 0.55 });
rain.material.color.set(0xc9d2e8); rain.castShadow = false;

// =====================================================================
// SET B — pier and sea (x = 200), SET C seawall (x = 400), SET D beach (x = 600)
// =====================================================================
function makeSea(parent, ox, oz, nx, nz, size) {
  const im = instanced(parent, nx * nz, 0xffffff);
  const cells = [];
  for (let ix = 0; ix < nx; ix++) for (let iz = 0; iz < nz; iz++) cells.push({ x: ox + ix * size, z: oz + iz * size });
  return { im, cells, size };
}
function updateSea(sea, t, cA, cB, amp = 0.25) {
  const { im, cells, size } = sea;
  const c = new THREE.Color();
  for (let i = 0; i < cells.length; i++) {
    const { x, z } = cells[i];
    const w = Math.sin(x * 0.55 + t * 1.6) * 0.5 + Math.sin(z * 0.8 - t * 2.1 + x * 0.2) * 0.5;
    const h = 1 + amp * w;
    setInst(im, i, x, -0.6 + h / 2 - 0.5, z, size * 0.96, h, size * 0.96);
    c.copy(cA).lerp(cB, clamp(0.5 + w * 0.5, 0, 1));
    im.setColorAt(i, c);
  }
  im.instanceMatrix.needsUpdate = true; im.instanceColor.needsUpdate = true;
}

const pierSet = new THREE.Group(); pierSet.position.x = 200; scene.add(pierSet);
const sea1 = makeSea(pierSet, -26, -30, 88, 84, 0.6);
{
  // pier boards
  for (let i = 0; i < 46; i++) box(pierSet, 0.58, 0.22, 2.6, i % 2 ? 0xb98a5e : 0xc99a6a, -16 + i * 0.6, 0.38, -5);
  for (let i = 0; i < 10; i++) { box(pierSet, 0.3, 1.4, 0.3, 0x7a5638, -15.5 + i * 3, -0.9, -6.2); box(pierSet, 0.3, 1.4, 0.3, 0x7a5638, -15.5 + i * 3, -0.9, -3.8); }
  // shore with town edge on the left
  box(pierSet, 10, 0.6, 30, 0xe9d3a3, -21, -0.1, -10);
  for (let j = 0; j < 4; j++) box(pierSet, 3.5, 3 + j % 2, 3, [0xf6e3c8, 0xf3c6cf, 0xcfe8d5, 0xf7d2b2][j], -24 + (j % 2) * 3, 0.5, -16 + j * 4.5);
  // sunset sun
  pierSet.userData.sun = box(pierSet, 6, 6, 0.5, 0xffd08a, 8, 1.5, -60, { emissive: 0xffb26b, ei: 1.4, cast: false });
  // falling town walls (foreground), pivot groups
  const mkWall = (sign) => {
    const piv = new THREE.Group(); piv.position.set(-1 + sign * 7.5, -0.6, 0.5); pierSet.add(piv);
    const facade = [0xf6e3c8, 0xf3c6cf, 0xcfe8d5, 0xf7d2b2, 0xd9d4f2];
    for (let bx = 0; bx < 15; bx++) for (let by = 0; by < 13; by++) {
      const house = Math.floor(bx / 5) + (sign > 0 ? 2 : 0);
      const c = new THREE.Color(facade[house % 5]).multiplyScalar((bx + by) % 2 ? 1 : 0.94).getHex();
      box(piv, 0.48, 0.48, 0.5, c, -sign * (bx * 0.5 + 0.25), by * 0.5, 0, { cast: true });
    }
    // windows, doors and roof trim per house
    for (let h = 0; h < 3; h++) {
      const cx = -sign * (h * 2.5 + 1.25);
      box(piv, 0.9, 0.9, 0.56, 0x6a7ec8, cx - 0.55, 4.0, 0, { emissive: 0xffd27a, ei: 0.35 });
      box(piv, 0.9, 0.9, 0.56, 0x6a7ec8, cx + 0.55, 4.0, 0, { emissive: 0xffd27a, ei: 0.35 });
      box(piv, 0.8, 1.6, 0.56, 0x8a5a3c, cx, 0.8, 0);
      box(piv, 2.5, 0.4, 0.7, [0xd8584f, 0x3f8f7a, 0xc0503a, 0x3f6fae][(h + (sign > 0 ? 1 : 0)) % 4], cx, 6.5, 0);
    }
    return piv;
  };
  pierSet.userData.wallL = mkWall(-1); pierSet.userData.wallR = mkWall(1);
}
const splash = instanced(pierSet, 60, 0xffffff); splash.material.color.set(0xffffff);
const sparkles = instanced(scene, 80, 0xffffff, { emissive: 0xffffff }); sparkles.material.emissiveIntensity = 0.9;

const wallSet = new THREE.Group(); wallSet.position.x = 400; scene.add(wallSet);
const sea2 = makeSea(wallSet, -24, -34, 80, 50, 0.6);
{
  for (let i = 0; i < 60; i++) box(wallSet, 0.5, 1.4, 1.8, i % 3 ? 0xb7b2c4 : 0xa9a3b8, -15 + i * 0.5, -0.6, 0.2);
  for (let i = 0; i < 60; i++) box(wallSet, 0.5, 0.2, 1.8, 0xd8d2e4, -15 + i * 0.5, 0.8 - 0.2, 0.2);
  box(wallSet, 40, 0.4, 10, 0xc9c1a6, 0, -0.9, 6);
  // lighthouse far away
  box(wallSet, 1.2, 6, 1.2, 0xf4f0f8, 14, -0.5, -26); box(wallSet, 1.6, 0.8, 1.6, 0xd8584f, 14, 5.5, -26, { emissive: 0xffd27a, ei: 0.4 });
}
// clouds: two banks that part
function mkCloud(parent, cx, cy, cz, seed, n = 26) {
  const g = new THREE.Group(); g.position.set(cx, cy, cz); parent.add(g);
  for (let i = 0; i < n; i++) {
    const s = 0.8 + hash(seed + i) * 1.4;
    box(g, s * 1.4, s, s, 0xffffff, (hash(seed + i * 2) - 0.5) * 7, (hash(seed + i * 3) - 0.5) * 1.4, (hash(seed + i * 5) - 0.5) * 3, { cast: false });
  }
  return g;
}
const cloudsL = [mkCloud(wallSet, -3, 8, -6, 10), mkCloud(wallSet, -7, 9.5, -10, 30)];
const cloudsR = [mkCloud(wallSet, 3, 8.4, -6, 50), mkCloud(wallSet, 7, 9.8, -10, 70)];
const shafts = [];
for (let i = 0; i < 4; i++) {
  const m = new THREE.Mesh(boxGeo, new THREE.MeshBasicMaterial({ color: 0xfff1c8, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
  m.scale.set(1.2 + i * 0.3, 14, 1.2); m.position.set(-2 + i * 1.6, 5, -3 - i); m.rotation.z = 0.25; wallSet.add(m); shafts.push(m);
}
// big leaf umbrella
const leaf = new THREE.Group(); wallSet.add(leaf);
for (let i = 0; i < 7; i++) box(leaf, 2.6 - Math.abs(i - 3) * 0.55, 0.14, 0.5, i % 2 ? 0x58b05a : 0x6cc56a, 0, 0, (i - 3) * 0.5, { cast: true });
box(leaf, 0.12, 1.6, 0.12, 0x4a8a3c, -0.6, -1.6, 0);

const beachSet = new THREE.Group(); beachSet.position.x = 600; scene.add(beachSet);
const sea3 = makeSea(beachSet, -24, -30, 80, 40, 0.6);
const sandTiles = [];
{
  const nx = 64, nz = 26;
  const im = instanced(beachSet, nx * nz, 0xffffff); let i = 0;
  for (let ix = 0; ix < nx; ix++) for (let iz = 0; iz < nz; iz++) {
    const x = -16 + ix * 0.5 + 0.25, z = -4 + iz * 0.5 + 0.25;
    const h = 0.4 + Math.max(0, Math.sin(x * 0.3) * 0.25 + Math.sin(z * 0.5 + x * 0.1) * 0.15) * (z > 3 ? 1 : 0.3) + hash(i) * 0.05;
    setInst(im, i, x, h / 2 - 0.4, z, 0.5, h, 0.5);
    im.setColorAt(i, new THREE.Color().setHSL(0.11, 0.55, 0.74 + hash(i * 1.7) * 0.06)); i++;
  }
  // shells / stones
  for (let j = 0; j < 14; j++) box(beachSet, 0.2, 0.12, 0.2, [0xf5c6d0, 0xffffff, 0xd9c6f5][j % 3], -6 + hash(j) * 12, 0, -2 + hash(j + 9) * 5);
}
const frags = []; // grey "unhappy" fragments
for (let j = 0; j < 26; j++) frags.push({ m: box(beachSet, 0.22, 0.22, 0.22, 0x7c7c86, -4 + hash(j * 4.1) * 8, 0, -1.5 + hash(j * 2.3) * 4), x0: 0, y0: 0, z0: 0 });
frags.forEach(f => { f.x0 = f.m.position.x; f.y0 = f.m.position.y; f.z0 = f.m.position.z; });

// glowing puzzle piece (voxel)
const puzzle = new THREE.Group(); scene.add(puzzle);
{
  const cells = [];
  for (let x = 0; x < 4; x++) for (let y = 0; y < 4; y++) cells.push([x, y]);
  cells.push([4, 1], [4, 2], [1, 4], [2, 4]); // tabs
  for (const [x, y] of cells) box(puzzle, 0.095, 0.095, 0.09, 0xffd36e, (x - 2) * 0.1, (y - 2) * 0.1, 0, { emissive: 0xffb43c, ei: 1.6, cast: false });
  const glowTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d'); const r = g.createRadialGradient(64, 64, 0, 64, 64, 64); r.addColorStop(0, 'rgba(255,220,140,0.9)'); r.addColorStop(1, 'rgba(255,200,120,0)'); g.fillStyle = r; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c); })();
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }));
  glow.scale.set(1.4, 1.4, 1); puzzle.add(glow); puzzle.userData.glow = glow;
}
const pLight = new THREE.PointLight(0xffc670, 0, 4); puzzle.add(pLight);

// =====================================================================
// characters (sprite billboards, unified height H)
// =====================================================================
const H = 2.0; // world height of a standing character (stand_h)
const loader = new THREE.TextureLoader();
const shadowTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d'); const r = g.createRadialGradient(32, 32, 0, 32, 32, 32); r.addColorStop(0, 'rgba(30,20,50,0.45)'); r.addColorStop(1, 'rgba(30,20,50,0)'); g.fillStyle = r; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();
async function loadChar(name) {
  const meta = await (await fetch(`assets/${name}/frames.json`)).json();
  const tex = {};
  const jobs = [];
  for (const [act, a] of Object.entries(meta.actions)) {
    tex[act] = [];
    a.frames.forEach((fr, i) => jobs.push(new Promise(res => loader.load(`assets/${name}/${fr.file}`, tx => { tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 4; tex[act][i] = tx; res(); }))));
  }
  await Promise.all(jobs);
  const k = H * (meta.mv_scale || 1) / meta.stand_h, cv = meta.canvas;
  const root = new THREE.Group(); scene.add(root);
  const pivot = new THREE.Group(); root.add(pivot); // for lean
  const mat = new THREE.MeshBasicMaterial({ transparent: true, alphaTest: 0.02, toneMapped: false, side: THREE.DoubleSide, fog: false });
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(cv * k, cv * k), mat);
  plane.position.set((cv / 2 - meta.center_x) * k, (meta.baseline_y - cv / 2) * k, 0);
  const planeX = plane.position.x, planeY = plane.position.y;
  pivot.add(plane);
  const sh = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 0.7), new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false }));
  sh.rotation.x = -Math.PI / 2; sh.position.y = 0.02; root.add(sh);
  const kp = await (await fetch(`assets/${name}/kp.json`)).json();
  return { name, meta, tex, kp, root, pivot, plane, mat, sh, planeX, planeY };
}
// put character: action, frame index, position, flip, tint, extras
function pose(ch, act, idx, x, y, z, o = {}) {
  const arr = ch.tex[act]; const i = clamp(Math.floor(idx), 0, arr.length - 1);
  ch.mat.map = arr[i]; ch.mat.needsUpdate = true; ch.cur = { act, i };
  ch.root.visible = true;
  // feet: stand on whatever is really under the footprint (voxel tiles and planks sit above the nominal y)
  if (o.snap !== false) y = Math.max(y, groundAt(x, y, z));
  ch.root.position.set(x, y, z);
  const br = o.breath ?? 1;
  // beat bob: a small squash on every beat and a sway that switches side on each beat (body language locked to the music)
  const bp = beatOf(curT), ph = ((bp % 1) + 1) % 1, side = (Math.floor(bp) % 2) ? 1 : -1;
  const bob = o.bob ?? 1;
  const squash = 1 - 0.05 * bob * Math.exp(-ph * 9);
  const sway = bob * 0.07 * side * (1 - 2 * Math.exp(-ph * 7));
  ch.pivot.scale.set(1 + (1 - squash) * 0.6, br * squash, 1);
  ch.pivot.rotation.z = (o.lean || 0) + sway;
  ch.pivot.position.y = o.hop || 0;
  const tn = o.tint || [1, 1, 1];
  ch.mat.color.setRGB(tn[0], tn[1], tn[2]);
  ch.sh.visible = o.shadow ?? true;
  ch.flip = !!o.flip;
}
// billboard: after the shot has placed the camera, turn each character to face it around Y. The plane stands at the
// front edge of the footprint (toward the camera) so tiles under the feet can't cut the soles; it is scaled back by
// the distance ratio so the on-screen size doesn't change
function faceCamera() {
  for (const ch of [C, D]) {
    if (!ch.root.visible) continue;
    const x = ch.root.position.x, y = ch.root.position.y, z = ch.root.position.z;
    const dx = camera.position.x - x, dz = camera.position.z - z;
    ch.pivot.rotation.y = Math.atan2(dx, dz);
    const dist = Math.hypot(dx, camera.position.y - y, dz), fw = Math.min(FOOT_FWD, dist * 0.2), ks = (dist - fw) / dist, sx = ch.flip ? -1 : 1;
    ch.plane.position.set(ch.planeX * ks * sx, ch.planeY * ks, fw);
    ch.plane.scale.set(sx * ks, ks, 1);
  }
}
// ground under a character: highest surface in the footprint, searched only just above the nominal height
const FOOT_FWD = 0.45;
const _ray = new THREE.Raycaster(), _down = new THREE.Vector3(0, -1, 0), _o = new THREE.Vector3();
const noGround = new Set();
function groundAt(x, y, z) {
  let best = -Infinity;
  const sets = [town, pierSet, wallSet, beachSet].filter(g => g.visible);
  for (const [ox, oz] of [[0, 0], [-0.22, 0], [0.22, 0], [0, 0.18], [0, -0.18]]) {
    _o.set(x + ox, y + 0.45, z + oz); _ray.set(_o, _down); _ray.far = 0.9;
    for (const h of _ray.intersectObjects(sets, true)) { if (noGround.has(h.object) || !h.object.visible) continue; best = Math.max(best, h.point.y); break; }
  }
  return best;
}
// looping actions, locked to the beat. Walks and runs: one step per beat, holding the contact pose and swinging through
// the step late so the foot plants on the beat. Everything else: pose to pose, a new pose on every beat
const loopIdx = (ch, act, t, cyclesPerBeat = 1) => {
  const n = ch.tex[act].length, b = beatOf(t) * cyclesPerBeat;
  if (/walk|run/.test(act)) {
    const p = ((b % 1) + 1) % 1, half = n / 2, step = Math.floor(p * 2), s = p * 2 - step;
    return step * half + (s < 0.55 ? 0 : Math.min(half - 1, 1 + Math.floor((s - 0.55) / 0.45 * (half - 1))));
  }
  return ((Math.floor(b) % n) + n) % n;
};
// one-shot actions: anticipate (hold the first pose), then move through the action fast so it lands on f1 (a beat)
const onceIdx = (ch, act, f, f0, f1, rev = false) => {
  const n = ch.tex[act].length, p = clamp((f - f0) / Math.max(1, f1 - f0), 0, 1);
  const i = p < 0.5 ? 0 : Math.min(n - 1, Math.ceil((p - 0.5) / 0.5 * (n - 1)));
  return rev ? n - 1 - i : i;
};
// hold a pose but keep it alive on the beat: alternate two neighbouring frames, one per beat
const ping = (t, a, b) => (((Math.floor(beatOf(t)) % 2) + 2) % 2 ? b : a);
const breath = t => 1 + 0.012 * Math.sin(beatOf(t) * Math.PI * 2);

// =====================================================================
// captions
// =====================================================================
let LYR = [];
const cap = document.getElementById('cap'), veil = document.getElementById('veil');
function caption(t) {
  let txt = '', op = 0;
  for (let i = 0; i < LYR.length; i++) {
    const L = LYR[i], next = LYR[i + 1] ? LYR[i + 1].t0 : L.t1 + 1;
    const end = Math.min(next - 0.12, L.t1 + 0.6, 28.24);
    if (t >= L.t0 - 0.02 && t < end) { txt = L.text; op = smooth(L.t0 - 0.02, L.t0 + 0.12, t) * (1 - smooth(end - 0.12, end, t)); }
  }
  cap.textContent = txt; cap.style.opacity = op;
  cap.style.transform = `translateY(${(1 - op) * 10}px)`;
}

// =====================================================================
// shot logic
// =====================================================================
let C, D; // Claude, DeepSeek
const sky = new THREE.Color();
// sky: a soft studio gradient, horizon colour below, a lighter lavender-tinted top (like the character renders' backdrop)
const skyCv = document.createElement('canvas'); skyCv.width = 2; skyCv.height = 256;
const skyCx = skyCv.getContext('2d'), skyTex = new THREE.CanvasTexture(skyCv); skyTex.colorSpace = THREE.SRGBColorSpace;
const _top = new THREE.Color();
function setSky(c, fogNear = 30, fogFar = 120) {
  sky.set(c); _top.set(c).lerp(new THREE.Color(0xe9e4ff), 0.45);
  const g = skyCx.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, '#' + _top.getHexString()); g.addColorStop(0.75, '#' + sky.getHexString()); g.addColorStop(1, '#' + sky.getHexString());
  skyCx.fillStyle = g; skyCx.fillRect(0, 0, 2, 256); skyTex.needsUpdate = true;
  scene.background = skyTex; scene.fog.color.copy(sky); scene.fog.near = fogNear; scene.fog.far = fogFar;
}
function keyAt(x, y, z, color = 0xfff0dc, intensity = 2.4) { key.position.set(x - 7, y + 12, z + 9); key.target.position.set(x, y, z); key.color.set(color); key.intensity = intensity; }
function look(px, py, pz, tx, ty, tz) { camera.position.set(px, py, pz); camera.lookAt(tx, ty, tz); }
// 运镜示范（第 4 批）：S1-01/03 慢推、S1-02 跟移、S1-05 升降、S1-06 环绕、S1-07 手持、S1-09 推近+变焦、S1-10 打点冲击。
// 新项目别手写这些：plan.json 的 camera 轨（tools/run.py camplan 起草）或 setupShot 里 R.cam.*，安全线自动夹。
const BASE_FOV = 28;
function fovPunch(f, f0, amt = 0.12) { camera.fov = BASE_FOV * (1 - amt * Math.exp(-Math.max(0, f - f0) / 3)); camera.updateProjectionMatrix(); }
function rainAt(t, cx, cz, amount) {
  const n = Math.floor(RAIN_N * amount);
  for (let i = 0; i < RAIN_N; i++) {
    if (i >= n) { setInst(rain, i, 0, -50, 0, 0, 0, 0); continue; }
    const x = cx + (hash(i) * 2 - 1) * 16, z = cz + (hash(i + 7.3) * 2 - 1) * 10;
    const y = 12 - ((t * 15 + hash(i + 3.1) * 12) % 12);
    setInst(rain, i, x, y, z, 0.035, 0.38, 0.035);
  }
  rain.instanceMatrix.needsUpdate = true;
}
function paintTown(cx, cz, radius) {
  const soft = 3;
  const kOf = (x, z) => 1 - smooth(radius - soft, radius, Math.hypot(x - cx, z - cz));
  for (const p of paintables) {
    const wp = p.m.getWorldPosition(_p); const k = kOf(wp.x, wp.z);
    p.m.material.color.copy(grey(p.c)).lerp(p.c, k);
    p.m.material.emissive.copy(p.e).multiplyScalar(k);
    if (p.e.getHex()) p.m.material.emissiveIntensity = 0.9 * k;
  }
  const im = town.userData.tiles, tiles = im.userData.tiles, c = new THREE.Color();
  for (let i = 0; i < tiles.length; i++) { const T = tiles[i]; c.copy(grey(T.c)).lerp(T.c, kOf(T.x, T.z)); im.setColorAt(i, c); }
  im.instanceColor.needsUpdate = true;
}
function hideFX() { setInst(sparkles, 0, 0, -50, 0, 0, 0, 0); for (let i = 0; i < 80; i++) setInst(sparkles, i, 0, -50, 0, 0, 0, 0); sparkles.instanceMatrix.needsUpdate = true; }
function burst(im, n, f, f0, cx, cy, cz, spread, up, colorFn) {
  const c = new THREE.Color();
  for (let i = 0; i < n; i++) {
    const age = (f - f0) / FPS;
    if (age < 0 || age > 1.6) { setInst(im, i, 0, -50, 0, 0, 0, 0); continue; }
    const a = hash(i * 1.3) * Math.PI * 2, sp = (0.4 + hash(i * 2.9)) * spread;
    const x = cx + Math.cos(a) * sp * age, z = cz + Math.sin(a) * sp * age * 0.5, y = cy + (up * (0.5 + hash(i * 5.1))) * age - 4.5 * age * age;
    const s = 0.09 * (1 - age / 1.6) + 0.02;
    setInst(im, i, x, y, z, s, s, s, age * 3, age * 2, 0);
    if (colorFn) { im.setColorAt(i, c.set(colorFn(i))); }
  }
  im.instanceMatrix.needsUpdate = true; if (im.instanceColor) im.instanceColor.needsUpdate = true;
}

let curT = 0;
function setupShot(f, sf) { const v = setupShot0(f, sf); faceCamera(); return v; }
function setupShot0(f, sf) {
  const t = f / FPS; curT = t;
  camera.fov = BASE_FOV; camera.updateProjectionMatrix();   // fov 每帧复位，写运镜的镜头自己再改（和引擎 camera.js 同一规矩）
  [C, D].forEach(ch => ch.root.visible = false);
  crowd.forEach(g => g.visible = false);
  rainAt(t, 0, 0, 0); hideFX();
  puzzle.visible = false; pLight.intensity = 0; leaf.visible = false;
  // reset state that only some shots touch, so any frame renders the same on its own (deterministic render(t))
  pierSet.userData.wallL.visible = pierSet.userData.wallR.visible = false;
  town.userData.lamp.material.emissiveIntensity = 0.25;
  burst(splash, 60, f, -999, 0, 0, 0, 0, 0);
  let veilColor = '#000', veilOp = 0;

  // ---------------- town (S1-01 … S1-04) ----------------
  if (sf < 290) {
    const grey0 = 0xb7b4c2;
    setSky(grey0, 40, 140);
    hemi.color.set(0xd9d6e6); hemi.intensity = 1.0;
    keyAt(-4, 0, -2, 0xe8e6f0, 1.3);
    let reveal = -5; // radius of colour
    if (sf < 44) { // S1-01 wide establishing
      const k = easeIO(f / 47);
      look(lerp(4, 0, k), lerp(26, 16, k), lerp(46, 33, k), -2, 0.5, -2);
      pose(C, 'idle', loopIdx(C, 'idle', t), -5.4, 0, -1.0, { breath: breath(t) });
      town.userData.lamp.material.emissiveIntensity = 0.25 + pulse(f, 2, 10) * 2.5;
      veilOp = 1 - smooth(0, 12, f); veilColor = '#000';
      if (f >= 33 && f < 38) { veilColor = '#ffffff'; veilOp = 0.25 * (1 - (f - 33) / 5); }
      rainAt(t, -2, -2, 1);
    } else if (sf < 126) { // S1-02 side tracking walk
      const stopF = 115;
      const remain = Math.max(0, (stopF - f) / FPS / SPB);
      const x = -5.4 - 0.8 * remain;
      const walking = f < stopF;
      const idx = walking ? loopIdx(C, 'walk_side', t, 0.5) : 0;
      pose(C, walking ? 'walk_side' : 'idle', walking ? idx : loopIdx(C, 'idle', t), x, 0, -1.0, { breath: walking ? 1 : breath(t) });
      look(x + 1.2, 2.6, 17, x + 1.2, 1.2, -1.5);
      crowd.forEach((g, i) => { g.visible = true; const cx = -2 - i * 2.6 - ((t - 2) * 1.9) % 30 + 6; g.position.set(cx, Math.abs(Math.sin((t + i) * 7.4)) * 0.06, -3.0 - (i % 2) * 0.8); });
      rainAt(t, x, -1, 1);
    } else if (sf < 207) { // S1-03 pray, push in
      const k = easeIO((f - 124) / 75);
      look(-5.4, lerp(2.4, 1.8, k), lerp(10, 6.2, k), -5.4, 1.25, -1);
      if (f < 147) pose(C, 'pray', onceIdx(C, 'pray', f, 126, 147), -5.4, 0, -1.0);
      else if (f < 166) pose(C, 'pray', ping(t, 2, 3), -5.4, 0, -1.0);
      else if (f < 187) pose(C, 'bow', Math.min(2, onceIdx(C, 'bow', f, 166, 187)), -5.4, 0, -1.0);   // 挫败: head drops
      else pose(C, 'cry', loopIdx(C, 'cry', t), -5.4, 0, -1.0);   // and she wipes her eyes, a new pose each beat
      town.userData.lamp.material.emissiveIntensity = 0.25;
      // cloud gap: a shaft of light that closes again
      const g = smooth(160, 168, f) * (1 - smooth(176, 190, f));
      shafts[0].parent === wallSet; // (shafts live at the seawall set; use veil glow instead)
      veilColor = '#fff6dd'; veilOp = g * 0.22;
      rainAt(t, -5.4, -1, 1);
    } else { // S1-04 DeepSeek arrives, world turns to colour
      const pk = easeIO((f - 249) / 39);
      look(-3.4, lerp(3.2, 2.6, pk), lerp(13.5, 10.8, pk), -4.2, lerp(1.3, 1.15, pk), -4);
      const wk = clamp((f - 207) / 42, 0, 1);
      const dz = lerp(-15, -3.0, easeOut(wk)), dx = lerp(-2.2, -3.0, wk);
      if (f < 249) pose(D, 'walk_front', loopIdx(D, 'walk_front', t, 0.5), dx, 0, dz);
      else pose(D, 'laugh', loopIdx(D, 'laugh', t, 1), dx, 0, dz, { breath: breath(t) });
      // Claude: facing camera, turns around to look at DeepSeek (turn_back reversed)
      if (f < 228) pose(C, 'idle', loopIdx(C, 'idle', t), -5.4, 0, -1.0, { breath: breath(t) });
      else if (f < 255) pose(C, 'turn_back', onceIdx(C, 'turn_back', f, 228, 249, true), -5.4, 0, -1.0, { breath: f > 249 ? breath(t) : 1 });
      else pose(C, 'reach_out', f < 269 ? onceIdx(C, 'reach_out', f, 255, 269) : ping(t, 3, 2), -5.4, 0, -1.0);   // 光明起来: reaches toward her
      reveal = f < 222 ? -5 : lerp(0, 60, easeOut((f - 222) / 30));
      paintTown(dx, dz, reveal);
      const kc = clamp(reveal / 40, 0, 1);
      setSky(new THREE.Color(0xb7b4c2).lerp(new THREE.Color(0xc7d8ff), kc).getHex(), 40, 140);
      hemi.color.set(new THREE.Color(0xd9d6e6).lerp(new THREE.Color(0xeee6ff), kc));
      keyAt(-4, 0, -2, new THREE.Color(0xe8e6f0).lerp(new THREE.Color(0xfff0d8), kc).getHex(), lerp(1.3, 2.6, kc));
      rainAt(t, -4, -3, 1 - smooth(222, 248, f));
      if (f >= 222 && f < 232) { veilColor = '#fff4e0'; veilOp = 0.35 * (1 - (f - 222) / 10); }
      burst(sparkles, 70, f, 248, (dx - 5.4) / 2, 1.2, (dz - 1) / 2, 2.6, 3, i => [0xffd36e, 0xff9ec4, 0x8fd3ff, 0xffffff][i % 4]);
      if (f >= 248 && f < 256) { veilColor = '#ffffff'; veilOp = 0.2 * (1 - (f - 248) / 8); }
      // sparkles burst at full colour
      burst(sparkles, 60, f, 248, dx, 1.2, dz, 3.5, 3.5, i => [0xffd36e, 0xff9ec4, 0x9fd8ff, 0xb9f59a][i % 4]);
    }
    if (sf < 207) paintTown(0, 0, -5);
  }
  // ---------------- pier (S1-05, S1-06) ----------------
  else if (sf < 453) {
    const X = 200;
    setSky(new THREE.Color(0xffc9a8).getHex(), 40, 160);
    hemi.color.set(0xffe2d6); hemi.intensity = 1.1;
    keyAt(X, 0, -5, 0xffd2a0, 2.6);
    updateSea(sea1, t, new THREE.Color(0x3f6fae), new THREE.Color(0x9fd0e8));
    pierSet.userData.sun.material.emissiveIntensity = 1.4;
    if (sf < 371) { // S1-05 walk onto the pier, walls fall, camera pulls back
      const k = easeIO((f - 289) / 85);
      look(X - 1.5, lerp(2.6, 4.6, k), lerp(11, 19, k), X - 0.5, 1.1, -5);
      const fq = Math.min(1, Math.max(0, (f - 287) / 24)); const fall = 0.04 + 0.96 * fq * fq;
      pierSet.userData.wallL.rotation.z = fall * Math.PI / 2 * 1.02; pierSet.userData.wallR.rotation.z = -fall * Math.PI / 2 * 1.02;
      pierSet.userData.wallL.visible = pierSet.userData.wallR.visible = f < 312;
      burst(sparkles, 50, f, 311, X - 1, 0.2, 0, 3.5, 4, () => 0xe8d9c2);
      const stopF = 351;
      const remain = Math.max(0, (stopF - f) / FPS / SPB);
      const xc = X - 1.0 - 0.8 * remain, xd = xc - 1.3;
      if (f < stopF) {
        pose(C, 'walk_side', loopIdx(C, 'walk_side', t, 0.5), xc, 0.49, -4.7);
        pose(D, 'walk_side', loopIdx(D, 'walk_side', t + SPB, 0.5), xd, 0.49, -5.4);
      } else {
        pose(C, 'look_up', onceIdx(C, 'look_up', f, 351, 371), xc, 0.49, -4.7, { breath: f > 371 ? breath(t) : 1 });
        pose(D, 'look_up', onceIdx(D, 'look_up', f, 353, 371), xd, 0.49, -5.4, { breath: f > 371 ? breath(t + 0.2) : 1 });
      }
      [C, D].forEach(ch => ch.mat.color.setRGB(1, 0.95, 0.9));
      // wave splash on the bar line
      burst(splash, 60, f, 331, X + 2.5, 0.3, -3.6, 2.2, 6, () => 0xffffff);
    } else { // S1-06 close two-shot, laughing; DeepSeek hops closer on 412; slow orbit around the couple
      const oa = THREE.MathUtils.degToRad(lerp(-14, 14, easeIO((f - 371) / 82)));
      look(X - 1.0 + Math.sin(oa) * 8.2, 1.75, -5 + Math.cos(oa) * 8.2, X - 1.0, 1.25, -5);
      const hopK = smooth(412, 426, f);
      const hop = (f >= 412 && f < 433) ? Math.sin((f - 412) / 21 * Math.PI) * 0.35 : 0;
      pose(C, 'laugh', loopIdx(C, 'laugh', t, 1), X - 0.15, 0.49, -4.9, { breath: breath(t), tint: [1, 0.95, 0.9] });
      pose(D, 'laugh', loopIdx(D, 'laugh', t, 1), X - 2.05 + hopK * 0.55, 0.49, -5.1, { hop, lean: -hopK * 0.06, tint: [1, 0.95, 0.9] });
      burst(sparkles, 70, f, 417, X - 1.0, 2.3, -4.9, 1.8, 2.2, i => [0xffd36e, 0xff9ec4, 0xffffff][i % 3]);
    }
  }
  // ---------------- seawall (S1-07, S1-08) ----------------
  else if (sf < 617) {
    const X = 400;
    if (sf < 539) { // S1-07 grey day, sitting together, rain, leaf umbrella
      setSky(0x9e9fb3, 30, 120);
      hemi.color.set(0xc9c9db); hemi.intensity = 0.95;
      keyAt(X, 0, 0, 0xdfe0ee, 1.2);
      updateSea(sea2, t, new THREE.Color(0x3f4d6e), new THREE.Color(0x7d8aa6), 0.35);
      const hx = Math.sin(t * 2.1) * 0.5 + Math.sin(t * 5.3 + 1.7) * 0.3 + Math.sin(t * 9.7 + 3.1) * 0.2;   // handheld（引擎里 R.cam.handheld）
      const hy = Math.sin(t * 1.7 + 2.3) * 0.5 + Math.sin(t * 4.9 + 4.1) * 0.3;
      look(X + 0.4 + hx * 0.05, 2.2 + hy * 0.05, 8.6, X, 1.35, 0);
      const lean = smooth(494, 504, f) * 0.14;
      const tint = [0.86, 0.86, 0.92];
      if (f < 466) pose(D, 'sit_idle', loopIdx(D, 'sit_idle', t, 1), X - 0.65, 0.8, 0.5, { tint });
      else pose(D, 'reach_out', f < 474 ? onceIdx(D, 'reach_out', f, 466, 474) : ping(t, 3, 2), X - 0.65, 0.8, 0.5, { tint });   // holds the leaf up over her
      pose(C, 'sit_idle', loopIdx(C, 'sit_idle', t + 0.4, 1), X + 0.65 - lean * 1.6, 0.8, 0.5, { lean, tint });
      const lift = easeOut((f - 462) / 12);
      leaf.visible = true; leaf.position.set(X - 400 - lerp(0.9, 0.2, lift), lerp(2.6, 3.25, lift) + Math.sin(t * 3) * 0.03, 0.4); leaf.rotation.set(0, 0, lerp(0.5, 0.12, lift));
      rainAt(t, X, 0, 1);
      cloudsL.concat(cloudsR).forEach((g, i) => { g.position.x = [-3, -7, 3, 7][i]; g.children.forEach(c => c.material.color.set(0x8a8aa0)); });
      shafts.forEach(s => s.material.opacity = 0);
    } else { // S1-08 low angle: DeepSeek parts the clouds
      const open1 = easeOut((f - 550) / 18), open2 = easeOut((f - 581) / 22);
      const open = open1 * 0.45 + open2 * 0.55;
      setSky(new THREE.Color(0x9e9fb3).lerp(new THREE.Color(0xbfd6ff), open).getHex(), 30, 140);
      hemi.color.set(new THREE.Color(0xc9c9db).lerp(new THREE.Color(0xf1ecff), open)); hemi.intensity = lerp(0.95, 1.15, open);
      keyAt(X, 0, 0, new THREE.Color(0xdfe0ee).lerp(new THREE.Color(0xfff0d0), open).getHex(), lerp(1.2, 2.8, open));
      updateSea(sea2, t, new THREE.Color(0x3f4d6e).lerp(new THREE.Color(0x3f78b8), open), new THREE.Color(0x7d8aa6).lerp(new THREE.Color(0xa8dcf0), open), 0.3);
      const k = easeIO((f - 543) / 73);
      look(X + 0.9, lerp(0.45, 0.6, k), lerp(7.6, 6.8, k), X + 0.1, 3.0, -1);
      pose(D, 'reach_out', f < 576 ? onceIdx(D, 'reach_out', f, 543, 576) : ping(t, 3, 2), X - 0.7, 0.8, 0.3);
      if (f < 596) pose(C, f < 555 ? 'idle' : 'look_up', f < 555 ? loopIdx(C, 'idle', t) : f < 576 ? onceIdx(C, 'look_up', f, 555, 576) : ping(t, 3, 2), X + 0.85, 0.8, 0.5);
      else pose(C, 'laugh', loopIdx(C, 'laugh', t, 1), X + 0.85, 0.8, 0.5, { breath: breath(t) });
      const cg = 0x8a8aa0, cw = 0xffffff;
      cloudsL.forEach((g, i) => { g.position.x = [-3, -7][i] - open * 9; g.children.forEach(c => c.material.color.set(new THREE.Color(cg).lerp(new THREE.Color(cw), open))); });
      cloudsR.forEach((g, i) => { g.position.x = [3, 7][i] + open * 9; g.children.forEach(c => c.material.color.set(new THREE.Color(cg).lerp(new THREE.Color(cw), open))); });
      shafts.forEach((s, i) => s.material.opacity = smooth(576 + i * 3, 596 + i * 3, f) * 0.22);
      rainAt(t, X, 0, 1 - smooth(543, 560, f));
      if (f >= 581 && f < 589) { veilColor = '#fff6e0'; veilOp = 0.18 * (1 - (f - 581) / 8); }
    }
  }
  // ---------------- beach (S1-09, S1-10) ----------------
  else {
    const X = 600;
    setSky(0xffd9b8, 40, 160);
    hemi.color.set(0xffeadf); hemi.intensity = 1.1;
    keyAt(X, 0, 0, 0xffdcae, 2.6);
    updateSea(sea3, t, new THREE.Color(0x4f86c0), new THREE.Color(0xb5e2ef), 0.2);
    puzzle.visible = true;
    if (sf < 678) { // S1-09 pick up the first piece together; dollyzoom (推近同时放宽 fov，纵深感被拉开)
      const k = easeIO((f - 617) / 60);
      look(X, lerp(1.9, 1.35, k), lerp(7.6, 4.6, k), X, lerp(0.9, 0.85, k), 0);
      camera.fov = lerp(BASE_FOV, BASE_FOV + 6, k); camera.updateProjectionMatrix();
      const pk = f < 637 ? 1 : f < 658 ? 2 : 3;   // bend on 617, crouch on 637, lift the piece on the 658 bar line
      pose(C, 'pick_up', pk, X + 0.75, 0, 0.1);
      pose(D, 'pick_up', pk, X - 0.75, 0, 0.1, { flip: true });
      const rise = easeOut((f - 630) / 28);
      puzzle.position.set(X, lerp(-0.1, 0.95, rise) + Math.sin(t * 4) * 0.03, 0.55);
      puzzle.rotation.set(0, Math.sin(t * 1.3) * 0.6, 0);
      puzzle.userData.glow.scale.setScalar(1.2 + 0.4 * rise + pulse(f, 658, 10) * 0.8);
      pLight.intensity = 2 * rise;
      // unhappy grey fragments blow away on 「淘汰」(f668)
      frags.forEach((fr, j) => {
        const a = clamp((f - 668 - hash(j) * 4) / 14, 0, 1);
        fr.m.position.set(fr.x0 + a * a * (6 + hash(j) * 6), fr.y0 + a * (1 + hash(j + 2) * 2), fr.z0 - a * 1.5);
        fr.m.rotation.set(a * 6, a * 4, 0); fr.m.visible = a < 1;
      });
    } else { // S1-10 hand-over → warm white (T1); fov punch on the beat the puzzle changes hands
      look(X, 1.25, 3.0, X, 1.05, 0);
      fovPunch(f, 678, 0.12);
      pose(C, 'reach_out', 3, X + 0.62, 0, 0.1, { flip: true });
      pose(D, 'reach_out', onceIdx(D, 'reach_out', f, 678, 684), X - 0.62, 0, 0.1);
      const p = easeIO((f - 678) / 6);
      puzzle.position.set(lerp(X + 0.25, X - 0.25, p), 1.05 + Math.sin(p * Math.PI) * 0.12, 0.35);
      puzzle.userData.glow.scale.setScalar(1.6 + Math.max(0, f - 678) * 0.5);
      pLight.intensity = 3 + Math.max(0, f - 678);
      frags.forEach(fr => fr.m.visible = false);
      veilColor = '#FFF4E0'; veilOp = f >= 686 ? 1 : 0.35 * easeIO((f - 678) / 8);
    }
  }
  return { veilColor, veilOp };
}


// =====================================================================
// shot transitions: render outgoing (A) and incoming (B) shots into
// targets, then mix them in a full-screen voxel transition shader
// =====================================================================
const rtOpts = { type: THREE.HalfFloatType, samples: 4, colorSpace: THREE.LinearSRGBColorSpace };
const rtA = new THREE.WebGLRenderTarget(1920, 1080, rtOpts), rtB = new THREE.WebGLRenderTarget(1920, 1080, rtOpts);
const tMat = new THREE.ShaderMaterial({
  uniforms: {
    tA: { value: rtA.texture }, tB: { value: rtB.texture }, p: { value: 0 }, mode: { value: 0 },
    center: { value: new THREE.Vector2(0.5, 0.5) }, grid: { value: new THREE.Vector2(16, 9) },
    gap: { value: new THREE.Color(0x2a2140) }, glow: { value: new THREE.Color(0xfff4e0) }, glowAmt: { value: 0.0 },
  },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: `
    uniform sampler2D tA, tB; uniform float p; uniform int mode; uniform vec2 center, grid;
    uniform vec3 gap, glow; uniform float glowAmt; varying vec2 vUv;
    float h1(vec2 c){ return fract(sin(dot(c, vec2(127.1, 311.7))) * 43758.5453); }
    float eio(float x){ x = clamp(x, 0.0, 1.0); return x < 0.5 ? 4.0*x*x*x : 1.0 - pow(-2.0*x + 2.0, 3.0) / 2.0; }
    vec3 tex(int which, vec2 uv){ uv = clamp(uv, 0.001, 0.999); return which == 0 ? texture2D(tA, uv).rgb : texture2D(tB, uv).rgb; }
    // arrival time of a cell in the stagger pattern
    float delay(vec2 cell){
      vec2 cc = (cell + 0.5) / grid;
      if (mode == 1) return (1.0 - cc.y) * 0.25 + h1(vec2(cell.x, 7.0)) * 0.75;   // rain: columns, random order
      return h1(cell);
    }
    // a voxel cube face: texture of the cell, bevelled edges
    vec3 cube(int which, vec2 cell, vec2 lq, float sz){
      vec3 c = tex(which, (cell + 0.5 + lq / (2.0 * sz)) / grid);
      float e = max(abs(lq.x), abs(lq.y)) / sz;
      c *= 1.0 - 0.35 * smoothstep(0.82, 1.0, e);
      c += 0.18 * smoothstep(0.82, 1.0, e) * step(0.0, lq.y) * step(abs(lq.x), lq.y);  // top edge highlight
      return c;
    }
    void main(){
      vec2 uv = vUv; vec3 col;
      float e = eio(p);
      if (mode == 5) {                       // whip tilt up: B sits above A, window races up with motion blur
        float sp = abs(eio(p + 0.05) - eio(p - 0.05)) * 0.8;
        vec3 acc = vec3(0.0);
        for (int i = 0; i < 16; i++) {
          float v = uv.y + e + (float(i) / 15.0 - 0.5) * sp;
          acc += v < 1.0 ? tex(0, vec2(uv.x, v)) : tex(1, vec2(uv.x, v - 1.0));
        }
        col = acc / 16.0;
      } else if (mode == 6) {                // zoom-through with radial blur
        float zA = 1.0 + 2.0 * e * e, zB = 1.0 + 1.2 * (1.0 - e) * (1.0 - e);
        float blur = sin(p * 3.14159) * 0.12;
        vec3 a = vec3(0.0), b = vec3(0.0);
        for (int i = 0; i < 12; i++) {
          float k = 1.0 - blur * float(i) / 11.0;
          a += tex(0, center + (uv - center) / (zA / k));
          b += tex(1, center + (uv - center) / (zB / k));
        }
        float m = smoothstep(0.35, 0.65, p);
        col = mix(a / 12.0, b / 12.0, m);
        col += glow * glowAmt * sin(p * 3.14159);
      } else if (mode == 10) {               // voxelize: picture breaks into cubes, swaps, rebuilds
        float bump = sin(p * 3.14159);
        float n = mix(140.0, 9.0, pow(bump, 0.7));       // cells down the short side: fine → coarse → fine
        vec2 g = vec2(n * 1.7778, n);
        vec2 cl = floor(uv * g), lq = fract(uv * g) - 0.5;
        int which = p < 0.5 ? 0 : 1;
        if (bump < 0.08) col = tex(which, uv);
        else {
          vec3 c = tex(which, (cl + 0.5) / g);
          float edge = max(abs(lq.x), abs(lq.y));
          c *= 1.0 - 0.4 * smoothstep(0.38, 0.5, edge) * bump;
          c += 0.15 * bump * smoothstep(0.3, 0.5, lq.y) * step(abs(lq.x), lq.y);
          col = c;
        }
        col += glow * glowAmt * bump * bump;
      } else if (mode == 11) {               // rows slide: A rows slide out, B rows slide in from the other side
        float row = floor(uv.y * grid.y);
        float dir = mod(row, 2.0) < 1.0 ? 1.0 : -1.0;
        float d = (1.0 - (row + 0.5) / grid.y) * 0.5;
        float s = eio((p - d) / 0.5);
        float x = uv.x - dir * s;
        if (x >= 0.0 && x <= 1.0) col = tex(0, vec2(x, uv.y));
        else col = tex(1, vec2(x + dir, uv.y));
        float seam = abs(x - (dir > 0.0 ? 0.0 : 1.0));
        col += glow * 0.5 * (1.0 - smoothstep(0.0, 0.006, seam)) * step(0.001, s) * step(s, 0.999);
      } else {                               // 1 = cubes rain in, 8 = cubes crumble away
        vec2 cell = floor(uv * grid);
        float w = 0.45;
        bool crumble = mode == 8;
        float own = clamp((p - delay(cell) * (1.0 - w)) / w, 0.0, 1.0);
        col = crumble ? (own <= 0.0 ? tex(0, uv) : tex(1, uv)) : (own >= 1.0 ? tex(1, uv) : tex(0, uv));
        // cubes passing through this pixel: crumble = falling from cells above; rain = dropping into cells below
        for (int k = 0; k < 6; k++) {
          vec2 c2 = cell + vec2(0.0, crumble ? float(k) : -float(k));
          float s2 = clamp((p - delay(c2) * (1.0 - w)) / w, 0.0, 1.0);
          if (s2 <= 0.0 || s2 >= 1.0) continue;
          float dy = crumble ? s2 * s2 * 4.0 : -(1.0 - s2) * (1.0 - s2) * 6.0;   // cells moved down (+) / still above (-)
          vec2 local = uv * grid - c2 + vec2(0.0, dy) - 0.5;
          float ang = (crumble ? s2 : (1.0 - s2)) * 1.4 * (h1(c2 + 3.1) - 0.5);
          local = mat2(cos(ang), -sin(ang), sin(ang), cos(ang)) * local;
          float sz = 0.5 * (crumble ? 1.0 - 0.3 * s2 : 1.0);
          if (abs(local.x) < sz && abs(local.y) < sz) {
            col = cube(crumble ? 0 : 1, c2, local, sz);
            if (crumble) col *= 1.0 - 0.3 * s2;
            break;
          }
        }
      }
      gl_FragColor = vec4(col, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
  depthTest: false, depthWrite: false, toneMapped: true,
});
const tScene = new THREE.Scene(), tCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
// miniature finish (every frame): tilt-shift blur outside a focus band, soft vignette, a little bloom on bright areas
const fbTex = new THREE.FramebufferTexture(1920, 1080), fbPos = new THREE.Vector2(0, 0);   // the finished frame, already tone mapped
const pMat = new THREE.ShaderMaterial({
  uniforms: { tP: { value: fbTex }, focus: { value: 0.5 }, band: { value: 0.22 } },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: `
    uniform sampler2D tP; uniform float focus, band; varying vec2 vUv;
    void main(){
      float d = abs(vUv.y - focus);
      float r = smoothstep(band, band + 0.3, d) * 5.0;           // blur radius in pixels, 0 inside the focus band
      vec2 px = vec2(1.0 / 1920.0, 1.0 / 1080.0);
      vec3 c = texture2D(tP, vUv).rgb, acc = c; float n = 1.0;
      if (r > 0.05) {
        for (int i = 0; i < 12; i++) {
          float a = float(i) * 2.39996, rr = r * sqrt((float(i) + 0.5) / 12.0);
          acc += texture2D(tP, vUv + vec2(cos(a), sin(a)) * rr * px).rgb; n += 1.0;
        }
      }
      vec3 col = acc / n;
      // soft bloom: lift the bright parts a touch
      col += max(col - 0.85, 0.0) * 0.35;
      // vignette
      vec2 q = vUv - 0.5; col *= 1.0 - 0.28 * smoothstep(0.35, 0.85, length(q * vec2(1.25, 1.0)));
      gl_FragColor = vec4(col, 1.0);   // display values in, display values out
    }`,
  depthTest: false, depthWrite: false, toneMapped: false,
});
const pScene = new THREE.Scene(); pScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), pMat));
tScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), tMat));

// cut frame, length (frames), shader mode, centre (uv, y up), cell grid, gap colour, glow
const CUTS = [
  { c: 44,  len: 14, mode: 1,  center: [0.5, 0.5],   grid: [16, 9],   glowAmt: 0.0 , kind: 'wipe', note: '方块像雨一列列落下，拼出街道' },  // cubes rain down into the street shot
  { c: 126, len: 10, mode: 6,  center: [0.52, 0.42], grid: [16, 9],   glowAmt: 0.0 , kind: 'through', note: '径向模糊推进，穿进 Claude' },  // zoom-through onto Claude
  { c: 207, len: 12, mode: 10, center: [0.5, 0.5],   grid: [16, 9],   glowAmt: 0.0 , kind: 'dissolve', note: '画面碎成体素再重新拼回（体素化溶解），落在 207 击点' },  // voxelize: the prayer breaks into cubes
  { c: 290, len: 16, mode: 8,  center: [0.5, 0.5],   grid: [16, 9],   glowAmt: 0.0 , kind: 'wipe', note: '灰色小镇崩成方块往下掉，露出码头' },  // the grey town crumbles away
  { c: 371, len: 10, mode: 6,  center: [0.5, 0.5],   grid: [16, 9],   glowAmt: 0.12 , kind: 'through', note: '推进到两人身上' }, // zoom into the couple
  { c: 453, len: 12, mode: 11, center: [0.5, 0.5],   grid: [16, 9],   glowAmt: 0.0 , kind: 'slide', note: '画面一条条横向滑走，夕阳换成阴天' },  // rows slide: sunset out, rain in
  { c: 539, len: 10, mode: 5,  center: [0.5, 0.5],   grid: [16, 9],   glowAmt: 0.0 , kind: 'whip', note: '甩镜头上摇到天空，动态模糊，落在 539 击点' },  // whip tilt up to the sky
  { c: 617, len: 12, mode: 10, center: [0.5, 0.5],   grid: [16, 9],   glowAmt: 0.35 , kind: 'dissolve', note: '光柱爆成体素，散开后是沙滩' }, // light bursts into voxels → beach
  { c: 678, len: 6,  mode: 6,  center: [0.5, 0.4],   grid: [16, 9],   glowAmt: 0.25 , kind: 'through', note: '推进到拼图块' }, // push into the puzzle
];
const fx = document.getElementById('fx'), fxc = fx.getContext('2d');

function render(f) {
  const t = f / FPS;
  const cut = CUTS.find(k => f >= k.c - k.len / 2 && f < k.c + k.len / 2);
  let v;
  if (!cut) {
    v = setupShot(f, f);
    renderer.setRenderTarget(null); renderer.render(scene, camera);
  } else {
    const vA = setupShot(f, cut.c - 1); renderer.setRenderTarget(rtA); renderer.render(scene, camera);
    const vB = setupShot(f, cut.c); renderer.setRenderTarget(rtB); renderer.render(scene, camera);
    renderer.setRenderTarget(null);
    const u = tMat.uniforms;
    u.p.value = (f - (cut.c - cut.len / 2) + 0.5) / cut.len;
    u.mode.value = cut.mode; u.center.value.set(...cut.center); u.grid.value.set(...cut.grid);
    u.glowAmt.value = cut.glowAmt;
    renderer.render(tScene, tCam);
    v = f < cut.c ? vA : vB;
  }
  renderer.copyFramebufferToTexture(fbPos, fbTex); renderer.render(pScene, tCam);
  veil.style.background = v.veilColor; veil.style.opacity = v.veilOp;
  fxc.clearRect(0, 0, 1920, 1080);
  if (!cut) drawEmotes(f, screenPoints());
  drawT1(f);
  caption(t);
}

// T1 hand-off: cream voxels burst out of the puzzle and tile the screen; 686–687 solid #FFF4E0
function drawT1(f) {
  if (f < 679) return;
  if (f >= 686) { fxc.fillStyle = '#FFF4E0'; fxc.fillRect(0, 0, 1920, 1080); return; }
  const cs = 60, cx = 960, cy = 610, maxD = Math.hypot(1000, 640);
  const p = (f - 679 + 1) / 7; // 1/7 … 1
  for (let gy = 0; gy < 18; gy++) for (let gx = 0; gx < 32; gx++) {
    const x = gx * cs + cs / 2, y = gy * cs + cs / 2;
    const d = Math.hypot(x - cx, y - cy) / maxD;
    const s = clamp((p * 1.35 - d - hash(gx * 31 + gy) * 0.15) / 0.3, 0, 1);
    if (s <= 0) continue;
    const z = s * s * (3 - 2 * s), w = cs * z;
    fxc.globalAlpha = 1;
    fxc.fillStyle = s >= 1 ? '#FFF4E0' : '#FFE9C2';
    fxc.fillRect(x - w / 2, y - w / 2, w, w);
    if (s < 1) { fxc.fillStyle = 'rgba(255,255,255,0.7)'; fxc.fillRect(x - w / 2, y - w / 2, w, Math.max(1, w * 0.18)); }
  }
}


// =====================================================================
// screen-space key points of the characters in the current scene state (song-mv window.probe, emote anchors)
// =====================================================================
const _v = new THREE.Vector3();
function screenPoints() {
  scene.updateMatrixWorld(); camera.updateMatrixWorld();
  const out = [];
  for (const ch of [C, D]) {
    if (!ch.root.visible || !ch.cur) continue;
    const m = ch.meta, k = H * (m.mv_scale || 1) / m.stand_h, cv = m.canvas;
    const P = (u, v) => { _v.set((u - cv / 2) * k, (cv / 2 - v) * k, 0).applyMatrix4(ch.plane.matrixWorld).project(camera); return [(_v.x + 1) / 2, (1 - _v.y) / 2]; };
    const q = ch.kp[ch.cur.act][ch.cur.i];
    const top = P(m.center_x, m.baseline_y - m.stand_h), bot = P(m.center_x, m.baseline_y);
    out.push({ id: ch.name, h: Math.abs(bot[1] - top[1]), root: P(m.center_x, m.baseline_y - 0.45 * m.stand_h),
      head: P(q[0], q[1]), handL: P(q[2], q[3]), handR: P(q[4], q[5]), footL: P(q[6], q[7]), footR: P(q[8], q[9]), top });
  }
  return out;
}
function shotFrameFor(f) { const cut = CUTS.find(k => f >= k.c - k.len / 2 && f < k.c + k.len / 2); return cut ? (f < cut.c ? cut.c - 1 : cut.c) : f; }

// =====================================================================
// emotes: voxel symbols that pop above a character's head on the beat (expression layer)
// =====================================================================
const GLYPH = {
  heart:   { c: '#ff5c8d', g: ['.XX.XX.', 'XXXXXXX', 'XXXXXXX', '.XXXXX.', '..XXX..', '...X...'] },
  star:    { c: '#ffd447', g: ['...X...', '...X...', '..XXX..', 'XXXXXXX', '..XXX..', '...X...', '...X...'] },
  exclaim: { c: '#ff5a4f', g: ['XX', 'XX', 'XX', 'XX', '..', 'XX'] },
  question:{ c: '#4fa3ff', g: ['.XXX.', 'X...X', '...X.', '..X..', '.....', '..X..'] },
  note:    { c: '#8a74e0', g: ['..XXX', '..X.X', '..X..', '..X..', 'XXX..', 'XXX..'] },
  cloud:   { c: '#8d8ca3', g: ['..XXX...', '.XXXXXX.', 'XXXXXXXX', 'XXXXXXXX'] },
  sweat:   { c: '#8fd3ff', g: ['.X.', 'XXX', 'XXX', '.X.'] },
};
// who, glyph, from/to frame (pops on a beat), side offset in body heights
const EMOTES = [
  { who: 'claude', g: 'cloud', f0: 65, f1: 123, dx: 0 },          // 渺小: a rain cloud follows her
  { who: 'claude', g: 'cloud', f0: 167, f1: 206, dx: 0 },         // 挫败
  { who: 'claude', g: 'exclaim', f0: 228, f1: 252, dx: 0.28 },    // she notices someone
  { who: 'deepseek', g: 'note', f0: 249, f1: 289, dx: 0.3 },
  { who: 'claude', g: 'heart', f0: 255, f1: 289, dx: 0.3 },       // 光明起来
  { who: 'claude', g: 'note', f0: 392, f1: 452, dx: 0.3 },
  { who: 'deepseek', g: 'heart', f0: 412, f1: 452, dx: -0.3 },    // the 412 hit
  { who: 'claude', g: 'heart', f0: 494, f1: 538, dx: 0.32 },      // leans on her shoulder
  { who: 'deepseek', g: 'sweat', f0: 474, f1: 538, dx: -0.3 },
  { who: 'deepseek', g: 'exclaim', f0: 543, f1: 575, dx: -0.3 },  // reaches for the sky
  { who: 'claude', g: 'star', f0: 596, f1: 616, dx: 0.3 },        // sun breaks through
  { who: 'claude', g: 'star', f0: 658, f1: 677, dx: 0.3 },
  { who: 'deepseek', g: 'star', f0: 658, f1: 677, dx: -0.3 },
];
function shade(hex, k) { const n = parseInt(hex.slice(1), 16); const c = [n >> 16, (n >> 8) & 255, n & 255].map(v => Math.round(k > 1 ? v + (255 - v) * (k - 1) : v * k)); return `rgb(${c})`; }
function drawGlyph(name, cx, cy, cell, a, t) {
  const G = GLYPH[name], rows = G.g, w = rows[0].length, h = rows.length;
  const x0 = cx - w * cell / 2, y0 = cy - h * cell;
  fxc.globalAlpha = a;
  const o = Math.max(2, cell * 0.22);
  fxc.fillStyle = '#2c2440';   // outline
  rows.forEach((r, j) => [...r].forEach((ch, i) => { if (ch === 'X') fxc.fillRect(x0 + i * cell - o, y0 + j * cell - o, cell + 2 * o, cell + 2 * o); }));
  rows.forEach((r, j) => [...r].forEach((ch, i) => {
    if (ch !== 'X') return;
    const x = x0 + i * cell, y = y0 + j * cell;
    fxc.fillStyle = G.c; fxc.fillRect(x, y, cell, cell);
    fxc.fillStyle = shade(G.c, 1.45); fxc.fillRect(x, y, cell, cell * 0.28);          // lit top face of the cube
    fxc.fillStyle = shade(G.c, 0.72); fxc.fillRect(x, y + cell * 0.8, cell, cell * 0.2); // shaded bottom
  }));
  if (name === 'cloud') {   // little rain drops under the cloud
    fxc.fillStyle = '#9fd0ff';
    for (let i = 0; i < 4; i++) { const ph = ((t * 2.2 + i * 0.27) % 1); fxc.fillRect(x0 + (1.2 + i * 1.8) * cell, y0 + h * cell + ph * cell * 3, cell * 0.4, cell * 0.8); }
  }
  fxc.globalAlpha = 1;
}
function drawEmotes(f, pts) {
  const t = f / FPS;
  for (const e of EMOTES) {
    if (f < e.f0 || f > e.f1) continue;
    const p = pts.find(q => q.id === e.who); if (!p) continue;
    const hp = p.h * 1080, cell = clamp(hp * 0.03, 5, 18);
    const age = f - e.f0, left = e.f1 - f;
    const pop = age < 5 ? 1 + 0.35 * Math.sin(age / 5 * Math.PI) : 1;       // overshoot on the beat it appears
    const a = Math.min(1, age / 2, left / 3 + 0.01);
    const bob = Math.sin(beatOf(t) * Math.PI * 2) * cell * 0.5;
    drawGlyph(e.g, p.top[0] * 1920 + e.dx * hp, p.top[1] * 1080 - hp * 0.04 + bob, cell * pop, a, t);
  }
}

// =====================================================================
// song-mv page contract: DUR, render(t), probe(t), TRANSITIONS
// =====================================================================
window.DUR = END_F / FPS;
window.TRANSITIONS = [
  ...CUTS.map((k, i) => ({ from: `S1-${String(i + 1).padStart(2, '0')}`, to: `S1-${String(i + 2).padStart(2, '0')}`,
    t0: (k.c - k.len / 2) / FPS, t1: (k.c + k.len / 2) / FPS, key: k.c / FPS, kind: k.kind, note: k.note })),
  { from: 'S1-04', to: 'S1-04', t0: 222 / FPS, t1: 249 / FPS, key: 248 / FPS, kind: 'incamera', note: '以 DeepSeek 为圆心，灰色小镇上色，248 强击点整条街上完色' },
  { from: 'S1-08', to: 'S1-08', t0: 550 / FPS, t1: 600 / FPS, key: 581 / FPS, kind: 'incamera', note: '乌云两次裂开，581 击点天空放晴、光柱照下' },
  { from: 'S1-10', to: 'T1', t0: 679 / FPS, t1: 688 / FPS, key: 682 / FPS, kind: 'wipe', note: '交接卡 T1：拼图的光炸成奶白方块铺满画面，686–687 纯色 #FFF4E0' },
];
window.probe = t => {
  const f = Math.round(t * FPS);
  setupShot(f, shotFrameFor(f));
  return screenPoints().map(({ top, ...p }) => p);
};

// ---------- boot ----------
async function boot() {
  LYR = await (await fetch('assets/lyrics.json')).json();
  [C, D] = await Promise.all([loadChar('claude'), loadChar('deepseek')]);
  await document.fonts.load('58px "ZCOOL KuaiLe"', '我们都是渺小真实存在祈愿小世界里不只有挫败直到遇见你以为就光明起来眼睛看到的广袤无垠大海有在日子可能被取代最灰暗陪着发呆让学会如何拨开阴霾将快乐全收集不开心淘汰');
  window.renderFrame = f => { render(f); return true; };
  window.render = t => { render(Math.min(END_F - 1, Math.round(t * FPS))); };
  const q = new URLSearchParams(location.search);
  if (q.has('f')) render(+q.get('f'));
  else if (!q.has('export')) { // preview playback
    const a = new Audio('assets/song.wav'); let t0 = performance.now();
    a.play().catch(() => { }); const loop = () => { const f = Math.floor((performance.now() - t0) / 1000 * FPS) % END_F; render(f); requestAnimationFrame(loop); }; loop();
  }
  window.READY = true;
}
boot();
