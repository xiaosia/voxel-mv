// 逐帧读页面自报的 window.voxelProbe(t) → out/voxel.json（体素关用）。由 tools/run.py voxel / video 调用。
// usage: node voxel_dump.mjs <render dir> <project dir> [step=1] [f0:f1] [--layout] [--out <name>]
//   f0:f1 = 本片段内帧号范围（含头不含尾），check --shot 只 dump 一个镜头的帧
//   --layout = 设 window.LAYOUT=1，探针多带碰撞体（俯视图 layout_map.py 用）
import fs from 'fs'; import path from 'path'; import { pathToFileURL } from 'url';
const args = process.argv.slice(2);
const [lib, dir, stepArg, rangeArg] = args.filter(a => !a.startsWith('--'));
const flag = n => args.includes(n);
const outFile = (args.find(a => a.startsWith('--out=')) || '').split('=')[1] || 'voxel.json';
const STEP = +(stepArg || 1), FPS = 24;
const { openDemo, closeServer } = await import(pathToFileURL(path.join(path.resolve(lib), 'core/render/page.mjs')).href);
const { browser, page } = await openDemo(dir, { w: 640, h: 360, q: 'export=1' });
const done = async code => { await browser.close(); closeServer(); process.exit(code); };
fs.mkdirSync(path.join(dir, 'out'), { recursive: true });
if (flag('--layout')) await page.evaluate(() => { window.LAYOUT = 1; });
const meta = await page.evaluate(() => ({ DUR: window.DUR, PLACEHOLDER: !!window.PLACEHOLDER, has: typeof window.voxelProbe === 'function', PLAN: window.PLAN, TRANSITIONS: window.TRANSITIONS || [] }));
if (!meta.has) { console.error('NO_VOXEL_PROBE：页面没有 window.voxelProbe(t)。用 engine/relay.js 的 R.run(...) 就会有；自己改引擎时要保留它。'); await done(4); }
const n = Math.floor(meta.DUR * FPS);
let k0 = 0, k1 = n;
if (rangeArg) { [k0, k1] = rangeArg.split(':').map(v => Math.max(0, Math.min(n, Math.round(+v)))); if (k1 <= k0) { console.error(`坏范围 ${rangeArg}（帧数 ${n}）`); await done(2); } }
const frames = [];
for (let i = k0; i < k1; i += 48 * STEP) {
  const ts = []; for (let k = i; k < Math.min(k1, i + 48 * STEP); k += STEP) ts.push(k / FPS);
  frames.push(...await page.evaluate(ts => ts.map(t => window.voxelProbe(t)), ts));
}
const { PLAN, ...rest } = meta;
fs.writeFileSync(path.join(dir, 'out', outFile), JSON.stringify({ fps: FPS, step: STEP, ...rest, frames }));
console.log(`voxel probe: ${frames.length} frames${rangeArg ? ` (frames ${k0}..${k1})` : ''} -> out/${outFile}`);
await done(0);
