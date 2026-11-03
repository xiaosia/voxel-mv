// 预检探针（合并 + 并行）：一遍逐帧读页面自报的数据，同时写出
//   out/probe.json     动作关 act_check.py、交接检查用（window.probe(t) 每帧一份）
//   out/voxel.json     体素关 voxel_check.py、运镜关、转场关 T8 用（window.voxelProbe(t) 每帧一份）
//   out/page_meta.json 转场关、钩子关、调色关用（window.TRANSITIONS）
// 以前是 probe_dump.mjs、voxel_dump.mjs 各开一个浏览器从头到尾各走一遍；现在分成 N 段给 N 个浏览器同时走，
// 引擎有 window.probeAll 时每帧只摆一次场景（老引擎没有就 voxelProbe + probe 各调一次，结果一样）。
// 每段开头先空跑前 2 帧再记：运镜速度（speed）要上一帧的机位，和渲染分块是同一个前提（每帧只由帧号决定）。
// usage: node probe_all.mjs <render dir> <project dir> [--workers N] [--layout]
import fs from 'fs'; import path from 'path'; import { pathToFileURL } from 'url';
const args = process.argv.slice(2);
const [lib, dir] = args.filter(a => !a.startsWith('--') && !/^\d+$/.test(a));
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const WK = Math.max(1, +opt('--workers', 4) || 1), LAYOUT = args.includes('--layout'), FPS = 24, BATCH = 48, WARM = 2;
const { openDemo, closeServer } = await import(pathToFileURL(path.join(path.resolve(lib), 'core/render/page.mjs')).href);
const t0 = Date.now();
fs.mkdirSync(path.join(dir, 'out'), { recursive: true });

const open = async () => {
  const { browser, page } = await openDemo(dir, { w: 640, h: 360, q: 'export=1' });   // 小窗口：只要数字
  if (LAYOUT) await page.evaluate(() => { window.LAYOUT = 1; });
  return { browser, page };
};
const first = await open();
const meta = await first.page.evaluate(() => ({ DUR: window.DUR, PLACEHOLDER: !!window.PLACEHOLDER, PLAN: window.PLAN,
  TRANSITIONS: Array.isArray(window.TRANSITIONS) ? window.TRANSITIONS : null,
  hasProbe: typeof window.probe === 'function', hasVoxel: typeof window.voxelProbe === 'function', hasAll: typeof window.probeAll === 'function' }));
fs.writeFileSync(path.join(dir, 'out/page_meta.json'), JSON.stringify({ DUR: meta.DUR, TRANSITIONS: meta.TRANSITIONS }, null, 1));
const quit = async code => { closeServer(); process.exit(code); };
if (!meta.hasProbe || !meta.hasVoxel) {
  console.error(`页面缺${!meta.hasProbe ? ' window.probe(t)' : ''}${!meta.hasVoxel ? ' window.voxelProbe(t)' : ''}：用 engine/relay.js 的 R.run(...) 就会有；自己改引擎时要保留它们。`);
  await first.browser.close(); await quit(4);
}

const n = Math.floor(meta.DUR * FPS), W = Math.min(WK, Math.max(1, Math.ceil(n / 240)));   // 太短的片子不值得多开浏览器
const per = Math.ceil(n / W), ranges = [...Array(W)].map((_, i) => [i * per, Math.min(n, (i + 1) * per)]).filter(([a, b]) => b > a);
const probe = new Array(n), voxel = new Array(n);
let done = 0, last = 0;

async function walk({ page }, [a, b]) {
  const grab = (ts, keep) => page.evaluate(({ ts, keep }) => ts.map(t => {
    if (window.probeAll) { const r = window.probeAll(t); return keep ? r : null; }
    const v = window.voxelProbe(t), p = window.probe(t);   // 先 voxelProbe 后 probe：下一帧 voxelProbe 读到的「上一帧机位」还是这一帧的
    return keep ? { probe: p, voxel: v } : null;
  }), { ts, keep });
  if (a > 0) await grab([...Array(Math.min(WARM, a))].map((_, k) => (a - Math.min(WARM, a) + k) / FPS), false);
  for (let i = a; i < b; i += BATCH) {
    const ts = []; for (let k = i; k < Math.min(b, i + BATCH); k++) ts.push(k / FPS);
    const rs = await grab(ts, true);
    rs.forEach((r, k) => { probe[i + k] = r.probe; voxel[i + k] = r.voxel; });
    done += rs.length;
    if (Date.now() - last > 15000) { last = Date.now(); console.log(`探针 ${done}/${n} 帧  ${((Date.now() - t0) / 1000).toFixed(0)}s`); }
  }
}

try {
  await Promise.all(ranges.map(async (r, i) => {
    const pg = i === 0 ? first : await open();
    try { await walk(pg, r); } finally { await pg.browser.close(); }
  }));
} catch (e) { console.error(`探针中断：${String(e.message || e).split('\n')[0]}`); await quit(1); }

fs.writeFileSync(path.join(dir, 'out/probe.json'), JSON.stringify({ fps: FPS, frames: probe }));
fs.writeFileSync(path.join(dir, 'out/voxel.json'), JSON.stringify({ fps: FPS, step: 1, DUR: meta.DUR, PLACEHOLDER: meta.PLACEHOLDER, has: true,
  TRANSITIONS: meta.TRANSITIONS || [], frames: voxel }));
const hasAll = meta.hasAll;
console.log(`探针：${n} 帧，${ranges.length} 个浏览器${hasAll ? '' : '（老引擎：每帧摆两次场景，升级引擎会快一倍）'}，${((Date.now() - t0) / 1000).toFixed(0)}s → out/probe.json、out/voxel.json、out/page_meta.json`);
await quit(0);
