// Render dist/dashboard.html in headless Chrome and capture one screenshot per
// tab into docs/img. Uses the Chrome already installed on the machine.
import puppeteer from "puppeteer-core";
import path from "node:path";
import { pathToFileURL } from "node:url";

const CHROME = process.env.CHROME_PATH ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const file = pathToFileURL(path.resolve("dist/dashboard.html")).href;
const outDir = "docs/img";

const tabs = [
  ["insights", "01-insights.png"],
  ["overview", "02-overview.png"],
  ["content", "03-content.png"],
  ["audience", "04-audience.png"],
  ["money", "05-monetization.png"],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1900, deviceScaleFactor: 2 });

// Fresh page load per tab -> a single clean click, matching the known-good
// flow. Avoids state accumulated by clicking through tabs in one session.
for (const [tab, name] of tabs) {
  await page.goto(file, { waitUntil: "networkidle0", timeout: 60000 });
  await sleep(2500); // let the default (insights) charts settle
  if (tab !== "insights") {
    await page.click(`.tab[data-tab="${tab}"]`); // handler re-renders the pane
    await sleep(2500);
  }
  // Clip to the footer's bottom so each image is tight (no dead space).
  const height = await page.evaluate(() => {
    const f = document.querySelector(".foot");
    return Math.ceil(f.getBoundingClientRect().bottom + window.scrollY) + 18;
  });
  await page.screenshot({
    path: path.join(outDir, name),
    clip: { x: 0, y: 0, width: 1440, height },
    // Capturing beyond the viewport resizes the page, which retriggers a
    // Chart.js line-scale glitch. Keep capture inside the viewport.
    captureBeyondViewport: false,
  });
  console.log("shot", name, `${height}px`);
}

await browser.close();
console.log("done");
