// 运镜库（第 4 批）：plan.json 的 camera 轨（声明式）或 setupShot 里 R.cam.*（命令式），
// 叠在 setupShot 摆好的基础机位上（基础机位 = R.look 留下的位置和看向点）。
// 不写 camera 轨、不调 R.cam 的项目：相机一个字段都不动，画面和以前逐帧一致（CAMLOG 照记，moves 为空）。
// 每帧把机位、看向点、fov、用到的运镜种类、实际运动速度记进 CAMLOG（探针带出 → out/voxel.json → camera_check.py 的 K1–K6）。
// K6 安全线在这里运行时夹：环绕 ±50°、俯仰 ±50°、tilt ±35°、fov [16,50]、推近不超过基础距离的一半、
// 手持 0.06 / 冲击 0.3 / 呼吸 0.04 / 滚转 8°；夹了什么记在 entry.fixed，报告里列进「已自动修」。
import * as THREE from 'three';

const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
let CAM = null, PLAN = null, H = null, TL = null;   // CAM=相机；H=引擎帮手；TL=audio.timeline.json（punch 的 hits/drops）
let TRACK = [], registered = [];                    // plan.json 的 camera 轨；R.cam.* 本帧登记的条目
let prevPos = null, prevFov = 28;                   // 上一帧的机位/fov（算 speed 用）
let fovSave = null;                                 // 上一帧被我们改写的 fov {base, applied}：fov 不像机位会被 setupShot 每帧重摆，不撤回会跨帧复利
let frameEntries = [];                              // 本次 render 里每个 setup 产生的 entry（转场帧有两个）
const clampN = (x, a, b) => Math.max(a, Math.min(b, x));
const fix = (e, s) => { const a = e.fixed ??= []; if (!a.includes(s)) a.push(s); };

// ---------- 缓动和 on: beat/bar/hit（把运镜进度锁到节拍网格上，一格一格走，每格 3 帧滑入） ----------
const EASES = {
  linear: x => x,
  easeIO: x => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  easeIn: x => x * x * x,
  easeOut: x => 1 - Math.pow(1 - x, 3),
  back: x => 1 + 2.7 * Math.pow(x - 1, 3) + 1.7 * Math.pow(x - 1, 2),
  expo: x => x >= 1 ? 1 : 1 - Math.pow(2, -10 * x),
};
const easeK = (name, x) => (EASES[name] || EASES.easeIO)(clampN(x, 0, 1));

function gridOf(e) {   // on 的网格（全曲帧号）：beat 用 tempo 网格、bar 每 4 拍、hit 用 TL 的重击点/炸点
  if (e.on === 'hit') {
    const hs = [...(TL?.hits || []), ...(TL?.drops || [])].map(h => Math.round((h.time ?? h) * H.FPS));
    return hs.length ? hs : [e.f0];
  }
  const spb = PLAN.tempo?.spb ?? 0.5, per = e.on === 'bar' ? 4 : 1;
  const b0 = Math.ceil(H.beatOf(e.f0 / H.FPS) - 1e-6), b1 = Math.floor(H.beatOf(e.f1 / H.FPS) + 1e-6);
  const out = [];
  for (let b = Math.ceil(b0 / per) * per; b <= b1; b += per) {
    const f = Math.round(H.beatT(b) * H.FPS);
    if (f >= e.f0 && f <= e.f1) out.push(f);
  }
  return out.length ? out : [e.f0];
}

function progress(e, f) {   // 0→1 进度；写了 on 就按格子走，没写就按 f0–f1 缓动
  if (!e.on) return easeK(e.ease, (f - e.f0) / Math.max(1, e.f1 - e.f0));
  const g = e.grid || (e.grid = gridOf(e));
  let i = g.findIndex(x => x > f);
  if (i === 0) return 0;
  if (i < 0) i = g.length;
  return easeK(e.ease || 'linear', clampN((i - 1 + clampN((f - g[i - 1]) / 3, 0, 1)) / (g.length - 1), 0, 1));
}

// ---------- 单个运镜怎么改工作机位 st = {pos, tgt, fov, baseFov, roll} ----------
function applyMove(st, e, k, e0, shotSeed, f) {
  const dir = V().subVectors(st.tgt, st.pos), dist = dir.length() || 1;
  const dirN = dir.clone().divideScalar(dist);
  const up = V(0, 1, 0), right = V().crossVectors(dirN, up).normalize();
  const rotY = (v, rad) => { const c = Math.cos(rad), s = Math.sin(rad), x = v.x * c + v.z * s, z = -v.x * s + v.z * c; v.x = x; v.z = z; };
  switch (e.move) {
    case 'dolly': st.pos.addScaledVector(dirN, (e.amt ?? 0) * k); break;
    case 'truck': st.pos.addScaledVector(right, (e.amt ?? 0) * k); st.tgt.addScaledVector(right, (e.amt ?? 0) * k); break;
    case 'crane': st.pos.y += (e.amt ?? 0) * k; st.tgt.y += (e.amt ?? 0) * k; break;
    case 'pan': { const d = e.deg ?? e.amt ?? 0; rotY(dirN, THREE.MathUtils.degToRad(d) * k); st.tgt.copy(st.pos).addScaledVector(dirN, dist); break; }
    case 'tilt': {
      let d = e.deg ?? e.amt ?? 0;
      if (Math.abs(d) > 35) { fix(e0, `tilt ${+d.toFixed(1)}° 夹到 ±35°（K6）`); d = Math.sign(d) * 35; }
      const pitch0 = Math.asin(clampN(dirN.y, -1, 1)), hd = dist * Math.cos(pitch0);
      const np = clampN(pitch0 + THREE.MathUtils.degToRad(d) * k, -0.95, 0.95);
      st.tgt.y = st.pos.y + Math.tan(np) * hd;
      break;
    }
    case 'orbit': {
      let a0 = e.from ?? 0, a1 = e.to ?? 0;
      if (Math.abs(a1 - a0) > 50) {
        const n = a0 + Math.sign(a1 - a0) * 50;
        fix(e0, `orbit ${a0}→${e.to}° 夹到 ${a0}→${n}°（环绕过半圈立牌会穿帮，K6）`); a1 = n; e.to = n;
      }
      const p = V().subVectors(st.pos, st.tgt);
      rotY(p, THREE.MathUtils.degToRad(a0 + (a1 - a0) * k));
      st.pos.copy(st.tgt).add(p);
      break;
    }
    case 'zoom': {
      const to = e.to ?? st.baseFov + (e.amt ?? 0), f2 = clampN(st.baseFov + (to - st.baseFov) * k, 16, 50);
      if (f2 === 16 || f2 === 50) fix(e0, 'zoom fov 夹到 [16, 50]（K6）');
      st.fov = f2;
      break;
    }
    case 'dollyzoom': {
      const a = clampN(e.amt ?? 0, -dist * 0.45, dist * 0.45);
      st.pos.addScaledVector(dirN, a * k);
      st.fov = clampN(st.fov + (e.dz ?? 10) * k, 16, 50);
      break;
    }
    case 'roll': {
      let d = e.deg ?? e.amt ?? 0;
      if (Math.abs(d) > 8) { fix(e0, 'roll 夹到 ±8°（K6）'); d = Math.sign(d) * 8; }
      st.roll += d * k;
      break;
    }
    case 'punch': {
      if (!e.on) e.on = 'hit';
      const g = (e.grid || (e.grid = gridOf(e))).reduce((b, x) => (f >= x && x > b ? x : b), -1);
      if (g < 0) break;
      const amt = clampN(e.amt ?? 0.15, 0, 0.3);
      if (amt !== (e.amt ?? 0.15)) fix(e0, 'punch 幅度夹到 ≤0.3（K6）');
      const env = Math.exp(-(f - g) / 3);
      st.fov *= 1 - amt * env;
      if (e.shake) {
        st.pos.x += (H.hash(g * 3.1) * 2 - 1) * e.shake * env;
        st.pos.y += (H.hash(g * 7.7) * 2 - 1) * e.shake * env;
      }
      break;
    }
    case 'handheld': {
      const amt = clampN(e.amt ?? 0.04, 0, 0.06);
      if (amt !== (e.amt ?? 0.04)) fix(e0, 'handheld 幅度夹到 ≤0.06（K6）');
      const w = f / H.FPS, s = shotSeed;
      st.pos.x += (Math.sin(w * 2.1 + s) * 0.5 + Math.sin(w * 5.3 + s * 2) * 0.3 + Math.sin(w * 9.7 + s * 3) * 0.2) * amt;
      st.pos.y += (Math.sin(w * 1.7 + s * 4) * 0.5 + Math.sin(w * 4.9 + s * 5) * 0.3 + Math.sin(w * 8.3 + s * 6) * 0.2) * amt;
      st.tgt.x += (Math.sin(w * 1.3 + s * 7) * 0.5 + Math.sin(w * 6.1 + s * 8) * 0.3) * amt;
      break;
    }
    case 'bob': {
      const amt = clampN(e.amt ?? 0.02, 0, 0.04);
      const ph = ((H.beatOf(f / H.FPS) % 1) + 1) % 1;
      st.pos.y += Math.sin(ph * Math.PI * 2) * amt;
      break;
    }
    case 'follow': break;   // endFrame 里套（要碰撞后的角色位置）
  }
}

export function init(camera, plan, helpers, timeline) {
  CAM = camera; PLAN = plan; H = helpers; TL = timeline || null;
  TRACK = plan.camera || [];
  if (!Array.isArray(window.CAMLOG)) window.CAMLOG = [];
  prevPos = null;
}
export const camlog = () => window.CAMLOG;

// 命令式：setupShot 里 R.cam.dolly({amt: 0.5})——只对这一帧生效（要连续就在自己的代码里逐帧给参数）
const reg = move => (o = {}) => registered.push({ ...o, move, f0: 0, f1: 1e9 });
export const api = { dolly: reg('dolly'), truck: reg('truck'), crane: reg('crane'), pan: reg('pan'), tilt: reg('tilt'),
  orbit: reg('orbit'), zoom: reg('zoom'), dollyzoom: reg('dollyzoom'), roll: reg('roll'), punch: reg('punch'),
  handheld: reg('handheld'), bob: reg('bob'), follow: reg('follow') };

function entriesFor(f, shotId) {
  return [...TRACK.filter(e => f >= e.f0 && f <= e.f1 && (!e.shot || e.shot === shotId)), ...registered];
}

// setupShot 之后（基础机位就位、R.cam.* 登记完）、碰撞解算之前：套用除 follow 外的运镜
export function beginFrame(f, shotId) {
  if (fovSave && CAM.fov === fovSave.applied) { CAM.fov = fovSave.base; CAM.updateProjectionMatrix(); }   // 撤回上一帧的 fov，回到基准（场景若自己改过就不动）
  fovSave = null;
  const es = entriesFor(f, shotId);
  registered = [];
  if (frameEntries.length > 4) frameEntries.shift();      // probe 只 setup 不 take，别让它堆一整片
  const e = { f, shot: shotId, moves: [], fixed: [], done: false };
  frameEntries.push(e);
  if (!es.length) return;                                 // 没写运镜：相机一个字段都不动（老项目逐帧一致）
  const st = { pos: CAM.position.clone(), tgt: H.lookTarget().clone(), fov: CAM.fov, baseFov: CAM.fov, roll: 0 };
  if (!st.tgt.lengthSq()) st.tgt.copy(st.pos).add(V(0, 0, -1));   // 没用过 R.look：拿默认朝向推一个看向点
  e.st = st;
  const seed = [...shotId].reduce((s, c) => s + c.charCodeAt(0) * 7.31, 1.7);
  for (const raw of es) {
    if (raw.move === 'follow') continue;
    const k = raw.f1 > 1e8 ? 1 : progress(raw, f);
    applyMove(st, { ...raw }, k, e, seed, f);
    if (!e.moves.includes(raw.move)) e.moves.push(raw.move);
  }
  CAM.position.copy(st.pos);
  CAM.lookAt(st.tgt);
  if (st.roll) CAM.rotateZ(THREE.MathUtils.degToRad(st.roll));
  if (st.fov !== e.st.baseFov) { CAM.fov = st.fov; CAM.updateProjectionMatrix(); fovSave = { base: st.baseFov, applied: st.fov }; }
  CAM.updateMatrixWorld();
}

// 碰撞解算之后、faceCamera 之前：follow 读碰撞后的角色位置；然后记 CAMLOG
export function endFrame(f, shotId) {
  const e = frameEntries[frameEntries.length - 1];
  if (!e || e.done) return;
  if (e.st) {
    const fs = entriesFor(f, shotId).filter(x => x.move === 'follow');
    const st = e.st;
    for (const raw of fs) {
      const ch = H.chars()[raw.who];
      if (!ch || !ch.root) continue;
      const p = ch.root.position, off = raw.offset || [0, 1.2, 3.5], lk = raw.look || [0, 1.3, 0];
      st.pos.set(p.x + off[0], p.y + off[1], p.z + off[2]);
      st.tgt.set(p.x + lk[0], p.y + lk[1], p.z + lk[2]);
      if (!e.moves.includes('follow')) e.moves.push('follow');
    }
    if (fs.length) {                                      // K6：俯仰安全线
      const dir = V().subVectors(st.tgt, st.pos), horiz = Math.hypot(dir.x, dir.z);
      const pitch = Math.atan2(dir.y, horiz), lim = Math.PI * 50 / 180;
      if (Math.abs(pitch) > lim) { st.tgt.y = st.pos.y + Math.tan(lim) * horiz * Math.sign(dir.y || 1); fix(e, '俯仰夹到 ±50°（K6）'); }
      CAM.position.copy(st.pos);
      CAM.lookAt(st.tgt);
      CAM.updateMatrixWorld();
    }
  }
  e.done = true;
  const P = CAM.position;
  e.pos = [+P.x.toFixed(3), +P.y.toFixed(3), +P.z.toFixed(3)];
  // 看向点用这一帧真正的目标，不要按等距反推：反推出来的相机→看向点距离恒为 5，
  // K1 的 dolly（距离变化）和 zoom 判据就永远不成立。
  // 运镜库开着的镜头读 st.tgt；手写 R.look 的老项目没有 st（beginFrame 没运镜就提前返回了），
  // 退而认 LOOK_T——只有相机真的朝着它看才算，否则（项目直接动 camera）还是用朝向反推。
  const fw = V(0, 0, -1).applyQuaternion(CAM.quaternion);
  let T = (e.st && e.st.tgt.lengthSq() > 0 && e.st.tgt.distanceToSquared(P) > 1e-6) ? e.st.tgt : null;
  if (!T && H.lookTarget) {
    const lt = H.lookTarget(), d = lt.clone().sub(P);
    if (lt.lengthSq() > 1e-6 && d.lengthSq() > 1e-6 && d.normalize().dot(fw) > 0.995) T = lt;
  }
  if (!T) T = P.clone().add(fw.multiplyScalar(5));
  e.target = [+T.x.toFixed(3), +T.y.toFixed(3), +T.z.toFixed(3)];
  e.fov = +CAM.fov.toFixed(2);
  if (prevPos) e.speed = +(P.distanceTo(prevPos) * H.FPS + Math.abs(CAM.fov - prevFov) * 2).toFixed(3);
  prevPos = P.clone(); prevFov = CAM.fov;
}

// render() 每个输出帧调一次：把可见那一侧的 entry 推进 window.CAMLOG
export function take(idx = frameEntries.length - 1) {
  const e = frameEntries[idx];
  frameEntries = [];
  if (!e || e.pos == null) return null;
  const out = { f: e.f, shot: e.shot, pos: e.pos, target: e.target, fov: e.fov, moves: e.moves, speed: e.speed };
  if (e.fixed.length) out.fixed = e.fixed;
  window.CAMLOG.push(out);
  if (window.CAMLOG.length > 30000) window.CAMLOG.splice(0, window.CAMLOG.length - 30000);
  return out;
}
export const last = () => { const e = frameEntries[frameEntries.length - 1]; if (!e || e.pos == null) return null;
  const out = { f: e.f, shot: e.shot, pos: e.pos, target: e.target, fov: e.fov, moves: e.moves, speed: e.speed };
  if (e.fixed.length) out.fixed = e.fixed; return out; };
