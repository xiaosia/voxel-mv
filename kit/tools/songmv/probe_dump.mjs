// Read what the page reports about itself. Called by render.sh (modes act / trans / video).
//   out/page_meta.json : { TRANSITIONS }            (always)
//   out/probe.json     : window.probe(t) per frame   (unless --meta-only)
// usage: node probe_dump.mjs <lemo-opuscar dir> <project dir> [fps=24] [--meta-only]
import fs from 'fs'; import path from 'path'; import { pathToFileURL } from 'url';
const args = process.argv.slice(2), metaOnly = args.includes('--meta-only');
const [lib, dir, fpsArg] = args.filter(a => a !== '--meta-only'), FPS = +(fpsArg || 24);
const { openDemo, closeServer } = await import(pathToFileURL(path.join(path.resolve(lib), 'core/render/page.mjs')).href);
const { browser, page } = await openDemo(dir, { w: 640, h: 360, q: 'export=1' });   // small window: only the numbers matter
const done = async code => { await browser.close(); closeServer(); process.exit(code); };
fs.mkdirSync(path.join(dir, 'out'), { recursive: true });
const meta = await page.evaluate(() => ({ DUR: window.DUR, TRANSITIONS: Array.isArray(window.TRANSITIONS) ? window.TRANSITIONS : null }));
fs.writeFileSync(path.join(dir, 'out/page_meta.json'), JSON.stringify(meta, null, 1));
if (metaOnly) { console.log(`page meta: ${meta.TRANSITIONS ? meta.TRANSITIONS.length + ' transitions' : 'no window.TRANSITIONS'} -> out/page_meta.json`); await done(0); }
const has = await page.evaluate(() => typeof window.probe === 'function');
if (!has) { console.error('NO_PROBE: the page has no window.probe(t). See SKILL.md "页面契约" (copy scripts/probe.js, call mark() where characters are drawn).'); await done(4); }
const n = Math.floor(meta.DUR * FPS), frames = [];
for (let i = 0; i < n; i += 48) {
  const ts = Array.from({ length: Math.min(48, n - i) }, (_, k) => (i + k) / FPS);
  frames.push(...await page.evaluate(ts => ts.map(t => window.probe(t)), ts));
}
fs.writeFileSync(path.join(dir, 'out/probe.json'), JSON.stringify({ fps: FPS, frames }));
console.log(`probe: ${frames.length} frames, ${frames.filter(f => f.length).length} with characters -> out/probe.json`);
await done(0);
