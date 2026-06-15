// Record a short demo GIF of the dashboard: switching tabs + toggling
// platforms. Captures frames with headless Chrome, encodes to GIF in pure JS
// (pngjs + gifenc) -- no ffmpeg/imagemagick required.
import puppeteer from "puppeteer-core";
import { PNG } from "pngjs";
import gifenc from "gifenc";
const { GIFEncoder, quantize, applyPalette } = gifenc;
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const CHROME = process.env.CHROME_PATH ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const file = pathToFileURL(path.resolve("dist/dashboard.html")).href;
const OUT = "docs/img/demo.gif";

const W = 1200, H = 760;       // capture region (header + tabs + KPIs + charts)
const SCALE = 0.78;            // downscale factor for a lighter GIF
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb"],
});
const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
await page.goto(file, { waitUntil: "networkidle0", timeout: 60000 });
await sleep(2500);

const frames = [];
async function grab(delay) {
  const buf = await page.screenshot({
    clip: { x: 0, y: 0, width: W, height: H },
    captureBeyondViewport: false,
  });
  frames.push({ buf: Buffer.from(buf), delay });
}
async function tab(name, delay = 1500) {
  await page.click(`.tab[data-tab="${name}"]`);
  await sleep(1300);
  await grab(delay);
}
async function chip(pf, delay = 1300) {
  await page.click(`.chip[data-pf="${pf}"]`);
  await sleep(1100);
  await grab(delay);
}

// --- storyboard ---
await grab(1400);            // overview
await tab("content");        // content performance
await tab("audience");       // audience growth
await tab("money");          // monetization
await tab("overview", 1200); // back to overview
await chip("tiktok");        // drop TikTok
await chip("instagram");     // drop Instagram -> YouTube only
await chip("instagram");     // bring Instagram back
await chip("tiktok", 1600);  // all three again

await browser.close();

// --- nearest-neighbour downscale RGBA ---
function downscale(src, sw, sh, scale) {
  const dw = Math.round(sw * scale), dh = Math.round(sh * scale);
  const dst = new Uint8Array(dw * dh * 4);
  for (let y = 0; y < dh; y++) {
    const sy = Math.min(sh - 1, (y / scale) | 0);
    for (let x = 0; x < dw; x++) {
      const sx = Math.min(sw - 1, (x / scale) | 0);
      const si = (sy * sw + sx) * 4, di = (y * dw + x) * 4;
      dst[di] = src[si]; dst[di + 1] = src[si + 1];
      dst[di + 2] = src[si + 2]; dst[di + 3] = src[si + 3];
    }
  }
  return { data: dst, width: dw, height: dh };
}

// --- encode GIF ---
const gif = GIFEncoder();
for (const { buf, delay } of frames) {
  const png = PNG.sync.read(buf);
  const { data, width, height } = downscale(png.data, png.width, png.height, SCALE);
  const palette = quantize(data, 256);
  const index = applyPalette(data, palette);
  gif.writeFrame(index, width, height, { palette, delay });
}
gif.finish();
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, gif.bytes());
const kb = Math.round(fs.statSync(OUT).size / 1024);
console.log(`wrote ${OUT}  (${frames.length} frames, ${kb} KB)`);
