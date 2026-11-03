// voxel-mv 引擎（来自七 AI 接力 MV《把回忆拼好给你》的公共引擎）。只有通用能力，没有任何场景：场景由 shots.js 自己搭。
// 单曲 MV：plan.json 的 start = 0、end = 全曲帧数、handoffs 为空，交接相关的函数不用管。
// 多段接力：plan.json 写本段的 start/end 和 handoffs，交接函数（T1–T6）照用，见 SKILL 的 references/relay.md。
// 内容：渲染器和灯光、方块工具、角色（身高校正、贴地、防穿模、踩拍）、碰撞（collide-core + collide，默认开）、
// 表情符号、段内转场、微缩后期、字幕、交接画面（T1–T6 两边共用同一份代码，保证切点对得上）、song-mv 页面契约（DUR / render / probe / TRANSITIONS）。
// 时间：页面内部一律用全曲帧号 f（= 段起始帧 + 本段第几帧）和全曲秒数 t = f / 24。
import * as THREE from 'three';
import * as collide from './collide.js';
import * as camlib from './camera.js';
export { THREE };
export { collider, noBlock, mark, spot, reserve, scatter, collect as collideCollect, CFG as collideCFG } from './collide.js';
export const cam = camlib.api;               // 运镜库：setupShot 里 R.cam.dolly({amt}) / R.cam.punch({amt, shake}) …（只对这一帧生效）

// 节拍网格：plan.json 的 tempo {beat0, spb}（new_project.py 按 beat_times 拟合）。下面的默认值是《把回忆拼好给你》的
export const FPS = 24;
export let BEAT0 = 0.1406, SPB = 0.852;
export const beatOf = t => (t - BEAT0) / SPB;                 // t：全曲秒数
export const beatFrame = n => Math.round((BEAT0 + n * SPB) * FPS);
export const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
export const smooth = (a, b, x) => { x = clamp((x - a) / (b - a), 0, 1); return x * x * (3 - 2 * x); };
export const lerp = (a, b, k) => a + (b - a) * k;
export const easeIO = x => (x = clamp(x, 0, 1), x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
export const easeOut = x => 1 - Math.pow(1 - clamp(x, 0, 1), 3);
export const hash = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
export const pulse = (f, f0, len) => (f >= f0 && f < f0 + len) ? Math.exp(-(f - f0) / (len / 3)) : 0;

// ---------- 渲染器、镜头、灯光 ----------
const canvas = document.getElementById('gl');
export const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(1920, 1080, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

export const scene = new THREE.Scene();
export const camera = new THREE.PerspectiveCamera(28, 1920 / 1080, 0.1, 400);
scene.fog = new THREE.Fog(0xcfc8e8, 30, 120);
export const hemi = new THREE.HemisphereLight(0xe6e0ff, 0x8d8399, 1.1);
scene.add(hemi);
export const key = new THREE.DirectionalLight(0xfff0dc, 2.4);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -18, right: 18, top: 18, bottom: -18, near: 1, far: 80 });
key.shadow.bias = -0.0008;
key.shadow.radius = 4;
scene.add(key, key.target);

const LOOK_T = new THREE.Vector3();          // 运镜库的基础看向点（R.look 记录；camera.js 在它上面叠运镜）
export function look(px, py, pz, tx, ty, tz) { camera.position.set(px, py, pz); camera.lookAt(tx, ty, tz); camera.updateMatrixWorld(); LOOK_T.set(tx, ty, tz); }
export function keyAt(x, y, z, color = 0xfff0dc, intensity = 2.4) { key.position.set(x - 7, y + 12, z + 9); key.target.position.set(x, y, z); key.color.set(color); key.intensity = intensity; }
// 天空：地平线颜色往上渐变到偏淡紫的顶，和角色立绘的棚拍底色一个路子
const skyCv = document.createElement('canvas'); skyCv.width = 2; skyCv.height = 256;
const skyCx = skyCv.getContext('2d'), skyTex = new THREE.CanvasTexture(skyCv); skyTex.colorSpace = THREE.SRGBColorSpace;
const _sky = new THREE.Color(), _top = new THREE.Color();
export function setSky(c, fogNear = 30, fogFar = 120, top = 0xe9e4ff, topMix = 0.45) {
  _sky.set(c); _top.set(c).lerp(new THREE.Color(top), topMix);
  const g = skyCx.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, '#' + _top.getHexString()); g.addColorStop(0.75, '#' + _sky.getHexString()); g.addColorStop(1, '#' + _sky.getHexString());
  skyCx.fillStyle = g; skyCx.fillRect(0, 0, 2, 256); skyTex.needsUpdate = true;
  scene.background = skyTex; scene.fog.color.copy(_sky); scene.fog.near = fogNear; scene.fog.far = fogFar;
}

// ---------- 方块工具 ----------
export const boxGeo = new THREE.BoxGeometry(1, 1, 1);
// 一个方块，(x, y, z) 是底面中心
export function box(parent, w, h, d, color, x, y, z, o = {}) {
  const m = new THREE.Mesh(boxGeo, new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, emissive: o.emissive || 0x000000, emissiveIntensity: o.ei ?? 1, transparent: !!o.opacity, opacity: o.opacity ?? 1 }));
  m.scale.set(w, h, d);
  m.position.set(x, y + h / 2, z);
  m.castShadow = o.cast ?? true; m.receiveShadow = true;
  parent.add(m);
  return m;
}
// 圆角方块：参数和 box 一样，o.r 是圆角半径（默认短边的 12%）。微缩模型的边角都不是锐利的，近处的大件优先用它
const _rgeo = new Map();
export function roundGeo(w, h, d, r) {
  const key = [w, h, d, r].map(v => v.toFixed(3)).join(',');
  if (_rgeo.has(key)) return _rgeo.get(key);
  const g = new THREE.BoxGeometry(w, h, d, 4, 4, 4), P = g.attributes.position, v = new THREE.Vector3(), c = new THREE.Vector3();
  const hx = w / 2 - r, hy = h / 2 - r, hz = d / 2 - r;
  for (let i = 0; i < P.count; i++) {
    v.fromBufferAttribute(P, i);
    c.set(clamp(v.x, -hx, hx), clamp(v.y, -hy, hy), clamp(v.z, -hz, hz));
    const dv = v.clone().sub(c); if (dv.lengthSq() > 1e-9) v.copy(c).addScaledVector(dv.normalize(), r);
    P.setXYZ(i, v.x, v.y, v.z);
  }
  g.computeVertexNormals(); _rgeo.set(key, g); return g;
}
export function rbox(parent, w, h, d, color, x, y, z, o = {}) {
  const r = Math.min(o.r ?? Math.min(w, h, d) * 0.12, Math.min(w, h, d) / 2 - 1e-3);
  const m = new THREE.Mesh(roundGeo(w, h, d, r), new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, emissive: o.emissive || 0x000000, emissiveIntensity: o.ei ?? 1, transparent: !!o.opacity, opacity: o.opacity ?? 1 }));
  m.position.set(x, y + h / 2, z);
  m.castShadow = o.cast ?? true; m.receiveShadow = true;
  parent.add(m);
  return m;
}
// 大量同样的方块（地砖、雨、粒子）
export function instanced(parent, n, color = 0xffffff, o = {}) {
  const im = new THREE.InstancedMesh(boxGeo, new THREE.MeshStandardMaterial({ color, roughness: 0.9, emissive: o.emissive || 0, transparent: !!o.opacity, opacity: o.opacity ?? 1 }), n);
  im.castShadow = o.cast ?? false; im.receiveShadow = true;
  im.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  parent.add(im);
  return im;
}
const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = new THREE.Vector3(), _p = new THREE.Vector3(), _e = new THREE.Euler();
export function setInst(im, i, x, y, z, sx, sy, sz, rx = 0, ry = 0, rz = 0) {
  _e.set(rx, ry, rz); _q.setFromEuler(_e); _p.set(x, y, z); _s.set(sx, sy, sz);
  _m.compose(_p, _q, _s); im.setMatrixAt(i, _m);
}

// ---------- 地面：角色脚底贴着这里登记的东西 ----------
const grounds = [];
export function addGround(obj) { grounds.push(obj); return obj; }
const _ray = new THREE.Raycaster(), _down = new THREE.Vector3(0, -1, 0), _o = new THREE.Vector3();
// 脚印里 5 个点往下打射线，取最高的表面；只在名义高度上方 0.45 内找，屋顶、树冠不会被当成地面
export function groundAt(x, y, z) {
  let best = -Infinity;
  const vis = grounds.filter(g => g.visible);
  if (!vis.length) return best;
  for (const [ox, oz] of [[0, 0], [-0.22, 0], [0.22, 0], [0, 0.18], [0, -0.18]]) {
    _o.set(x + ox, y + 0.45, z + oz); _ray.set(_o, _down); _ray.far = 0.9;
    for (const h of _ray.intersectObjects(vis, true)) { if (!h.object.visible) continue; best = Math.max(best, h.point.y); break; }
  }
  return best;
}

// =====================================================================
// 角色：立牌，统一身高 H，按「眼睛到脚底」校正（frames.json 的 mv_scale）
// =====================================================================
export const H = 2.0;
export const chars = {};          // name -> 角色
const loader = new THREE.TextureLoader();
const shadowTex = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d'); const r = g.createRadialGradient(32, 32, 0, 32, 32, 32); r.addColorStop(0, 'rgba(30,20,50,0.45)'); r.addColorStop(1, 'rgba(30,20,50,0)'); g.fillStyle = r; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c); })();
// 只加载用得到的动作（动作轨里出现的 + plan.json 的 extra_actions），七个人同框时显存也够
export async function loadChar(name, acts = null) {
  const meta = await (await fetch(`assets/${name}/frames.json`)).json();
  const tex = {}, jobs = [];
  for (const [act, a] of Object.entries(meta.actions)) {
    if (acts && !acts.has(act)) continue;
    tex[act] = [];
    a.frames.forEach((fr, i) => jobs.push(new Promise(res => loader.load(`assets/${name}/${fr.file}`, tx => { tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 4; tex[act][i] = tx; res(); }))));
  }
  await Promise.all(jobs);
  const k = H * (meta.mv_scale || 1) / meta.stand_h, cv = meta.canvas;
  const root = new THREE.Group(); scene.add(root);
  const pivot = new THREE.Group(); root.add(pivot);
  const mat = new THREE.MeshBasicMaterial({ transparent: true, alphaTest: 0.02, toneMapped: false, side: THREE.DoubleSide, fog: false });
  mat.onBeforeCompile = s => {   // 整张立牌写同一个深度（脚往镜头方向 foot_r 那点的投影深度）：道具要么整在前要么整在后，不再把角色切开
    s.uniforms.uFlatDepth = { value: mat.userData.flatD ?? 0.5 };
    s.fragmentShader = s.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform float uFlatDepth;')
      .replace('#include <dithering_fragment>', '#include <dithering_fragment>\n\tgl_FragDepth = uFlatDepth;');
    mat.userData.shader = s;
  };
  mat.customProgramCacheKey = () => 'flatdepth';
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(cv * k, cv * k), mat);
  plane.position.set((cv / 2 - meta.center_x) * k, (meta.baseline_y - cv / 2) * k, 0);
  pivot.add(plane);
  const sh = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 0.7), new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false }));
  sh.rotation.x = -Math.PI / 2; sh.position.y = 0.02; root.add(sh);
  const kp = await (await fetch(`assets/${name}/kp.json`)).json();
  const motion = {};   // 每个动作自身的动作幅度（关键点最大位移 / 身高）
  for (const [act, fr] of Object.entries(kp)) motion[act] = Math.max(0, ...fr.map(q => Math.max(...[0, 2, 4, 6, 8].map(j => Math.hypot(q[j] - fr[0][j], q[j + 1] - fr[0][j + 1]))))) / meta.stand_h;
  const ch = { name, meta, tex, kp, motion, root, pivot, plane, mat, sh, planeX: plane.position.x, planeY: plane.position.y, k };
  root.visible = false;
  chars[name] = ch;
  return ch;
}
let curT = 0;
// 摆一个角色：动作、帧序（从 0 数）、脚底位置。o：flip 朝左、lean 倾斜、hop 跳起、yaw 立牌翻转角（弧度，舞句的转身/转圈用）、breath 呼吸、tint 调色、
// bob 每拍下蹲和左右摆的强度（默认 1，0 关掉）、shadow 影子、snap 贴地（默认开）、onTop 画在最前面（交接定位默认开）
export function pose(ch, act, idx, x, y, z, o = {}) {
  const arr = ch.tex[act];
  if (!arr) throw new Error(`${ch.name} 的动作 ${act} 没加载：把它写进 plan.json 的 tracks 或 extra_actions`);
  let i = clamp(Math.floor(idx), 0, arr.length - 1);
  const bads = ch.meta.bad && ch.meta.bad[act];   // 坏帧自动换成最近的好帧（结果和探针一致）
  if (bads && bads.includes(i)) for (let d = 1; d < arr.length; d++) {
    if (i - d >= 0 && !bads.includes(i - d)) { i -= d; break; }
    if (i + d < arr.length && !bads.includes(i + d)) { i += d; break; }
  }
  ch.mat.map = arr[i]; ch.mat.needsUpdate = true; ch.cur = { act, i };
  ch.root.visible = true;
  ch.o = { scale: o.scale ?? 1, snap: o.snap !== false, onTop: !!o.onTop, hop: o.hop || 0, y0: y };   // 体素关用
  if (o.snap !== false) y = Math.max(y, groundAt(x, y, z));
  ch.root.position.set(x, y, z);
  const br = o.breath ?? 1;
  const bp = beatOf(curT), ph = ((bp % 1) + 1) % 1, side = (Math.floor(bp) % 2) ? 1 : -1;
  const bob = o.bob ?? 1;
  const squash = 1 - 0.05 * bob * Math.exp(-ph * 9);
  const sway = bob * 0.07 * side * (1 - 2 * Math.exp(-ph * 7));
  ch.pivot.scale.set((1 + (1 - squash) * 0.6) * (o.scale ?? 1), br * squash * (o.scale ?? 1), 1);
  ch.pivot.rotation.z = (o.lean || 0) + sway;
  ch.pivot.position.y = o.hop || 0;
  const tn = o.tint || [1, 1, 1];
  ch.mat.color.setRGB(tn[0], tn[1], tn[2]);
  ch.mat.opacity = o.opacity ?? 1;
  ch.sh.visible = o.shadow ?? true;
  ch.mat.depthTest = !o.onTop; ch.plane.renderOrder = o.onTop ? 10 : 0;   // onTop：画在场景最前面，不会被地面或墙挡住
  ch.flip = !!o.flip; ch.yaw = o.yaw || 0;
  collide.intent(ch, x, z, o);   // 记下本帧站位，setup() 在镜头摆好后统一解算碰撞
}
// 立牌朝向镜头（绕 Y 轴），并更新整张同深度的 uFlatDepth。必须在镜头摆好之后算：引擎在 setupShot 之后自动调用
function faceCamera() {
  camera.updateMatrixWorld();
  for (const ch of Object.values(chars)) {
    if (!ch.root.visible) continue;
    const { x, y, z } = ch.root.position;
    const dx = camera.position.x - x, dz = camera.position.z - z;
    ch.pivot.rotation.y = Math.atan2(dx, dz);
    const cy = Math.cos(ch.yaw || 0), sx = (ch.flip ? -1 : 1) * (cy < 0 ? -1 : 1) * Math.max(0.04, Math.abs(cy));   // yaw：舞句里立牌翻面（转身、转圈）
    ch.plane.position.set(ch.planeX * sx, ch.planeY, 0);
    ch.plane.scale.set(sx, 1, 1);
    const dl = Math.hypot(dx, dz), fr = Math.max(0.05, ch.meta.foot_r ?? 0.3);   // 深度取样点：脚 + 朝镜头 foot_r
    _v.set(dl > 1e-6 ? x + dx / dl * fr : x, y, dl > 1e-6 ? z + dz / dl * fr : z).project(camera);
    const d = clamp(_v.z * 0.5 + 0.5, 0, 1);
    ch.mat.userData.flatD = d;   // 首帧编译前 onBeforeCompile 也从这里取值，单帧渲染不落默认值
    if (ch.mat.userData.shader) ch.mat.userData.shader.uniforms.uFlatDepth.value = d;
  }
}
// 交接用：把角色放到屏幕上的指定位置。xPx 身体中线、feetPx 脚底（像素），hFrac 身高占画面高的比例。
// 镜头先摆好再调用；返回世界坐标（已经写进角色）
const _ndc = new THREE.Vector3(), _dir = new THREE.Vector3();
export function placeOnScreen(ch, act, idx, xPx, feetPx, hFrac, o = {}) {
  camera.updateMatrixWorld();
  const fovH = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
  const hWorld = H * (o.scale ?? 1);
  const dist = hWorld / (hFrac * fovH);                     // 离镜头多远，身高正好是 hFrac
  _ndc.set(xPx / 960 - 1, 1 - feetPx / 540, 0.5).unproject(camera);
  _dir.copy(_ndc).sub(camera.position).normalize();
  const fwd = new THREE.Vector3(); camera.getWorldDirection(fwd);
  const along = dist / Math.max(0.2, _dir.dot(fwd));
  const p = camera.position.clone().addScaledVector(_dir, along);
  pose(ch, act, idx, p.x, p.y, p.z, { shadow: false, onTop: true, ...o, snap: false, bob: o.bob ?? 0 });   // 交接定位默认画在最前面，场景挡不住
  return p;
}
// 让角色的头（kp 里的头部点）落在屏幕 (xPx, yPx)，身高占画面 hFrac。T2 的「头在 (50%, 40%)」用这个
export function placeHead(ch, act, idx, xPx, yPx, hFrac, o = {}) {
  let fx = xPx, fy = yPx + 0.6 * hFrac * 1080;
  for (let it = 0; it < 3; it++) {
    placeOnScreen(ch, act, idx, fx, fy, hFrac, o);
    ch.root.updateMatrixWorld(true);
    const m = ch.meta, k = ch.k, cv = m.canvas, q = ch.kp[act][idx];
    _v.set((q[0] - cv / 2) * k, (cv / 2 - q[1]) * k, 0).applyMatrix4(ch.plane.matrixWorld).project(camera);
    fx += xPx - (_v.x + 1) * 960; fy += yPx - (1 - _v.y) * 540;
  }
}
export function hideChars() { for (const ch of Object.values(chars)) ch.root.visible = false; }

// ---------- 踩拍 ----------
// 循环动作：一拍一个姿势。走路一拍一步（定住接触姿势，拍子后半段才迈过去，脚落在拍上），跑步一拍两步
export const loopIdx = (ch, act, t) => {
  const n = ch.tex[act].length;
  if (/walk|run/.test(act)) {
    const b = beatOf(t) * (/run/.test(act) ? 1 : 0.5);
    const p = ((b % 1) + 1) % 1, half = n / 2, step = Math.floor(p * 2), s = p * 2 - step;
    return step * half + (s < 0.55 ? 0 : Math.min(half - 1, 1 + Math.floor((s - 0.55) / 0.45 * (half - 1))));
  }
  return ((Math.floor(beatOf(t)) % n) + n) % n;
};
// 一次性动作：前半段停在第一帧蓄力，后半段快速做完，最后一帧正好落在 f1（拍点）。from/to 限定用哪几帧（从 0 数）
export const onceIdx = (ch, act, f, f0, f1, rev = false, from = 0, to = null) => {
  const n = (to ?? ch.tex[act].length - 1) - from + 1, p = clamp((f - f0) / Math.max(1, f1 - f0), 0, 1);
  const i = p < 0.5 ? 0 : Math.min(n - 1, Math.ceil((p - 0.5) / 0.5 * (n - 1)));
  return from + (rev ? n - 1 - i : i);
};
// 停住也要活：两帧每拍来回换一次
export const ping = (t, a, b) => (((Math.floor(beatOf(t)) % 2) + 2) % 2 ? b : a);
export const breath = t => 1 + 0.012 * Math.sin(beatOf(t) * Math.PI * 2);

// 动作轨：plan.json 里每个角色一串 [模式, 动作, f0, f1, ...]，按分镜预先填好。
//   ["loop", act, f0, f1]          循环，一拍一姿势（走一拍一步、跑一拍两步）
//   ["once", act, f0, f1, {rev, from, to}]  一次性，f1 落拍；之后到下一条之前自动在最后两帧来回
//   ["ping", act, f0, f1, a, b]    停住，a/b 两帧每拍来回（从 0 数）
//   ["hold", act, f0, f1, i]       定在第 i 帧（配合每拍下蹲摆动，不会定格）
//   ["off", f0, f1]                不出场
let PLAN = null;
export function actAt(name, f) {
  const tr = PLAN.tracks[name]; if (!tr) return null;
  const ch = chars[name], t = f / FPS;
  let e = null;
  for (const x of tr) { const f0 = x[0] === 'off' ? x[1] : x[2]; if (f0 <= f) e = x; else break; }
  if (!e || e[0] === 'off') return null;
  const [mode, act, f0, f1] = e;
  const n = mode === 'dance' ? 0 : ch.tex[act].length;
  if (mode === 'loop') {
    const o = e[4];
    if (o && (o.from != null || o.to != null)) { const a0 = o.from ?? 0, a1 = o.to ?? n - 1, m = a1 - a0 + 1; return { act, idx: a0 + ((Math.floor(beatOf(t)) % m) + m) % m, mode }; }
    return { act, idx: loopIdx(ch, act, t), mode };
  }
  if (mode === 'dance') return danceAt(name, e, t);
  if (mode === 'ping') return { act, idx: ping(t, e[4], e[5]), mode };
  if (mode === 'hold') return { act, idx: e[4], mode };
  if (mode === 'once') {
    const o = e[4] || {}, last = o.to ?? n - 1, first = o.from ?? 0;
    if (f <= f1) return { act, idx: onceIdx(ch, act, f, f0, f1, !!o.rev, first, last), mode, landing: f1 };
    const end = o.rev ? first : last, prev = o.rev ? first + 1 : last - 1;
    return { act, idx: ping(t, prev, end), mode: 'after' };
  }
  return null;
}
export const plan = () => PLAN;

// ---------- 编舞层：dance 条目按舞句库（engine/moves.json + plan.json 的 moves）一拍一步展开 ----------
//   ["dance", 舞句, f0, f1, {mirror, canon, speed, size}]
//   mirror 镜像（朝向和左右位移反过来，多人对称用）；canon 晚几拍开始（可以是小数，轮唱/波浪用）；
//   speed 0.5 半速（一步两拍）/ 2 倍速；size 位移、跳、倾斜的幅度倍数。f0 放在拍上，舞句从 f0 那一拍开始循环
let MOVES = { slots: {}, phrases: {} };
export const moves = () => MOVES;
export function phraseOf(id) {
  const ph = MOVES.phrases[id];
  if (!ph) throw new Error(`舞句 ${id} 不在 engine/moves.json 或 plan.json 的 moves 里`);
  return ph;
}
// 槽位（@clap 这种）→ 这个角色有的第一个动作；不是槽位就原样返回
export function resolveAct(meta, a) {
  if (a[0] !== '@') return a;
  const c = (MOVES.slots[a] || []).find(x => meta.actions[x]);
  if (!c) throw new Error(`槽位 ${a} 里的动作这个角色一个都没有：${(MOVES.slots[a] || []).join(' / ')}`);
  return c;
}
export function danceActs(meta, id) { return [...new Set(phraseOf(id).steps.map(s => resolveAct(meta, s.a)))]; }
const easeO = x => 1 - (1 - clamp(x, 0, 1)) ** 2, easeM = x => { x = clamp(x, 0, 1); return x * x * (3 - 2 * x); };
function danceAt(name, e, t) {
  const ch = chars[name], ph = phraseOf(e[1]), o = e[4] || {}, S = ph.steps, n = S.length;
  const size = o.size ?? 1, mir = o.mirror ? -1 : 1;
  const B0 = Math.round(beatOf(e[2] / FPS));
  let b = (beatOf(t + 0.5 / FPS) - B0 - (o.canon || 0)) * (o.speed || 1);   // +半帧：拍点那一帧（四舍五入到帧）算新的一步，和检查脚本一致
  const pre = b < 0; if (pre) b = 0;
  const kk = Math.floor(b), k = ((kk % n) + n) % n, loop = Math.floor(kk / n), p = pre ? 0 : b - kk;
  const st = S[k], pv = kk > 0 ? S[(k - 1 + n) % n] : {};   // 第一步从站位（偏移 0）出发
  const act = resolveAct(ch.meta, st.a), nf = ch.tex[act].length;
  let i = st.i2 != null && p >= 0.5 ? st.i2 : (st.i ?? 0); if (i < 0) i += nf; i = clamp(i, 0, nf - 1);
  const mix = (key, u) => lerp(pv[key] || 0, st[key] || 0, u);
  const turns = S.filter(s => s.turn).length, before = loop * turns + S.slice(0, k).filter(s => s.turn).length;
  const yaw = Math.PI * (before + (st.turn ? easeM(p / 0.35) : 0) + (o.mirror ? 1 : 0)) + (st.spin ? 2 * Math.PI * easeM(p / 0.6) : 0);
  return { act, idx: i, mode: 'dance', phrase: e[1], step: k,
    fx: { dx: mix('dx', easeO(p / 0.4)) * size * mir, dz: mix('dz', easeO(p / 0.4)) * size, hop: (st.hop || 0) * size * Math.sin(Math.PI * p),
          lean: mix('lean', easeO(p / 0.3)) * size * mir, yaw, sq: st.sq || 0 } };
}
// 这一帧属于哪个镜头（sf 是引擎传给 setupShot 的镜头帧）
export function shotOf(sf) { return PLAN.shots.find(s => sf >= s.f0 && sf <= s.f1) || PLAN.shots[PLAN.shots.length - 1] || { id: 'S01', f0: PLAN.start, f1: PLAN.end - 1 }; }
// 按动作轨摆角色（位置、朝向、调色由你给）。这一帧动作轨里没有她就隐藏，返回 false
export function play(name, f, x, y, z, o = {}) {
  const a = actAt(name, f), ch = chars[name];
  if (!a) { ch.root.visible = false; return false; }
  const stillish = a.mode === 'ping' || a.mode === 'after' || a.mode === 'hold';
  if (a.fx) {   // 舞句：位移、跳、倾斜、翻面叠加在你给的站位和选项上
    const fx = a.fx;
    pose(ch, a.act, a.idx, x + fx.dx * H, y, z + fx.dz * H, { ...o, hop: (o.hop || 0) + fx.hop * H, lean: (o.lean || 0) + fx.lean,
      yaw: (o.yaw || 0) + fx.yaw, bob: (o.bob ?? 1) * (1 + fx.sq) });
    return true;
  }
  pose(ch, a.act, a.idx, x, y, z, { breath: stillish ? breath(f / FPS) : 1, ...o });
  return true;
}

// ---------- 常用特效（都是发光小方块）----------
// 雨：rain.at(t, 中心x, 中心z, 0~1 的雨量)
export function makeRain(n = 700, color = 0xc9d2e8) {
  const im = instanced(scene, n, 0xffffff, { opacity: 0.55 }); im.material.color.set(color);
  return { im, at(t, cx, cz, amount) {
    const k = Math.floor(n * amount);
    for (let i = 0; i < n; i++) {
      if (i >= k) { setInst(im, i, 0, -50, 0, 0, 0, 0); continue; }
      const x = cx + (hash(i) * 2 - 1) * 16, z = cz + (hash(i + 7.3) * 2 - 1) * 10;
      const y = 12 - ((t * 15 + hash(i + 3.1) * 12) % 12);
      setInst(im, i, x, y, z, 0.035, 0.38, 0.035);
    }
    im.instanceMatrix.needsUpdate = true;
  } };
}
// 爆开的方块粒子：burst.at(f, 爆开帧, x, y, z, 散开范围, 向上速度, i => 颜色)，1.6 秒后消失
export function makeBurst(n = 80, emissive = 0xffffff) {
  const im = instanced(scene, n, 0xffffff, { emissive }); im.material.emissiveIntensity = 0.9;
  const c = new THREE.Color();
  return { im, at(f, f0, cx, cy, cz, spread, up, colorFn) {
    for (let i = 0; i < n; i++) {
      const age = (f - f0) / FPS;
      if (age < 0 || age > 1.6) { setInst(im, i, 0, -50, 0, 0, 0, 0); continue; }
      const a = hash(i * 1.3) * Math.PI * 2, sp = (0.4 + hash(i * 2.9)) * spread;
      const x = cx + Math.cos(a) * sp * age, z = cz + Math.sin(a) * sp * age * 0.5, y = cy + (up * (0.5 + hash(i * 5.1))) * age - 4.5 * age * age;
      const s = 0.09 * (1 - age / 1.6) + 0.02;
      setInst(im, i, x, y, z, s, s, s, age * 3, age * 2, 0);
      if (colorFn) { c.set(colorFn(i)); im.setColorAt(i, c); }
    }
    im.instanceMatrix.needsUpdate = true; if (im.instanceColor) im.instanceColor.needsUpdate = true;
  }, hide() { for (let i = 0; i < n; i++) setInst(im, i, 0, -50, 0, 0, 0, 0); im.instanceMatrix.needsUpdate = true; } };
}

// =====================================================================
// 段内转场：A（旧镜头）和 B（新镜头）分别渲到两张图，再用全屏着色器混合。
// 模式：1 方块雨落  5 甩镜上摇  6 穿梭推进  7 拉远  8 碎裂崩塌  10 体素化（光爆）  11 横条滑移  12 甩镜横移
//      13 闪白/闪黑  14 落色再起  15 圈入圈出  16 形状匹配  17 遮挡扫过  18 故障  19 拉穿  20 旋转  21 光晕扫过  22 分屏滑开  23 抖帧硬切
// =====================================================================
const rtOpts = { type: THREE.HalfFloatType, samples: 4, colorSpace: THREE.LinearSRGBColorSpace };
const rtA = new THREE.WebGLRenderTarget(1920, 1080, rtOpts), rtB = new THREE.WebGLRenderTarget(1920, 1080, rtOpts);
const tMat = new THREE.ShaderMaterial({
  uniforms: {
    tA: { value: rtA.texture }, tB: { value: rtB.texture }, p: { value: 0 }, mode: { value: 0 },
    center: { value: new THREE.Vector2(0.5, 0.5) }, grid: { value: new THREE.Vector2(16, 9) },
    glow: { value: new THREE.Color(0xfff4e0) }, glowAmt: { value: 0.0 },
    uColor: { value: new THREE.Color('#ffffff') }, uDir: { value: 1.0 }, uOff: { value: new THREE.Vector2() },
  },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: `
    uniform sampler2D tA, tB; uniform float p; uniform int mode; uniform vec2 center, grid;
    uniform vec3 glow; uniform float glowAmt; uniform vec3 uColor; uniform float uDir; uniform vec2 uOff; varying vec2 vUv;
    float h1(vec2 c){ return fract(sin(dot(c, vec2(127.1, 311.7))) * 43758.5453); }
    float eio(float x){ x = clamp(x, 0.0, 1.0); return x < 0.5 ? 4.0*x*x*x : 1.0 - pow(-2.0*x + 2.0, 3.0) / 2.0; }
    vec3 tex(int which, vec2 uv){ uv = clamp(uv, 0.001, 0.999); return which == 0 ? texture2D(tA, uv).rgb : texture2D(tB, uv).rgb; }
    float delay(vec2 cell){
      vec2 cc = (cell + 0.5) / grid;
      if (mode == 1) return (1.0 - cc.y) * 0.25 + h1(vec2(cell.x, 7.0)) * 0.75;
      return h1(cell);
    }
    vec3 cube(int which, vec2 cell, vec2 lq, float sz){
      vec3 c = tex(which, (cell + 0.5 + lq / (2.0 * sz)) / grid);
      float e = max(abs(lq.x), abs(lq.y)) / sz;
      c *= 1.0 - 0.35 * smoothstep(0.82, 1.0, e);
      c += 0.18 * smoothstep(0.82, 1.0, e) * step(0.0, lq.y) * step(abs(lq.x), lq.y);
      return c;
    }
    void main(){
      vec2 uv = vUv; vec3 col;
      float e = eio(p);
      if (mode == 5 || mode == 12) {         // 甩镜：5 往上，12 横向（内容往左走）
        float sp = abs(eio(p + 0.05) - eio(p - 0.05)) * 0.8;
        vec3 acc = vec3(0.0);
        for (int i = 0; i < 16; i++) {
          float o = (float(i) / 15.0 - 0.5) * sp;
          if (mode == 5) { float v = uv.y + e + o; acc += v < 1.0 ? tex(0, vec2(uv.x, v)) : tex(1, vec2(uv.x, v - 1.0)); }
          else { float u = uv.x + e + o; acc += u < 1.0 ? tex(0, vec2(u, uv.y)) : tex(1, vec2(u - 1.0, uv.y)); }
        }
        col = acc / 16.0;
      } else if (mode == 6 || mode == 7) {   // 6 穿梭推进（径向模糊），7 拉远
        float zA = 1.0 + 2.0 * e * e, zB = 1.0 + 1.2 * (1.0 - e) * (1.0 - e);
        if (mode == 7) { zA = 1.0 / (1.0 + 1.5 * e * e); zB = 1.0 / (1.0 + 1.0 * (1.0 - e) * (1.0 - e)); }
        float blur = sin(p * 3.14159) * 0.12;
        vec3 a = vec3(0.0), b = vec3(0.0);
        for (int i = 0; i < 12; i++) {
          float k = 1.0 - blur * float(i) / 11.0;
          a += tex(0, center + (uv - center) / (zA / k));
          b += tex(1, center + (uv - center) / (zB / k));
        }
        col = mix(a / 12.0, b / 12.0, smoothstep(0.35, 0.65, p));
        col += glow * glowAmt * sin(p * 3.14159);
      } else if (mode == 10) {               // 体素化：画面碎成方块，换画面，再拼回来
        float bump = sin(p * 3.14159);
        float n = mix(140.0, 9.0, pow(bump, 0.7));
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
      } else if (mode == 11) {               // 横条滑移
        float row = floor(uv.y * grid.y);
        float dir = mod(row, 2.0) < 1.0 ? 1.0 : -1.0;
        float d = (1.0 - (row + 0.5) / grid.y) * 0.5;
        float s = eio((p - d) / 0.5);
        float x = uv.x - dir * s;
        if (x >= 0.0 && x <= 1.0) col = tex(0, vec2(x, uv.y));
        else col = tex(1, vec2(x + dir, uv.y));
        float seam = abs(x - (dir > 0.0 ? 0.0 : 1.0));
        col += glow * 0.5 * (1.0 - smoothstep(0.0, 0.006, seam)) * step(0.001, s) * step(s, 0.999);
      } else if (mode == 13) {               // 闪白/闪黑（uColor，默认白）：中点最亮，前后各露出一边画面
        col = mix(tex(p < 0.5 ? 0 : 1, uv), uColor, clamp(sin(p * 3.14159) * 1.15, 0.0, 1.0));
      } else if (mode == 14) {               // 落色再起（uColor，默认黑）：A 落进颜色、停一拍、B 从颜色里浮出来
        float g = p < 0.5 ? 1.0 - eio(p / 0.45) : eio((p - 0.55) / 0.45);
        col = mix(uColor, tex(p < 0.5 ? 0 : 1, uv), clamp(g, 0.0, 1.0));
      } else if (mode == 15) {               // 圈入圈出（center=圆心，dir=+1 新画面从圆心长出来 / -1 旧画面收进圆里）
        float r = length((uv - center) * vec2(1.7778, 1.0));
        float rr = (uDir > 0.0 ? e : 1.0 - e) * 1.3;
        col = mix(uDir > 0.0 ? tex(1, uv) : tex(0, uv), uDir > 0.0 ? tex(0, uv) : tex(1, uv), smoothstep(-0.004, 0.004, r - rr));
      } else if (mode == 16) {               // 形状匹配：uOff = a−b（JS 按 cut.match 算），B 从匹配位置滑回原位
        col = mix(tex(0, uv), tex(1, uv + uOff * (1.0 - e)), smoothstep(0.3, 0.7, e));
      } else if (mode == 17) {               // 遮挡扫过：一块色板（uColor，默认深色）从 dir=+1 左往右扫过，前后换画面
        float d = uDir > 0.0 ? uv.x : 1.0 - uv.x;
        float head = e * 1.4 - 0.2, w = 0.18;
        col = mix(tex(0, uv), tex(1, uv), 1.0 - step(head - w, d));
        float band = 1.0 - smoothstep(w * 0.8, w, abs(d - head));
        vec3 occ = uColor * (0.82 + 0.18 * h1(floor(uv * vec2(48.0, 27.0)))) * (0.85 + 0.15 * uv.y);
        col = mix(col, occ, band);
      } else if (mode == 18) {               // 故障：中段最强，RGB 分离 + 行块错位，信号坏掉的感觉里换画面
        float g = sin(p * 3.14159), tt = floor(p * 12.0);
        float blk = step(0.35, h1(vec2(floor(uv.y * 16.0), tt)));
        float off = (h1(vec2(tt, 7.7)) - 0.5) * 0.1 * g * blk;
        vec2 uvd = uv + vec2(off, 0.0);
        vec3 cA = vec3(tex(0, uvd + vec2(0.012, 0.0) * g).r, tex(0, uvd).g, tex(0, uvd - vec2(0.012, 0.0) * g).b);
        vec3 cB = vec3(tex(1, uvd + vec2(0.012, 0.0) * g).r, tex(1, uvd).g, tex(1, uvd - vec2(0.012, 0.0) * g).b);
        col = mix(cA, cB, step(0.5, p));
        col += uColor * g * g * 0.25;
      } else if (mode == 19) {               // 拉穿：A 往 center 冲进去、黑点一捏，B 从里面拉出来（比 through 重）
        float zA = 1.0 + 3.0 * e * e, zB = 1.0 + 2.4 * (1.0 - e) * (1.0 - e);
        float blur = sin(p * 3.14159) * 0.28;
        vec3 a = vec3(0.0), b = vec3(0.0);
        for (int i = 0; i < 12; i++) {
          float k = 1.0 - blur * float(i) / 11.0;
          a += tex(0, center + (uv - center) / (zA / k));
          b += tex(1, center + (uv - center) / (zB / k));
        }
        col = mix(a / 12.0, b / 12.0, smoothstep(0.4, 0.6, p));
        col = mix(col, uColor, 0.55 * sin(p * 3.14159));
      } else if (mode == 20) {               // 旋转：A 转着放大出画，B 转着缩小进画（dir=±1 转向，center=旋转中心）
        float a1 = uDir * e * 2.2, a2 = uDir * (1.0 - e) * 2.2;
        vec2 pA = center + mat2(cos(a1), -sin(a1), sin(a1), cos(a1)) * (uv - center) / mix(1.0, 2.6, e);
        vec2 pB = center + mat2(cos(a2), -sin(a2), sin(a2), cos(a2)) * (uv - center) / mix(2.6, 1.0, e);
        col = mix(tex(0, pA), tex(1, pB), smoothstep(0.35, 0.65, e));
      } else if (mode == 21) {               // 光晕扫过：暖光（uColor，默认暖黄）从 dir=+1 左下角漫进来，把画面换成 B
        float d = (uv.x + uv.y) * 0.5;
        if (uDir < 0.0) d = 1.0 - d;
        float head = e * 1.5 - 0.15;
        col = mix(tex(0, uv), tex(1, uv), 1.0 - smoothstep(head - 0.5, head, d));
        col += uColor * exp(-abs(d - head) * 7.0) * 0.6;
      } else if (mode == 22) {               // 分屏滑开：A 左右两半往 dir=+1 两边滑开，露出底下的 B
        float s = eio(p), side = uv.x < 0.5 ? 1.0 : -1.0;
        float x = uv.x + side * uDir * s;
        col = (x >= 0.0 && x <= 1.0) ? tex(0, vec2(x, uv.y)) : tex(1, uv);
        float seam = min(abs(uv.x - s), abs(uv.x - (1.0 - s)));
        col += glow * 0.5 * (1.0 - smoothstep(0.0, 0.006, seam)) * step(0.001, s) * step(s, 0.999);
      } else if (mode == 23) {               // 抖帧硬切：A B A B B 五段跳切，最后一跳落回 key 那一拍
        int seg = int(p * 5.0);
        bool b = seg == 1 || seg >= 3;
        col = tex(b ? 1 : 0, uv);
      } else {                               // 1 方块雨落进新画面，8 旧画面碎成方块掉下去
        vec2 cell = floor(uv * grid);
        float w = 0.45;
        bool crumble = mode == 8;
        float own = clamp((p - delay(cell) * (1.0 - w)) / w, 0.0, 1.0);
        col = crumble ? (own <= 0.0 ? tex(0, uv) : tex(1, uv)) : (own >= 1.0 ? tex(1, uv) : tex(0, uv));
        for (int k = 0; k < 6; k++) {
          vec2 c2 = cell + vec2(0.0, crumble ? float(k) : -float(k));
          float s2 = clamp((p - delay(c2) * (1.0 - w)) / w, 0.0, 1.0);
          if (s2 <= 0.0 || s2 >= 1.0) continue;
          float dy = crumble ? s2 * s2 * 4.0 : -(1.0 - s2) * (1.0 - s2) * 6.0;
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
const tCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const tScene = new THREE.Scene(); tScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), tMat));

// 微缩后期（每帧）：拷贝帧缓冲再处理，不经过 render target，角色贴图不会被色调映射两次。
// 移轴模糊（focus 焦点高度、band 清晰带宽）、亮部泛光、调色（见下面 GRADE）、暗角；hblur 横向动态模糊（像素，甩镜交接用）
const fbTex = new THREE.FramebufferTexture(1920, 1080), fbPos = new THREE.Vector2(0, 0);
const pMat = new THREE.ShaderMaterial({
  uniforms: { tP: { value: fbTex }, focus: { value: 0.5 }, band: { value: 0.22 }, hblur: { value: 0 },
    gExp: { value: 1 }, gCon: { value: 1 }, gSat: { value: 1 }, gTemp: { value: 0 }, gTint: { value: 0 },
    gSh: { value: new THREE.Vector3(0.5, 0.5, 0.5) }, gShA: { value: 0 }, gHi: { value: new THREE.Vector3(0.5, 0.5, 0.5) }, gHiA: { value: 0 }, gVig: { value: 0.28 } },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: `
    uniform sampler2D tP; uniform float focus, band, hblur; varying vec2 vUv;
    uniform float gExp, gCon, gSat, gTemp, gTint, gShA, gHiA, gVig; uniform vec3 gSh, gHi;
    void main(){
      vec2 px = vec2(1.0 / 1920.0, 1.0 / 1080.0);
      vec3 c;
      if (hblur > 0.5) {
        vec3 acc = vec3(0.0);
        for (int i = 0; i < 32; i++) acc += texture2D(tP, vUv + vec2((float(i) / 31.0 - 0.5) * hblur * px.x, 0.0)).rgb;
        c = acc / 32.0;
      } else c = texture2D(tP, vUv).rgb;
      float d = abs(vUv.y - focus);
      float r = smoothstep(band, band + 0.3, d) * 5.0 * step(hblur, 0.5);
      vec3 acc = c; float n = 1.0;
      if (r > 0.05) {
        for (int i = 0; i < 12; i++) {
          float a = float(i) * 2.39996, rr = r * sqrt((float(i) + 0.5) / 12.0);
          acc += texture2D(tP, vUv + vec2(cos(a), sin(a)) * rr * px).rgb; n += 1.0;
        }
      }
      vec3 col = acc / n;
      col += max(col - 0.85, 0.0) * 0.35;
      // 调色：曝光 → 冷暖 / 偏绿偏品红 → 暗部、亮部染色 → 对比 → 饱和（全中性时等于没调）
      col *= gExp;
      col *= vec3(1.0 + 0.08 * gTemp - 0.02 * gTint, 1.0 + 0.04 * gTint, 1.0 - 0.08 * gTemp - 0.02 * gTint);
      float lu = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col += (gSh - 0.5) * gShA * (1.0 - smoothstep(0.0, 0.6, lu));
      col += (gHi - 0.5) * gHiA * smoothstep(0.4, 1.0, lu);
      col = (col - 0.5) * gCon + 0.5;
      lu = dot(col, vec3(0.2126, 0.7152, 0.0722));
      col = max(mix(vec3(lu), col, gSat), 0.0);
      vec2 q = vUv - 0.5; col *= 1.0 - gVig * smoothstep(0.35, 0.85, length(q * vec2(1.25, 1.0)));
      gl_FragColor = vec4(col, 1.0);
    }`,
  depthTest: false, depthWrite: false, toneMapped: false,
});
const pScene = new THREE.Scene(); pScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), pMat));

// ---------- 调色（GRADE）：按段落 / 场景变的色调，角色和场景一起调，字幕不受影响 ----------
// plan.json 的 grade：[{f, exp, con, sat, temp, tint, shadow, shadowAmt, hi, hiAmt, vig, ease, dark, why}]，f 是全曲帧号。
// 从 f 开始用 ease 帧（默认 0：在这一帧直接切，适合放在转场关键帧上）从上一个关键帧过渡过来；没写的参数是中性值。
// setupShot 返回的 grade（同样的字段）叠加在上面，做一闪、渐暗之类的镜头内变化：exp/con/sat 相乘，temp/tint 相加，其余覆盖。
export const GRADE0 = { exp: 1, con: 1, sat: 1, temp: 0, tint: 0, shadow: '#808080', shadowAmt: 0, hi: '#808080', hiAmt: 0, vig: 0.28 };
const _gc = new THREE.Color(), _gc2 = new THREE.Color();
function gradeKeys() { return (PLAN.grade || []).slice().sort((a, b) => a.f - b.f); }
function lerpGrade(a, b, k) {
  const o = {};
  for (const n of Object.keys(GRADE0)) {
    if (n === 'shadow' || n === 'hi') { _gc.set(a[n]); _gc2.set(b[n]); o[n] = '#' + _gc.lerp(_gc2, k).getHexString(); }
    else o[n] = a[n] + (b[n] - a[n]) * k;
  }
  return o;
}
export function gradeAt(f) {
  const keys = gradeKeys(); let cur = { ...GRADE0 };
  for (const g of keys) {
    if (f < g.f) break;
    const tgt = { ...GRADE0, ...g }, e = g.ease || 0;
    cur = e > 0 && f < g.f + e ? lerpGrade(cur, tgt, easeIO((f - g.f + 1) / e)) : tgt;
  }
  return cur;
}
function applyGrade(f, extra) {
  const g = gradeAt(f);
  if (extra) for (const [n, v] of Object.entries(extra)) {
    if (n === 'exp' || n === 'con' || n === 'sat') g[n] *= v; else if (n === 'temp' || n === 'tint') g[n] += v; else if (n in GRADE0) g[n] = v;
  }
  const u = pMat.uniforms;
  u.gExp.value = g.exp; u.gCon.value = g.con; u.gSat.value = g.sat; u.gTemp.value = g.temp; u.gTint.value = g.tint;
  _gc.set(g.shadow); u.gSh.value.set(_gc.r, _gc.g, _gc.b); u.gShA.value = g.shadowAmt;
  _gc.set(g.hi); u.gHi.value.set(_gc.r, _gc.g, _gc.b); u.gHiA.value = g.hiAmt; u.gVig.value = g.vig;
  return g;
}

// =====================================================================
// 表情符号：代码拼的方块符号，挂在角色头顶，大小跟头走，在拍上弹出、随拍轻跳
// =====================================================================
export const GLYPH = {
  heart:      { c: '#ff5c8d', g: ['.XX.XX.', 'XXXXXXX', 'XXXXXXX', '.XXXXX.', '..XXX..', '...X...'] },
  heartbreak: { c: '#d9466f', g: ['.XX.XX.', 'XXX.XXX', 'XX.XXXX', '.XXX.X.', '..X.X..', '...X...'] },
  star:       { c: '#ffd447', g: ['...X...', '...X...', '..XXX..', 'XXXXXXX', '..XXX..', '...X...', '...X...'] },
  sparkle:    { c: '#fff2a8', g: ['..X..', '..X..', 'XX.XX', '..X..', '..X..'] },
  exclaim:    { c: '#ff5a4f', g: ['XX', 'XX', 'XX', 'XX', '..', 'XX'] },
  question:   { c: '#4fa3ff', g: ['.XXX.', 'X...X', '...X.', '..X..', '.....', '..X..'] },
  note:       { c: '#8a74e0', g: ['..XXX', '..X.X', '..X..', '..X..', 'XXX..', 'XXX..'] },
  cloud:      { c: '#8d8ca3', g: ['..XXX...', '.XXXXXX.', 'XXXXXXXX', 'XXXXXXXX'] },
  sweat:      { c: '#8fd3ff', g: ['.X.', 'XXX', 'XXX', '.X.'] },
  tear:       { c: '#6fc3ff', g: ['.X.', '.X.', 'XXX', 'XXX', '.X.'] },
  dots:       { c: '#6f6a86', g: ['X.X.X'] },
  zzz:        { c: '#9a8fe0', g: ['XXX....', '..X....', 'XXX.XX.', '.....X.', '....XX.'] },
  idea:       { c: '#ffe066', g: ['.XXX.', 'XXXXX', 'XXXXX', '.XXX.', '.X.X.', '.XXX.'] },
  anger:      { c: '#ff4f4f', g: ['XX.XX', 'X...X', '.....', 'X...X', 'XX.XX'] },
  dizzy:      { c: '#c58cff', g: ['.XXX.', 'X...X', 'X.X.X', 'X..X.', '.XX..'] },
  flower:     { c: '#ff9ccf', g: ['.X.X.', 'XXXXX', '.XOX.', 'XXXXX', '.X.X.'] },
};
export const GLYPH_CN = { 爱心: 'heart', 心碎: 'heartbreak', 星星: 'star', 闪光: 'sparkle', 感叹号: 'exclaim', 问号: 'question', 音符: 'note', 乌云: 'cloud', 汗滴: 'sweat', 泪滴: 'tear', 省略号: 'dots', zzz: 'zzz', 灯泡: 'idea', 怒: 'anger', 晕: 'dizzy', 小花: 'flower' };
const fx = document.getElementById('fx');
export const fxc = fx.getContext('2d');
function shade(hex, k) { const n = parseInt(hex.slice(1), 16); const c = [n >> 16, (n >> 8) & 255, n & 255].map(v => Math.round(k > 1 ? v + (255 - v) * (k - 1) : v * k)); return `rgb(${c})`; }
export function drawGlyph(name, cx, cy, cell, a, t) {
  const G = GLYPH[GLYPH_CN[name] || name]; if (!G) return;
  const rows = G.g, w = rows[0].length, h = rows.length;
  const x0 = cx - w * cell / 2, y0 = cy - h * cell;
  fxc.globalAlpha = a;
  const o = Math.max(2, cell * 0.22);
  fxc.fillStyle = '#2c2440';
  rows.forEach((r, j) => [...r].forEach((ch, i) => { if (ch !== '.') fxc.fillRect(x0 + i * cell - o, y0 + j * cell - o, cell + 2 * o, cell + 2 * o); }));
  rows.forEach((r, j) => [...r].forEach((ch, i) => {
    if (ch === '.') return;
    const x = x0 + i * cell, y = y0 + j * cell, col = ch === 'O' ? '#ffe36b' : G.c;
    fxc.fillStyle = col; fxc.fillRect(x, y, cell, cell);
    fxc.fillStyle = shade(col, 1.45); fxc.fillRect(x, y, cell, cell * 0.28);
    fxc.fillStyle = shade(col, 0.72); fxc.fillRect(x, y + cell * 0.8, cell, cell * 0.2);
  }));
  if (G === GLYPH.cloud) {
    fxc.fillStyle = '#9fd0ff';
    for (let i = 0; i < 4; i++) { const ph = ((t * 2.2 + i * 0.27) % 1); fxc.fillRect(x0 + (1.2 + i * 1.8) * cell, y0 + h * cell + ph * cell * 3, cell * 0.4, cell * 0.8); }
  }
  fxc.globalAlpha = 1;
}
function drawEmotes(f, pts) {
  const t = f / FPS;
  for (const e of PLAN.emotes) {
    if (f < e.f0 || f > e.f1) continue;
    const p = pts.find(q => q.id === e.who); if (!p) continue;
    const hp = p.h * 1080, cell = clamp(hp * 0.03, 5, 18);
    const age = f - e.f0, left = e.f1 - f;
    const pop = age < 5 ? 1 + 0.35 * Math.sin(age / 5 * Math.PI) : 1;
    const a = Math.min(1, age / 2, left / 3 + 0.01);
    const bob = Math.sin(beatOf(t) * Math.PI * 2) * cell * 0.5;
    const dx = e.dx ?? 0.3;
    drawGlyph(e.g, p.top[0] * 1920 + dx * hp, p.top[1] * 1080 - hp * 0.04 + bob, cell * pop, a, t);
  }
}

// =====================================================================
// 交接画面（交接卡 T1–T6）。两边用同一份代码，切点那一帧必然对得上；只在交接窗口里调用
// =====================================================================
export const HANDOFF = {
  T1: { cut: 688, color: '#FFF4E0' },
  T2: { cut: 1353, cx: 960, cy: 432, close0: 1342, black0: 1350, open1: 1373, hMax: 1.15 },
  T3: { cut: 2048, hFrac: 0.40, feetPx: 918, pxPerBeat: 200, exitX: 2200, entryX: -125 },
  T4: { cut: 2590, hFrac: 0.45, feetPx: 918, xPx: 960, act: 'look_up', idx: 3 },
  T5: { cut: 3030, color: '#1F3B66', f0: 3009, f1: 3051 },
  T6: { cut: 3684, blurPx: 120 },
  FADE_IN: { f0: 0, f1: 12 }, FADE_OUT: { f0: 4370, f1: 4405 },
};
const PX_PER_FRAME_T3 = HANDOFF.T3.pxPerBeat / (SPB * FPS);
// T1 入场（S2）：688–689 纯色，然后奶白方块从中间往外裂开，露出画面，到 699 收完
export function drawT1In(f) {
  const T = HANDOFF.T1;
  if (f >= T.cut + 12) return;
  if (f < T.cut + 2) { fxc.fillStyle = T.color; fxc.fillRect(0, 0, 1920, 1080); return; }
  const p = (f - T.cut - 2) / 9, cs = 60, maxD = Math.hypot(960, 540);
  for (let gy = 0; gy < 18; gy++) for (let gx = 0; gx < 32; gx++) {
    const x = gx * cs + cs / 2, y = gy * cs + cs / 2, d = Math.hypot(x - 960, y - 540) / maxD;
    const s = clamp(1 - (p * 1.4 - d - hash(gx * 31 + gy) * 0.2) / 0.3, 0, 1);
    if (s <= 0) continue;
    const w = cs * s * s * (3 - 2 * s);
    fxc.fillStyle = s >= 1 ? T.color : '#FFE9C2'; fxc.fillRect(x - w / 2, y - w / 2, w, w);
  }
}
// T2 圆形收黑 / 开黑，圆心 (50%, 40%)
function irisMask(r) {
  fxc.save(); fxc.fillStyle = '#000'; fxc.beginPath(); fxc.rect(0, 0, 1920, 1080);
  if (r > 0) fxc.arc(HANDOFF.T2.cx, HANDOFF.T2.cy, r, 0, Math.PI * 2, true);
  fxc.fill('evenodd'); fxc.restore();
}
const IRIS_R = Math.hypot(1920 * 0.5, 1080 * 0.6) + 20;
// T2 两边共用的定位：Gemini 的眼睛对准圆心 (50%, 40%)；S2 从 h0 推到 hMax（1342 到顶），S3 从 hMax 拉回到 h1（1393 到位）
export function placeT2(f, h0 = 0.55, h1 = 0.8) {
  const T = HANDOFF.T2, a = actAt('gemini', f); if (!a) return;
  const h = f < T.cut ? lerp(h0, T.hMax, easeIO((f - (T.close0 - 71)) / 71)) : lerp(T.hMax, h1, easeIO((f - T.cut) / 40));
  placeHead(chars.gemini, a.act, a.idx, T.cx, T.cy - 0.07 * h * 1080, h);
}
export function drawT2Out(f) { const T = HANDOFF.T2; if (f < T.close0) return; irisMask(f >= T.black0 ? 0 : IRIS_R * (1 - easeIO((f - T.close0 + 1) / (T.black0 - T.close0)))); }
export function drawT2In(f) { const T = HANDOFF.T2; if (f >= T.open1) return; irisMask(f < T.cut + 3 ? 0 : IRIS_R * easeIO((f - T.cut - 3) / (T.open1 - T.cut - 3))); }
// T3：ZAI 侧面走，一拍一步，屏幕速度固定。出场：2047 那一帧刚好完全出右边画框；入场：2048 那一帧刚从左边进来
export function t3X(f) { const T = HANDOFF.T3; return f < T.cut ? T.exitX + (f - (T.cut - 1)) * PX_PER_FRAME_T3 : T.entryX + (f - T.cut) * PX_PER_FRAME_T3; }
export function placeT3(f) { const ch = chars.zai, a = loopIdx(ch, 'walk_side', f / FPS); return placeOnScreen(ch, 'walk_side', a, t3X(f), HANDOFF.T3.feetPx, HANDOFF.T3.hFrac, { bob: 0 }); }
// T4：同姿势变身，「仰望」第 4 帧，中线 50%，脚底 85%，身高 45%
export function placeT4(name, f) { const T = HANDOFF.T4; return placeOnScreen(chars[name], T.act, T.idx, T.xPx, T.feetPx, T.hFrac, { bob: 0 }); }
// T4 烟花爆闪：中心在角色头顶上方，k 是 0~1 的强度
export function drawFlash(k, cx = 960, cy = 260) {
  if (k <= 0) return;
  const g = fxc.createRadialGradient(cx, cy, 0, cx, cy, 1300);
  g.addColorStop(0, `rgba(255,248,230,${0.95 * k})`); g.addColorStop(0.4, `rgba(255,220,170,${0.55 * k})`); g.addColorStop(1, 'rgba(255,220,170,0)');
  fxc.fillStyle = g; fxc.fillRect(0, 0, 1920, 1080);
}
// T5 巨鲸擦屏（S5 出场、S6 入场同一条鲸）：鲸从左往右游，3028–3031 鲸身占满画面
const WHALE_L = 2350, WHALE_V = (1920 + 24) / (3028 - 3009);
export function drawWhale(f) {
  const T = HANDOFF.T5; if (f < T.f0 || f > T.f1) return;
  const head = (f - T.f0) * WHALE_V, tail = head - WHALE_L, cs = 40;
  const body = (x) => {  // 身体上下边：头圆、尾细
    const u = clamp((x - tail) / WHALE_L, 0, 1);
    const half = u > 0.92 ? 900 * Math.sqrt(Math.max(0, (1 - u) / 0.08)) : u < 0.12 ? 380 + 520 * (u / 0.12) : 900;
    return [540 - half - 60, 540 + half];
  };
  for (let x = Math.floor(Math.max(0, tail - 200) / cs) * cs; x < Math.min(1920, head); x += cs) {
    const [top, bot] = body(x + cs / 2);
    for (let y = Math.floor(top / cs) * cs; y < bot; y += cs) {
      const belly = y > 540 + 380;
      fxc.fillStyle = belly ? '#26487a' : T.color; fxc.fillRect(x, y, cs + 1, cs + 1);
      fxc.fillStyle = 'rgba(255,255,255,0.06)'; fxc.fillRect(x, y, cs, cs * 0.2);
    }
  }
  // 尾鳍、眼睛、嘴角的拼图光
  if (tail > -300 && tail < 1920) { fxc.fillStyle = T.color; fxc.fillRect(tail - 240, 120, 260, 380); fxc.fillRect(tail - 240, 600, 260, 380); }
  if (head - 260 > 0 && head - 260 < 1920) {
    fxc.fillStyle = '#0d1f3a'; fxc.fillRect(head - 300, 330, 44, 44);
    fxc.fillStyle = '#ffd36e'; fxc.fillRect(head - 120, 560, 56, 56);
  }
}
// T6 甩镜：返回这一帧的横向模糊像素（≥ 画面宽 5%）；内容往左走 = 你的镜头往右甩
export function t6Blur(f) { const T = HANDOFF.T6; const d = f < T.cut ? (f - (T.cut - 10)) / 7 : 1 - (f - T.cut - 3) / 17; return clamp(d, 0, 1) * T.blurPx; }

// =====================================================================
// 字幕：每句在句首出现（≤ 0.1 秒），交接窗口里由段落自己决定显示不显示
// =====================================================================
let LYR = [];
const cap = document.getElementById('cap'), veil = document.getElementById('veil');
function caption(t, hideFrom = Infinity) {
  let txt = '', op = 0;
  for (let i = 0; i < LYR.length; i++) {
    const L = LYR[i], next = LYR[i + 1] ? LYR[i + 1].t0 : L.t1 + 1;
    const end = Math.min(next - 0.12, L.t1 + 0.6, hideFrom);
    if (t >= L.t0 - 0.02 && t < end) { txt = L.text; op = smooth(L.t0 - 0.02, L.t0 + 0.12, t) * (1 - smooth(end - 0.12, end, t)); }
  }
  cap.textContent = txt; cap.style.opacity = op;
  cap.style.transform = `translateY(${(1 - op) * 10}px)`;
}

// =====================================================================
// 屏幕上的角色关键点（song-mv 的 window.probe、表情符号的锚点、交接检查）
// =====================================================================
const _v = new THREE.Vector3();
function screenPoints() {
  scene.updateMatrixWorld(); camera.updateMatrixWorld();
  const out = [];
  for (const ch of Object.values(chars)) {
    if (!ch.root.visible || !ch.cur) continue;
    const m = ch.meta, k = ch.k, cv = m.canvas;
    const P = (u, v) => { _v.set((u - cv / 2) * k, (cv / 2 - v) * k, 0).applyMatrix4(ch.plane.matrixWorld).project(camera); return [(_v.x + 1) / 2, (1 - _v.y) / 2]; };
    const q = ch.kp[ch.cur.act][ch.cur.i];
    const top = P(m.center_x, m.baseline_y - m.stand_h), bot = P(m.center_x, m.baseline_y);
    const fx_ = [q[2], q[4], q[6], q[8], q[0]].map(u => P(u, m.baseline_y)[0]);
    out.push({ id: ch.name, h: Math.abs(bot[1] - top[1]), root: P(m.center_x, m.baseline_y - 0.45 * m.stand_h),
      head: P(q[0], q[1]), handL: P(q[2], q[3]), handR: P(q[4], q[5]), footL: P(q[6], q[7]), footR: P(q[8], q[9]), top,
      base: bot, act: ch.cur.act, i: ch.cur.i, xmin: Math.min(...fx_), xmax: Math.max(...fx_) });
  }
  return out;
}

// =====================================================================
// 主循环：段落注册 SEG，引擎负责转场、后期、表情、字幕和页面契约
// SEG = { build(), setupShot(f, sf) → { veilColor, veilOp, focus, band, hblur, hideCaption, grade }, overlay(f) }
// =====================================================================
let SEG = null, CUTS = [], HAS_T2 = false, LASTV = {};
function cutAt(f) { return CUTS.find(k => f >= k.c - k.len / 2 && f < k.c + k.len / 2); }
function shotFrameFor(f) { const cut = cutAt(f); return cut ? (f < cut.c ? cut.c - 1 : cut.c) : f; }
let lastShotId = null;
function setup(f, sf) {
  curT = f / FPS;
  collide.clearIntents();
  hideChars();
  const v = SEG.setupShot(f, sf) || {};
  const shot = shotOf(sf);
  camlib.beginFrame(f, shot.id);              // 运镜轨叠在 setupShot 摆好的机位上（follow 要碰撞后的位置，endFrame 再套）
  if (shot.id !== lastShotId) { collide.collect(); lastShotId = shot.id; }   // 换镜头场景变了，重新收一遍碰撞体
  collide.beginFrame(f, shot.id);
  const tp = (PLAN.touch || []).filter(p => f >= p.f0 && f < p.f1).map(p => [p.a, p.b]);   // 拥抱、牵手：登记的一对不互相推
  const cr = collide.resolveFrame(camera.position, tp);
  collide.clearIntents();
  for (const n of cr.nudges) {   // 推完了重新贴地（文档流程第 4 步）
    const ch = chars[n.who];
    if (ch && ch.o && ch.o.snap !== false) ch.root.position.y = Math.max(ch.o.y0, groundAt(ch.root.position.x, ch.o.y0, ch.root.position.z));
  }
  window.NUDGES = cr.nudges.map(n => ({ ...n, f }));
  window.STUCK = cr.stuck.map(s => ({ ...s, f }));
  camlib.endFrame(f, shot.id);                // follow（读碰撞后的角色位置）+ 记 CAMLOG
  faceCamera();
  return v;
}
function render(f) {
  const t = f / FPS, c0 = cutAt(f), cut = c0 && c0.mode !== 0 ? c0 : null;   // mode 0：自己在 overlay 里画的转场，引擎只登记不混合
  let v;
  if (!cut) {
    v = setup(f, f);
    renderer.setRenderTarget(null); renderer.render(scene, camera);
  } else {
    const vA = setup(f, cut.c - 1); renderer.setRenderTarget(rtA); renderer.render(scene, camera);
    const vB = setup(f, cut.c); renderer.setRenderTarget(rtB); renderer.render(scene, camera);
    renderer.setRenderTarget(null);
    const u = tMat.uniforms;
    u.p.value = (f - (cut.c - cut.len / 2) + 0.5) / cut.len;
    u.mode.value = cut.mode; u.center.value.set(...(cut.center || [0.5, 0.5])); u.grid.value.set(...(cut.grid || [16, 9]));
    u.glowAmt.value = cut.glowAmt || 0;
    u.uColor.value.set(cut.color || TINT[cut.mode] || '#ffffff');
    u.uDir.value = cut.dir ?? 1;
    if (cut.match) u.uOff.value.set(cut.match.a[0] - cut.match.b[0], cut.match.a[1] - cut.match.b[1]); else u.uOff.value.set(0, 0);
    renderer.render(tScene, tCam);
    v = f < cut.c ? vA : vB;
  }
  camlib.take(cut ? (f < cut.c ? 0 : 1) : 0);   // 可见那一侧的运镜记档（CAMLOG 给运镜关用）
  pMat.uniforms.focus.value = v.focus ?? 0.5; pMat.uniforms.band.value = v.band ?? 0.22; pMat.uniforms.hblur.value = v.hblur ?? 0;
  applyGrade(f, v.grade);
  renderer.copyFramebufferToTexture(fbPos, fbTex); renderer.render(pScene, tCam);
  veil.style.background = v.veilColor || '#000'; veil.style.opacity = v.veilOp || 0;
  fxc.clearRect(0, 0, 1920, 1080);
  if (!cut) drawEmotes(f, screenPoints());
  if (SEG.overlay) SEG.overlay(f);
  const T2 = HANDOFF.T2, blackout = HAS_T2 && f >= T2.black0 && f < T2.cut + 3;   // T2 全黑那几帧连字幕也不出，保证全黑
  caption(t, v.hideCaption || blackout ? -1 : Infinity);
}


// =====================================================================
// 体素关自报：window.voxelProbe(t) → 每个角色的世界身高、贴地、鞋底遮挡、屏幕像素高、坏帧，以及后期参数。
// tools/voxel_dump.mjs 逐帧读，tools/voxel_check.py 判 V1–V7。自己改引擎时保留这个函数
// =====================================================================
const _rc = new THREE.Raycaster(), _sp = new THREE.Vector3(), _cp = new THREE.Vector3();
function solid(o) {   // 会挡住鞋底的场景物体：可见、不透明的普通网格（粒子、雨、立牌、影子不算）
  for (let p = o; p; p = p.parent) if (!p.visible) return false;
  return o.isMesh && !o.isInstancedMesh && !(o.material && (o.material.transparent || o.material.depthTest === false));
}
function voxelInfo(v) {
  scene.updateMatrixWorld(); camera.updateMatrixWorld();
  const planes = new Set(Object.values(chars).flatMap(c => [c.plane, c.sh]));
  const blockers = []; scene.traverse(o => { if (!planes.has(o) && solid(o)) blockers.push(o); });
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
  const pts = screenPoints(), out = [];
  for (const p of pts) {
    const ch = chars[p.id], m = ch.meta, k = ch.k, cv = m.canvas, q = ch.kp[ch.cur.act][ch.cur.i];
    const eyeSole = m.eye_sole || 0.61 * m.stand_h / (m.mv_scale || 1);
    const W = ch.root.position;
    let g = groundAt(W.x, W.y, W.z), deep = false;
    if (g === -Infinity && grounds.some(o => o.visible)) {   // 名义高度附近没地面：往下多找一段，找到了就是飘在空中
      _o.set(W.x, W.y + 0.45, W.z); _ray.set(_o, _down); _ray.far = 60;
      const hit = _ray.intersectObjects(grounds.filter(o => o.visible), true).find(h => h.object.visible);
      if (hit) { g = hit.point.y; deep = true; }
    }
    // 鞋底三个点（左脚、右脚、中线，在脚底线上方 2% 身高）从镜头打射线：foot_r 内撞到算「贴着站」不算挡（推开后贴墙是合法的）
    const footR = Math.max(0.05, m.foot_r ?? 0.3);
    let blocked = 0, tested = 0, legit = 0;
    if (!ch.o.onTop) for (const u of [q[6], q[8], m.center_x]) {
      _sp.set((u - cv / 2) * k, (cv / 2 - (m.baseline_y - 0.02 * m.stand_h)) * k, 0).applyMatrix4(ch.plane.matrixWorld);
      _cp.copy(_sp).sub(camera.position); const d = _cp.length(); _rc.set(camera.position, _cp.normalize());
      tested++;
      _rc.far = d - 0.05;
      if (_rc.intersectObjects(blockers, false).length) {
        _rc.far = d - footR;
        if (_rc.intersectObjects(blockers, false).length) blocked++; else legit++;   // 只在 foot_r 内：推开后贴着的家具
      }
    }
    out.push({ id: p.id, act: ch.cur.act, i: ch.cur.i, bad: !!(m.bad && m.bad[ch.cur.act] && m.bad[ch.cur.act].includes(ch.cur.i)),
      eyeW: eyeSole * k * ch.o.scale, H: H * ch.o.scale, scale: ch.o.scale, snap: ch.o.snap, onTop: ch.o.onTop, hop: ch.o.hop,
      gap: g === -Infinity ? null : W.y - g, noGround: ch.o.snap && g === -Infinity, deep, blocked, legit, tested,
      pos: [W.x, W.y, W.z], right: W.x * right.x + W.y * right.y + W.z * right.z, flip: !!ch.flip !== (Math.cos(ch.yaw || 0) < 0),
      dist: camera.position.distanceTo(W), hpx: p.h * 1080, srcpx: m.stand_h, h: p.h, base: p.base });
  }
  let meshes = 0; scene.traverse(o => { if (o.isMesh && !planes.has(o)) { for (let p = o; p; p = p.parent) if (!p.visible) return; meshes += o.isInstancedMesh ? o.count : 1; } });
  // check --layout 时由 voxel_dump.mjs 设 window.LAYOUT=1：多带一份碰撞体（俯视图 layout_map.py 画灰框用）
  const colliders = window.LAYOUT ? collide.active().map(c => ({ id: c.id, kind: c.kind, shape: c.shape, box: c.box, ...(c.cyl ? { cyl: c.cyl } : {}) })) : [];
  return { chars: out, post: { focus: v.focus ?? 0.5, band: v.band ?? 0.22, hblur: v.hblur ?? 0 }, meshes,
    cam: camlib.last(),     // 运镜档（camera_check.py 的 K1–K6 用）：{pos, target, fov, moves, speed, fixed?}
    colliders, nudges: window.NUDGES || [], stuck: window.STUCK || [] };
}

// 转场模式名 → 着色器编号（plan.json 里写名字）
export const MODES = { rain: 1, whip_up: 5, through: 6, pullback: 7, crumble: 8, voxel: 10, rows: 11, whip: 12,
  flash: 13, dip: 14, iris: 15, match: 16, occlude: 17, glitch: 18, zoom_out: 19, spin: 20, leak: 21, split: 22, jump: 23 };
const KIND = { rain: 'wipe', whip_up: 'whip', through: 'through', pullback: 'through', crumble: 'wipe', voxel: 'voxel', rows: 'slide', whip: 'whip',
  flash: 'flash', dip: 'dip', iris: 'iris', match: 'match', occlude: 'wipe', glitch: 'glitch', zoom_out: 'through', spin: 'rotate', leak: 'leak', split: 'slide', jump: 'cut' };
// 转场色默认值（cut.color 可覆盖）：闪白白、落色黑、遮挡深板、故障冷蓝、拉穿黑捏、光晕暖黄
const TINT = { 13: '#ffffff', 14: '#000000', 17: '#14141c', 18: '#9db8ff', 19: '#000000', 21: '#ffd9a0' };

export async function run(seg) {
  SEG = seg;
  PLAN = await (await fetch('plan.json')).json();
  const START = PLAN.start, END = PLAN.end;
  if (PLAN.tempo) { BEAT0 = PLAN.tempo.beat0; SPB = PLAN.tempo.spb; }
  if (PLAN.handoff_cards) Object.assign(HANDOFF, PLAN.handoff_cards);
  PLAN.cuts ??= []; PLAN.incamera ??= []; PLAN.handoffs ??= []; PLAN.emotes ??= []; PLAN.tracks ??= {}; PLAN.shots ??= []; PLAN.touch ??= [];
  HAS_T2 = PLAN.handoffs.some(h => h.card === 'T2');
  CUTS = PLAN.cuts.map(k => ({ ...k, mode: MODES[k.mode] ?? k.mode }));
  LYR = await (await fetch('assets/lyrics.json')).json();
  try { MOVES = await (await fetch('engine/moves.json')).json(); } catch (err) { MOVES = { slots: {}, phrases: {} }; }
  Object.assign(MOVES.slots, PLAN.slots || {}); Object.assign(MOVES.phrases, PLAN.moves || {});
  await Promise.all(PLAN.cast.map(async name => {
    const tr = (PLAN.tracks[name] || []).filter(e => e[0] !== 'off'), dances = tr.filter(e => e[0] === 'dance');
    const meta = dances.length ? await (await fetch(`assets/${name}/frames.json`)).json() : null;
    const acts = new Set([...tr.filter(e => e[0] !== 'dance').map(e => e[1]), ...dances.flatMap(e => danceActs(meta, e[1])), ...((PLAN.extra_actions || {})[name] || [])]);
    const cards = new Set(PLAN.handoffs.map(h => h.card));
    if (name === 'zai' && cards.has('T3')) acts.add('walk_side');                          // T3 交接
    if ((name === 'zai' || name === 'qwen') && cards.has('T4')) acts.add('look_up');      // T4 交接
    return loadChar(name, acts);
  }));
  collide.init(PLAN, scene, chars, grounds);   // 碰撞：plan.collide 配置 + 本帧场景收碰撞体
  let TL = null;                                // 运镜库的 punch（on: 'hit'）读重击点/炸点；老项目没有这文件就退化到 f0 起跳
  try { TL = await (await fetch('data/audio.timeline.json')).json(); } catch (err) { }
  camlib.init(camera, PLAN, { FPS, beatOf, beatT: b => BEAT0 + b * SPB, hash, chars: () => chars, lookTarget: () => LOOK_T }, TL);
  if (seg.build) await seg.build();
  try { await document.fonts.load('58px "ZCOOL KuaiLe"', LYR.map(l => l.text).join('')); } catch (e) { }   // 字幕字体按字分包，先把用到的字载进来
  await document.fonts.ready;
  window.PLACEHOLDER = !!seg.placeholder;
  window.DUR = (END - START) / FPS;
  window.TRANSITIONS = [
    ...PLAN.cuts.map(k => ({ from: k.from, to: k.to, t0: (k.c - k.len / 2 - START) / FPS, t1: (k.c + k.len / 2 - START) / FPS, key: (k.c - START) / FPS, kind: KIND[k.mode] || k.kind, mv: k.mode, dir: k.dir, note: k.note })),
    ...PLAN.incamera.map(k => ({ from: k.shot, to: k.shot, t0: (k.f0 - START) / FPS, t1: (k.f1 - START) / FPS, key: (k.key - START) / FPS, kind: 'incamera', note: k.note })),
    // 交接也是转场：入场、出场里画面有明显变化的都登记（T3 走出走入画框不算换画面，不登记）
    ...PLAN.handoffs.filter(h => h.kind).map(h => h.side === 'out'
      ? { from: h.shot, to: h.card, t0: (h.f0 - START) / FPS, t1: (h.f1 - START) / FPS, key: (h.key - START) / FPS, kind: h.kind, note: h.note }
      : { from: h.card, to: h.shot, t0: (h.f0 - START) / FPS, t1: (h.f1 - START) / FPS, key: (h.key - START) / FPS, kind: h.kind, note: h.note }),
  ];
  const frameOf = t => Math.min(END - 1, START + Math.round(t * FPS));
  window.render = t => render(frameOf(t));
  window.renderFrame = lf => { render(START + lf); return true; };
  window.probe = t => { const f = frameOf(t); setup(f, shotFrameFor(f)); return screenPoints().map(({ top, ...p }) => p); };
  window.voxelProbe = t => { const f = frameOf(t), sf = shotFrameFor(f), v = setup(f, sf); return { f, shot: shotOf(sf).id, cut: !!cutAt(f), ...voxelInfo(v) }; };
  // 探针合并版：一次 setup 同时给动作关（probe）和体素关（voxelProbe）的数据，tools/probe_all.mjs 用（老引擎没有它就分别调两个）
  window.probeAll = t => { const f = frameOf(t), sf = shotFrameFor(f), v = setup(f, sf), info = voxelInfo(v);
    return { probe: screenPoints().map(({ top, ...p }) => p), voxel: { f, shot: shotOf(sf).id, cut: !!cutAt(f), ...info } }; };
  window.PLAN = PLAN;
  const q = new URLSearchParams(location.search);
  if (q.has('f')) render(+q.get('f'));
  else if (!q.has('export')) {   // 浏览器里直接打开：带音乐预览
    const a = new Audio('data/song.wav'); const t0 = performance.now();
    a.play().catch(() => { });
    const loop = () => { const lf = Math.floor((performance.now() - t0) / 1000 * FPS) % (END - START); render(START + lf); requestAnimationFrame(loop); };
    loop();
  }
  window.READY = true;
}
