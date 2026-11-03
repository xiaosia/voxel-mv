// 逐帧读页面自报的 window.voxelProbe(t) → out/voxel.json（体素关用）。由 tools/run.py voxel / video 调用。
// usage: node voxel_dump.mjs <render dir> <project dir> [step=1]
import fs from 'fs'; import path from 'path'; import { pathToFileURL } from 'url';
const [lib, dir, stepArg] = process.argv.slice(2), STEP = +(stepArg || 1), FPS = 24;
const { openDemo, closeServer } = await import(pathToFileURL(path.join(path.resolve(lib), 'core/render/page.mjs')).href);
const { browser, page } = await openDemo(dir, { w: 640, h: 360, q: 'export=1' });
const done = async code => { await browser.close(); closeServer(); process.exit(code); };
fs.mkdirSync(path.join(dir, 'out'), { recursive: true });
const meta = await page.evaluate(() => ({ DUR: window.DUR, PLACEHOLDER: !!window.PLACEHOLDER, has: typeof window.voxelProbe === 'function', PLAN: window.PLAN, TRANSITIONS: window.TRANSITIONS || [] }));
if (!meta.has) { console.error('NO_VOXEL_PROBE：页面没有 window.voxelProbe(t)。用 engine/relay.js 的 R.run(...) 就会有；自己改引擎时要保留它。'); await done(4); }
const n = Math.floor(meta.DUR * FPS), frames = [];
for (let i = 0; i < n; i += 48 * STEP) {
  const ts = []; for (let k = i; k < Math.min(n, i + 48 * STEP); k += STEP) ts.push(k / FPS);
  frames.push(...await page.evaluate(ts => ts.map(t => window.voxelProbe(t)), ts));
}
const { PLAN, ...rest } = meta;
fs.writeFileSync(path.join(dir, 'out/voxel.json'), JSON.stringify({ fps: FPS, step: STEP, ...rest, frames }));
console.log(`voxel probe: ${frames.length} frames -> out/voxel.json`);
await done(0);
