// 碰撞系统的 three.js 包装：从场景收集碰撞体（一件家具一个）、每帧更新 AABB、读 plan.json 的 collide 配置，
// 给 relay.js 提供 R.collider / R.noBlock / R.mark / R.spot / R.reserve / R.scatter。
// 纯计算在 collide-core.js（resolveAll）。
import * as THREE from 'three';
import { resolveAll, classify, DEFAULTS } from './collide-core.js';

export const CFG = { ...DEFAULTS, prefer: 'short', off: [] };

const registry = new Map();     // obj -> {kind, shape, pad, seat, id}（R.collider 手工登记）
const noBlockSet = new Set();   // R.noBlock 的对象：子树整棵不参与
const marks = new Map();        // id -> {x, z, face, sit}
const reserves = [];            // {x, z, r}（R.reserve / R.mark 的座位；按坐标去重，setup 每帧重复调用不会堆积）
const reserveKeys = new Set();
let scene = null, grounds = [], charRoots = new Set();
let colliders = [];             // 本帧的碰撞体（beginFrame 重算）
const boxCache = new Map();     // obj -> {sig, box}（世界矩阵没变就复用）

const _box = new THREE.Box3();

function named(o) { return (o.name || '').trim(); }

function skipMesh(o) {   // 和 voxelInfo 的 solid() 同一判定：实例化、透明、关深度都不算实体
  return o.isInstancedMesh || !(o.isMesh && o.material && !o.material.transparent && o.material.depthTest !== false);
}

function inNoBlock(o) { for (let p = o; p; p = p.parent) if (noBlockSet.has(p)) return true; return false; }

function solidBox(obj) {   // 物体的实体 AABB：只算可见、不透明的普通网格
  _box.makeEmpty();
  obj.updateWorldMatrix(true, true);
  obj.traverse(m => {
    if (m.isMesh && !skipMesh(m)) {
      _m.copy(m.boundingBox || (m.boundingBox = new THREE.Box3().setFromBufferAttribute(m.geometry.attributes.position)));
      _m.applyMatrix4(m.matrixWorld); _box.union(_m);
    }
  });
  return _box;
}
const _m = new THREE.Box3();

function mkCol(obj, id, b, reg) {   // 一个碰撞体：AABB + 圆柱参数（shape cyl 用）
  const box = { x0: b.min.x, x1: b.max.x, y0: b.min.y, y1: b.max.y, z0: b.min.z, z1: b.max.z };
  return { id, obj, box, shape: reg?.shape || 'box', kind: reg?.kind || 'auto', pad: reg?.pad,
    cyl: (reg?.shape || 'box') === 'cyl' ? { cx: (box.x0 + box.x1) / 2, cz: (box.z0 + box.z1) / 2, cr: Math.max(box.x1 - box.x0, box.z1 - box.z0) / 2 } : null };
}

function collectUnit(obj, id, depth) {
  if (inNoBlock(obj)) return;
  const reg = registry.get(obj);
  const b = solidBox(obj);
  if (b.isEmpty()) return;
  if (reg) { colliders.push(mkCol(obj, reg.id || id, b, reg)); return; }   // 手工登记的按整件算，不下钻
  const side = Math.max(b.max.x - b.min.x, b.max.y - b.min.y, b.max.z - b.min.z);
  if (side > 6 && depth < 3 && obj.children.length) {   // 大件（房子、整片地面）下钻一层，一件家具一个
    obj.children.forEach((c, i) => collectUnit(c, `${id}/${named(c) || i}`, depth + 1));
    return;
  }
  colliders.push(mkCol(obj, id, b, findRegistry(obj)));
}

function findRegistry(obj) {
  for (let p = obj; p; p = p.parent) { const r = registry.get(p); if (r) return r; }
  return null;
}

// 建完场景跑一次：场景根下的每个直接子 Group 是一件家具（单边 > 6 的下钻）。
// 注意不按 grounds 跳过：真实项目习惯把整个场景容器 addGround 进去，跳过它等于全场景没有碰撞体。
// 地板推不了人这件事由 collide-core 的 classify 管（顶面 ≤ 脚底 + 25% 身高 = low，能踩上去）；
// 真不想让某件家具参与，用 R.noBlock 或 R.collider(obj, { kind: 'ground' })。
export function collect() {
  colliders = [];
  let i = 0;
  for (const top of scene.children) {
    if (charRoots.has(top) || top.isLight || top.isCamera || noBlockSet.has(top)) continue;
    collectUnit(top, named(top) || `物件${i}`, 0);   // 大件（整个场景容器）下钻成一件件家具
    i++;
  }
  return colliders;
}

let offShot = false;
// 每帧（setupShot 之后）：世界矩阵变了的才重算 AABB；不可见的碰撞体这帧跳过
export function beginFrame(f, shotId) {
  offShot = CFG.off.includes(shotId);
  for (const c of colliders) {
    let vis = true;
    for (let p = c.obj; p; p = p.parent) if (!p.visible) { vis = false; break; }
    c.skip = !vis;
    if (!vis) continue;
    c.obj.updateWorldMatrix(true, true);
    const sig = c.obj.matrixWorld.elements.join(',');
    let cached = boxCache.get(c.obj);
    if (!cached || cached.sig !== sig) {
      const b = solidBox(c.obj);
      cached = { sig, box: { x0: b.min.x, x1: b.max.x, y0: b.min.y, y1: b.max.y, z0: b.min.z, z1: b.max.z } };
      boxCache.set(c.obj, cached);
      if (c.shape === 'cyl') { const B = cached.box; c.cyl = { cx: (B.x0 + B.x1) / 2, cz: (B.z0 + B.z1) / 2, cr: Math.max(B.x1 - B.x0, B.z1 - B.z0) / 2 }; }
    }
    c.box = cached.box;
  }
  return colliders;
}

export function active() { return offShot ? [] : colliders.filter(c => !c.skip); }

// ---------- 手工 API（全部可选） ----------
// shots.js 在模块顶层就把场景搭完，R.collider / R.noBlock 于是也在 collide.init 之前跑：
// 那时 scene 还没交进来，collect() 会炸。登记照做，收碰撞体交给 init 和 relay 的换镜头重收。
export function collider(obj, o = {}) { registry.set(obj, { id: o.id || named(obj), ...o }); if (scene) collect(); }
export function noBlock(obj) { noBlockSet.add(obj); if (scene) collect(); }
export function mark(id, x, z, o = {}) { marks.set(id, { x, z, face: o.face, sit: o.sit }); if (o.sit != null) reserve(x, z, 0.45); }
export function spot(id) { const m = marks.get(id); return m ? { x: m.x, z: m.z, face: m.face, sit: m.sit } : null; }
export function reserve(x, z, r = 0.6) { const k = `${x.toFixed(2)},${z.toFixed(2)},${r}`; if (reserveKeys.has(k)) return; reserveKeys.add(k); reserves.push({ x, z, r }); }
export function markList() { return marks; }

// 随机撒树石：fn(i, x, z) 放东西；avoid 时避开预留区和现有碰撞体的占地（地面这类能踩上去的 low 不算障碍）
export function scatter(n, fn, o = {}) {
  const [x0, z0, x1, z1] = o.area || [-20, -14, 20, 14];
  const blocks = (x, z) => colliders.some(c => {
    if (c.skip) return false;
    const k = c.kind && c.kind !== 'auto' ? c.kind : classify(c.box, 0, 2.0);
    return k !== 'low' && k !== 'none' && k !== 'ground' && x > c.box.x0 - 0.7 && x < c.box.x1 + 0.7 && z > c.box.z0 - 0.7 && z < c.box.z1 + 0.7;
  });
  const bad = (x, z) => reserves.some(r => Math.hypot(x - r.x, z - r.z) < r.r + (o.margin ?? 0.6)) || (o.avoid !== false && blocks(x, z));
  for (let i = 0; i < n; i++) {
    for (let t = 0; t < 40; t++) {
      const x = x0 + hash2(i * 7.31 + t * 3.7) * (x1 - x0), z = z0 + hash2(i * 5.17 + t * 9.1 + 40) * (z1 - z0);
      if (!bad(x, z)) { fn(i, x, z); break; }
    }
  }
}
const hash2 = n => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };

// ---------- 接到 relay：每帧收集角色意图 → resolveAll → 应用 ----------
const intents = new Map();      // name -> {x, z, o}
export function init(plan, scn, chars, gnds) {
  scene = scn; grounds = gnds;
  charRoots = new Set(Object.values(chars).map(c => c.root));
  const C = plan.collide || {};
  Object.assign(CFG, C, { off: C.off || [] });
  if (C.pad != null) CFG.pad = C.pad;
  if (C.charGap != null) CFG.gap = C.charGap;
  collect();   // 顶层建场景的项目（shots.js 模块级）在这里才第一次收到碰撞体；build() 里建的老是换镜头时重收
}

export function intent(ch, x, z, o) { intents.set(ch.name, { ch, x, z, o: o || {} }); }

export function clearIntents() { intents.clear(); }

// 在 setupShot 之后、faceCamera 之前跑：推开后写回 ch.root.position，返回 {nudges, stuck}
export function resolveFrame(camPos, touchPairs) {
  const cols = active();
  const list = [];
  for (const { ch, x, z, o } of intents.values()) {
    if (o.collide === false || o.onTop) continue;
    const m = ch.meta;
    const body = { name: ch.name, x, z, r: m.foot_r ?? 0.3, rb: m.body_r ?? 0.45, y0: (ch.o?.y0 ?? 0) + (ch.o?.hop || 0), h: 2.0 * (ch.o?.scale ?? 1), mass: m.mass ?? 1, collide: true,
      touch: o.touch ? new Set([].concat(o.touch)) : null, exclude: o.touchIgnore ? new Set([].concat(o.touchIgnore)) : null };
    const cur = ch.cur;
    if (cur && /^sit/.test(cur.act)) {   // 坐着：找 0.3 内的座位，那个座位不推它
      const seat = cols.find(c => c.kind === 'seat' && Math.hypot(x - (c.cyl ? c.cyl.cx : (c.box.x0 + c.box.x1) / 2), z - (c.cyl ? c.cyl.cz : (c.box.z0 + c.box.z1) / 2)) <= 0.3);
      if (seat) body.sitNear = seat.id;
    }
    list.push(body);
  }
  const r = resolveAll(list, cols, { pad: CFG.pad, prefer: CFG.prefer, cam: camPos ? [camPos.x, camPos.z] : null, gap: CFG.gap, touchPairs });
  for (const b of list) {
    const p = r.pos.get(b.name), it = intents.get(b.name);
    it.ch.root.position.x = p.x; it.ch.root.position.z = p.z;
  }
  return { nudges: r.nudges, stuck: r.stuck };
}

export { marks as markMap, reserves as reserveList };
