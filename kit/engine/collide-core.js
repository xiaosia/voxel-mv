// 碰撞核心：纯计算、不依赖 three.js（song-mv 以后也能用）。
// 输入角色 [{name,x,z,r,rb,y0,h,mass,collide,touch,sitNear,exclude}]、碰撞体 [{id,box,shape,pad,kind,noBlock}]，
// 输出推开后的位置、NUDGES（谁被谁推了多少）、STUCK（推不开的，带原因和建议）。
// box 是世界 AABB {x0,x1,y0,y1,z0,z1}；shape 'box' | 'cyl'（cyl 另有 cx/cz/cr）。
export const DEFAULTS = {
  pad: 0.05,          // 碰撞体外扩
  stepFrac: 0.25,     // 顶面 ≤ y0 + 0.25H：矮，不推（能踩上去）
  headMin: 0.7,       // 底面在 y0 + 0.7H 以上、净空以下：头顶太低（穿胸的横梁也算）
  overTop: 1.15,      // 底面 ≥ y0 + 1.15H：高过头顶，忽略
  pushMax: 0.8,       // 一帧里累计推开超过这个数：照常渲染，但记 STUCK
  gap: 0.1,           // 角色两两之间的额外空隙
};

// 这个碰撞体对某个角色算什么：y0 脚底高度、h 身高。手工给过 kind（auto 以外）就不重新算
export function classify(box, y0, h, o = DEFAULTS) {
  if (box.y1 <= y0 + o.stepFrac * h) return 'low';
  if (box.y0 >= y0 + o.overTop * h) return 'none';
  if (box.y0 >= y0 + o.headMin * h) return 'over';
  return 'solid';
}

// 圆和 AABB 的 xz 投影：返回推出向量（最小平移），不相交返回 null
export function pushOutBox(px, pz, r, b) {
  const cx = Math.max(b.x0, Math.min(px, b.x1)), cz = Math.max(b.z0, Math.min(pz, b.z1));
  const dx = px - cx, dz = pz - cz, d2 = dx * dx + dz * dz;
  if (d2 > r * r) return null;
  if (d2 > 1e-9) {
    const d = Math.sqrt(d2);
    return { x: dx / d * (r - d), z: dz / d * (r - d) };
  }
  const l = px - b.x0, rr = b.x1 - px, bk = pz - b.z0, t = b.z1 - pz, m = Math.min(l, rr, bk, t);
  if (m === l) return { x: -(l + r), z: 0 };
  if (m === rr) return { x: rr + r, z: 0 };
  if (m === bk) return { x: 0, z: -(bk + r) };
  return { x: 0, z: t + r };
}

// 圆和圆柱（cx,cz,cr）：返回推出向量，不相交返回 null
export function pushOutCyl(px, pz, r, c) {
  const dx = px - c.cx, dz = pz - c.cz, d = Math.hypot(dx, dz), R = r + c.cr;
  if (d >= R) return null;
  if (d < 1e-6) return { x: R, z: 0 };
  return { x: dx / d * (R - d), z: dz / d * (R - d) };
}

// 把所有角色推开。opts：{pad, prefer:'short'|'away', cam:[x,z], gap}
// 结果只由当帧输入决定（纯函数）：分块并行渲染和单独渲染一帧，位置一致。
export function resolveAll(list, colliders, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const pos = new Map(list.map(c => [c.name, { x: c.x, z: c.z }]));
  const nudges = [], stuck = [];
  for (const ch of list) {
    if (ch.collide === false) continue;
    let x = ch.x, z = ch.z, total = 0, by = null, over = null, unresolved = false;
    for (let it = 0; it < 3; it++) {
      let moved = false;
      for (const col of colliders) {
        if (col.noBlock) continue;
        if (ch.exclude && ch.exclude.has(col.id)) continue;
        const kind = col.kind === 'ground' || col.kind === 'none' ? col.kind : (col.kind && col.kind !== 'auto' ? col.kind : classify(col.box, ch.y0, ch.h, o));
        if (kind === 'ground' || kind === 'low' || kind === 'none') continue;
        if (kind === 'seat' && ch.sitNear === col.id) continue;   // 坐在自己的座位上：不推
        const r = (ch.touch && ch.touch.has(col.id)) ? Math.min(ch.r, 0.06) : ch.r + (col.pad ?? o.pad);   // touch：只推到贴边
        const p = col.shape === 'cyl' ? pushOutCyl(x, z, r, col) : pushOutBox(x, z, r, col.box);
        if (!p) continue;
        if (o.prefer === 'away' && o.cam) {   // 方向优先远离镜头：能推出去就用这个方向
          const dx = x - o.cam[0], dz = z - o.cam[1], d = Math.hypot(dx, dz);
          if (d > 1e-6) {
            const ux = dx / d, uz = dz / d;
            const nx = x + ux * (r + 1e-3) * 2, nz = z + uz * (r + 1e-3) * 2;   // 试探位置
            const q = col.shape === 'cyl' ? pushOutCyl(nx, nz, r, col) : pushOutBox(nx, nz, r, col.box);
            if (!q) { p.x = ux * (Math.hypot(p.x, p.z) + 0.02); p.z = uz * (Math.hypot(p.x, p.z) + 0.02); }
          }
        }
        x += p.x; z += p.z;
        const d = Math.hypot(p.x, p.z);
        total += d; by = col.id; moved = true;
        if (kind === 'over') over = col;
      }
      if (!moved) { break; }
      if (it === 2) unresolved = true;
    }
    pos.set(ch.name, { x, z });
    if (total > 1e-4) nudges.push({ who: ch.name, from: [ch.x, ch.z], to: [x, z], by, dist: total });
    if (over) stuck.push({ who: ch.name, by: over.id, reason: '头顶太低',
      hint: `${over.id} 底面 ${over.box.y0.toFixed(2)}，${ch.name} 身高 ${ch.h.toFixed(1)}：把横梁/门洞抬高到 ${(ch.y0 + o.overTop * ch.h).toFixed(2)} 以上，或让角色绕开` });
    else if (total > o.pushMax) stuck.push({ who: ch.name, by, reason: '推开太远',
      hint: `${by} 把 ${ch.name} 推了 ${total.toFixed(2)}（> ${o.pushMax}）：站位写在家具外面，或者这件家具标 R.noBlock / kind:'low'` });
    else if (unresolved) stuck.push({ who: ch.name, by, reason: '推不开',
      hint: `${ch.name} 迭代 3 次还和 ${by} 重叠（比如卡进凹角）：挪站位，或把这件家具标 R.noBlock` });
  }
  // 角色两两拉开：距离 ≥ rb1 + rb2 + gap，按 mass 分配（0 = 钉住）
  for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
    const A = list[i], B = list[j];
    if (A.collide === false || B.collide === false) continue;
    const a = pos.get(A.name), b = pos.get(B.name), min = A.rb + B.rb + o.gap;
    if (opts.touchPairs && opts.touchPairs.some(([n1, n2]) => (n1 === A.name && n2 === B.name) || (n1 === B.name && n2 === A.name))) continue;
    let dx = b.x - a.x, dz = b.z - a.z, d = Math.hypot(dx, dz);
    if (d >= min) continue;
    const ux = d < 1e-6 ? 1 : dx / d, uz = d < 1e-6 ? 0 : dz / d, need = min - Math.max(d, 1e-3);
    const ma = A.mass ?? 1, mb = B.mass ?? 1, s = ma + mb;
    if (s <= 0) continue;
    const ka = ma === 0 ? 0 : (mb === 0 ? 1 : mb / s), kb = mb === 0 ? 0 : (ma === 0 ? 1 : ma / s);
    a.x -= ux * need * ka; a.z -= uz * need * ka;
    b.x += ux * need * kb; b.z += uz * need * kb;
    if (ka > 0) nudges.push({ who: A.name, by: B.name, dist: need * ka, from: null, to: [a.x, a.z] });
    if (kb > 0) nudges.push({ who: B.name, by: A.name, dist: need * kb, from: null, to: [b.x, b.z] });
  }
  return { pos, nudges, stuck };
}
